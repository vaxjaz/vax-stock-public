"""Pure renderer for the daily market environment email."""
from vaxstock.report.claude_md import render_regime_digest_line, render_track_section


def _value(value):
    return "待验证" if value is None or value == "" else str(value)


def build_macro_email(payload, tracks=()):
    overview = payload.get("market_overview") or {}
    lines = [f"宏观环境 {overview.get('trade_date') or '待验证'}", "",
             f"大盘状态: {_value(payload.get('market_regime'))}",
             render_regime_digest_line(payload.get("regime_audit")),
             f"上涨 {_value(overview.get('up_count'))} / 下跌 {_value(overview.get('down_count'))} / "
             f"涨停 {_value(overview.get('limit_up_count'))} / 跌停 {_value(overview.get('limit_down_count'))}"]
    for row in payload.get("indices") or []:
        lines.append(f"{_value(row.get('name'))}: {_value(row.get('price'))} | "
                     f"涨跌幅 {_value(row.get('change_pct'))}% | 数据日期 {_value(row.get('trade_date'))}")
    north = payload.get("north_flow") or {}
    lines.append(f"北向净流入: {_value(north.get('total_inflow'))}亿 | 数据日期 {_value(north.get('trade_date'))}")
    if north.get("note"):
        lines.append(str(north["note"]))
    freshness = payload.get("freshness") or {}
    if freshness.get("critical_failures"):
        lines.append("数据待验证: " + ", ".join(freshness["critical_failures"]))
    macro = payload.get("macro") or {}
    indicators = macro.get("indicators") or {}
    regime = macro.get("macro_regime") if indicators and macro.get("available") is not False else None
    lines.extend(["", f"宏观七维: {_value(regime)}"])
    for key, label in (("etf_net_sub", "ETF净申赎"), ("margin_ratio", "融资"),
                       ("turnover", "换手"), ("hs300_erp", "ERP"),
                       ("breadth", "市场宽度"), ("m1_yoy", "M1"), ("sf_pulse", "社融脉冲")):
        row = indicators.get(key) or {}
        signal = row.get("signal_5d") if key == "etf_net_sub" else row.get("signal")
        if key == "breadth":
            signal = " / ".join(_value(row.get(k)) for k in
                                ("above_ma60_signal", "above_ma200_signal", "ma250_bias_signal"))
        if row.get("available") is False:
            signal = None
        date = row.get("latest_date") or row.get("latest_month")
        lines.append(f"{label}: {_value(signal)} | 数据日期 {_value(date)}")
        fields = {
            "etf_net_sub": (("value_5d_yi", "5日净申赎", "亿"), ("value_20d_yi", "20日净申赎", "亿")),
            "margin_ratio": (("ratio_pct", "融资比", "%"),),
            "turnover": (("turnover_rate", "换手率", "%"),),
            "hs300_erp": (("erp_pct", "ERP", "%"),),
            "breadth": (("above_ma60_pct", "MA60以上比例", "%"),
                        ("above_ma200_pct", "MA200以上比例", "%"),
                        ("ma250_bias_pct", "MA250乖离", "%")),
            "m1_yoy": (("value_pct", "同比", "%"),),
            "sf_pulse": (("pulse_yoy_pct", "脉冲同比", "%"), ("accel_pp", "加速度", "百分点")),
        }
        if row:
            lines.append("  " + " / ".join(f"{label}: {_value(row.get(field))}{unit}" for field, label, unit in fields[key]))
        if date and len(str(date)) == 8 and str(date) < str(overview.get("trade_date") or ""):
            lines.append("  数据滞后于报告交易日")
    for error in macro.get("errors") or []:
        lines.append(f"待验证: {error}")
    us = payload.get("us_market") or {}
    lines.extend(["", f"美股环境: {_value(us.get('sentiment'))}"])
    for category in ("indices", "etfs", "stocks", "macro"):
        for row in us.get(category) or []:
            if category == "stocks" and row.get("symbol") != "NVDA":
                continue
            lines.append(f"{_value(row.get('name'))}: {_value(row.get('price'))} "
                         f"{row.get('unit') or ''} | 涨跌幅 {_value(row.get('change_pct'))}% "
                         f"| 数据日期 {_value(row.get('date'))}")
    if not any(us.get(k) for k in ("indices", "etfs", "stocks", "macro")):
        lines.append("美股数据待验证")
    for track in tracks:
        lines.extend(["", render_track_section(track)])
    if not tracks:
        lines.extend(["", "AI/SOX环境待验证"])
    return "\n".join(lines)
