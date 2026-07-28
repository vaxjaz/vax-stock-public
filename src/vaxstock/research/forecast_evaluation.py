# -*- coding: utf-8 -*-
"""Point-in-time evaluation and calibration for MR7 shadow forecasts.

The evaluation unit is one forecast date and one horizon.  The realized
target is reconstructed from the complete stock cross-section and the exact
candidate directions frozen by the forecast.  Partial stock outcomes are
never used to approximate a result.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from vaxstock.research.contracts import (
    FORECAST_CALIBRATION_SCHEMA_VERSION,
    FORECAST_RESULT_SCHEMA_VERSION,
    ContractError,
    canonical_digest,
    make_forecast_result_id,
    validate_forecast_audit,
    validate_forecast_calibration_audit,
    validate_forecast_result,
    validate_group_outcome_sample,
    validate_selection_audit,
)
from vaxstock.research.group_outcome import select_eod_group_assignments
from vaxstock.research.walk_forward_select import (
    SelectionPolicy,
    build_candidate_sessions,
)


EVALUATOR_VERSION = "selected_group_spread_eval_v1"
CALIBRATION_VERSION = "forecast_calibration_v1"
MINIMUM_EVALUATED_DATES = 20


def _aware(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include a timezone offset")
    return parsed


def _policy(selection: Mapping[str, Any]) -> SelectionPolicy:
    raw = selection.get("policy")
    if not isinstance(raw, Mapping):
        raise ContractError("selection policy is required for evaluation")
    policy = SelectionPolicy(
        min_side_stocks=raw.get("min_side_stocks"),
        min_train_dates=raw.get("min_train_dates"),
        min_oos_dates=raw.get("min_oos_dates"),
        top_k=raw.get("top_k"),
        embargo_sessions=raw.get("embargo_sessions"),
    )
    policy.validate()
    return policy


def _candidate_identity(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    training = candidate.get("training")
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "series_id": str(candidate.get("series_id") or ""),
        "axis": str(candidate.get("axis") or ""),
        "direction": candidate.get("direction"),
        "training_independent_dates": (
            training.get("independent_dates")
            if isinstance(training, Mapping)
            else candidate.get("training_independent_dates")
        ),
    }


def _verify_source_link(
    forecast_audit: Mapping[str, Any],
    selection_audit: Mapping[str, Any],
) -> None:
    validate_forecast_audit(forecast_audit)
    validate_selection_audit(selection_audit)
    for field in ("as_of_trade_date", "select_version"):
        if forecast_audit.get(field) != selection_audit.get(field):
            raise ContractError(
                f"forecast/selection {field} mismatch"
            )
    if (
        forecast_audit.get("selection_input_digest")
        != selection_audit.get("input_digest")
    ):
        raise ContractError("forecast/selection input digest mismatch")
    if _aware(
        forecast_audit.get("decision_at"), "forecast decision_at"
    ) != _aware(
        selection_audit.get("decision_at"), "selection decision_at"
    ):
        raise ContractError("forecast/selection decision_at mismatch")


def _complete_cross_section(
    *,
    as_of_trade_date: str,
    horizon_sessions: int,
    group_factor_rows: Iterable[Mapping[str, Any]],
    outcome_rows: Iterable[Mapping[str, Any]],
) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    Dict[str, Any],
]:
    groups, _ = select_eod_group_assignments(group_factor_rows)
    target_groups = {
        code: dict(row)
        for (trade_date, code), row in groups.items()
        if trade_date == as_of_trade_date
    }
    if not target_groups:
        raise ContractError(
            "forecast baseline has no EOD group cross-section"
        )

    outcomes: Dict[str, Dict[str, Any]] = {}
    for raw in outcome_rows:
        row = dict(raw)
        validate_group_outcome_sample(row)
        if (
            str(row["as_of_trade_date"]) != as_of_trade_date
            or int(row["horizon_sessions"]) != horizon_sessions
        ):
            continue
        code = str(row["code"])
        previous = outcomes.get(code)
        if (
            previous is not None
            and canonical_digest(previous) != canonical_digest(row)
        ):
            raise ContractError(
                "conflicting forecast evaluation outcome at "
                f"{as_of_trade_date}/{code}/T+{horizon_sessions}"
            )
        outcomes[code] = row

    expected_codes = set(target_groups)
    available_codes = expected_codes & set(outcomes)
    pending = {
        "horizon_sessions": horizon_sessions,
        "expected_stock_outcomes": len(expected_codes),
        "available_stock_outcomes": len(available_codes),
        "missing_codes": sorted(expected_codes - available_codes),
    }
    if available_codes != expected_codes:
        return (
            list(target_groups.values()),
            [outcomes[code] for code in sorted(available_codes)],
            pending,
        )
    extra_codes = set(outcomes) - expected_codes
    if extra_codes:
        raise ContractError(
            "forecast evaluation outcomes contain codes outside group "
            f"cross-section: {sorted(extra_codes)}"
        )
    return (
        list(target_groups.values()),
        [outcomes[code] for code in sorted(expected_codes)],
        pending,
    )


def _build_result(
    *,
    forecast_audit: Mapping[str, Any],
    forecast: Mapping[str, Any],
    selection: Mapping[str, Any],
    horizon: int,
    group_rows: Sequence[Mapping[str, Any]],
    outcome_rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    outcome_available_at = max(
        _aware(row["outcome_available_at"], "outcome_available_at")
        for row in outcome_rows
    )
    if outcome_available_at <= _aware(
        forecast["generated_at"], "forecast generated_at"
    ):
        raise ContractError(
            "forecast result must become available after forecast generation"
        )
    sessions, build_audit = build_candidate_sessions(
        group_factor_rows=group_rows,
        outcome_rows=outcome_rows,
        horizon_sessions=horizon,
        decision_at=outcome_available_at.isoformat(timespec="seconds"),
        policy=_policy(selection),
    )
    baseline = str(forecast_audit["as_of_trade_date"])
    sessions = [
        row for row in sessions
        if str(row["as_of_trade_date"]) == baseline
    ]
    by_candidate = {
        str(row["candidate_id"]): row for row in sessions
    }
    forecast_candidates = forecast.get("current_candidates")
    selection_candidates = selection.get("current_candidates")
    if (
        not isinstance(forecast_candidates, list)
        or not isinstance(selection_candidates, list)
    ):
        raise ContractError(
            "available forecast requires source candidate lists"
        )
    forecast_identities = [
        _candidate_identity(candidate)
        for candidate in forecast_candidates
        if isinstance(candidate, Mapping)
    ]
    selection_identities = [
        _candidate_identity(candidate)
        for candidate in selection_candidates
        if isinstance(candidate, Mapping)
    ]
    if (
        len(forecast_identities) != len(forecast_candidates)
        or forecast_identities != selection_identities
    ):
        raise ContractError(
            "forecast candidates do not match frozen selection candidates"
        )
    if (
        forecast.get("selection_policy_digest")
        != selection.get("policy_digest")
    ):
        raise ContractError("forecast selection policy digest mismatch")

    candidate_results = []
    for candidate in forecast_identities:
        session = by_candidate.get(candidate["candidate_id"])
        if session is None:
            raise ContractError(
                "selected candidate lacks a complete current cross-section: "
                f"{candidate['candidate_id']}"
            )
        if (
            session["series_id"] != candidate["series_id"]
            or session["axis"] != candidate["axis"]
        ):
            raise ContractError(
                "selected candidate identity changed at evaluation"
            )
        raw_spread = float(session["spread"])
        direction = int(candidate["direction"])
        candidate_results.append({
            **candidate,
            "positive_state": session["positive_state"],
            "negative_state": session["negative_state"],
            "positive_n": int(session["positive_n"]),
            "negative_n": int(session["negative_n"]),
            "raw_group_spread": raw_spread,
            "direction_adjusted_spread": direction * raw_spread,
        })
    actual = statistics.fmean(
        row["direction_adjusted_spread"] for row in candidate_results
    )
    distribution = forecast.get("distribution")
    if not isinstance(distribution, Mapping):
        raise ContractError(
            "available forecast is missing its empirical distribution"
        )
    expected = float(forecast["expected_excess_return"])
    predicted_direction = str(forecast["direction"])
    signed_error = actual - expected
    outcome_dates = {
        str(row["outcome_trade_date"]) for row in outcome_rows
    }
    if len(outcome_dates) != 1:
        raise ContractError(
            "forecast result cross-section has mixed outcome dates"
        )
    group_ids = sorted(
        str(row["factor_value_id"]) for row in group_rows
    )
    outcome_ids = sorted(
        str(row["outcome_id"]) for row in outcome_rows
    )
    input_digest = canonical_digest({
        "forecast_input_digest": forecast["input_digest"],
        "forecast_audit_input_digest": forecast_audit["input_digest"],
        "selection_input_digest": forecast_audit[
            "selection_input_digest"
        ],
        "predicted_direction": predicted_direction,
        "expected_spread": expected,
        "confidence": float(forecast["confidence"]),
        "forecast_distribution": {
            field: distribution[field]
            for field in (
                "independent_oos_dates",
                "q10",
                "q25",
                "median",
                "q75",
                "q90",
                "unit",
            )
        },
        "group_factor_value_ids": group_ids,
        "group_outcome_ids": outcome_ids,
        "candidate_results": candidate_results,
        "outcome_trade_date": next(iter(outcome_dates)),
        "outcome_available_at": outcome_available_at.isoformat(
            timespec="seconds"
        ),
    })
    result = {
        "schema_version": FORECAST_RESULT_SCHEMA_VERSION,
        "result_id": "",
        "as_of_trade_date": baseline,
        "horizon_sessions": horizon,
        "outcome_trade_date": next(iter(outcome_dates)),
        "outcome_available_at": outcome_available_at.isoformat(
            timespec="seconds"
        ),
        "evaluated_at": outcome_available_at.isoformat(
            timespec="seconds"
        ),
        "select_version": str(forecast["select_version"]),
        "forecast_version": str(forecast["forecast_version"]),
        "evaluator_version": EVALUATOR_VERSION,
        "forecast_input_digest": str(forecast["input_digest"]),
        "forecast_audit_input_digest": str(
            forecast_audit["input_digest"]
        ),
        "selection_input_digest": str(
            forecast_audit["selection_input_digest"]
        ),
        "target": str(forecast["target"]),
        "strategy": str(forecast["strategy"]),
        "predicted_direction": predicted_direction,
        "expected_spread": expected,
        "confidence": float(forecast["confidence"]),
        "actual_selected_group_spread": actual,
        "direction_hit": (
            actual > 0
            if predicted_direction == "positive_spread"
            else actual < 0
        ),
        "signed_error": signed_error,
        "absolute_error": abs(signed_error),
        "within_q25_q75": (
            float(distribution["q25"])
            <= actual
            <= float(distribution["q75"])
        ),
        "within_q10_q90": (
            float(distribution["q10"])
            <= actual
            <= float(distribution["q90"])
        ),
        "forecast_distribution": {
            field: distribution[field]
            for field in (
                "independent_oos_dates",
                "q10",
                "q25",
                "median",
                "q75",
                "q90",
                "unit",
            )
        },
        "candidate_results": candidate_results,
        "group_factor_value_ids": group_ids,
        "group_outcome_ids": outcome_ids,
        "cross_section_audit": {
            "expected_stock_outcomes": len(group_rows),
            "candidate_session_rows": build_audit[
                "candidate_session_rows"
            ],
            "statistical_unit": build_audit["statistical_unit"],
        },
        "input_digest": input_digest,
        "production_eligible": False,
        "promotion_status": "manual_review_required",
    }
    result["result_id"] = make_forecast_result_id(result)
    validate_forecast_result(result)
    return result


def evaluate_forecast_audit(
    *,
    forecast_audit: Mapping[str, Any],
    selection_audit: Mapping[str, Any],
    group_factor_rows: Iterable[Mapping[str, Any]],
    outcome_rows: Iterable[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Evaluate every matured available horizon in one forecast audit."""

    _verify_source_link(forecast_audit, selection_audit)
    groups = [dict(row) for row in group_factor_rows]
    outcomes = [dict(row) for row in outcome_rows]
    baseline = str(forecast_audit["as_of_trade_date"])
    results = []
    pending = {}
    counts = Counter()
    for raw_horizon in sorted(
        forecast_audit["forecasts"], key=lambda value: int(value)
    ):
        horizon = int(raw_horizon)
        forecast = forecast_audit["forecasts"][raw_horizon]
        selection_box = selection_audit["horizons"].get(
            str(horizon)
        )
        if not isinstance(selection_box, Mapping):
            raise ContractError(
                f"selection is missing T+{horizon} source"
            )
        selection = selection_box.get("selection")
        if not isinstance(selection, Mapping):
            raise ContractError(
                f"selection T+{horizon} source is invalid"
            )
        if forecast["status"] == "abstain":
            counts["abstain"] += 1
            continue
        if selection.get("status") != "shadow_candidate":
            raise ContractError(
                "available forecast requires shadow candidate selection"
            )
        counts["available"] += 1
        target_groups, target_outcomes, pending_box = (
            _complete_cross_section(
                as_of_trade_date=baseline,
                horizon_sessions=horizon,
                group_factor_rows=groups,
                outcome_rows=outcomes,
            )
        )
        if pending_box["missing_codes"]:
            counts["pending"] += 1
            pending[str(horizon)] = {
                **pending_box,
                "reason": "incomplete_stock_cross_section",
            }
            continue
        result = _build_result(
            forecast_audit=forecast_audit,
            forecast=forecast,
            selection=selection,
            horizon=horizon,
            group_rows=target_groups,
            outcome_rows=target_outcomes,
        )
        results.append(result)
        counts["evaluated"] += 1
    return results, {
        "as_of_trade_date": baseline,
        "forecast_audit_input_digest": forecast_audit["input_digest"],
        "available_forecasts": counts["available"],
        "abstain_forecasts": counts["abstain"],
        "evaluated_forecasts": counts["evaluated"],
        "pending_forecasts": counts["pending"],
        "pending": pending,
        "statistical_unit": "one_forecast_date_per_horizon",
    }


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def build_calibration_audit(
    *,
    forecast_audits: Iterable[Mapping[str, Any]],
    result_rows: Iterable[Mapping[str, Any]],
    as_of_trade_date: str,
    decision_at: str,
    select_version: str,
    forecast_version: str,
    minimum_evaluated_dates: int = MINIMUM_EVALUATED_DATES,
) -> Dict[str, Any]:
    """Build a point-in-time, per-horizon calibration snapshot."""

    try:
        datetime.strptime(str(as_of_trade_date), "%Y%m%d")
    except ValueError as exc:
        raise ContractError("as_of_trade_date must be YYYYMMDD") from exc
    cutoff = _aware(decision_at, "decision_at")
    if (
        isinstance(minimum_evaluated_dates, bool)
        or not isinstance(minimum_evaluated_dates, int)
        or minimum_evaluated_dates <= 0
    ):
        raise ContractError(
            "minimum_evaluated_dates must be a positive integer"
        )
    audits = []
    forecast_by_key = {}
    for raw in forecast_audits:
        audit = dict(raw)
        validate_forecast_audit(audit)
        if (
            audit["select_version"] != select_version
            or audit["forecast_version"] != forecast_version
            or str(audit["as_of_trade_date"]) > str(as_of_trade_date)
            or _aware(audit["decision_at"], "forecast decision_at") > cutoff
        ):
            continue
        audits.append(audit)
        for raw_horizon, forecast in audit["forecasts"].items():
            key = (
                str(audit["as_of_trade_date"]),
                int(raw_horizon),
                str(forecast["input_digest"]),
            )
            if key in forecast_by_key:
                raise ContractError(
                    f"duplicate forecast identity in calibration: {key}"
                )
            forecast_by_key[key] = {
                "forecast": forecast,
                "forecast_audit_input_digest": audit["input_digest"],
                "selection_input_digest": audit[
                    "selection_input_digest"
                ],
            }

    visible_results = []
    result_by_key = {}
    for raw in result_rows:
        result = dict(raw)
        validate_forecast_result(result)
        if (
            result["select_version"] != select_version
            or result["forecast_version"] != forecast_version
            or result["evaluator_version"] != EVALUATOR_VERSION
            or str(result["outcome_trade_date"]) > str(as_of_trade_date)
            or _aware(
                result["outcome_available_at"], "outcome_available_at"
            ) > cutoff
        ):
            continue
        key = (
            str(result["as_of_trade_date"]),
            int(result["horizon_sessions"]),
            str(result["forecast_input_digest"]),
        )
        source = forecast_by_key.get(key)
        if source is None:
            raise ContractError(
                "forecast result has no visible source forecast"
            )
        forecast = source["forecast"]
        if forecast["status"] != "available":
            raise ContractError(
                "abstain forecast cannot have an evaluated result"
            )
        if (
            result["forecast_audit_input_digest"]
            != source["forecast_audit_input_digest"]
            or result["selection_input_digest"]
            != source["selection_input_digest"]
        ):
            raise ContractError(
                "forecast result source audit digest mismatch"
            )
        previous = result_by_key.get(key)
        if (
            previous is not None
            and canonical_digest(previous) != canonical_digest(result)
        ):
            raise ContractError(
                f"conflicting forecast result in calibration: {key}"
            )
        result_by_key[key] = result
        visible_results.append(result)

    horizons = defaultdict(lambda: {
        "forecasts": [],
        "results": [],
    })
    for key, source in forecast_by_key.items():
        horizons[key[1]]["forecasts"].append(source["forecast"])
    for result in result_by_key.values():
        horizons[int(result["horizon_sessions"])]["results"].append(result)

    horizon_metrics = {}
    threshold_reached = False
    for horizon in sorted(horizons):
        forecasts = horizons[horizon]["forecasts"]
        results = horizons[horizon]["results"]
        available = sum(
            forecast["status"] == "available" for forecast in forecasts
        )
        abstain = len(forecasts) - available
        evaluated = len(results)
        pending = available - evaluated
        if pending < 0:
            raise ContractError(
                "evaluated forecast count exceeds available forecasts"
            )
        threshold_reached = (
            threshold_reached or evaluated >= minimum_evaluated_dates
        )
        actual = [
            float(result["actual_selected_group_spread"])
            for result in results
        ]
        signed_error = [
            float(result["signed_error"]) for result in results
        ]
        absolute_error = [
            float(result["absolute_error"]) for result in results
        ]
        metric_status = (
            "no_available_forecasts"
            if available == 0
            else (
                "shadow_sample_threshold_reached"
                if evaluated >= minimum_evaluated_dates
                else "insufficient_evaluated_dates"
            )
        )
        horizon_metrics[str(horizon)] = {
            "forecast_dates": len(forecasts),
            "available_forecasts": available,
            "abstain_forecasts": abstain,
            "evaluated_dates": evaluated,
            "pending_available": pending,
            "direction_hit_rate": (
                sum(result["direction_hit"] for result in results)
                / evaluated
                if evaluated
                else None
            ),
            "mean_actual_spread": _mean(actual),
            "mean_signed_error": _mean(signed_error),
            "mean_absolute_error": _mean(absolute_error),
            "q25_q75_coverage": (
                sum(result["within_q25_q75"] for result in results)
                / evaluated
                if evaluated
                else None
            ),
            "q10_q90_coverage": (
                sum(result["within_q10_q90"] for result in results)
                / evaluated
                if evaluated
                else None
            ),
            "evidence_status": metric_status,
            "statistical_unit": "one_forecast_date",
        }
    available_total = sum(
        metrics["available_forecasts"]
        for metrics in horizon_metrics.values()
    )
    status = (
        "no_available_forecasts"
        if available_total == 0
        else (
            "shadow_sample_threshold_reached"
            if threshold_reached
            else "insufficient_evaluated_dates"
        )
    )
    forecast_digests = sorted({
        str(audit["input_digest"]) for audit in audits
    })
    result_ids = sorted({
        str(result["result_id"]) for result in visible_results
    })
    normalized_decision = cutoff.isoformat(timespec="seconds")
    input_digest = canonical_digest({
        "as_of_trade_date": str(as_of_trade_date),
        "decision_at": normalized_decision,
        "select_version": select_version,
        "forecast_version": forecast_version,
        "evaluator_version": EVALUATOR_VERSION,
        "calibration_version": CALIBRATION_VERSION,
        "minimum_evaluated_dates": minimum_evaluated_dates,
        "status": status,
        "horizons": dict(
            sorted(horizon_metrics.items(), key=lambda item: int(item[0]))
        ),
        "forecast_audit_input_digests": forecast_digests,
        "result_ids": result_ids,
    })
    audit = {
        "schema_version": FORECAST_CALIBRATION_SCHEMA_VERSION,
        "as_of_trade_date": str(as_of_trade_date),
        "decision_at": normalized_decision,
        "select_version": str(select_version),
        "forecast_version": str(forecast_version),
        "evaluator_version": EVALUATOR_VERSION,
        "calibration_version": CALIBRATION_VERSION,
        "minimum_evaluated_dates": minimum_evaluated_dates,
        "status": status,
        "horizons": dict(
            sorted(horizon_metrics.items(), key=lambda item: int(item[0]))
        ),
        "forecast_audit_input_digests": forecast_digests,
        "result_ids": result_ids,
        "input_digest": input_digest,
        "production_eligible": False,
        "promotion_status": "manual_review_required",
        "scope": (
            "shadow selected-group-spread calibration; metrics are shown "
            "at every N but do not establish factor effectiveness"
        ),
    }
    validate_forecast_calibration_audit(audit)
    return audit


def render_calibration_markdown(
    audit: Mapping[str, Any],
) -> str:
    """Render the audit as a compact human-readable research report."""

    validate_forecast_calibration_audit(audit)
    lines = [
        "# Research v2 Forecast Calibration",
        "",
        f"- as_of_trade_date: `{audit['as_of_trade_date']}`",
        f"- decision_at: `{audit['decision_at']}`",
        f"- status: `{audit['status']}`",
        f"- select_version: `{audit['select_version']}`",
        f"- forecast_version: `{audit['forecast_version']}`",
        "- production_eligible: `false`",
        "",
        "| Horizon | Forecasts | Available | Abstain | Evaluated | Pending | "
        "Direction hit | MAE | Q10-Q90 coverage | Evidence |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for horizon in sorted(audit["horizons"], key=lambda value: int(value)):
        metrics = audit["horizons"][horizon]
        def fmt(value: Any) -> str:
            return "NA" if value is None else f"{float(value):.4f}"

        lines.append(
            f"| T+{horizon} | {metrics['forecast_dates']} | "
            f"{metrics['available_forecasts']} | "
            f"{metrics['abstain_forecasts']} | "
            f"{metrics['evaluated_dates']} | "
            f"{metrics['pending_available']} | "
            f"{fmt(metrics['direction_hit_rate'])} | "
            f"{fmt(metrics['mean_absolute_error'])} | "
            f"{fmt(metrics['q10_q90_coverage'])} | "
            f"{metrics['evidence_status']} |"
        )
    lines.extend([
        "",
        "说明：一个独立样本等于一个 forecast date × horizon；逐股票行不作为"
        "独立样本。所有 N 均展示，但达到样本门槛也只进入人工复核，不自动认定"
        "因子有效。",
        "",
    ])
    return "\n".join(lines)
