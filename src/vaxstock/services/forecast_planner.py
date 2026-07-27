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
import math
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from vaxstock import config
from vaxstock.services.company_context import build_context_from_payload_item, summarize_context
from vaxstock.services.history_summary import load_live_history
from vaxstock.sources.codex import CodexCallError

logger = logging.getLogger(__name__)

FORECAST_DIR = config.STATE_DIR / "forecast"
OBSERVATION_TASKS_FILE = FORECAST_DIR / "observation_tasks.jsonl"
CURRENT_TASKS_FILE = FORECAST_DIR / "current_tasks.json"
CURRENT_TASKS_MD_FILE = FORECAST_DIR / "current_tasks.md"
OBSERVATION_JOBS_FILE = FORECAST_DIR / "observation_jobs.jsonl"
CURRENT_OBSERVATION_JOB_FILE = FORECAST_DIR / "current_job.json"
PLAN_PROMPT_FILE = config.PROJECT_ROOT / "deploy" / "d_observation_plan_prompt.md"

SCHEMA_VERSION = 1
EVIDENCE_SCHEMA_VERSION = 1
DEFAULT_PLAN_VERSION = "d_observe_llm_v2"
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


def _read_json(path) -> Optional[dict]:
    p = Path(path)
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception as e:
        logger.warning(f"D line json parse failed, skip: {p} {str(e)[:80]}")
        return None


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


def _compact_macro(macro: Dict[str, Any]) -> Dict[str, Any]:
    indicators = macro.get("indicators") or {}
    fields = {
        "etf_net_sub": (
            "value_5d_yi", "value_20d_yi", "signal_5d", "signal_20d", "latest_date",
        ),
        "margin_ratio": (
            "ratio_pct", "percentile_3y", "signal", "latest_date", "stale",
        ),
        "turnover": (
            "turnover_rate", "percentile_3y", "signal", "proxy_code", "latest_date",
        ),
        "hs300_erp": (
            "pe_ttm", "yield_10y_pct", "yield_source", "erp_pct", "percentile_5y", "signal", "latest_date",
        ),
        "breadth": (
            "available", "above_ma60_pct", "above_ma60_signal",
            "above_ma200_pct", "above_ma200_signal", "ma250_bias_pct",
            "ma250_bias_signal", "latest_date", "bias_latest_date",
        ),
        "m1_yoy": (
            "value_pct", "mom_delta_pp", "percentile_10y", "signal", "latest_month",
        ),
        "sf_pulse": (
            "pulse_yoy_pct", "accel_pp", "signal", "latest_month",
        ),
    }
    compact_indicators = {}
    for name, allowed in fields.items():
        raw = indicators.get(name)
        if not isinstance(raw, dict):
            continue
        compact_indicators[name] = {
            key: raw.get(key) for key in allowed if key in raw
        }
    return {
        "macro_regime": macro.get("macro_regime"),
        "bullish_count": macro.get("bullish_count"),
        "bearish_count": macro.get("bearish_count"),
        "indicators": compact_indicators,
        "errors": list(macro.get("errors") or []),
    }


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
            "vetoes": first.get("vetoes"),
            "pending": first.get("pending"),
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
        "macro": _compact_macro(macro),
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
    """Build compact B-line history by code from append-only factor_results rows.

    ``factor_results.jsonl`` may append one horizon set first and later append
    more horizons for the same ``(trade_date, code)``. Evidence should present
    one merged row per date instead of exposing append mechanics to the LLM.
    """
    by_code_date: Dict[str, Dict[str, Dict[str, Any]]] = {}
    complete_seen: Dict[Tuple[str, str], bool] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip()
        td = str(row.get("trade_date") or "").strip()
        if not (code and td):
            continue
        dst = by_code_date.setdefault(code, {}).setdefault(td, {
            "trade_date": td,
            "ret": {},
            "mkt_ret": {},
            "excess": {},
            "complete": False,
        })
        for key in ("ret", "mkt_ret", "excess"):
            vals = row.get(key) or {}
            if isinstance(vals, dict):
                dst[key].update(vals)
        if row.get("complete") is True:
            complete_seen[(code, td)] = True
            dst["complete"] = True
    out = {}
    for code, vals_by_date in by_code_date.items():
        rows_out = []
        for td, row in vals_by_date.items():
            row["complete"] = bool(complete_seen.get((code, td), row.get("complete")))
            rows_out.append(row)
        out[code] = sorted(rows_out, key=lambda r: r["trade_date"])[-limit:]
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


def _codex_plan_runtime_config(secrets: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve D-line Codex runtime config, falling back to shared Codex config."""
    timeout = secrets.get("codex_dline_timeout")
    if timeout is None:
        timeout = secrets.get("codex_timeout", 30)
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = 30
    return {
        "url": secrets.get("codex_url"),
        "model": secrets.get("codex_dline_model") or secrets.get("codex_model"),
        "token": secrets.get("codex_token"),
        "timeout": timeout,
    }


def _stock_code(item: Dict[str, Any]) -> str:
    return str((item or {}).get("code") or "").strip()


def select_observation_task_codes(payload: Dict[str, Any], task_pool: Optional[Dict[str, Dict[str, Any]]] = None,
                                  *, include_task_pool: bool = False) -> List[str]:
    """Return D-line task codes, with production defaulting to holdings only.

    The wide watchlist remains the A/B/C data foundation.  D-line LLM planning
    consumes only current holdings so non-position alerts do not create intraday
    noise.  ``include_task_pool`` is an explicit research/replay opt-in and is
    never enabled by the production worker.
    """
    holding_codes = {
        _stock_code(item)
        for item in (payload or {}).get("stocks") or []
        if isinstance(item, dict) and item.get("group") == "holding" and _stock_code(item)
    }
    wanted = set(holding_codes)
    if include_task_pool:
        pool = task_pool if task_pool is not None else config.load_task_pool()
        wanted.update(
            str(code).strip()
            for code, info in (pool or {}).items()
            if str(code).strip() and (info or {}).get("active") is not False
        )
    ordered = []
    seen = set()
    for item in (payload or {}).get("stocks") or []:
        code = _stock_code(item) if isinstance(item, dict) else ""
        if code and code in wanted and code not in seen:
            ordered.append(code)
            seen.add(code)
    return ordered


def build_observation_evidence(payload: Dict[str, Any], target_trade_date: str, *,
                               c_predictions: Optional[Iterable[Dict[str, Any]]] = None,
                               factor_results: Optional[Iterable[Dict[str, Any]]] = None,
                               prediction_history: Optional[Dict[str, Dict[str, Any]]] = None,
                               task_codes: Optional[Iterable[str]] = None,
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
    prediction_history_idx = prediction_history if prediction_history is not None else load_live_history(cutoff_trade_date=baseline)
    market = _compact_market(payload)
    ts = generated_at or _now_iso()
    task_code_set = {str(c).strip() for c in task_codes or [] if str(c).strip()} if task_codes is not None else None
    evidences: List[Dict[str, Any]] = []

    for item in (payload or {}).get("stocks") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        if task_code_set is not None and code not in task_code_set:
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
            "B_prediction_history_summary": prediction_history_idx.get(code) or {
                "available": False,
                "source": "eod_predictions+eod_prediction_results",
                "generation_mode": "live",
                "horizon": "1",
                "cutoff_trade_date": baseline,
                "evaluated": 0,
            },
            "C_prediction": pred_idx.get(code),
            "E_context": build_context_from_payload_item(item, payload, target),
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
    runtime = _codex_plan_runtime_config(s)
    if not (s.get("codex_enabled", True) and runtime.get("url") and runtime.get("model") and runtime.get("token")):
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
        url=runtime["url"],
        model=runtime["model"],
        token=runtime["token"],
        timeout=runtime["timeout"],
        raise_on_error=True,
    )


def generate_observation_tasks(payload: Dict[str, Any], target_trade_date: str, *,
                               c_predictions: Optional[Iterable[Dict[str, Any]]] = None,
                               factor_results: Optional[Iterable[Dict[str, Any]]] = None,
                               prediction_history: Optional[Dict[str, Dict[str, Any]]] = None,
                               task_codes: Optional[Iterable[str]] = None,
                               planner_func: Optional[Callable[[Dict[str, Any]], Any]] = None,
                               plan_version: str = DEFAULT_PLAN_VERSION,
                               generated_at: Optional[str] = None,
                               task_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
                               failure_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None) -> List[Dict[str, Any]]:
    """Generate D-line observation tasks from A/B/C evidence.

    ``planner_func`` is a seam for tests/replay. When omitted, Codex is called
    via the configured local OpenAI-compatible endpoint. Successful tasks may be
    recorded immediately through ``task_callback`` so a provider outage cannot
    erase earlier LLM work in the same run.
    """
    evidences = build_observation_evidence(
        payload,
        target_trade_date,
        c_predictions=c_predictions,
        factor_results=factor_results,
        prediction_history=prediction_history,
        task_codes=task_codes,
        generated_at=generated_at,
    )
    tasks = []
    total = len(evidences)
    runtime = None if planner_func else _codex_plan_runtime_config(config.SECRETS)
    for idx, evidence in enumerate(evidences, start=1):
        stock = evidence.get("stock") or {}
        code = str(stock.get("code") or "").strip()
        name = stock.get("name")
        evidence_chars = len(json.dumps(evidence, ensure_ascii=False, default=str))
        started = dt.datetime.now()
        if runtime:
            logger.info(
                "D-line plan: [%s/%s] start code=%s name=%s model=%s timeout=%ss evidence_chars=%s",
                idx,
                total,
                code,
                name,
                runtime.get("model"),
                runtime.get("timeout"),
                evidence_chars,
            )
        else:
            logger.info(
                "D-line plan: [%s/%s] start code=%s name=%s planner=injected evidence_chars=%s",
                idx,
                total,
                code,
                name,
                evidence_chars,
            )
        try:
            raw = planner_func(evidence) if planner_func else _call_codex_for_plan(evidence)
        except CodexCallError as e:
            elapsed = (dt.datetime.now() - started).total_seconds()
            setattr(e, "stock_code", code)
            logger.warning(
                "D-line plan: [%s/%s] codex_error code=%s elapsed=%.2fs error_type=%s status=%s retryable=%s message=%s",
                idx,
                total,
                code,
                elapsed,
                getattr(e, "error_type", None),
                getattr(e, "status_code", None),
                getattr(e, "retryable", None),
                str(e)[:180],
            )
            raise
        elapsed = (dt.datetime.now() - started).total_seconds()
        plan = _parse_llm_json(raw)
        raw_chars = len(raw or "") if isinstance(raw, str) else 0
        logger.info(
            "D-line plan: [%s/%s] done code=%s elapsed=%.2fs raw_present=%s raw_chars=%s json_ok=%s",
            idx,
            total,
            code,
            elapsed,
            bool(raw),
            raw_chars,
            bool(plan),
        )
        if not plan:
            logger.warning("D-line plan: LLM output invalid/empty, skip %s", code)
            if failure_callback:
                failure_callback(code, "invalid_or_empty", {"raw_present": bool(raw), "raw_chars": raw_chars})
            continue
        task = task_from_llm_plan(evidence, plan, plan_version=plan_version, created_at=generated_at)
        if task:
            tasks.append(task)
            if task_callback:
                task_callback(task)
        else:
            logger.warning("D-line plan: LLM schema invalid, skip %s", code)
            if failure_callback:
                failure_callback(code, "schema_invalid", {"raw_present": bool(raw), "raw_chars": raw_chars})
    return tasks

def make_observation_job_id(baseline_trade_date: str, target_trade_date: str,
                            plan_version: str = DEFAULT_PLAN_VERSION) -> str:
    return "_".join([str(baseline_trade_date), str(target_trade_date), str(plan_version), "job"])


def enqueue_observation_job(payload_path, target_trade_date: str, *,
                            c_predictions: Optional[Iterable[Dict[str, Any]]] = None,
                            baseline_trade_date: Optional[str] = None,
                            task_codes: Optional[Iterable[str]] = None,
                            plan_version: str = DEFAULT_PLAN_VERSION,
                            job_path=None,
                            current_job_path=None) -> Dict[str, Any]:
    """Queue D-line observation planning without calling Codex synchronously."""
    baseline = str(baseline_trade_date or "").strip()
    target = str(target_trade_date or "").strip()
    if not (baseline and target and payload_path):
        return {"queued": 0, "skipped": 1, "reason": "missing_job_fields"}
    job = {
        "schema_version": SCHEMA_VERSION,
        "job_id": make_observation_job_id(baseline, target, plan_version=plan_version),
        "line": "D",
        "status": "queued",
        "created_at": _now_iso(),
        "plan_version": plan_version,
        "baseline_trade_date": baseline,
        "target_trade_date": target,
        "payload_path": str(payload_path),
        "c_predictions": list(c_predictions or []),
    }
    if task_codes is not None:
        job["task_codes"] = sorted({
            str(code).strip() for code in task_codes if str(code).strip()
        })
    hist = Path(job_path or OBSERVATION_JOBS_FILE)
    current = Path(current_job_path or CURRENT_OBSERVATION_JOB_FILE)
    existing = {r.get("job_id") for r in _read_jsonl(hist)}
    queued = 0
    skipped = 0
    if job["job_id"] in existing:
        skipped = 1
    else:
        _append_jsonl(hist, job)
        queued = 1
    _write_json(current, job)
    return {"queued": queued, "skipped": skipped, "job_id": job["job_id"], "current": str(current)}


def _task_job_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        str((row or {}).get("baseline_trade_date") or "").strip(),
        str((row or {}).get("target_trade_date") or "").strip(),
        str((row or {}).get("plan_version") or DEFAULT_PLAN_VERSION).strip(),
    )


def _existing_task_codes(history_path, baseline_trade_date: str, target_trade_date: str,
                         plan_version: str = DEFAULT_PLAN_VERSION) -> set:
    key = (str(baseline_trade_date or "").strip(), str(target_trade_date or "").strip(), str(plan_version or DEFAULT_PLAN_VERSION).strip())
    codes = set()
    for row in _read_jsonl(history_path):
        if not isinstance(row, dict) or _task_job_key(row) != key:
            continue
        code = str(row.get("code") or "").strip()
        if code:
            codes.add(code)
    return codes


def _tasks_for_targets(history_path, target_dates: Optional[Iterable[str]] = None,
                       allowed_codes: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    target_set = {str(d).strip() for d in target_dates or [] if str(d).strip()}
    allowed_set = None if allowed_codes is None else {
        str(code).strip() for code in allowed_codes if str(code).strip()
    }
    rows_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in _read_jsonl(history_path):
        if not isinstance(row, dict):
            continue
        target = str(row.get("target_trade_date") or "").strip()
        if target_set and target not in target_set:
            continue
        tid = str(row.get("task_id") or "").strip()
        code = str(row.get("code") or "").strip()
        if allowed_set is not None and code not in allowed_set:
            continue
        if not tid:
            continue
        key = (target, code or tid)
        # History is append-only, but current_tasks is an active snapshot.  If a
        # same-day task is regenerated under a newer plan_version, the latest row
        # should replace the older one for intraday consumption.
        rows_by_key[key] = row
    return sorted(
        rows_by_key.values(),
        key=lambda r: (
            str(r.get("target_trade_date") or ""),
            str(r.get("baseline_trade_date") or ""),
            str(r.get("code") or ""),
            str(r.get("task_id") or ""),
        ),
    )


_FIELD_LABELS = {
    "price": "现价",
    "change_pct": "涨跌幅",
    "amplitude_pct": "振幅",
    "amount_yi": "成交额(亿)",
    "price_vs_ma5_pct": "相对MA5",
    "price_vs_ma10_pct": "相对MA10",
    "price_vs_ma20_pct": "相对MA20",
    "price_vs_ma60_pct": "相对MA60",
    "volume_ratio_5d": "5日量比",
    "position_20d_pct": "20日位置",
    "position_52w_pct": "52周位置",
    "recent_5d_change_pct": "近5日涨跌",
    "recent_20d_change_pct": "近20日涨跌",
    "macd_hist": "MACD柱",
    "rsi_14": "RSI14",
}

_TRIGGER_LABELS = {
    "breakdown_confirm": "破位确认",
    "breakout_confirm": "突破确认",
    "reclaim_confirm": "收复确认",
    "weak_rebound": "弱反弹",
    "failed_breakout": "突破失败",
    "panic_rebound_probe": "恐慌反弹观察",
    "risk_off_confirm": "风险回避确认",
    "noise_filter": "噪音过滤",
}

_ACTION_LABELS = {
    "candidate_buy": "候选买入验证",
    "watch": "观察验证",
    "avoid": "回避/低优先级验证",
}


def _finite_float(value) -> Optional[float]:
    num = _to_float(value)
    if num is None or not math.isfinite(num):
        return None
    return num


def _fmt_number(value, digits: int = 2, signed: bool = False) -> str:
    num = _finite_float(value)
    if num is None:
        return "N/A"
    sign = "+" if signed and num > 0 else ""
    return f"{sign}{num:.{digits}f}"


def _fmt_pct(value, digits: int = 2, signed: bool = True) -> str:
    num = _finite_float(value)
    if num is None:
        return "N/A"
    sign = "+" if signed and num > 0 else ""
    return f"{sign}{num:.{digits}f}%"


def _fmt_confidence(value) -> str:
    num = _finite_float(value)
    if num is None:
        return "N/A"
    return f"{num * 100:.0f}%"


def _short_text(value, limit: int = 140) -> str:
    txt = str(value or "").strip().replace("\n", " ")
    if len(txt) <= limit:
        return txt
    return txt[:limit - 1].rstrip() + "..."


def _field_value_text(field: str, value) -> str:
    if field.endswith("_pct") or field in {"change_pct", "amplitude_pct", "position_20d_pct", "position_52w_pct", "recent_5d_change_pct", "recent_20d_change_pct"}:
        return _fmt_pct(value)
    return _fmt_number(value)


def _price_reference_for_clause(field: str, op: str, value, metrics: Dict[str, Any]) -> str:
    ma_key_by_field = {
        "price_vs_ma5_pct": "ma5",
        "price_vs_ma10_pct": "ma10",
        "price_vs_ma20_pct": "ma20",
        "price_vs_ma60_pct": "ma60",
    }
    ma_key = ma_key_by_field.get(field)
    pct = _finite_float(value)
    ma = _finite_float((metrics or {}).get(ma_key)) if ma_key else None
    if ma is None or pct is None:
        return ""
    price = ma * (1.0 + pct / 100.0)
    return f" (约价 {op} {_fmt_number(price)}, {ma_key.upper()}={_fmt_number(ma)})"


def _condition_clause_text(clause: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    field = str((clause or {}).get("field") or "").strip()
    op = str((clause or {}).get("op") or "").strip()
    value = (clause or {}).get("value")
    label = _FIELD_LABELS.get(field, field or "?")
    price_ref = _price_reference_for_clause(field, op, value, metrics)
    return f"{label} {op} {_field_value_text(field, value)}{price_ref}"


def _condition_text(condition: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    parts = []
    for key, label in (("all", "同时"), ("any", "任一")):
        clauses = (condition or {}).get(key) or []
        if not clauses:
            continue
        rendered = "; ".join(_condition_clause_text(c, metrics) for c in clauses if isinstance(c, dict))
        if rendered:
            parts.append(f"{label}: {rendered}")
    return " | ".join(parts) if parts else "N/A"


def _task_sort_key(task: Dict[str, Any]) -> Tuple[int, int, str]:
    group_rank = 0 if task.get("group") == "holding" else 1
    prediction = (((task.get("evidence_pack") or {}).get("C_prediction") or {}).get("prediction") or {})
    action_rank = {"candidate_buy": 0, "watch": 1, "avoid": 2}.get(prediction.get("action"), 9)
    return (group_rank, action_rank, str(task.get("code") or ""))


def render_current_tasks_markdown(snapshot: Dict[str, Any]) -> str:
    """Render current D-line tasks into a human-readable markdown digest."""
    tasks = [t for t in (snapshot or {}).get("tasks") or [] if isinstance(t, dict)]
    target_dates = ", ".join(str(x) for x in (snapshot or {}).get("target_trade_dates") or []) or "N/A"
    lines = [
        "# D线盘中观察任务摘要",
        "",
        f"- updated_at: {(snapshot or {}).get('updated_at') or 'N/A'}",
        f"- target_trade_dates: {target_dates}",
        f"- tasks: {len(tasks)}",
        "- 口径: 本文件只翻译 D线观察任务, 不给买卖建议; 价格来自 T-1 EOD 基准与任务触发条件。",
        "",
        "## 任务总览",
        "",
    ]
    for group, title in (("holding", "持仓"), ("watchlist", "观察/任务池")):
        group_tasks = sorted([t for t in tasks if t.get("group") == group], key=_task_sort_key)
        if not group_tasks:
            continue
        lines += [f"### {title}", ""]
        for task in group_tasks:
            evidence = task.get("evidence_pack") or {}
            metrics = (evidence.get("A_eod") or {}).get("metrics") or {}
            price = (evidence.get("A_eod") or {}).get("price")
            prediction = ((evidence.get("C_prediction") or {}).get("prediction") or {})
            action = prediction.get("action")
            direction = prediction.get("direction")
            confidence = prediction.get("confidence")
            trigger_types = [str(t.get("trigger_type") or "") for t in ((task.get("observation") or {}).get("trigger_blueprints") or [])]
            trigger_names = ", ".join(_TRIGGER_LABELS.get(x, x) for x in trigger_types if x) or "N/A"
            decision_context = task.get("decision_context") or {}
            independent_label = str(decision_context.get("label") or "").strip()
            c_line_label = "C线(仅留档)" if independent_label else "C线"
            prefix = f"独立验证: {independent_label} | " if independent_label else ""
            lines.append(
                f"- **{task.get('code')} {task.get('name')}** | {prefix}{c_line_label}: {_ACTION_LABELS.get(action, action or 'N/A')} / {direction or 'N/A'} / 置信度 {_fmt_confidence(confidence)} | "
                f"分析价 {_fmt_number(price)} | MA20偏离 {_fmt_pct(metrics.get('price_vs_ma20_pct'))} | 触发: {trigger_names}"
            )
        lines.append("")

    lines += ["## 个股明细", ""]
    for task in sorted(tasks, key=_task_sort_key):
        evidence = task.get("evidence_pack") or {}
        a_eod = evidence.get("A_eod") or {}
        metrics = a_eod.get("metrics") or {}
        prediction = (evidence.get("C_prediction") or {}).get("prediction") or {}
        ctx_summary = summarize_context(evidence.get("E_context") or {})
        obs = task.get("observation") or {}
        decision_context = task.get("decision_context") or {}
        concepts = ", ".join(str(x) for x in task.get("concepts") or []) or "N/A"
        action = prediction.get("action")
        lines += [
            f"### {task.get('code')} {task.get('name')} ({'持仓' if task.get('group') == 'holding' else '观察'})",
            "",
            f"- C线: {_ACTION_LABELS.get(action, action or 'N/A')} / direction={prediction.get('direction') or 'N/A'} / confidence={_fmt_confidence(prediction.get('confidence'))}",
            f"- C线依据: {_short_text(prediction.get('reason'), 180) or 'N/A'}",
            f"- 概念: {concepts}",
            f"- E-context: earnings={ctx_summary.get('earnings_status')}; next_report={ctx_summary.get('next_report_date') or 'N/A'}; events={ctx_summary.get('company_event_count')}; industry={ctx_summary.get('industry_status')}",
            f"- 真实价量基准(T-1 EOD): 分析价={_fmt_number(a_eod.get('price'))}; MA5={_fmt_number(metrics.get('ma5'))}; MA10={_fmt_number(metrics.get('ma10'))}; MA20={_fmt_number(metrics.get('ma20'))}; MA60={_fmt_number(metrics.get('ma60'))}",
            f"- 位置/动量: MA5偏离={_fmt_pct(metrics.get('price_vs_ma5_pct'))}; MA20偏离={_fmt_pct(metrics.get('price_vs_ma20_pct'))}; MA60偏离={_fmt_pct(metrics.get('price_vs_ma60_pct'))}; 20日位置={_fmt_pct(metrics.get('position_20d_pct'), signed=False)}; 52周位置={_fmt_pct(metrics.get('position_52w_pct'), signed=False)}",
            f"- 量能/近期: 5日量比={_fmt_number(metrics.get('volume_ratio_5d'))}; 近5日={_fmt_pct(metrics.get('recent_5d_change_pct'))}; 近20日={_fmt_pct(metrics.get('recent_20d_change_pct'))}; MACD柱={_fmt_number(metrics.get('macd_hist'), 3)}; RSI14={_fmt_number(metrics.get('rsi_14'))}",
        ]
        if decision_context:
            lines += [
                f"- 独立决策上下文: {_short_text(decision_context.get('label'), 80) or 'N/A'}",
                f"- 与C线关系: {_short_text(decision_context.get('relation_to_c_line'), 180) or 'N/A'}",
                f"- 审计说明: {_short_text(decision_context.get('audit_note'), 180) or 'N/A'}",
            ]
        lines += [
            "- 独立客观评价:" if decision_context else "- LLM客观评价:",
            f"  - 观察意图: {_short_text(obs.get('observe_intent'), 220) or 'N/A'}",
            f"  - 主要风险: {_short_text(obs.get('primary_risk'), 220) or 'N/A'}",
            f"  - C线反馈焦点: {_short_text(obs.get('c_line_feedback_focus'), 220) or 'N/A'}",
            f"  - 证伪/修正条件: {_short_text(obs.get('falsify_if'), 220) or 'N/A'}",
            "- 触发条件:",
        ]
        triggers = obs.get("trigger_blueprints") or []
        if not triggers:
            lines.append("  - N/A")
        for idx, trigger in enumerate(triggers, start=1):
            ttype = str(trigger.get("trigger_type") or "")
            lines.append(
                f"  {idx}. {_TRIGGER_LABELS.get(ttype, ttype or 'N/A')} / severity={trigger.get('severity') or 'N/A'}: "
                f"{_condition_text(trigger.get('condition') or {}, metrics)}"
            )
            why = _short_text(trigger.get("why"), 180)
            feedback = _short_text(trigger.get("expected_feedback_to_c"), 120)
            if why:
                lines.append(f"     - 客观含义: {why}")
            if feedback:
                lines.append(f"     - 对C线反馈: {feedback}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _current_tasks_markdown_path(current_path) -> Path:
    current = Path(current_path or CURRENT_TASKS_FILE)
    return CURRENT_TASKS_MD_FILE if current == CURRENT_TASKS_FILE else current.with_suffix(".md")

def _materialize_current_tasks(history_path, current_path, target_dates: Optional[Iterable[str]] = None,
                               allowed_codes: Optional[Iterable[str]] = None) -> int:
    current = Path(current_path or CURRENT_TASKS_FILE)
    tasks = _tasks_for_targets(
        history_path,
        target_dates=target_dates,
        allowed_codes=allowed_codes,
    )
    target_list = sorted({str(t.get("target_trade_date") or "") for t in tasks if t.get("target_trade_date")})
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now_iso(),
        "target_trade_dates": target_list,
        "tasks": tasks,
    }
    _write_json(current, snapshot)
    _current_tasks_markdown_path(current).write_text(render_current_tasks_markdown(snapshot), encoding="utf-8")
    return len(tasks)


def _job_snapshot(job: Dict[str, Any], *, status: str, baseline: str, target: str,
                  plan_version: str, task_codes: List[str], done_codes: List[str],
                  remaining_codes: List[str], stats: Dict[str, Any], failures: Optional[List[Dict[str, Any]]] = None,
                  error: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = dict(job or {})
    out.update({
        "status": status,
        "updated_at": _now_iso(),
        "plan_version": plan_version,
        "baseline_trade_date": baseline,
        "target_trade_date": target,
        "task_codes": task_codes,
        "done_codes": done_codes,
        "remaining_codes": remaining_codes,
        "stats": stats,
    })
    if status in {"done", "partial_done", "partial_failed", "missing_payload"}:
        out["finished_at"] = _now_iso()
    if failures:
        out["failures"] = failures
    if error:
        out["error"] = error
    return out


def run_observation_job(job: Optional[Dict[str, Any]] = None, *,
                        planner_func: Optional[Callable[[Dict[str, Any]], Any]] = None,
                        job_path=None,
                        current_job_path=None,
                        history_path=None,
                        current_tasks_path=None) -> Dict[str, Any]:
    """Consume the current D-line planning job and generate observation tasks.

    The worker is resumable. Existing tasks for the same baseline/target/version
    are skipped, successful tasks are appended immediately, and provider outages
    leave the job as ``partial_failed`` instead of pretending it is done.
    """
    del job_path  # history of queued jobs is append-only; current_job is the worker cursor.
    current = Path(current_job_path or CURRENT_OBSERVATION_JOB_FILE)
    hist = Path(history_path or OBSERVATION_TASKS_FILE)
    current_tasks = Path(current_tasks_path or CURRENT_TASKS_FILE)
    job = job or _read_json(current)
    if not job:
        logger.info("D线观察任务: 无待处理 job")
        return {"status": "no_job", "generated": 0, "written": 0, "skipped": 0}
    payload_path = job.get("payload_path")
    payload = _read_json(payload_path) if payload_path else None
    if not payload:
        logger.warning("D线观察任务: job payload 不可读,跳过: %s", payload_path)
        snap = _job_snapshot(
            job,
            status="missing_payload",
            baseline=str(job.get("baseline_trade_date") or ""),
            target=str(job.get("target_trade_date") or ""),
            plan_version=str(job.get("plan_version") or DEFAULT_PLAN_VERSION),
            task_codes=list(job.get("task_codes") or []),
            done_codes=list(job.get("done_codes") or []),
            remaining_codes=list(job.get("remaining_codes") or []),
            stats={"generated": 0, "written": 0, "skipped": 0, "current": 0},
            error={"type": "missing_payload", "message": str(payload_path or "")},
        )
        _write_json(current, snap)
        return {
            "status": "missing_payload",
            "target_trade_date": str(job.get("target_trade_date") or ""),
            "generated": 0,
            "written": 0,
            "skipped": 0,
        }

    baseline = str(job.get("baseline_trade_date") or ((payload.get("market_overview") or {}).get("trade_date")) or "").strip()
    target = str(job.get("target_trade_date") or "").strip()
    plan_version = str(job.get("plan_version") or DEFAULT_PLAN_VERSION).strip()
    task_codes = select_observation_task_codes(payload)
    if isinstance(job.get("task_codes"), list):
        freshness_allowed = {
            str(code).strip() for code in job["task_codes"] if str(code).strip()
        }
        task_codes = [code for code in task_codes if code in freshness_allowed]
    existing_codes = _existing_task_codes(hist, baseline, target, plan_version)
    done_codes = [c for c in task_codes if c in existing_codes]
    pending_codes = [c for c in task_codes if c not in existing_codes]

    if not pending_codes:
        current_count = _materialize_current_tasks(
            hist, current_tasks, target_dates=[target] if target else None,
            allowed_codes=task_codes,
        )
        stats = {"generated": 0, "written": 0, "skipped": 0, "current": current_count, "existing": len(done_codes)}
        snap = _job_snapshot(
            job,
            status="done",
            baseline=baseline,
            target=target,
            plan_version=plan_version,
            task_codes=task_codes,
            done_codes=done_codes,
            remaining_codes=[],
            stats=stats,
        )
        _write_json(current, snap)
        logger.info("D-line observation worker: all %s tasks already exist, no-op", len(done_codes))
        return {
            "status": "done",
            "target_trade_date": target,
            **stats,
            "task_codes": len(task_codes),
            "remaining": 0,
        }

    running = _job_snapshot(
        job,
        status="running",
        baseline=baseline,
        target=target,
        plan_version=plan_version,
        task_codes=task_codes,
        done_codes=done_codes,
        remaining_codes=pending_codes,
        stats={"generated": 0, "written": 0, "skipped": 0, "current": len(done_codes), "existing": len(done_codes)},
    )
    running.setdefault("started_at", _now_iso())
    running["last_run_started_at"] = _now_iso()
    _write_json(current, running)

    generated = 0
    written = 0
    skipped = 0
    current_count = _materialize_current_tasks(
        hist, current_tasks, target_dates=[target] if target else None,
        allowed_codes=task_codes,
    )
    failures: List[Dict[str, Any]] = []

    def _record_task(task: Dict[str, Any]) -> None:
        nonlocal generated, written, skipped, current_count
        generated += 1
        stats = record_observation_tasks(
            [task], history_path=hist, current_path=current_tasks,
            active_codes=task_codes,
        )
        written += int(stats.get("written", 0))
        skipped += int(stats.get("skipped", 0))
        current_count = int(stats.get("current", current_count))

    def _record_failure(code: str, reason: str, detail: Dict[str, Any]) -> None:
        failures.append({"code": code, "reason": reason, "detail": detail, "at": _now_iso()})

    try:
        generate_observation_tasks(
            payload,
            target,
            c_predictions=job.get("c_predictions") or [],
            task_codes=pending_codes,
            planner_func=planner_func,
            plan_version=plan_version,
            task_callback=_record_task,
            failure_callback=_record_failure,
        )
    except CodexCallError as e:
        existing_after = _existing_task_codes(hist, baseline, target, plan_version)
        done_after = [c for c in task_codes if c in existing_after]
        remaining_after = [c for c in task_codes if c not in existing_after]
        current_count = _materialize_current_tasks(
            hist, current_tasks, target_dates=[target] if target else None,
            allowed_codes=task_codes,
        )
        stats = {
            "generated": generated,
            "written": written,
            "skipped": skipped,
            "current": current_count,
            "existing": len(done_after),
        }
        error = {
            "type": getattr(e, "error_type", "codex_error"),
            "status_code": getattr(e, "status_code", None),
            "code": getattr(e, "code", None),
            "retryable": getattr(e, "retryable", False),
            "failed_code": getattr(e, "stock_code", None),
            "message": str(e)[:300],
        }
        snap = _job_snapshot(
            job,
            status="partial_failed",
            baseline=baseline,
            target=target,
            plan_version=plan_version,
            task_codes=task_codes,
            done_codes=done_after,
            remaining_codes=remaining_after,
            stats=stats,
            failures=failures,
            error=error,
        )
        _write_json(current, snap)
        logger.warning(
            "D-line observation worker partial_failed: generated=%s written=%s remaining=%s failed_code=%s error_type=%s",
            generated,
            written,
            len(remaining_after),
            error.get("failed_code"),
            error.get("type"),
        )
        return {
            "status": "partial_failed",
            "target_trade_date": target,
            **stats,
            "task_codes": len(task_codes),
            "remaining": len(remaining_after),
            "error": error,
        }

    existing_after = _existing_task_codes(hist, baseline, target, plan_version)
    done_after = [c for c in task_codes if c in existing_after]
    remaining_after = [c for c in task_codes if c not in existing_after]
    current_count = _materialize_current_tasks(
        hist, current_tasks, target_dates=[target] if target else None,
        allowed_codes=task_codes,
    )
    status = "done" if not remaining_after else "partial_done"
    stats = {
        "generated": generated,
        "written": written,
        "skipped": skipped,
        "current": current_count,
        "existing": len(done_after),
    }
    snap = _job_snapshot(
        job,
        status=status,
        baseline=baseline,
        target=target,
        plan_version=plan_version,
        task_codes=task_codes,
        done_codes=done_after,
        remaining_codes=remaining_after,
        stats=stats,
        failures=failures,
    )
    _write_json(current, snap)
    return {
        "status": status,
        "target_trade_date": target,
        **stats,
        "task_codes": len(task_codes),
        "remaining": len(remaining_after),
    }


def record_observation_tasks(tasks: Iterable[Dict[str, Any]], *,
                             history_path=None,
                             current_path=None,
                             active_codes: Optional[Iterable[str]] = None) -> Dict[str, int]:
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
    target_dates = sorted({str(t.get("target_trade_date") or "") for t in rows if t.get("target_trade_date")})
    current_count = 0
    if target_dates:
        current_count = _materialize_current_tasks(
            hist, current, target_dates=target_dates,
            allowed_codes=active_codes,
        )
    if written:
        logger.info("D线观察任务写入 %s 条(%s)", written, hist)
    return {"written": written, "skipped": skipped, "current": current_count}
