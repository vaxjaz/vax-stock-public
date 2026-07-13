# -*- coding: utf-8 -*-
"""Chinese rendering for audited stock history and earnings context."""

from typing import Any, Mapping


def _pct(value: Any, signed: bool = True) -> str:
    try:
        number = float(value) * 100
    except (TypeError, ValueError):
        return "待验证"
    return f"{number:+.2f}%" if signed else f"{number:.2f}%"


def _metric_pct(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "待验证"
    return f"{number:+.2f}%"


def _period(value: Any) -> str:
    text = str(value or "")
    if len(text) != 8:
        return text or "报告期待验证"
    labels = {"0331": "Q1", "0630": "H1", "0930": "Q1-Q3", "1231": "年报"}
    return f"{text[:4]}{labels.get(text[4:], text[4:])}"


def _date(value: Any) -> str:
    text = str(value or "")
    if len(text) == 8:
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text or "待公布"


def format_live_history(summary: Mapping[str, Any]) -> str:
    if not summary or not summary.get("available") or not summary.get("evaluated"):
        return "真实历史结果待积累"
    horizons = summary.get("horizons") or {}
    keys = summary.get("key_horizons") or ("1", "5", "10", "30")
    parts = []
    for horizon in keys:
        cell = horizons.get(str(horizon)) or {}
        if not cell.get("evaluated"):
            continue
        cell_count = int(cell["evaluated"])
        cell_positive = int(cell.get("positive_excess_count") or 0)
        parts.append(
            f"T+{horizon} {cell_count}\u6b21\uff0c\u5e73\u5747\u8d85\u989d"
            f"{_pct(cell.get('avg_excess'))}\uff0c{cell_positive}/{cell_count}"
            f"\u6b21\u8dd1\u8d62\u6307\u6570"
        )
    if parts:
        return "\uff1b".join(parts)
    count = int(summary["evaluated"])
    positive = int(summary.get("positive_excess_count") or 0)
    return f"live已核验{count}次，平均超额{_pct(summary.get('avg_excess'))}，{positive}/{count}次跑赢指数"


def format_earnings(earnings: Mapping[str, Any]) -> str:
    earnings = earnings or {}
    latest = earnings.get("latest_report") or {}
    parts = []
    if latest.get("period"):
        parts.append(_period(latest.get("period")))
    for label, key in (
        ("净利同比", "net_profit_yoy"),
        ("营收同比", "revenue_yoy"),
        ("ROE", "roe"),
        ("毛利率", "gross_margin"),
    ):
        if latest.get(key) is not None:
            parts.append(f"{label}{_metric_pct(latest.get(key))}")
    report_text = "财报待验证" if not parts else "财报 " + "，".join(parts)

    next_report = earnings.get("next_report") or {}
    expected = next_report.get("expected_ann_date")
    if expected:
        next_text = f"预计披露 {_date(expected)}（{_period(next_report.get('period'))}，交易所预约，可能修订）"
    else:
        next_text = "预计披露待公布"
    return f"{report_text}；{next_text}"

def format_today_strategy(row: Mapping[str, Any]) -> str:
    if not row:
        return "今日策略待生成"
    text = str(row.get("action") or "今日策略待确认")
    add = row.get("conditional_add") or {}
    risk = row.get("risk_reduce") or {}
    if add:
        shares = add.get("estimated_shares")
        amount = add.get("amount")
        detail = []
        if shares is not None:
            detail.append(f"约{int(shares)}股")
        if amount is not None:
            detail.append(f"{float(amount):,.2f}元")
        text += "；条件满足后加仓" + ("/".join(detail) if detail else "，金额盘中重算")
    if risk:
        shares = risk.get("estimated_shares")
        text += f"；风险触发后减仓约{int(shares)}股" if shares is not None else "；风险触发后减仓股数盘中重算"
    return text