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
from typing import Any, Dict, List, Literal, Mapping, Optional, TypedDict


OBSERVATION_SCHEMA_VERSION = 1
FORECAST_SCHEMA_VERSION = 1
RUN_MANIFEST_SCHEMA_VERSION = 1


class ContractError(ValueError):
    """Raised when data cannot safely cross a research pipeline boundary."""


ObservationQuality = Literal["observed", "revised", "stale", "missing"]
ForecastStatus = Literal["available", "abstain"]


class AtomicObservation(TypedDict):
    """One append-only, point-in-time fact.

    ``effective_date`` says which economic/reporting period the value belongs
    to. ``available_at`` says when a decision process was first allowed to use
    it.  The two fields must never be substituted for each other.
    """

    schema_version: int
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


def assert_available_as_of(record: Mapping[str, Any], as_of: str) -> None:
    """Reject a fact that was not available at the simulated decision time."""

    validate_atomic_observation(record)
    available_at = _parse_aware_timestamp(record.get("available_at"), "available_at")
    decision_at = _parse_aware_timestamp(as_of, "as_of")
    if available_at > decision_at:
        raise ContractError("look-ahead detected: available_at is after as_of")


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
