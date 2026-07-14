# -*- coding: utf-8 -*-
"""Runtime evidence that D-line tasks received verified same-session quotes."""

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from vaxstock import config


OBSERVATION_STATUS_FILE = config.STATE_DIR / "forecast" / "current_observation_status.json"
OBSERVATION_HISTORY_FILE = config.STATE_DIR / "forecast" / "observation_coverage.jsonl"
SCHEMA_VERSION = 2
COVERAGE_POLICY_VERSION = "d_full_session_v1"
MIN_SESSION_OBSERVATIONS = 15
OPENING_DEADLINE = "09:40:00"
MORNING_END_EARLIEST = "11:20:00"
AFTERNOON_START_DEADLINE = "13:15:00"
CLOSING_EARLIEST = "14:50:00"
MAX_SESSION_GAP_SECONDS = 30 * 60


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


def _history_path(status_path: Path, history_path=None) -> Path:
    if history_path is not None:
        return Path(history_path)
    if status_path == Path(OBSERVATION_STATUS_FILE):
        return Path(OBSERVATION_HISTORY_FILE)
    return status_path.with_name("observation_coverage.jsonl")


def _clock_seconds(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    try:
        parsed = dt.datetime.strptime(text, "%H:%M:%S").time()
    except ValueError:
        return None
    return parsed.hour * 3600 + parsed.minute * 60 + parsed.second


def _session_name(quote_time: Any) -> Optional[str]:
    seconds = _clock_seconds(quote_time)
    if seconds is None:
        return None
    if _clock_seconds("09:25:00") <= seconds <= _clock_seconds("11:32:00"):
        return "morning"
    if _clock_seconds("13:00:00") <= seconds <= _clock_seconds("15:02:00"):
        return "afternoon"
    return None


def assess_observation_coverage(row: Dict[str, Any]) -> Dict[str, Any]:
    """Classify whether a no-trigger task had auditable full-session coverage."""
    morning_count = int(row.get("morning_observation_count") or 0)
    afternoon_count = int(row.get("afternoon_observation_count") or 0)
    first_morning = _clock_seconds(row.get("first_morning_quote_time"))
    last_morning = _clock_seconds(row.get("last_morning_quote_time"))
    first_afternoon = _clock_seconds(row.get("first_afternoon_quote_time"))
    last_afternoon = _clock_seconds(row.get("last_afternoon_quote_time"))
    max_morning_gap = row.get("max_morning_gap_seconds")
    max_afternoon_gap = row.get("max_afternoon_gap_seconds")
    checks = {
        "morning_count": morning_count >= MIN_SESSION_OBSERVATIONS,
        "afternoon_count": afternoon_count >= MIN_SESSION_OBSERVATIONS,
        "opening_seen": (
            first_morning is not None
            and first_morning <= _clock_seconds(OPENING_DEADLINE)
        ),
        "morning_end_seen": (
            last_morning is not None
            and last_morning >= _clock_seconds(MORNING_END_EARLIEST)
        ),
        "afternoon_start_seen": (
            first_afternoon is not None
            and first_afternoon <= _clock_seconds(AFTERNOON_START_DEADLINE)
        ),
        "closing_seen": (
            last_afternoon is not None
            and last_afternoon >= _clock_seconds(CLOSING_EARLIEST)
        ),
        "morning_gap": (
            max_morning_gap is not None
            and float(max_morning_gap) <= MAX_SESSION_GAP_SECONDS
        ),
        "afternoon_gap": (
            max_afternoon_gap is not None
            and float(max_afternoon_gap) <= MAX_SESSION_GAP_SECONDS
        ),
    }
    return {
        "policy_version": COVERAGE_POLICY_VERSION,
        "qualified": all(checks.values()),
        "checks": checks,
        "thresholds": {
            "minimum_observations_per_session": MIN_SESSION_OBSERVATIONS,
            "opening_deadline": OPENING_DEADLINE,
            "morning_end_earliest": MORNING_END_EARLIEST,
            "afternoon_start_deadline": AFTERNOON_START_DEADLINE,
            "closing_earliest": CLOSING_EARLIEST,
            "maximum_in_session_gap_seconds": MAX_SESSION_GAP_SECONDS,
        },
    }


def _read_history_ids(path: Path) -> set:
    if not path.exists():
        return set()
    out = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("coverage_id"):
            out.add(str(row["coverage_id"]))
    return out


def _archive_state(state: Dict[str, Any], history_path: Path, *, finalized_at=None) -> Dict[str, int]:
    target = _trade_date_key(state.get("target_trade_date"))
    tasks = state.get("tasks") or {}
    if not target or not isinstance(tasks, dict):
        return {"written": 0, "skipped": 0}
    existing = _read_history_ids(history_path)
    written = skipped = 0
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        for task_id, raw in sorted(tasks.items()):
            if not isinstance(raw, dict):
                continue
            coverage_id = hashlib.sha256(
                f"{target}|{task_id}|{COVERAGE_POLICY_VERSION}".encode("utf-8")
            ).hexdigest()
            if coverage_id in existing:
                skipped += 1
                continue
            row = {
                "schema_version": SCHEMA_VERSION,
                "coverage_id": coverage_id,
                "target_trade_date": target,
                "task_id": str(task_id),
                "code": str(raw.get("code") or ""),
                "finalized_at": str(
                    finalized_at or dt.datetime.now().isoformat(timespec="seconds")
                ),
                "observation": dict(raw),
                "quality": assess_observation_coverage(raw),
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            existing.add(coverage_id)
            written += 1
    return {"written": written, "skipped": skipped}


def finalize_observation_coverage(trade_date: str, *, status_path=None,
                                  history_path=None, finalized_at=None) -> Dict[str, Any]:
    """Freeze current runtime coverage into append-only per-task history."""
    target = _trade_date_key(trade_date)
    path = Path(status_path or OBSERVATION_STATUS_FILE)
    state, error = _read_state(path)
    if error:
        return {"status": "invalid", "written": 0, "detail": error}
    if not state:
        return {"status": "missing", "written": 0, "target_trade_date": target}
    actual = _trade_date_key(state.get("target_trade_date"))
    if not target or actual != target:
        return {
            "status": "target_mismatch", "written": 0,
            "target_trade_date": target, "observed_trade_date": actual,
        }
    stats = _archive_state(
        state, _history_path(path, history_path), finalized_at=finalized_at,
    )
    return {"status": "finalized", "target_trade_date": target, **stats}


def record_task_observation(task: Dict[str, Any], quote: Dict[str, Any], *,
                            observed_at=None, status_path=None,
                            history_path=None) -> Dict[str, Any]:
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
        _archive_state(state, _history_path(path, history_path), finalized_at=observed)
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
        task_id, quote_date, str(quote_time or ""),
        str(price), str(quote.get("amount") or ""),
    ])
    if current.get("last_observation_key") == observation_key:
        return {"status": "duplicate", "task_id": task_id, "code": code}

    count = int(current.get("observation_count") or 0) + 1
    updated = {
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
    session = _session_name(quote_time)
    for name in ("morning", "afternoon"):
        updated[f"{name}_observation_count"] = int(
            current.get(f"{name}_observation_count") or 0
        )
        updated[f"first_{name}_quote_time"] = current.get(
            f"first_{name}_quote_time"
        )
        updated[f"last_{name}_quote_time"] = current.get(
            f"last_{name}_quote_time"
        )
        updated[f"max_{name}_gap_seconds"] = current.get(
            f"max_{name}_gap_seconds"
        )
    if session:
        previous_seconds = _clock_seconds(current.get(f"last_{session}_quote_time"))
        current_seconds = _clock_seconds(quote_time)
        gap = (
            current_seconds - previous_seconds
            if previous_seconds is not None and current_seconds is not None
            else 0
        )
        updated[f"{session}_observation_count"] += 1
        updated[f"first_{session}_quote_time"] = (
            current.get(f"first_{session}_quote_time") or quote_time
        )
        updated[f"last_{session}_quote_time"] = quote_time
        updated[f"max_{session}_gap_seconds"] = max(
            int(current.get(f"max_{session}_gap_seconds") or 0),
            max(0, gap),
        )
    tasks[task_id] = updated
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
            item = dict(row)
            item["quality"] = assess_observation_coverage(item)
            by_code.setdefault(code, []).append(item)
    return {"status": "available", "target_trade_date": target, "by_code": by_code}
