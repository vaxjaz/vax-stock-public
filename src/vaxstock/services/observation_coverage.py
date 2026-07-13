# -*- coding: utf-8 -*-
"""Runtime evidence that D-line tasks received verified same-session quotes."""

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Optional

from vaxstock import config


OBSERVATION_STATUS_FILE = config.STATE_DIR / "forecast" / "current_observation_status.json"
SCHEMA_VERSION = 1


def _trade_date_key(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    for pattern in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, pattern).strftime("%Y%m%d")
        except ValueError:
            continue
    return None


def _observed_at(value=None) -> str:
    if isinstance(value, dt.datetime):
        return value.isoformat(timespec="seconds")
    text = str(value or "").strip()
    if text:
        dt.datetime.fromisoformat(text)
        return text
    return dt.datetime.now().isoformat(timespec="seconds")


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


def _write_state(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def record_task_observation(task: Dict[str, Any], quote: Dict[str, Any], *,
                            observed_at=None, status_path=None) -> Dict[str, Any]:
    path = Path(status_path or OBSERVATION_STATUS_FILE)
    task_id = str(task.get("task_id") or "").strip()
    code = str(task.get("code") or "").strip()
    target = _trade_date_key(task.get("target_trade_date"))
    quote_date = _trade_date_key(quote.get("trade_date"))
    price = quote.get("price")
    if not task_id or not code or not target:
        return {"status": "skipped", "reason": "task_identity_incomplete"}
    if quote_date != target:
        return {
            "status": "skipped", "reason": "quote_trade_date_mismatch",
            "target_trade_date": target, "quote_trade_date": quote_date,
        }
    try:
        price_value = float(price)
    except (TypeError, ValueError):
        return {"status": "skipped", "reason": "quote_price_invalid"}
    try:
        observed = _observed_at(observed_at)
    except ValueError:
        return {"status": "skipped", "reason": "observed_at_invalid"}

    state, error = _read_state(path)
    if error:
        return {"status": "error", "reason": "status_file_invalid", "detail": error}
    if state and _trade_date_key(state.get("target_trade_date")) != target:
        state = {}
    raw_tasks = (state or {}).get("tasks")
    if raw_tasks is None:
        raw_tasks = {}
    if not isinstance(raw_tasks, dict):
        return {"status": "error", "reason": "status_file_invalid_schema", "detail": "tasks_not_object"}
    tasks = dict(raw_tasks)
    raw_current = tasks.get(task_id)
    if raw_current is None:
        raw_current = {}
    if not isinstance(raw_current, dict):
        return {"status": "error", "reason": "status_file_invalid_schema", "detail": "task_not_object"}
    current = dict(raw_current)
    quote_time = str(quote.get("trade_time") or "").strip() or None
    observation_key = "|".join([
        task_id, observed, quote_date,
        str(quote_time or ""), str(price), str(quote.get("amount") or ""),
    ])
    if current.get("last_observation_key") == observation_key:
        return {"status": "duplicate", "task_id": task_id, "code": code}

    count = int(current.get("observation_count") or 0) + 1
    tasks[task_id] = {
        "task_id": task_id,
        "code": code,
        "target_trade_date": target,
        "first_observed_at": current.get("first_observed_at") or observed,
        "last_observed_at": observed,
        "observation_count": count,
        "first_quote_trade_time": current.get("first_quote_trade_time") or quote_time,
        "last_quote_trade_time": quote_time,
        "last_price": price_value,
        "last_change_pct": quote.get("change_pct"),
        "last_quote_source": quote.get("source"),
        "last_observation_key": observation_key,
    }
    _write_state(path, {
        "schema_version": SCHEMA_VERSION,
        "target_trade_date": target,
        "updated_at": observed,
        "tasks": tasks,
    })
    return {"status": "written", "task_id": task_id, "code": code, "observation_count": count}


def load_observation_coverage(trade_date: str, *, status_path=None) -> Dict[str, Any]:
    target = _trade_date_key(trade_date)
    if not target:
        return {"status": "invalid_target", "target_trade_date": None, "by_code": {}}
    path = Path(status_path or OBSERVATION_STATUS_FILE)
    state, error = _read_state(path)
    if error:
        return {"status": "invalid", "target_trade_date": target, "by_code": {}, "detail": error}
    if not state:
        return {"status": "missing", "target_trade_date": target, "by_code": {}}
    actual = _trade_date_key(state.get("target_trade_date"))
    if actual != target:
        return {
            "status": "target_mismatch", "target_trade_date": target,
            "observed_trade_date": actual, "by_code": {},
        }
    raw_tasks = state.get("tasks")
    if raw_tasks is None:
        raw_tasks = {}
    if not isinstance(raw_tasks, dict):
        return {
            "status": "invalid", "target_trade_date": target,
            "by_code": {}, "detail": "tasks_not_object",
        }
    by_code: Dict[str, list] = {}
    for row in raw_tasks.values():
        if not isinstance(row, dict) or _trade_date_key(row.get("target_trade_date")) != target:
            continue
        code = str(row.get("code") or "").strip()
        if code:
            by_code.setdefault(code, []).append(dict(row))
    return {"status": "available", "target_trade_date": target, "by_code": by_code}
