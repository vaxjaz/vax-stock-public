# -*- coding: utf-8 -*-
"""D line observation planner.

The D line is the intraday observation/alert layer that validates C-line
EOD predictions with live behavior.  This module builds an extensible
evidence pack for Codex from A/B/C data, asks Codex for next-session
observation tasks, validates the returned trigger DSL, and records tasks as
append-only history.

No network calls happen at import time.  Codex is called only by
``generate_observation_tasks`` when the caller does not inject a planner
function for tests/replay.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from vaxstock import config

logger = logging.getLogger(__name__)

FORECAST_DIR = config.STATE_DIR / "forecast"
OBSERVATION_TASKS_FILE = FORECAST_DIR / "observation_tasks.jsonl"
CURRENT_TASKS_FILE = FORECAST_DIR / "current_tasks.json"
PLAN_PROMPT_FILE = config.PROJECT_ROOT / "deploy" / "d_observation_plan_prompt.md"

SCHEMA_VERSION = 1
EVIDENCE_SCHEMA_VERSION = 1
DEFAULT_PLAN_VERSION = "d_observe_llm_v1"
DEFAULT_SOURCE = "codex_llm"

ALLOWED_TRIGGER_FIELDS = {
    "price",
    "change_pct",
    "amplitude_pct",
    "amount_yi",
    "price_vs_ma5_pct",
    "price_vs_ma10_pct",
    "price_vs_ma20_pct",
    "price_vs_ma60_pct",
    "volume_ratio_5d",
    "position_20d_pct",
    "position_52w_pct",
    "recent_5d_change_pct",
    "recent_20d_change_pct",
    "macd_hist",
    "rsi_14",
}
ALLOWED_OPS = {"<", "<=", ">", ">=", "==", "!="}
ALLOWED_TRIGGER_TYPES = {
    "breakdown_confirm",
    "breakout_confirm",
    "reclaim_confirm",
    "weak_rebound",
    "failed_breakout",
    "panic_rebound_probe",
    "risk_off_confirm",
    "noise_filter",
}
ALLOWED_SEVERITY = {"low", "medium", "high"}


def _now_iso() -> str:
    """Generation timestamp only; never a trade-date anchor."""
    return dt.datetime.now().isoformat(timespec="seconds")


def _read_jsonl(path) -> List[dict]:
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                logger.warning(f"D line jsonl 行解析失败,跳过: {line[:80]}")
    return rows


def _append_jsonl(path, row) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _write_json(path, obj) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compact_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "right_side_score",
        "right_side_grade",
        "position_20d_pct",
        "position_52w_pct",
        "main_inflow_10d",
        "main_inflow_10d_yuan",
        "np_yoy",
        "holder_change_pct",
        "pe_percentile",
        "pb_percentile",
        "turnover_z",
        "ma5",
        "ma10",
        "ma20",
        "ma60",
        "price_vs_ma5_pct",
        "price_vs_ma20_pct",
        "price_vs_ma60_pct",
        "volume_ratio_5d",
        "recent_5d_change_pct",
        "recent_20d_change_pct",
        "macd_hist",
        "rsi_14",
    ]
    return {k: metrics.get(k) for k in keys if k in metrics}


def _compact_market(payload: Dict[str, Any]) -> Dict[str, Any]:
    overview = payload.get("market_overview") or {}
    macro = payload.get("macro") or {}
    tracks = payload.get("tracks") or []
    ai_track = None
    if tracks:
        first = tracks[0] or {}
        ai_track = {
            "track_name": first.get("track_name"),
            "available": first.get("available"),
            "position_ceiling": first.get("position_ceiling"),
            "summary_lines": first.get("summary_lines"),
        }
    return {
        "market_regime": payload.get("market_regime"),
        "macro_regime": macro.get("macro_regime"),
        "trade_date": overview.get("trade_date"),
        "breadth": {
            "up_count": overview.get("up_count"),
            "down_count": overview.get("down_count"),
            "limit_up_count": overview.get("limit_up_count"),
            "limit_down_count": overview.get("limit_down_count"),
        },
        "ai_track": ai_track,
    }


def _prediction_index(c_predictions: Optional[Iterable[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for pred in c_predictions or []:
        if not isinstance(pred, dict):
            continue
        code = str(pred.get("code") or "").strip()
        if code:
            idx[code] = pred
    return idx


def _factor_history_index(rows: Optional[Iterable[Dict[str, Any]]], limit: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    """Build compact B-line history by code from factor_results rows."""
    by_code: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip()
        td = str(row.get("trade_date") or "").strip()
        if not (code and td):
            continue
        by_code.setdefault(code, []).append({
            "trade_date": td,
            "ret": row.get("ret") or {},
            "mkt_ret": row.get("mkt_ret") or {},
            "excess": row.get("excess") or {},
            "complete": row.get("complete"),
        })
    out = {}
    for code, vals in by_code.items():
        out[code] = sorted(vals, key=lambda r: r["trade_date"])[-limit:]
    return out


def _load_factor_results() -> List[dict]:
    try:
        from vaxstock.services.eval_recorder import RESULTS_FILE
    except Exception:
        return []
    return _read_jsonl(RESULTS_FILE)


def _load_prompt() -> str:
    try:
        return PLAN_PROMPT_FILE.read_text(encoding="utf-8")
    except Exception:
        return (
            "你是D线盘中观察任务生成器。基于A/B/C定稿证据,为次日盘中生成客观观察任务。"
            "只输出JSON,不要输出买卖价、止损价、目标价,不要臆测盘中资金。"
        )


def build_observation_evidence(payload: Dict[str, Any], target_trade_date: str, *,
                               c_predictions: Optional[Iterable[Dict[str, Any]]] = None,
                               factor_results: Optional[Iterable[Dict[str, Any]]] = None,
                               generated_at: Optional[str] = None) -> List[Dict[str, Any]]:
    """Build per-stock D-line evidence packs from A/B/C data.

    A-line evidence comes from the current EOD payload. B-line evidence is a
    compact recent factor-result history. C-line evidence is the freshly
    generated EOD prediction for the target trade date.
    """
    baseline = str(((payload or {}).get("market_overview") or {}).get("trade_date") or "").strip()
    target = str(target_trade_date or "").strip()
    if not (baseline and target):
        return []

    pred_idx = _prediction_index(c_predictions)
    factor_idx = _factor_history_index(factor_results if factor_results is not None else _load_factor_results())
    market = _compact_market(payload)
    ts = generated_at or _now_iso()
    evidences: List[Dict[str, Any]] = []

    for item in (payload or {}).get("stocks") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        rt = item.get("realtime") or {}
        metrics = item.get("metrics") or {}
        evidence = {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "line": "D",
            "purpose": "validate_c_line_with_intraday_observation",
            "generated_at": ts,
            "baseline_trade_date": baseline,
            "target_trade_date": target,
            "stock": {
                "code": code,
                "name": rt.get("name") or item.get("configured_name"),
                "group": item.get("group"),
                "concepts": list(item.get("concepts") or []),
            },
            "A_eod": {
                "price": rt.get("price"),
                "metrics": _compact_metrics(metrics),
                "market": market,
            },
            "B_factor_history": factor_idx.get(code, []),
            "C_prediction": pred_idx.get(code),
            "D_contract": {
                "allowed_trigger_fields": sorted(ALLOWED_TRIGGER_FIELDS),
                "allowed_ops": sorted(ALLOWED_OPS),
                "allowed_trigger_types": sorted(ALLOWED_TRIGGER_TYPES),
                "forbidden_outputs": [
                    "intraday_new_score",
                    "buy_sell_price_instruction",
                    "fabricated_fund_flow",
                ],
                "notification_role": "objective_evaluation_for_user_decision",
            },
        }
        evidences.append(evidence)
    return evidences


def _parse_llm_json(raw) -> Optional[dict]:
    if isinstance(raw, dict):
        return raw
    if not raw or not isinstance(raw, str):
        return None
    txt = raw.strip()
    i, j = txt.find("{"), txt.rfind("}")
    if i == -1 or j == -1 or j < i:
        return None
    try:
        obj = json.loads(txt[i:j + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _normalize_clause(clause: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(clause, dict):
        return None
    field = str(clause.get("field") or "").strip()
    op = str(clause.get("op") or "").strip()
    if field not in ALLOWED_TRIGGER_FIELDS or op not in ALLOWED_OPS:
        return None
    value = clause.get("value")
    num = _to_float(value)
    return {
        "field": field,
        "op": op,
        "value": num if num is not None else value,
    }


def _normalize_condition(condition: Dict[str, Any]) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    if not isinstance(condition, dict):
        return None
    out: Dict[str, List[Dict[str, Any]]] = {}
    for key in ("all", "any"):
        vals = condition.get(key) or []
        if not isinstance(vals, list):
            continue
        clean = []
        for clause in vals:
            norm = _normalize_clause(clause)
            if norm:
                clean.append(norm)
        if clean:
            out[key] = clean
    return out or None


def _normalize_trigger(trigger: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(trigger, dict):
        return None
    ttype = str(trigger.get("trigger_type") or "").strip()
    if ttype not in ALLOWED_TRIGGER_TYPES:
        return None
    condition = _normalize_condition(trigger.get("condition") or {})
    if not condition:
        return None
    severity = str(trigger.get("severity") or "medium").strip()
    if severity not in ALLOWED_SEVERITY:
        severity = "medium"
    return {
        "trigger_type": ttype,
        "severity": severity,
        "condition": condition,
        "why": str(trigger.get("why") or "").strip(),
        "expected_feedback_to_c": str(trigger.get("expected_feedback_to_c") or "").strip(),
    }


def make_task_id(baseline_trade_date: str, target_trade_date: str, code: str,
                 plan_version: str = DEFAULT_PLAN_VERSION) -> str:
    return "_".join([str(baseline_trade_date), str(target_trade_date), str(code), str(plan_version)])


def task_from_llm_plan(evidence: Dict[str, Any], llm_plan: Dict[str, Any], *,
                       plan_version: str = DEFAULT_PLAN_VERSION,
                       created_at: Optional[str] = None,
                       source: str = DEFAULT_SOURCE) -> Optional[Dict[str, Any]]:
    """Validate a Codex plan and convert it into a D-line observation task."""
    plan = _parse_llm_json(llm_plan)
    if not plan:
        return None
    triggers = []
    for trig in plan.get("trigger_blueprints") or []:
        norm = _normalize_trigger(trig)
        if norm:
            triggers.append(norm)
    if not triggers:
        return None

    stock = evidence.get("stock") or {}
    baseline = str(evidence.get("baseline_trade_date") or "").strip()
    target = str(evidence.get("target_trade_date") or "").strip()
    code = str(stock.get("code") or "").strip()
    if not (baseline and target and code):
        return None

    watch_points = plan.get("watch_points") or []
    if not isinstance(watch_points, list):
        watch_points = []
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": make_task_id(baseline, target, code, plan_version=plan_version),
        "line": "D",
        "created_at": created_at or _now_iso(),
        "source": source,
        "plan_version": plan_version,
        "baseline_trade_date": baseline,
        "target_trade_date": target,
        "code": code,
        "name": stock.get("name"),
        "group": stock.get("group"),
        "concepts": list(stock.get("concepts") or []),
        "status": "active",
        "evidence_pack": evidence,
        "observation": {
            "observe_intent": str(plan.get("observe_intent") or "").strip(),
            "primary_risk": str(plan.get("primary_risk") or "").strip(),
            "watch_points": watch_points,
            "trigger_blueprints": triggers,
            "c_line_feedback_focus": str(plan.get("c_line_feedback_focus") or "").strip(),
            "falsify_if": str(plan.get("falsify_if") or "").strip(),
        },
    }


def _call_codex_for_plan(evidence: Dict[str, Any]) -> Optional[str]:
    s = config.SECRETS
    if not (s.get("codex_enabled", True) and s.get("codex_url") and s.get("codex_model") and s.get("codex_token")):
        logger.warning("D线观察计划: Codex 配置缺失,跳过 LLM 任务生成")
        return None
    from vaxstock.sources.codex import call_codex
    user_msg = (
        "请基于以下 A/B/C 证据生成单只股票的 D线次日盘中观察任务 JSON。\n"
        "JSON 必须符合 system prompt 的 schema,不得输出 markdown。\n\n"
        f"{json.dumps(evidence, ensure_ascii=False, default=str)}"
    )
    return call_codex(
        _load_prompt(),
        user_msg,
        url=s.get("codex_url"),
        model=s.get("codex_model"),
        token=s.get("codex_token"),
        timeout=int(s.get("codex_timeout", 30)),
    )


def generate_observation_tasks(payload: Dict[str, Any], target_trade_date: str, *,
                               c_predictions: Optional[Iterable[Dict[str, Any]]] = None,
                               factor_results: Optional[Iterable[Dict[str, Any]]] = None,
                               planner_func: Optional[Callable[[Dict[str, Any]], Any]] = None,
                               plan_version: str = DEFAULT_PLAN_VERSION,
                               generated_at: Optional[str] = None) -> List[Dict[str, Any]]:
    """Generate D-line observation tasks from A/B/C evidence.

    ``planner_func`` is a seam for tests/replay.  When omitted, Codex is called
    via the configured local OpenAI-compatible endpoint.
    """
    evidences = build_observation_evidence(
        payload,
        target_trade_date,
        c_predictions=c_predictions,
        factor_results=factor_results,
        generated_at=generated_at,
    )
    tasks = []
    for evidence in evidences:
        raw = planner_func(evidence) if planner_func else _call_codex_for_plan(evidence)
        plan = _parse_llm_json(raw)
        if not plan:
            logger.warning("D线观察计划: LLM 输出非 JSON 或为空,跳过 %s", (evidence.get("stock") or {}).get("code"))
            continue
        task = task_from_llm_plan(evidence, plan, plan_version=plan_version, created_at=generated_at)
        if task:
            tasks.append(task)
        else:
            logger.warning("D线观察计划: LLM schema 校验失败,跳过 %s", (evidence.get("stock") or {}).get("code"))
    return tasks


def record_observation_tasks(tasks: Iterable[Dict[str, Any]], *,
                             history_path=None,
                             current_path=None) -> Dict[str, int]:
    """Idempotently append D-line tasks and materialize current active tasks."""
    hist = Path(history_path or OBSERVATION_TASKS_FILE)
    current = Path(current_path or CURRENT_TASKS_FILE)
    rows = [t for t in tasks if isinstance(t, dict)]
    existing = {r.get("task_id") for r in _read_jsonl(hist)}
    written = skipped = 0
    for task in rows:
        tid = task.get("task_id")
        if not tid or tid in existing:
            skipped += 1
            continue
        _append_jsonl(hist, task)
        existing.add(tid)
        written += 1
    if rows:
        target_dates = sorted({str(t.get("target_trade_date") or "") for t in rows if t.get("target_trade_date")})
        _write_json(current, {
            "schema_version": SCHEMA_VERSION,
            "updated_at": _now_iso(),
            "target_trade_dates": target_dates,
            "tasks": rows,
        })
    if written:
        logger.info(f"D线观察任务写入 {written} 条({hist})")
    return {"written": written, "skipped": skipped, "current": len(rows)}
