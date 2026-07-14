# -*- coding: utf-8 -*-
"""Deterministic intraday market-health checks over verified quotes."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from vaxstock import config


FORECAST_DIR = config.STATE_DIR / "forecast"
CURRENT_HEALTH_FILE = FORECAST_DIR / "current_market_health.json"
HEALTH_EVENTS_FILE = FORECAST_DIR / "market_health_events.jsonl"
SCHEMA_VERSION = 1
POLICY_VERSION = "market_health_v1"
CHECK_INTERVAL_SECONDS = int(os.environ.get("MARKET_HEALTH_INTERVAL_SECONDS", "900"))
MIN_VALID_HOLDINGS = 3
MIN_QUOTE_COVERAGE_RATIO = 0.50
SYNC_MOVE_PCT = 3.0
SYNC_MIN_COUNT = 3
SYNC_MIN_RATIO = 0.40
AI_SYNC_MIN_COUNT = 2
AI_SYNC_MIN_RATIO = 0.50
HOLDING_SHOCK_DROP_PCT = -7.0
HOLDING_SHOCK_AMPLITUDE_PCT = 9.0
C_DIRECTION_CONTRADICTION_PCT = 5.0
MAX_QUOTE_AGE_SECONDS = 20 * 60
MAX_QUOTE_FUTURE_SECONDS = 120
AI_CONCEPTS = {"\u0041\u0049\u7b97\u529b", "\u0041\u0049\u0044\u0043"}
VALID_REGIMES = {"momentum", "value", "panic"}


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _observed_at(value=None) -> str:
    if isinstance(value, dt.datetime):
        return value.isoformat(timespec="seconds")
    text = str(value or "").strip()
    if text:
        dt.datetime.fromisoformat(text)
        return text
    return _now_iso()


def _trade_date_key(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    for pattern in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, pattern).strftime("%Y%m%d")
        except ValueError:
            continue
    return None


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _quote_datetime(quote: Mapping[str, Any]) -> Optional[dt.datetime]:
    trade_date = _trade_date_key(quote.get("trade_date"))
    trade_time = str(quote.get("trade_time") or "").strip()
    if not trade_date or not trade_time:
        return None
    try:
        return dt.datetime.strptime(
            f"{trade_date} {trade_time}", "%Y%m%d %H:%M:%S",
        )
    except ValueError:
        return None

def _read_state(path: Path):
    if not path.exists():
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return None, "root_not_object"
    return data, None


def _write_state(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(dict(data), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _read_event_ids(path: Path) -> set:
    if not path.exists():
        return set()
    event_ids = set()
    for line_no, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1,
    ):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid event JSON at line {line_no}: {exc}") from exc
        if not isinstance(row, dict) or not row.get("event_id"):
            raise ValueError(f"event_id missing at line {line_no}")
        event_ids.add(str(row["event_id"]))
    return event_ids


def _append_events(path: Path, rows: Iterable[Mapping[str, Any]]):
    existing = _read_event_ids(path)
    written = []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            event_id = str(row.get("event_id") or "")
            if not event_id or event_id in existing:
                continue
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            existing.add(event_id)
            written.append(dict(row))
    return written


def _event_id(trade_date: str, signal_key: str, episode: int, status: str) -> str:
    raw = f"{trade_date}|{signal_key}|{episode}|{status}|{POLICY_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _regime_event_id(trade_date: str, previous: str, current: str,
                     episode: int) -> str:
    raw = f"{trade_date}|regime|{previous}|{current}|{episode}|{POLICY_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _policy() -> Dict[str, Any]:
    return {
        "version": POLICY_VERSION,
        "check_interval_seconds": CHECK_INTERVAL_SECONDS,
        "minimum_valid_holdings": MIN_VALID_HOLDINGS,
        "minimum_quote_coverage_ratio": MIN_QUOTE_COVERAGE_RATIO,
        "synchronized_move_pct": SYNC_MOVE_PCT,
        "synchronized_minimum_count": SYNC_MIN_COUNT,
        "synchronized_minimum_ratio": SYNC_MIN_RATIO,
        "ai_synchronized_minimum_count": AI_SYNC_MIN_COUNT,
        "ai_synchronized_minimum_ratio": AI_SYNC_MIN_RATIO,
        "holding_shock_drop_pct": HOLDING_SHOCK_DROP_PCT,
        "holding_shock_amplitude_pct": HOLDING_SHOCK_AMPLITUDE_PCT,
        "c_direction_contradiction_pct": C_DIRECTION_CONTRADICTION_PCT,
        "maximum_quote_age_seconds": MAX_QUOTE_AGE_SECONDS,
        "maximum_quote_future_seconds": MAX_QUOTE_FUTURE_SECONDS,
        "ai_concepts": sorted(AI_CONCEPTS),
        "market_overview_used_for_trigger": False,
    }


def _quote_snapshot(code: str, quote: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "code": code,
        "name": quote.get("name"),
        "trade_time": quote.get("trade_time"),
        "price": _number(quote.get("price")),
        "change_pct": _number(quote.get("change_pct")),
        "amplitude_pct": _number(quote.get("amplitude_pct")),
        "amount": _number(quote.get("amount")),
        "source": quote.get("source"),
    }


def _signal(key: str, event_type: str, severity: str, scope: str,
            summary: str, evidence: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "signal_key": key,
        "event_type": event_type,
        "severity": severity,
        "scope": scope,
        "summary": summary,
        "evidence": dict(evidence),
    }


def _task_prediction_index(tasks: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for task in tasks or []:
        code = str((task or {}).get("code") or "").strip()
        prediction = (
            (((task or {}).get("evidence_pack") or {}).get("C_prediction") or {}).get("prediction")
            or {}
        )
        if code and isinstance(prediction, dict):
            out[code] = dict(prediction)
    return out


def evaluate_market_health(*, quotes: Mapping[str, Mapping[str, Any]],
                           holdings: Mapping[str, Mapping[str, Any]],
                           tasks: Iterable[Mapping[str, Any]] = (),
                           observed_at=None) -> Dict[str, Any]:
    """Return deterministic active signals or an explicit data-quality failure."""
    holding_codes = sorted(str(code) for code in (holdings or {}) if str(code))
    observed_dt = None
    if observed_at is not None:
        try:
            observed_dt = dt.datetime.fromisoformat(_observed_at(observed_at))
        except ValueError:
            return {
                "status": "insufficient_data", "trade_date": None,
                "signals": {},
                "quality": {"reason": "observed_at_invalid"},
            }
        if observed_dt.tzinfo is not None:
            observed_dt = observed_dt.replace(tzinfo=None)
    dated = {}
    stale_codes = []
    seen_dates = set()
    for code in holding_codes:
        quote = (quotes or {}).get(code) or {}
        trade_date = _trade_date_key(quote.get("trade_date"))
        if trade_date:
            seen_dates.add(trade_date)
        quote_dt = _quote_datetime(quote)
        price = _number(quote.get("price"))
        change_pct = _number(quote.get("change_pct"))
        fresh = quote_dt is not None
        if fresh and observed_dt is not None:
            age = (observed_dt - quote_dt).total_seconds()
            fresh = -MAX_QUOTE_FUTURE_SECONDS <= age <= MAX_QUOTE_AGE_SECONDS
        if trade_date and price is not None and price > 0 and change_pct is not None and fresh:
            dated[code] = dict(quote)
        elif trade_date and quote_dt is not None and observed_dt is not None and not fresh:
            stale_codes.append(code)

    if len(seen_dates) != 1:
        return {
            "status": "insufficient_data",
            "trade_date": None,
            "signals": {},
            "quality": {
                "reason": "quote_trade_date_missing_or_mixed",
                "observed_trade_dates": sorted(seen_dates),
            },
        }
    trade_date = next(iter(seen_dates))
    valid = {
        code: quote for code, quote in dated.items()
        if _trade_date_key(quote.get("trade_date")) == trade_date
    }
    total = len(holding_codes)
    coverage_ratio = len(valid) / total if total else 0.0
    quality = {
        "holding_count": total,
        "valid_quote_count": len(valid),
        "quote_coverage_ratio": coverage_ratio,
        "trade_date": trade_date,
        "sources": sorted({str(row.get("source") or "") for row in valid.values()}),
        "stale_quote_codes": sorted(stale_codes),
    }
    if len(valid) < MIN_VALID_HOLDINGS or coverage_ratio < MIN_QUOTE_COVERAGE_RATIO:
        quality["reason"] = "holding_quote_coverage_insufficient"
        return {
            "status": "insufficient_data",
            "trade_date": trade_date,
            "signals": {},
            "quality": quality,
        }

    signals: Dict[str, Dict[str, Any]] = {}
    falling = [
        code for code, quote in valid.items()
        if _number(quote.get("change_pct")) <= -SYNC_MOVE_PCT
    ]
    rising = [
        code for code, quote in valid.items()
        if _number(quote.get("change_pct")) >= SYNC_MOVE_PCT
    ]
    if len(falling) >= SYNC_MIN_COUNT and len(falling) / len(valid) >= SYNC_MIN_RATIO:
        evidence = {
            "matched_codes": sorted(falling),
            "matched_count": len(falling),
            "valid_quote_count": len(valid),
            "matched_ratio": len(falling) / len(valid),
            "threshold_pct": -SYNC_MOVE_PCT,
            "quotes": [_quote_snapshot(code, valid[code]) for code in sorted(falling)],
        }
        signals["portfolio_synchronized_drop"] = _signal(
            "portfolio_synchronized_drop", "portfolio_synchronized_drop", "high",
            "portfolio",
            f"{len(falling)}/{len(valid)}\u53ea\u6301\u4ed3\u540c\u6b65\u4e0b\u8dcc\u81f3\u5c11{SYNC_MOVE_PCT:.1f}%",
            evidence,
        )
    if len(rising) >= SYNC_MIN_COUNT and len(rising) / len(valid) >= SYNC_MIN_RATIO:
        evidence = {
            "matched_codes": sorted(rising),
            "matched_count": len(rising),
            "valid_quote_count": len(valid),
            "matched_ratio": len(rising) / len(valid),
            "threshold_pct": SYNC_MOVE_PCT,
            "quotes": [_quote_snapshot(code, valid[code]) for code in sorted(rising)],
        }
        signals["portfolio_synchronized_rise"] = _signal(
            "portfolio_synchronized_rise", "portfolio_synchronized_rise", "medium",
            "portfolio",
            f"{len(rising)}/{len(valid)}\u53ea\u6301\u4ed3\u540c\u6b65\u4e0a\u6da8\u81f3\u5c11{SYNC_MOVE_PCT:.1f}%",
            evidence,
        )

    ai_codes = []
    for code in valid:
        concepts = set(str(value) for value in ((holdings.get(code) or {}).get("concepts") or []))
        if concepts & AI_CONCEPTS:
            ai_codes.append(code)
    ai_falling = [
        code for code in ai_codes
        if _number(valid[code].get("change_pct")) <= -SYNC_MOVE_PCT
    ]
    ai_rising = [
        code for code in ai_codes
        if _number(valid[code].get("change_pct")) >= SYNC_MOVE_PCT
    ]
    if ai_codes and len(ai_falling) >= AI_SYNC_MIN_COUNT and len(ai_falling) / len(ai_codes) >= AI_SYNC_MIN_RATIO:
        signals["ai_holdings_synchronized_drop"] = _signal(
            "ai_holdings_synchronized_drop", "ai_holdings_synchronized_drop", "high",
            "ai_holdings",
            f"AI\u6301\u4ed3{len(ai_falling)}/{len(ai_codes)}\u53ea\u540c\u6b65\u4e0b\u8dcc\u81f3\u5c11{SYNC_MOVE_PCT:.1f}%",
            {
                "ai_codes": sorted(ai_codes),
                "matched_codes": sorted(ai_falling),
                "matched_count": len(ai_falling),
                "ai_valid_count": len(ai_codes),
                "matched_ratio": len(ai_falling) / len(ai_codes),
                "threshold_pct": -SYNC_MOVE_PCT,
                "quotes": [_quote_snapshot(code, valid[code]) for code in sorted(ai_falling)],
            },
        )
    if ai_codes and len(ai_rising) >= AI_SYNC_MIN_COUNT and len(ai_rising) / len(ai_codes) >= AI_SYNC_MIN_RATIO:
        signals["ai_holdings_synchronized_rise"] = _signal(
            "ai_holdings_synchronized_rise", "ai_holdings_synchronized_rise", "medium",
            "ai_holdings",
            f"AI\u6301\u4ed3{len(ai_rising)}/{len(ai_codes)}\u53ea\u540c\u6b65\u4e0a\u6da8\u81f3\u5c11{SYNC_MOVE_PCT:.1f}%",
            {
                "ai_codes": sorted(ai_codes),
                "matched_codes": sorted(ai_rising),
                "matched_count": len(ai_rising),
                "ai_valid_count": len(ai_codes),
                "matched_ratio": len(ai_rising) / len(ai_codes),
                "threshold_pct": SYNC_MOVE_PCT,
                "quotes": [_quote_snapshot(code, valid[code]) for code in sorted(ai_rising)],
            },
        )

    prediction_index = _task_prediction_index(tasks)
    for code, quote in sorted(valid.items()):
        change_pct = _number(quote.get("change_pct"))
        amplitude_pct = _number(quote.get("amplitude_pct"))
        if (
            change_pct <= HOLDING_SHOCK_DROP_PCT
            or (amplitude_pct is not None and amplitude_pct >= HOLDING_SHOCK_AMPLITUDE_PCT)
        ):
            key = f"holding_shock:{code}"
            signals[key] = _signal(
                key, "holding_shock", "high", code,
                f"{quote.get('name') or code}\u51fa\u73b0\u6781\u7aef\u6ce2\u52a8",
                {
                    "quote": _quote_snapshot(code, quote),
                    "drop_threshold_pct": HOLDING_SHOCK_DROP_PCT,
                    "amplitude_threshold_pct": HOLDING_SHOCK_AMPLITUDE_PCT,
                },
            )

        prediction = prediction_index.get(code) or {}
        direction = str(prediction.get("direction") or "").strip().lower()
        contradicted = (
            direction == "up" and change_pct <= -C_DIRECTION_CONTRADICTION_PCT
        ) or (
            direction == "down" and change_pct >= C_DIRECTION_CONTRADICTION_PCT
        )
        if contradicted:
            key = f"c_direction_contradiction:{code}"
            signals[key] = _signal(
                key, "c_direction_contradiction", "medium", code,
                f"{quote.get('name') or code}\u76d8\u4e2d\u65b9\u5411\u4e0eC\u7ebf\u660e\u663e\u76f8\u53cd",
                {
                    "quote": _quote_snapshot(code, quote),
                    "c_line": {
                        "action": prediction.get("action"),
                        "direction": prediction.get("direction"),
                        "confidence": prediction.get("confidence"),
                    },
                    "contradiction_threshold_pct": C_DIRECTION_CONTRADICTION_PCT,
                },
            )

    return {
        "status": "evaluated",
        "trade_date": trade_date,
        "signals": signals,
        "quality": quality,
    }


def _due(state: Mapping[str, Any], observed_at: str, trade_date: str,
         force: bool) -> bool:
    if force or _trade_date_key(state.get("trade_date")) != trade_date:
        return True
    last = str(state.get("last_checked_at") or "").strip()
    if not last:
        return True
    try:
        elapsed = (
            dt.datetime.fromisoformat(observed_at)
            - dt.datetime.fromisoformat(last)
        ).total_seconds()
    except ValueError:
        return True
    return elapsed >= CHECK_INTERVAL_SECONDS


def run_market_health_check(*, quotes: Mapping[str, Mapping[str, Any]],
                            holdings: Mapping[str, Mapping[str, Any]],
                            tasks: Iterable[Mapping[str, Any]] = (),
                            market_ctx_loader: Optional[Callable[[], Mapping[str, Any]]] = None,
                            observed_at=None, force: bool = False,
                            state_path=None, events_path=None) -> Dict[str, Any]:
    """Evaluate, persist state transitions, and return newly written high-risk events."""
    try:
        stamp = _observed_at(observed_at)
    except ValueError:
        return {"status": "invalid_observed_at", "written": 0, "notifications": []}
    evaluated = evaluate_market_health(
        quotes=quotes, holdings=holdings, tasks=tasks, observed_at=stamp,
    )
    trade_date = evaluated.get("trade_date")
    path = Path(state_path or CURRENT_HEALTH_FILE)
    events = Path(events_path or HEALTH_EVENTS_FILE)
    state, error = _read_state(path)
    if error:
        return {
            "status": "invalid_state", "written": 0,
            "notifications": [], "detail": error,
        }
    if not trade_date:
        return {
            "status": "insufficient_data", "written": 0,
            "notifications": [], "quality": evaluated.get("quality") or {},
        }
    if not _due(state or {}, stamp, trade_date, force):
        return {"status": "throttled", "written": 0, "notifications": []}

    if _trade_date_key((state or {}).get("trade_date")) != trade_date:
        state = {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "trade_date": trade_date,
            "signals": {},
            "last_regime": None,
            "regime_episode": 0,
        }
    if evaluated.get("status") != "evaluated":
        updated = {
            **state,
            "last_checked_at": stamp,
            "last_quality": evaluated.get("quality") or {},
        }
        _write_state(path, updated)
        return {
            "status": "insufficient_data", "written": 0,
            "notifications": [], "trade_date": trade_date,
            "quality": evaluated.get("quality") or {},
        }

    market_ctx = dict(market_ctx_loader() or {}) if market_ctx_loader else {}
    regime = str(market_ctx.get("regime") or "").strip()
    if regime not in VALID_REGIMES:
        regime = None
    previous_regime = str(state.get("last_regime") or "").strip() or None
    pending_events = []
    regime_episode = int(state.get("regime_episode") or 0)
    if regime and previous_regime and regime != previous_regime:
        regime_episode += 1
        severity = "high" if regime == "panic" else "medium"
        pending_events.append({
            "schema_version": SCHEMA_VERSION,
            "event_id": _regime_event_id(
                trade_date, previous_regime, regime, regime_episode,
            ),
            "trade_date": trade_date,
            "observed_at": stamp,
            "status": "transition",
            "event_type": "market_regime_change",
            "signal_key": "market_regime_change",
            "episode": regime_episode,
            "severity": severity,
            "scope": "market",
            "summary": f"\u5e02\u573aregime\u4ece{previous_regime}\u5207\u6362\u4e3a{regime}",
            "evidence": {
                "previous_regime": previous_regime,
                "current_regime": regime,
                "source": "GET /market regime",
                "overview_used_for_trigger": False,
            },
            "policy": _policy(),
            "evaluation": {"user_execution_used": False},
        })

    previous_signals = state.get("signals") or {}
    if not isinstance(previous_signals, dict):
        return {
            "status": "invalid_state", "written": 0,
            "notifications": [], "detail": "signals_not_object",
        }
    current_signals = evaluated.get("signals") or {}
    next_signals = {}
    all_keys = sorted(set(previous_signals) | set(current_signals))
    for key in all_keys:
        old = previous_signals.get(key) or {}
        signal = current_signals.get(key)
        was_active = bool(old.get("active"))
        episode = int(old.get("episode") or 0)
        if signal:
            if not was_active:
                episode += 1
                pending_events.append({
                    "schema_version": SCHEMA_VERSION,
                    "event_id": _event_id(trade_date, key, episode, "opened"),
                    "trade_date": trade_date,
                    "observed_at": stamp,
                    "status": "opened",
                    "episode": episode,
                    **signal,
                    "policy": _policy(),
                    "evaluation": {"user_execution_used": False},
                })
            next_signals[key] = {
                "active": True,
                "episode": episode,
                "opened_at": old.get("opened_at") if was_active else stamp,
                "last_seen_at": stamp,
                "event_type": signal.get("event_type"),
                "severity": signal.get("severity"),
                "summary": signal.get("summary"),
            }
        elif was_active:
            pending_events.append({
                "schema_version": SCHEMA_VERSION,
                "event_id": _event_id(trade_date, key, episode, "recovered"),
                "trade_date": trade_date,
                "observed_at": stamp,
                "status": "recovered",
                "episode": episode,
                "signal_key": key,
                "event_type": old.get("event_type"),
                "severity": "low",
                "scope": "recovery",
                "summary": f"{old.get('summary') or key}\u5df2\u6062\u590d",
                "evidence": {"previous_severity": old.get("severity")},
                "policy": _policy(),
                "evaluation": {"user_execution_used": False},
            })
            next_signals[key] = {
                **old,
                "active": False,
                "episode": episode,
                "recovered_at": stamp,
            }
        else:
            next_signals[key] = dict(old)

    try:
        written = _append_events(events, pending_events)
    except (OSError, UnicodeError, ValueError) as exc:
        return {
            "status": "invalid_events", "written": 0,
            "notifications": [], "detail": f"{type(exc).__name__}: {exc}",
        }
    updated = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "trade_date": trade_date,
        "last_checked_at": stamp,
        "last_quality": evaluated.get("quality") or {},
        "last_regime": regime or previous_regime,
        "regime_episode": regime_episode,
        "signals": next_signals,
        "evaluation": {"user_execution_used": False},
    }
    _write_state(path, updated)
    notifications = [
        row for row in written
        if row.get("severity") == "high"
        and row.get("status") in {"opened", "transition"}
    ]
    return {
        "status": "written" if written else "no_change",
        "trade_date": trade_date,
        "written": len(written),
        "events": written,
        "notifications": notifications,
        "active_signals": sum(
            1 for row in next_signals.values() if (row or {}).get("active")
        ),
        "quality": evaluated.get("quality") or {},
    }


def render_market_health_notification(events: Iterable[Mapping[str, Any]]) -> str:
    rows = list(events or [])
    lines = [
        "【主动盘面体检】",
        "",
        "以下为确定性规则首次命中或风险升级，不是自动交易指令：",
        "",
    ]
    for row in rows:
        lines.append(
            f"- {row.get('summary') or row.get('event_type')}"
            f"（风险级别: {row.get('severity') or '待确认'}）"
        )
        if row.get("observed_at"):
            lines.append(f"  发现时间: {row['observed_at']}")
        evidence = row.get("evidence") or {}
        quote_rows = list(evidence.get("quotes") or [])
        matched_codes = list(evidence.get("matched_codes") or [])
        if matched_codes and not quote_rows:
            lines.append("  涉及标的: " + ", ".join(str(code) for code in matched_codes))
        if isinstance(evidence.get("quote"), Mapping):
            quote_rows.append(evidence["quote"])
        for quote in quote_rows:
            code = quote.get("code") or "?"
            name = quote.get("name") or code
            price = _number(quote.get("price"))
            change = _number(quote.get("change_pct"))
            amplitude = _number(quote.get("amplitude_pct"))
            facts = []
            if price is not None:
                facts.append(f"现价{price:.2f}")
            if change is not None:
                facts.append(f"涨跌{change:+.2f}%")
            if amplitude is not None:
                facts.append(f"振幅{amplitude:.2f}%")
            lines.append(f"  {name}({code}): " + "，".join(facts))
        previous = evidence.get("previous_regime")
        current = evidence.get("current_regime")
        if previous and current:
            lines.append(f"  市场状态: {previous} -> {current}")
    lines += [
        "",
        "处理原则: 暂停新增风险暴露，等待D线与收盘数据复核。",
        "数据口径: 持仓行情来自同一交易日实时quote；市场状态来自 /market；用户成交不参与触发。",
    ]
    return "\n".join(lines)