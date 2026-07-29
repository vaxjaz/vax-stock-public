# -*- coding: utf-8 -*-
"""Render the human-facing EOD research status report.

This report deliberately does not consume legacy scores or hard-coded factor
rankings.  The full payload remains available to machine consumers through
``payload.json`` / ``claude.json``; this module only decides what a human sees.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _trade_date(data: Mapping[str, Any]) -> str:
    value = str(
        _mapping(data.get("market_overview")).get("trade_date") or ""
    ).strip()
    if len(value) == 8 and value.isdigit():
        return value
    return "待验证"


def _fmt_number(value: Any, digits: int = 2) -> str:
    if value is None or isinstance(value, bool):
        return "待验证"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "待验证"


def _fmt_pct(value: Any) -> str:
    text = _fmt_number(value)
    return text if text == "待验证" else f"{text}%"


def _stage_line(name: str, stage: Mapping[str, Any]) -> str:
    status = str(stage.get("status") or "not_executed")
    reason = str(stage.get("reason") or "").strip()
    metrics = _mapping(stage.get("metrics"))
    details = []
    for key in (
        "observations",
        "factors",
        "outputs",
        "candidate_hits",
        "stocks",
        "memberships",
        "samples_ready",
        "samples_written",
        "factor_series_tested",
        "factor_series_total",
        "candidate_tests",
        "pending_forecasts",
    ):
        value = metrics.get(key)
        if value is not None:
            details.append(f"{key}={value}")
    suffix = f" | {', '.join(details)}" if details else ""
    if reason:
        suffix += f" | reason={reason}"
    return f"- {name}: **{status}**{suffix}"


def _render_market(data: Mapping[str, Any]) -> list[str]:
    overview = _mapping(data.get("market_overview"))
    audit = _mapping(data.get("regime_audit"))
    lines = [
        "## 市场事实",
        "",
        (
            f"- regime: **{data.get('market_regime') or '待验证'}**"
            f" | raw={audit.get('raw_regime') or '待验证'}"
            f" | 原因={audit.get('reason') or '待验证'}"
        ),
        (
            "- 全市场: "
            f"涨{overview.get('up_count', '待验证')} / "
            f"跌{overview.get('down_count', '待验证')} / "
            f"涨停{overview.get('limit_up_count', '待验证')} / "
            f"跌停{overview.get('limit_down_count', '待验证')}"
        ),
    ]
    indices = data.get("indices")
    if isinstance(indices, list) and indices:
        lines.extend(["", "### 指数"])
        for row in indices:
            item = _mapping(row)
            lines.append(
                f"- {item.get('name') or item.get('symbol') or '待验证'}: "
                f"{_fmt_number(item.get('price'))} "
                f"({_fmt_pct(item.get('change_pct'))})"
            )
    return lines


def _render_research(summary: Mapping[str, Any]) -> list[str]:
    stages = _mapping(summary.get("stages"))
    lines = ["## 新研究链路", ""]
    for key, label in (
        ("snapshot", "基础快照"),
        ("curve", "连续曲线"),
        ("group", "动态分组"),
        ("outcome", "结果关联"),
        ("select", "因子选择"),
        ("forecast", "预测"),
        ("evaluation", "预测核验"),
    ):
        lines.append(_stage_line(label, _mapping(stages.get(key))))

    group = _mapping(stages.get("group"))
    group_metrics = _mapping(group.get("metrics"))
    event_state = group_metrics.get("systemic_event_state")
    if event_state is not None:
        lines.extend([
            "",
            "### 事件观测",
            (
                f"- state={event_state}"
                f" | direction={group_metrics.get('systemic_event_direction') or '待验证'}"
                f" | breadth={_fmt_number(group_metrics.get('event_stock_breadth'), 4)}"
                f" | families={group_metrics.get('systemic_event_families', '待验证')}"
            ),
            "- 事件字段仅为候选观测，不等于已经验证的交易信号。",
        ])
    return lines


def _render_decision(summary: Mapping[str, Any]) -> list[str]:
    status = str(summary.get("status") or "blocked")
    production_eligible = bool(summary.get("production_eligible"))
    blocking_stage = str(summary.get("blocking_stage") or "").strip()
    reason = str(summary.get("reason") or "").strip()
    lines = ["## 决策结论", ""]
    if production_eligible:
        lines.append(
            "- **研究输出已通过当前生产资格检查。** "
            "具体结论必须来自版本化 forecast 审计，不使用旧评分回退。"
        )
    else:
        lines.append(
            "- **ABSTAIN：当前没有通过验证的新算法交易结论。**"
        )
        lines.append(
            "- 不展示或回退任何旧评分与旧因子排名，"
            "不把候选拐点包装成有效信号。"
        )
    lines.append(f"- research_status: {status}")
    if blocking_stage:
        lines.append(f"- blocking_stage: {blocking_stage}")
    if reason:
        lines.append(f"- reason: {reason}")
    return lines


def _render_tracks(
    track_results: Optional[Iterable[Mapping[str, Any]]],
    *,
    report_trade_date: str,
) -> list[str]:
    rows = list(track_results or [])
    lines = ["## 赛道原始状态", ""]
    if not rows:
        lines.append("- 待验证：没有赛道结果。")
        return lines
    for raw in rows:
        row = _mapping(raw)
        name = row.get("track_name") or "未命名赛道"
        source_date = str(row.get("date") or "").replace("-", "")
        date_note = (
            ""
            if not source_date or source_date == report_trade_date
            else f" | source_date={source_date}（与报告交易日不一致）"
        )
        lines.append(
            f"- {name}: available={bool(row.get('available'))}"
            f" | position_ceiling={row.get('position_ceiling') or '待验证'}"
            f"{date_note}"
        )
    return lines


def build_research_eod_markdown(
    data: Mapping[str, Any],
    *,
    research_summary: Optional[Mapping[str, Any]] = None,
    track_results: Optional[Sequence[Mapping[str, Any]]] = None,
) -> str:
    """Build a concise EOD report without any legacy scoring fallback."""

    summary = _mapping(research_summary or data.get("research_summary"))
    trade_date = _trade_date(data)
    stocks = data.get("stocks")
    stock_rows = stocks if isinstance(stocks, list) else []
    holdings = sum(
        str(_mapping(row).get("group") or "").lower()
        in {"holding", "持仓"}
        for row in stock_rows
    )
    watchlist = len(stock_rows) - holdings
    freshness = _mapping(data.get("freshness"))

    lines = [
        f"# 新研究 EOD {trade_date}",
        "",
        "> 本报告已停用旧量化框架、旧因子排名和个股评分模板。"
        "底层结构化数据继续落盘，供回放与新算法使用。",
        "",
        "## 数据口径",
        "",
        f"- trade_date: {trade_date}",
        f"- generated_at: {data.get('generated_at') or '待验证'}",
        f"- freshness: {freshness.get('status') or '待验证'}",
        f"- universe: 持仓{holdings} / 观察池{watchlist} / 合计{len(stock_rows)}",
        "",
        *_render_market(data),
        "",
        *_render_research(summary),
        "",
        *_render_decision(summary),
        "",
        *_render_tracks(track_results, report_trade_date=trade_date),
        "",
        "## 审计边界",
        "",
        "- 完整原始数据见同目录 payload.json；机器压缩视图见 claude.json。",
        "- 本报告不因研究链路阻断而回退旧评分系统。",
    ]
    return "\n".join(lines).rstrip() + "\n"
