# -*- coding: utf-8 -*-
"""Point-in-time F dimension for completed overseas market anchors.

The existing ``sources.us_market`` module remains the network adapter and
human-facing payload source.  This module only normalizes that already
retrieved payload into append-only research observations and deterministic
candidate factors.

The factors are deliberately modest:

* one completed-session return for each pre-registered anchor;
* one categorical context describing each return sign;
* one majority direction across NVDA, SOXX, and QQQ.

No return threshold, stock action, or effectiveness claim is made here.
"""

from __future__ import annotations

import math
from datetime import datetime
from numbers import Real
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from vaxstock.research.contracts import (
    FACTOR_VALUE_SCHEMA_VERSION,
    OBSERVATION_SCHEMA_VERSION,
    RUN_MANIFEST_SCHEMA_VERSION,
    ContractError,
    canonical_digest,
    factor_input_digest,
    make_factor_value_id,
    make_observation_id,
    make_run_id,
)


DIMENSION = "F"
FEATURE_SET_VERSION = "global_anchor_dimension_v1"
ANCHOR_FACTOR_VERSION = "F_completed_session_return_v1"
ANCHOR_CONTEXT_FACTOR_ID = "global_anchor_context"
ANCHOR_CONTEXT_FACTOR_VERSION = "F_global_anchor_context_v1"
ANCHOR_CONTEXT_ENTITY_ID = "GLOBAL-AI"
NOT_EXECUTED = "not_executed"
SOURCE = "yfinance"
SOURCE_REF_PREFIX = "payload.us_market"

ANCHORS: Dict[str, Dict[str, str]] = {
    "nvda": {"symbol": "NVDA", "category": "stocks"},
    "soxx": {"symbol": "SOXX", "category": "etfs"},
    "qqq": {"symbol": "QQQ", "category": "etfs"},
    "vix": {"symbol": "^VIX", "category": "indices"},
}
EQUITY_MAJORITY_KEYS = ("nvda", "soxx", "qqq")


def _trade_date(value: Any, field: str = "as_of_trade_date") -> str:
    text = str(value or "").strip()
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ContractError(f"{field} must be YYYYMMDD") from exc
    return text


def _source_date(value: Any) -> str:
    text = str(value or "").strip().replace("-", "")
    return _trade_date(text, "anchor source session date")


def _aware(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include timezone")
    return parsed


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool) or not isinstance(value, Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Real):
        number = float(value)
        if not math.isfinite(number):
            return None
        return int(value) if isinstance(value, int) else number
    if isinstance(value, Mapping):
        return {str(key): _json_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(child) for child in value]
    return str(value)


def _existing_index(
    observations: Iterable[Mapping[str, Any]],
) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    return {
        (
            str(row.get("source") or ""),
            str(row.get("source_ref") or ""),
            str(row.get("revision_id") or ""),
        ): dict(row)
        for row in observations
        if row.get("source") and row.get("source_ref") and row.get("revision_id")
    }


def _observation(
    *,
    entity_id: str,
    field: str,
    value: Any,
    effective_date: str,
    available_at: str,
    source_ref: str,
    revision_id: str,
    existing: Mapping[Tuple[str, str, str], Mapping[str, Any]],
) -> Dict[str, Any]:
    identity = (SOURCE, source_ref, revision_id)
    if identity in existing:
        return dict(existing[identity])
    row = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "observation_id": "",
        "entity_type": "market",
        "entity_id": entity_id,
        "dimension": DIMENSION,
        "field": field,
        "value": _json_value(value),
        "effective_date": effective_date,
        # yfinance does not expose a reliable publication timestamp.  The
        # system retrieval time is therefore the conservative first-use time.
        "available_at": available_at,
        "retrieved_at": available_at,
        "source": SOURCE,
        "source_ref": source_ref,
        "revision_id": revision_id,
        "quality": "observed",
    }
    row["observation_id"] = make_observation_id(row)
    return row


def _factor(
    *,
    factor_id: str,
    factor_version: str,
    value: Any,
    as_of_trade_date: str,
    effective_date: str,
    calculated_at: str,
    inputs: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    rows = list(inputs)
    input_ids = sorted({str(row["observation_id"]) for row in rows})
    if not input_ids:
        raise ContractError(f"{factor_id} requires source observations")
    available_at = max(
        rows,
        key=lambda row: _aware(row["available_at"], "available_at"),
    )["available_at"]
    row = {
        "schema_version": FACTOR_VALUE_SCHEMA_VERSION,
        "factor_value_id": "",
        "entity_type": "market",
        "entity_id": ANCHOR_CONTEXT_ENTITY_ID,
        "dimension": DIMENSION,
        "factor_id": factor_id,
        "factor_version": factor_version,
        "value": _json_value(value),
        "as_of_trade_date": as_of_trade_date,
        "effective_date": effective_date,
        "available_at": str(available_at),
        "calculated_at": calculated_at,
        "input_observation_ids": input_ids,
        "input_digest": factor_input_digest(input_ids),
        "quality": "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _rows_by_symbol(us_market: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for category in ("indices", "etfs", "stocks", "macro"):
        raw_rows = us_market.get(category) or []
        if not isinstance(raw_rows, list):
            raise ContractError(f"us_market.{category} must be an array")
        for raw in raw_rows:
            if not isinstance(raw, Mapping):
                raise ContractError(f"us_market.{category} row must be an object")
            symbol = str(raw.get("symbol") or "").strip()
            if not symbol:
                continue
            previous = indexed.get(symbol)
            row = dict(raw)
            if previous is not None and canonical_digest(previous) != canonical_digest(row):
                raise ContractError(f"conflicting us_market rows for {symbol}")
            indexed[symbol] = row
    return indexed


def _direction(value: float) -> str:
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def _majority_direction(states: Mapping[str, str]) -> Optional[str]:
    values = [states.get(key) for key in EQUITY_MAJORITY_KEYS]
    if any(value not in {"up", "down", "flat"} for value in values):
        return None
    up = sum(value == "up" for value in values)
    down = sum(value == "down" for value in values)
    if up >= 2:
        return "up"
    if down >= 2:
        return "down"
    return "mixed"


def build_global_anchor_run(
    *,
    as_of_trade_date: str,
    retrieved_at: str,
    us_market: Mapping[str, Any],
    existing_observations: Iterable[Mapping[str, Any]] = (),
    mode: str = "live",
) -> Tuple[
    Dict[str, Any],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    Dict[str, Any],
]:
    """Normalize one completed overseas-session payload into F factors."""

    as_of = _trade_date(as_of_trade_date)
    retrieved = _aware(retrieved_at, "retrieved_at")
    retrieved_iso = retrieved.isoformat(timespec="seconds")
    if mode not in {"live", "replay", "backtest"}:
        raise ContractError("mode must be live/replay/backtest")
    if not isinstance(us_market, Mapping):
        raise ContractError("us_market must be an object")

    by_symbol = _rows_by_symbol(us_market)
    existing = _existing_index(existing_observations)
    observations: List[Dict[str, Any]] = []
    factors: List[Dict[str, Any]] = []
    states: Dict[str, str] = {}
    returns: Dict[str, float] = {}
    sessions: Dict[str, str] = {}
    notes = [
        "candidate F factors only; no production action or effective label",
        "available_at uses conservative system retrieval time because the "
        "source payload has no authoritative publication timestamp",
        "close-to-close anchor return is a T+1 pre-open context, not an "
        "executable A-share return",
    ]

    missing = []
    invalid = []
    anchor_observations: Dict[str, Dict[str, Any]] = {}
    for key, definition in ANCHORS.items():
        symbol = definition["symbol"]
        raw = by_symbol.get(symbol)
        if raw is None:
            missing.append(symbol)
            continue
        price = _number(raw.get("price"))
        previous = _number(raw.get("prev_close"))
        try:
            session_date = _source_date(raw.get("date"))
        except ContractError:
            invalid.append(f"{symbol}:invalid_session_date")
            continue
        if price is None or previous is None or price <= 0 or previous <= 0:
            invalid.append(f"{symbol}:invalid_close")
            continue
        return_pct = (price / previous - 1.0) * 100.0
        reported = _number(raw.get("change_pct"))
        if reported is not None and not math.isclose(
            return_pct,
            reported,
            rel_tol=0.0,
            abs_tol=0.10,
        ):
            invalid.append(f"{symbol}:return_mismatch")
            continue
        value = {
            "anchor_key": key,
            "symbol": symbol,
            "source_session_date": session_date,
            "close": price,
            "previous_close": previous,
            "reported_change_pct": reported,
            "calculated_return_pct": return_pct,
            "volume": _number(raw.get("volume")),
            "payload_category": definition["category"],
        }
        source_ref = f"{SOURCE_REF_PREFIX}:{symbol}:{session_date}"
        observation = _observation(
            entity_id=symbol,
            field="completed_session",
            value=value,
            effective_date=session_date,
            available_at=retrieved_iso,
            source_ref=source_ref,
            revision_id=canonical_digest(value),
            existing=existing,
        )
        observations.append(observation)
        anchor_observations[key] = observation
        returns[key] = return_pct
        states[key] = _direction(return_pct)
        sessions[key] = session_date
        factors.append(
            _factor(
                factor_id=f"anchor_return_1d_pct.{key}",
                factor_version=ANCHOR_FACTOR_VERSION,
                value=return_pct,
                as_of_trade_date=as_of,
                effective_date=session_date,
                calculated_at=retrieved_iso,
                inputs=[observation],
            )
        )

    collection_status = {
        "required_symbols": [ANCHORS[key]["symbol"] for key in ANCHORS],
        "available_anchor_keys": sorted(returns),
        "missing_symbols": sorted(missing),
        "invalid_symbols": sorted(invalid),
        "complete": not missing and not invalid,
    }
    status_ref = f"{SOURCE_REF_PREFIX}:collection:{as_of}"
    status_observation = _observation(
        entity_id=ANCHOR_CONTEXT_ENTITY_ID,
        field="collection_status",
        value=collection_status,
        effective_date=as_of,
        available_at=retrieved_iso,
        source_ref=status_ref,
        revision_id=canonical_digest(collection_status),
        existing=existing,
    )
    observations.append(status_observation)

    majority = _majority_direction(states)
    context_value = {
        "context_version": ANCHOR_CONTEXT_FACTOR_VERSION,
        "states": {
            "anchor_nvda_direction": states.get("nvda"),
            "anchor_soxx_direction": states.get("soxx"),
            "anchor_qqq_direction": states.get("qqq"),
            "anchor_vix_direction": states.get("vix"),
            "anchor_equity_majority_direction": majority,
        },
        "returns_pct": dict(sorted(returns.items())),
        "source_session_dates": dict(sorted(sessions.items())),
        "collection_complete": collection_status["complete"],
        "timing_semantics": (
            "completed overseas session available at A-share T+1 pre-open; "
            "forecast label may use A-share T close as direction baseline "
            "but is non-executable at that close"
        ),
    }
    context_inputs = [status_observation, *anchor_observations.values()]
    factors.append(
        _factor(
            factor_id=ANCHOR_CONTEXT_FACTOR_ID,
            factor_version=ANCHOR_CONTEXT_FACTOR_VERSION,
            value=context_value,
            as_of_trade_date=as_of,
            effective_date=as_of,
            calculated_at=retrieved_iso,
            inputs=context_inputs,
        )
    )

    observation_ids = sorted(
        {str(row["observation_id"]) for row in observations}
    )
    factor_ids = sorted(str(row["factor_value_id"]) for row in factors)
    input_digest = canonical_digest({
        "observation_ids": observation_ids,
        "factor_value_ids": factor_ids,
    })
    manifest = {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": "",
        "mode": mode,
        "as_of_trade_date": as_of,
        "universe_id": ANCHOR_CONTEXT_ENTITY_ID,
        "feature_set_version": FEATURE_SET_VERSION,
        "group_version": NOT_EXECUTED,
        "select_version": NOT_EXECUTED,
        "forecast_version": NOT_EXECUTED,
        "input_digest": input_digest,
        "generated_at": retrieved_iso,
        "notes": notes,
        "stage": "global_anchor_refresh",
        "source_refs": [SOURCE_REF_PREFIX],
        "observation_count": len(observations),
        "factor_value_count": len(factors),
        "observation_digest": canonical_digest(observation_ids),
        "factor_value_digest": canonical_digest(factor_ids),
    }
    manifest["run_id"] = make_run_id(manifest)
    summary = {
        "as_of_trade_date": as_of,
        "status": "complete" if collection_status["complete"] else "partial",
        "available_anchor_keys": sorted(returns),
        "missing_symbols": sorted(missing),
        "invalid_symbols": sorted(invalid),
        "equity_majority_direction": majority,
        "states": context_value["states"],
        "observations": len(observations),
        "factors": len(factors),
    }
    return manifest, observations, factors, summary
