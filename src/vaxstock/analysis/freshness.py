# -*- coding: utf-8 -*-
"""Pure EOD data-freshness checks.

The forecast gate is intentionally separate from data collection. It checks
dates supplied by sources and never substitutes ``now()`` for a missing market
trade date.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional


FRESHNESS_SCHEMA_VERSION = 1


def _trade_date(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError:
        return None
    return text


def _history_trade_date(stock: Mapping[str, Any]) -> Optional[str]:
    history = stock.get("history_tail") or []
    if not isinstance(history, list) or not history:
        return None
    dates = [
        _trade_date((row or {}).get("trade_date"))
        for row in history
        if isinstance(row, Mapping)
    ]
    valid = [value for value in dates if value]
    return max(valid) if valid else None


def _digest(refs: Mapping[str, Any]) -> str:
    raw = json.dumps(
        refs,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def assess_eod_freshness(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a fail-closed forecast gate for one collected EOD payload."""

    market_date = _trade_date(
        ((payload or {}).get("market_overview") or {}).get("trade_date")
    )
    failures: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []

    market_ok = market_date is not None
    checks.append({
        "name": "market_overview",
        "critical": True,
        "status": "ready" if market_ok else "blocked",
        "data_date": market_date,
        "expected_trade_date": market_date,
    })
    if not market_ok:
        failures.append({
            "check": "market_overview",
            "reason": "trade_date_missing_or_invalid",
        })

    indices = list((payload or {}).get("indices") or [])
    index_dates = [_trade_date((row or {}).get("trade_date")) for row in indices]
    index_ok = bool(indices) and market_ok and all(
        value == market_date for value in index_dates
    )
    checks.append({
        "name": "indices",
        "critical": True,
        "status": "ready" if index_ok else "blocked",
        "data_dates": index_dates,
        "expected_trade_date": market_date,
        "count": len(indices),
    })
    if not index_ok:
        failures.append({
            "check": "indices",
            "reason": "missing_or_trade_date_mismatch",
            "data_dates": index_dates,
        })

    stocks = list((payload or {}).get("stocks") or [])
    stock_dates = {
        str((stock or {}).get("code") or ""): _history_trade_date(stock or {})
        for stock in stocks
    }
    blocked_codes = sorted(
        code for code, value in stock_dates.items()
        if not code or not market_ok or value != market_date
    )
    eligible_codes = sorted(
        code for code, value in stock_dates.items()
        if code and market_ok and value == market_date
    )
    if not stocks:
        stock_status = "blocked"
    elif blocked_codes:
        stock_status = "degraded" if eligible_codes else "blocked"
    else:
        stock_status = "ready"
    checks.append({
        "name": "stock_history",
        "critical": True,
        "scope": "per_target",
        "status": stock_status,
        "expected_trade_date": market_date,
        "count": len(stocks),
        "eligible_codes": eligible_codes,
        "blocked_codes": blocked_codes,
    })
    if not stocks:
        failures.append({
            "check": "stock_history",
            "reason": "empty_universe",
        })
    elif not eligible_codes:
        failures.append({
            "check": "stock_history",
            "reason": "no_eligible_targets",
            "blocked_codes": blocked_codes,
        })
    blocked_targets = [
        {
            "code": code,
            "reason": "history_trade_date_missing_or_mismatch",
            "data_date": stock_dates.get(code),
            "expected_trade_date": market_date,
        }
        for code in blocked_codes
    ]

    refs = {
        "market_trade_date": market_date,
        "index_trade_dates": index_dates,
        "stock_trade_dates": stock_dates,
    }
    eligible = not failures
    status = "blocked" if not eligible else ("degraded" if blocked_targets else "ready")
    return {
        "schema_version": FRESHNESS_SCHEMA_VERSION,
        "status": status,
        "forecast_eligible": eligible,
        "trade_date": market_date,
        "checks": checks,
        "critical_failures": failures,
        "eligible_codes": eligible_codes,
        "blocked_targets": blocked_targets,
        "input_digest": _digest(refs),
    }
