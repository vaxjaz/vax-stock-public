# -*- coding: utf-8 -*-
"""Label-free, point-in-time grouping for the Research v2 pipeline.

``group`` does not estimate returns and does not choose securities.  It turns
the facts legally visible at one decision time into independent cohort axes:

* market regime and macro regime;
* cross-sectional factor tertiles inside the point-in-time user universe;
* causal stock-curve states;
* point-in-time concept-track state and stock-vs-track relations.

The axes remain separate.  Later research may test intersections in a
walk-forward sample, but this layer never searches outcomes or materializes a
single high-dimensional cluster.  That separation is what prevents the group
definition from being fitted to future returns.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from numbers import Real
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from vaxstock.research.causal_curve import (
    CURVE_FACTOR_VERSION,
    DEFAULT_PARAMETERS as DEFAULT_CURVE_PARAMETERS,
    STOCK_CURVE_VECTOR_FACTOR_ID,
    TRACK_AGGREGATE_VECTOR_FACTOR_ID,
    TRACK_CURVE_VECTOR_FACTOR_ID,
    TRACK_FACTOR_VERSION,
    is_curve_eligible,
)
from vaxstock.research.contracts import (
    FACTOR_VALUE_SCHEMA_VERSION,
    RUN_MANIFEST_SCHEMA_VERSION,
    ContractError,
    canonical_digest,
    factor_input_digest,
    make_factor_value_id,
    make_run_id,
    validate_atomic_observation,
    validate_factor_value,
)
from vaxstock.research.global_anchor_dimension import (
    ANCHOR_CONTEXT_ENTITY_ID,
    ANCHOR_CONTEXT_FACTOR_ID,
    ANCHOR_CONTEXT_FACTOR_VERSION,
    DIMENSION as GLOBAL_ANCHOR_DIMENSION,
)


CHINA_TZ = timezone(timedelta(hours=8))
FEATURE_SET_VERSION = "contextual_multiview_group_feature_set_v3"
GROUP_VERSION = "contextual_multiview_group_v3"
GROUP_CONTEXT_FACTOR_ID = "group_context_vector"
STOCK_GROUP_FACTOR_ID = "stock_group_vector"
GROUP_CONTEXT_FACTOR_VERSION = "group_context_vector_v3"
STOCK_GROUP_FACTOR_VERSION = "stock_group_vector_v3"
GROUP_DIMENSION = "research_group"
NOT_EXECUTED = "not_executed"
CURVE_STATE_FIELDS = (
    "slope_recent",
    "acceleration",
    "turning",
    "anomaly",
    "change_point",
)
TRACK_RELATION_FIELDS = ("level", "slope_recent")


@dataclass(frozen=True)
class GroupParameters:
    """Structural sufficiency rules, not fitted return thresholds."""

    minimum_cross_section: int = 9
    minimum_distinct_values: int = 3
    lower_quantile: float = 1.0 / 3.0
    upper_quantile: float = 2.0 / 3.0
    systemic_event_breadth_threshold: float = 0.5
    minimum_event_cluster_stocks: int = 3


DEFAULT_PARAMETERS = GroupParameters()


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
        raise ContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include a timezone offset")
    return parsed


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _validate_parameters(parameters: GroupParameters) -> None:
    if (
        isinstance(parameters.minimum_cross_section, bool)
        or not isinstance(parameters.minimum_cross_section, int)
        or parameters.minimum_cross_section < 3
    ):
        raise ContractError("minimum_cross_section must be an integer >= 3")
    if (
        isinstance(parameters.minimum_distinct_values, bool)
        or not isinstance(parameters.minimum_distinct_values, int)
        or parameters.minimum_distinct_values < 2
        or parameters.minimum_distinct_values > parameters.minimum_cross_section
    ):
        raise ContractError(
            "minimum_distinct_values must be an integer within "
            "[2, minimum_cross_section]"
        )
    for name, value in (
        ("lower_quantile", parameters.lower_quantile),
        ("upper_quantile", parameters.upper_quantile),
        (
            "systemic_event_breadth_threshold",
            parameters.systemic_event_breadth_threshold,
        ),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
        ):
            raise ContractError(f"{name} must be a finite number")
    if not (
        0 < float(parameters.lower_quantile)
        < float(parameters.upper_quantile)
        < 1
    ):
        raise ContractError("quantile boundaries must satisfy 0 < lower < upper < 1")
    if not 0 < float(parameters.systemic_event_breadth_threshold) <= 1:
        raise ContractError(
            "systemic_event_breadth_threshold must be within (0, 1]"
        )
    if (
        isinstance(parameters.minimum_event_cluster_stocks, bool)
        or not isinstance(parameters.minimum_event_cluster_stocks, int)
        or parameters.minimum_event_cluster_stocks <= 0
    ):
        raise ContractError(
            "minimum_event_cluster_stocks must be a positive integer"
        )


def group_version(parameters: GroupParameters = DEFAULT_PARAMETERS) -> str:
    """Bind a non-default grouping protocol to a new immutable version."""

    _validate_parameters(parameters)
    if parameters == DEFAULT_PARAMETERS:
        return GROUP_VERSION
    return (
        f"{GROUP_VERSION}."
        f"{canonical_digest(asdict(parameters))[:12]}"
    )


def _factor_versions(parameters: GroupParameters) -> Tuple[str, str]:
    group_version(parameters)
    if parameters == DEFAULT_PARAMETERS:
        return GROUP_CONTEXT_FACTOR_VERSION, STOCK_GROUP_FACTOR_VERSION
    digest = canonical_digest(asdict(parameters))[:12]
    return (
        f"{GROUP_CONTEXT_FACTOR_VERSION}.{digest}",
        f"{STOCK_GROUP_FACTOR_VERSION}.{digest}",
    )


def factor_series_id(row: Mapping[str, Any]) -> str:
    """Stable identity of one reviewed continuous factor series."""

    return (
        f"{row['dimension']}::{row['factor_id']}::"
        f"{row['factor_version']}"
    )


def _native_factor(row: Mapping[str, Any]) -> bool:
    trade_date = datetime.strptime(
        _trade_date(row.get("as_of_trade_date"), "factor as_of_trade_date"),
        "%Y%m%d",
    ).date()
    calculated_date = _aware(
        row.get("calculated_at"), "factor calculated_at"
    ).astimezone(CHINA_TZ).date()
    return calculated_date in {trade_date, trade_date + timedelta(days=1)}


def _factor_ref(row: Mapping[str, Any]) -> Dict[str, str]:
    return {
        "factor_value_id": str(row["factor_value_id"]),
        "as_of_trade_date": str(row["as_of_trade_date"]),
    }


def _derived_factor(
    *,
    entity_type: str,
    entity_id: str,
    factor_id: str,
    factor_version: str,
    value: Any,
    as_of_trade_date: str,
    calculated_at: str,
    input_factors: Iterable[Mapping[str, Any]],
    input_observations: Iterable[Mapping[str, Any]] = (),
) -> Dict[str, Any]:
    factors = {
        (str(row["as_of_trade_date"]), str(row["factor_value_id"])): row
        for row in input_factors
    }
    observations = {
        str(row["observation_id"]): row for row in input_observations
    }
    refs = [_factor_ref(factors[key]) for key in sorted(factors)]
    observation_ids = sorted(observations)
    if not refs and not observation_ids:
        raise ContractError(f"{factor_id} requires upstream inputs")
    availability = [
        _aware(row.get("available_at"), "upstream factor available_at")
        for row in factors.values()
    ]
    availability.extend(
        _aware(row.get("available_at"), "input observation available_at")
        for row in observations.values()
    )
    calculated = _aware(calculated_at, "calculated_at")
    available = max(availability)
    dependency_ready_at = max(
        [
            available,
            *(
                _aware(
                    row.get("calculated_at"),
                    "upstream factor calculated_at",
                )
                for row in factors.values()
            ),
        ]
    )
    if calculated < dependency_ready_at:
        raise ContractError("derived factor calculated before an upstream input")
    row: Dict[str, Any] = {
        "schema_version": FACTOR_VALUE_SCHEMA_VERSION,
        "factor_value_id": "",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "dimension": GROUP_DIMENSION,
        "factor_id": factor_id,
        "factor_version": factor_version,
        "value": value,
        "as_of_trade_date": as_of_trade_date,
        "effective_date": as_of_trade_date,
        "available_at": available.isoformat(timespec="seconds"),
        "calculated_at": calculated.isoformat(timespec="seconds"),
        "input_observation_ids": observation_ids,
        "input_factor_refs": refs,
        "input_digest": factor_input_digest(observation_ids, refs),
        "quality": "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _resolve_factors(
    rows: Sequence[Mapping[str, Any]],
    *,
    decision_at: datetime,
    predicate,
) -> Dict[Tuple[str, str, str, str, str, str], Dict[str, Any]]:
    resolved: Dict[Tuple[str, str, str, str, str, str], Dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        if not predicate(row):
            continue
        if _aware(row.get("calculated_at"), "factor calculated_at") > decision_at:
            continue
        key = (
            str(row["as_of_trade_date"]),
            str(row["entity_type"]),
            str(row["entity_id"]),
            str(row["dimension"]),
            str(row["factor_id"]),
            str(row["factor_version"]),
        )
        previous = resolved.get(key)
        if previous is None or (
            _aware(row["calculated_at"], "factor calculated_at"),
            str(row["factor_value_id"]),
        ) > (
            _aware(previous["calculated_at"], "factor calculated_at"),
            str(previous["factor_value_id"]),
        ):
            resolved[key] = row
    return resolved


def _latest_observations(
    rows: Sequence[Mapping[str, Any]],
    *,
    target: str,
    decision_at: datetime,
    predicate,
) -> Dict[str, Dict[str, Any]]:
    selected: Dict[str, Dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        if not predicate(row):
            continue
        effective_date = _trade_date(
            row.get("effective_date"), "observation effective_date"
        )
        available = _aware(row.get("available_at"), "observation available_at")
        if effective_date > target or available > decision_at:
            continue
        entity_id = str(row["entity_id"])
        previous = selected.get(entity_id)
        if previous is None or (
            effective_date,
            available,
            str(row["observation_id"]),
        ) > (
            str(previous["effective_date"]),
            _aware(previous["available_at"], "observation available_at"),
            str(previous["observation_id"]),
        ):
            selected[entity_id] = row
    return selected


def _exact_universe_snapshot(
    rows: Sequence[Mapping[str, Any]],
    *,
    target: str,
    decision_at: datetime,
) -> Dict[str, Any]:
    candidates = []
    for raw in rows:
        row = dict(raw)
        if not (
            row.get("entity_type") == "market"
            and row.get("entity_id") == "CN-A"
            and row.get("dimension") == "universe"
            and row.get("field") == "universe_snapshot"
            and str(row.get("effective_date") or "") == target
            and _aware(
                row.get("available_at"), "universe snapshot available_at"
            )
            <= decision_at
        ):
            continue
        candidates.append(row)
    if not candidates:
        raise ContractError(
            "exact-date point-in-time universe snapshot is required"
        )
    return max(
        candidates,
        key=lambda row: (
            _aware(row["available_at"], "universe snapshot available_at"),
            str(row["observation_id"]),
        ),
    )


def _universe_codes(snapshot: Mapping[str, Any]) -> List[str]:
    value = snapshot.get("value")
    if not isinstance(value, Mapping):
        raise ContractError("universe snapshot value must be an object")
    raw_codes = value.get("active_codes")
    if not isinstance(raw_codes, list):
        raise ContractError("universe snapshot active_codes must be a list")
    codes = [str(code).strip() for code in raw_codes]
    if any(not code for code in codes) or len(codes) != len(set(codes)):
        raise ContractError(
            "universe snapshot active_codes must be unique non-empty strings"
        )
    active_count = value.get("active_count")
    if (
        isinstance(active_count, bool)
        or not isinstance(active_count, int)
        or active_count != len(codes)
    ):
        raise ContractError(
            "universe snapshot active_count does not match active_codes"
        )
    return sorted(codes)


def materialize_group_id(
    group_version_value: str,
    *,
    axis: str,
    state: str,
    series_id: Optional[str] = None,
    concept: Optional[str] = None,
) -> str:
    """Materialize a cohort ID from one stored axis-state tuple.

    Group vectors store the tuple rather than repeating this 64-byte digest
    for every stock.  Consumers that need a join key call this versioned
    function; the tuple itself remains the canonical, human-auditable state.
    """

    identity = {
        "group_version": group_version_value,
        "axis": axis,
        "state": state,
        "series_id": series_id,
        "concept": concept,
    }
    return f"group_{canonical_digest(identity)}"


def _state_membership(
    *,
    state: Optional[str],
    status: str = "available",
) -> Dict[str, Any]:
    clean_state = str(state).strip() if state is not None else None
    available = status == "available" and bool(clean_state)
    return {
        "state": clean_state if available else None,
        "status": "available" if available else status,
    }


def _direction(value: Any) -> Optional[str]:
    numeric = _number(value)
    if numeric is None:
        return None
    if numeric > 0:
        return "up"
    if numeric < 0:
        return "down"
    return "flat"


def _relation(left: Any, right: Any) -> Optional[str]:
    first = _number(left)
    second = _number(right)
    if first is None or second is None:
        return None
    if first > second:
        return "above"
    if first < second:
        return "below"
    return "equal"


def _curve_states(
    curve: Optional[Mapping[str, Any]],
) -> List[Optional[str]]:
    if not isinstance(curve, Mapping):
        return [None for _ in CURVE_STATE_FIELDS]

    sample_count = curve.get("sample_count")
    sample_count = (
        int(sample_count)
        if isinstance(sample_count, int) and not isinstance(sample_count, bool)
        else 0
    )
    slope_window = DEFAULT_CURVE_PARAMETERS.slope_window
    slope = _direction(curve.get("slope_recent"))
    acceleration = _direction(curve.get("acceleration"))

    detector_specs = (
        (
            "turning",
            curve.get("turning_candidate"),
            sample_count >= slope_window * 2,
        ),
        (
            "anomaly",
            curve.get("anomaly_candidate"),
            (
                _number(curve.get("innovation_robust_z")) is not None
                or bool(curve.get("innovation_zero_scale_break"))
            ),
        ),
        (
            "change_point",
            curve.get("change_point_candidate"),
            sample_count >= slope_window * 2,
        ),
    )
    states: List[Optional[str]] = [slope, acceleration]
    for name, candidate, ready in detector_specs:
        states.append(
            (str(candidate) if candidate else "none") if ready else None
        )
    return states


def _midranks(
    values: Sequence[Tuple[str, float]],
) -> Dict[str, float]:
    """Return empirical percentile midranks; ties always share one rank."""

    ordered = sorted(values, key=lambda item: (item[1], item[0]))
    if len(ordered) < 2:
        return {}
    ranks: Dict[str, float] = {}
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        midrank = ((index + end - 1) / 2.0) / (len(ordered) - 1)
        for position in range(index, end):
            ranks[ordered[position][0]] = float(midrank)
        index = end
    return ranks


def _bucket(rank_pct: float, parameters: GroupParameters) -> str:
    if rank_pct <= parameters.lower_quantile:
        return "low"
    if rank_pct >= parameters.upper_quantile:
        return "high"
    return "middle"


def _cross_sections(
    current_base: Sequence[Mapping[str, Any]],
    *,
    parameters: GroupParameters,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[Tuple[str, str], Dict[str, Any]]]:
    by_series: Dict[str, List[Tuple[str, float]]] = {}
    for row in current_base:
        numeric = _number(row.get("value"))
        if numeric is None:
            continue
        by_series.setdefault(factor_series_id(row), []).append(
            (str(row["entity_id"]), numeric)
        )

    contexts: Dict[str, Dict[str, Any]] = {}
    assignments: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for series_id, values in sorted(by_series.items()):
        distinct = len({value for _, value in values})
        if len(values) < parameters.minimum_cross_section:
            contexts[series_id] = {
                "status": "insufficient_cross_section",
                "eligible_count": len(values),
                "distinct_value_count": distinct,
                "minimum_cross_section": parameters.minimum_cross_section,
                "minimum_distinct_values": parameters.minimum_distinct_values,
            }
            continue
        if distinct < parameters.minimum_distinct_values:
            contexts[series_id] = {
                "status": "insufficient_variation",
                "eligible_count": len(values),
                "distinct_value_count": distinct,
                "minimum_cross_section": parameters.minimum_cross_section,
                "minimum_distinct_values": parameters.minimum_distinct_values,
            }
            continue
        ranks = _midranks(values)
        counts = {"low": 0, "middle": 0, "high": 0}
        for code, numeric in values:
            rank_pct = ranks[code]
            bucket = _bucket(rank_pct, parameters)
            counts[bucket] += 1
            assignments[(code, series_id)] = {
                "status": "available",
                "rank_pct": rank_pct,
                "bucket": bucket,
            }
        contexts[series_id] = {
            "status": "available",
            "eligible_count": len(values),
            "distinct_value_count": distinct,
            "method": "empirical_midrank_tertiles",
            "lower_quantile": parameters.lower_quantile,
            "upper_quantile": parameters.upper_quantile,
            "bucket_counts": counts,
            "minimum": min(value for _, value in values),
            "maximum": max(value for _, value in values),
        }
    return contexts, assignments


def _vector_series(row: Optional[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not isinstance(row, Mapping):
        return {}
    value = row.get("value")
    series = value.get("series") if isinstance(value, Mapping) else None
    if not isinstance(series, Mapping):
        return {}
    return {
        str(series_id): dict(series_value)
        for series_id, series_value in series.items()
        if isinstance(series_value, Mapping)
    }


def _event_direction(event: str) -> Optional[str]:
    for suffix in ("positive", "negative", "up", "down"):
        if event.endswith(f"_{suffix}"):
            return suffix
    return None


def _event_field(
    *,
    stock_curves: Mapping[str, Mapping[str, Any]],
    track_curves: Mapping[str, Mapping[str, Any]],
    universe_codes: Sequence[str],
    parameters: GroupParameters,
) -> Dict[str, Any]:
    """Aggregate raw curve events without deleting their common component."""

    eligible_by_series: Dict[str, set[str]] = {}
    cluster_members: Dict[Tuple[str, str], set[str]] = {}
    event_family_members: Dict[str, set[str]] = {}
    event_family_series: Dict[str, set[str]] = {}
    event_stocks = set()
    event_count = 0
    direction_counts: Dict[str, int] = {}
    type_counts: Dict[str, int] = {}
    for code in universe_codes:
        curve = stock_curves.get(code)
        series = _vector_series(curve)
        for series_id, state in series.items():
            eligible_by_series.setdefault(series_id, set()).add(code)
            events = state.get("candidate_events") or []
            if not isinstance(events, list):
                raise ContractError("curve candidate_events must be a list")
            for raw_event in events:
                event = str(raw_event).strip()
                if not event:
                    continue
                event_count += 1
                event_stocks.add(code)
                cluster_members.setdefault((series_id, event), set()).add(code)
                event_family_members.setdefault(event, set()).add(code)
                event_family_series.setdefault(event, set()).add(series_id)
                event_type = event.rsplit("_", 1)[0]
                type_counts[event_type] = type_counts.get(event_type, 0) + 1
                direction = _event_direction(event)
                if direction:
                    direction_counts[direction] = (
                        direction_counts.get(direction, 0) + 1
                    )

    clusters = []
    for (series_id, event), members in sorted(cluster_members.items()):
        eligible = len(eligible_by_series.get(series_id) or ())
        breadth = len(members) / eligible if eligible else None
        systemic = bool(
            breadth is not None
            and breadth >= parameters.systemic_event_breadth_threshold
            and len(members) >= parameters.minimum_event_cluster_stocks
        )
        clusters.append({
            "cluster_id": canonical_digest({
                "series_id": series_id,
                "event": event,
            }),
            "series_id": series_id,
            "event": event,
            "direction": _event_direction(event),
            "member_count": len(members),
            "eligible_count": eligible,
            "breadth": breadth,
            "member_codes": sorted(members),
            "systemic_candidate": systemic,
        })

    family_clusters = []
    for event, members in sorted(event_family_members.items()):
        breadth = len(members) / len(universe_codes) if universe_codes else None
        systemic = bool(
            breadth is not None
            and breadth >= parameters.systemic_event_breadth_threshold
            and len(members) >= parameters.minimum_event_cluster_stocks
        )
        family_clusters.append({
            "cluster_id": canonical_digest({
                "scope": "cross_series_event_family",
                "event": event,
            }),
            "event": event,
            "direction": _event_direction(event),
            "series_count": len(event_family_series[event]),
            "series_ids": sorted(event_family_series[event]),
            "member_count": len(members),
            "eligible_count": len(universe_codes),
            "breadth": breadth,
            "member_codes": sorted(members),
            "systemic_candidate": systemic,
        })

    eligible_stock_series = sum(
        len(codes) for codes in eligible_by_series.values()
    )
    universe_count = len(universe_codes)
    stock_breadth = (
        len(event_stocks) / universe_count if universe_count else None
    )
    systemic_clusters = [
        row for row in clusters if row["systemic_candidate"]
    ]
    systemic_family_clusters = [
        row for row in family_clusters if row["systemic_candidate"]
    ]
    if not event_count:
        systemic_state = "none"
    elif systemic_clusters or systemic_family_clusters:
        systemic_state = "broad"
    else:
        systemic_state = "localized"
    systemic_directions = sorted({
        str(row["direction"])
        for row in [*systemic_family_clusters, *systemic_clusters]
        if row.get("direction")
    })
    systemic_direction = (
        systemic_directions[0]
        if len(systemic_directions) == 1
        else ("mixed" if systemic_directions else None)
    )

    track_events = []
    for concept, curve in sorted(track_curves.items()):
        for series_id, state in sorted(_vector_series(curve).items()):
            events = state.get("candidate_events") or []
            if not isinstance(events, list):
                raise ContractError("track curve candidate_events must be a list")
            for raw_event in events:
                event = str(raw_event).strip()
                if event:
                    track_events.append({
                        "concept": concept,
                        "series_id": series_id,
                        "event": event,
                        "direction": _event_direction(event),
                    })

    return {
        "evidence_label": "candidate_not_validated",
        "raw_events_preserved_in_curve_factors": True,
        "systemic_state": systemic_state,
        "systemic_direction": systemic_direction,
        "universe_count": universe_count,
        "curve_eligible_stock_count": sum(
            code in stock_curves for code in universe_codes
        ),
        "eligible_stock_series": eligible_stock_series,
        "event_count": event_count,
        "event_density": (
            event_count / eligible_stock_series
            if eligible_stock_series
            else None
        ),
        "event_stock_count": len(event_stocks),
        "event_stock_breadth": stock_breadth,
        "direction_counts": dict(sorted(direction_counts.items())),
        "event_type_counts": dict(sorted(type_counts.items())),
        "clusters": clusters,
        "event_family_clusters": family_clusters,
        "systemic_cluster_count": len(systemic_clusters),
        "systemic_event_family_count": len(systemic_family_clusters),
        "localized_cluster_count": len(clusters) - len(systemic_clusters),
        "track_event_count": len(track_events),
        "track_events": track_events,
        "thresholds": {
            "systemic_event_breadth_threshold": (
                parameters.systemic_event_breadth_threshold
            ),
            "minimum_event_cluster_stocks": (
                parameters.minimum_event_cluster_stocks
            ),
            "threshold_status": "structural_candidate_not_effective_claim",
        },
    }


def _membership_value(row: Mapping[str, Any]) -> Dict[str, Any]:
    value = row.get("value")
    if not isinstance(value, Mapping):
        raise ContractError("universe membership value must be an object")
    concepts = value.get("concepts") or []
    if not isinstance(concepts, list):
        raise ContractError("universe membership concepts must be a list")
    return {
        "name": value.get("name"),
        "role": value.get("group"),
        "concepts": sorted({
            str(concept).strip()
            for concept in concepts
            if str(concept).strip()
        }),
    }


def _market_context(
    market_observation: Mapping[str, Any],
    *,
    target: str,
) -> Dict[str, Any]:
    value = market_observation.get("value")
    if not isinstance(value, Mapping):
        raise ContractError("market context value must be an object")
    effective_date = _trade_date(
        market_observation.get("effective_date"), "market effective_date"
    )
    states = {}
    for field in ("regime", "macro_regime"):
        raw = value.get(field)
        state = str(raw).strip() if raw is not None else None
        states[field] = _state_membership(
            state=state,
            status="available" if state else "source_missing",
        )
    return {
        "effective_date": effective_date,
        "context_timing": "same_trade_date" if effective_date == target else "prior_date",
        "states": states,
    }


def _global_anchor_context(
    factor: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Expose reviewed market-anchor states without treating them as stocks."""

    allowed = (
        "anchor_nvda_direction",
        "anchor_soxx_direction",
        "anchor_qqq_direction",
        "anchor_vix_direction",
        "anchor_equity_majority_direction",
    )
    if not isinstance(factor, Mapping):
        return {
            "status": "source_missing",
            "factor_value_id": None,
            "states": {field: None for field in allowed},
            "returns_pct": {},
            "source_session_dates": {},
            "timing_semantics": None,
        }
    value = factor.get("value")
    if not isinstance(value, Mapping):
        raise ContractError("global anchor context factor value must be an object")
    raw_states = value.get("states") or {}
    if not isinstance(raw_states, Mapping):
        raise ContractError("global anchor context states must be an object")
    states = {}
    for field in allowed:
        raw = raw_states.get(field)
        state = str(raw).strip() if raw is not None else None
        if state is not None and state not in {"up", "down", "flat", "mixed"}:
            raise ContractError(f"invalid global anchor state: {field}={state}")
        states[field] = state
    returns = value.get("returns_pct") or {}
    sessions = value.get("source_session_dates") or {}
    if not isinstance(returns, Mapping) or not isinstance(sessions, Mapping):
        raise ContractError("global anchor returns/sessions must be objects")
    return {
        "status": (
            "available"
            if states.get("anchor_equity_majority_direction")
            else "partial"
        ),
        "factor_value_id": str(factor["factor_value_id"]),
        "states": states,
        "returns_pct": dict(returns),
        "source_session_dates": dict(sessions),
        "timing_semantics": value.get("timing_semantics"),
    }


def build_contextual_group_run(
    *,
    as_of_trade_date: str,
    calculated_at: str,
    factor_rows: Iterable[Mapping[str, Any]],
    observations: Iterable[Mapping[str, Any]],
    mode: str = "live",
    parameters: GroupParameters = DEFAULT_PARAMETERS,
    _inputs_validated: bool = False,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    """Build one label-free multi-view grouping run."""

    target = _trade_date(as_of_trade_date, "as_of_trade_date")
    decision_at = _aware(calculated_at, "calculated_at")
    calculated_iso = decision_at.isoformat(timespec="seconds")
    _validate_parameters(parameters)
    if mode not in {"live", "replay", "backtest"}:
        raise ContractError("mode must be live/replay/backtest")
    target_date = datetime.strptime(target, "%Y%m%d").date()
    local_calculation_date = decision_at.astimezone(CHINA_TZ).date()
    if (
        mode == "live"
        and local_calculation_date
        not in {target_date, target_date + timedelta(days=1)}
    ):
        raise ContractError(
            "live group calculation is outside the target/next-calendar-day boundary"
        )

    factors = [dict(row) for row in factor_rows]
    observation_rows = [dict(row) for row in observations]
    if not _inputs_validated:
        for row in factors:
            validate_factor_value(row)
        for row in observation_rows:
            validate_atomic_observation(row)

    universe_snapshot = _exact_universe_snapshot(
        observation_rows,
        target=target,
        decision_at=decision_at,
    )
    universe_codes = _universe_codes(universe_snapshot)
    all_memberships = _latest_observations(
        observation_rows,
        target=target,
        decision_at=decision_at,
        predicate=lambda row: (
            row.get("entity_type") == "stock"
            and row.get("dimension") == "universe"
            and row.get("field") == "membership"
        ),
    )
    missing_memberships = sorted(
        set(universe_codes) - set(all_memberships)
    )
    if missing_memberships:
        raise ContractError(
            "universe snapshot members are missing membership facts: "
            f"{missing_memberships[:3]}"
        )
    memberships = {
        code: all_memberships[code] for code in universe_codes
    }
    if not memberships:
        raise ContractError("no point-in-time universe memberships for group run")
    markets = _latest_observations(
        observation_rows,
        target=target,
        decision_at=decision_at,
        predicate=lambda row: (
            row.get("entity_type") == "market"
            and row.get("dimension") == "market_context"
            and row.get("field") == "market_snapshot"
        ),
    )
    market_observation = markets.get("CN-A")
    if market_observation is None:
        raise ContractError("point-in-time CN-A market context is required")

    base_index = _resolve_factors(
        factors,
        decision_at=decision_at,
        predicate=lambda row: (
            str(row.get("as_of_trade_date") or "") == target
            and is_curve_eligible(row)
            and _native_factor(row)
        ),
    )
    current_base = [
        row for row in base_index.values()
        if str(row["entity_id"]) in memberships
    ]
    if not current_base:
        raise ContractError("no eligible current factors for group run")

    anchor_index = _resolve_factors(
        factors,
        decision_at=decision_at,
        predicate=lambda row: (
            str(row.get("as_of_trade_date") or "") == target
            and row.get("entity_type") == "market"
            and row.get("entity_id") == ANCHOR_CONTEXT_ENTITY_ID
            and row.get("dimension") == GLOBAL_ANCHOR_DIMENSION
            and row.get("factor_id") == ANCHOR_CONTEXT_FACTOR_ID
            and row.get("factor_version") == ANCHOR_CONTEXT_FACTOR_VERSION
            and row.get("quality") == "calculated"
        ),
    )
    anchor_factor = (
        max(
            anchor_index.values(),
            key=lambda row: (
                _aware(row["calculated_at"], "anchor calculated_at"),
                str(row["factor_value_id"]),
            ),
        )
        if anchor_index
        else None
    )
    global_anchor_context = _global_anchor_context(anchor_factor)

    stock_curve_index = _resolve_factors(
        factors,
        decision_at=decision_at,
        predicate=lambda row: (
            str(row.get("as_of_trade_date") or "") == target
            and row.get("entity_type") == "stock"
            and row.get("dimension") == "causal_curve"
            and row.get("factor_id") == STOCK_CURVE_VECTOR_FACTOR_ID
            and row.get("factor_version") == CURVE_FACTOR_VERSION
            and row.get("quality") == "calculated"
        ),
    )
    track_aggregate_index = _resolve_factors(
        factors,
        decision_at=decision_at,
        predicate=lambda row: (
            str(row.get("as_of_trade_date") or "") == target
            and row.get("entity_type") == "track"
            and row.get("dimension") == "track_aggregate"
            and row.get("factor_id") == TRACK_AGGREGATE_VECTOR_FACTOR_ID
            and row.get("factor_version") == TRACK_FACTOR_VERSION
            and row.get("quality") == "calculated"
        ),
    )
    track_curve_index = _resolve_factors(
        factors,
        decision_at=decision_at,
        predicate=lambda row: (
            str(row.get("as_of_trade_date") or "") == target
            and row.get("entity_type") == "track"
            and row.get("dimension") == "causal_curve"
            and row.get("factor_id") == TRACK_CURVE_VECTOR_FACTOR_ID
            and row.get("factor_version") == CURVE_FACTOR_VERSION
            and row.get("quality") == "calculated"
        ),
    )
    stock_curves = {
        str(row["entity_id"]): row for row in stock_curve_index.values()
    }
    track_aggregates = {
        str(row["entity_id"]): row for row in track_aggregate_index.values()
    }
    track_curves = {
        str(row["entity_id"]): row for row in track_curve_index.values()
    }

    group_version_value = group_version(parameters)
    context_factor_version, stock_factor_version = _factor_versions(parameters)
    universe_id = f"user_universe_{canonical_digest(universe_codes)[:16]}"
    membership_values = {
        code: _membership_value(row) for code, row in memberships.items()
    }
    market_context = _market_context(
        market_observation,
        target=target,
    )
    cross_context, cross_assignments = _cross_sections(
        current_base,
        parameters=parameters,
    )

    concept_members: Dict[str, List[str]] = {}
    for code, membership in membership_values.items():
        for concept in membership["concepts"]:
            concept_members.setdefault(concept, []).append(code)

    track_context: Dict[str, Dict[str, Any]] = {}
    for concept, member_codes in sorted(concept_members.items()):
        aggregate = track_aggregates.get(concept)
        curve = track_curves.get(concept)
        aggregate_series = _vector_series(aggregate)
        curve_series = _vector_series(curve)
        if len(member_codes) < DEFAULT_CURVE_PARAMETERS.minimum_track_members:
            status = "thin_track"
        elif not aggregate_series:
            status = "eligible_factor_coverage_missing"
        else:
            status = "available"
        series_context = {}
        for series_id, aggregate_value in sorted(aggregate_series.items()):
            track_states = _curve_states(
                curve_series.get(series_id),
            )
            series_context[series_id] = {
                "level": _number(aggregate_value.get("level")),
                "member_count": aggregate_value.get("member_count"),
                "curve_state_vector": track_states,
            }
        track_context[concept] = {
            "status": status,
            "point_in_time_member_count": len(member_codes),
            "point_in_time_member_codes": sorted(member_codes),
            "series": series_context,
        }

    event_field = _event_field(
        stock_curves=stock_curves,
        track_curves=track_curves,
        universe_codes=universe_codes,
        parameters=parameters,
    )
    context_inputs = [
        *current_base,
        *stock_curves.values(),
        *track_aggregates.values(),
        *track_curves.values(),
    ]
    if anchor_factor is not None:
        context_inputs.append(anchor_factor)
    context_factor = _derived_factor(
        entity_type="market",
        entity_id=universe_id,
        factor_id=GROUP_CONTEXT_FACTOR_ID,
        factor_version=context_factor_version,
        value={
            "group_version": group_version_value,
            "label_usage": "none",
            "intersection_policy": "axes_remain_separate",
            "group_identity_protocol": {
                "algorithm": "sha256_canonical_json",
                "fields": [
                    "group_version",
                    "axis",
                    "state",
                    "series_id",
                    "concept",
                ],
                "materializer": (
                    "vaxstock.research.contextual_group.materialize_group_id"
                ),
            },
            "state_vector_schema": {
                "curve_state_fields": list(CURVE_STATE_FIELDS),
                "track_relation_fields": list(TRACK_RELATION_FIELDS),
                "unavailable_token": None,
                "detector_control_state": "none",
            },
            "universe": {
                "universe_id": universe_id,
                "entity_count": len(universe_codes),
                "entity_ids": universe_codes,
                "snapshot_observation_id": universe_snapshot["observation_id"],
                "snapshot_effective_date": universe_snapshot["effective_date"],
                "membership_semantics": (
                    (universe_snapshot.get("value") or {}).get(
                        "membership_semantics"
                    )
                ),
                "upstream_completeness": (
                    (universe_snapshot.get("value") or {}).get(
                        "upstream_completeness"
                    )
                ),
            },
            "market": market_context,
            "global_anchor": global_anchor_context,
            "event_field": event_field,
            "cross_sections": cross_context,
            "tracks": track_context,
            "parameters": asdict(parameters),
        },
        as_of_trade_date=target,
        calculated_at=calculated_iso,
        input_factors=context_inputs,
        input_observations=[
            universe_snapshot,
            market_observation,
            *memberships.values(),
        ],
    )

    base_by_code: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in current_base:
        base_by_code.setdefault(str(row["entity_id"]), {})[
            factor_series_id(row)
        ] = row

    stock_outputs: List[Dict[str, Any]] = []
    statistical_membership_count = 0
    partial_count = 0
    for code in universe_codes:
        membership = membership_values[code]
        current_series = base_by_code.get(code, {})
        stock_curve = stock_curves.get(code)
        curve_series = _vector_series(stock_curve)
        factor_groups: Dict[str, Dict[str, Any]] = {}
        stock_membership_count = 0
        unavailable: List[str] = []
        for series_id, base_factor in sorted(current_series.items()):
            cross = cross_assignments.get((code, series_id))
            if cross is None:
                cross_group = {
                    "status": (
                        cross_context.get(series_id, {}).get("status")
                        or "cross_section_unavailable"
                    ),
                    "rank_pct": None,
                    "bucket": None,
                }
                unavailable.append(f"{series_id}:cross_section")
            else:
                cross_group = dict(cross)
                stock_membership_count += 1

            curve_states = _curve_states(
                curve_series.get(series_id),
            )
            curve_state = curve_series.get(series_id)
            raw_curve_events = (
                curve_state.get("candidate_events") or []
                if isinstance(curve_state, Mapping)
                else []
            )
            if not isinstance(raw_curve_events, list):
                raise ContractError("curve candidate_events must be a list")
            curve_events = sorted({
                str(event).strip()
                for event in raw_curve_events
                if str(event).strip()
            })
            event_detection_ready = any(
                state is not None for state in curve_states[2:]
            )
            stock_membership_count += sum(
                state is not None for state in curve_states
            )

            track_relations = {}
            for concept in membership["concepts"]:
                track_series = (
                    track_context.get(concept, {}).get("series", {}).get(series_id)
                )
                if not isinstance(track_series, Mapping):
                    continue
                level_relation = _relation(
                    base_factor.get("value"), track_series.get("level")
                )
                stock_slope = (
                    curve_series.get(series_id, {}).get("slope_recent")
                    if isinstance(curve_series.get(series_id), Mapping)
                    else None
                )
                track_curve_for_series = _vector_series(
                    track_curves.get(concept)
                ).get(series_id, {})
                slope_relation = _relation(
                    stock_slope, track_curve_for_series.get("slope_recent")
                )
                stock_membership_count += sum(
                    state is not None
                    for state in (level_relation, slope_relation)
                )
                track_relations[concept] = [level_relation, slope_relation]
            factor_groups[series_id] = {
                "cross_section": cross_group,
                "curve_state_vector": curve_states,
                "curve_candidate_events": curve_events,
                "curve_event_detection_ready": event_detection_ready,
                "track_relation_vectors": track_relations,
            }

        market_membership_count = sum(
            state.get("status") == "available"
            for state in market_context["states"].values()
        )
        anchor_membership_count = sum(
            state is not None
            for state in global_anchor_context["states"].values()
        )
        stock_membership_count += (
            market_membership_count + anchor_membership_count
        )
        statistical_membership_count += stock_membership_count
        status = "available" if current_series else "no_eligible_current_factors"
        if unavailable or not current_series:
            partial_count += 1
        stock_inputs = [
            context_factor,
            *current_series.values(),
        ]
        if stock_curve is not None:
            stock_inputs.append(stock_curve)
        stock_outputs.append(
            _derived_factor(
                entity_type="stock",
                entity_id=code,
                factor_id=STOCK_GROUP_FACTOR_ID,
                factor_version=stock_factor_version,
                value={
                    "group_version": group_version_value,
                    "status": status,
                    "label_usage": "none",
                    "membership_effective_date": memberships[code][
                        "effective_date"
                    ],
                    "role": {
                        "value": membership["role"],
                        "audit_only": True,
                        "reason": "portfolio role is endogenous and excluded from statistical groups",
                    },
                    "concepts": membership["concepts"],
                    "track_status": {
                        concept: track_context.get(concept, {}).get(
                            "status", "track_unavailable"
                        )
                        for concept in membership["concepts"]
                    },
                    "selection_context": {
                        "market_regime": (
                            market_context["states"].get("regime") or {}
                        ).get("state"),
                        "macro_regime": (
                            market_context["states"].get("macro_regime") or {}
                        ).get("state"),
                        "systemic_event_state": event_field["systemic_state"],
                        "systemic_event_direction": (
                            event_field["systemic_direction"]
                            if event_field["systemic_state"] == "broad"
                            else None
                        ),
                        **global_anchor_context["states"],
                    },
                    "factor_groups": factor_groups,
                    "statistical_membership_count": stock_membership_count,
                    "unavailable": sorted(unavailable),
                },
                as_of_trade_date=target,
                calculated_at=calculated_iso,
                input_factors=stock_inputs,
                input_observations=[memberships[code]],
            )
        )

    outputs = [context_factor, *stock_outputs]
    input_identity = {
        "group_version": group_version_value,
        "parameters": asdict(parameters),
        "factor_value_ids": sorted(
            str(row["factor_value_id"]) for row in context_inputs
        ),
        "observation_ids": sorted(
            str(row["observation_id"])
            for row in [
                universe_snapshot,
                market_observation,
                *memberships.values(),
            ]
        ),
    }
    manifest = {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": "",
        "mode": mode,
        "as_of_trade_date": target,
        "universe_id": universe_id,
        "feature_set_version": FEATURE_SET_VERSION,
        "group_version": group_version_value,
        "select_version": NOT_EXECUTED,
        "forecast_version": NOT_EXECUTED,
        "input_digest": canonical_digest(input_identity),
        "generated_at": calculated_iso,
        "notes": [
            "group assignment is label-free; factor_results/outcomes are not inputs",
            "market, factor, curve and track axes remain separate; no fitted intersections",
            "the exact-date universe snapshot controls active membership; entry/exit never rewrites history",
            "raw curve events are preserved and aggregated into systemic/track/localized candidate fields",
            "holding/watchlist role is audit-only because it is an endogenous portfolio state",
            (
                "global anchor states are pre-open market context; they are "
                "not cross-sectional stock factors or executable returns"
            ),
            (
                "concept memberships are point-in-time user-universe labels, "
                "not official industry-index constituent history"
            ),
            "missing or structurally thin inputs produce unavailable states, never neutral values",
            "group memberships are candidates for later walk-forward evaluation, not effective claims",
        ],
        "stage": "group",
        "observation_count": 0,
        "factor_value_count": len(outputs),
        "observation_digest": canonical_digest([]),
        "factor_value_digest": canonical_digest(
            sorted(row["factor_value_id"] for row in outputs)
        ),
        "label_usage": "none",
        "context_factor_id": context_factor["factor_value_id"],
    }
    manifest["run_id"] = make_run_id(manifest)
    summary = {
        "as_of_trade_date": target,
        "universe_count": len(universe_codes),
        "current_base_factors": len(current_base),
        "cross_section_series": len(cross_context),
        "cross_section_available": sum(
            row.get("status") == "available"
            for row in cross_context.values()
        ),
        "track_count": len(track_context),
        "track_available": sum(
            row.get("status") == "available"
            for row in track_context.values()
        ),
        "track_thin": sum(
            row.get("status") == "thin_track"
            for row in track_context.values()
        ),
        "event_count": event_field["event_count"],
        "event_stock_breadth": event_field["event_stock_breadth"],
        "systemic_event_state": event_field["systemic_state"],
        "systemic_event_clusters": event_field["systemic_cluster_count"],
        "systemic_event_families": event_field[
            "systemic_event_family_count"
        ],
        "systemic_event_direction": event_field["systemic_direction"],
        "global_anchor_status": global_anchor_context["status"],
        "global_anchor_states": global_anchor_context["states"],
        "track_event_count": event_field["track_event_count"],
        "stock_group_vectors": len(stock_outputs),
        "partial_stock_vectors": partial_count,
        "statistical_memberships": statistical_membership_count,
        "outputs": len(outputs),
        "label_usage": "none",
        "effectiveness_status": "not_evaluated",
    }
    return manifest, outputs, summary
