# -*- coding: utf-8 -*-
"""Point-in-time contracts for the v2 research pipeline.

This module intentionally depends on the Python standard library only.  It
defines the stable boundary shared by future factor ingestion, grouping,
selection, forecasting, replay, and report code.  It does not perform I/O,
load market-data clients, or choose a trading action.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any, Dict, List, Literal, Mapping, NotRequired, Optional, TypedDict


OBSERVATION_SCHEMA_VERSION = 1
FACTOR_VALUE_SCHEMA_VERSION = 1
FORECAST_SCHEMA_VERSION = 1
RUN_MANIFEST_SCHEMA_VERSION = 1
GROUP_OUTCOME_SCHEMA_VERSION = 1
SELECTION_AUDIT_SCHEMA_VERSION = 1
FORECAST_AUDIT_SCHEMA_VERSION = 1
FORECAST_RESULT_SCHEMA_VERSION = 1
FORECAST_CALIBRATION_SCHEMA_VERSION = 1


class ContractError(ValueError):
    """Raised when data cannot safely cross a research pipeline boundary."""


ObservationQuality = Literal["observed", "revised", "stale", "missing"]
FactorQuality = Literal["calculated", "stale", "missing"]
ForecastStatus = Literal["available", "abstain"]


class AtomicObservation(TypedDict):
    """One append-only, point-in-time fact.

    ``effective_date`` says which economic/reporting period the value belongs
    to. ``available_at`` says when a decision process was first allowed to use
    it.  The two fields must never be substituted for each other.
    """

    schema_version: int
    observation_id: str
    entity_type: str
    entity_id: str
    dimension: str
    field: str
    value: Any
    effective_date: str
    available_at: str
    retrieved_at: str
    source: str
    source_ref: str
    revision_id: str
    quality: ObservationQuality


class FactorValue(TypedDict):
    """One immutable factor value calculated from point-in-time observations."""

    schema_version: int
    factor_value_id: str
    entity_type: str
    entity_id: str
    dimension: str
    factor_id: str
    factor_version: str
    value: Any
    as_of_trade_date: str
    effective_date: str
    available_at: str
    calculated_at: str
    input_observation_ids: List[str]
    input_factor_refs: NotRequired[List["FactorInputRef"]]
    input_digest: str
    quality: FactorQuality


class FactorInputRef(TypedDict):
    """A compact, partition-addressable dependency on an upstream factor."""

    factor_value_id: str
    as_of_trade_date: str


class ForecastOutput(TypedDict):
    """Auditable output of ``forecast(select(group(features)))``."""

    schema_version: int
    status: ForecastStatus
    as_of_trade_date: str
    target: str
    strategy: str
    horizon: str
    direction: Optional[str]
    expected_excess_return: Optional[float]
    confidence: Optional[float]
    primary_benchmark: str
    secondary_benchmark: Optional[str]
    group_version: str
    select_version: str
    forecast_version: str
    feature_set_version: str
    input_digest: str
    generated_at: str
    abstain_reason: Optional[str]


class RunManifest(TypedDict):
    """Immutable identity and input boundary for one research/replay run."""

    schema_version: int
    run_id: str
    mode: Literal["live", "replay", "backtest"]
    as_of_trade_date: str
    universe_id: str
    feature_set_version: str
    group_version: str
    select_version: str
    forecast_version: str
    input_digest: str
    generated_at: str
    notes: List[str]


class GroupOutcomeSample(TypedDict):
    """One matured horizon outcome joined to one frozen group assignment."""

    schema_version: int
    outcome_id: str
    as_of_trade_date: str
    code: str
    group_factor_value_id: str
    group_factor_version: str
    group_version: str
    group_available_at: str
    group_calculated_at: str
    horizon_sessions: int
    outcome_trade_date: str
    outcome_available_at: str
    ret: float
    benchmark_ret: float
    excess_ret: float
    benchmark_code: str
    benchmark_kind: str
    source: str
    source_ref: str
    independent_session_id: str
    input_digest: str


class SelectionAudit(TypedDict):
    """One immutable point-in-time walk-forward selection audit."""

    schema_version: int
    as_of_trade_date: str
    decision_at: str
    select_version: str
    input_digest: str
    horizons: Dict[str, Any]
    status_counts: Dict[str, int]
    production_eligible: bool
    promotion_status: str


class ForecastAudit(TypedDict):
    """One immutable conditional-distribution forecast audit."""

    schema_version: int
    as_of_trade_date: str
    decision_at: str
    select_version: str
    forecast_version: str
    selection_input_digest: str
    input_digest: str
    forecasts: Dict[str, Any]
    status_counts: Dict[str, int]
    production_eligible: bool
    promotion_status: str


class ForecastResult(TypedDict):
    """One matured day-by-horizon result for a frozen forecast."""

    schema_version: int
    result_id: str
    as_of_trade_date: str
    horizon_sessions: int
    outcome_trade_date: str
    outcome_available_at: str
    evaluated_at: str
    select_version: str
    forecast_version: str
    evaluator_version: str
    forecast_input_digest: str
    forecast_audit_input_digest: str
    selection_input_digest: str
    target: str
    strategy: str
    predicted_direction: str
    expected_spread: float
    confidence: float
    forecast_distribution: Dict[str, Any]
    actual_selected_group_spread: float
    direction_hit: bool
    signed_error: float
    absolute_error: float
    within_q25_q75: bool
    within_q10_q90: bool
    candidate_results: List[Dict[str, Any]]
    group_factor_value_ids: List[str]
    group_outcome_ids: List[str]
    cross_section_audit: Dict[str, Any]
    input_digest: str
    production_eligible: bool
    promotion_status: str


class ForecastCalibrationAudit(TypedDict):
    """Immutable per-horizon calibration snapshot."""

    schema_version: int
    as_of_trade_date: str
    decision_at: str
    select_version: str
    forecast_version: str
    evaluator_version: str
    calibration_version: str
    minimum_evaluated_dates: int
    status: str
    horizons: Dict[str, Any]
    forecast_audit_input_digests: List[str]
    result_ids: List[str]
    input_digest: str
    production_eligible: bool
    promotion_status: str
    scope: str


def canonical_digest(value: Any) -> str:
    """Return a deterministic SHA-256 digest for JSON-compatible input."""

    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContractError(f"input is not canonical JSON: {exc}") from exc
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def factor_input_digest(
    observation_ids: List[str],
    factor_refs: Optional[List[Mapping[str, Any]]] = None,
) -> str:
    """Digest direct observations and optional upstream-factor references.

    The observations-only representation intentionally preserves the v1
    digest used by already stored base factors. Derived factors use the
    structured representation so their full dependency DAG is immutable.
    """

    observations = sorted(str(value) for value in observation_ids)
    refs = sorted(
        (
            {
                "factor_value_id": str(ref.get("factor_value_id") or ""),
                "as_of_trade_date": str(ref.get("as_of_trade_date") or ""),
            }
            for ref in (factor_refs or [])
        ),
        key=lambda ref: (ref["as_of_trade_date"], ref["factor_value_id"]),
    )
    if not refs:
        return canonical_digest(observations)
    return canonical_digest(
        {
            "input_observation_ids": observations,
            "input_factor_refs": refs,
        }
    )


def make_observation_id(record: Mapping[str, Any]) -> str:
    """Build the immutable identity of one source fact revision."""

    identity = {
        "entity_type": record.get("entity_type"),
        "entity_id": record.get("entity_id"),
        "dimension": record.get("dimension"),
        "field": record.get("field"),
        "effective_date": record.get("effective_date"),
        "available_at": record.get("available_at"),
        "source": record.get("source"),
        "source_ref": record.get("source_ref"),
        "revision_id": record.get("revision_id"),
    }
    return f"obs_{canonical_digest(identity)}"


def make_factor_value_id(record: Mapping[str, Any]) -> str:
    """Build the identity of one factor version on one frozen input set."""

    identity = {
        "entity_type": record.get("entity_type"),
        "entity_id": record.get("entity_id"),
        "dimension": record.get("dimension"),
        "factor_id": record.get("factor_id"),
        "factor_version": record.get("factor_version"),
        "as_of_trade_date": record.get("as_of_trade_date"),
        "available_at": record.get("available_at"),
        "input_digest": record.get("input_digest"),
    }
    return f"factor_{canonical_digest(identity)}"


def make_run_id(record: Mapping[str, Any]) -> str:
    """Build a deterministic run identity independent of wall-clock retries."""

    identity = {
        "mode": record.get("mode"),
        "as_of_trade_date": record.get("as_of_trade_date"),
        "universe_id": record.get("universe_id"),
        "feature_set_version": record.get("feature_set_version"),
        "group_version": record.get("group_version"),
        "select_version": record.get("select_version"),
        "forecast_version": record.get("forecast_version"),
        "input_digest": record.get("input_digest"),
    }
    return f"run_{canonical_digest(identity)}"


def make_group_outcome_id(record: Mapping[str, Any]) -> str:
    """Build the immutable identity of one group/horizon outcome."""

    identity = {
        "as_of_trade_date": record.get("as_of_trade_date"),
        "code": record.get("code"),
        "group_factor_value_id": record.get("group_factor_value_id"),
        "horizon_sessions": record.get("horizon_sessions"),
        "source": record.get("source"),
    }
    return f"outcome_{canonical_digest(identity)}"


def _require_text(record: Mapping[str, Any], field: str) -> str:
    value = str(record.get(field) or "").strip()
    if not value:
        raise ContractError(f"{field} is required")
    return value


def _parse_trade_date(value: Any, field: str) -> str:
    text = str(value or "").strip()
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ContractError(f"{field} must be YYYYMMDD") from exc
    return text


def _parse_aware_timestamp(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include a timezone offset")
    return parsed


def validate_atomic_observation(record: Mapping[str, Any]) -> None:
    """Validate provenance, revision identity, and point-in-time timestamps."""

    if record.get("schema_version") != OBSERVATION_SCHEMA_VERSION:
        raise ContractError("unsupported observation schema_version")
    for field in (
        "observation_id",
        "entity_type",
        "entity_id",
        "dimension",
        "field",
        "effective_date",
        "source",
        "source_ref",
        "revision_id",
    ):
        _require_text(record, field)

    available_at = _parse_aware_timestamp(record.get("available_at"), "available_at")
    retrieved_at = _parse_aware_timestamp(record.get("retrieved_at"), "retrieved_at")
    if retrieved_at < available_at:
        raise ContractError("retrieved_at cannot precede available_at")

    quality = record.get("quality")
    if quality not in {"observed", "revised", "stale", "missing"}:
        raise ContractError("quality must be observed/revised/stale/missing")
    if quality == "missing" and record.get("value") is not None:
        raise ContractError("missing observations must have value=None")
    if record.get("observation_id") != make_observation_id(record):
        raise ContractError("observation_id does not match immutable identity")
    canonical_digest(record.get("value"))


def validate_factor_value(record: Mapping[str, Any]) -> None:
    """Validate factor identity, version, inputs, and point-in-time boundary."""

    if record.get("schema_version") != FACTOR_VALUE_SCHEMA_VERSION:
        raise ContractError("unsupported factor schema_version")
    for field in (
        "factor_value_id",
        "entity_type",
        "entity_id",
        "dimension",
        "factor_id",
        "factor_version",
        "effective_date",
        "input_digest",
    ):
        _require_text(record, field)
    _parse_trade_date(record.get("as_of_trade_date"), "as_of_trade_date")
    available_at = _parse_aware_timestamp(record.get("available_at"), "available_at")
    calculated_at = _parse_aware_timestamp(record.get("calculated_at"), "calculated_at")
    if calculated_at < available_at:
        raise ContractError("calculated_at cannot precede available_at")

    input_ids = record.get("input_observation_ids")
    if not isinstance(input_ids, list):
        raise ContractError("input_observation_ids must be a list")
    if any(not isinstance(value, str) or not value.strip() for value in input_ids):
        raise ContractError("input_observation_ids must contain non-empty strings")
    if len(set(input_ids)) != len(input_ids):
        raise ContractError("input_observation_ids must not contain duplicates")

    raw_factor_refs = record.get("input_factor_refs", [])
    if not isinstance(raw_factor_refs, list):
        raise ContractError("input_factor_refs must be a list")
    factor_refs: List[Dict[str, str]] = []
    for ref in raw_factor_refs:
        if not isinstance(ref, Mapping):
            raise ContractError("input_factor_refs entries must be objects")
        factor_value_id = str(ref.get("factor_value_id") or "").strip()
        if not factor_value_id:
            raise ContractError("input_factor_refs.factor_value_id is required")
        ref_date = _parse_trade_date(
            ref.get("as_of_trade_date"),
            "input_factor_refs.as_of_trade_date",
        )
        factor_refs.append(
            {
                "factor_value_id": factor_value_id,
                "as_of_trade_date": ref_date,
            }
        )
    factor_ref_keys = [
        (ref["as_of_trade_date"], ref["factor_value_id"]) for ref in factor_refs
    ]
    if len(set(factor_ref_keys)) != len(factor_ref_keys):
        raise ContractError("input_factor_refs must not contain duplicates")
    if not input_ids and not factor_refs:
        raise ContractError("a factor requires observation or upstream-factor inputs")
    if any(ref["factor_value_id"] == record.get("factor_value_id") for ref in factor_refs):
        raise ContractError("a factor cannot reference itself")

    expected_input_digest = factor_input_digest(input_ids, factor_refs)
    if record.get("input_digest") != expected_input_digest:
        raise ContractError("input_digest does not match factor inputs")

    quality = record.get("quality")
    if quality not in {"calculated", "stale", "missing"}:
        raise ContractError("factor quality must be calculated/stale/missing")
    if quality == "missing" and record.get("value") is not None:
        raise ContractError("missing factor values must have value=None")
    if quality != "missing" and record.get("value") is None:
        raise ContractError("non-missing factor values require a value")
    canonical_digest(record.get("value"))
    if record.get("factor_value_id") != make_factor_value_id(record):
        raise ContractError("factor_value_id does not match immutable identity")


def validate_run_manifest(record: Mapping[str, Any]) -> None:
    """Validate deterministic identity and frozen algorithm/input versions."""

    if record.get("schema_version") != RUN_MANIFEST_SCHEMA_VERSION:
        raise ContractError("unsupported run manifest schema_version")
    if record.get("mode") not in {"live", "replay", "backtest"}:
        raise ContractError("mode must be live/replay/backtest")
    _parse_trade_date(record.get("as_of_trade_date"), "as_of_trade_date")
    for field in (
        "run_id",
        "universe_id",
        "feature_set_version",
        "group_version",
        "select_version",
        "forecast_version",
        "input_digest",
    ):
        _require_text(record, field)
    _parse_aware_timestamp(record.get("generated_at"), "generated_at")
    notes = record.get("notes")
    if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
        raise ContractError("notes must be a list of strings")
    if record.get("run_id") != make_run_id(record):
        raise ContractError("run_id does not match immutable identity")


def assert_available_as_of(record: Mapping[str, Any], as_of: str) -> None:
    """Reject a fact that was not available at the simulated decision time."""

    validate_atomic_observation(record)
    available_at = _parse_aware_timestamp(record.get("available_at"), "available_at")
    decision_at = _parse_aware_timestamp(as_of, "as_of")
    if available_at > decision_at:
        raise ContractError("look-ahead detected: available_at is after as_of")


def assert_factor_available_as_of(record: Mapping[str, Any], as_of: str) -> None:
    """Reject a factor that had not been calculated and available by ``as_of``."""

    validate_factor_value(record)
    available_at = _parse_aware_timestamp(record.get("available_at"), "available_at")
    calculated_at = _parse_aware_timestamp(record.get("calculated_at"), "calculated_at")
    decision_at = _parse_aware_timestamp(as_of, "as_of")
    if available_at > decision_at or calculated_at > decision_at:
        raise ContractError("look-ahead detected: factor is after as_of")


def validate_forecast_output(record: Mapping[str, Any]) -> None:
    """Validate the minimum auditable forecast/abstention contract."""

    if record.get("schema_version") != FORECAST_SCHEMA_VERSION:
        raise ContractError("unsupported forecast schema_version")
    status = record.get("status")
    if status not in {"available", "abstain"}:
        raise ContractError("status must be available or abstain")
    _parse_trade_date(record.get("as_of_trade_date"), "as_of_trade_date")
    for field in (
        "target",
        "strategy",
        "horizon",
        "primary_benchmark",
        "group_version",
        "select_version",
        "forecast_version",
        "feature_set_version",
        "input_digest",
    ):
        _require_text(record, field)
    _parse_aware_timestamp(record.get("generated_at"), "generated_at")

    confidence = record.get("confidence")
    expected = record.get("expected_excess_return")
    if status == "abstain":
        _require_text(record, "abstain_reason")
        if record.get("direction") is not None:
            raise ContractError("abstain forecast cannot contain direction")
        if confidence is not None or expected is not None:
            raise ContractError("abstain forecast cannot contain numeric prediction")
        return

    if not record.get("direction"):
        raise ContractError("available forecast requires direction")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ContractError("available forecast requires numeric confidence")
    if not math.isfinite(float(confidence)) or not 0 <= float(confidence) <= 1:
        raise ContractError("confidence must be finite and within [0, 1]")
    if not isinstance(expected, (int, float)) or isinstance(expected, bool):
        raise ContractError("available forecast requires expected_excess_return")
    if not math.isfinite(float(expected)):
        raise ContractError("expected_excess_return must be finite")


def validate_group_outcome_sample(record: Mapping[str, Any]) -> None:
    """Validate one mature label without permitting a point-in-time shortcut."""

    if record.get("schema_version") != GROUP_OUTCOME_SCHEMA_VERSION:
        raise ContractError("unsupported group outcome schema_version")
    baseline = _parse_trade_date(
        record.get("as_of_trade_date"), "as_of_trade_date"
    )
    outcome_date = _parse_trade_date(
        record.get("outcome_trade_date"), "outcome_trade_date"
    )
    if outcome_date <= baseline:
        raise ContractError("outcome_trade_date must follow as_of_trade_date")
    for field in (
        "outcome_id",
        "code",
        "group_factor_value_id",
        "group_factor_version",
        "group_version",
        "benchmark_code",
        "benchmark_kind",
        "source",
        "source_ref",
        "independent_session_id",
        "input_digest",
    ):
        _require_text(record, field)
    if record.get("independent_session_id") != baseline:
        raise ContractError("independent_session_id must equal as_of_trade_date")
    group_available = _parse_aware_timestamp(
        record.get("group_available_at"), "group_available_at"
    )
    group_calculated = _parse_aware_timestamp(
        record.get("group_calculated_at"), "group_calculated_at"
    )
    outcome_available = _parse_aware_timestamp(
        record.get("outcome_available_at"), "outcome_available_at"
    )
    if group_calculated < group_available:
        raise ContractError("group_calculated_at cannot precede group_available_at")
    if outcome_available < group_calculated:
        raise ContractError("outcome cannot be available before its group assignment")

    horizon = record.get("horizon_sessions")
    if (
        isinstance(horizon, bool)
        or not isinstance(horizon, int)
        or horizon <= 0
    ):
        raise ContractError("horizon_sessions must be a positive integer")
    numeric = {}
    for field in ("ret", "benchmark_ret", "excess_ret"):
        value = record.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ContractError(f"{field} must be a finite number")
        numeric[field] = float(value)
    if not math.isclose(
        numeric["excess_ret"],
        numeric["ret"] - numeric["benchmark_ret"],
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ContractError("excess_ret must equal ret - benchmark_ret")
    expected_digest = canonical_digest({
        "group_factor_value_id": record.get("group_factor_value_id"),
        "horizon_sessions": horizon,
        "outcome_trade_date": outcome_date,
        "outcome_available_at": record.get("outcome_available_at"),
        "ret": numeric["ret"],
        "benchmark_ret": numeric["benchmark_ret"],
        "excess_ret": numeric["excess_ret"],
        "benchmark_code": record.get("benchmark_code"),
        "source": record.get("source"),
    })
    if record.get("input_digest") != expected_digest:
        raise ContractError("group outcome input_digest does not match inputs")
    if record.get("outcome_id") != make_group_outcome_id(record):
        raise ContractError("outcome_id does not match immutable identity")


def validate_selection_audit(record: Mapping[str, Any]) -> None:
    """Reject a selection artifact that weakens the research-only boundary."""

    if record.get("schema_version") != SELECTION_AUDIT_SCHEMA_VERSION:
        raise ContractError("unsupported selection audit schema_version")
    _parse_trade_date(record.get("as_of_trade_date"), "as_of_trade_date")
    _parse_aware_timestamp(record.get("decision_at"), "decision_at")
    for field in ("select_version", "input_digest", "promotion_status"):
        _require_text(record, field)
    if record.get("production_eligible") is not False:
        raise ContractError("selection audit must not be production eligible")
    if record.get("promotion_status") != "manual_review_required":
        raise ContractError("selection promotion requires manual review")

    horizons = record.get("horizons")
    if not isinstance(horizons, Mapping) or not horizons:
        raise ContractError("selection horizons must be a non-empty object")
    counts: Dict[str, int] = {}
    for raw_horizon, raw_result in horizons.items():
        try:
            horizon = int(str(raw_horizon))
        except (TypeError, ValueError) as exc:
            raise ContractError("selection horizon key must be positive") from exc
        if horizon <= 0 or not isinstance(raw_result, Mapping):
            raise ContractError("selection horizon entry is invalid")
        build = raw_result.get("build")
        selection = raw_result.get("selection")
        if not isinstance(build, Mapping) or not isinstance(selection, Mapping):
            raise ContractError("selection horizon requires build and selection")
        if build.get("horizon_sessions") != horizon:
            raise ContractError("selection build horizon mismatch")
        if selection.get("horizon_sessions") != horizon:
            raise ContractError("selection result horizon mismatch")
        if selection.get("select_version") != record.get("select_version"):
            raise ContractError("selection version mismatch")
        if selection.get("production_eligible") is not False:
            raise ContractError("selection result must not be production eligible")
        if selection.get("promotion_status") != "manual_review_required":
            raise ContractError("selection result requires manual review")
        status = selection.get("status")
        if status not in {"abstain", "shadow_candidate"}:
            raise ContractError("unsupported selection status")
        if status == "abstain" and not str(
            selection.get("abstain_reason") or ""
        ).strip():
            raise ContractError("abstain selection requires a reason")
        if status == "shadow_candidate":
            policy = selection.get("policy")
            if not isinstance(policy, Mapping):
                raise ContractError("shadow candidate requires policy")
            minimum_oos = policy.get("min_oos_dates")
            if (
                isinstance(minimum_oos, bool)
                or not isinstance(minimum_oos, int)
                or minimum_oos <= 0
            ):
                raise ContractError(
                    "shadow candidate requires positive min_oos_dates"
                )
            if int(selection.get("oos_independent_dates") or 0) < minimum_oos:
                raise ContractError(
                    "shadow candidate has insufficient independent OOS dates"
                )
            current_candidates = selection.get("current_candidates")
            if (
                not isinstance(current_candidates, list)
                or not current_candidates
            ):
                raise ContractError(
                    "shadow candidate requires current selected candidates"
                )
        counts[str(status)] = counts.get(str(status), 0) + 1
    if record.get("status_counts") != dict(sorted(counts.items())):
        raise ContractError("selection status_counts mismatch")


def validate_forecast_audit(record: Mapping[str, Any]) -> None:
    """Validate conditional forecasts without allowing production promotion."""

    if record.get("schema_version") != FORECAST_AUDIT_SCHEMA_VERSION:
        raise ContractError("unsupported forecast audit schema_version")
    as_of_trade_date = _parse_trade_date(
        record.get("as_of_trade_date"), "as_of_trade_date"
    )
    decision_at = _parse_aware_timestamp(
        record.get("decision_at"), "decision_at"
    )
    for field in (
        "select_version",
        "forecast_version",
        "selection_input_digest",
        "input_digest",
        "promotion_status",
    ):
        _require_text(record, field)
    if record.get("production_eligible") is not False:
        raise ContractError("forecast audit must not be production eligible")
    if record.get("promotion_status") != "manual_review_required":
        raise ContractError("forecast promotion requires manual review")

    forecasts = record.get("forecasts")
    if not isinstance(forecasts, Mapping) or not forecasts:
        raise ContractError("forecasts must be a non-empty object")
    counts: Dict[str, int] = {}
    for raw_horizon, raw_forecast in forecasts.items():
        try:
            horizon = int(str(raw_horizon))
        except (TypeError, ValueError) as exc:
            raise ContractError("forecast horizon key must be positive") from exc
        if horizon <= 0 or not isinstance(raw_forecast, Mapping):
            raise ContractError("forecast horizon entry is invalid")
        validate_forecast_output(raw_forecast)
        if raw_forecast.get("as_of_trade_date") != as_of_trade_date:
            raise ContractError("forecast as_of_trade_date mismatch")
        if raw_forecast.get("select_version") != record.get("select_version"):
            raise ContractError("forecast select_version mismatch")
        if raw_forecast.get("forecast_version") != record.get(
            "forecast_version"
        ):
            raise ContractError("forecast version mismatch")
        if _parse_aware_timestamp(
            raw_forecast.get("generated_at"), "generated_at"
        ) != decision_at:
            raise ContractError("forecast generated_at must equal decision_at")
        if raw_forecast.get("target") != "selected_group_spread":
            raise ContractError("unsupported forecast target")
        if raw_forecast.get("primary_benchmark") != "000001.SH":
            raise ContractError("unsupported forecast benchmark")
        if raw_forecast.get("horizon") != f"T+{horizon}_sessions":
            raise ContractError("forecast horizon label mismatch")
        _require_text(raw_forecast, "selection_policy_digest")
        if raw_forecast.get("production_eligible") is not False:
            raise ContractError(
                "individual forecast must not be production eligible"
            )
        status = str(raw_forecast.get("status"))
        if status == "available":
            distribution = raw_forecast.get("distribution")
            candidates = raw_forecast.get("current_candidates")
            if not isinstance(distribution, Mapping):
                raise ContractError(
                    "available forecast requires conditional distribution"
                )
            if not isinstance(candidates, list) or not candidates:
                raise ContractError(
                    "available forecast requires current candidates"
                )
            sample_n = distribution.get("independent_oos_dates")
            if (
                isinstance(sample_n, bool)
                or not isinstance(sample_n, int)
                or sample_n <= 0
            ):
                raise ContractError(
                    "forecast distribution requires independent OOS dates"
                )
            distribution_values = [
                distribution.get(field)
                for field in (
                    "mean",
                    "q10",
                    "q25",
                    "median",
                    "q75",
                    "q90",
                    "positive_rate",
                    "empirical_sign_consistency",
                )
            ]
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in distribution_values
            ):
                raise ContractError(
                    "forecast distribution values must be finite"
                )
            quantiles = [
                distribution.get(field)
                for field in ("q10", "q25", "median", "q75", "q90")
            ]
            if not (
                float(quantiles[0])
                <= float(quantiles[1])
                <= float(quantiles[2])
                <= float(quantiles[3])
                <= float(quantiles[4])
            ):
                raise ContractError("forecast quantiles must be ordered")
            for field in ("positive_rate", "empirical_sign_consistency"):
                value = float(distribution[field])
                if not 0 <= value <= 1:
                    raise ContractError(
                        f"forecast {field} must be within [0, 1]"
                    )
            median = float(distribution["median"])
            expected_direction = (
                "positive_spread" if median > 0 else "negative_spread"
            )
            if median == 0 or raw_forecast.get("direction") != expected_direction:
                raise ContractError(
                    "forecast direction must match non-zero OOS median"
                )
            if distribution.get("unit") != "decimal_excess_spread":
                raise ContractError("unsupported forecast distribution unit")
            if not math.isclose(
                float(raw_forecast["expected_excess_return"]),
                float(distribution["median"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ContractError(
                    "forecast expectation must equal OOS distribution median"
                )
            if not math.isclose(
                float(raw_forecast["confidence"]),
                float(distribution.get("empirical_sign_consistency")),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ContractError(
                    "forecast confidence must equal empirical sign consistency"
                )
            for candidate in candidates:
                if not isinstance(candidate, Mapping):
                    raise ContractError(
                        "forecast candidate identity is invalid"
                    )
                for field in ("candidate_id", "series_id", "axis"):
                    _require_text(candidate, field)
                condition = candidate.get("condition", {})
                if not isinstance(condition, Mapping):
                    raise ContractError(
                        "forecast candidate condition must be an object"
                    )
                canonical_digest(dict(condition))
                if (
                    isinstance(candidate.get("direction"), bool)
                    or candidate.get("direction") not in {-1, 1}
                ):
                    raise ContractError(
                        "forecast candidate direction must be -1 or 1"
                    )
                training_n = candidate.get("training_independent_dates")
                if (
                    isinstance(training_n, bool)
                    or not isinstance(training_n, int)
                    or training_n <= 0
                ):
                    raise ContractError(
                        "forecast candidate training dates must be positive"
                    )
        else:
            if raw_forecast.get("distribution") is not None:
                raise ContractError(
                    "abstain forecast cannot contain a distribution"
                )
            if raw_forecast.get("current_candidates"):
                raise ContractError(
                    "abstain forecast cannot expose selected candidates"
                )
        counts[status] = counts.get(status, 0) + 1
    if record.get("status_counts") != dict(sorted(counts.items())):
        raise ContractError("forecast status_counts mismatch")
    expected_digest = canonical_digest({
        "selection_input_digest": record.get("selection_input_digest"),
        "select_version": record.get("select_version"),
        "forecast_version": record.get("forecast_version"),
        "forecast_input_digests": sorted(
            str(forecast.get("input_digest"))
            for forecast in forecasts.values()
        ),
    })
    if record.get("input_digest") != expected_digest:
        raise ContractError("forecast audit input_digest mismatch")


def make_forecast_result_id(record: Mapping[str, Any]) -> str:
    """Return the immutable identity of one forecast-date/horizon result."""

    return canonical_digest({
        "as_of_trade_date": record.get("as_of_trade_date"),
        "horizon_sessions": record.get("horizon_sessions"),
        "select_version": record.get("select_version"),
        "forecast_version": record.get("forecast_version"),
        "evaluator_version": record.get("evaluator_version"),
        "forecast_input_digest": record.get("forecast_input_digest"),
    })


def validate_forecast_result(record: Mapping[str, Any]) -> None:
    """Validate a matured selected-group-spread result."""

    if record.get("schema_version") != FORECAST_RESULT_SCHEMA_VERSION:
        raise ContractError("unsupported forecast result schema_version")
    baseline = _parse_trade_date(
        record.get("as_of_trade_date"), "as_of_trade_date"
    )
    outcome_date = _parse_trade_date(
        record.get("outcome_trade_date"), "outcome_trade_date"
    )
    if outcome_date <= baseline:
        raise ContractError("forecast outcome date must follow baseline")
    outcome_available = _parse_aware_timestamp(
        record.get("outcome_available_at"), "outcome_available_at"
    )
    evaluated_at = _parse_aware_timestamp(
        record.get("evaluated_at"), "evaluated_at"
    )
    if evaluated_at != outcome_available:
        raise ContractError(
            "forecast evaluated_at must freeze first complete availability"
        )
    for field in (
        "result_id",
        "select_version",
        "forecast_version",
        "evaluator_version",
        "forecast_input_digest",
        "forecast_audit_input_digest",
        "selection_input_digest",
        "target",
        "strategy",
        "predicted_direction",
        "input_digest",
        "promotion_status",
    ):
        _require_text(record, field)
    if record.get("target") != "selected_group_spread":
        raise ContractError("unsupported forecast result target")
    if record.get("strategy") != "walk_forward_selected_group_spread":
        raise ContractError("unsupported forecast result strategy")
    horizon = record.get("horizon_sessions")
    if (
        isinstance(horizon, bool)
        or not isinstance(horizon, int)
        or horizon <= 0
    ):
        raise ContractError("forecast result horizon must be positive")
    if record.get("predicted_direction") not in {
        "positive_spread",
        "negative_spread",
    }:
        raise ContractError("unsupported forecast result direction")
    numeric_fields = (
        "expected_spread",
        "confidence",
        "actual_selected_group_spread",
        "signed_error",
        "absolute_error",
    )
    for field in numeric_fields:
        value = record.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ContractError(f"{field} must be a finite number")
    confidence = float(record["confidence"])
    if not 0 <= confidence <= 1:
        raise ContractError("forecast result confidence must be within [0, 1]")
    distribution = record.get("forecast_distribution")
    if not isinstance(distribution, Mapping):
        raise ContractError(
            "forecast result requires frozen forecast distribution"
        )
    distribution_fields = (
        "q10",
        "q25",
        "median",
        "q75",
        "q90",
    )
    distribution_values = [
        distribution.get(field) for field in distribution_fields
    ]
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in distribution_values
    ):
        raise ContractError(
            "forecast result distribution quantiles must be finite"
        )
    if not (
        float(distribution_values[0])
        <= float(distribution_values[1])
        <= float(distribution_values[2])
        <= float(distribution_values[3])
        <= float(distribution_values[4])
    ):
        raise ContractError(
            "forecast result distribution quantiles must be ordered"
        )
    distribution_n = distribution.get("independent_oos_dates")
    if (
        isinstance(distribution_n, bool)
        or not isinstance(distribution_n, int)
        or distribution_n <= 0
    ):
        raise ContractError(
            "forecast result distribution requires independent OOS dates"
        )
    if distribution.get("unit") != "decimal_excess_spread":
        raise ContractError("unsupported forecast result distribution unit")
    actual = float(record["actual_selected_group_spread"])
    expected = float(record["expected_spread"])
    if not math.isclose(
        expected,
        float(distribution["median"]),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ContractError(
            "forecast result expectation must equal frozen median"
        )
    signed_error = actual - expected
    if not math.isclose(
        float(record["signed_error"]),
        signed_error,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ContractError("forecast result signed_error mismatch")
    if not math.isclose(
        float(record["absolute_error"]),
        abs(signed_error),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ContractError("forecast result absolute_error mismatch")
    expected_hit = (
        actual > 0
        if record["predicted_direction"] == "positive_spread"
        else actual < 0
    )
    if (
        not isinstance(record.get("direction_hit"), bool)
        or record["direction_hit"] is not expected_hit
    ):
        raise ContractError("forecast result direction_hit mismatch")
    for field in ("within_q25_q75", "within_q10_q90"):
        if not isinstance(record.get(field), bool):
            raise ContractError(f"{field} must be boolean")
    if record["within_q25_q75"] is not (
        float(distribution["q25"])
        <= actual
        <= float(distribution["q75"])
    ):
        raise ContractError("forecast result q25-q75 coverage mismatch")
    if record["within_q10_q90"] is not (
        float(distribution["q10"])
        <= actual
        <= float(distribution["q90"])
    ):
        raise ContractError("forecast result q10-q90 coverage mismatch")

    candidates = record.get("candidate_results")
    if not isinstance(candidates, list) or not candidates:
        raise ContractError("forecast result requires candidate results")
    adjusted_values = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise ContractError("forecast candidate result must be an object")
        for field in ("candidate_id", "series_id", "axis"):
            _require_text(candidate, field)
        direction = candidate.get("direction")
        if (
            isinstance(direction, bool)
            or direction not in {-1, 1}
        ):
            raise ContractError(
                "forecast candidate result direction must be -1 or 1"
            )
        raw_spread = candidate.get("raw_group_spread")
        adjusted = candidate.get("direction_adjusted_spread")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in (raw_spread, adjusted)
        ):
            raise ContractError("forecast candidate spreads must be finite")
        if not math.isclose(
            float(adjusted),
            int(direction) * float(raw_spread),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ContractError(
                "forecast candidate direction-adjusted spread mismatch"
            )
        adjusted_values.append(float(adjusted))
    if not math.isclose(
        actual,
        sum(adjusted_values) / len(adjusted_values),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ContractError(
            "actual selected group spread must average candidate results"
        )
    for field in ("group_factor_value_ids", "group_outcome_ids"):
        values = record.get(field)
        if (
            not isinstance(values, list)
            or not values
            or any(not str(value).strip() for value in values)
            or values != sorted(set(values))
        ):
            raise ContractError(f"{field} must be a sorted unique list")
    if len(record["group_factor_value_ids"]) != len(
        record["group_outcome_ids"]
    ):
        raise ContractError(
            "forecast result group/outcome cross-section size mismatch"
        )
    cross_section = record.get("cross_section_audit")
    if not isinstance(cross_section, Mapping):
        raise ContractError("forecast result cross_section_audit is required")
    expected_stock_outcomes = cross_section.get(
        "expected_stock_outcomes"
    )
    candidate_session_rows = cross_section.get(
        "candidate_session_rows"
    )
    if (
        isinstance(expected_stock_outcomes, bool)
        or not isinstance(expected_stock_outcomes, int)
        or expected_stock_outcomes != len(record["group_outcome_ids"])
    ):
        raise ContractError(
            "forecast result expected stock outcome count mismatch"
        )
    if (
        isinstance(candidate_session_rows, bool)
        or not isinstance(candidate_session_rows, int)
        or candidate_session_rows < len(candidates)
    ):
        raise ContractError(
            "forecast result candidate session count is invalid"
        )
    if (
        cross_section.get("statistical_unit")
        != "complete_daily_cross_section"
    ):
        raise ContractError(
            "unsupported forecast result statistical unit"
        )
    expected_digest = canonical_digest({
        "forecast_input_digest": record.get("forecast_input_digest"),
        "forecast_audit_input_digest": record.get(
            "forecast_audit_input_digest"
        ),
        "selection_input_digest": record.get("selection_input_digest"),
        "predicted_direction": record.get("predicted_direction"),
        "expected_spread": record.get("expected_spread"),
        "confidence": record.get("confidence"),
        "forecast_distribution": record.get("forecast_distribution"),
        "group_factor_value_ids": record.get("group_factor_value_ids"),
        "group_outcome_ids": record.get("group_outcome_ids"),
        "candidate_results": record.get("candidate_results"),
        "outcome_trade_date": record.get("outcome_trade_date"),
        "outcome_available_at": record.get("outcome_available_at"),
    })
    if record.get("input_digest") != expected_digest:
        raise ContractError("forecast result input_digest mismatch")
    if record.get("result_id") != make_forecast_result_id(record):
        raise ContractError("forecast result_id mismatch")
    if record.get("production_eligible") is not False:
        raise ContractError("forecast result must not be production eligible")
    if record.get("promotion_status") != "manual_review_required":
        raise ContractError(
            "forecast result promotion requires manual review"
        )


def validate_forecast_calibration_audit(
    record: Mapping[str, Any],
) -> None:
    """Validate an immutable calibration snapshot without promoting it."""

    if record.get("schema_version") != FORECAST_CALIBRATION_SCHEMA_VERSION:
        raise ContractError(
            "unsupported forecast calibration schema_version"
        )
    _parse_trade_date(record.get("as_of_trade_date"), "as_of_trade_date")
    _parse_aware_timestamp(record.get("decision_at"), "decision_at")
    for field in (
        "select_version",
        "forecast_version",
        "evaluator_version",
        "calibration_version",
        "status",
        "input_digest",
        "promotion_status",
        "scope",
    ):
        _require_text(record, field)
    minimum = record.get("minimum_evaluated_dates")
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or minimum <= 0
    ):
        raise ContractError(
            "minimum_evaluated_dates must be a positive integer"
        )
    if record.get("production_eligible") is not False:
        raise ContractError(
            "forecast calibration must not be production eligible"
        )
    if record.get("promotion_status") != "manual_review_required":
        raise ContractError(
            "forecast calibration promotion requires manual review"
        )
    horizons = record.get("horizons")
    if not isinstance(horizons, Mapping) or not horizons:
        raise ContractError("forecast calibration horizons are required")
    for raw_horizon, metrics in horizons.items():
        try:
            horizon = int(str(raw_horizon))
        except (TypeError, ValueError) as exc:
            raise ContractError(
                "forecast calibration horizon must be positive"
            ) from exc
        if horizon <= 0 or not isinstance(metrics, Mapping):
            raise ContractError(
                "forecast calibration horizon entry is invalid"
            )
        count_fields = (
            "forecast_dates",
            "available_forecasts",
            "abstain_forecasts",
            "evaluated_dates",
            "pending_available",
        )
        counts = {}
        for field in count_fields:
            value = metrics.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ContractError(
                    f"forecast calibration {field} must be non-negative"
                )
            counts[field] = value
        if (
            counts["available_forecasts"] + counts["abstain_forecasts"]
            != counts["forecast_dates"]
        ):
            raise ContractError("forecast calibration forecast count mismatch")
        if (
            counts["evaluated_dates"] + counts["pending_available"]
            != counts["available_forecasts"]
        ):
            raise ContractError(
                "forecast calibration evaluated/pending count mismatch"
            )
        metric_fields = (
            "direction_hit_rate",
            "mean_actual_spread",
            "mean_signed_error",
            "mean_absolute_error",
            "q25_q75_coverage",
            "q10_q90_coverage",
        )
        values = [metrics.get(field) for field in metric_fields]
        if counts["evaluated_dates"] == 0:
            if any(value is not None for value in values):
                raise ContractError(
                    "empty calibration metrics must be null"
                )
        elif any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in values
        ):
            raise ContractError(
                "evaluated calibration metrics must be finite"
            )
        for field in (
            "direction_hit_rate",
            "q25_q75_coverage",
            "q10_q90_coverage",
        ):
            value = metrics.get(field)
            if value is not None and not 0 <= float(value) <= 1:
                raise ContractError(
                    f"forecast calibration {field} must be within [0, 1]"
                )
        if (
            metrics.get("q25_q75_coverage") is not None
            and float(metrics["q10_q90_coverage"])
            < float(metrics["q25_q75_coverage"])
        ):
            raise ContractError(
                "wide forecast interval coverage cannot be below narrow"
            )
        if (
            metrics.get("mean_absolute_error") is not None
            and float(metrics["mean_absolute_error"]) < 0
        ):
            raise ContractError(
                "forecast calibration mean_absolute_error cannot be negative"
            )
        expected_status = (
            "no_available_forecasts"
            if counts["available_forecasts"] == 0
            else (
                "shadow_sample_threshold_reached"
                if counts["evaluated_dates"] >= minimum
                else "insufficient_evaluated_dates"
            )
        )
        if metrics.get("evidence_status") != expected_status:
            raise ContractError(
                "forecast calibration evidence_status mismatch"
            )
    forecast_digests = record.get("forecast_audit_input_digests")
    result_ids = record.get("result_ids")
    for values, field in (
        (forecast_digests, "forecast_audit_input_digests"),
        (result_ids, "result_ids"),
    ):
        if (
            not isinstance(values, list)
            or values != sorted(set(values))
            or any(not str(value).strip() for value in values)
        ):
            raise ContractError(f"{field} must be a sorted unique list")
    expected_digest = canonical_digest({
        "as_of_trade_date": record.get("as_of_trade_date"),
        "decision_at": record.get("decision_at"),
        "select_version": record.get("select_version"),
        "forecast_version": record.get("forecast_version"),
        "evaluator_version": record.get("evaluator_version"),
        "calibration_version": record.get("calibration_version"),
        "minimum_evaluated_dates": minimum,
        "status": record.get("status"),
        "horizons": record.get("horizons"),
        "forecast_audit_input_digests": forecast_digests,
        "result_ids": result_ids,
    })
    if record.get("input_digest") != expected_digest:
        raise ContractError("forecast calibration input_digest mismatch")
    available_total = sum(
        int(metrics["available_forecasts"])
        for metrics in horizons.values()
    )
    threshold_reached = any(
        int(metrics["evaluated_dates"]) >= minimum
        for metrics in horizons.values()
    )
    expected_status = (
        "no_available_forecasts"
        if available_total == 0
        else (
            "shadow_sample_threshold_reached"
            if threshold_reached
            else "insufficient_evaluated_dates"
        )
    )
    if record.get("status") != expected_status:
        raise ContractError("forecast calibration status mismatch")
