# -*- coding: utf-8 -*-
"""Point-in-time walk-forward selection over MR5 group state spreads.

The statistical unit is one complete daily cross-section, never one stock
row.  Every available factor series is tested through its cross-sectional
state, all five causal-curve states, and available track-relative states.
The same atomic candidates are also tested separately inside each first-order
market, macro, and systemic-event context.  High-order interactions are not
executed until the independent-date count can support them.

This module can rank shadow candidates, but it cannot promote a factor to
``effective`` or alter a production action.  Thin history produces an
explicit abstention.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from vaxstock.research.contracts import (
    ContractError,
    SELECTION_AUDIT_SCHEMA_VERSION,
    canonical_digest,
    validate_selection_audit,
    validate_group_outcome_sample,
)
from vaxstock.research.group_outcome import select_eod_group_assignments


SELECT_VERSION = "walk_forward_group_spread_v4"
DEFAULT_HORIZONS = (1, 3, 5, 10, 20)
EXPLORATORY_WINDOWS = (5, 10, 20)
EXPLORATORY_REPORT_LIMIT = 20
AXIS_SIDES = {
    "cross_section_bucket": ("high", "low"),
    "curve_slope": ("up", "down"),
    "curve_acceleration": ("up", "down"),
    "curve_turning": ("up", "down"),
    "curve_anomaly": ("positive", "negative"),
    "curve_change_point": ("up", "down"),
    "curve_event_presence": ("event", "quiet"),
    "curve_event_direction": ("positive", "negative"),
    "track_level_relation": ("above", "below"),
    "track_slope_relation": ("above", "below"),
}
CONDITION_FIELDS = (
    "market_regime",
    "macro_regime",
    "systemic_event_state",
    "systemic_event_direction",
    "anchor_nvda_direction",
    "anchor_soxx_direction",
    "anchor_qqq_direction",
    "anchor_vix_direction",
    "anchor_equity_majority_direction",
)
ANCHOR_CONDITION_FIELDS = {
    "anchor_nvda_direction",
    "anchor_soxx_direction",
    "anchor_qqq_direction",
    "anchor_vix_direction",
    "anchor_equity_majority_direction",
}
ANCHOR_RELATION_REGISTRY_VERSION = "anchor_relation_registry_v1"
ANCHOR_RELATION_CONCEPTS = {
    "anchor_nvda_direction": {
        "AI算力", "服务器", "AI硬件", "AI芯片",
    },
    "anchor_soxx_direction": {
        "AI算力", "AI芯片", "半导体", "半导体设备", "半导体材料",
    },
    "anchor_qqq_direction": {
        "AI算力", "AI硬件", "AI芯片", "IDC",
    },
    "anchor_vix_direction": {
        "AI算力", "AI硬件", "AI芯片", "服务器", "半导体", "IDC",
    },
    "anchor_equity_majority_direction": {
        "AI算力", "AI硬件", "AI芯片", "服务器", "半导体", "IDC",
    },
}


@dataclass(frozen=True)
class SelectionPolicy:
    """Versioned research guardrails, not empirically proven thresholds."""

    min_side_stocks: int = 3
    min_train_dates: int = 40
    min_oos_dates: int = 20
    top_k: int = 3
    embargo_sessions: Optional[int] = None

    def validate(self) -> None:
        for field in (
            "min_side_stocks",
            "min_train_dates",
            "min_oos_dates",
            "top_k",
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ContractError(f"{field} must be a positive integer")
        if (
            self.embargo_sessions is not None
            and (
                isinstance(self.embargo_sessions, bool)
                or not isinstance(self.embargo_sessions, int)
                or self.embargo_sessions < 0
            )
        ):
            raise ContractError(
                "embargo_sessions must be a non-negative integer or None"
            )


def policy_digest(policy: SelectionPolicy, horizon: int) -> str:
    policy.validate()
    return canonical_digest({
        "select_version": SELECT_VERSION,
        "horizon_sessions": _positive_horizon(horizon),
        "policy": asdict(policy),
        "candidate_axes": [
            "cross_section_bucket:high-low",
            "curve_slope:up-down",
            "curve_acceleration:up-down",
            "curve_turning:up-down",
            "curve_anomaly:positive-negative",
            "curve_change_point:up-down",
            "curve_event_presence:event-quiet",
            "curve_event_direction:positive-negative",
            "track_level_relation:above-below",
            "track_slope_relation:above-below",
        ],
        "conditioning": {
            "mode": "unconditional_plus_each_first_order_context",
            "fields": list(CONDITION_FIELDS),
            "high_order_interactions": "not_executed",
            "anchor_relation_registry_version": (
                ANCHOR_RELATION_REGISTRY_VERSION
            ),
            "anchor_relation_concepts": {
                field: sorted(concepts)
                for field, concepts in sorted(
                    ANCHOR_RELATION_CONCEPTS.items()
                )
            },
        },
        "statistical_unit": "complete_daily_cross_section",
        "exploratory_diagnostics": {
            "windows": list(EXPLORATORY_WINDOWS),
            "report_limit_per_finding_type": EXPLORATORY_REPORT_LIMIT,
            "forecast_eligible": False,
        },
    })


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


def _aware(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include a timezone offset")
    return parsed


def _candidate_id(
    axis: str,
    series_id: str,
    *,
    concept: Optional[str] = None,
    condition: Optional[Mapping[str, str]] = None,
) -> str:
    identity = {
        "axis": axis,
        "series_id": series_id,
        "concept": concept,
        "condition": dict(condition or {}),
    }
    return f"candidate_{canonical_digest(identity)}"


def _event_direction(event: str) -> Optional[str]:
    for suffix in ("positive", "negative", "up", "down"):
        if event.endswith(f"_{suffix}"):
            return suffix
    return None


def _candidate_states(
    group: Mapping[str, Any],
) -> Iterable[Dict[str, Any]]:
    """Yield all legal atomic axes plus each first-order context."""

    value = group.get("value")
    factor_groups = (
        value.get("factor_groups")
        if isinstance(value, Mapping)
        else None
    )
    if not isinstance(factor_groups, Mapping):
        raise ContractError("stock group factor_groups must be an object")
    raw_context = value.get("selection_context")
    if raw_context is None:
        raw_context = {}
    if not isinstance(raw_context, Mapping):
        raise ContractError("stock selection_context must be an object")
    contexts = {
        field: str(raw_context[field]).strip()
        for field in CONDITION_FIELDS
        if raw_context.get(field) is not None
        and str(raw_context.get(field)).strip()
    }

    def candidates(
        *,
        axis: str,
        series_id: str,
        side: str,
        concept: Optional[str] = None,
    ) -> Iterable[Dict[str, Any]]:
        if axis not in AXIS_SIDES or side not in AXIS_SIDES[axis]:
            return
        variants: List[Optional[Dict[str, str]]] = [None]
        variants.extend(
            {field: contexts[field]}
            for field in sorted(contexts)
            if (
                field not in ANCHOR_CONDITION_FIELDS
                or (
                    concept is not None
                    and str(concept)
                    in ANCHOR_RELATION_CONCEPTS.get(field, set())
                )
            )
        )
        for condition in variants:
            yield {
                "candidate_id": _candidate_id(
                    axis,
                    series_id,
                    concept=concept,
                    condition=condition,
                ),
                "axis": axis,
                "series_id": series_id,
                "concept": concept,
                "condition": dict(condition or {}),
                "side": side,
            }

    for raw_series_id, raw_state in sorted(factor_groups.items()):
        series_id = str(raw_series_id)
        if not isinstance(raw_state, Mapping):
            raise ContractError("stock factor-group state must be an object")
        cross = raw_state.get("cross_section")
        if isinstance(cross, Mapping) and cross.get("status") == "available":
            bucket = cross.get("bucket")
            if bucket in AXIS_SIDES["cross_section_bucket"]:
                yield from candidates(
                    axis="cross_section_bucket",
                    series_id=series_id,
                    side=str(bucket),
                )

        curve = raw_state.get("curve_state_vector")
        if curve is not None:
            if not isinstance(curve, Sequence) or isinstance(
                curve, (str, bytes)
            ):
                raise ContractError("curve_state_vector must be an array")
            for index, axis in (
                (0, "curve_slope"),
                (1, "curve_acceleration"),
                (2, "curve_turning"),
                (3, "curve_anomaly"),
                (4, "curve_change_point"),
            ):
                state = curve[index] if len(curve) > index else None
                if state in AXIS_SIDES[axis]:
                    yield from candidates(
                        axis=axis,
                        series_id=series_id,
                        side=str(state),
                    )

        event_ready = raw_state.get("curve_event_detection_ready")
        if event_ready is not None and not isinstance(event_ready, bool):
            raise ContractError(
                "curve_event_detection_ready must be boolean or null"
            )
        raw_events = raw_state.get("curve_candidate_events")
        if raw_events is None:
            raw_events = []
        if not isinstance(raw_events, list):
            raise ContractError("curve_candidate_events must be an array")
        events = [
            str(event).strip()
            for event in raw_events
            if str(event).strip()
        ]
        if event_ready:
            yield from candidates(
                axis="curve_event_presence",
                series_id=series_id,
                side="event" if events else "quiet",
            )
            event_directions = {
                (
                    "positive"
                    if direction in {"positive", "up"}
                    else "negative"
                )
                for direction in (
                    _event_direction(event) for event in events
                )
                if direction in {"positive", "negative", "up", "down"}
            }
            if len(event_directions) == 1:
                yield from candidates(
                    axis="curve_event_direction",
                    series_id=series_id,
                    side=next(iter(event_directions)),
                )

        track_relations = raw_state.get("track_relation_vectors") or {}
        if not isinstance(track_relations, Mapping):
            raise ContractError("track_relation_vectors must be an object")
        for concept, relation in sorted(track_relations.items()):
            if not isinstance(relation, Sequence) or isinstance(
                relation, (str, bytes)
            ):
                raise ContractError("track relation vector must be an array")
            for index, axis in (
                (0, "track_level_relation"),
                (1, "track_slope_relation"),
            ):
                state = relation[index] if len(relation) > index else None
                if state in AXIS_SIDES[axis]:
                    yield from candidates(
                        axis=axis,
                        series_id=series_id,
                        side=str(state),
                        concept=str(concept),
                    )


def build_candidate_sessions(
    *,
    group_factor_rows: Iterable[Mapping[str, Any]],
    outcome_rows: Iterable[Mapping[str, Any]],
    horizon_sessions: int,
    decision_at: str,
    policy: SelectionPolicy = SelectionPolicy(),
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Build one independent cross-sectional spread per date and candidate."""

    policy.validate()
    horizon = _positive_horizon(horizon_sessions)
    final_decision = _aware(decision_at, "decision_at")
    groups, group_audit = select_eod_group_assignments(group_factor_rows)
    groups = {
        key: row
        for key, row in groups.items()
        if _aware(row.get("calculated_at"), "group calculated_at")
        <= final_decision
    }
    expected_codes: Dict[str, set] = defaultdict(set)
    decision_times: Dict[str, datetime] = {}
    for (trade_date, code), group in groups.items():
        expected_codes[trade_date].add(code)
        calculated = _aware(group.get("calculated_at"), "group calculated_at")
        previous = decision_times.get(trade_date)
        decision_times[trade_date] = max(previous, calculated) if previous else calculated

    outcomes: Dict[Tuple[str, str], Dict[str, Any]] = {}
    outcome_conflicts = 0
    superseded_outcomes_excluded = 0
    for raw in outcome_rows:
        row = dict(raw)
        validate_group_outcome_sample(row)
        if int(row["horizon_sessions"]) != horizon:
            continue
        if _aware(row["outcome_available_at"], "outcome_available_at") > final_decision:
            continue
        key = (str(row["as_of_trade_date"]), str(row["code"]))
        group = groups.get(key)
        if group is None:
            continue
        group_value = group.get("value")
        current_group_version = (
            group_value.get("group_version")
            if isinstance(group_value, Mapping)
            else None
        )
        if (
            row.get("group_version") != current_group_version
            or row.get("group_factor_version") != group.get("factor_version")
        ):
            superseded_outcomes_excluded += 1
            continue
        if row.get("group_factor_value_id") != group.get("factor_value_id"):
            outcome_conflicts += 1
            raise ContractError(
                "group outcome points to a different current-version group "
                f"at {key[0]}/{key[1]}/T+{horizon}"
            )
        previous = outcomes.get(key)
        if previous is not None:
            if canonical_digest(previous) != canonical_digest(row):
                outcome_conflicts += 1
                raise ContractError(
                    f"conflicting group outcome for {key[0]}/{key[1]}/T+{horizon}"
                )
            continue
        outcomes[key] = row

    all_series = set()
    for group in groups.values():
        value = group.get("value")
        factor_groups = (
            value.get("factor_groups")
            if isinstance(value, Mapping)
            else None
        )
        if not isinstance(factor_groups, Mapping):
            raise ContractError("stock group factor_groups must be an object")
        all_series.update(str(series_id) for series_id in factor_groups)

    candidate_catalog: Dict[str, Dict[str, Any]] = {}
    sessions: List[Dict[str, Any]] = []
    incomplete_dates = {}
    usable_dates = 0
    side_failures = 0
    side_failures_by_axis = Counter()
    for trade_date in sorted(expected_codes):
        codes = expected_codes[trade_date]
        available_codes = {
            code for code in codes if (trade_date, code) in outcomes
        }
        if available_codes != codes:
            incomplete_dates[trade_date] = {
                "expected": len(codes),
                "available": len(available_codes),
            }
            continue
        usable_dates += 1
        date_outcomes = {
            code: outcomes[(trade_date, code)] for code in sorted(codes)
        }
        outcome_dates = {
            str(row["outcome_trade_date"]) for row in date_outcomes.values()
        }
        if len(outcome_dates) != 1:
            raise ContractError(
                f"cross-section outcome date mismatch at {trade_date}/T+{horizon}"
            )
        available_at = max(
            _aware(row["outcome_available_at"], "outcome_available_at")
            for row in date_outcomes.values()
        )
        sides: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for code, outcome in date_outcomes.items():
            group = groups[(trade_date, code)]
            if outcome["group_factor_value_id"] != group["factor_value_id"]:
                raise ContractError(
                    f"group identity mismatch at {trade_date}/{code}/T+{horizon}"
                )
            for candidate in _candidate_states(group):
                candidate_id = str(candidate["candidate_id"])
                side = str(candidate["side"])
                sides[candidate_id][side].append(float(outcome["excess_ret"]))
                identity = {
                    "candidate_id": candidate_id,
                    "series_id": str(candidate["series_id"]),
                    "axis": str(candidate["axis"]),
                    "concept": candidate.get("concept"),
                    "condition": dict(candidate.get("condition") or {}),
                }
                previous = candidate_catalog.get(candidate_id)
                if (
                    previous is not None
                    and canonical_digest(previous) != canonical_digest(identity)
                ):
                    raise ContractError(
                        f"candidate identity collision: {candidate_id}"
                    )
                candidate_catalog[candidate_id] = identity

        for candidate_id in sorted(sides):
            identity = candidate_catalog[candidate_id]
            axis = identity["axis"]
            positive, negative = AXIS_SIDES[axis]
            positive_values = sides[candidate_id].get(positive, [])
            negative_values = sides[candidate_id].get(negative, [])
            if (
                len(positive_values) < policy.min_side_stocks
                or len(negative_values) < policy.min_side_stocks
            ):
                side_failures += 1
                side_failures_by_axis[axis] += 1
                continue
            sessions.append({
                "candidate_id": candidate_id,
                "series_id": identity["series_id"],
                "axis": axis,
                "concept": identity["concept"],
                "condition": identity["condition"],
                "positive_state": positive,
                "negative_state": negative,
                "as_of_trade_date": trade_date,
                "outcome_trade_date": next(iter(outcome_dates)),
                "outcome_available_at": available_at.isoformat(
                    timespec="seconds"
                ),
                "decision_at": decision_times[trade_date].isoformat(
                    timespec="seconds"
                ),
                "horizon_sessions": horizon,
                "positive_n": len(positive_values),
                "negative_n": len(negative_values),
                "positive_mean_excess": statistics.fmean(positive_values),
                "negative_mean_excess": statistics.fmean(negative_values),
                "spread": (
                    statistics.fmean(positive_values)
                    - statistics.fmean(negative_values)
                ),
                "statistical_unit": "complete_daily_cross_section",
            })

    candidate_counts = Counter(row["candidate_id"] for row in sessions)
    catalog_rows = []
    axis_candidate_counts = Counter()
    axis_session_rows = Counter()
    for candidate_id in sorted(candidate_catalog):
        identity = candidate_catalog[candidate_id]
        independent_dates = int(candidate_counts.get(candidate_id, 0))
        axis_candidate_counts[identity["axis"]] += 1
        axis_session_rows[identity["axis"]] += independent_dates
        catalog_rows.append({
            **identity,
            "independent_dates": independent_dates,
            "status": (
                "tested"
                if independent_dates
                else "no_complete_sided_sessions"
            ),
        })

    factor_coverage = []
    for series_id in sorted(all_series):
        candidates = [
            row for row in catalog_rows if row["series_id"] == series_id
        ]
        complete_sessions = sum(
            int(row["independent_dates"]) for row in candidates
        )
        factor_coverage.append({
            "series_id": series_id,
            "candidate_axes_seen": sorted({
                str(row["axis"]) for row in candidates
            }),
            "candidate_ids": sorted(
                str(row["candidate_id"]) for row in candidates
            ),
            "complete_candidate_sessions": complete_sessions,
            "status": (
                "tested"
                if complete_sessions
                else "unavailable_or_one_sided"
            ),
        })
    return sessions, {
        "horizon_sessions": horizon,
        "decision_at": final_decision.isoformat(timespec="seconds"),
        "group_audit": group_audit,
        "group_trade_dates": len(expected_codes),
        "complete_outcome_trade_dates": usable_dates,
        "incomplete_outcome_trade_dates": len(incomplete_dates),
        "incomplete_by_trade_date": incomplete_dates,
        "candidate_session_rows": len(sessions),
        "candidate_tests": len(candidate_counts),
        "candidate_independent_date_counts": dict(sorted(candidate_counts.items())),
        "candidate_catalog": catalog_rows,
        "factor_coverage": factor_coverage,
        "factor_series_total": len(all_series),
        "factor_series_tested": sum(
            row["status"] == "tested" for row in factor_coverage
        ),
        "factor_series_untested": sum(
            row["status"] != "tested" for row in factor_coverage
        ),
        "axis_candidate_counts": dict(sorted(axis_candidate_counts.items())),
        "axis_session_rows": dict(sorted(axis_session_rows.items())),
        "side_minimum_failures": side_failures,
        "side_minimum_failures_by_axis": dict(
            sorted(side_failures_by_axis.items())
        ),
        "outcome_conflicts": outcome_conflicts,
        "superseded_outcomes_excluded": superseded_outcomes_excluded,
        "statistical_unit": "complete_daily_cross_section",
    }


def _summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    values = [float(row["spread"]) for row in rows]
    count = len(values)
    if not count:
        raise ContractError("cannot summarize an empty candidate")
    mean = statistics.fmean(values)
    median = statistics.median(values)
    stdev = statistics.stdev(values) if count > 1 else None
    standard_error = (
        stdev / math.sqrt(count) if stdev is not None else None
    )
    return {
        "independent_dates": count,
        "mean_spread": mean,
        "median_spread": median,
        "positive_rate": sum(value > 0 for value in values) / count,
        "sample_stdev": stdev,
        "date_level_standard_error_descriptive": standard_error,
        "descriptive_t_like_not_for_inference": (
            mean / standard_error
            if standard_error not in {None, 0.0}
            else None
        ),
        "serial_correlation_adjustment": "none; inference disabled",
    }


def _direction(value: float) -> Optional[str]:
    if math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-15):
        return None
    return "positive" if value > 0 else "negative"


def _exploratory_diagnostics(
    sessions: Sequence[Mapping[str, Any]],
    *,
    policy: SelectionPolicy,
) -> Dict[str, Any]:
    """Expose real-data changes without promoting short samples to forecast."""

    by_candidate: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in sessions:
        by_candidate[str(row["candidate_id"])].append(row)

    evidence = []
    for candidate_id, raw_rows in by_candidate.items():
        rows = sorted(
            raw_rows,
            key=lambda row: str(row["as_of_trade_date"]),
        )
        first = rows[0]
        full = _summary(rows)
        full_direction = _direction(float(full["median_spread"]))
        windows = {}
        for window in EXPLORATORY_WINDOWS:
            if len(rows) < window:
                continue
            stats = _summary(rows[-window:])
            windows[str(window)] = {
                "independent_dates": stats["independent_dates"],
                "mean_spread": stats["mean_spread"],
                "median_spread": stats["median_spread"],
                "positive_rate": stats["positive_rate"],
                "direction": _direction(float(stats["median_spread"])),
            }
        comparable_directions = [
            str(row["direction"])
            for row in windows.values()
            if row["direction"] is not None
        ]
        recent_direction = (
            windows[str(EXPLORATORY_WINDOWS[0])]["direction"]
            if str(EXPLORATORY_WINDOWS[0]) in windows
            else None
        )
        recent_reversal = bool(
            full_direction is not None
            and recent_direction is not None
            and full_direction != recent_direction
        )
        direction_consistent = bool(
            full_direction is not None
            and comparable_directions
            and all(
                direction == full_direction
                for direction in comparable_directions
            )
        )
        evidence.append({
            "candidate_id": candidate_id,
            "series_id": str(first["series_id"]),
            "axis": str(first["axis"]),
            "concept": first.get("concept"),
            "condition": dict(first.get("condition") or {}),
            "independent_dates": int(full["independent_dates"]),
            "full_history": {
                "mean_spread": full["mean_spread"],
                "median_spread": full["median_spread"],
                "positive_rate": full["positive_rate"],
                "direction": full_direction,
            },
            "rolling_windows": windows,
            "recent_reversal": recent_reversal,
            "direction_consistent": direction_consistent,
            "forecast_eligible": False,
            "evidence_status": (
                "eligible_for_walk_forward_training"
                if len(rows) >= policy.min_train_dates
                else "exploratory_below_training_minimum"
            ),
        })

    def rank_key(row: Mapping[str, Any]) -> Tuple[Any, ...]:
        median = abs(float(row["full_history"]["median_spread"]))
        return (
            -int(row["independent_dates"]),
            -median,
            str(row["candidate_id"]),
        )

    reversals = sorted(
        (row for row in evidence if row["recent_reversal"]),
        key=rank_key,
    )
    consistent = sorted(
        (row for row in evidence if row["direction_consistent"]),
        key=rank_key,
    )
    return {
        "candidate_count": len(evidence),
        "recent_reversal_count": len(reversals),
        "direction_consistent_count": len(consistent),
        "windows": list(EXPLORATORY_WINDOWS),
        "ranking_order": (
            "independent_dates desc, absolute full-history median spread "
            "desc, candidate_id; descriptive only"
        ),
        "recent_reversals": reversals[:EXPLORATORY_REPORT_LIMIT],
        "direction_consistent_candidates": (
            consistent[:EXPLORATORY_REPORT_LIMIT]
        ),
        "evidence_label": "candidate_not_validated",
        "forecast_eligible": False,
    }


def _training_candidates(
    sessions: Sequence[Mapping[str, Any]],
    *,
    validation_date: str,
    validation_decision_at: datetime,
    session_index: Mapping[str, int],
    embargo_sessions: int,
    min_train_dates: int,
) -> List[Dict[str, Any]]:
    by_candidate: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    validation_index = session_index[validation_date]
    for row in sessions:
        baseline = str(row["as_of_trade_date"])
        outcome_date = str(row["outcome_trade_date"])
        if baseline >= validation_date or outcome_date >= validation_date:
            continue
        if _aware(row["outcome_available_at"], "outcome_available_at") > validation_decision_at:
            continue
        outcome_index = session_index.get(outcome_date)
        if outcome_index is None:
            raise ContractError(
                f"outcome date {outcome_date} is absent from session calendar"
            )
        if validation_index - outcome_index <= embargo_sessions:
            continue
        by_candidate[str(row["candidate_id"])].append(row)

    candidates = []
    for candidate_id, rows in by_candidate.items():
        if len(rows) < min_train_dates:
            continue
        stats = _summary(rows)
        orientation_source = (
            stats["median_spread"]
            if stats["median_spread"] != 0
            else stats["mean_spread"]
        )
        direction = 1 if orientation_source >= 0 else -1
        first = rows[0]
        candidates.append({
            "candidate_id": candidate_id,
            "series_id": first["series_id"],
            "axis": first["axis"],
            "concept": first.get("concept"),
            "condition": dict(first.get("condition") or {}),
            "direction": direction,
            "ranking_score": abs(float(stats["median_spread"])),
            "training": stats,
        })
    return sorted(
        candidates,
        key=lambda row: (
            -float(row["ranking_score"]),
            str(row["candidate_id"]),
        ),
    )


def run_walk_forward_select(
    *,
    candidate_sessions: Iterable[Mapping[str, Any]],
    horizon_sessions: int,
    policy: SelectionPolicy = SelectionPolicy(),
    current_as_of_trade_date: Optional[str] = None,
    current_decision_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Expanding walk-forward audit with purge, embargo, and abstention."""

    policy.validate()
    horizon = _positive_horizon(horizon_sessions)
    rows = [dict(row) for row in candidate_sessions]
    if any(int(row.get("horizon_sessions", 0)) != horizon for row in rows):
        raise ContractError("candidate session horizon mismatch")
    dates = sorted({str(row["as_of_trade_date"]) for row in rows})
    outcome_dates = {str(row["outcome_trade_date"]) for row in rows}
    if (current_as_of_trade_date is None) != (current_decision_at is None):
        raise ContractError(
            "current_as_of_trade_date and current_decision_at are required together"
        )
    current_date = str(current_as_of_trade_date or "")
    if current_date:
        try:
            datetime.strptime(current_date, "%Y%m%d")
        except ValueError as exc:
            raise ContractError(
                "current_as_of_trade_date must be YYYYMMDD"
            ) from exc
    calendar = sorted(
        set(dates)
        | outcome_dates
        | ({current_date} if current_date else set())
    )
    session_index = {trade_date: index for index, trade_date in enumerate(calendar)}
    decision_times = {}
    for row in rows:
        trade_date = str(row["as_of_trade_date"])
        value = _aware(row["decision_at"], "candidate decision_at")
        previous = decision_times.get(trade_date)
        decision_times[trade_date] = max(previous, value) if previous else value
    by_date_candidate = {
        (str(row["as_of_trade_date"]), str(row["candidate_id"])): row
        for row in rows
    }
    if len(by_date_candidate) != len(rows):
        raise ContractError("duplicate candidate/date session")

    embargo = (
        horizon
        if policy.embargo_sessions is None
        else policy.embargo_sessions
    )
    folds = []
    attempted_candidates = set()
    for validation_date in dates:
        train = _training_candidates(
            rows,
            validation_date=validation_date,
            validation_decision_at=decision_times[validation_date],
            session_index=session_index,
            embargo_sessions=embargo,
            min_train_dates=policy.min_train_dates,
        )
        attempted_candidates.update(row["candidate_id"] for row in train)
        if not train:
            continue
        selected = []
        for candidate in train:
            validation = by_date_candidate.get(
                (validation_date, str(candidate["candidate_id"]))
            )
            if validation is None:
                continue
            selected.append({
                **candidate,
                "validation_spread": float(validation["spread"]),
                "direction_adjusted_spread": (
                    int(candidate["direction"])
                    * float(validation["spread"])
                ),
            })
            if len(selected) >= policy.top_k:
                break
        if not selected:
            continue
        folds.append({
            "validation_trade_date": validation_date,
            "validation_decision_at": decision_times[
                validation_date
            ].isoformat(timespec="seconds"),
            "candidate_tests_in_fold": len(train),
            "selected": selected,
            "strategy_oos_spread": statistics.fmean(
                row["direction_adjusted_spread"] for row in selected
            ),
        })

    oos_values = [float(fold["strategy_oos_spread"]) for fold in folds]
    current_train = []
    if current_date:
        current_train = _training_candidates(
            rows,
            validation_date=current_date,
            validation_decision_at=_aware(
                current_decision_at, "current_decision_at"
            ),
            session_index=session_index,
            embargo_sessions=embargo,
            min_train_dates=policy.min_train_dates,
        )
    current_candidates = current_train[:policy.top_k]
    exploratory = _exploratory_diagnostics(rows, policy=policy)
    if len(folds) < policy.min_oos_dates:
        status = "abstain"
        reason = "insufficient_independent_oos_dates"
    elif current_date and not current_candidates:
        status = "abstain"
        reason = "current_training_unavailable"
    else:
        status = "shadow_candidate"
        reason = None
    return {
        "select_version": SELECT_VERSION,
        "status": status,
        "abstain_reason": reason,
        "promotion_status": "manual_review_required",
        "production_eligible": False,
        "horizon_sessions": horizon,
        "policy": {
            **asdict(policy),
            "effective_embargo_sessions": embargo,
        },
        "policy_digest": policy_digest(policy, horizon),
        "independent_dates_available": len(dates),
        "candidate_tests_total": len({
            str(row["candidate_id"]) for row in rows
        }),
        "candidate_tests_reaching_train_minimum": len(attempted_candidates),
        "current_candidate_tests": len(current_train),
        "current_candidates": current_candidates,
        "exploratory_diagnostics": exploratory,
        "oos_independent_dates": len(folds),
        "oos_summary": (
            {
                "mean_spread": statistics.fmean(oos_values),
                "median_spread": statistics.median(oos_values),
                "positive_rate": (
                    sum(value > 0 for value in oos_values) / len(oos_values)
                ),
            }
            if oos_values
            else None
        ),
        "folds": folds,
        "leakage_controls": {
            "expanding_walk_forward": True,
            "outcome_must_precede_validation": True,
            "outcome_available_at_gate": True,
            "purge": "outcome_trade_date < validation_trade_date",
            "embargo_sessions": embargo,
            "daily_cross_section_cluster": True,
        },
        "evidence_label": (
            "candidate_not_validated"
            if folds
            else "insufficient_history"
        ),
    }


def build_selection_audit(
    *,
    group_factor_rows: Iterable[Mapping[str, Any]],
    outcome_rows: Iterable[Mapping[str, Any]],
    as_of_trade_date: str,
    decision_at: str,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    policy: SelectionPolicy = SelectionPolicy(),
) -> Dict[str, Any]:
    """Build all requested horizon audits from one frozen decision point."""

    try:
        datetime.strptime(str(as_of_trade_date), "%Y%m%d")
    except ValueError as exc:
        raise ContractError("as_of_trade_date must be YYYYMMDD") from exc
    groups = [dict(row) for row in group_factor_rows]
    outcomes = [dict(row) for row in outcome_rows]
    results = {}
    input_ids = []
    for horizon in horizons:
        h = _positive_horizon(horizon)
        sessions, build_audit = build_candidate_sessions(
            group_factor_rows=groups,
            outcome_rows=outcomes,
            horizon_sessions=h,
            decision_at=decision_at,
            policy=policy,
        )
        selection = run_walk_forward_select(
            candidate_sessions=sessions,
            horizon_sessions=h,
            policy=policy,
            current_as_of_trade_date=str(as_of_trade_date),
            current_decision_at=decision_at,
        )
        results[str(h)] = {
            "build": build_audit,
            "selection": selection,
        }
        input_ids.extend(
            f"{row['candidate_id']}:{row['as_of_trade_date']}:{row['spread']}"
            for row in sessions
        )
    digest = canonical_digest({
        "as_of_trade_date": as_of_trade_date,
        "decision_at": decision_at,
        "select_version": SELECT_VERSION,
        "horizons": [_positive_horizon(value) for value in horizons],
        "policy": asdict(policy),
        "candidate_sessions": sorted(input_ids),
    })
    statuses = Counter(
        result["selection"]["status"] for result in results.values()
    )
    audit = {
        "schema_version": SELECTION_AUDIT_SCHEMA_VERSION,
        "as_of_trade_date": str(as_of_trade_date),
        "decision_at": _aware(
            decision_at, "decision_at"
        ).isoformat(timespec="seconds"),
        "select_version": SELECT_VERSION,
        "input_digest": digest,
        "horizons": results,
        "status_counts": dict(sorted(statuses.items())),
        "production_eligible": False,
        "promotion_status": "manual_review_required",
    }
    validate_selection_audit(audit)
    return audit
