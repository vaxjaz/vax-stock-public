# -*- coding: utf-8 -*-
"""每日操作清单中文渲染。"""

from typing import Any, Mapping

from vaxstock.report.market_context import render_market_background_lines

from vaxstock.report.stock_evidence import (
    format_earnings, format_history_verdict, format_live_history,
)

_TIER_LABELS = {
    "ordinary": "普通",
    "core": "核心",
    "strategic_core": "战略核心",
}
_UNIT_LABELS = {"half_unit": "0.5单位", "unit": "1单位"}
_TRIGGER_LABELS = {
    "reclaim_confirm": "收复确认",
    "breakout_confirm": "突破确认",
    "panic_rebound_probe": "恐慌修复确认",
    "breakdown_confirm": "破位确认",
    "failed_breakout": "突破失败",
    "risk_off_confirm": "转弱减仓确认",
    "weak_rebound": "弱反弹",
    "noise_filter": "噪音过滤",
}
_SEVERITY_LABELS = {"high": "高", "medium": "中", "low": "低"}


_SOURCE_LABELS = {
    "broker_screenshot_user_confirmed": "已确认券商截图",
    "eod_revalued_from_confirmed_cash_and_holdings": "已确认现金和持仓 + EOD收盘价",
    "close_quote_revalued_from_confirmed_cash_and_holdings": "已确认现金和持仓 + 当日收盘行情",
}


def _amount(value: Any) -> str:
    return "待确认" if value is None else f"{float(value):,.2f}元"


def _pct(value: Any) -> str:
    return "待确认" if value is None else f"{float(value):.2f}%"


def _trigger_fact_text(fact: Mapping[str, Any]) -> str:
    trigger_type = str(fact.get("trigger_type") or "触发条件")
    label = _TRIGGER_LABELS.get(trigger_type, trigger_type)
    raw_time = str(fact.get("trade_time") or "待确认")
    trade_time = raw_time[:8] if len(raw_time) >= 8 else raw_time
    price = "待确认" if fact.get("price") is None else f"{float(fact['price']):.2f}"
    severity = _SEVERITY_LABELS.get(str(fact.get("severity") or ""), fact.get("severity") or "待确认")
    text = f"{trade_time}触发{label}，触发价{price}，风险级别{severity}"
    occurrences = int(fact.get("occurrences") or 1)
    if occurrences > 1:
        text += f"；同一任务重复记录{occurrences}次，本报告按首次触发"
    return text


def _coverage_fact_text(fact: Mapping[str, Any]) -> str:
    count = int(fact.get("observation_count") or 0)
    first = fact.get("first_quote_trade_time") or fact.get("first_observed_at") or "待确认"
    last = fact.get("last_quote_trade_time") or fact.get("last_observed_at") or "待确认"
    price = "待确认" if fact.get("last_price") is None else f"{float(fact['last_price']):.2f}"
    return f"有效观察{count}次，首笔{first}，末笔{last}，最后价{price}"


_DLINE_VERDICT_LABELS = {
    "new_evidence": "首次形成有效结论",
    "insufficient_counterfactual": "有效对照样本不足",
    "preliminary_support": "初步支持当前D线条件",
    "stable_support": "稳定支持当前D线条件",
    "preliminary_conflict": "初步反对当前D线条件",
    "stable_conflict": "稳定反对当前D线条件",
    "mixed": "结果混合",
    "insufficient_intraday_path": "盘中演变样本不足",
    "mixed_intraday_path": "盘中演变结果混合",
    "preliminary_sustained": "初步显示触发后持续有效",
    "stable_sustained": "稳定显示触发后持续有效",
    "preliminary_trigger_early": "初步显示触发偏早",
    "stable_trigger_early": "稳定显示触发偏早",
    "preliminary_intraday_fade": "初步显示触发后盘中转弱",
    "stable_intraday_fade": "稳定显示触发后盘中转弱",
    "preliminary_intraday_conflict": "初步显示触发方向无效",
    "stable_intraday_conflict": "稳定显示触发方向无效",
}

_DLINE_TRIGGER_LABELS = {
    "breakout_confirm": "突破确认",
    "reclaim_confirm": "收复确认",
    "panic_rebound_probe": "恐慌修复观察",
    "breakdown_confirm": "破位确认",
    "failed_breakout": "突破失败",
    "risk_off_confirm": "风险关闭",
    "weak_rebound": "弱反弹",
    "noise_filter": "噪音过滤",
}


def _dline_change_key_label(value: Any) -> str:
    parts = str(value or "").split("|")
    if len(parts) < 3:
        return str(value or "待确认")
    trigger = _DLINE_TRIGGER_LABELS.get(parts[1], parts[1])
    scope = "盘中演变" if parts[-1] == "intraday" else f"T+{parts[-1]}"
    return f"{trigger}（{scope}）"


def _dline_rule_change_lines(background: Mapping[str, Any]):
    changes = list(background.get("dline_rule_changes") or [])
    if not changes:
        return []
    parts = []
    for change in changes[:3]:
        key = _dline_change_key_label(change.get("cell_key"))
        before = _DLINE_VERDICT_LABELS.get(
            str(change.get("before") or ""), str(change.get("before") or "待确认")
        )
        after = _DLINE_VERDICT_LABELS.get(
            str(change.get("after") or ""), str(change.get("after") or "待确认")
        )
        parts.append(f"{key}: {before} -> {after}")
    if len(changes) > 3:
        parts.append(f"另{len(changes) - 3}项")
    as_of = background.get("dline_rule_review_as_of") or "待确认"
    return [f"- D线规则复盘变化（截至{as_of}）: " + "；".join(parts)]

def _evidence_convergence_lines(report: Mapping[str, Any]):
    if report.get("status") not in {"ready", "partial_data"}:
        reason = report.get("reason") or "同一EOD基准日的证据收敛报告缺失"
        return [
            "## 证据收敛",
            "",
            f"- 待确认: {reason}；不使用其他日期报告替代。",
            "",
        ]
    facts = report.get("facts") or {}
    changes = (report.get("convergence") or {}).get("changes") or []
    findings = report.get("special_findings") or []
    effect = report.get("strategy_effect") or {}
    change_text = "；".join(
        str(row.get("summary")).rstrip("。；")
        for row in changes[:4] if row.get("summary")
    ) or "没有可确认的结论变化。"
    finding_text = "；".join(
        str(row.get("summary")).rstrip("。；")
        for row in findings[:4] if row.get("summary")
    ) or "未识别到新的环境冲突、集中触发或期限反转。"
    late_limited = int(facts.get("dline_late_limited_evolution_paths") or 0)
    evolution_suffix = (
        f"（其中晚盘触发仅检查可达节点{late_limited}条）" if late_limited else ""
    )
    return [
        "## 证据收敛",
        "",
        (
            f"- **1. 今天新增什么证据**: 成熟C线结果"
            f"{facts.get('new_matured_c_results', 0)}条；D线选择"
            f"{facts.get('dline_selected_stocks', 0)}只、触发"
            f"{facts.get('dline_triggered_stocks', 0)}只、可评价演变"
            f"{facts.get('dline_complete_evolution_paths', 0)}条{evolution_suffix}。"
        ),
        f"- **2. 哪些结论发生变化**: {change_text}",
        f"- **3. 特殊环境或冲突**: {finding_text}",
        f"- **4. 是否改变今天动作**: {effect.get('summary') or '待确认'}",
        "",
    ]

def render_daily_action_markdown(plan: Mapping[str, Any]) -> str:
    bg = plan.get("background") or {}
    account = plan.get("account") or {}
    units = account.get("unit_amounts") or {}
    target = bg.get("target_trade_date") or "待确认"
    source = _SOURCE_LABELS.get(account.get("source"), account.get("source") or "待验证")
    title = "收盘操作复盘" if plan.get("phase") == "close_review" else "每日操作清单"
    lines = [
        f"# {target} {title}",
        "",
    ]
    if plan.get("phase") == "close_review":
        lines += [
            "- **收盘口径**: D线已触发只代表条件真实发生；没有实际成交记录时，一律标记为执行待确认。",
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
        *render_market_background_lines(bg),
        *_dline_rule_change_lines(bg),
        "",
        f"- 账户: 仓位 {_pct(account.get('reported_position_pct'))}，可用现金 {_amount(account.get('available_cash'))}；0.5单位 {_amount(units.get('half_unit'))}，1单位 {_amount(units.get('unit'))}。",
        f"- 数据口径: EOD基准 {bg.get('baseline_trade_date') or '待验证'}；账户估值日 {account.get('as_of_trade_date') or '待验证'}；来源 {source}。",
        *([
            f"- 收盘行情: 日期 {account.get('price_trade_date') or '待确认'}；"
            f"来源 {account.get('price_source') or '待确认'}。"
        ] if plan.get("phase") == "close_review" else []),
        "",
        *(_evidence_convergence_lines(plan.get("evidence_convergence") or {})
          if plan.get("phase") != "close_review" else []),
        "## 持仓操作",
        "",
    ]
    for idx, row in enumerate(plan.get("holdings") or [], start=1):
        tier = _TIER_LABELS.get(row.get("tier"), "待分类")
        lines.append(
            f"{idx}. **{row.get('name') or row.get('code')}**"
            f"（{tier}仓 {_pct(row.get('current_weight_pct'))}/{_pct(row.get('cap_pct'))}）"
        )
        lines.append(
            f"   - **1. 今天做什么**: {row.get('action') or '待确认'}。"
            f"原因: {row.get('reason') or '待确认'}。"
        )
        if row.get("pnl_pct") is not None:
            lines.append(
                f"   - **2. 当前实际盈亏**: {float(row['pnl_pct']):+.2f}%"
                f"（估算{float(row['pnl_amount_estimate']):+,.2f}元；"
                f"成本{float(row['cost_price']):.3f}/参考价{float(row['reference_price']):.3f}）。"
            )
        else:
            lines.append("   - **2. 当前实际盈亏**: 待确认（成本或参考价不完整）。")
        lines.append(
            f"   - **3. 历史策略表现**: {format_live_history(row.get('history_summary') or {})}"
        )
        lines.append(
            "   - **4. 历史结果是否改变今天动作**: "
            f"{format_history_verdict(row.get('history_verdict') or {})}"
        )
        lines.append(f"   - 财报背景: {format_earnings(row.get('earnings') or {})}")
        for fact in row.get("dline_triggers") or []:
            lines.append(f"   - D线事实: {_trigger_fact_text(fact)}。")
        if plan.get("phase") == "close_review":
            coverage = row.get("dline_coverage")
            if coverage:
                lines.append(f"   - D线观察: {_coverage_fact_text(coverage)}。")
            elif row.get("dline_triggers"):
                lines.append("   - D线观察: 独立覆盖记录缺失；已冻结触发事实仍保留。")
            else:
                lines.append("   - D线观察: 无与当前任务匹配的有效观察记录，盘中条件结果待确认。")
        add = row.get("conditional_add")
        if add:
            unit = _UNIT_LABELS.get(add.get("unit"), add.get("unit"))
            record_status = add.get("trigger_record_status")
            if record_status == "recorded":
                lines.append(
                    f"   - 加仓结果: 条件已触发；加仓上限{unit}，按参考价估算"
                    f"{add.get('estimated_shares')}股/{_amount(add.get('amount'))}；实际成交待确认。"
                )
            elif record_status == "not_recorded":
                lines.append(
                    f"   - 加仓结果: D线未记录到{add.get('condition')}；系统未产生加仓执行依据。"
                )
            elif record_status == "coverage_missing":
                lines.append(
                    "   - 加仓结果: D线观察记录不足，无法确认条件是否发生；系统不执行加仓。"
                )
            else:
                lines.append(
                    f"   - 加仓开关: {add.get('condition')}后，加仓上限{unit}，"
                    f"按参考价估算{add.get('estimated_shares')}股/{_amount(add.get('amount'))}。"
                )
        risk = row.get("risk_reduce")
        if risk:
            unit = _UNIT_LABELS.get(risk.get("unit"), risk.get("unit"))
            shares = f"估算{risk.get('estimated_shares')}股" if risk.get("estimated_shares") is not None else "股数待确认"
            record_status = risk.get("trigger_record_status")
            if record_status == "recorded":
                lines.append(
                    f"   - 风险结果: 条件已触发；减仓上限{unit}，{shares}/"
                    f"{_amount(risk.get('estimated_amount'))}；实际成交待确认。"
                )
            elif record_status == "not_recorded":
                lines.append(
                    f"   - 风险结果: D线未记录到{risk.get('condition')}；系统未产生减仓执行依据。"
                )
            elif record_status == "coverage_missing":
                lines.append(
                    "   - 风险结果: D线观察记录不足，无法确认条件是否发生；请按实际行情复核。"
                )
            else:
                lines.append(
                    f"   - 风险开关: {risk.get('condition')}后，减仓上限{unit}，"
                    f"{shares}/{_amount(risk.get('estimated_amount'))}。"
                )
    new_positions = plan.get("new_positions") or {}
    footer = (
        "> 触发时间和触发价来自D线冻结记录；金额和股数按记录价格估算；实际成交以用户确认持仓为准。"
        if plan.get("phase") == "close_review" else
        "> 金额和股数为参考价估算；盘中只有对应D线条件真实触发后才执行，并按实时价重算。"
    )
    lines += [
        "",
        "## 新开仓",
        "",
        f"- **{new_positions.get('action') or '待确认'}**：{new_positions.get('reason') or '待确认'}。",
        "",
        footer,
    ]
    return "\n".join(lines).rstrip() + "\n"
