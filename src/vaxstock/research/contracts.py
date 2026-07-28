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
