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
                logger.warning(f"D line jsonl è¡Œè§£æžå¤±è´¥,è·³è¿‡: {line[:80]}")
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
            "ä½ æ˜¯Dçº¿ç›˜ä¸­è§‚å¯Ÿä»»åŠ¡ç”Ÿæˆå™¨ã€‚åŸºäºŽA/B/Cå®šç¨¿è¯æ®,ä¸ºæ¬¡æ—¥ç›˜ä¸­ç”Ÿæˆå®¢è§‚è§‚å¯Ÿä»»åŠ¡ã€‚"
            "åªè¾“å‡ºJSON,ä¸è¦è¾“å‡ºä¹°å–ä»·ã€æ­¢æŸä»·ã€ç›®æ ‡ä»·,ä¸è¦è‡†æµ‹ç›˜ä¸­èµ„é‡‘ã€‚"
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
            "B_prediction_history_summïß9¶‰žËkºwµçTœ¤¥ôì5ÄÀõí}™µÑ}¹Õµ‰•È¡µ•ÑÉ¥Ì¹•Ð µ„ÄÀœ¤¥ôì5ÈÀõí}™µÑ}¹Õµ‰•È¡µ•ÑÉ¥Ì¹•Ð µ„ÈÀœ¤¥ôì5ØÀõí}™µÑ}¹Õµ‰•È¡µ•ÑÉ¥Ì¹•Ð µ„ØÀœ¤¥ôˆ°4(€€€€€€€€€€€˜ˆ´ƒ’ö7žö¸¿–*£¦<è5×–?žšìõí}™µÑ}ÁÐ¡µ•ÑÉ¥Ì¹•Ð ÁÉ¥•}ÙÍ}µ„Õ}ÁÐœ¤¥ôì5ÈÃ–?žšìõí}™µÑ}ÁÐ¡µ•ÑÉ¥Ì¹•Ð ÁÉ¥•}ÙÍ}µ„ÈÁ}ÁÐœ¤¥ôì5ØÃ–?žšìõí}™µÑ}ÁÐ¡µ•ÑÉ¥Ì¹•Ð ÁÉ¥•}ÙÍ}µ„ØÁ}ÁÐœ¤¥ôì€ÈÃš^—’ö7žö¸õí}™µÑ}ÁÐ¡µ•ÑÉ¥Ì¹•Ð Á½Í¥Ñ¥½¹|ÈÁ‘}ÁÐœ¤°Í¥¹•õ…±Í”¥ôì€ÔË–F£’ö7žö¸õí}™µÑ}ÁÐ¡µ•ÑÉ¥Ì¹•Ð Á½Í¥Ñ¥½¹|ÔÉÝ}ÁÐœ¤°Í¥¹•õ…±Í”¥ôˆ°4(€€€€€€€€€€€˜ˆ´ƒ¦?¢ô¿¢þGšr|è€×š^—¦?š¾Põí}™µÑ}¹Õµ‰•È¡µ•ÑÉ¥Ì¹•Ð Ù½±Õµ•}É…Ñ¥½|Õœ¤¥ôìƒ¢þD×š^”õí}™µÑ}ÁÐ¡µ•ÑÉ¥Ì¹•Ð É••¹Ñ|Õ‘}¡…¹•}ÁÐœ¤¥ôìƒ¢þDÈÃš^”õí}™µÑ}ÁÐ¡µ•ÑÉ¥Ì¹•Ð É••¹Ñ|ÈÁ‘}¡…¹•}ÁÐœ¤¥ôì5š~Äõí}™µÑ}¹Õµ‰•È¡µ•ÑÉ¥Ì¹•Ð µ…‘}¡¥ÍÐœ¤°€Ì¥ôìIM$ÄÐõí}™µÑ}¹Õµ‰•È¡µ•ÑÉ¥Ì¹•Ð ÉÍ¥|ÄÐœ¤¥ôˆ°4(€€€€€€€t4(€€€€€€€¥˜‘•¥Í¥½¹}½¹Ñ•áÐè4(€€€€€€€€€€€±¥¹•Ì€¬ôl4(€€€€€€€€€€€€€€€˜ˆ´ƒž.³ž®/–Ïž¶[’â+’â/šZèí}Í¡½ÉÑ}Ñ•áÐ¡‘•¥Í¥½¹}½¹Ñ•áÐ¹•Ð ±…‰•°œ¤°€àÀ¤½È€8½ôˆ°4(€€€€€€€€€€€€€€€˜ˆ´ƒ’â9žêÿ–ÏžÎìèí}Í¡½ÉÑ}Ñ•áÐ¡‘•¥Í¥½¹}½¹Ñ•áÐ¹•Ð É•±…Ñ¥½¹}Ñ½}}±¥¹”œ¤°€ÄàÀ¤½È€8½ôˆ°4(€€€€€€€€€€€€€€€˜ˆ´ƒ–º‡¢º‡¢¾Óšb8èí}Í¡½ÉÑ}Ñ•áÐ¡‘•¥Í¥½¹}½¹Ñ•áÐ¹•Ð …Õ‘¥Ñ}¹½Ñ”œ¤°€ÄàÀ¤½È€8½ôˆ°4(€€€€€€€€€€€t4(€€€€€€€±¥¹•Ì€¬ôl4(€€€€€€€€€€€€ˆ´ƒž.³ž®/–º‹¢ž¢¾’îÜèˆ¥˜‘•¥Í¥½¹}½¹Ñ•áÐ•±Í”€ˆ´117–º‹¢ž¢¾’îÜèˆ°4(€€€€€€€€€€€˜ˆ€€´ƒ¢ž–¾š?–nøèí}Í¡½ÉÑ}Ñ•áÐ¡½‰Ì¹•Ð ½‰Í•ÉÙ•}¥¹Ñ•¹Ðœ¤°€ÈÈÀ¤½È€8½ôˆ°4(€€€€€€€€€€€˜ˆ€€´ƒ’âï¢š¦Ž;¦f¤èí}Í¡½ÉÑ}Ñ•áÐ¡½‰Ì¹•Ð ÁÉ¥µ…Éå}É¥Í¬œ¤°€ÈÈÀ¤½È€8½ôˆ°4(€€€€€€€€€€€˜ˆ€€´žêÿ–>7¦š#ž›ž
äèí}Í¡½ÉÑ}Ñ•áÐ¡½‰Ì¹•Ð }±¥¹•}™••‘‰…­}™½ÕÌœ¤°€ÈÈÀ¤½È€8½ôˆ°4(€€€€€€€€€€€˜ˆ€€´ƒ¢¾’ò¨¿’þ»š¶šv‡’îØèí}Í¡½ÉÑ}Ñ•áÐ¡½‰Ì¹•Ð ™…±Í¥™å}¥˜œ¤°€ÈÈÀ¤½È€8½ôˆ°4(€€€€€€€€€€€€ˆ´ƒ¢ž›–>Gšv‡’îØèˆ°4(€€€€€€€t4(€€€€€€€ÑÉ¥•ÉÌ€ô½‰Ì¹•Ð ‰ÑÉ¥•É}‰±Õ•ÁÉ¥¹ÑÌˆ¤½Èmt4(€€€€€€€¥˜¹½ÐÑÉ¥•ÉÌè4(€€€€€€€€€€€±¥¹•Ì¹…ÁÁ•¹ ˆ€€´8½ˆ¤4(€€€€€€€™½È¥‘à°ÑÉ¥•È¥¸•¹Õµ•É…Ñ”¡ÑÉ¥•ÉÌ°ÍÑ…ÉÐôÄ¤è4(€€€€€€€€€€€ÑÑåÁ”€ôÍÑÈ¡ÑÉ¥•È¹•Ð ‰ÑÉ¥•É}ÑåÁ”ˆ¤½È€ˆˆ¤4(€€€€€€€€€€€±¥¹•Ì¹…ÁÁ•¹ 4(€€€€€€€€€€€€€€€˜ˆ€í¥‘áô¸í}QI%I}1	1L¹•Ð¡ÑÑåÁ”°ÑÑåÁ”½È€8½œ¥ô€¼Í•Ù•É¥ÑäõíÑÉ¥•È¹•Ð Í•Ù•É¥Ñäœ¤½È€8½ôè€ˆ4(€€€€€€€€€€€€€€€˜‰í}½¹‘¥Ñ¥½¹}Ñ•áÐ¡ÑÉ¥•È¹•Ð ½¹‘¥Ñ¥½¸œ¤½Èíô°µ•ÑÉ¥Ì¥ôˆ4(€€€€€€€€€€€€¤4(€€€€€€€€€€€Ý¡ä€ô}Í¡½ÉÑ}Ñ•áÐ¡ÑÉ¥•È¹•Ð ‰Ý¡äˆ¤°€ÄàÀ¤4(€€€€€€€€€€€™••‘‰…¬€ô}Í¡½ÉÑ}Ñ•áÐ¡ÑÉ¥•È¹•Ð ‰•áÁ•Ñ•‘}™••‘‰…­}Ñ½}Œˆ¤°€ÄÈÀ¤4(€€€€€€€€€€€¥˜Ý¡äè4(€€€€€€€€€€€€€€€±¥¹•Ì¹…ÁÁ•¹¡˜ˆ€€€€€´ƒ–º‹¢ž–B¯’æ$èíÝ¡åôˆ¤4(€€€€€€€€€€€¥˜™••‘‰…¬è4(€€€€€€€€€€€€€€€±¥¹•Ì¹…ÁÁ•¹¡˜ˆ€€€€€´ƒ–¾åžêÿ–>7¦š èí™••‘‰…­ôˆ¤4(€€€€€€€±¥¹•Ì¹…ÁÁ•¹ ˆˆ¤4(€€€É•ÑÕÉ¸€‰q¸ˆ¹©½¥¸¡±¥¹•Ì¤¹ÉÍÑÉ¥À ¤€¬€‰q¸ˆ4(4(4)‘•˜}ÕÉÉ•¹Ñ}Ñ…Í­Í}µ…É­‘½Ý¹}Á…Ñ ¡ÕÉÉ•¹Ñ}Á…Ñ ¤€´øA…Ñ è4(€€€ÕÉÉ•¹Ð€ôA…Ñ ¡ÕÉÉ•¹Ñ}Á…Ñ ½ÈUII9Q}QM-M}%1¤4(€€€É•ÑÕÉ¸UII9Q}QM-M}5}%1¥˜ÕÉÉ•¹Ð€ôôUII9Q}QM-M}%1•±Í”ÕÉÉ•¹Ð¹Ý¥Ñ¡}ÍÕ™™¥à ˆ¹µˆ¤4(4)‘•˜}µ…Ñ•É¥…±¥é•}ÕÉÉ•¹Ñ}Ñ…Í­Ì¡¡¥ÍÑ½Éå}Á…Ñ °ÕÉÉ•¹Ñ}Á…Ñ °Ñ…É•Ñ}‘…Ñ•Ìè=ÁÑ¥½¹…±m%Ñ•É…‰±•mÍÑÉut€ô9½¹”°4(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€…±±½Ý•‘}½‘•Ìè=ÁÑ¥½¹…±m%Ñ•É…‰±•mÍÑÉut€ô9½¹”¤€´ø¥¹Ðè4(€€€ÕÉÉ•¹Ð€ôA…Ñ ¡ÕÉÉ•¹Ñ}Á…Ñ ½ÈUII9Q}QM-M}%1¤4(€€€Ñ…Í­Ì€ô}Ñ…Í­Í}™½É}Ñ…É•ÑÌ 4(€€€€€€€¡¥ÍÑ½Éå}Á…Ñ °4(€€€€€€€Ñ…É•Ñ}‘…Ñ•ÌõÑ…É•Ñ}‘…Ñ•Ì°4(€€€€€€€…±±½Ý•‘}½‘•Ìõ…±±½Ý•‘}½‘•Ì°4(€€€€¤4(€€€Ñ…É•Ñ}±¥ÍÐ€ôÍ½ÉÑ•¡íÍÑÈ¡Ð¹•Ð ‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ”ˆ¤½È€ˆˆ¤™½ÈÐ¥¸Ñ…Í­Ì¥˜Ð¹•Ð ‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ”ˆ¥ô¤4(€€€Í¹…ÁÍ¡½Ð€ôì4(€€€€€€€€‰Í¡•µ…}Ù•ÉÍ¥½¸ˆèM!5}YIM%=8°4(€€€€€€€€‰ÕÁ‘…Ñ•‘}…Ðˆè}¹½Ý}¥Í¼ ¤°4(€€€€€€€€‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ•ÌˆèÑ…É•Ñ}±¥ÍÐ°4(€€€€€€€€‰Ñ…Í­ÌˆèÑ…Í­Ì°4(€€€ô4(€€€}ÝÉ¥Ñ•}©Í½¸¡ÕÉÉ•¹Ð°Í¹…ÁÍ¡½Ð¤4(€€€}ÕÉÉ•¹Ñ}Ñ…Í­Í}µ…É­‘½Ý¹}Á…Ñ ¡ÕÉÉ•¹Ð¤¹ÝÉ¥Ñ•}Ñ•áÐ¡É•¹‘•É}ÕÉÉ•¹Ñ}Ñ…Í­Í}µ…É­‘½Ý¸¡Í¹…ÁÍ¡½Ð¤°•¹½‘¥¹œô‰ÕÑ˜´àˆ¤4(€€€É•ÑÕÉ¸±•¸¡Ñ…Í­Ì¤4(4(4)‘•˜}©½‰}Í¹…ÁÍ¡½Ð¡©½ˆè¥ÑmÍÑÈ°¹åt°€¨°ÍÑ…ÑÕÌèÍÑÈ°‰…Í•±¥¹”èÍÑÈ°Ñ…É•ÐèÍÑÈ°4(€€€€€€€€€€€€€€€€€Á±…¹}Ù•ÉÍ¥½¸èÍÑÈ°Ñ…Í­}½‘•Ìè1¥ÍÑmÍÑÉt°‘½¹•}½‘•Ìè1¥ÍÑmÍÑÉt°4(€€€€€€€€€€€€€€€€€É•µ…¥¹¥¹}½‘•Ìè1¥ÍÑmÍÑÉt°ÍÑ…ÑÌè¥ÑmÍÑÈ°¹åt°™…¥±ÕÉ•Ìè=ÁÑ¥½¹…±m1¥ÍÑm¥ÑmÍÑÈ°¹åuut€ô9½¹”°4(€€€€€€€€€€€€€€€€€•ÉÉ½Èè=ÁÑ¥½¹…±m¥ÑmÍÑÈ°¹åut€ô9½¹”¤€´ø¥ÑmÍÑÈ°¹åtè4(€€€½ÕÐ€ô‘¥Ð¡©½ˆ½Èíô¤4(€€€½ÕÐ¹ÕÁ‘…Ñ”¡ì4(€€€€€€€€‰ÍÑ…ÑÕÌˆèÍÑ…ÑÕÌ°4(€€€€€€€€‰ÕÁ‘…Ñ•‘}…Ðˆè}¹½Ý}¥Í¼ ¤°4(€€€€€€€€‰Á±…¹}Ù•ÉÍ¥½¸ˆèÁ±…¹}Ù•ÉÍ¥½¸°4(€€€€€€€€‰‰…Í•±¥¹•}ÑÉ…‘•}‘…Ñ”ˆè‰…Í•±¥¹”°4(€€€€€€€€‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ”ˆèÑ…É•Ð°4(€€€€€€€€‰Ñ…Í­}½‘•ÌˆèÑ…Í­}½‘•Ì°4(€€€€€€€€‰‘½¹•}½‘•Ìˆè‘½¹•}½‘•Ì°4(€€€€€€€€‰É•µ…¥¹¥¹}½‘•ÌˆèÉ•µ…¥¹¥¹}½‘•Ì°4(€€€€€€€€‰ÍÑ…ÑÌˆèÍÑ…ÑÌ°4(€€€ô¤4(€€€¥˜ÍÑ…ÑÕÌ¥¸ì‰‘½¹”ˆ°€‰Á…ÉÑ¥…±}‘½¹”ˆ°€‰Á…ÉÑ¥…±}™…¥±•ˆ°€‰µ¥ÍÍ¥¹}Á…å±½…‰ôè4(€€€€€€€½ÕÑl‰™¥¹¥Í¡•‘}…Ð‰t€ô}¹½Ý}¥Í¼ ¤4(€€€¥˜™…¥±ÕÉ•Ìè4(€€€€€€€½ÕÑl‰™…¥±ÕÉ•Ì‰t€ô™…¥±ÕÉ•Ì4(€€€¥˜•ÉÉ½Èè4(€€€€€€€½ÕÑl‰•ÉÉ½È‰t€ô•ÉÉ½È4(€€€É•ÑÕÉ¸½ÕÐ4(4(4)‘•˜ÉÕ¹}½‰Í•ÉÙ…Ñ¥½¹}©½ˆ¡©½ˆè=ÁÑ¥½¹…±m¥ÑmÍÑÈ°¹åut€ô9½¹”°€¨°4(€€€€€€€€€€€€€€€€€€€€€€€Á±…¹¹•É}™Õ¹Œè=ÁÑ¥½¹…±m…±±…‰±•mm¥ÑmÍÑÈ°¹åut°¹åut€ô9½¹”°4(€€€€€€€€€€€€€€€€€€€€€€€©½‰}Á…Ñ õ9½¹”°4(€€€€€€€€€€€€€€€€€€€€€€€ÕÉÉ•¹Ñ}©½‰}Á…Ñ õ9½¹”°4(€€€€€€€€€€€€€€€€€€€€€€€¡¥ÍÑ½Éå}Á…Ñ õ9½¹”°4(€€€€€€€€€€€€€€€€€€€€€€€ÕÉÉ•¹Ñ}Ñ…Í­Í}Á…Ñ õ9½¹”¤€´ø¥ÑmÍÑÈ°¹åtè4(€€€€ˆˆ‰½¹ÍÕµ”Ñ¡”ÕÉÉ•¹Ðµ±¥¹”Á±…¹¹¥¹œ©½ˆ…¹•¹•É…Ñ”½‰Í•ÉÙ…Ñ¥½¸Ñ…Í­Ì¸4(4(€€€Q¡”Ý½É­•È¥ÌÉ•ÍÕµ…‰±”¸á¥ÍÑ¥¹œÑ…Í­Ì™½ÈÑ¡”Í…µ”‰…Í•±¥¹”½Ñ…É•Ð½Ù•ÉÍ¥½¸4(€€€…É”Í­¥ÁÁ•°ÍÕ•ÍÍ™Õ°Ñ…Í­Ì…É”…ÁÁ•¹‘•¥µµ•‘¥…Ñ•±ä°…¹ÁÉ½Ù¥‘•È½ÕÑ…•Ì4(€€€±•…Ù”Ñ¡”©½ˆ…ÌÁ…ÉÑ¥…±}™…¥±•‘€¥¹ÍÑ•…½˜ÁÉ•Ñ•¹‘¥¹œ¥Ð¥Ì‘½¹”¸4(€€€€ˆˆˆ4(€€€‘•°©½‰}Á…Ñ €€Œ¡¥ÍÑ½Éä½˜ÅÕ•Õ•©½‰Ì¥Ì…ÁÁ•¹µ½¹±äìÕÉÉ•¹Ñ}©½ˆ¥ÌÑ¡”Ý½É­•ÈÕÉÍ½È¸4(€€€ÕÉÉ•¹Ð€ôA…Ñ ¡ÕÉÉ•¹Ñ}©½‰}Á…Ñ ½ÈUII9Q}=	MIYQ%=9})=	}%1¤4(€€€¡¥ÍÐ€ôA…Ñ ¡¡¥ÍÑ½Éå}Á…Ñ ½È=	MIYQ%=9}QM-M}%1¤4(€€€ÕÉÉ•¹Ñ}Ñ…Í­Ì€ôA…Ñ ¡ÕÉÉ•¹Ñ}Ñ…Í­Í}Á…Ñ ½ÈUII9Q}QM-M}%1¤4(€€€©½ˆ€ô©½ˆ½È}É•…‘}©Í½¸¡ÕÉÉ•¹Ð¤4(€€€¥˜¹½Ð©½ˆè4(€€€€€€€±½•È¹¥¹™¼ ‰žêÿ¢ž–¾’îï–*„èƒš^ƒ–ú–’žB©½ˆˆ¤4(€€€€€€€É•ÑÕÉ¸ì‰ÍÑ…ÑÕÌˆè€‰¹½}©½ˆˆ°€‰•¹•É…Ñ•ˆè€À°€‰ÝÉ¥ÑÑ•¸ˆè€À°€‰Í­¥ÁÁ•ˆè€Áô4(€€€Á…å±½…‘}Á…Ñ €ô©½ˆ¹•Ð ‰Á…å±½…‘}Á…Ñ ˆ¤4(€€€Á…å±½…€ô}É•…‘}©Í½¸¡Á…å±½…‘}Á…Ñ ¤¥˜Á…å±½…‘}Á…Ñ •±Í”9½¹”4(€€€¥˜¹½ÐÁ…å±½…è4(€€€€€€€±½•È¹Ý…É¹¥¹œ ‰žêÿ¢ž–¾’îï–*„è©½ˆÁ…å±½…ƒ’â7–>¿¢¾ì³¢ÞÏ¢þè€•Ìˆ°Á…å±½…‘}Á…Ñ ¤4(€€€€€€€Í¹…À€ô}©½‰}Í¹…ÁÍ¡½Ð 4(€€€€€€€€€€€©½ˆ°4(€€€€€€€€€€€ÍÑ…ÑÕÌô‰µ¥ÍÍ¥¹}Á…å±½…ˆ°4(€€€€€€€€€€€‰…Í•±¥¹”õÍÑÈ¡©½ˆ¹•Ð ‰‰…Í•±¥¹•}ÑÉ…‘•}‘…Ñ”ˆ¤½È€ˆˆ¤°4(€€€€€€€€€€€Ñ…É•ÐõÍÑÈ¡©½ˆ¹•Ð ‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ”ˆ¤½È€ˆˆ¤°4(€€€€€€€€€€€Á±…¹}Ù•ÉÍ¥½¸õÍÑÈ¡©½ˆ¹•Ð ‰Á±…¹}Ù•ÉÍ¥½¸ˆ¤½ÈU1Q}A19}YIM%=8¤°4(€€€€€€€€€€€Ñ…Í­}½‘•Ìõ±¥ÍÐ¡©½ˆ¹•Ð ‰Ñ…Í­}½‘•Ìˆ¤½Èmt¤°4(€€€€€€€€€€€‘½¹•}½‘•Ìõ±¥ÍÐ¡©½ˆ¹•Ð ‰‘½¹•}½‘•Ìˆ¤½Èmt¤°4(€€€€€€€€€€€É•µ…¥¹¥¹}½‘•Ìõ±¥ÍÐ¡©½ˆ¹•Ð ‰É•µ…¥¹¥¹}½‘•Ìˆ¤½Èmt¤°4(€€€€€€€€€€€ÍÑ…ÑÌõì‰•¹•É…Ñ•ˆè€À°€‰ÝÉ¥ÑÑ•¸ˆè€À°€‰Í­¥ÁÁ•ˆè€À°€‰ÕÉÉ•¹Ðˆè€Áô°4(€€€€€€€€€€€•ÉÉ½Èõì‰ÑåÁ”ˆè€‰µ¥ÍÍ¥¹}Á…å±½…ˆ°€‰µ•ÍÍ…”ˆèÍÑÈ¡Á…å±½…‘}Á…Ñ ½È€ˆˆ¥ô°4(€€€€€€€€¤4(€€€€€€€}ÝÉ¥Ñ•}©Í½¸¡ÕÉÉ•¹Ð°Í¹…À¤4(€€€€€€€É•ÑÕÉ¸ì4(€€€€€€€€€€€€‰ÍÑ…ÑÕÌˆè€‰µ¥ÍÍ¥¹}Á…å±½…ˆ°4(€€€€€€€€€€€€‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ”ˆèÍÑÈ¡©½ˆ¹•Ð ‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ”ˆ¤½È€ˆˆ¤°4(€€€€€€€€€€€€‰•¹•É…Ñ•ˆè€À°4(€€€€€€€€€€€€‰ÝÉ¥ÑÑ•¸ˆè€À°4(€€€€€€€€€€€€‰Í­¥ÁÁ•ˆè€À°4(€€€€€€€ô4(4(€€€‰…Í•±¥¹”€ôÍÑÈ¡©½ˆ¹•Ð ‰‰…Í•±¥¹•}ÑÉ…‘•}‘…Ñ”ˆ¤½È€ ¡Á…å±½…¹•Ð ‰µ…É­•Ñ}½Ù•ÉÙ¥•Üˆ¤½Èíô¤¹•Ð ‰ÑÉ…‘•}‘…Ñ”ˆ¤¤½È€ˆˆ¤¹ÍÑÉ¥À ¤4(€€€Ñ…É•Ð€ôÍÑÈ¡©½ˆ¹•Ð ‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ”ˆ¤½È€ˆˆ¤¹ÍÑÉ¥À ¤4(€€€Á±…¹}Ù•ÉÍ¥½¸€ôÍÑÈ¡©½ˆ¹•Ð ‰Á±…¹}Ù•ÉÍ¥½¸ˆ¤½ÈU1Q}A19}YIM%=8¤¹ÍÑÉ¥À ¤4(€€€Ñ…Í­}½‘•Ì€ôÍ•±•Ñ}½‰Í•ÉÙ…Ñ¥½¹}Ñ…Í­}½‘•Ì¡Á…å±½…¤4(€€€¥˜¥Í¥¹ÍÑ…¹”¡©½ˆ¹•Ð ‰Ñ…Í­}½‘•Ìˆ¤°±¥ÍÐ¤è4(€€€€€€€™É•Í¡¹•ÍÍ}…±±½Ý•€ôì4(€€€€€€€€€€€ÍÑÈ¡½‘”¤¹ÍÑÉ¥À ¤™½È½‘”¥¸©½‰l‰Ñ…Í­}½‘•Ì‰t¥˜ÍÑÈ¡½‘”¤¹ÍÑÉ¥À ¤4(€€€€€€€ô4(€€€€€€€Ñ…Í­}½‘•Ì€ôm½‘”™½È½‘”¥¸Ñ…Í­}½‘•Ì¥˜½‘”¥¸™É•Í¡¹•ÍÍ}…±±½Ý•‘t4(€€€•á¥ÍÑ¥¹}½‘•Ì€ô}•á¥ÍÑ¥¹}Ñ…Í­}½‘•Ì¡¡¥ÍÐ°‰…Í•±¥¹”°Ñ…É•Ð°Á±…¹}Ù•ÉÍ¥½¸¤4(€€€‘½¹•}½‘•Ì€ômŒ™½ÈŒ¥¸Ñ…Í­}½‘•Ì¥˜Œ¥¸•á¥ÍÑ¥¹}½‘•Ít4(€€€Á•¹‘¥¹}½‘•Ì€ômŒ™½ÈŒ¥¸Ñ…Í­}½‘•Ì¥˜Œ¹½Ð¥¸•á¥ÍÑ¥¹}½‘•Ít4(4(€€€¥˜¹½ÐÁ•¹‘¥¹}½‘•Ìè4(€€€€€€€ÕÉÉ•¹Ñ}½Õ¹Ð€ô}µ…Ñ•É¥…±¥é•}ÕÉÉ•¹Ñ}Ñ…Í­Ì 4(€€€€€€€€€€€¡¥ÍÐ°ÕÉÉ•¹Ñ}Ñ…Í­Ì°Ñ…É•Ñ}‘…Ñ•ÌõmÑ…É•Ñt¥˜Ñ…É•Ð•±Í”9½¹”°4(€€€€€€€€€€€…±±½Ý•‘}½‘•ÌõÑ…Í­}½‘•Ì°4(€€€€€€€€¤4(€€€€€€€ÍÑ…ÑÌ€ôì‰•¹•É…Ñ•ˆè€À°€‰ÝÉ¥ÑÑ•¸ˆè€À°€‰Í­¥ÁÁ•ˆè€À°€‰ÕÉÉ•¹ÐˆèÕÉÉ•¹Ñ}½Õ¹Ð°€‰•á¥ÍÑ¥¹œˆè±•¸¡‘½¹•}½‘•Ì¥ô4(€€€€€€€Í¹…À€ô}©½‰}Í¹…ÁÍ¡½Ð 4(€€€€€€€€€€€©½ˆ°4(€€€€€€€€€€€ÍÑ…ÑÕÌô‰‘½¹”ˆ°4(€€€€€€€€€€€‰…Í•±¥¹”õ‰…Í•±¥¹”°4(€€€€€€€€€€€Ñ…É•ÐõÑ…É•Ð°4(€€€€€€€€€€€Á±…¹}Ù•ÉÍ¥½¸õÁ±…¹}Ù•ÉÍ¥½¸°4(€€€€€€€€€€€Ñ…Í­}½‘•ÌõÑ…Í­}½‘•Ì°4(€€€€€€€€€€€‘½¹•}½‘•Ìõ‘½¹•}½‘•Ì°4(€€€€€€€€€€€É•µ…¥¹¥¹}½‘•Ìõmt°4(€€€€€€€€€€€ÍÑ…ÑÌõÍÑ…ÑÌ°4(€€€€€€€€¤4(€€€€€€€}ÝÉ¥Ñ•}©Í½¸¡ÕÉÉ•¹Ð°Í¹…À¤4(€€€€€€€±½•È¹¥¹™¼ ‰µ±¥¹”½‰Í•ÉÙ…Ñ¥½¸Ý½É­•Èè…±°€•ÌÑ…Í­Ì…±É•…‘ä•á¥ÍÐ°¹¼µ½Àˆ°±•¸¡‘½¹•}½‘•Ì¤¤4(€€€€€€€É•ÑÕÉ¸ì4(€€€€€€€€€€€€‰ÍÑ…ÑÕÌˆè€‰‘½¹”ˆ°4(€€€€€€€€€€€€‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ”ˆèÑ…É•Ð°4(€€€€€€€€€€€€¨©ÍÑ…ÑÌ°4(€€€€€€€€€€€€‰Ñ…Í­}½‘•Ìˆè±•¸¡Ñ…Í­}½‘•Ì¤°4(€€€€€€€€€€€€‰É•µ…¥¹¥¹œˆè€À°4(€€€€€€€ô4(4(€€€ÉÕ¹¹¥¹œ€ô}©½‰}Í¹…ÁÍ¡½Ð 4(€€€€€€€©½ˆ°4(€€€€€€€ÍÑ…ÑÕÌô‰ÉÕ¹¹¥¹œˆ°4(€€€€€€€‰…Í•±¥¹”õ‰…Í•±¥¹”°4(€€€€€€€Ñ…É•ÐõÑ…É•Ð°4(€€€€€€€Á±…¹}Ù•ÉÍ¥½¸õÁ±…¹}Ù•ÉÍ¥½¸°4(€€€€€€€Ñ…Í­}½‘•ÌõÑ…Í­}½‘•Ì°4(€€€€€€€‘½¹•}½‘•Ìõ‘½¹•}½‘•Ì°4(€€€€€€€É•µ…¥¹¥¹}½‘•ÌõÁ•¹‘¥¹}½‘•Ì°4(€€€€€€€ÍÑ…ÑÌõì‰•¹•É…Ñ•ˆè€À°€‰ÝÉ¥ÑÑ•¸ˆè€À°€‰Í­¥ÁÁ•ˆè€À°€‰ÕÉÉ•¹Ðˆè±•¸¡‘½¹•}½‘•Ì¤°€‰•á¥ÍÑ¥¹œˆè±•¸¡‘½¹•}½‘•Ì¥ô°4(€€€€¤4(€€€ÉÕ¹¹¥¹œ¹Í•Ñ‘•™…Õ±Ð ‰ÍÑ…ÉÑ•‘}…Ðˆ°}¹½Ý}¥Í¼ ¤¤4(€€€ÉÕ¹¹¥¹l‰±…ÍÑ}ÉÕ¹}ÍÑ…ÉÑ•‘}…Ð‰t€ô}¹½Ý}¥Í¼ ¤4(€€€}ÝÉ¥Ñ•}©Í½¸¡ÕÉÉ•¹Ð°ÉÕ¹¹¥¹œ¤4(4(€€€•¹•É…Ñ•€ô€À4(€€€ÝÉ¥ÑÑ•¸€ô€À4(€€€Í­¥ÁÁ•€ô€À4(€€€ÕÉÉ•¹Ñ}½Õ¹Ð€ô}µ…Ñ•É¥…±¥é•}ÕÉÉ•¹Ñ}Ñ…Í­Ì 4(€€€€€€€¡¥ÍÐ°ÕÉÉ•¹Ñ}Ñ…Í­Ì°Ñ…É•Ñ}‘…Ñ•ÌõmÑ…É•Ñt¥˜Ñ…É•Ð•±Í”9½¹”°4(€€€€€€€…±±½Ý•‘}½‘•ÌõÑ…Í­}½‘•Ì°4(€€€€¤4(€€€™…¥±ÕÉ•Ìè1¥ÍÑm¥ÑmÍÑÈ°¹åut€ômt4(4(€€€‘•˜}É•½É‘}Ñ…Í¬¡Ñ…Í¬è¥ÑmÍÑÈ°¹åt¤€´ø9½¹”è4(€€€€€€€¹½¹±½…°•¹•É…Ñ•°ÝÉ¥ÑÑ•¸°Í­¥ÁÁ•°ÕÉÉ•¹Ñ}½Õ¹Ð4(€€€€€€€•¹•É…Ñ•€¬ô€Ä4(€€€€€€€ÍÑ…ÑÌ€ôÉ•½É‘}½‰Í•ÉÙ…Ñ¥½¹}Ñ…Í­Ì 4(€€€€€€€€€€€mÑ…Í­t°¡¥ÍÑ½Éå}Á…Ñ õ¡¥ÍÐ°ÕÉÉ•¹Ñ}Á…Ñ õÕÉÉ•¹Ñ}Ñ…Í­Ì°4(€€€€€€€€€€€…Ñ¥Ù•}½‘•ÌõÑ…Í­}½‘•Ì°4(€€€€€€€€¤4(€€€€€€€ÝÉ¥ÑÑ•¸€¬ô¥¹Ð¡ÍÑ…ÑÌ¹•Ð ‰ÝÉ¥ÑÑ•¸ˆ°€À¤¤4(€€€€€€€Í­¥ÁÁ•€¬ô¥¹Ð¡ÍÑ…ÑÌ¹•Ð ‰Í­¥ÁÁ•ˆ°€À¤¤4(€€€€€€€ÕÉÉ•¹Ñ}½Õ¹Ð€ô¥¹Ð¡ÍÑ…ÑÌ¹•Ð ‰ÕÉÉ•¹Ðˆ°ÕÉÉ•¹Ñ}½Õ¹Ð¤¤4(4(€€€‘•˜}É•½É‘}™…¥±ÕÉ”¡½‘”èÍÑÈ°É•…Í½¸èÍÑÈ°‘•Ñ…¥°è¥ÑmÍÑÈ°¹åt¤€´ø9½¹”è4(€€€€€€€™…¥±ÕÉ•Ì¹…ÁÁ•¹¡ì‰½‘”ˆè½‘”°€‰É•…Í½¸ˆèÉ•…Í½¸°€‰‘•Ñ…¥°ˆè‘•Ñ…¥°°€‰…Ðˆè}¹½Ý}¥Í¼ ¥ô¤4(4(€€€ÑÉäè4(€€€€€€€•¹•É…Ñ•}½‰Í•ÉÙ…Ñ¥½¹}Ñ…Í­Ì 4(€€€€€€€€€€€Á…å±½…°4(€€€€€€€€€€€Ñ…É•Ð°4(€€€€€€€€€€€}ÁÉ•‘¥Ñ¥½¹Ìõ©½ˆ¹•Ð ‰}ÁÉ•‘¥Ñ¥½¹Ìˆ¤½Èmt°4(€€€€€€€€€€€Ñ…Í­}½‘•ÌõÁ•¹‘¥¹}½‘•Ì°4(€€€€€€€€€€€Á±…¹¹•É}™Õ¹ŒõÁ±…¹¹•É}™Õ¹Œ°4(€€€€€€€€€€€Á±…¹}Ù•ÉÍ¥½¸õÁ±…¹}Ù•ÉÍ¥½¸°4(€€€€€€€€€€€Ñ…Í­}…±±‰…¬õ}É•½É‘}Ñ…Í¬°4(€€€€€€€€€€€™…¥±ÕÉ•}…±±‰…¬õ}É•½É‘}™…¥±ÕÉ”°4(€€€€€€€€¤4(€€€•á•ÁÐ½‘•á…±±ÉÉ½È…Ì”è4(€€€€€€€•á¥ÍÑ¥¹}…™Ñ•È€ô}•á¥ÍÑ¥¹}Ñ…Í­}½‘•Ì¡¡¥ÍÐ°‰…Í•±¥¹”°Ñ…É•Ð°Á±…¹}Ù•ÉÍ¥½¸¤4(€€€€€€€‘½¹•}…™Ñ•È€ômŒ™½ÈŒ¥¸Ñ…Í­}½‘•Ì¥˜Œ¥¸•á¥ÍÑ¥¹}…™Ñ•Ét4(€€€€€€€É•µ…¥¹¥¹}…™Ñ•È€ômŒ™½ÈŒ¥¸Ñ…Í­}½‘•Ì¥˜Œ¹½Ð¥¸•á¥ÍÑ¥¹}…™Ñ•Ét4(€€€€€€€ÕÉÉ•¹Ñ}½Õ¹Ð€ô}µ…Ñ•É¥…±¥é•}ÕÉÉ•¹Ñ}Ñ…Í­Ì 4(€€€€€€€€€€€¡¥ÍÐ°ÕÉÉ•¹Ñ}Ñ…Í­Ì°Ñ…É•Ñ}‘…Ñ•ÌõmÑ…É•Ñt¥˜Ñ…É•Ð•±Í”9½¹”°4(€€€€€€€€€€€…±±½Ý•‘}½‘•ÌõÑ…Í­}½‘•Ì°4(€€€€€€€€¤4(€€€€€€€ÍÑ…ÑÌ€ôì4(€€€€€€€€€€€€‰•¹•É…Ñ•ˆè•¹•É…Ñ•°4(€€€€€€€€€€€€‰ÝÉ¥ÑÑ•¸ˆèÝÉ¥ÑÑ•¸°4(€€€€€€€€€€€€‰Í­¥ÁÁ•ˆèÍ­¥ÁÁ•°4(€€€€€€€€€€€€‰ÕÉÉ•¹ÐˆèÕÉÉ•¹Ñ}½Õ¹Ð°4(€€€€€€€€€€€€‰•á¥ÍÑ¥¹œˆè±•¸¡‘½¹•}…™Ñ•È¤°4(€€€€€€€ô4(€€€€€€€•ÉÉ½È€ôì4(€€€€€€€€€€€€‰ÑåÁ”ˆè•Ñ…ÑÑÈ¡”°€‰•ÉÉ½É}ÑåÁ”ˆ°€‰½‘•á}•ÉÉ½Èˆ¤°4(€€€€€€€€€€€€‰ÍÑ…ÑÕÍ}½‘”ˆè•Ñ…ÑÑÈ¡”°€‰ÍÑ…ÑÕÍ}½‘”ˆ°9½¹”¤°4(€€€€€€€€€€€€‰½‘”ˆè•Ñ…ÑÑÈ¡”°€‰½‘”ˆ°9½¹”¤°4(€€€€€€€€€€€€‰É•ÑÉå…‰±”ˆè•Ñ…ÑÑÈ¡”°€‰É•ÑÉå…‰±”ˆ°…±Í”¤°4(€€€€€€€€€€€€‰™…¥±•‘}½‘”ˆè•Ñ…ÑÑÈ¡”°€‰ÍÑ½­}½‘”ˆ°9½¹”¤°4(€€€€€€€€€€€€‰µ•ÍÍ…”ˆèÍÑÈ¡”¥lèÌÀÁt°4(€€€€€€€ô4(€€€€€€€Í¹…À€ô}©½‰}Í¹…ÁÍ¡½Ð 4(€€€€€€€€€€€©½ˆ°4(€€€€€€€€€€€ÍÑ…ÑÕÌô‰Á…ÉÑ¥…±}™…¥±•ˆ°4(€€€€€€€€€€€‰…Í•±¥¹”õ‰…Í•±¥¹”°4(€€€€€€€€€€€Ñ…É•ÐõÑ…É•Ð°4(€€€€€€€€€€€Á±…¹}Ù•ÉÍ¥½¸õÁ±…¹}Ù•ÉÍ¥½¸°4(€€€€€€€€€€€Ñ…Í­}½‘•ÌõÑ…Í­}½‘•Ì°4(€€€€€€€€€€€‘½¹•}½‘•Ìõ‘½¹•}…™Ñ•È°4(€€€€€€€€€€€É•µ…¥¹¥¹}½‘•ÌõÉ•µ…¥¹¥¹}…™Ñ•È°4(€€€€€€€€€€€ÍÑ…ÑÌõÍÑ…ÑÌ°4(€€€€€€€€€€€™…¥±ÕÉ•Ìõ™…¥±ÕÉ•Ì°4(€€€€€€€€€€€•ÉÉ½Èõ•ÉÉ½È°4(€€€€€€€€¤4(€€€€€€€}ÝÉ¥Ñ•}©Í½¸¡ÕÉÉ•¹Ð°Í¹…À¤4(€€€€€€€±½•È¹Ý…É¹¥¹œ 4(€€€€€€€€€€€€‰µ±¥¹”½‰Í•ÉÙ…Ñ¥½¸Ý½É­•ÈÁ…ÉÑ¥…±}™…¥±•è•¹•É…Ñ•ô•ÌÝÉ¥ÑÑ•¸ô•ÌÉ•µ…¥¹¥¹œô•Ì™…¥±•‘}½‘”ô•Ì•ÉÉ½É}ÑåÁ”ô•Ìˆ°4(€€€€€€€€€€€•¹•É…Ñ•°4(€€€€€€€€€€€ÝÉ¥ÑÑ•¸°4(€€€€€€€€€€€±•¸¡É•µ…¥¹¥¹}…™Ñ•È¤°4(€€€€€€€€€€€•ÉÉ½È¹•Ð ‰™…¥±•‘}½‘”ˆ¤°4(€€€€€€€€€€€•ÉÉ½È¹•Ð ‰ÑåÁ”ˆ¤°4(€€€€€€€€¤4(€€€€€€€É•ÑÕÉ¸ì4(€€€€€€€€€€€€‰ÍÑ…ÑÕÌˆè€‰Á…ÉÑ¥…±}™…¥±•ˆ°4(€€€€€€€€€€€€‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ”ˆèÑ…É•Ð°4(€€€€€€€€€€€€¨©ÍÑ…ÑÌ°4(€€€€€€€€€€€€‰Ñ…Í­}½‘•Ìˆè±•¸¡Ñ…Í­}½‘•Ì¤°4(€€€€€€€€€€€€‰É•µ…¥¹¥¹œˆè±•¸¡É•µ…¥¹¥¹}…™Ñ•È¤°4(€€€€€€€€€€€€‰•ÉÉ½Èˆè•ÉÉ½È°4(€€€€€€€ô4(4(€€€•á¥ÍÑ¥¹}…™Ñ•È€ô}•á¥ÍÑ¥¹}Ñ…Í­}½‘•Ì¡¡¥ÍÐ°‰…Í•±¥¹”°Ñ…É•Ð°Á±…¹}Ù•ÉÍ¥½¸¤4(€€€‘½¹•}…™Ñ•È€ômŒ™½ÈŒ¥¸Ñ…Í­}½‘•Ì¥˜Œ¥¸•á¥ÍÑ¥¹}…™Ñ•Ét4(€€€É•µ…¥¹¥¹}…™Ñ•È€ômŒ™½ÈŒ¥¸Ñ…Í­}½‘•Ì¥˜Œ¹½Ð¥¸•á¥ÍÑ¥¹}…™Ñ•Ét4(€€€ÕÉÉ•¹Ñ}½Õ¹Ð€ô}µ…Ñ•É¥…±¥é•}ÕÉÉ•¹Ñ}Ñ…Í­Ì 4(€€€€€€€¡¥ÍÐ°ÕÉÉ•¹Ñ}Ñ…Í­Ì°Ñ…É•Ñ}‘…Ñ•ÌõmÑ…É•Ñt¥˜Ñ…É•Ð•±Í”9½¹”°4(€€€€€€€…±±½Ý•‘}½‘•ÌõÑ…Í­}½‘•Ì°4(€€€€¤4(€€€ÍÑ…ÑÕÌ€ô€‰‘½¹”ˆ¥˜¹½ÐÉ•µ…¥¹¥¹}…™Ñ•È•±Í”€‰Á…ÉÑ¥…±}‘½¹”ˆ4(€€€ÍÑ…ÑÌ€ôì4(€€€€€€€€‰•¹•É…Ñ•ˆè•¹•É…Ñ•°4(€€€€€€€€‰ÝÉ¥ÑÑ•¸ˆèÝÉ¥ÑÑ•¸°4(€€€€€€€€‰Í­¥ÁÁ•ˆèÍ­¥ÁÁ•°4(€€€€€€€€‰ÕÉÉ•¹ÐˆèÕÉÉ•¹Ñ}½Õ¹Ð°4(€€€€€€€€‰•á¥ÍÑ¥¹œˆè±•¸¡‘½¹•}…™Ñ•È¤°4(€€€ô4(€€€Í¹…À€ô}©½‰}Í¹…ÁÍ¡½Ð 4(€€€€€€€©½ˆ°4(€€€€€€€ÍÑ…ÑÕÌõÍÑ…ÑÕÌ°4(€€€€€€€‰…Í•±¥¹”õ‰…Í•±¥¹”°4(€€€€€€€Ñ…É•ÐõÑ…É•Ð°4(€€€€€€€Á±…¹}Ù•ÉÍ¥½¸õÁ±…¹}Ù•ÉÍ¥½¸°4(€€€€€€€Ñ…Í­}½‘•ÌõÑ…Í­}½‘•Ì°4(€€€€€€€‘½¹•}½‘•Ìõ‘½¹•}…™Ñ•È°4(€€€€€€€É•µ…¥¹¥¹}½‘•ÌõÉ•µ…¥¹¥¹}…™Ñ•È°4(€€€€€€€ÍÑ…ÑÌõÍÑ…ÑÌ°4(€€€€€€€™…¥±ÕÉ•Ìõ™…¥±ÕÉ•Ì°4(€€€€¤4(€€€}ÝÉ¥Ñ•}©Í½¸¡ÕÉÉ•¹Ð°Í¹…À¤4(€€€É•ÑÕÉ¸ì4(€€€€€€€€‰ÍÑ…ÑÕÌˆèÍÑ…ÑÕÌ°4(€€€€€€€€‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ”ˆèÑ…É•Ð°4(€€€€€€€€¨©ÍÑ…ÑÌ°4(€€€€€€€€‰Ñ…Í­}½‘•Ìˆè±•¸¡Ñ…Í­}½‘•Ì¤°4(€€€€€€€€‰É•µ…¥¹¥¹œˆè±•¸¡É•µ…¥¹¥¹}…™Ñ•È¤°4(€€€ô4(4(4)‘•˜É•½É‘}½‰Í•ÉÙ…Ñ¥½¹}Ñ…Í­Ì¡Ñ…Í­Ìè%Ñ•É…‰±•m¥ÑmÍÑÈ°¹åut°€¨°4(€€€€€€€€€€€€€€€€€€€€€€€€€€€€¡¥ÍÑ½Éå}Á…Ñ õ9½¹”°4(€€€€€€€€€€€€€€€€€€€€€€€€€€€€ÕÉÉ•¹Ñ}Á…Ñ õ9½¹”°4(€€€€€€€€€€€€€€€€€€€€€€€€€€€€…Ñ¥Ù•}½‘•Ìè=ÁÑ¥½¹…±m%Ñ•É…‰±•mÍÑÉut€ô9½¹”¤€´ø¥ÑmÍÑÈ°¥¹Ñtè4(€€€€ˆˆ‰%‘•µÁ½Ñ•¹Ñ±ä…ÁÁ•¹µ±¥¹”Ñ…Í­Ì…¹µ…Ñ•É¥…±¥é”ÕÉÉ•¹Ð…Ñ¥Ù”Ñ…Í­Ì¸ˆˆˆ4(€€€¡¥ÍÐ€ôA…Ñ ¡¡¥ÍÑ½Éå}Á…Ñ ½È=	MIYQ%=9}QM-M}%1¤4(€€€ÕÉÉ•¹Ð€ôA…Ñ ¡ÕÉÉ•¹Ñ}Á…Ñ ½ÈUII9Q}QM-M}%1¤4(€€€É½ÝÌ€ômÐ™½ÈÐ¥¸Ñ…Í­Ì¥˜¥Í¥¹ÍÑ…¹”¡Ð°‘¥Ð¥t4(€€€•á¥ÍÑ¥¹œ€ôíÈ¹•Ð ‰Ñ…Í­}¥ˆ¤™½ÈÈ¥¸}É•…‘}©Í½¹°¡¡¥ÍÐ¥ô4(€€€ÝÉ¥ÑÑ•¸€ôÍ­¥ÁÁ•€ô€À4(€€€™½ÈÑ…Í¬¥¸É½ÝÌè4(€€€€€€€Ñ¥€ôÑ…Í¬¹•Ð ‰Ñ…Í­}¥ˆ¤4(€€€€€€€¥˜¹½ÐÑ¥½ÈÑ¥¥¸•á¥ÍÑ¥¹œè4(€€€€€€€€€€€Í­¥ÁÁ•€¬ô€Ä4(€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€}…ÁÁ•¹‘}©Í½¹°¡¡¥ÍÐ°Ñ…Í¬¤4(€€€€€€€•á¥ÍÑ¥¹œ¹…‘¡Ñ¥¤4(€€€€€€€ÝÉ¥ÑÑ•¸€¬ô€Ä4(€€€Ñ…É•Ñ}‘…Ñ•Ì€ôÍ½ÉÑ•¡íÍÑÈ¡Ð¹•Ð ‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ”ˆ¤½È€ˆˆ¤™½ÈÐ¥¸É½ÝÌ¥˜Ð¹•Ð ‰Ñ…É•Ñ}ÑÉ…‘•}‘…Ñ”ˆ¥ô¤4(€€€ÕÉÉ•¹Ñ}½Õ¹Ð€ô€À4(€€€¥˜Ñ…É•Ñ}‘…Ñ•Ìè4(€€€€€€€ÕÉÉ•¹Ñ}½Õ¹Ð€ô}µ…Ñ•É¥…±¥é•}ÕÉÉ•¹Ñ}Ñ…Í­Ì 4(€€€€€€€€€€€¡¥ÍÐ°ÕÉÉ•¹Ð°Ñ…É•Ñ}‘…Ñ•ÌõÑ…É•Ñ}‘…Ñ•Ì°4(€€€€€€€€€€€…±±½Ý•‘}½‘•Ìõ…Ñ¥Ù•}½‘•Ì°4(€€€€€€€€¤4(€€€¥˜ÝÉ¥ÑÑ•¸è4(€€€€€€€±½•È¹¥¹™¼ ‰žêÿ¢ž–¾’îï–*‡–g–”€•Ìƒšv„ •Ì¤ˆ°ÝÉ¥ÑÑ•¸°¡¥ÍÐ¤4(€€€É•ÑÕÉ¸ì‰ÝÉ¥ÑÑ•¸ˆèÝÉ¥ÑÑ•¸°€‰Í­¥ÁÁ•ˆèÍ­¥ÁÁ•°€‰ÕÉÉ•¹ÐˆèÕÉÉ•¹Ñ}½Õ¹Ñô4(