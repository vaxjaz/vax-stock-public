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


CHINA_TZ = timezone(timedelta(hours=8))
FEATURE_SET_VERSION = "contextual_multiview_group_feature_set_v1"
GROUP_VERSION = "contextual_multiview_group_v1"
GROUP_CONTEXT_FACTOR_ID = "group_context_vector"
STOCK_GROUP_FACTOR_ID = "stock_group_vector"
GROUP_CONTEXT_FACTOR_VERSION = "group_context_vector_v1"
STOCK_GROUP_FACTOR_VERSION = "stock_group_vector_v1"
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

    memberships = _latest_observations(
        observation_rows,
        target=target,
        decision_at=decision_at,
        predicate=lambda row: (
            row.get("entity_type") == "stock"
            and row.get("dimension") == "universe"
            and row.get("field") == "membership"
        ),
    )
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
    universe_codes = sorted(memberships)
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

    context_inputs = [
        *current_base,
        *track_aggregates.values(),
        *track_curves.values(),
    ]
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
            },
            "market": market_context,
            "cross_sections": cross_context,
            "tracks": track_context,
            "parameters": asdict(parameters),
        },
        as_of_trade_date=target,
        calculated_at=calculated_iso,
        input_factors=context_inputs,
        input_observations=[market_observation, *memberships.values()],
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
                "track_relation_vectors": track_relations,
            }

        market_membership_count = sum(
            state.get("status") == "available"
            for state in market_context["states"].values()
        )
        stock_membership_count += market_membership_count
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
            for row in [market_observation, *memberships.values()]
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
            "holding/watchlist role is audit-only because it is an endogenous portfolio state",
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
        "stock_group_vectors": len(stock_outputs),
        "partial_stock_vectors": partial_count,
        "statistical_memberships": statistical_membership_count,
        "outputs": len(outputs),
        "label_usage": "none",
        "effectiveness_status": "not_evaluated",
    }
    return manifest, outputs, summary
