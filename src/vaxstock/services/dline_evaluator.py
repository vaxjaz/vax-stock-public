# -*- coding: utf-8 -*-
"""Backfill objective D-line outcomes without using user execution data."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from vaxstock import config
from vaxstock.services.eval_recorder import merge_result_rows
from vaxstock.services.forecast_recorder import DLINE_PLAN_VERSION
from vaxstock.services.observation_coverage import (
    OBSERVATION_HISTORY_FILE, OBSERVATION_STATUS_FILE,
    finalize_observation_coverage,
)

logger = logging.getLogger(__name__)

FORECAST_DIR = config.STATE_DIR / "forecast"
TASKS_FILE = FORECAST_DIR / "observation_tasks.jsonl"
FORECASTS_FILE = FORECAST_DIR / "forecasts.jsonl"
RESULTS_FILE = FORECAST_DIR / "forecast_results.jsonl"
SNAPSHOTS_FILE = config.STATE_DIR / "eval" / "factor_snapshots.jsonl"
FACTOR_RESULTS_FILE = config.STATE_DIR / "eval" / "factor_results.jsonl"

SCHEMA_VERSION = 1
POSITIVE_TRIGGER_TYPES = {
    "breakout_confirm", "reclaim_confirm", "panic_rebound_probe",
}
NON_POSITIVE_TRIGGER_TYPES = {
    "breakdown_confirm", "failed_breakout", "risk_off_confirm",
}
UNSCORED_TRIGGER_TYPES = {"weak_rebound", "noise_filter"}


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _trade_date_key(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return text
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        compact = text.replace("-", "")
        return compact if compact.isdigit() else None
    return None


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_jsonl(path) -> List[Dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    rows = []
    for line_no, raw in enumerate(
        source.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "D-line result source invalid JSON: path=%s line=%s",
                source, line_no,
            )
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _append_jsonl(path, row: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, default=str) + "\n")


def trigger_expectation(trigger_type: str) -> str:
    if trigger_type in POSITIVE_TRIGGER_TYPES:
        return "positive"
    if trigger_type in NON_POSITIVE_TRIGGER_TYPES:
        return "non_positive"
    return "unscored"


def dline_decision_hit(expectation: str, trigger_status: str,
                       outcome_return: Optional[float]) -> Optional[bool]:
    """Score both fired decisions and qualified no-fire filtering decisions."""
    if outcome_return is None or expectation == "unscored":
        return None
    if expectation == "positive":
        return outcome_return > 0 if trigger_status == "triggered" else outcome_return <= 0
    if expectation == "non_positive":
        return outcome_return <= 0 if trigger_status == "triggered" else outcome_return > 0
    return None


def _sample_id(task_id: str, blueprint_index: int,
               blueprint: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {
            "task_id": task_id,
            "blueprint_index": blueprint_index,
            "trigger_type": blueprint.get("trigger_type"),
            "condition": blueprint.get("condition"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _task_index(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for row in rows:
        task_id = str((row or {}).get("task_id") or "").strip()
        if task_id:
            out[task_id] = row
    return out


def _coverage_index(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for row in rows:
        task_id = str((row or {}).get("task_id") or "").strip()
        if task_id:
            out[task_id] = row
    return out


def _trigger_index(rows: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    ordered = sorted(rows, key=lambda row: str(row.get("forecast_ts") or ""))
    for row in ordered:
        inputs = (row or {}).get("inputs_ref") or {}
        structured = (row or {}).get("structured") or {}
        if structured.get("source") != "dline_task_blueprint":
            continue
        task_id = str(
            inputs.get("dline_task_id") or structured.get("task_id") or ""
        ).strip()
        blueprint = inputs.get("trigger_blueprint") or {}
        trigger_type = str(
            blueprint.get("trigger_type") or structured.get("trigger_type") or ""
        ).strip()
        plan_version = str(inputs.get("dline_plan_version") or "").strip()
        if not task_id or not trigger_type or plan_version != DLINE_PLAN_VERSION:
            continue
        key = (task_id, trigger_type)
        if key in out:
            continue
        quote = inputs.get("quote_snapshot") or {}
        out[key] = {
            "forecast_ts": row.get("forecast_ts"),
            "trade_date": _trade_date_key(row.get("trade_date")),
            "trade_time": quote.get("trade_time"),
            "price": _number(quote.get("price")),
            "change_pct": _number(quote.get("change_pct")),
            "source": quote.get("source"),
        }
    return out


def _snapshot_index(rows: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out = {}
    for row in rows:
        trade_date = _trade_date_key((row or {}).get("trade_date"))
        code = str((row or {}).get("code") or "").strip()
        if trade_date and code:
            out[(trade_date, code)] = row
    return out


def _existing_result_keys(rows: Iterable[Dict[str, Any]]) -> set:
    return {
        (str(row.get("sample_id") or ""), str(row.get("horizon") or ""))
        for row in rows
        if row.get("sample_id") is not None and row.get("horizon") is not None
    }


def _coverage_status(coverage: Optional[Mapping[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    if not coverage:
        return "coverage_missing", {}
    quality = dict(coverage.get("quality") or {})
    return (
        "qualified_not_triggered" if quality.get("qualified")
        else "coverage_incomplete",
        quality,
    )


def _result_row(*, task: Mapping[str, Any], blueprint: Mapping[str, Any],
                blueprint_index: int, sample_id: str, trigger: Optional[Mapping[str, Any]],
                coverage: Optional[Mapping[str, Any]], horizon: str,
                horizon_trade_date: str, target_close: float,
                ret_from_target_close: Optional[float], filled_at: str) -> Optional[Dict[str, Any]]:
    trigger_status, quality = _coverage_status(coverage)
    if trigger:
        trigger_status = "triggered"
    if trigger_status not in {"triggered", "qualified_not_triggered"}:
        return None

    trigger_price = _number((trigger or {}).get("price"))
    ret_from_trigger = None
    if trigger_price and trigger_price > 0:
        horizon_price = target_close
        if ret_from_target_close is not None:
            horizon_price = target_close * (1.0 + ret_from_target_close)
        ret_from_trigger = horizon_price / trigger_price - 1.0

    if trigger_status == "triggered":
        outcome_return = ret_from_trigger
        outcome_basis = "first_trigger_price"
    else:
        outcome_return = ret_from_target_close
        outcome_basis = "target_eod_close"

    expectation = trigger_expectation(str(blueprint.get("trigger_type") or ""))
    c_prediction = (
        (((task.get("evidence_pack") or {}).get("C_prediction") or {}).get("prediction"))
        or {}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "sample_id": sample_id,
        "task_id": task.get("task_id"),
        "code": task.get("code"),
        "name": task.get("name"),
        "baseline_trade_date": _trade_date_key(task.get("baseline_trade_date")),
        "target_trade_date": _trade_date_key(task.get("target_trade_date")),
        "plan_version": task.get("plan_version"),
        "blueprint_index": blueprint_index,
        "trigger_type": blueprint.get("trigger_type"),
        "severity": blueprint.get("severity"),
        "expectation": expectation,
        "horizon": str(horizon),
        "horizon_trade_date": _trade_date_key(horizon_trade_date),
        "trigger": {
            "status": trigger_status,
            "forecast_ts": (trigger or {}).get("forecast_ts"),
            "trade_time": (trigger or {}).get("trade_time"),
            "price": trigger_price,
            "change_pct": (trigger or {}).get("change_pct"),
        },
        "coverage": {
            "coverage_id": (coverage or {}).get("coverage_id"),
            "quality": quality,
        },
        "c_line": {
            "rule_version": c_prediction.get("rule_version"),
            "action": c_prediction.get("action"),
            "direction": c_prediction.get("direction"),
            "confidence": c_prediction.get("confidence"),
        },
        "outcome": {
            "source": "factor_snapshots+factor_results",
            "target_eod_close": target_close,
            "ret_from_target_close": ret_from_target_close,
            "ret_from_trigger": ret_from_trigger,
            "evaluation_return": outcome_return,
            "evaluation_basis": outcome_basis,
        },
        "evaluation": {
            "classifier_hit_basis": "target_eod_close_stock_return_sign",
            "classifier_hit": dline_decision_hit(
                expectation, trigger_status, ret_from_target_close,
            ),
            "timing_hit_basis": "first_trigger_price_stock_return_sign",
            "timing_hit": (
                dline_decision_hit(expectation, trigger_status, outcome_return)
                if trigger_status == "triggered" else None
            ),
            "decision_hit": dline_decision_hit(
                expectation, trigger_status, ret_from_target_close,
            ),
            "user_execution_used": False,
        },
        "filled_at": filled_at,
    }


def build_dline_results(*, tasks: Iterable[Dict[str, Any]],
                        forecasts: Iterable[Dict[str, Any]],
                        coverage_rows: Iterable[Dict[str, Any]],
                        snapshots: Iterable[Dict[str, Any]],
                        factor_results: Iterable[Dict[str, Any]],
                        existing_results: Iterable[Dict[str, Any]] = (),
                        filled_at: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    task_idx = _task_index(tasks)
    coverage_idx = _coverage_index(coverage_rows)
    trigger_idx = _trigger_index(forecasts)
    snapshot_idx = _snapshot_index(snapshots)
    factor_idx = merge_result_rows(factor_results)
    existing = _existing_result_keys(existing_results)
    now = filled_at or _now_iso()
    new_rows: List[Dict[str, Any]] = []
    stats = {
        "tasks": len(task_idx), "blueprints": 0, "generated": 0,
        "skipped_existing": 0, "pending_outcome": 0,
        "coverage_missing": 0,
    }

    for task_id, task in sorted(task_idx.items()):
        target = _trade_date_key(task.get("target_trade_date"))
        code = str(task.get("code") or "").strip()
        snapshot = snapshot_idx.get((target, code)) if target and code else None
        target_close = _number((snapshot or {}).get("price_at_snapshot"))
        factor = factor_idx.get((target, code), {}) if target and code else {}
        coverage = coverage_idx.get(task_id)
        blueprints = ((task.get("observation") or {}).get("trigger_blueprints") or [])
        for blueprint_index, blueprint in enumerate(blueprints):
            if not isinstance(blueprint, dict):
                continue
            stats["blueprints"] += 1
            trigger_type = str(blueprint.get("trigger_type") or "").strip()
            trigger = trigger_idx.get((task_id, trigger_type))
            if not trigger and not ((coverage or {}).get("quality") or {}).get("qualified"):
                stats["coverage_missing"] += 1
                continue
            if target_close is None or target_close <= 0:
                stats["pending_outcome"] += 1
                continue

            sample_id = _sample_id(task_id, blueprint_index, blueprint)
            candidates = []
            if trigger:
                candidates.append(("0", target, None))
            for horizon, value in sorted(
                (factor.get("ret") or {}).items(),
                key=lambda item: int(item[0]) if str(item[0]).isdigit() else 10**9,
            ):
                ret = _number(value)
                horizon_date = (factor.get("horizon_trade_dates") or {}).get(str(horizon))
                if ret is not None and _trade_date_key(horizon_date):
                    candidates.append((str(horizon), str(horizon_date), ret))
            if not candidates:
                stats["pending_outcome"] += 1
                continue

            for horizon, horizon_date, ret in candidates:
                key = (sample_id, horizon)
                if key in existing:
                    stats["skipped_existing"] += 1
                    continue
                row = _result_row(
                    task=task,
                    blueprint=blueprint,
                    blueprint_index=blueprint_index,
                    sample_id=sample_id,
                    trigger=trigger,
                    coverage=coverage,
                    horizon=horizon,
                    horizon_trade_date=horizon_date,
                    target_close=target_close,
                    ret_from_target_close=ret,
                    filled_at=now,
                )
                if row is not None:
                    new_rows.append(row)
                    existing.add(key)
                    stats["generated"] += 1
    return new_rows, stats


def backfill_dline_results(*, as_of_trade_date=None, tasks_path=None,
                           forecasts_path=None, coverage_path=None,
                           observation_status_path=None, snapshots_path=None,
                           factor_results_path=None, results_path=None,
                           filled_at=None) -> Dict[str, Any]:
    if as_of_trade_date:
        finalization = finalize_observation_coverage(
            as_of_trade_date,
            status_path=observation_status_path or OBSERVATION_STATUS_FILE,
            history_path=coverage_path or OBSERVATION_HISTORY_FILE,
            finalized_at=filled_at,
        )
    else:
        finalization = {"status": "not_requested", "written": 0}

    target = Path(results_path or RESULTS_FILE)
    existing = _read_jsonl(target)
    rows, stats = build_dline_results(
        tasks=_read_jsonl(tasks_path or TASKS_FILE),
        forecasts=_read_jsonl(forecasts_path or FORECASTS_FILE),
        coverage_rows=_read_jsonl(coverage_path or OBSERVATION_HISTORY_FILE),
        snapshots=_read_jsonl(snapshots_path or SNAPSHOTS_FILE),
        factor_results=_read_jsonl(factor_results_path or FACTOR_RESULTS_FILE),
        existing_results=existing,
        filled_at=filled_at,
    )
    for row in rows:
        _append_jsonl(target, row)
    return {
        "status": "written" if rows else "no_change",
        "written": len(rows),
        "existing": len(existing),
        "coverage_finalization": finalization,
        **stats,
    }
