# -*- coding: utf-8 -*-
"""Render frozen EOD market, macro and AI-track evidence for daily actions."""

from typing import Any, Mapping


def _number(value: Any):
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Any, *, digits: int = 2, signed: bool = False, suffix: str = "") -> str:
    number = _number(value)
    if number is None:
        return "待确认"
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:.{digits}f}{suffix}"


def _date(value: Any) -> str:
    text = str(value or "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if len(text) == 6 and text.isdigit():
        return f"{text[:4]}-{text[4:]}"
    return text or "待确认"


def _signal(item: Mapping[str, Any], key: str = "signal") -> str:
    return str(item.get(key) or "待确认")


def _macro_lines(background: Mapping[str, Any]) -> list[str]:
    macro = background.get("macro") or {}
    indicators = macro.get("indicators") or {}
    regime = macro.get("macro_regime") or background.get("macro_regime") or "待验证"
    bullish = macro.get("bullish_count")
    bearish = macro.get("bearish_count")
    score = ""
    if bullish is not None or bearish is not None:
        score = f"；支持计数{bullish if bullish is not None else '待确认'}，风险计数{bearish if bearish is not None else '待确认'}"

    lines = ["### 宏观背景", f"- 总结: {regime}{score}。"]
    if not indicators:
        lines.append("- 7维明细: 待确认（当前D线任务未冻结宏观明细）。")
        return lines

    etf = indicators.get("etf_net_sub") or {}
    lines.append(
        "- 1. ETF净申赎: "
        f"近5日{_fmt(etf.get('value_5d_yi'), signed=True, suffix='亿元')}({_signal(etf, 'signal_5d')})；"
        f"近20日{_fmt(etf.get('value_20d_yi'), signed=True, suffix='亿元')}({_signal(etf, 'signal_20d')})；"
        f"数据日{_date(etf.get('latest_date'))}。"
    )

    margin = indicators.get("margin_ratio") or {}
    stale = "，数据滞后" if margin.get("stale") is True else ""
    lines.append(
        "- 2. 融资买入额/沪深成交额: "
        f"{_fmt(margin.get('ratio_pct'), suffix='%')}；近3年分位"
        f"{_fmt(margin.get('percentile_3y'), suffix='%')}；信号{_signal(margin)}；"
        f"数据日{_date(margin.get('latest_date'))}{stale}。"
    )

    turnover = indicators.get("turnover") or {}
    lines.append(
        "- 3. 市场换手率代理: "
        f"{_fmt(turnover.get('turnover_rate'), suffix='%')}；近3年分位"
        f"{_fmt(turnover.get('percentile_3y'), suffix='%')}；信号{_signal(turnover)}；"
        f"代理{turnover.get('proxy_code') or '待确认'}；数据日{_date(turnover.get('latest_date'))}。"
    )

    erp = indicators.get("hs300_erp") or {}
    lines.append(
        "- 4. 沪深300风险溢价: "
        f"ERP {_fmt(erp.get('erp_pct'), suffix='%')}；近5年分位"
        f"{_fmt(erp.get('percentile_5y'), suffix='%')}；沪深300 PE(TTM)"
        f"{_fmt(erp.get('pe_ttm'))}；10年国债收益率"
        f"{_fmt(erp.get('yield_10y_pct'), suffix='%')}({erp.get('yield_source') or '来源待确认'})；"
        f"信号{_signal(erp)}；数据日{_date(erp.get('latest_date'))}。"
    )

    breadth = indicators.get("breadth") or {}
    if breadth.get("available") is False:
        lines.append("- 5. 全市场宽度: 待确认。")
    else:
        lines.append(
            "- 5. 全市场宽度: "
            f"站上MA60 {_fmt(breadth.get('above_ma60_pct'), suffix='%')}({_signal(breadth, 'above_ma60_signal')})；"
            f"站上MA200 {_fmt(breadth.get('above_ma200_pct'), suffix='%')}({_signal(breadth, 'above_ma200_signal')})；"
            f"中证全指MA250乖离{_fmt(breadth.get('ma250_bias_pct'), signed=True, suffix='%')}"
            f"({_signal(breadth, 'ma250_bias_signal')})；数据日{_date(breadth.get('latest_date'))}。"
        )

    m1 = indicators.get("m1_yoy") or {}
    lines.append(
        "- 6. M1同比: "
        f"{_fmt(m1.get('value_pct'), signed=True, suffix='%')}；较上月变化"
        f"{_fmt(m1.get('mom_delta_pp'), signed=True, suffix='个百分点')}；"
        f"近10年分位{_fmt(m1.get('percentile_10y'), suffix='%')}；信号{_signal(m1)}；"
        f"数据月{_date(m1.get('latest_month'))}。"
    )

    social = indicators.get("sf_pulse") or {}
    lines.append(
        "- 7. 社融脉冲: "
        f"同比{_fmt(social.get('pulse_yoy_pct'), signed=True, suffix='%')}；加速度"
        f"{_fmt(social.get('accel_pp'), signed=True, suffix='个百分点')}；"
        f"信号{_signal(social)}；数据月{_date(social.get('latest_month'))}。"
    )
    errors = list(macro.get("errors") or [])
    if errors:
        lines.append(f"- 数据缺口: {len(errors)}项；有缺口的维度不作默认值填充。")
    return lines


def _ai_meaning(position_ceiling: Any) -> str:
    text = str(position_ceiling or "")
    if text.startswith("进攻档"):
        return "赛道层没有禁止加仓；单股仍须通过C线、D线和仓位上限。"
    if text.startswith("中性档"):
        return "赛道层只允许持有观察，不因赛道信号主动加仓。"
    if text.startswith("减档"):
        return "赛道层禁止加仓，并要求高位仓位关注减仓。"
    if text.startswith("防御档"):
        return "赛道层要求明显压低仓位。"
    if text.startswith("清仓档"):
        return "赛道层触发清仓级风险信号。"
    return "赛道层结论待确认，不能替代单股操作。"


def _ai_lines(background: Mapping[str, Any]) -> list[str]:
    track = background.get("ai_track") or {}
    ceiling = track.get("position_ceiling") or background.get("ai_position_ceiling") or "待验证"
    available = track.get("available")
    status = "已核验" if available is True else "待验证" if available is False else "状态待确认"
    name = track.get("track_name") or "AI赛道"
    lines = [
        f"### {name}",
        f"- 档位: {ceiling}；数据状态: {status}。",
        f"- 怎么理解: {_ai_meaning(ceiling)}本段是赛道背景，不是买卖指令。",
    ]
    summaries = [str(value).strip() for value in (track.get("summary_lines") or []) if str(value).strip()]
    if summaries:
        lines.append("- 证据:")
        lines.extend(f"  - {value}" for value in summaries)
    else:
        lines.append("- 证据: 待确认（当前任务未冻结AI赛道明细）。")

    vetoes = list(track.get("vetoes") or [])
    if vetoes:
        names = []
        for veto in vetoes:
            if isinstance(veto, (list, tuple)) and veto:
                names.append(str(veto[0]))
            elif isinstance(veto, Mapping):
                names.append(str(veto.get("name") or veto.get("type") or "未命名否决"))
            else:
                names.append(str(veto))
        lines.append(f"- 否决项: {len(vetoes)}项（{'、'.join(names)}）。")
    elif available is True:
        lines.append("- 否决项: 0项。")

    pending = [str(value) for value in (track.get("pending") or []) if value]
    if pending:
        lines.append(f"- 待确认项: {'、'.join(pending)}。")
    return lines


def render_market_background_lines(background: Mapping[str, Any]) -> list[str]:
    breadth = background.get("breadth") or {}
    lines = [
        "### 市场状态",
        f"- 结论: {background.get('market_regime_text') or '待验证'}；"
        f"EOD日期{_date(background.get('baseline_trade_date'))}。",
        "- 涨跌分布: "
        f"上涨{breadth.get('up_count') if breadth.get('up_count') is not None else '待确认'}家；"
        f"下跌{breadth.get('down_count') if breadth.get('down_count') is not None else '待确认'}家；"
        f"涨停{breadth.get('limit_up_count') if breadth.get('limit_up_count') is not None else '待确认'}家；"
        f"跌停{breadth.get('limit_down_count') if breadth.get('limit_down_count') is not None else '待确认'}家。",
        "",
        *_macro_lines(background),
        "",
        *_ai_lines(background),
    ]
    return lines
