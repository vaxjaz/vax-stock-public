# -*- coding: utf-8 -*-
"""D线 forecast 数据层: 盘中触发结构化预测的冻结写入(append-only)。

D线 = 盘中预测告警/观察层: 盘中触发那一刻, 把 codex 的结构化研判
(verdict/direction/confidence/horizon/falsify_if)连同**当时输入**(T-1 基准+lite 快照+regime)一起
冻结入库, 供日后 T+k 回测归因。

铁律(CLAUDE.md §7):
  - 预测先于结果冻结、append-only(只增不改); inputs_ref 必须存当时输入(回测归因命门)。
  - trade_date 锚触发当日交易日(由调用方从触发数据取, 非 now()); 缺则跳过不写(不臆造日期)。
  - 本 PR 只做"预测冻结写入"; 结果回填(forecast_results.jsonl + T+k)留后续 PR。
  - D线与 B线(eval 全截面)分开存/分开写入时点;D线不可冒充 B线全样本。
"""

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from vaxstock import config

logger = logging.getLogger(__name__)

FORECAST_DIR = config.STATE_DIR / "forecast"
FORECASTS_FILE = FORECAST_DIR / "forecasts.jsonl"
DLINE_PLAN_VERSION = "d_observe_llm_v2"
SCHEMA_VERSION = 1


def _now_iso() -> str:
    """生成时刻戳(ISO); 仅作记录时刻, 非交易日基准(§9.1)。"""
    return dt.datetime.now().isoformat(timespec="seconds")


def _append_jsonl(path, row) -> None:
    """原子 append 一行 JSON(同 eval_recorder 写法; 只增不改)。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _read_jsonl(path) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                logger.warning("forecast markdown: jsonl parse failed, skip: %s", line[:80])
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _as_float(value) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_number(value, digits: int = 2, suffix: str = "", signed: bool = False) -> str:
    num = _as_float(value)
    if num is None:
        return "\u5f85\u83b7\u53d6"
    sign = "+" if signed and num > 0 else ""
    return f"{sign}{num:.{digits}f}{suffix}"


def _fmt_pct(value, digits: int = 2, signed: bool = True) -> str:
    return _fmt_number(value, digits=digits, suffix="%", signed=signed)


def _fmt_confidence(value) -> str:
    num = _as_float(value)
    if num is None:
        return "\u5f85\u83b7\u53d6"
    if abs(num) <= 1:
        num *= 100
    return f"{num:.0f}%"


def _fmt_amount_yi(values: Dict[str, Any], quote: Dict[str, Any]) -> str:
    amount_yi = _as_float((values or {}).get("amount_yi"))
    if amount_yi is None:
        amount = _as_float((quote or {}).get("amount"))
        amount_yi = None if amount is None else amount / 1e8
    return _fmt_number(amount_yi, digits=2, suffix="\u4ebf", signed=False)


def _short_text(value, limit: int = 180) -> str:
    text = str(value or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[:limit - 1].rstrip() + "..."


def _is_dline_v2_row(row: Dict[str, Any]) -> bool:
    inputs_ref = (row or {}).get("inputs_ref") or {}
    structured = (row or {}).get("structured") or {}
    return (
        structured.get("source") == "dline_task_blueprint"
        and inputs_ref.get("dline_plan_version") == DLINE_PLAN_VERSION
    )


def _dline_rows(rows: List[Dict[str, Any]], trade_date: Optional[str] = None) -> List[Dict[str, Any]]:
    target = str(trade_date).strip() if trade_date else None
    out = []
    for row in rows:
        if not _is_dline_v2_row(row):
            continue
        if target and str(row.get("trade_date") or "").strip() != target:
            continue
        out.append(row)
    return sorted(out, key=lambda r: (str(r.get("trade_date") or ""), str(r.get("forecast_ts") or ""), str(r.get("code") or "")))


def _latest_dline_trade_date(rows: List[Dict[str, Any]]) -> Optional[str]:
    dates = [str(r.get("trade_date") or "").strip() for r in rows if _is_dline_v2_row(r) and r.get("trade_date")]
    return sorted(dates)[-1] if dates else None


def _date_file_token(trade_date: str) -> str:
    token = "".join(ch for ch in str(trade_date or "") if ch.isalnum() or ch in ("-", "_"))
    return token or "unknown"


def _trigger_paths(base_path: Path, trade_date: Optional[str], current_path=None, summary_dir=None) -> Dict[str, Optional[Path]]:
    current = Path(current_path) if current_path else base_path.with_name("current_triggers.md")
    summary = None
    if trade_date:
        parent = Path(summary_dir) if summary_dir else base_path.parent
        summary = parent / f"trigger_summary_{_date_file_token(trade_date)}.md"
    return {"current": current, "summary": summary}


def _missing() -> str:
    return "\u5f85\u83b7\u53d6"


def render_trigger_summary_markdown(rows: List[Dict[str, Any]], trade_date: Optional[str] = None) -> str:
    """Render D-line v2 trigger rows from forecasts.jsonl into a readable digest.

    This is a derived markdown view only. It never mutates the append-only
    forecast rows and it does not evaluate future results.
    """
    selected = _dline_rows(rows, trade_date=trade_date)
    scope = str(trade_date or "\u5168\u90e8").strip()
    lines = [
        "# D\u7ebf\u76d8\u4e2d\u89e6\u53d1\u6c47\u603b",
        "",
        f"- updated_at: {_now_iso()}",
        f"- trade_date: {scope}",
        f"- triggers: {len(selected)}",
        f"- \u53e3\u5f84: \u4ec5\u6c47\u603b `forecasts.jsonl` \u4e2d `structured.source=dline_task_blueprint` \u4e14 `dline_plan_version={DLINE_PLAN_VERSION}` \u7684\u89e6\u53d1\u8bb0\u5f55\u3002",
        "- \u6570\u636e\u6e90: \u73b0\u4ef7/\u6da8\u8dcc\u5e45/\u632f\u5e45/\u6210\u4ea4\u989d\u6765\u81ea\u89e6\u53d1\u65f6 `quote_snapshot`; MA\u504f\u79bb\u6765\u81ea `trigger_values`; C\u7ebf\u4e3a `evidence_pack.C_prediction` \u539f\u59cb\u5b57\u6bb5; LLM\u5ba2\u89c2\u8bc4\u4ef7\u4e3a\u89e6\u53d1\u65f6\u5199\u5165\u7684 `reasoning`\u3002",
        "- \u8fb9\u754c: \u672c\u62a5\u544a\u53ea\u505a D\u7ebf\u89e6\u53d1\u590d\u76d8\u89c6\u56fe, \u4e0d\u7ed9\u4e70\u5356\u5efa\u8bae, \u4e0d\u81ea\u52a8\u8c03\u53c2\u3002",
        "",
    ]
    if not selected:
        lines.append("\u6682\u65e0 D\u7ebf v2 \u89e6\u53d1\u8bb0\u5f55\u3002")
        return "\n".join(lines).rstrip() + "\n"

    for idx, row in enumerate(selected, start=1):
        inputs_ref = row.get("inputs_ref") or {}
        quote = inputs_ref.get("quote_snapshot") or {}
        values = inputs_ref.get("trigger_values") or {}
        evidence = inputs_ref.get("evidence_pack") or {}
        c_pred = ((evidence.get("C_prediction") or {}).get("prediction") or {})
        blueprint = inputs_ref.get("trigger_blueprint") or {}
        trigger_type = blueprint.get("trigger_type") or (row.get("structured") or {}).get("verdict") or _missing()
        name = quote.get("name") or row.get("name") or ""
        code = row.get("code") or quote.get("code") or "N/A"
        title = f"{code} {name}".strip()
        lines += [
            f"## {idx}. {title}",
            "",
            f"- \u89e6\u53d1: {trigger_type} / severity={blueprint.get('severity') or _missing()} / fire_count={(row.get('structured') or {}).get('fire_count') or _missing()}",
            f"- \u65f6\u95f4: forecast_ts={row.get('forecast_ts') or _missing()}; trade_time={quote.get('trade_time') or _missing()}; trade_date={row.get('trade_date') or _missing()}",
            f"- \u5b9e\u65f6\u884c\u60c5: \u73b0\u4ef7={_fmt_number(quote.get('price'))}; \u6da8\u8dcc\u5e45={_fmt_pct(quote.get('change_pct'))}; \u632f\u5e45={_fmt_pct(quote.get('amplitude_pct'), signed=False)}; \u6210\u4ea4\u989d={_fmt_amount_yi(values, quote)}",
            f"- \u5747\u7ebf\u504f\u79bb: MA5={_fmt_pct(values.get('price_vs_ma5_pct'))}; MA20={_fmt_pct(values.get('price_vs_ma20_pct'))}; MA60={_fmt_pct(values.get('price_vs_ma60_pct'))}",
            f"- C\u7ebf\u539f\u59cb\u9884\u6d4b: action={c_pred.get('action') or _missing()}; direction={c_pred.get('direction') or _missing()}; confidence={_fmt_confidence(c_pred.get('confidence'))}",
            f"- \u89e6\u53d1\u4f9d\u636e: {_short_text(blueprint.get('why'), 260) or _missing()}",
            f"- LLM\u5ba2\u89c2\u8bc4\u4ef7: {_short_text(row.get('reasoning'), 360) or _missing()}",
            f"- C\u7ebf\u53cd\u54fa\u7ebf\u7d22: expected_feedback_to_c={_short_text(blueprint.get('expected_feedback_to_c'), 220) or _missing()}; baseline={inputs_ref.get('baseline_date') or _missing()}; task_id={inputs_ref.get('dline_task_id') or _missing()}; MA20\u89e6\u53d1\u4f4d\u7f6e={_fmt_pct(values.get('price_vs_ma20_pct'))}",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def refresh_trigger_markdown(trade_date: Optional[str] = None, *, forecasts_path=None,
                             current_path=None, summary_dir=None) -> Dict[str, Any]:
    """Regenerate current D-line trigger markdown and a date-specific summary."""
    path = Path(forecasts_path or FORECASTS_FILE)
    rows = _read_jsonl(path)
    target = str(trade_date).strip() if trade_date else _latest_dline_trade_date(rows)
    markdown = render_trigger_summary_markdown(rows, trade_date=target)
    paths = _trigger_paths(path, target, current_path=current_path, summary_dir=summary_dir)

    current = paths["current"]
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text(markdown, encoding="utf-8")

    summary = paths["summary"]
    if summary:
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text(markdown, encoding="utf-8")

    count = len(_dline_rows(rows, trade_date=target))
    return {
        "trade_date": target,
        "count": count,
        "current_path": str(current),
        "summary_path": str(summary) if summary else None,
    }

def record_forecast(code, trade_date, trigger_note, inputs_ref, structured,
                    reasoning, falsify_if) -> bool:
    """冻结写入一条盘中触发预测(append-only)。返回是否写入。

    inputs_ref: {baseline_date, t1_baseline, lite_snapshot, regime} —— 冻结当时输入(回测归因命门)。
    structured: {verdict, direction, confidence, horizon, thesis_tags, news_refs}。
    trade_date 缺失 -> warning + 跳过不写(不臆造日期, §9.1)。
    """
    if not trade_date:
        logger.warning(f"forecast 缺 trade_date(code={code}), 跳过不写(不臆造日期)")
        return False
    row = {
        "schema_version": SCHEMA_VERSION,
        "forecast_ts": _now_iso(),
        "trade_date": str(trade_date),
        "code": code,
        "trigger_note": trigger_note,
        "inputs_ref": inputs_ref,
        "structured": structured,
        "reasoning": reasoning,
        "falsify_if": falsify_if,
    }
    _append_jsonl(FORECASTS_FILE, row)
    if _is_dline_v2_row(row):
        try:
            refresh_trigger_markdown(trade_date)
        except Exception as exc:
            logger.warning("forecast markdown 刷新失败: %s: %s", type(exc).__name__, exc)
    logger.info(f"forecast 冻结: {trade_date} {code} "
                f"verdict={(structured or {}).get('verdict')} "
                f"dir={(structured or {}).get('direction')} "
                f"conf={(structured or {}).get('confidence')}")
    return True
