# -*- coding: utf-8 -*-
"""Regime audit writer.

Reads already-collected payload data and writes auditable regime evidence.
It does not fetch data and does not mutate regime state.
"""

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from vaxstock import config
from vaxstock.indicators.regime import explain_market_regime

logger = logging.getLogger(__name__)

EVAL_DIR = config.STATE_DIR / "eval"
REGIME_AUDIT_JSONL = EVAL_DIR / "regime_audit.jsonl"
SCHEMA_VERSION = 1


def _now_iso() -> str:
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
                logger.warning(f"regime audit jsonl 行解析失败, 跳过: {line[:60]}")
    return rows


def _append_jsonl(path, row) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def build_regime_audit(payload: Dict[str, Any], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    """Build a regime audit row from already-collected EOD payload."""
    overview = payload.get("market_overview") or {}
    indices = payload.get("indices") or []
    smoothed = payload.get("market_regime")
    audit = dict(explain_market_regime(indices, overview, smoothed_regime=smoothed))
    audit.update({
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or payload.get("generated_at") or _now_iso(),
        "source_payload": "eod_payload",
    })
    return audit


def render_regime_audit(audit: Dict[str, Any]) -> str:
    """Render a compact markdown audit report."""
    inputs = audit.get("inputs") or {}
    sources = audit.get("sources") or {}
    lines = [
        f"# Regime Audit {audit.get('trade_date') or 'nodate'}",
        "",
        "> 本报告解释 market_regime 的原始输入和判定过程; 不重新取数, 不修改 regime 状态。",
        "",
        f"- trade_date: {audit.get('trade_date') or '待验证'}",
        f"- raw_regime: {audit.get('raw_regime') or '待验证'}",
        f"- smoothed_regime: {audit.get('smoothed_regime') or '待验证'}",
        f"- reason: {audit.get('reason') or '待验证'}",
        f"- indices_source: {', '.join(sources.get('indices') or ['待验证'])}",
        f"- market_overview_source: {sources.get('market_overview') or '待验证'}",
        "",
        "## Inputs",
        "| field | value |",
        "|---|---:|",
        f"| limit_down_count | {inputs.get('limit_down_count')} |",
        f"| limit_down_threshold | {inputs.get('limit_down_threshold')} |",
        f"| sh_change_pct | {inputs.get('sh_change_pct')} |",
        f"| cyb_change_pct | {inputs.get('cyb_change_pct')} |",
        f"| kc50_change_pct | {inputs.get('kc50_change_pct')} |",
        f"| growth_avg_change_pct | {inputs.get('growth_avg_change_pct')} |",
        f"| growth_minus_sh_pct | {inputs.get('growth_minus_sh_pct')} |",
        f"| sh_minus_growth_pct | {inputs.get('sh_minus_growth_pct')} |",
        "",
        "## Rules",
        "- `limit_down_count > 50` => raw `panic`。",
        "- `growth_avg - sh >= 2.0%` => raw `momentum`。",
        "- `sh - growth_avg >= 1.0%` => raw `value`。",
        "- 其他情况按当前规则 raw `momentum`。",
        "- smoothing: panic 单日生效; panic 解除需连续2日非 panic; momentum/value 切换需连续2日同向。",
    ]
    return "\n".join(lines).rstrip() + "\n"


def record_regime_audit(payload: Dict[str, Any], *, jsonl_path=None, output_dir=None) -> Dict[str, Any]:
    """Write regime audit JSONL and markdown. Same trade_date JSONL row is idempotent."""
    audit = payload.get("regime_audit") or build_regime_audit(payload)
    trade_date = str(audit.get("trade_date") or "").strip()
    if not trade_date:
        return {"written": 0, "skipped": 0, "report": None, "reason": "missing_trade_date"}

    out_jsonl = Path(jsonl_path or REGIME_AUDIT_JSONL)
    report_dir = Path(output_dir) if output_dir is not None else out_jsonl.parent
    report_path = report_dir / f"regime_audit_{trade_date}.md"

    existing_dates = {str(r.get("trade_date") or "") for r in _read_jsonl(out_jsonl)}
    written = 0
    skipped = 0
    if trade_date in existing_dates:
        skipped = 1
    else:
        _append_jsonl(out_jsonl, audit)
        written = 1

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_regime_audit(audit), encoding="utf-8")
    logger.info(f"Regime Audit 落盘: {report_path}")
    return {"written": written, "skipped": skipped, "report": str(report_path), "trade_date": trade_date}