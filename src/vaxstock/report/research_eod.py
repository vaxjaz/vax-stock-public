# -*- coding: utf-8 -*-
"""Render the conclusion-first EOD market and anchor report.

All calculations must be completed before this report layer is called.  This
module only renders ``analyst_context`` and never fetches data, calculates a
fallback score, or promotes an unvalidated probability to a conclusion.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _trade_date(data: Mapping[str, Any]) -> str:
    value = str(
        _mapping(data.get("market_overview")).get("trade_date") or ""
    ).strip().replace("-", "")
    return value if len(value) == 8 and value.isdigit() else "待验证"


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None or isinstance(value, bool):
        return "待验证"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "待验证"


def _pct(value: Any, digits: int = 2) -> str:
    text = _fmt(value, digits)
    return text if text == "待验证" else f"{text}%"


def _signed(value: Any, *, suffix: str = "", digits: int = 2) -> str:
    if value is None or isinstance(value, bool):
        return "待验证"
    try:
        return f"{float(value):+.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "待验证"


def _metric(metric: Mapping[str, Any], *, suffix: str = "%") -> tuple[str, str, str, str]:
    return (
        f"{_fmt(metric.get('current'))}{suffix}" if metric.get("current") is not None else "待验证",
        (
            f"{_fmt(metric.get('reference_5_sessions'))}{suffix}"
            if metric.get("reference_5_sessions") is not None
            else "待验证"
        ),
        _signed(metric.get("change_5_sessions"), suffix="pp" if suffix == "%" else suffix),
        str(metric.get("reference_5_sessions_trade_date") or "待验证"),
    )


def _state_text(states: Mapping[str, Any]) -> list[str]:
    breadth = {
        "repairing_but_long_term_majority_below_ma200": (
            "**大盘修复是真实的，但仍不是全面强势。** MA60与MA200宽度同步改善，"
            "但超过半数股票仍在MA200下方。"
        ),
        "broad_repair": "**大盘处于广泛修复。** MA60与MA200宽度同步改善，且MA200宽度已过半。",
        "deteriorating": "**市场宽度正在恶化。** MA60与MA200宽度较五个交易日前同步下降。",
        "mixed": "**市场宽度信号分化。** 短中期宽度没有形成同向变化。",
        "insufficient_history": "**市场宽度方向待验证。** 有效历史不足五个报告交易日。",
    }.get(str(states.get("breadth_state")), "**市场宽度状态待验证。**")
    funding = {
        "short_outflow_medium_inflow_divergence": (
            "**增量资金质量出现背离。** ETF近5日净赎回，但20日累计仍为净申购，"
            "说明短线承接转弱、尚未演变成中期全面撤退。"
        ),
        "broad_outflow": "**ETF资金形成短中期共同流出。** 5日与20日窗口均为净赎回。",
        "broad_inflow": "**ETF资金形成短中期共同流入。** 5日与20日窗口均为净申购。",
        "mixed": "**ETF资金方向混合。** 5日与20日窗口尚未给出一致方向。",
        "insufficient_data": "**ETF资金状态待验证。** 当前窗口数据不完整。",
    }.get(str(states.get("funding_state")), "**ETF资金状态待验证。**")
    leverage = {
        "not_deleveraging_high_leverage_fragility": (
            "**当前不是“杀杠杆”，而是高杠杆脆弱期。** 融资占比没有收缩且处于3年高分位；"
            "若价格与宽度随后转弱，才容易触发被动去杠杆。"
        ),
        "active_deleveraging": (
            "**已满足主动去杠杆识别条件。** 融资占比下降、ETF短线流出和MA60宽度恶化同时发生。"
        ),
        "leverage_contracting_not_systemic": (
            "**融资杠杆正在收缩，但尚未构成系统性杀杠杆。** 其余确认条件没有同时满足。"
        ),
        "not_deleveraging": "**当前未识别到杀杠杆。** 融资占比未形成收缩。",
        "insufficient_history": "**杀杠杆状态待验证。** 融资历史或宽度历史不足。",
    }.get(str(states.get("deleveraging_state")), "**杀杠杆状态待验证。**")
    ai = {
        "demand_proxy_intact_price_reversal_not_confirmed": (
            "**AI需求景气代理仍在扩张，但价格锚没有确认真反转。** "
            "SOX仍未通过MA50/动量闸门，当前只能定义为需求与价格背离。"
        ),
        "demand_and_price_gate_aligned": (
            "**AI需求代理与海外价格闸门同向。** 这是反转确认的必要组合，但仍不等于个股买点。"
        ),
        "demand_and_price_both_weak": "**AI需求代理与海外价格锚同时偏弱。** 当前不具备反转条件。",
        "price_repair_without_demand_confirmation": (
            "**AI价格锚修复，但需求代理未确认。** 当前上涨缺少景气层配合。"
        ),
        "insufficient_data": "**AI状态待验证。** 需求代理或SOX价格闸门缺失。",
    }.get(str(states.get("ai_state")), "**AI状态待验证。**")
    return [f"- {breadth}", f"- {funding}", f"- {leverage}", f"- {ai}"]


def _render_market(context: Mapping[str, Any]) -> list[str]:
    market = _mapping(context.get("market"))
    participation = _mapping(market.get("participation"))
    style = _mapping(market.get("style"))
    breadth = _mapping(market.get("breadth"))
    lines = [
        "## 大环境重算",
        "",
        (
            f"- 当日参与度：上涨{participation.get('up_count', '待验证')} / "
            f"下跌{participation.get('down_count', '待验证')} / "
            f"上涨占比{_pct(participation.get('up_ratio_pct'))}；"
            f"涨停{participation.get('limit_up_count', '待验证')} / "
            f"跌停{participation.get('limit_down_count', '待验证')}。"
        ),
        (
            f"- 风格差：上证{_pct(style.get('sh_change_pct'))}，"
            f"成长均值{_pct(style.get('growth_average_change_pct'))}，"
            f"上证领先成长{_signed(style.get('sh_minus_growth_pp'), suffix='pp')}。"
        ),
        "",
        "| A股指数 | 收盘 | 当日涨跌 | 数据日 |",
        "|---|---:|---:|---|",
    ]
    indices = market.get("indices")
    if isinstance(indices, list):
        for raw in indices:
            row = _mapping(raw)
            lines.append(
                f"| {row.get('name') or row.get('symbol') or '待验证'} | "
                f"{_fmt(row.get('price'))} | {_pct(row.get('change_pct'))} | "
                f"{row.get('source_trade_date') or '待验证'} |"
            )
    if not isinstance(indices, list) or not indices:
        lines.append("| 待验证 | 待验证 | 待验证 | 待验证 |")
    lines.extend([
        "",
        "| 市场宽度 | 当前 | 5个报告交易日前 | 变化 | 比较基准日 |",
        "|---|---:|---:|---:|---|",
    ])
    for key, label in (
        ("above_ma60_pct", "全市场站上MA60"),
        ("above_ma200_pct", "全市场站上MA200"),
        ("ma250_bias_pct", "全市场MA250乖离"),
    ):
        now, reference, change, reference_date = _metric(_mapping(breadth.get(key)))
        lines.append(f"| {label} | {now} | {reference} | {change} | {reference_date} |")
    lines.extend([
        "",
        f"- 宽度数据日：{breadth.get('latest_date') or '待验证'}；"
        f"MA60有效样本{breadth.get('valid_count_ma60', '待验证')}，"
        f"MA200有效样本{breadth.get('valid_count_ma200', '待验证')}。",
    ])
    return lines


def _render_funding(context: Mapping[str, Any]) -> list[str]:
    market = _mapping(context.get("market"))
    funding = _mapping(market.get("funding"))
    margin = _mapping(market.get("margin"))
    valuation = _mapping(market.get("valuation_credit"))
    margin_now, margin_ref, margin_delta, margin_ref_date = _metric(
        _mapping(margin.get("ratio_pct"))
    )
    etf5_hist = _mapping(funding.get("etf_net_sub_5d_history"))
    etf20_hist = _mapping(funding.get("etf_net_sub_20d_history"))
    stale = "，滞后" if margin.get("stale") is True else ""
    lines = [
        "## 资金、杠杆与信用锚",
        "",
        "| 指标 | 当前 | 5个报告交易日前 | 变化 | 数据日/月份 |",
        "|---|---:|---:|---:|---|",
        (
            f"| ETF滚动5日净申赎 | {_fmt(funding.get('etf_net_sub_5d_yi'))}亿元 | "
            f"{_fmt(etf5_hist.get('reference_5_sessions'))}亿元 | "
            f"{_signed(etf5_hist.get('change_5_sessions'), suffix='亿元')} | "
            f"{funding.get('latest_date') or '待验证'} |"
        ),
        (
            f"| ETF滚动20日净申赎 | {_fmt(funding.get('etf_net_sub_20d_yi'))}亿元 | "
            f"{_fmt(etf20_hist.get('reference_5_sessions'))}亿元 | "
            f"{_signed(etf20_hist.get('change_5_sessions'), suffix='亿元')} | "
            f"{funding.get('latest_date') or '待验证'} |"
        ),
        (
            f"| 融资余额/流通市值 | {margin_now} | {margin_ref} | {margin_delta} | "
            f"{margin.get('latest_date') or '待验证'}{stale} |"
        ),
        (
            f"| 融资占比3年分位 | {_pct(margin.get('percentile_3y'))} | — | — | "
            f"{margin.get('latest_date') or '待验证'}{stale} |"
        ),
        (
            f"| 沪深300 ERP / 5年分位 | {_pct(valuation.get('erp_pct'))} / "
            f"{_pct(valuation.get('erp_percentile_5y'))} | — | — | "
            f"{valuation.get('erp_latest_date') or '待验证'} |"
        ),
        (
            f"| 沪深300 PE / 中国10Y | {_fmt(valuation.get('hs300_pe_ttm'))} / "
            f"{_pct(valuation.get('cn_10y_yield_pct'), 4)} | — | — | "
            f"{valuation.get('erp_latest_date') or '待验证'} |"
        ),
        (
            f"| 换手率3年分位 | {_pct(valuation.get('turnover_percentile_3y'))} | — | — | "
            f"{valuation.get('turnover_latest_date') or '待验证'} |"
        ),
        (
            f"| M1同比 / 环比变化 | {_pct(valuation.get('m1_yoy_pct'))} / "
            f"{_signed(valuation.get('m1_mom_delta_pp'), suffix='pp')} | — | — | "
            f"{valuation.get('m1_latest_month') or '待验证'} |"
        ),
        (
            f"| 社融脉冲 / 加速度 | {_pct(valuation.get('social_financing_pulse_yoy_pct'))} / "
            f"{_signed(valuation.get('social_financing_acceleration_pp'), suffix='pp')} | — | — | "
            f"{valuation.get('social_financing_latest_month') or '待验证'} |"
        ),
        "",
        "- 本报告把“杀杠杆”定义为：融资占比下降、ETF近5日净流出、MA60宽度恶化三项同时出现；"
        "单独高融资分位只表示脆弱性，不等于正在去杠杆。",
    ]
    return lines


def _render_ai(context: Mapping[str, Any]) -> list[str]:
    ai = _mapping(context.get("ai_anchors"))
    demand = _mapping(ai.get("demand_proxy"))
    gate = _mapping(ai.get("price_gate"))
    local = _mapping(ai.get("local_risk"))
    capital = _mapping(ai.get("capital_cycle"))
    lines = [
        "## AI与海外锚",
        "",
        "| 价格锚 | 当前 | 当日变化 | 5个来源交易日变化 | 来源日 |",
        "|---|---:|---:|---:|---|",
    ]
    anchors = ai.get("price_anchors")
    if isinstance(anchors, list):
        for raw in anchors:
            row = _mapping(raw)
            lines.append(
                f"| {row.get('name') or row.get('symbol') or '待验证'} ({row.get('symbol') or '—'}) | "
                f"{_fmt(row.get('price'), 4)} | {_pct(row.get('daily_change_pct'))} | "
                f"{_pct(row.get('return_5_sessions_pct'))} | {row.get('source_date') or '待验证'} |"
            )
    if not isinstance(anchors, list) or not anchors:
        lines.append("| 待验证 | 待验证 | 待验证 | 待验证 | 待验证 |")
    lines.extend([
        "",
        (
            f"- **SOX价格闸门：{'开放' if gate.get('gate_open') is True else '关闭' if gate.get('gate_open') is False else '待验证'}。** "
            f"收盘{_fmt(gate.get('sox_close'))}，MA50 {_fmt(gate.get('sox_ma50'))}，"
            f"相对MA50 {_pct(gate.get('sox_vs_ma50_pct'))}，近1月动量{_pct(gate.get('sox_momentum_1m_pct'))}。"
        ),
        (
            "- **AI需求景气代理（不是Capex）：** "
            f"NVDA季度营收同比{_pct(demand.get('revenue_yoy_pct'))}，"
            f"环比{_pct(demand.get('revenue_qoq_pct'))}，"
            f"增速加速度{_signed(demand.get('revenue_acceleration_pp'), suffix='pp')}，"
            f"最新季营收{_fmt(demand.get('latest_revenue_busd'))}亿美元。"
        ),
        "- **本土风险与拥挤（当前 / T-5变化）：** "
        f"QVIX300 {_fmt(_mapping(local.get('qvix_300')).get('current'))} / "
        f"{_signed(_mapping(local.get('qvix_300')).get('change_5_sessions'))}；"
        f"QVIX创业板 {_fmt(_mapping(local.get('qvix_cyb')).get('current'))} / "
        f"{_signed(_mapping(local.get('qvix_cyb')).get('change_5_sessions'))}；"
        f"AI篮子换手分位{_pct(_mapping(local.get('basket_turnover_percentile_pct')).get('current'))} / "
        f"{_signed(_mapping(local.get('basket_turnover_percentile_pct')).get('change_5_sessions'), suffix='pp')}；"
        f"52周位置{_pct(_mapping(local.get('basket_52w_position_pct')).get('current'))} / "
        f"{_signed(_mapping(local.get('basket_52w_position_pct')).get('change_5_sessions'), suffix='pp')}。",
        f"- **赛道仓位上限：** {ai.get('position_ceiling') or '待验证'}。",
        "",
        "### AI资本周期锚",
        "",
    ])
    if capital.get("available") is True:
        lines.append("- 已接入，详见结构化附件。")
    else:
        missing = capital.get("missing")
        missing_text = "、".join(str(item) for item in missing) if isinstance(missing, list) else "待验证"
        lines.extend([
            f"- **未接入：** {missing_text}。",
            f"- **结论边界：** {capital.get('conclusion_limit') or '待验证'}。",
        ])
    return lines


def build_research_eod_markdown(
    data: Mapping[str, Any],
    *,
    research_summary: Optional[Mapping[str, Any]] = None,
    track_results: Optional[Sequence[Mapping[str, Any]]] = None,
) -> str:
    """Build the analyst EOD; individual-stock rows are intentionally omitted."""

    del research_summary, track_results  # pipeline/audit facts remain in attachments
    trade_date = _trade_date(data)
    context = _mapping(data.get("analyst_context"))
    freshness = _mapping(data.get("freshness"))
    if context.get("status") == "calculation_failed" or not context:
        reason = context.get("reason") or "analyst_context_missing"
        return (
            f"# EOD市场与AI锚 {trade_date}\n\n"
            "## 核心结论\n\n"
            f"- **待验证：大环境与锚重算未完成。** reason={reason}\n\n"
            "- 未使用旧评分、影子概率或中性默认值回退。\n"
        )

    history = _mapping(context.get("history"))
    capital = _mapping(_mapping(context.get("ai_anchors")).get("capital_cycle"))
    lines = [
        f"# EOD市场与AI锚 {trade_date}",
        "",
        "## 核心结论",
        "",
        *_state_text(_mapping(context.get("states"))),
        (
            "- **资本周期顶部暂不能下结论。** "
            + str(capital.get("conclusion_limit") or "相关锚数据待验证")
            + "。"
        ),
        "",
        *_render_market(context),
        "",
        *_render_funding(context),
        "",
        *_render_ai(context),
        "",
        "## 数据与结论边界",
        "",
        f"- trade_date={trade_date}；generated_at={data.get('generated_at') or '待验证'}；"
        f"freshness={freshness.get('status') or '待验证'}。",
        f"- 重算版本={context.get('calculation_version') or '待验证'}；"
        f"报告交易日样本={history.get('report_session_count', '待验证')}；"
        f"5日比较基准={history.get('five_session_reference_trade_date') or '待验证'}。",
        "- 价格锚5日变化按各自source_date去重后计算：P(t)/P(t-5)-1；"
        "宽度与融资变化按报告交易日T减T-5计算。",
        "- 正文不展示个股明细、旧评分、研究流水账或未经样本外验证的影子概率；"
        "完整原始输入和重算结果见payload.json。",
    ]
    return "\n".join(lines).rstrip() + "\n"
