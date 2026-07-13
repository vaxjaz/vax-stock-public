# -*- coding: utf-8 -*-
"""Render a concise review of user-confirmed executions."""

from typing import Any, Mapping


_STATUS_LABELS = {
    "executed": "按计划执行",
    "partial_execution": "部分执行",
    "over_executed": "超过计划数量",
    "not_executed": "条件触发但未执行",
    "unplanned_execution": "计划外交易",
    "opposite_execution": "方向与计划相反",
    "mixed_execution": "同日买卖方向混合",
    "executed_without_quantity_plan": "已执行，计划数量待核对",
    "no_action": "无计划、无交易",
}
_SIDE_LABELS = {"buy": "买入", "sell": "卖出", "mixed": "买卖混合"}


def _price(value: Any) -> str:
    return "待确认" if value is None else f"{float(value):.3f}"


def _pct(value: Any) -> str:
    if value is None:
        return "不适用"
    sign = "+" if float(value) > 0 else ""
    return f"{sign}{float(value):.2f}%"


def _execution_text(row: Mapping[str, Any]) -> str:
    side = row.get("actual_side")
    if side is None:
        return "无成交"
    return (
        f"{_SIDE_LABELS.get(side, side)}{int(row.get('actual_shares') or 0)}股"
        f" @ {_price(row.get('actual_average_price'))}"
    )


def _plan_text(row: Mapping[str, Any]) -> str:
    side = row.get("expected_side")
    if side is None:
        return "无执行计划"
    shares = row.get("expected_shares")
    shares_text = "数量待确认" if shares is None else f"{int(shares)}股"
    return f"{_SIDE_LABELS.get(side, side)}{shares_text} @ 触发价{_price(row.get('trigger_price'))}"


def render_execution_review(review: Mapping[str, Any], *, projection_status: str) -> str:
    target = review.get("trade_date") or "待确认"
    lines = [
        f"# {target} 实际成交复盘",
        "",
        f"- 确认编号: `{review.get('confirmation_id') or '待确认'}`",
        "- 数据来源: 用户确认的券商成交与持仓截图",
        f"- 持仓同步: {projection_status}",
        "- 口径: 实际成交只取用户确认数据；未确认字段不推算。",
        "",
        "| 股票 | 系统计划 | 实际成交 | 对账结果 | 不利价差 |",
        "|---|---|---|---|---:|",
    ]
    for row in review.get("rows") or []:
        result = _STATUS_LABELS.get(row.get("status"), row.get("status") or "待确认")
        if row.get("policy_violation") == "forbidden_board_execution":
            result += "；违反交易板块约束"
        lines.append(
            f"| {row.get('code')} {row.get('name') or ''} | {_plan_text(row)} | "
            f"{_execution_text(row)} | {result} | {_pct(row.get('adverse_slippage_pct'))} |"
        )
    lines += [
        "",
        "> 不利价差为正表示实际成交价比触发价更差；买入价更高或卖出价更低均记为正。",
    ]
    return "\n".join(lines).rstrip() + "\n"
