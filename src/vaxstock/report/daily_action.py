# -*- coding: utf-8 -*-
"""每日操作清单中文渲染。"""

from typing import Any, Mapping

from vaxstock.report.stock_evidence import (
    format_earnings, format_history_verdict, format_live_history,
)

_TIER_LABELS = {
    "ordinary": "普通",
    "core": "核心",
    "strategic_core": "战略核心",
}
_UNIT_LABELS = {"half_unit": "0.5单位", "unit": "1单位"}
_SOURCE_LABELS = {
    "broker_screenshot_user_confirmed": "已确认券商截图",
    "eod_revalued_from_confirmed_cash_and_holdings": "已确认现金和持仓 + EOD收盘价",
}


def _amount(value: Any) -> str:
    return "待确认" if value is None else f"{float(value):,.2f}元"


def _pct(value: Any) -> str:
    return "待确认" if value is None else f"{float(value):.2f}%"


def render_daily_action_markdown(plan: Mapping[str, Any]) -> str:
    bg = plan.get("background") or {}
    account = plan.get("account") or {}
    units = account.get("unit_amounts") or {}
    target = bg.get("target_trade_date") or "待确认"
    source = _SOURCE_LABELS.get(account.get("source"), account.get("source") or "待验证")
    lines = [
        f"# {target} 每日操作清单",
        "",
    ]
    if plan.get("degraded"):
        lines += [
            "- **降级模式**: D线未完整生成，今日禁止所有条件加仓。",
            "",
        ]
    lines += [
        "## 今日背景",
        "",
        f"- 市场: {bg.get('market_regime_text') or '待验证'}；宏观: {bg.get('macro_regime') or '待验证'}；AI赛道限制: {bg.get('ai_position_ceiling') or '待验证'}。",
        f"- 账户: 仓位 {_pct(account.get('reported_position_pct'))}，可用现金 {_amount(account.get('available_cash'))}；0.5单位 {_amount(units.get('half_unit'))}，1单位 {_amount(units.get('unit'))}。",
        f"- 数据口径: EOD基准 {bg.get('baseline_trade_date') or '待验证'}；账户估值日 {account.get('as_of_trade_date') or '待验证'}；来源 {source}。",
        "",
        "## 持仓操作",
        "",
    ]
    for idx, row in enumerate(plan.get("holdings") or [], start=1):
        tier = _TIER_LABELS.get(row.get("tier"), "待分类")
        lines.append(
            f"{idx}. **{row.get('name') or row.get('code')}**：{row.get('action')}"
            f"（{tier}仓 {_pct(row.get('current_weight_pct'))}/{_pct(row.get('cap_pct'))}）"
        )
        if row.get("pnl_pct") is not None:
            lines.append(
                f"   - 持仓收益: {float(row['pnl_pct']):+.2f}%（估算{float(row['pnl_amount_estimate']):+,.2f}元；"
                f"成本{float(row['cost_price']):.3f}/参考价{float(row['reference_price']):.3f}）"
            )
        lines.append(f"   - 真实历史: {format_live_history(row.get('history_summary') or {})}")
        lines.append(f"   - 策略校正: {format_history_verdict(row.get('history_verdict') or {})}")
        lines.append(f"   - 公司财报: {format_earnings(row.get('earnings') or {})}")
        lines.append(f"   - 原因: {row.get('reason')}")
        add = row.get("conditional_add")
        if add:
            lines.append(
                f"   - 加仓开关: {add.get('condition')}后，加仓上限{_UNIT_LABELS.get(add.get('unit'), add.get('unit'))}，"
                f"按参考价估算{add.get('estimated_shares')}股/{_amount(add.get('amount'))}。"
            )
        risk = row.get("risk_reduce")
        if risk:
            shares = f"估算{risk.get('estimated_shares')}股" if risk.get("estimated_shares") is not None else "股数盘中重算"
            lines.append(
                f"   - 风险开关: {risk.get('condition')}后，减仓上限{_UNIT_LABELS.get(risk.get('unit'), risk.get('unit'))}，"
                f"{shares}/{_amount(risk.get('estimated_amount'))}。"
            )
    new_positions = plan.get("new_positions") or {}
    lines += [
        "",
        "## 新开仓",
        "",
        f"- **{new_positions.get('action') or '待确认'}**：{new_positions.get('reason') or '待确认'}。",
        "",
        "> 金额和股数为参考价估算；盘中只有对应D线条件真实触发后才执行，并按实时价重算。",
    ]
    return "\n".join(lines).rstrip() + "\n"
