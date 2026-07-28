# -*- coding: utf-8 -*-
"""Strictly causal curve features for stock and track factor histories.

The implementation is deliberately model-neutral:

* only an explicit registry of continuous source factors is eligible;
* time is measured in verified trading-session order, not calendar distance;
* every statistic uses the current point and its past only;
* robust medians, Theil-Sen slopes, and MAD-style scales suppress isolated
  noise without erasing the raw level;
* event flags are versioned *candidate detectors*, never effectiveness claims.

Importing this module performs no filesystem or network I/O.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from numbers import Real
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

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
FEATURE_SET_VERSION = "causal_curve_feature_set_v3"
CURVE_FACTOR_VERSION = "causal_curve_theil_mad_vector_v3"
TRACK_FACTOR_VERSION = "track_cross_section_median_vector_v2"
ELIGIBILITY_VERSION = "continuous_factor_registry_v1"
NOT_EXECUTED = "not_executed"
STOCK_CURVE_VECTOR_FACTOR_ID = "stock_curve_vector"
TRACK_AGGREGATE_VECTOR_FACTOR_ID = "track_aggregate_vector"
TRACK_CURVE_VECTOR_FACTOR_ID = "track_curve_vector"

DERIVED_DIMENSIONS = {"causal_curve", "track_aggregate"}

# This is a data-semantics registry, not a statistical winner list. Raw levels
# outside it remain in factor_values and can be added by a forward-only version.
LEGACY_CONTINUOUS_FACTORS = {
    "legacy.price_vs_ma20_pct",
    "legacy.position_20d_pct",
    "legacy.position_52w_pct",
    "legacy.recent_5d_change_pct",
    "legacy.recent_20d_change_pct",
    "legacy.volume_ratio_20d",
    "legacy.turnover_pct",
    "legacy.turnover_zscore",
    "legacy.main_inflow_5d",
    "legacy.main_inflow_10d",
    "legacy.inflow_slope",
    "legacy.macd_hist",
    "legacy.rsi_14",
    "legacy.right_side_score",
    "legacy.pe_percentile_1y",
    "legacy.pb_percentile_1y",
    "legacy.np_yoy",
    "legacy.roe_avg",
    "legacy.gross_margin",
}

# Eligibility is intentionally explicit.  A future E factor does not become a
# curve input merely because it happens to be numeric; its semantics must first
# be reviewed and added to this versioned registry.
EXPECTATION_CONTINUOUS_FACTOR_PREFIXES = (
    "seller_consensus_eps_median_90d.",
    "seller_consensus_eps_org_count_90d.",
    "seller_consensus_net_profit_median_wan_90d.",
    "seller_consensus_net_profit_org_count_90d.",
    "seller_report_row_count_90d.",
    "seller_reported_forward_pe_median_90d.",
    "eps_required_at_seller_reported_pe_median.",
    "current_forward_pe_from_seller_consensus_eps.",
    "current_forward_pe_vs_seller_reported_pe_gap_pct.",
    "guidance_net_profit_mid_wan.",
    "preannouncement_seller_net_profit_median_wan.",
    "guidance_vs_preannouncement_seller_net_profit_gap_pct.",
)


@dataclass(frozen=True)
class CurveParameters:
    smooth_window: int = 3
    slope_window: int = 5
    anomaly_history: int = 20
    trend_window: int = 10
    minimum_residuals: int = 5
    anomaly_z_threshold: float = 3.5
    shift_z_threshold: float = 3.0
    reversal_strength_threshold: float = 0.75
    shift_persistence: float = 0.8
    minimum_track_members: int = 3

    @property
    def maximum_history(self) -> int:
        return max(
            self.anomaly_history + self.trend_window + 1,
            self.slope_window * 2,
            self.smooth_window,
        )


DEFAULT_PARAMETERS = CurveParameters()


def _parameter_payload(parameters: CurveParameters) -> Dict[str, Any]:
    return asdict(parameters)


def curve_factor_version(parameters: CurveParameters) -> str:
    """Bind non-default parameterizations to a distinct factor identity."""

    if parameters == DEFAULT_PARAMETERS:
        return CURVE_FACTOR_VERSION
    return (
        f"{CURVE_FACTOR_VERSION}."
        f"{canonical_digest(_parameter_payload(parameters))[:12]}"
    )


def track_factor_version(parameters: CurveParameters) -> str:
    """Bind the minimum-member rule to the aggregate factor identity."""

    if parameters.minimum_track_members == DEFAULT_PARAMETERS.minimum_track_members:
        return TRACK_FACTOR_VERSION
    return (
        f"{TRACK_FACTOR_VERSION}."
        f"{canonical_digest({'minimum_track_members': parameters.minimum_track_members})[:12]}"
    )


def _validate_parameters(parameters: CurveParameters) -> None:
    integer_fields = {
        "smooth_window": parameters.smooth_window,
        "slope_window": parameters.slope_window,
        "anomaly_history": parameters.anomaly_history,
        "trend_window": parameters.trend_window,
        "minimum_residuals": parameters.minimum_residuals,
        "minimum_track_members": parameters.minimum_track_members,
    }
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in integer_fields.values()
    ):
        raise ContractError("curve window parameters must be integers")
    if parameters.smooth_window < 1:
        raise ContractError("smooth_window must be positive")
    if parameters.slope_window < 2:
        raise ContractError("slope_window must be at least 2")
    if parameters.trend_window < 2:
        raise ContractError("trend_window must be at least 2")
    if parameters.minimum_residuals < 2:
        raise ContractError("minimum_residuals must be at least 2")
    if parameters.minimum_track_members < 2:
        raise ContractError("minimum_track_members must be at least 2")
    if parameters.anomaly_history < parameters.minimum_residuals:
        raise ContractError("anomaly_history must cover minimum_residuals")
    if parameters.trend_window < parameters.minimum_residuals:
        raise ContractError("trend_window must cover minimum_residuals")
    positive_thresholds = (
        parameters.anomaly_z_threshold,
        parameters.shift_z_threshold,
        parameters.reversal_strength_threshold,
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(float(value))
        or float(value) <= 0
        for value in positive_thresholds
    ):
        raise ContractError("curve detector thresholds must be positive")
    if (
        isinstance(parameters.shift_persistence, bool)
        or not isinstance(parameters.shift_persistence, Real)
        or not math.isfinite(float(parameters.shift_persistence))
        or not 0 < float(parameters.shift_persistence) <= 1
    ):
        raise ContractError("shift_persistence must be within (0, 1]")


def _aware(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include timezone")
    return parsed


def _trade_date(value: Any, field: str = "trade_date") -> str:
    text = str(value or "").strip()
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ContractError(f"{field} must be YYYYMMDD") from exc
    return text


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _theil_sen(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    slopes = [
        (float(values[j]) - float(values[i])) / float(j - i)
        for i in range(len(values) - 1)
        for j in range(i + 1, len(values))
    ]
    return float(median(slopes)) if slopes else None


def _trend_prediction(values: Sequence[float]) -> Optional[float]:
    slope = _theil_sen(values)
    if slope is None:
        return None
    intercept = median(
        float(value) - slope * index for index, value in enumerate(values)
    )
    return float(intercept + slope * len(values))


def _mad_scale(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    center = float(median(values))
    mad = float(median(abs(float(value) - center) for value in values))
    scale = 1.4826 * mad
    return scale if scale > 0 else None


def _movement_scale(values: Sequence[float]) -> Optional[float]:
    """Robust typical absolute per-session movement.

    The median absolute step is deliberately not a dispersion around the
    median step: a clean -1,+1 reversal has real movement even though the
    median change is zero.  Exact flat histories retain an explicit no-scale
    state.
    """

    if len(values) < 2:
        return None
    changes = [
        float(values[index]) - float(values[index - 1])
        for index in range(1, len(values))
    ]
    absolute_step = float(median(abs(change) for change in changes))
    return absolute_step if absolute_step > 0 else None


def _sign(value: Optional[float]) -> int:
    if value is None or value == 0:
        return 0
    return 1 if value > 0 else -1


def _robust_score(
    value: float,
    baseline: Sequence[float],
) -> Tuple[Optional[float], bool]:
    """Return (robust z, exact zero-scale break)."""

    if not baseline:
        return None, False
    center = float(median(baseline))
    scale = _mad_scale(baseline)
    deviation = float(value) - center
    if scale is None:
        if deviation == 0:
            return 0.0, False
        return None, True
    return deviation / scale, False


def compute_causal_curve(
    values: Sequence[float],
    *,
    parameters: CurveParameters = DEFAULT_PARAMETERS,
) -> Dict[str, Any]:
    """Compute one end-of-series feature vector without future observations."""

    _validate_parameters(parameters)
    numeric = [_number(value) for value in values]
    if not numeric or any(value is None for value in numeric):
        raise ContractError("curve values must be non-empty finite numbers")
    clean = [float(value) for value in numeric if value is not None]
    n = len(clean)
    unavailable: List[str] = []
    events: List[str] = []
    current = clean[-1]
    smooth = float(median(clean[-parameters.smooth_window:]))
    delta_1 = current - clean[-2] if n >= 2 else None
    if delta_1 is None:
        unavailable.append("delta_1:requires_2_sessions")

    recent_slope = None
    prior_slope = None
    acceleration = None
    reversal_strength = None
    turning_candidate = None
    slope_window = parameters.slope_window
    if n >= slope_window:
        recent_slope = _theil_sen(clean[-slope_window:])
    else:
        unavailable.append(f"slope_recent:requires_{slope_window}_sessions")
    if n >= slope_window * 2:
        prior_slope = _theil_sen(clean[-2 * slope_window:-slope_window])
        acceleration = (
            (recent_slope - prior_slope) / slope_window
            if recent_slope is not None and prior_slope is not None
            else None
        )
        noise_history = clean[:-1][-parameters.anomaly_history:]
        movement_scale = _movement_scale(noise_history)
        if (
            _sign(prior_slope) != 0
            and _sign(recent_slope) != 0
            and _sign(prior_slope) != _sign(recent_slope)
        ):
            if movement_scale is None:
                unavailable.append("slope_reversal_strength:zero_movement_scale")
            else:
                reversal_strength = (
                    _sign(recent_slope)
                    * min(abs(prior_slope), abs(recent_slope))
                    / movement_scale
                )
                if abs(reversal_strength) >= parameters.reversal_strength_threshold:
                    turning_candidate = "up" if reversal_strength > 0 else "down"
                    events.append(f"turning_{turning_candidate}")
    else:
        movement_scale = _movement_scale(
            clean[:-1][-parameters.anomaly_history:]
        )
        unavailable.append(
            f"slope_prior_and_acceleration:requires_{slope_window * 2}_sessions"
        )

    innovation = None
    innovation_z = None
    anomaly_candidate = None
    anomaly_zero_scale_break = False
    history = clean[:-1]
    if len(history) >= parameters.trend_window:
        current_prediction = _trend_prediction(history[-parameters.trend_window:])
        if current_prediction is not None:
            innovation = current - current_prediction
        residuals: List[float] = []
        start = max(2, len(history) - parameters.anomaly_history)
        for index in range(start, len(history)):
            train = history[max(0, index - parameters.trend_window):index]
            if len(train) < parameters.minimum_residuals:
                continue
            prediction = _trend_prediction(train)
            if prediction is not None:
                residuals.append(history[index] - prediction)
        if innovation is not None and len(residuals) >= parameters.minimum_residuals:
            innovation_z, anomaly_zero_scale_break = _robust_score(
                innovation, residuals
            )
            if anomaly_zero_scale_break or (
                innovation_z is not None
                and abs(innovation_z) >= parameters.anomaly_z_threshold
            ):
                anomaly_candidate = "positive" if innovation > median(residuals) else "negative"
                events.append(f"anomaly_{anomaly_candidate}")
        else:
            unavailable.append(
                f"innovation_z:requires_{parameters.minimum_residuals}_causal_residuals"
            )
    else:
        unavailable.append(
            f"innovation:requires_{parameters.trend_window + 1}_sessions"
        )

    level_shift = None
    level_shift_z = None
    change_point_candidate = None
    shift_zero_scale_break = False
    if n >= slope_window * 2:
        prior_segment = clean[-2 * slope_window:-slope_window]
        recent_segment = clean[-slope_window:]
        prior_fit_slope = _theil_sen(prior_segment)
        prior_fit_intercept = (
            float(
                median(
                    value - float(prior_fit_slope) * index
                    for index, value in enumerate(prior_segment)
                )
            )
            if prior_fit_slope is not None
            else float(median(prior_segment))
        )
        prior_residuals = [
            value - (prior_fit_intercept + float(prior_fit_slope or 0.0) * index)
            for index, value in enumerate(prior_segment)
        ]
        recent_residuals = [
            value
            - (
                prior_fit_intercept
                + float(prior_fit_slope or 0.0) * (slope_window + index)
            )
            for index, value in enumerate(recent_segment)
        ]
        level_shift = float(median(recent_residuals))
        level_scale = _mad_scale(prior_residuals)
        scale_candidates = [
            value
            for value in (level_scale, movement_scale)
            if value is not None and value > 0
        ]
        shift_scale = max(scale_candidates) if scale_candidates else None
        if shift_scale is None:
            if level_shift != 0:
                shift_zero_scale_break = True
        else:
            level_shift_z = level_shift / shift_scale
        if level_shift > 0:
            persistence = sum(value > 0 for value in recent_residuals) / slope_window
            direction = "up"
        elif level_shift < 0:
            persistence = sum(value < 0 for value in recent_residuals) / slope_window
            direction = "down"
        else:
            persistence = 0.0
            direction = None
        threshold_passed = shift_zero_scale_break or (
            level_shift_z is not None
            and abs(level_shift_z) >= parameters.shift_z_threshold
        )
        if (
            direction is not None
            and threshold_passed
            and persistence >= parameters.shift_persistence
        ):
            change_point_candidate = direction
            events.append(f"change_point_{direction}")
    else:
        persistence = None
        unavailable.append(
            f"level_shift:requires_{slope_window * 2}_sessions"
        )

    return {
        "sample_count": n,
        "level": current,
        "smoothed_level": smooth,
        "delta_1": delta_1,
        "slope_recent": recent_slope,
        "slope_prior": prior_slope,
        "acceleration": acceleration,
        "movement_scale": movement_scale,
        "slope_reversal_strength": reversal_strength,
        "turning_candidate": turning_candidate,
        "innovation": innovation,
        "innovation_robust_z": innovation_z,
        "innovation_zero_scale_break": anomaly_zero_scale_break,
        "anomaly_candidate": anomaly_candidate,
        "level_shift_detrended": level_shift,
        "level_shift_robust_z": level_shift_z,
        "level_shift_zero_scale_break": shift_zero_scale_break,
        "shift_persistence": persistence,
        "change_point_candidate": change_point_candidate,
        "candidate_events": events,
        "unavailable": unavailable,
        "detector_status": "candidate_not_validated",
        "parameters": _parameter_payload(parameters),
        "parameter_version": curve_factor_version(parameters),
    }


def is_curve_eligible(row: Mapping[str, Any]) -> bool:
    if row.get("entity_type") != "stock":
        return False
    if row.get("dimension") in DERIVED_DIMENSIONS:
        return False
    if _number(row.get("value")) is None or row.get("quality") != "calculated":
        return False
    factor_id = str(row.get("factor_id") or "")
    if factor_id in LEGACY_CONTINUOUS_FACTORS:
        return True
    return (
        str(row.get("dimension") or "") == "E"
        and factor_id.startswith(EXPECTATION_CONTINUOUS_FACTOR_PREFIXES)
    )


def _is_native_point_in_time(row: Mapping[str, Any]) -> bool:
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
    dimension: str,
    factor_id: str,
    factor_version: str,
    value: Any,
    as_of_trade_date: str,
    effective_date: str,
    calculated_at: str,
    input_factors: Iterable[Mapping[str, Any]],
    input_observations: Iterable[Mapping[str, Any]] = (),
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    factors = {
        (str(row["as_of_trade_date"]), str(row["factor_value_id"])): row
        for row in input_factors
    }
    observations = {
        str(row["observation_id"]): row for row in input_observations
    }
    refs = [
        _factor_ref(factors[key]) for key in sorted(factors)
    ]
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
        "dimension": dimension,
        "factor_id": factor_id,
        "factor_version": factor_version,
        "value": value,
        "as_of_trade_date": as_of_trade_date,
        "effective_date": effective_date,
        "available_at": available.isoformat(timespec="seconds"),
        "calculated_at": calculated.isoformat(timespec="seconds"),
        "input_observation_ids": observation_ids,
        "input_factor_refs": refs,
        "input_digest": factor_input_digest(observation_ids, refs),
        "quality": "calculated",
    }
    if extra:
        row.update(dict(extra))
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _latest_memberships(
    observations: Iterable[Mapping[str, Any]],
    *,
    decision_at: datetime,
    inputs_validated: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    by_code: Dict[str, List[Dict[str, Any]]] = {}
    for raw in observations:
        row = dict(raw)
        if not inputs_validated:
            validate_atomic_observation(row)
        if (
            row.get("entity_type") != "stock"
            or row.get("dimension") != "universe"
            or row.get("field") != "membership"
            or _aware(row.get("available_at"), "membership available_at") > decision_at
        ):
            continue
        by_code.setdefault(str(row["entity_id"]), []).append(row)
    for rows in by_code.values():
        rows.sort(
            key=lambda row: (
                str(row.get("effective_date") or ""),
                _aware(row.get("available_at"), "membership available_at"),
                str(row.get("observation_id") or ""),
            )
        )
    return by_code


def _membership_at(
    memberships: Mapping[str, Sequence[Mapping[str, Any]]],
    code: str,
    trade_date: str,
) -> Optional[Dict[str, Any]]:
    usable = [
        row for row in memberships.get(code, [])
        if str(row.get("effective_date") or "") <= trade_date
    ]
    return dict(usable[-1]) if usable else None


def _resolve_factors(
    rows: Iterable[Mapping[str, Any]],
    *,
    decision_at: datetime,
    predicate,
    inputs_validated: bool = False,
) -> Dict[Tuple[str, str, str, str, str, str], Dict[str, Any]]:
    resolved: Dict[Tuple[str, str, str, str, str, str], Dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        if not inputs_validated:
            validate_factor_value(row)
        if not predicate(row):
            continue
        if _aware(row.get("calculated_at"), "factor calculated_at") > decision_at:
            continue
        if not _is_native_point_in_time(row):
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


def _series_key(row: Mapping[str, Any]) -> Tuple[str, str, str, str, str]:
    return (
        str(row["entity_type"]),
        str(row["entity_id"]),
        str(row["dimension"]),
        str(row["factor_id"]),
        str(row["factor_version"]),
    )


def _contiguous_suffix(
    rows: Sequence[Mapping[str, Any]],
    *,
    session_index: Mapping[str, int],
    maximum_history: int,
) -> List[Dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: str(row["as_of_trade_date"]))
    if not ordered:
        return []
    suffix = [dict(ordered[-1])]
    expected = session_index[str(ordered[-1]["as_of_trade_date"])] - 1
    for raw in reversed(ordered[:-1]):
        index = session_index.get(str(raw["as_of_trade_date"]))
        if index != expected:
            break
        suffix.append(dict(raw))
        expected -= 1
        if len(suffix) >= maximum_history:
            break
    suffix.reverse()
    return suffix


def _base_series_id(row: Mapping[str, Any]) -> str:
    return (
        f"{row['dimension']}::{row['factor_id']}::"
        f"{row['factor_version']}"
    )


def _curve_series(
    current: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    *,
    parameters: CurveParameters,
    previous_series: Optional[Mapping[str, Any]] = None,
    session_index: Optional[Mapping[str, int]] = None,
) -> Tuple[Dict[str, Any], bool]:
    direct_values = [_number(row.get("value")) for row in history]
    if any(value is None for value in direct_values):
        raise ContractError("curve history contains a non-numeric value")
    state_dates = [str(row["as_of_trade_date"]) for row in history]
    state_values = [
        float(value) for value in direct_values if value is not None
    ]
    lineage_mode = "direct_window"
    used_previous = False
    if previous_series is not None:
        raw_dates = previous_series.get("state_trade_dates")
        raw_values = previous_series.get("state_values")
        if not isinstance(raw_dates, list) or not isinstance(raw_values, list):
            raise ContractError("previous curve series state is missing")
        if len(raw_dates) != len(raw_values) or not raw_dates:
            raise ContractError("previous curve series state lengths do not match")
        previous_dates = [
            _trade_date(value, "previous curve series state_trade_dates")
            for value in raw_dates
        ]
        previous_values = [_number(value) for value in raw_values]
        if any(value is None for value in previous_values):
            raise ContractError(
                "previous curve series state contains non-numeric values"
            )
        if len(previous_dates) > parameters.maximum_history:
            raise ContractError(
                "previous curve series state exceeds maximum history"
            )
        if session_index is not None:
            indexes = [session_index.get(value) for value in previous_dates]
            if any(value is None for value in indexes) or any(
                int(indexes[index]) != int(indexes[index - 1]) + 1
                for index in range(1, len(indexes))
            ):
                raise ContractError(
                    "previous curve series state is not session-contiguous"
                )
            current_index = session_index.get(str(current["as_of_trade_date"]))
            if (
                current_index is None
                or int(indexes[-1]) != int(current_index) - 1
            ):
                raise ContractError(
                    "previous curve series does not end at the prior session"
                )
        state_dates = [
            *previous_dates,
            str(current["as_of_trade_date"]),
        ][-parameters.maximum_history:]
        state_values = [
            *[float(value) for value in previous_values if value is not None],
            float(current["value"]),
        ][-parameters.maximum_history:]
        lineage_mode = "previous_curve_plus_current_factor"
        used_previous = True
    curve = compute_causal_curve(
        state_values,
        parameters=parameters,
    )
    # Parameter identity is stored once on the enclosing vector rather than
    # repeated for every series.
    curve.pop("parameters", None)
    curve.pop("parameter_version", None)
    curve.update(
        {
            "window_start_trade_date": state_dates[0],
            "window_end_trade_date": state_dates[-1],
            "state_trade_dates": state_dates,
            "state_values": state_values,
            "lineage_mode": lineage_mode,
            "base_entity_type": str(current["entity_type"]),
            "base_dimension": str(current["dimension"]),
            "base_factor_id": str(current["factor_id"]),
            "base_factor_version": str(current["factor_version"]),
            "eligibility_version": ELIGIBILITY_VERSION,
        }
    )
    return curve, used_previous


def build_causal_curve_run(
    *,
    as_of_trade_date: str,
    calculated_at: str,
    factor_rows: Iterable[Mapping[str, Any]],
    observations: Iterable[Mapping[str, Any]],
    mode: str = "live",
    parameters: CurveParameters = DEFAULT_PARAMETERS,
    _inputs_validated: bool = False,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    """Build current stock curves plus point-in-time concept-track curves.

    ``_inputs_validated`` is an internal replay optimization.  Callers outside
    the replay service must keep the default so every supplied contract row is
    verified before use.
    """

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
            "live curve calculation is outside the target/next-calendar-day boundary"
        )
    materialized_factors = [dict(row) for row in factor_rows]
    materialized_observations = [dict(row) for row in observations]

    base = _resolve_factors(
        materialized_factors,
        decision_at=decision_at,
        predicate=lambda row: (
            str(row.get("as_of_trade_date") or "") <= target
            and is_curve_eligible(row)
        ),
        inputs_validated=_inputs_validated,
    )
    session_dates = sorted({key[0] for key in base})
    if target not in session_dates:
        raise ContractError("no eligible native point-in-time factors for target date")
    session_index = {trade_date: index for index, trade_date in enumerate(session_dates)}
    memberships = _latest_memberships(
        materialized_observations,
        decision_at=decision_at,
        inputs_validated=_inputs_validated,
    )

    base_by_series: Dict[Tuple[str, str, str, str, str], List[Dict[str, Any]]] = {}
    current_base: List[Dict[str, Any]] = []
    for row in base.values():
        base_by_series.setdefault(_series_key(row), []).append(row)
        if str(row["as_of_trade_date"]) == target:
            current_base.append(row)

    curve_version = curve_factor_version(parameters)
    aggregate_version = track_factor_version(parameters)
    prior_curves = _resolve_factors(
        materialized_factors,
        decision_at=decision_at,
        predicate=lambda row: (
            row.get("dimension") == "causal_curve"
            and row.get("factor_version") == curve_version
            and str(row.get("as_of_trade_date") or "") < target
            and row.get("quality") == "calculated"
        ),
        inputs_validated=_inputs_validated,
    )
    previous_session = (
        session_dates[session_index[target] - 1]
        if session_index[target] > 0
        else None
    )
    previous_curve_index = {
        (
            str(row["as_of_trade_date"]),
            str(row["entity_type"]),
            str(row["entity_id"]),
            str(row["factor_id"]),
        ): row
        for row in prior_curves.values()
    }

    def previous_vector(
        entity_type: str,
        entity_id: str,
        factor_id: str,
    ) -> Optional[Dict[str, Any]]:
        if previous_session is None:
            return None
        return previous_curve_index.get(
            (previous_session, entity_type, entity_id, factor_id)
        )

    stock_groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in current_base:
        stock_groups.setdefault(
            (str(row["entity_type"]), str(row["entity_id"])),
            [],
        ).append(row)

    stock_curves: List[Dict[str, Any]] = []
    stock_curve_series_count = 0
    for (entity_type, entity_id), current_rows in sorted(stock_groups.items()):
        previous = previous_vector(
            entity_type,
            entity_id,
            STOCK_CURVE_VECTOR_FACTOR_ID,
        )
        previous_value = previous.get("value") if previous else {}
        previous_series_map = (
            previous_value.get("series")
            if isinstance(previous_value, Mapping)
            else {}
        ) or {}
        if not isinstance(previous_series_map, Mapping):
            raise ContractError("previous stock curve vector series must be an object")
        series_payload: Dict[str, Dict[str, Any]] = {}
        dependencies: List[Mapping[str, Any]] = []
        used_previous = False
        candidate_events: List[Dict[str, str]] = []
        for current in sorted(current_rows, key=_base_series_id):
            series_id = _base_series_id(current)
            history = _contiguous_suffix(
                base_by_series[_series_key(current)],
                session_index=session_index,
                maximum_history=parameters.maximum_history,
            )
            previous_series = previous_series_map.get(series_id)
            if previous_series is not None and not isinstance(
                previous_series, Mapping
            ):
                raise ContractError("previous stock curve series must be an object")
            curve, chained = _curve_series(
                current,
                history,
                parameters=parameters,
                previous_series=previous_series,
                session_index=session_index,
            )
            series_payload[series_id] = curve
            used_previous = used_previous or chained
            dependencies.extend([current] if chained else history)
            candidate_events.extend(
                {"series_id": series_id, "event": str(event)}
                for event in curve["candidate_events"]
            )
        if used_previous and previous is not None:
            dependencies.append(previous)
        stock_curve_series_count += len(series_payload)
        stock_curves.append(
            _derived_factor(
                entity_type=entity_type,
                entity_id=entity_id,
                dimension="causal_curve",
                factor_id=STOCK_CURVE_VECTOR_FACTOR_ID,
                factor_version=curve_version,
                value={
                    "series": series_payload,
                    "series_count": len(series_payload),
                    "candidate_events": candidate_events,
                    "parameters": _parameter_payload(parameters),
                    "parameter_version": curve_version,
                    "detector_status": "candidate_not_validated",
                },
                as_of_trade_date=target,
                effective_date=target,
                calculated_at=calculated_iso,
                input_factors=dependencies,
            )
        )

    track_groups: Dict[
        str,
        Dict[str, List[Tuple[Dict[str, Any], Dict[str, Any]]]],
    ] = {}
    for row in current_base:
        code = str(row["entity_id"])
        membership = _membership_at(memberships, code, target)
        concepts = (
            list((membership.get("value") or {}).get("concepts") or [])
            if membership
            else []
        )
        for concept in sorted({
            str(value).strip() for value in concepts if str(value).strip()
        }):
            track_groups.setdefault(concept, {}).setdefault(
                _base_series_id(row), []
            ).append((row, membership))

    track_factors: List[Dict[str, Any]] = []
    track_aggregate_series_count = 0
    for concept, grouped_series in sorted(track_groups.items()):
        series_payload: Dict[str, Dict[str, Any]] = {}
        input_factors: List[Mapping[str, Any]] = []
        input_observations: List[Mapping[str, Any]] = []
        all_member_codes = set()
        for series_id, members in sorted(grouped_series.items()):
            member_rows = [row for row, _ in members]
            if len(member_rows) < parameters.minimum_track_members:
                continue
            usable_values = [
                float(value)
                for value in (_number(row.get("value")) for row in member_rows)
                if value is not None
            ]
            if len(usable_values) < parameters.minimum_track_members:
                continue
            exemplar = member_rows[0]
            member_codes = sorted(
                str(row["entity_id"]) for row in member_rows
            )
            series_payload[series_id] = {
                "level": float(median(usable_values)),
                "member_count": len(usable_values),
                "member_codes": member_codes,
                "base_dimension": str(exemplar["dimension"]),
                "base_factor_id": str(exemplar["factor_id"]),
                "base_factor_version": str(exemplar["factor_version"]),
            }
            input_factors.extend(member_rows)
            input_observations.extend(
                membership for _, membership in members
            )
            all_member_codes.update(member_codes)
        if not series_payload:
            continue
        track_aggregate_series_count += len(series_payload)
        track_factors.append(
            _derived_factor(
                entity_type="track",
                entity_id=concept,
                dimension="track_aggregate",
                factor_id=TRACK_AGGREGATE_VECTOR_FACTOR_ID,
                factor_version=aggregate_version,
                value={
                    "series": series_payload,
                    "series_count": len(series_payload),
                    "member_universe_count": len(all_member_codes),
                    "member_universe_codes": sorted(all_member_codes),
                    "minimum_track_members": parameters.minimum_track_members,
                    "aggregation": "cross_section_median",
                    "eligibility_version": ELIGIBILITY_VERSION,
                },
                as_of_trade_date=target,
                effective_date=target,
                calculated_at=calculated_iso,
                input_factors=input_factors,
                input_observations=input_observations,
            )
        )

    prior_tracks = _resolve_factors(
        materialized_factors,
        decision_at=decision_at,
        predicate=lambda row: (
            row.get("entity_type") == "track"
            and row.get("dimension") == "track_aggregate"
            and row.get("factor_version") == aggregate_version
            and row.get("factor_id") == TRACK_AGGREGATE_VECTOR_FACTOR_ID
            and str(row.get("as_of_trade_date") or "") < target
            and row.get("quality") == "calculated"
        ),
        inputs_validated=_inputs_validated,
    )
    aggregate_rows = [*prior_tracks.values(), *track_factors]
    aggregate_history: Dict[
        Tuple[str, str],
        List[Tuple[Dict[str, Any], Dict[str, Any]]],
    ] = {}
    for aggregate in aggregate_rows:
        value = aggregate.get("value")
        series_map = value.get("series") if isinstance(value, Mapping) else None
        if not isinstance(series_map, Mapping):
            raise ContractError("track aggregate vector series must be an object")
        for series_id, series_value in series_map.items():
            if not isinstance(series_value, Mapping):
                raise ContractError("track aggregate series must be an object")
            level = _number(series_value.get("level"))
            if level is None:
                raise ContractError("track aggregate series level must be numeric")
            pseudo = {
                "entity_type": "track",
                "entity_id": str(aggregate["entity_id"]),
                "dimension": str(series_value["base_dimension"]),
                "factor_id": str(series_value["base_factor_id"]),
                "factor_version": str(series_value["base_factor_version"]),
                "value": level,
                "as_of_trade_date": str(aggregate["as_of_trade_date"]),
                "effective_date": str(aggregate["effective_date"]),
            }
            aggregate_history.setdefault(
                (str(aggregate["entity_id"]), str(series_id)),
                [],
            ).append((aggregate, pseudo))

    track_curves: List[Dict[str, Any]] = []
    track_curve_series_count = 0
    for aggregate in sorted(
        track_factors, key=lambda row: str(row["entity_id"])
    ):
        concept = str(aggregate["entity_id"])
        previous = previous_vector(
            "track",
            concept,
            TRACK_CURVE_VECTOR_FACTOR_ID,
        )
        previous_value = previous.get("value") if previous else {}
        previous_series_map = (
            previous_value.get("series")
            if isinstance(previous_value, Mapping)
            else {}
        ) or {}
        if not isinstance(previous_series_map, Mapping):
            raise ContractError("previous track curve vector series must be an object")
        current_series_map = aggregate["value"]["series"]
        series_payload: Dict[str, Dict[str, Any]] = {}
        dependencies: List[Mapping[str, Any]] = []
        used_previous = False
        candidate_events: List[Dict[str, str]] = []
        for series_id, current_value in sorted(current_series_map.items()):
            pairs = aggregate_history[(concept, series_id)]
            pseudo_rows = [pseudo for _, pseudo in pairs]
            history = _contiguous_suffix(
                pseudo_rows,
                session_index=session_index,
                maximum_history=parameters.maximum_history,
            )
            history_dates = {
                str(row["as_of_trade_date"]) for row in history
            }
            previous_series = previous_series_map.get(series_id)
            if previous_series is not None and not isinstance(
                previous_series, Mapping
            ):
                raise ContractError("previous track curve series must be an object")
            current_pseudo = next(
                pseudo for source, pseudo in pairs
                if source["factor_value_id"] == aggregate["factor_value_id"]
            )
            curve, chained = _curve_series(
                current_pseudo,
                history,
                parameters=parameters,
                previous_series=previous_series,
                session_index=session_index,
            )
            series_payload[series_id] = curve
            used_previous = used_previous or chained
            if chained:
                dependencies.append(aggregate)
            else:
                dependencies.extend(
                    source for source, pseudo in pairs
                    if str(pseudo["as_of_trade_date"]) in history_dates
                )
            candidate_events.extend(
                {"series_id": series_id, "event": str(event)}
                for event in curve["candidate_events"]
            )
        if used_previous and previous is not None:
            dependencies.append(previous)
        track_curve_series_count += len(series_payload)
        track_curves.append(
            _derived_factor(
                entity_type="track",
                entity_id=concept,
                dimension="causal_curve",
                factor_id=TRACK_CURVE_VECTOR_FACTOR_ID,
                factor_version=curve_version,
                value={
                    "series": series_payload,
                    "series_count": len(series_payload),
                    "candidate_events": candidate_events,
                    "parameters": _parameter_payload(parameters),
                    "parameter_version": curve_version,
                    "detector_status": "candidate_not_validated",
                },
                as_of_trade_date=target,
                effective_date=target,
                calculated_at=calculated_iso,
                input_factors=dependencies,
            )
        )

    outputs = [*track_factors, *stock_curves, *track_curves]
    output_ids = sorted(str(row["factor_value_id"]) for row in outputs)
    upstream_refs = sorted(
        {
            (
                str(ref["as_of_trade_date"]),
                str(ref["factor_value_id"]),
            )
            for row in outputs
            for ref in (row.get("input_factor_refs") or [])
        }
    )
    observation_ids = sorted(
        {
            str(observation_id)
            for row in outputs
            for observation_id in row.get("input_observation_ids") or []
        }
    )
    input_digest = canonical_digest(
        {
            "upstream_factor_refs": upstream_refs,
            "membership_observation_ids": observation_ids,
            "parameters": _parameter_payload(parameters),
            "eligibility_version": ELIGIBILITY_VERSION,
        }
    )
    universe_entities = sorted(
        {
            (str(row["entity_type"]), str(row["entity_id"]))
            for row in current_base
        }
    )
    manifest: Dict[str, Any] = {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": "",
        "mode": mode,
        "as_of_trade_date": target,
        "universe_id": f"curve_universe_{canonical_digest(universe_entities)[:16]}",
        "feature_set_version": FEATURE_SET_VERSION,
        "group_version": NOT_EXECUTED,
        "select_version": NOT_EXECUTED,
        "forecast_version": NOT_EXECUTED,
        "input_digest": input_digest,
        "generated_at": calculated_iso,
        "notes": [
            "strictly causal session-indexed curves; no future rows",
            "rolling median + Theil-Sen slope + causal residual MAD",
            "turning/change/anomaly thresholds are candidate detectors, not effective labels",
            "non-native historical backfills are excluded from live curve history",
            "curve lineage uses previous-session curve + current factor when available",
            "curve outputs are one vector per stock/track to avoid repeated row metadata",
            (
                "track aggregates require at least "
                f"{parameters.minimum_track_members} current members"
            ),
            "group/select/forecast were not executed",
        ],
        "stage": "causal_curve_refresh",
        "observation_count": 0,
        "factor_value_count": len(outputs),
        "observation_digest": canonical_digest([]),
        "factor_value_digest": canonical_digest(output_ids),
        "upstream_factor_ref_count": len(upstream_refs),
        "upstream_factor_ref_digest": canonical_digest(upstream_refs),
        "membership_observation_count": len(observation_ids),
        "membership_observation_digest": canonical_digest(observation_ids),
        "curve_parameters": _parameter_payload(parameters),
        "eligibility_version": ELIGIBILITY_VERSION,
    }
    manifest["run_id"] = make_run_id(manifest)
    summary = {
        "as_of_trade_date": target,
        "eligible_base_rows": len(base),
        "current_stock_factor_series": len(current_base),
        "track_aggregates": len(track_factors),
        "stock_curves": len(stock_curves),
        "track_curves": len(track_curves),
        "stock_curve_series": stock_curve_series_count,
        "track_aggregate_series": track_aggregate_series_count,
        "track_curve_series": track_curve_series_count,
        "outputs": len(outputs),
        "session_count": len(session_dates),
        "candidate_hits": sum(
            len((row.get("value") or {}).get("candidate_events") or [])
            for row in [*stock_curves, *track_curves]
        ),
        "detector_status": "candidate_not_validated",
    }
    return manifest, outputs, summary
