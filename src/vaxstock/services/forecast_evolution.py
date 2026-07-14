# -*- coding: utf-8 -*-
"""Freeze verified intraday paths after a D-line trigger.

The path is market-data-only. User executions are never read or evaluated here.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from vaxstock import config


FORECAST_DIR = config.STATE_DIR / "forecast"
CURRENT_EVOLUTION_FILE = FORECAST_DIR / "current_evolution_status.json"
EVOLUTION_HISTORY_FILE = FORECAST_DIR / "forecast_evolution.jsonl"
SCHEMA_VERSION = 1
POLICY_VERSION = "d_intraday_evolution_v1"
CHECKPOINT_SECONDS = {"15m": 15 * 60, "30m": 30 * 60}
CHECKPOINT_MAX_DELAY_SECONDS = 5 * 60
CLOSE_EARLIEST = "14:50:00"
SESSION_WINDOWS = (
    ("09:25:00", "11:30:00"),
    ("13:00:00", "15:02:00"),
)
POSITIVE_TRIGGER_TYPES = {
    "breakout_confirm", "reclaim_confirm", "panic_rebound_probe",
}
NON_POSITIVE_TRIGGER_TYPES = {
    "breakdown_confirm", "failed_breakout", "risk_off_confirm",
}


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


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
        return float(value)
    except (TypeError, ValueError):
        return None


def _clock_seconds(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    try:
        parsed = dt.datetime.strptime(text, "%H:%M:%S").time()
    except ValueError:
        return None
    return parsed.hour * 3600 + parsed.minute * 60 + parsed.second


def _in_observation_session(value: Any) -> bool:
    seconds = _clock_seconds(value)
    if seconds is None:
        return False
    return any(
        _clock_seconds(start) <= seconds <= _clock_seconds(end)
        for start, end in SESSION_WINDOWS
    )


def _trading_elapsed_seconds(start_time: Any, end_time: Any) -> Optional[int]:
    start = _clock_seconds(start_time)
    end = _clock_seconds(end_time)
    if start is None or end is None or end < start:
        return None
    elapsed = 0
    for window_start, window_end in SESSION_WINDOWS:
        left = max(start, _clock_seconds(window_start))
        right = min(end, _clock_seconds(window_end))
        if right > left:
            elapsed += right - left
    return elapsed


def _expectation(trigger_type: str) -> str:
    if trigger_type in POSITIVE_TRIGGER_TYPES:
        return "positive"
    if trigger_type in NON_POSITIVE_TRIGGER_TYPES:
        return "non_positive"
    return "unscored"


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


def _history_path(status_path: Path, history_path=None) -> Path:
    if history_path is not None:
        return Path(history_path)
    if status_path == Path(CURRENT_EVOLUTION_FILE):
        return Path(EVOLUTION_HISTORY_FILE)
    return status_path.with_name("forecast_evolution.jsonl")


def _read_history_ids(path: Path) -> set:
    if not path.exists():
        return set()
    ids = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("evolution_id"):
            ids.add(str(row["evolution_id"]))
    return ids


def _evolution_id(target: str, task_id: str, trigger_type: str) -> str:
    raw = f"{target}|{task_id}|{trigger_type}|{POLICY_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _quote_point(quote: Mapping[str, Any], *, elapsed_seconds=None) -> Dict[str, Any]:
    point = {
        "trade_time": str(quote.get("trade_time") or "").strip() or None,
        "price": _number(quote.get("price")),
        "change_pct": _number(quote.get("change_pct")),
        "amount": _number(quote.get("amount")),
        "source": quote.get("source"),
    }
    if elapsed_seconds is not None:
        point["trading_elapsed_seconds"] = int(elapsed_seconds)
    return point


def _quote_key(target: str, quote: Mapping[str, Any]) -> str:
    return "|".join([
        target,
        str(quote.get("trade_time") or ""),
        str(quote.get("price") or ""),
        str(quote.get("amount") or ""),
    ])


def _return_from(trigger_price: Optional[float], price: Optional[float]) -> Optional[float]:
    if trigger_price is None or trigger_price <= 0 or price is None:
        return None
    return price / trigger_price - 1.0


def _final_row(raw: Mapping[str, Any], *, finalized_at: str) -> Dict[str, Any]:
    trigger = dict(raw.get("trigger") or {})
    trigger_price = _number(trigger.get("price"))
    checkpoints = {
        key: dict(value)
        for key, value in (raw.get("checkpoints") or {}).items()
        if isinstance(value, dict)
    }
    last = dict(raw.get("last_quote") or {})
    last_seconds = _clock_seconds(last.get("trade_time"))
    if (
        "close" not in checkpoints
        and last_seconds is not None
        and last_seconds >= _clock_seconds(CLOSE_EARLIEST)
    ):
        checkpoints["close"] = {
            **last,
            "basis": "last_verified_intraday_quote",
        }
    for point in checkpoints.values():
        point["return_from_trigger"] = _return_from(
            trigger_price, _number(point.get("price")),
        )

    min_price = _number((raw.get("min_price") or {}).get("price"))
    max_price = _number((raw.get("max_price") or {}).get("price"))
    min_return = _return_from(trigger_price, min_price)
    max_return = _return_from(trigger_price, max_price)
    expectation = str(raw.get("expectation") or "unscored")
    if expectation == "positive":
        favourable = max_return
        adverse = min_return
    elif expectation == "non_positive":
        favourable = -min_return if min_return is not None else None
        adverse = -max_return if max_return is not None else None
    else:
        favourable = adverse = None

    quality = {
        "policy_version": POLICY_VERSION,
        "checkpoint_15m_available": "15m" in checkpoints,
        "checkpoint_30m_available": "30m" in checkpoints,
        "close_available": "close" in checkpoints,
    }
    quality["complete"] = all(
        quality[key]
        for key in (
            "checkpoint_15m_available",
            "checkpoint_30m_available",
            "close_available",
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "evolution_id": raw.get("evolution_id"),
        "target_trade_date": raw.get("target_trade_date"),
        "task_id": raw.get("task_id"),
        "code": raw.get("code"),
        "name": raw.get("name"),
        "plan_version": raw.get("plan_version"),
        "trigger_type": raw.get("trigger_type"),
        "expectation": expectation,
        "trigger": trigger,
        "checkpoints": checkpoints,
        "path": {
            "observation_count": int(raw.get("observation_count") or 0),
            "min_price": dict(raw.get("min_price") or {}),
            "max_price": dict(raw.get("max_price") or {}),
            "last_quote": last,
            "min_return_from_trigger": min_return,
            "max_return_from_trigger": max_return,
            "maximum_favourable_move": favourable,
            "maximum_adverse_move": adverse,
        },
        "quality": quality,
        "evaluation": {
            "user_execution_used": False,
            "official_eod_close_used": False,
        },
        "finalized_at": finalized_at,
    }


def _archive_state(state: Mapping[str, Any], history_path: Path, *, finalized_at=None):
    target = _trade_date_key(state.get("target_trade_date"))
    evolutions = state.get("evolutions") or {}
    if not target or not isinstance(evolutions, dict):
        return {"written": 0, "skipped": 0}
    existing = _read_history_ids(history_path)
    written = skipped = 0
    stamp = str(finalized_at or _now_iso())
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        for evolution_id, raw in sorted(evolutions.items()):
            if not isinstance(raw, dict):
                continue
            if evolution_id in existing:
                skipped += 1
                continue
            row = _final_row(raw, finalized_at=stamp)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            existing.add(evolution_id)
            written += 1
    return {"written": written, "skipped": skipped}


def start_trigger_evolution(task: Mapping[str, Any], trigger_type: str,
                            quote: Mapping[str, Any], *, forecast_ts=None,
                            status_path=None, history_path=None) -> Dict[str, Any]:
    path = Path(status_path or CURRENT_EVOLUTION_FILE)
    task_id = str(task.get("task_id") or "").strip()
    code = str(task.get("code") or quote.get("code") or "").strip()
    target = _trade_date_key(task.get("target_trade_date"))
    quote_date = _trade_date_key(quote.get("trade_date"))
    trade_time = str(quote.get("trade_time") or "").strip()
    price = _number(quote.get("price"))
    trigger_type = str(trigger_type or "").strip()
    if not task_id or not code or not target or not trigger_type:
        return {"status": "skipped", "reason": "trigger_identity_incomplete"}
    if quote_date != target:
        return {"status": "skipped", "reason": "quote_trade_date_mismatch"}
    if price is None or price <= 0:
        return {"status": "skipped", "reason": "quote_price_invalid"}
    if not _in_observation_session(trade_time):
        return {"status": "skipped", "reason": "quote_time_invalid"}

    state, error = _read_state(path)
    if error:
        return {"status": "error", "reason": "status_file_invalid", "detail": error}
    if state and _trade_date_key(state.get("target_trade_date")) != target:
        _archive_state(
            state, _history_path(path, history_path), finalized_at=forecast_ts,
        )
        state = {}
    evolutions = (state or {}).get("evolutions") or {}
    if not isinstance(evolutions, dict):
        return {"status": "error", "reason": "status_file_invalid_schema"}
    evolution_id = _evolution_id(target, task_id, trigger_type)
    if evolution_id in evolutions:
        return {"status": "duplicate", "evolution_id": evolution_id}

    point = _quote_point(quote, elapsed_seconds=0)
    raw = {
        "evolution_id": evolution_id,
        "target_trade_date": target,
        "task_id": task_id,
        "code": code,
        "name": task.get("name"),
        "plan_version": task.get("plan_version"),
        "trigger_type": trigger_type,
        "expectation": _expectation(trigger_type),
        "evaluation": {"user_execution_used": False},
        "trigger": {**point, "forecast_ts": forecast_ts},
        "checkpoints": {"trigger": dict(point)},
        "observation_count": 1,
        "min_price": {"price": price, "trade_time": trade_time},
        "max_price": {"price": price, "trade_time": trade_time},
        "last_quote": dict(point),
        "last_quote_key": _quote_key(target, quote),
    }
    updated = dict(evolutions)
    updated[evolution_id] = raw
    _write_state(path, {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "target_trade_date": target,
        "updated_at": str(forecast_ts or _now_iso()),
        "evolutions": updated,
    })
    return {"status": "written", "evolution_id": evolution_id}


def record_evolution_observation(task: Mapping[str, Any], quote: Mapping[str, Any], *,
                                 observed_at=None, status_path=None,
                                 history_path=None) -> Dict[str, Any]:
    path = Path(status_path or CURRENT_EVOLUTION_FILE)
    task_id = str(task.get("task_id") or "").strip()
    target = _trade_date_key(task.get("target_trade_date"))
    quote_date = _trade_date_key(quote.get("trade_date"))
    trade_time = str(quote.get("trade_time") or "").strip()
    price = _number(quote.get("price"))
    if not task_id or not target:
        return {"status": "skipped", "reason": "task_identity_incomplete"}
    if quote_date != target:
        return {"status": "skipped", "reason": "quote_trade_date_mismatch"}
    if price is None or price <= 0:
        return {"status": "skipped", "reason": "quote_price_invalid"}
    if not _in_observation_session(trade_time):
        return {"status": "skipped", "reason": "quote_outside_session"}

    state, error = _read_state(path)
    if error:
        return {"status": "error", "reason": "status_file_invalid", "detail": error}
    if not state:
        return {"status": "no_active", "written": 0}
    actual = _trade_date_key(state.get("target_trade_date"))
    if actual != target:
        _archive_state(
            state, _history_path(path, history_path), finalized_at=observed_at,
        )
        return {"status": "no_active", "written": 0, "archived_target": actual}
    evolutions = state.get("evolutions") or {}
    if not isinstance(evolutions, dict):
        return {"status": "error", "reason": "status_file_invalid_schema"}

    updated = dict(evolutions)
    written = duplicates = stale = 0
    quote_key = _quote_key(target, quote)
    for evolution_id, original in evolutions.items():
        if not isinstance(original, dict) or str(original.get("task_id")) != task_id:
            continue
        current = dict(original)
        if current.get("last_quote_key") == quote_key:
            duplicates += 1
            continue
        trigger = current.get("trigger") or {}
        elapsed = _trading_elapsed_seconds(trigger.get("trade_time"), trade_time)
        last_seconds = _clock_seconds((current.get("last_quote") or {}).get("trade_time"))
        current_seconds = _clock_seconds(trade_time)
        if elapsed is None or (
            last_seconds is not None and current_seconds is not None
            and current_seconds < last_seconds
        ):
            stale += 1
            continue

        point = _quote_point(quote, elapsed_seconds=elapsed)
        checkpoints = dict(current.get("checkpoints") or {})
        for label, threshold in CHECKPOINT_SECONDS.items():
            if label in checkpoints:
                continue
            if threshold <= elapsed <= threshold + CHECKPOINT_MAX_DELAY_SECONDS:
                checkpoints[label] = {
                    **point,
                    "scheduled_trading_elapsed_seconds": threshold,
                    "capture_delay_seconds": elapsed - threshold,
                }
        current["checkpoints"] = checkpoints
        current["observation_count"] = int(current.get("observation_count") or 0) + 1
        current["last_quote"] = point
        current["last_quote_key"] = quote_key
        min_point = dict(current.get("min_price") or {})
        max_point = dict(current.get("max_price") or {})
        if _number(min_point.get("price")) is None or price < _number(min_point.get("price")):
            current["min_price"] = {"price": price, "trade_time": trade_time}
        if _number(max_point.get("price")) is None or price > _number(max_point.get("price")):
            current["max_price"] = {"price": price, "trade_time": trade_time}
        updated[evolution_id] = current
        written += 1

    if written:
        _write_state(path, {
            **state,
            "updated_at": str(observed_at or _now_iso()),
            "evolutions": updated,
        })
    status = "written" if written else "duplicate" if duplicates else "stale" if stale else "no_active"
    return {
        "status": status,
        "written": written,
        "duplicates": duplicates,
        "stale": stale,
    }


def restore_active_evolutions(tasks: Iterable[Mapping[str, Any]], *,
                              forecasts_path=None, status_path=None,
                              history_path=None) -> Dict[str, int]:
    from vaxstock.services.forecast_recorder import load_dline_trigger_facts

    by_target = {}
    for task in tasks:
        target = _trade_date_key(task.get("target_trade_date"))
        if target:
            by_target.setdefault(target, []).append(task)
    written = duplicates = skipped = 0
    for target, target_tasks in by_target.items():
        facts = load_dline_trigger_facts(target, forecasts_path=forecasts_path)
        for task in target_tasks:
            task_id = str(task.get("task_id") or "")
            code = str(task.get("code") or "")
            for fact in facts.get(code) or []:
                if str(fact.get("task_id") or "") != task_id:
                    continue
                result = start_trigger_evolution(
                    task,
                    str(fact.get("trigger_type") or ""),
                    {
                        "code": code,
                        "trade_date": target,
                        "trade_time": fact.get("trade_time"),
                        "price": fact.get("price"),
                        "change_pct": fact.get("change_pct"),
                        "source": fact.get("source"),
                    },
                    forecast_ts=fact.get("forecast_ts"),
                    status_path=status_path,
                    history_path=history_path,
                )
                if result.get("status") == "written":
                    written += 1
                elif result.get("status") == "duplicate":
                    duplicates += 1
                else:
                    skipped += 1
    return {"written": written, "duplicates": duplicates, "skipped": skipped}


def finalize_evolutions(trade_date: str, *, status_path=None,
                        history_path=None, finalized_at=None) -> Dict[str, Any]:
    target = _trade_date_key(trade_date)
    path = Path(status_path or CURRENT_EVOLUTION_FILE)
    state, error = _read_state(path)
    if error:
        return {"status": "invalid", "written": 0, "detail": error}
    if not state:
        return {"status": "missing", "written": 0, "target_trade_date": target}
    actual = _trade_date_key(state.get("target_trade_date"))
    if not target or actual != target:
        return {
            "status": "target_mismatch",
            "written": 0,
            "target_trade_date": target,
            "observed_trade_date": actual,
        }
    stats = _archive_state(
        state,
        _history_path(path, history_path),
        finalized_at=finalized_at,
    )
    return {"status": "finalized", "target_trade_date": target, **stats}
