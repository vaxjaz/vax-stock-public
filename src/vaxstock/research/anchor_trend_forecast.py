# -*- coding: utf-8 -*-
"""Transparent dual-direction probability MVP for AI under external anchors.

This is a separate forecast target from ``conditional_group_spread``.  It
estimates both whether the point-in-time ``AI算力`` member basket will rise
and whether it will produce positive excess return over the legacy benchmark
after the current completed overseas-session context.

The primary condition is pre-registered: the majority sign of NVDA, SOXX and
QQQ.  Individual anchors are reported as marginal evidence only; they are not
naively multiplied as if independent.
"""

from __future__ import annotations

import math
from datetime import datetime
from statistics import fmean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from vaxstock.research.contracts import ContractError, canonical_digest
from vaxstock.research.global_anchor_dimension import (
    ANCHOR_CONTEXT_FACTOR_ID,
    ANCHOR_CONTEXT_FACTOR_VERSION,
    ANCHOR_CONTEXT_ENTITY_ID,
    DIMENSION as GLOBAL_ANCHOR_DIMENSION,
)
from vaxstock.research.group_outcome import merge_legacy_factor_results


FORECAST_VERSION = "anchor_ai_track_probability_v1"
SELECT_VERSION = "pre_registered_anchor_state_select_v1"
GROUP_VERSION = "point_in_time_ai_concept_basket_v1"
TARGET = "AI算力_equal_weight_dual_direction"
ABSOLUTE_TARGET = "AI算力_equal_weight_positive_return"
EXCESS_TARGET = "AI算力_equal_weight_positive_excess"
PRIMARY_BENCHMARK = "000001.SH"
DEFAULT_HORIZONS = (1, 5, 20)
PRIMARY_CONDITION = "anchor_equity_majority_direction"
MARGINAL_CONDITIONS = (
    "anchor_nvda_direction",
    "anchor_soxx_direction",
    "anchor_qqq_direction",
    "anchor_vix_direction",
)
PRIOR_STRENGTH = 5.0
POSITIVE_THRESHOLD = 0.55
NEGATIVE_THRESHOLD = 0.45
MINIMUM_TRACK_MEMBERS = 3


def _trade_date(value: Any, field: str) -> str:
    text = str(value or "").strip()
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ContractError(f"{field} must be YYYYMMDD") from exc
    return text


def _aware(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include timezone")
    return parsed


def _positive_horizon(value: Any) -> int:
    if isinstance(value, bool):
        raise ContractError("horizon must be a positive integer")
    try:
        horizon = int(value)
    except (TypeError, ValueError) as exc:
        raise ContractError("horizon must be a positive integer") from exc
    if horizon <= 0:
        raise ContractError("horizon must be a positive integer")
    return horizon


def _anchor_contexts(
    rows: Iterable[Mapping[str, Any]],
    *,
    decision_at: datetime,
) -> Dict[str, Dict[str, Any]]:
    contexts: Dict[str, Dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        if not (
            row.get("entity_type") == "market"
            and row.get("entity_id") == ANCHOR_CONTEXT_ENTITY_ID
            and row.get("dimension") == GLOBAL_ANCHOR_DIMENSION
            and row.get("factor_id") == ANCHOR_CONTEXT_FACTOR_ID
            and row.get("factor_version") == ANCHOR_CONTEXT_FACTOR_VERSION
            and row.get("quality") == "calculated"
            and _aware(row.get("calculated_at"), "anchor calculated_at")
            <= decision_at
        ):
            continue
        trade_date = _trade_date(
            row.get("as_of_trade_date"), "anchor as_of_trade_date"
        )
        value = row.get("value")
        states = value.get("states") if isinstance(value, Mapping) else None
        if not isinstance(states, Mapping):
            raise ContractError("anchor context states must be an object")
        previous = contexts.get(trade_date)
        if previous is None or (
            _aware(row["calculated_at"], "anchor calculated_at"),
            str(row["factor_value_id"]),
        ) > (
            _aware(previous["calculated_at"], "anchor calculated_at"),
            str(previous["factor_value_id"]),
        ):
            contexts[trade_date] = row
    return contexts


def _snapshot_memberships(
    snapshots: Iterable[Mapping[str, Any]],
) -> Dict[Tuple[str, str], bool]:
    memberships: Dict[Tuple[str, str], bool] = {}
    identities: Dict[Tuple[str, str], str] = {}
    for raw in snapshots:
        row = dict(raw)
        trade_date = _trade_date(
            row.get("trade_date"), "snapshot trade_date"
        )
        code = str(row.get("code") or "").strip()
        if not code:
            raise ContractError("snapshot code is required")
        concepts = row.get("concepts") or []
        if not isinstance(concepts, list):
            raise ContractError("snapshot concepts must be an array")
        is_member = "AI算力" in {
            str(concept).strip() for concept in concepts
        }
        key = (trade_date, code)
        identity = canonical_digest({
            "trade_date": trade_date,
            "code": code,
            "concepts": sorted(str(value) for value in concepts),
        })
        if key in identities and identities[key] != identity:
            raise ContractError(
                f"conflicting snapshot membership at {trade_date}/{code}"
            )
        identities[key] = identity
        memberships[key] = is_member
    return memberships


def _base_probability(wins: int, total: int) -> float:
    # Uniform Beta(1,1) base-rate prior.  The method is fixed and reported,
    # not tuned on the current sample.
    return (wins + 1.0) / (total + 2.0)


def _shrunk_probability(
    wins: int,
    total: int,
    *,
    base_probability: float,
) -> Dict[str, float]:
    alpha = wins + PRIOR_STRENGTH * base_probability
    beta = (total - wins) + PRIOR_STRENGTH * (1.0 - base_probability)
    posterior = alpha / (alpha + beta)
    variance = (
        alpha * beta
        / ((alpha + beta) ** 2 * (alpha + beta + 1.0))
    )
    # A transparent normal approximation to a 90% posterior interval.  It is
    # descriptive and is not presented as a calibrated confidence interval.
    radius = 1.6448536269514722 * math.sqrt(max(variance, 0.0))
    return {
        "mean": posterior,
        "q05_approx": max(0.0, posterior - radius),
        "q95_approx": min(1.0, posterior + radius),
    }


def _evidence_label(conditional_dates: int) -> str:
    if conditional_dates <= 0:
        return "no_matching_history"
    if conditional_dates < 5:
        return "sparse_estimate"
    if conditional_dates < 20:
        return "estimated_not_oos_validated"
    return "directional_evidence_candidate_not_oos_validated"


def _direction(
    probability: float,
    *,
    positive_label: str,
    negative_label: str,
) -> str:
    if probability >= POSITIVE_THRESHOLD:
        return positive_label
    if probability <= NEGATIVE_THRESHOLD:
        return negative_label
    return "no_edge"


def _condition_estimate(
    sessions: Sequence[Mapping[str, Any]],
    *,
    field: str,
    state: Optional[str],
    base_probability: float,
    outcome_field: str,
) -> Dict[str, Any]:
    if not state:
        return {
            "field": field,
            "state": None,
            "independent_dates": 0,
            "positive_dates": 0,
            "raw_positive_rate": None,
            "posterior_probability": None,
            "probability_lift_vs_base": None,
            "posterior_interval_90_approx": None,
            "evidence_label": "current_state_missing",
        }
    selected = [
        row for row in sessions
        if (row.get("states") or {}).get(field) == state
    ]
    wins = sum(bool(row[outcome_field]) for row in selected)
    total = len(selected)
    if total == 0:
        return {
            "field": field,
            "state": state,
            "independent_dates": 0,
            "positive_dates": 0,
            "raw_positive_rate": None,
            "posterior_probability": None,
            "probability_lift_vs_base": None,
            "posterior_interval_90_approx": None,
            "evidence_label": "no_matching_history",
        }
    posterior = _shrunk_probability(
        wins,
        total,
        base_probability=base_probability,
    )
    return {
        "field": field,
        "state": state,
        "independent_dates": total,
        "positive_dates": wins,
        "raw_positive_rate": wins / total if total else None,
        "posterior_probability": posterior["mean"],
        "probability_lift_vs_base": (
            posterior["mean"] - base_probability
        ),
        "posterior_interval_90_approx": [
            posterior["q05_approx"],
            posterior["q95_approx"],
        ],
        "evidence_label": _evidence_label(total),
    }


def _target_estimate(
    sessions: Sequence[Mapping[str, Any]],
    *,
    target: str,
    outcome_field: str,
    current_states: Mapping[str, Any],
    positive_direction: str,
    negative_direction: str,
    current_target_available: bool,
) -> Dict[str, Any]:
    wins = sum(bool(row[outcome_field]) for row in sessions)
    base_probability = _base_probability(wins, len(sessions))
    primary = _condition_estimate(
        sessions,
        field=PRIMARY_CONDITION,
        state=current_states.get(PRIMARY_CONDITION),
        base_probability=base_probability,
        outcome_field=outcome_field,
    )
    marginals = [
        _condition_estimate(
            sessions,
            field=field,
            state=current_states.get(field),
            base_probability=base_probability,
            outcome_field=outcome_field,
        )
        for field in MARGINAL_CONDITIONS
    ]
    probability = primary.get("posterior_probability")
    if not current_target_available:
        status = "abstain"
        direction = None
        direction_reason = "current_track_membership_insufficient"
        probability = None
    elif probability is None:
        status = "abstain"
        direction = None
        direction_reason = (
            "current_anchor_state_missing"
            if primary.get("state") is None
            else "no_matching_history"
        )
    else:
        status = "estimated"
        if primary["independent_dates"] < 5:
            direction = None
            direction_reason = "sparse_conditional_history"
        else:
            direction = _direction(
                float(probability),
                positive_label=positive_direction,
                negative_label=negative_direction,
            )
            direction_reason = None
    return {
        "status": status,
        "target": target,
        "direction": direction,
        "direction_reason": direction_reason,
        "probability_positive": probability,
        "probability_negative": (
            1.0 - float(probability)
            if probability is not None
            else None
        ),
        "base_probability_positive": base_probability,
        "base_independent_dates": len(sessions),
        "base_positive_dates": wins,
        "primary_condition": primary,
        "marginal_anchor_evidence": marginals,
        "evidence_label": primary["evidence_label"],
        "production_eligible": False,
    }


def build_anchor_trend_forecast(
    *,
    as_of_trade_date: str,
    decision_at: str,
    anchor_factor_rows: Iterable[Mapping[str, Any]],
    snapshots: Iterable[Mapping[str, Any]],
    factor_result_rows: Iterable[Mapping[str, Any]],
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> Dict[str, Any]:
    """Build one immutable, research-only AI track probability estimate."""

    as_of = _trade_date(as_of_trade_date, "as_of_trade_date")
    decision = _aware(decision_at, "decision_at")
    anchor_rows = [dict(row) for row in anchor_factor_rows]
    snapshot_rows = [dict(row) for row in snapshots]
    result_rows = [dict(row) for row in factor_result_rows]
    contexts = _anchor_contexts(anchor_rows, decision_at=decision)
    current = contexts.get(as_of)
    memberships = _snapshot_memberships(snapshot_rows)
    current_track_codes = sorted(
        code
        for (trade_date, code), is_member in memberships.items()
        if trade_date == as_of and is_member
    )
    current_target_available = (
        len(current_track_codes) >= MINIMUM_TRACK_MEMBERS
    )
    outcomes, outcome_merge_audit = merge_legacy_factor_results(result_rows)

    forecasts: Dict[str, Dict[str, Any]] = {}
    used_session_identities = []
    for raw_horizon in horizons:
        horizon = _positive_horizon(raw_horizon)
        sessions = []
        session_coverage = {
            "candidate_dates": 0,
            "complete_dates": 0,
            "excluded_insufficient_members": [],
            "excluded_incomplete_outcomes": [],
        }
        dates = sorted({
            trade_date
            for trade_date, _ in memberships
            if trade_date < as_of and trade_date in contexts
        })
        for trade_date in dates:
            session_coverage["candidate_dates"] += 1
            expected_codes = sorted(
                code
                for membership_date, code in memberships
                if (
                    membership_date == trade_date
                    and memberships[(membership_date, code)]
                )
            )
            if len(expected_codes) < MINIMUM_TRACK_MEMBERS:
                session_coverage["excluded_insufficient_members"].append({
                    "trade_date": trade_date,
                    "expected_member_count": len(expected_codes),
                })
                continue
            available_outcomes = {}
            for code in expected_codes:
                outcome = outcomes.get((trade_date, code, horizon))
                if (
                    outcome is not None
                    and _aware(
                        outcome["outcome_available_at"],
                        "outcome available_at",
                    )
                    <= decision
                ):
                    available_outcomes[code] = outcome
            missing_codes = sorted(
                set(expected_codes) - set(available_outcomes)
            )
            if missing_codes:
                session_coverage["excluded_incomplete_outcomes"].append({
                    "trade_date": trade_date,
                    "expected_member_count": len(expected_codes),
                    "available_member_count": len(available_outcomes),
                    "missing_codes": missing_codes,
                })
                continue
            excess_values = [
                float(available_outcomes[code]["excess_ret"])
                for code in expected_codes
            ]
            return_values = [
                float(available_outcomes[code]["ret"])
                for code in expected_codes
            ]
            context_value = contexts[trade_date].get("value") or {}
            states = context_value.get("states") or {}
            track_return = fmean(return_values)
            track_excess = fmean(excess_values)
            session = {
                "trade_date": trade_date,
                "member_count": len(excess_values),
                "member_codes": expected_codes,
                "track_return": track_return,
                "track_excess_return": track_excess,
                "positive_return": track_return > 0,
                "positive_excess": track_excess > 0,
                "states": dict(states),
                "anchor_factor_value_id": contexts[trade_date][
                    "factor_value_id"
                ],
            }
            sessions.append(session)
            session_coverage["complete_dates"] += 1
            used_session_identities.append({
                "horizon": horizon,
                "trade_date": trade_date,
                "member_count": len(excess_values),
                "member_codes": expected_codes,
                "track_return": track_return,
                "track_excess_return": track_excess,
                "anchor_factor_value_id": session[
                    "anchor_factor_value_id"
                ],
            })

        current_states = (
            dict((current.get("value") or {}).get("states") or {})
            if current is not None
            else {}
        )
        absolute = _target_estimate(
            sessions,
            target=ABSOLUTE_TARGET,
            outcome_field="positive_return",
            current_states=current_states,
            positive_direction="up",
            negative_direction="down",
            current_target_available=current_target_available,
        )
        relative = _target_estimate(
            sessions,
            target=EXCESS_TARGET,
            outcome_field="positive_excess",
            current_states=current_states,
            positive_direction="positive_excess",
            negative_direction="negative_excess",
            current_target_available=current_target_available,
        )
        status = (
            "estimated"
            if (
                absolute["status"] == "estimated"
                or relative["status"] == "estimated"
            )
            else "abstain"
        )
        forecasts[str(horizon)] = {
            "status": status,
            "horizon_sessions": horizon,
            "target": TARGET,
            "targets": {
                "absolute_return": absolute,
                "benchmark_excess": relative,
            },
            "absolute_direction": absolute["direction"],
            "probability_positive_return": absolute[
                "probability_positive"
            ],
            "direction": relative["direction"],
            "probability_positive_excess": relative[
                "probability_positive"
            ],
            "probability_negative_excess": relative[
                "probability_negative"
            ],
            "base_probability_positive_excess": relative[
                "base_probability_positive"
            ],
            "base_independent_dates": relative[
                "base_independent_dates"
            ],
            "base_positive_dates": relative["base_positive_dates"],
            "session_coverage": session_coverage,
            "primary_condition": relative["primary_condition"],
            "marginal_anchor_evidence": relative[
                "marginal_anchor_evidence"
            ],
            "abstain_reason": relative["direction_reason"],
            "evidence_label": relative["evidence_label"],
            "production_eligible": False,
        }

    current_factor_id = (
        str(current["factor_value_id"]) if current is not None else None
    )
    input_identity = {
        "as_of_trade_date": as_of,
        "decision_at": decision.isoformat(timespec="seconds"),
        "forecast_version": FORECAST_VERSION,
        "select_version": SELECT_VERSION,
        "group_version": GROUP_VERSION,
        "current_anchor_factor_value_id": current_factor_id,
        "current_track_codes": current_track_codes,
        "used_sessions": sorted(
            used_session_identities,
            key=lambda row: (
                row["horizon"],
                row["trade_date"],
            ),
        ),
    }
    return {
        "schema_version": 1,
        "as_of_trade_date": as_of,
        "decision_at": decision.isoformat(timespec="seconds"),
        "target": TARGET,
        "primary_benchmark": PRIMARY_BENCHMARK,
        "benchmark_status": (
            "legacy_available_not_ideal_industry_benchmark"
        ),
        "group_version": GROUP_VERSION,
        "select_version": SELECT_VERSION,
        "forecast_version": FORECAST_VERSION,
        "current_anchor_factor_value_id": current_factor_id,
        "current_anchor_states": (
            dict((current.get("value") or {}).get("states") or {})
            if current is not None
            else {}
        ),
        "current_track_membership": {
            "status": (
                "available"
                if current_target_available
                else "insufficient_members"
            ),
            "member_count": len(current_track_codes),
            "minimum_members": MINIMUM_TRACK_MEMBERS,
            "member_codes": current_track_codes,
            "membership_semantics": (
                "point_in_time_user_concept_labels_not_official_index"
            ),
        },
        "probability_method": {
            "model": "beta_shrinkage_to_empirical_base",
            "base_prior": "Beta(1,1)",
            "conditional_prior_strength": PRIOR_STRENGTH,
            "primary_condition": PRIMARY_CONDITION,
            "positive_threshold": POSITIVE_THRESHOLD,
            "negative_threshold": NEGATIVE_THRESHOLD,
            "interval": "normal_approximation_to_90pct_beta_posterior",
            "multiple_anchor_combination": (
                "not_executed; marginal anchors are correlated and are "
                "reported separately"
            ),
        },
        "horizons": forecasts,
        "outcome_merge_audit": outcome_merge_audit,
        "input_digest": canonical_digest(input_identity),
        "evidence_status": "estimated_not_oos_validated",
        "production_eligible": False,
        "scope": (
            "AI算力 point-in-time concept basket direction estimate; "
            "not a stock price target or portfolio action"
        ),
        "timing_semantics": (
            "decision occurs after the completed overseas session and before "
            "the next A-share open; labels use prior A-share close and are "
            "directional, not executable close-to-close returns"
        ),
    }
