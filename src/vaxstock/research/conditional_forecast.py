# -*- coding: utf-8 -*-
"""Conditional distribution forecast over the MR6 selected group spread.

This layer forecasts the algorithm-level, direction-adjusted spread that was
actually evaluated out of sample.  It does not invent a stock-level price
target and does not translate the result into a portfolio action.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from vaxstock.research.contextual_group import GROUP_VERSION
from vaxstock.research.contracts import (
    FORECAST_AUDIT_SCHEMA_VERSION,
    FORECAST_SCHEMA_VERSION,
    ContractError,
    canonical_digest,
    validate_forecast_audit,
    validate_forecast_output,
    validate_selection_audit,
)


FORECAST_VERSION = "conditional_group_spread_v1"
FORECAST_STRATEGY = "walk_forward_selected_group_spread"
FORECAST_TARGET = "selected_group_spread"
PRIMARY_BENCHMARK = "000001.SH"


def _finite_values(values: Iterable[Any], field: str) -> List[float]:
    result = []
    for value in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ContractError(f"{field} must contain finite numbers")
        result.append(float(value))
    if not result:
        raise ContractError(f"{field} cannot be empty")
    return result


def _quantile(values: Sequence[float], probability: float) -> float:
    """Deterministic linear-interpolation empirical quantile."""

    if not 0 <= probability <= 1:
        raise ContractError("quantile probability must be within [0, 1]")
    ordered = sorted(_finite_values(values, "quantile values"))
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _abstain_forecast(
    *,
    selection_audit: Mapping[str, Any],
    horizon: int,
    reason: str,
    selection: Mapping[str, Any],
) -> Dict[str, Any]:
    digest = canonical_digest({
        "selection_input_digest": selection_audit["input_digest"],
        "horizon_sessions": horizon,
        "selection_policy_digest": selection.get("policy_digest"),
        "forecast_version": FORECAST_VERSION,
        "status": "abstain",
        "reason": reason,
    })
    row = {
        "schema_version": FORECAST_SCHEMA_VERSION,
        "status": "abstain",
        "as_of_trade_date": str(selection_audit["as_of_trade_date"]),
        "target": FORECAST_TARGET,
        "strategy": FORECAST_STRATEGY,
        "horizon": f"T+{horizon}_sessions",
        "direction": None,
        "expected_excess_return": None,
        "confidence": None,
        "primary_benchmark": PRIMARY_BENCHMARK,
        "secondary_benchmark": None,
        "group_version": GROUP_VERSION,
        "select_version": str(selection_audit["select_version"]),
        "forecast_version": FORECAST_VERSION,
        "feature_set_version": GROUP_VERSION,
        "input_digest": digest,
        "selection_policy_digest": selection.get("policy_digest"),
        "generated_at": str(selection_audit["decision_at"]),
        "abstain_reason": reason,
        "distribution": None,
        "current_candidates": [],
        "evidence_label": "insufficient_forecast_evidence",
        "production_eligible": False,
    }
    validate_forecast_output(row)
    return row


def _available_forecast(
    *,
    selection_audit: Mapping[str, Any],
    horizon: int,
    selection: Mapping[str, Any],
) -> Dict[str, Any]:
    folds = selection.get("folds")
    if not isinstance(folds, list):
        raise ContractError("shadow selection folds must be a list")
    if any(not isinstance(fold, Mapping) for fold in folds):
        raise ContractError("shadow selection folds contain an invalid entry")
    values = _finite_values(
        (fold.get("strategy_oos_spread") for fold in folds),
        "strategy_oos_spread",
    )
    declared_oos = selection.get("oos_independent_dates")
    if (
        isinstance(declared_oos, bool)
        or not isinstance(declared_oos, int)
        or declared_oos != len(values)
    ):
        raise ContractError("shadow selection OOS sample count mismatch")
    minimum_oos = int((selection.get("policy") or {}).get("min_oos_dates") or 0)
    if len(values) < minimum_oos or minimum_oos <= 0:
        raise ContractError("shadow selection OOS sample is below policy")
    current_candidates = selection.get("current_candidates")
    if not isinstance(current_candidates, list) or not current_candidates:
        raise ContractError("shadow selection has no current candidates")

    median = _quantile(values, 0.5)
    if math.isclose(median, 0.0, rel_tol=0.0, abs_tol=1e-15):
        return _abstain_forecast(
            selection_audit=selection_audit,
            horizon=horizon,
            reason="zero_oos_median",
            selection=selection,
        )
    direction = "positive_spread" if median > 0 else "negative_spread"
    sign_consistency = (
        sum(value > 0 for value in values) / len(values)
        if median > 0
        else sum(value < 0 for value in values) / len(values)
    )
    distribution = {
        "independent_oos_dates": len(values),
        "mean": statistics.fmean(values),
        "q10": _quantile(values, 0.10),
        "q25": _quantile(values, 0.25),
        "median": median,
        "q75": _quantile(values, 0.75),
        "q90": _quantile(values, 0.90),
        "positive_rate": sum(value > 0 for value in values) / len(values),
        "empirical_sign_consistency": sign_consistency,
        "unit": "decimal_excess_spread",
        "inference_status": (
            "empirical_oos_distribution; no parametric confidence claim"
        ),
    }
    candidate_identity = [
        {
            "candidate_id": str(candidate.get("candidate_id") or ""),
            "series_id": str(candidate.get("series_id") or ""),
            "axis": str(candidate.get("axis") or ""),
            "direction": candidate.get("direction"),
            "training_independent_dates": (
                (candidate.get("training") or {}).get("independent_dates")
            ),
        }
        for candidate in current_candidates
        if isinstance(candidate, Mapping)
    ]
    if len(candidate_identity) != len(current_candidates) or any(
        not candidate["candidate_id"]
        or not candidate["series_id"]
        or not candidate["axis"]
        or isinstance(candidate["direction"], bool)
        or candidate["direction"] not in {-1, 1}
        or isinstance(candidate["training_independent_dates"], bool)
        or not isinstance(candidate["training_independent_dates"], int)
        or candidate["training_independent_dates"] <= 0
        for candidate in candidate_identity
    ):
        raise ContractError("current candidate identity is incomplete")
    digest = canonical_digest({
        "selection_input_digest": selection_audit["input_digest"],
        "horizon_sessions": horizon,
        "selection_policy_digest": selection.get("policy_digest"),
        "forecast_version": FORECAST_VERSION,
        "oos_distribution": distribution,
        "current_candidates": candidate_identity,
    })
    row = {
        "schema_version": FORECAST_SCHEMA_VERSION,
        "status": "available",
        "as_of_trade_date": str(selection_audit["as_of_trade_date"]),
        "target": FORECAST_TARGET,
        "strategy": FORECAST_STRATEGY,
        "horizon": f"T+{horizon}_sessions",
        "direction": direction,
        "expected_excess_return": median,
        "confidence": sign_consistency,
        "primary_benchmark": PRIMARY_BENCHMARK,
        "secondary_benchmark": None,
        "group_version": GROUP_VERSION,
        "select_version": str(selection_audit["select_version"]),
        "forecast_version": FORECAST_VERSION,
        "feature_set_version": GROUP_VERSION,
        "input_digest": digest,
        "selection_policy_digest": selection.get("policy_digest"),
        "generated_at": str(selection_audit["decision_at"]),
        "abstain_reason": None,
        "distribution": distribution,
        "current_candidates": candidate_identity,
        "confidence_definition": (
            "fraction of independent OOS folds sharing the median direction"
        ),
        "conditioning_scope": (
            "selected group-state axes; current market regime recorded in "
            "group inputs but not separately estimated"
        ),
        "evidence_label": "shadow_conditional_distribution",
        "production_eligible": False,
    }
    validate_forecast_output(row)
    return row


def build_forecast_audit(
    selection_audit: Mapping[str, Any],
) -> Dict[str, Any]:
    """Transform one immutable selection audit into forecast distributions."""

    validate_selection_audit(selection_audit)
    forecasts = {}
    horizons = selection_audit["horizons"]
    for raw_horizon in sorted(horizons, key=lambda value: int(value)):
        horizon = int(raw_horizon)
        result = horizons[raw_horizon]
        selection = result["selection"]
        if selection["status"] != "shadow_candidate":
            reason = (
                "select_abstain:"
                f"{selection.get('abstain_reason') or 'unspecified'}"
            )
            forecast = _abstain_forecast(
                selection_audit=selection_audit,
                horizon=horizon,
                reason=reason,
                selection=selection,
            )
        else:
            forecast = _available_forecast(
                selection_audit=selection_audit,
                horizon=horizon,
                selection=selection,
            )
        forecasts[str(horizon)] = forecast

    status_counts = Counter(
        forecast["status"] for forecast in forecasts.values()
    )
    digest = canonical_digest({
        "selection_input_digest": selection_audit["input_digest"],
        "select_version": selection_audit["select_version"],
        "forecast_version": FORECAST_VERSION,
        "forecast_input_digests": sorted(
            forecast["input_digest"] for forecast in forecasts.values()
        ),
    })
    audit = {
        "schema_version": FORECAST_AUDIT_SCHEMA_VERSION,
        "as_of_trade_date": str(selection_audit["as_of_trade_date"]),
        "decision_at": str(selection_audit["decision_at"]),
        "select_version": str(selection_audit["select_version"]),
        "forecast_version": FORECAST_VERSION,
        "selection_input_digest": str(selection_audit["input_digest"]),
        "input_digest": digest,
        "forecasts": forecasts,
        "status_counts": dict(sorted(status_counts.items())),
        "production_eligible": False,
        "promotion_status": "manual_review_required",
        "scope": (
            "algorithm-level selected group spread; not stock price target "
            "and not portfolio action"
        ),
    }
    validate_forecast_audit(audit)
    return audit
