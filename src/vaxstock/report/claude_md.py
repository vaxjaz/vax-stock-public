# -*- coding: utf-8 -*-
"""report 层: 给 Claude/GPT 的结构化指标渲染(compact + markdown + 通用赛道渲染)。

纯渲染层: 只吃已组装好的 payload/claude_data, 禁止 import sources/analysis(不取数)。
依赖只允许 util / config / tracks.contract。

MR5 改造(对 monolith stock_report_enhanced.py 的迁移版):
  - compact_for_claude: 删掉 sector_analysis / hot_sector_scan 两个 key(东财板块④/热门赛道⑦已砍)
  - build_claude_markdown: 删 "## 二、板块赛道" 整段 + "热门赛道扫描" 段;
    新增赛道落点——传入 track_results 则逐个 render_track_section
  - 同时移除 macro_indicators / us_market / opportunity_scanner 三段跨层 lazy import 渲染块:
    它们不属于 report 允许依赖(util/config/tracks.contract), 在新包里本就 ImportError 空转。
    对应数据 key(macro/us_market/opportunity_scan)仍保留在 compact 输出(SSOT), 渲染待
    services 层(MR6)以注入/预渲染方式接回。
  - render_track_section: 新增通用赛道渲染, 从 vaxstock.tracks.contract 直接 import(守叶子规矩)
"""

from typing import Any, Dict, List, Optional

from vaxstock.tracks.contract import TrackResult
from vaxstock.util import fmt_num, fmt_pct


def compact_for_claude(payload: Dict[str, Any]) -> Dict[str, Any]:
    result = {
        "generated_at": payload["generated_at"],
        "data_sources": payload["data_sources"],
        "tushare_points_level": payload.get("tushare_points_level", 0),
        "analysis_instruction": (
            "你是一名专业的A股分析师。基于以下结构化数据,做一份**决策导向**的分析报告。\n"
            "\n"
            "【量化框架 v1.4 — 沪深300扩展379只/745日回测(2026-06-16重跑,修幸存者偏差+前复权)】\n"
            "因子有效性排名（IC回测验证）:\n"
            "  🥇 净利同比      (IC=0.0240, ICIR=2.56) - IC最高\n"
            "  🥇 10日主力净流入 (IC=0.0229, ICIR=2.44) - 实战最强(多空+12.89%/夏普0.90)\n"
            "  🥈 股东户数变化  (IC=-0.0219, ICIR=-3.56) - 最稳定(负向)\n"
            "  🥈 右侧合成评分  (IC=0.0202, ICIR=3.13) - 排序强但多空仅+0.77%,作下限过滤非alpha\n"
            "  ❌ 无效/已删: 20日位置/PE百分位/RSI/换手Z/MA5偏离度/资金流斜率\n"
            "\n"
            "【市场环境过滤(regime filter)】\n"
            "- 动量市: 反转因子(PE百分位/20日位置/RSI)失效,以资金流+业绩+户数为准\n"
            "- 价值市: 反转因子启用,可考虑低位价值股\n"
            "- 恐慌市: 建议观望,提高现金\n"
            "看 market_regime 字段判断当前环境。\n"
            "\n"
            "【个股评分使用】\n"
            "每只股票已经计算 right_side_score (v1.1新公式):\n"
            "  >= 3.5 强买入信号\n"
            "  >= 2.0 可考虑介入\n"
            "  >= 0.5 观察等待\n"
            "  <  0.5 回避\n"
            "right_side_signals 字段是评分明细,直接引用。\n"
            "\n"
            "【输出要求】\n"
            "1. 大盘+板块整体判断,明确指出当前是哪种 regime\n"
            "2. **宏观环境(v1.3新增)**:综合判断 Macro Regime,与短期 regime 叠加给仓位建议\n"
            "3. 每只持仓做风险评估,以v1.1评分为准,辅以业绩/股东户数趋势\n"
            "4. 每只观察池做介入判断,优先看 right_side_score >= 2.0 的标的\n"
            "5. 给出明日3-5个具体观察重点\n"
            "6. 不要给具体买卖价格指令,只做风险评估+方向判断"
        ),
        "indices": payload.get("indices", []),
        "market_overview": payload.get("market_overview", {}),
        "market_regime": payload.get("market_regime", "momentum"),  # v1.1: 市场环境
        "north_flow": payload.get("north_flow"),
        "hsgt_flow_history": payload.get("hsgt_flow_history"),  # 北向资金近5日(Tushare)
        "us_market": payload.get("us_market"),              # v1.2: 美股参考
        "opportunity_scan": payload.get("opportunity_scan"), # v1.2: 机会仓
        "macro": payload.get("macro"),                       # v1.3: 宏观6维度
        "stocks": [],
    }
    for item in payload.get("stocks", []):
        rt = item.get("realtime") or {}
        mt = item.get("metrics") or {}
        result["stocks"].append({
            "group": item.get("group"),
            "code": item.get("code"),
            "name": rt.get("name") or item.get("configured_name"),
            "concepts": item.get("concepts", []),
            "cost_price": item.get("cost_price"),
            "shares": item.get("shares"),
            # === 实时行情 ===
            "price": rt.get("price"),
            "change_pct": rt.get("change_pct"),
            "amplitude_pct": rt.get("amplitude_pct"),
            "amount_yuan": rt.get("amount"),
            "open": rt.get("open"),
            "high": rt.get("high"),
            "low": rt.get("low"),
            # === 均线/趋势 ===
            "ma5": mt.get("ma5"), "ma10": mt.get("ma10"),
            "ma20": mt.get("ma20"), "ma60": mt.get("ma60"),
            "price_vs_ma5_pct": mt.get("price_vs_ma5_pct"),
            "price_vs_ma20_pct": mt.get("price_vs_ma20_pct"),
            "price_vs_ma60_pct": mt.get("price_vs_ma60_pct"),
            "ma_trend": mt.get("ma_trend"),
            # === 量价 ===
            "volume_ratio_5d": mt.get("volume_ratio_5d"),
            "volume_ratio_20d": mt.get("volume_ratio_20d"),
            "turnover_pct": mt.get("turnover_pct"),
            # === 估值(含历史百分位) ===
            "pe_ttm": mt.get("pe_ttm"),
            "pb_mrq": mt.get("pb_mrq"),
            "ps_ttm": mt.get("ps_ttm"),
            "pe_percentile_1y": mt.get("pe_percentile_1y"),
            "pb_percentile_1y": mt.get("pb_percentile_1y"),
            # === 区间位置 ===
            "range_20d_high": mt.get("range_20d_high"),
            "range_20d_low": mt.get("range_20d_low"),
            "position_20d_pct": mt.get("position_20d_pct"),
            "range_52w_high": mt.get("range_52w_high"),
            "range_52w_low": mt.get("range_52w_low"),
            "position_52w_pct": mt.get("position_52w_pct"),
            # === 周期涨幅 ===
            "recent_5d_change_pct": mt.get("recent_5d_change_pct"),
            "recent_20d_change_pct": mt.get("recent_20d_change_pct"),
            "ytd_change_pct": mt.get("ytd_change_pct"),
            # === 技术指标 ===
            "macd_dif": mt.get("macd_dif"),
            "macd_dea": mt.get("macd_dea"),
            "macd_hist": mt.get("macd_hist"),
            "rsi_14": mt.get("rsi_14"),
            # === 量化新增指标(v1.0) ===
            "turnover_zscore": mt.get("turnover_zscore"),
            "inflow_slope": mt.get("inflow_slope"),
            "right_side_score": mt.get("right_side_score"),
            "right_side_grade": mt.get("right_side_grade"),
            "right_side_signals": mt.get("right_side_signals"),
            # === 资金流向(Tushare 2000分,4档明细) ===
            "main_inflow_today_yuan": mt.get("main_inflow_today"),
            "main_inflow_today_pct": mt.get("main_inflow_today_pct"),
            "main_inflow_5d_yuan": mt.get("main_inflow_5d"),
            "main_inflow_10d_yuan": mt.get("main_inflow_10d"),
            "buy_elg_amount_yuan": mt.get("buy_elg_amount"),     # 特大单买入
            "sell_elg_amount_yuan": mt.get("sell_elg_amount"),    # 特大单卖出
            "buy_lg_amount_yuan": mt.get("buy_lg_amount"),       # 大单买入
            "sell_lg_amount_yuan": mt.get("sell_lg_amount"),     # 大单卖出
            # === 基本面 ===
            "np_yoy": mt.get("np_yoy"),                     # 净利同比%
            "or_yoy": mt.get("or_yoy"),                     # 营收同比%
            "q_np_yoy": mt.get("q_np_yoy"),                 # 单季净利同比%
            "roe_avg": mt.get("roe_avg"),                   # ROE%
            "roe_dt": mt.get("roe_dt"),                     # 扣非ROE%
            "gross_margin": mt.get("gross_margin"),         # 毛利率%
            "net_margin": mt.get("net_margin"),             # 净利率%
            "debt_to_assets": mt.get("debt_to_assets"),     # 资产负债率%
            "eps": mt.get("eps"),                           # EPS
            "ocfps": mt.get("ocfps"),                       # 每股经营现金流
            "report_date": mt.get("report_date"),
            # === Tushare独家数据 ===
            "forecast": item.get("forecast"),               # 业绩预告
            "holder_change": item.get("holder_change"),     # 股东户数变化
            "fina_history": item.get("fina_history"),       # 财务4期历史
            # === 持仓 ===
            "pnl_pct": mt.get("pnl_pct"),
            "pnl_amount": mt.get("pnl_amount"),
            # === 风险 ===
            "risk_level": mt.get("risk_level"),
            "alerts": mt.get("alerts"),
        })
    return result


def render_track_section(result: TrackResult) -> str:
    """通用赛道渲染(赛道契约在报告里的落点, 口子的报告侧)。

    纯函数, 只读入参 dict 的契约字段, 不内省任何赛道专属字段名:
      - 标题: track_name + date
      - summary_lines: 信号细节由赛道自产, 逐行直接打印
      - 否决块: 遍历 vetoes 打印; 空则 "✅ 无否决触发"
      - 档位行: position_ceiling
      - pending 非空: 打印 "⚠️ 待验证维度"
    """
    lines: List[str] = []
    lines.append(f"### {result.get('track_name', '?')} 赛道  {result.get('date', '')}")
    for ln in result.get("summary_lines", []) or []:
        lines.append(ln)

    lines.append("—— 三道硬否决(veto) ——")
    vetoes = result.get("vetoes") or []
    if vetoes:
        for v in vetoes:
            # v 为 (名, 原因); JSON 往返后可能是 list, 统一按索引取
            name = v[0] if len(v) > 0 else ""
            why = v[1] if len(v) > 1 else ""
            lines.append(f"  🚫 {name}: {why}")
    else:
        lines.append("  ✅ 无否决触发")

    lines.append(f"★ 赛道仓位档位: {result.get('position_ceiling', '')}")
    pending = result.get("pending") or []
    if pending:
        lines.append(f"⚠️ 待验证维度: {pending}")
    return "\n".join(lines)


def build_claude_markdown(claude_data: Dict[str, Any],
                          track_results: Optional[List[TrackResult]] = None) -> str:
    lines = []
    lines.append("# 股票日报结构化指标(增强版)")
    lines.append("")
    lines.append(f"生成时间: {claude_data['generated_at']}")
    lines.append("")
    lines.append("## 分析要求")
    lines.append(claude_data["analysis_instruction"])
    lines.append("")

    # 大盘
    lines.append("## 一、大盘环境")

    # v1.1: 市场环境分类（动量市/价值市/恐慌市）
    regime = claude_data.get("market_regime", "momentum")
    regime_label = {
        "momentum": "📈 **动量市** (成长股占优,反转因子失效,建议关注资金流+业绩+筹码)",
        "value":    "💰 **价值市** (主板占优,反转因子启用,可考虑低位价值股)",
        "panic":    "🚨 **恐慌市** (跌停超50个,建议观望,提高现金比例)"
    }.get(regime, regime)
    lines.append(f"- {regime_label}")

    for idx in claude_data.get("indices", []):
        if "error" not in idx:
            lines.append(f"- {idx.get('name')}: {fmt_num(idx.get('price'))} {fmt_pct(idx.get('change_pct'))}")

    mo = claude_data.get("market_overview", {})
    if mo:
        lines.append(f"- 全市场涨跌: 涨{mo.get('up_count', 0)} / 跌{mo.get('down_count', 0)} / 涨停{mo.get('limit_up_count', 0)} / 跌停{mo.get('limit_down_count', 0)}")
    nf = claude_data.get("north_flow")
    if nf:
        if nf.get("total_inflow") is not None:
            freshness = "今日" if nf.get("is_today") else f"延迟({nf.get('trade_date','')})"
            lines.append(f"- 北向资金({freshness}): {nf['total_inflow']:+.2f}亿 (沪{nf.get('hgt_inflow') or 0:.1f} / 深{nf.get('sgt_inflow') or 0:.1f})")
        elif nf.get("note"):
            lines.append(f"- 北向资金: ℹ️ {nf['note']}")
    lines.append("")

    # 个股
    lines.append("## 三、个股指标")
    for s in claude_data.get("stocks", []):
        lines.append(f"### {s.get('name')} ({s.get('code')}) - {s.get('group')}")
        concepts = s.get("concepts", [])
        if concepts:
            lines.append(f"- 概念: {', '.join(concepts[:10])}")  # 概念太多截断
        lines.append(f"- 行情: 现价 {fmt_num(s.get('price'))} | 涨跌幅 {fmt_pct(s.get('change_pct'))} | 振幅 {fmt_num(s.get('amplitude_pct'), 2, '%')}")
        lines.append(f"- 均线: MA5/10/20/60 = {fmt_num(s.get('ma5'))}/{fmt_num(s.get('ma10'))}/{fmt_num(s.get('ma20'))}/{fmt_num(s.get('ma60'))}")
        lines.append(f"- 趋势: {s.get('ma_trend') or '-'} | vs MA20: {fmt_pct(s.get('price_vs_ma20_pct'))} | vs MA60: {fmt_pct(s.get('price_vs_ma60_pct'))}")
        lines.append(f"- 位置: 20日 {fmt_num(s.get('position_20d_pct'), 0, '%')} | 52周 {fmt_num(s.get('position_52w_pct'), 0, '%')}")
        lines.append(f"- 区间: 20日 [{fmt_num(s.get('range_20d_low'))} - {fmt_num(s.get('range_20d_high'))}] | 52周 [{fmt_num(s.get('range_52w_low'))} - {fmt_num(s.get('range_52w_high'))}]")
        lines.append(f"- 涨幅: 5日 {fmt_pct(s.get('recent_5d_change_pct'))} | 20日 {fmt_pct(s.get('recent_20d_change_pct'))} | 年初至今 {fmt_pct(s.get('ytd_change_pct'))}")
        lines.append(f"- 量价: 量比5日 {fmt_num(s.get('volume_ratio_5d'), 2, 'x')} | 换手 {fmt_num(s.get('turnover_pct'), 2, '%')}")

        # 资金流向(主力+4档明细)
        infl_today = s.get("main_inflow_today_yuan")
        infl_5d = s.get("main_inflow_5d_yuan")
        infl_10d = s.get("main_inflow_10d_yuan")
        if infl_today is not None:
            line = f"- 资金流向: 今日主力 {infl_today/1e8:+.2f}亿"
            if infl_5d is not None:
                line += f" | 5日 {infl_5d/1e8:+.2f}亿"
            if infl_10d is not None:
                line += f" | 10日 {infl_10d/1e8:+.2f}亿"
            lines.append(line)
            # 4档明细(特大单/大单)
            buy_elg = s.get("buy_elg_amount_yuan")
            sell_elg = s.get("sell_elg_amount_yuan")
            buy_lg = s.get("buy_lg_amount_yuan")
            sell_lg = s.get("sell_lg_amount_yuan")
            if buy_elg is not None and sell_elg is not None:
                elg_net = buy_elg - sell_elg
                lg_net = (buy_lg or 0) - (sell_lg or 0)
                lines.append(f"  • 特大单净额 {elg_net/1e8:+.2f}亿 (买{buy_elg/1e8:.2f}/卖{sell_elg/1e8:.2f})")
                lines.append(f"  • 大单净额 {lg_net/1e8:+.2f}亿 (买{(buy_lg or 0)/1e8:.2f}/卖{(sell_lg or 0)/1e8:.2f})")

        # 估值
        pe_pct = s.get("pe_percentile_1y")
        pb_pct = s.get("pb_percentile_1y")
        lines.append(f"- 估值: PE-TTM {fmt_num(s.get('pe_ttm'), 1)} (历史{fmt_num(pe_pct, 0, '%') if pe_pct is not None else '-'}) | PB {fmt_num(s.get('pb_mrq'), 2)} (历史{fmt_num(pb_pct, 0, '%') if pb_pct is not None else '-'})")

        # 技术指标
        lines.append(f"- 技术: MACD({s.get('macd_dif')}/{s.get('macd_dea')}/{s.get('macd_hist')}) | RSI14 {fmt_num(s.get('rsi_14'), 0)}")

        # 量化新增指标(v1.0)
        rss = s.get("right_side_score")
        rsg = s.get("right_side_grade") or "-"
        rssigs = s.get("right_side_signals") or []
        if rss is not None:
            lines.append(f"- 🎯 右侧信号评分: {rss:.1f}分 [{rsg}]")
            for sig in rssigs:
                lines.append(f"  {sig}")
        tz = s.get("turnover_zscore")
        if tz is not None:
            lines.append(f"- 换手Z-score: {tz:.2f} (>2异常放量/<-1缩量)")
        slope = s.get("inflow_slope")
        if slope is not None:
            lines.append(f"- 资金斜率: {slope/1e4:+.1f}万/日 ({'改善↑' if slope > 0 else '恶化↓'})")

        # 业绩(扩展版,加入扣非ROE/单季同比)
        if s.get("np_yoy") is not None or s.get("roe_avg") is not None:
            biz_line = f"- 业绩({s.get('report_date', '-')}): "
            parts = []
            if s.get("np_yoy") is not None:
                parts.append(f"净利同比 {fmt_pct(s.get('np_yoy'))}")
            if s.get("or_yoy") is not None:
                parts.append(f"营收同比 {fmt_pct(s.get('or_yoy'))}")
            if s.get("q_np_yoy") is not None:
                parts.append(f"单季净利同比 {fmt_pct(s.get('q_np_yoy'))}")
            if s.get("roe_avg") is not None:
                parts.append(f"ROE {fmt_pct(s.get('roe_avg'))}")
            if s.get("roe_dt") is not None:
                parts.append(f"扣非ROE {fmt_pct(s.get('roe_dt'))}")
            if s.get("gross_margin") is not None:
                parts.append(f"毛利率 {fmt_pct(s.get('gross_margin'))}")
            if s.get("net_margin") is not None:
                parts.append(f"净利率 {fmt_pct(s.get('net_margin'))}")
            if s.get("debt_to_assets") is not None:
                parts.append(f"资产负债率 {fmt_pct(s.get('debt_to_assets'))}")
            biz_line += " | ".join(parts)
            lines.append(biz_line)

        # 业绩预告(Tushare独家)
        fc = s.get("forecast")
        if fc and fc.get("type"):
            line = f"- 🎯 业绩预告({fc.get('end_date')}): {fc.get('type')}"
            pmin = fc.get("p_change_min")
            pmax = fc.get("p_change_max")
            if pmin is not None and pmax is not None:
                line += f" | 净利变动 {pmin:.1f}% ~ {pmax:.1f}%"
            elif pmin is not None:
                line += f" | 净利变动 {pmin:.1f}%+"
            if fc.get("summary"):
                summary = fc["summary"][:80]
                line += f"\n  • 原因: {summary}"
            lines.append(line)

        # 股东户数变化(Tushare独家)
        hc = s.get("holder_change")
        if hc and hc.get("change_pct") is not None:
            chg = hc["change_pct"]
            arrow = "↓" if chg < 0 else "↑"
            lines.append(f"- 👥 股东户数: {hc.get('prev_date')}→{hc.get('latest_date')} 变化 {chg:+.2f}% {arrow} ({hc.get('interpretation')})")

        # 财务历史(看趋势)
        fh = s.get("fina_history")
        if fh and len(fh) >= 2:
            # 显示每一期的"期间标签",防止单季vs累计比较失真
            # 同时增加 q_np_yoy (单季净利同比, 可跨期对比) 作为更准确的趋势指标
            period_seq = " → ".join(
                f"{(r.get('end_date') or '')[:6]}({r.get('period_type','?')})" for r in reversed(fh)
            )
            roe_trend = " → ".join(
                f"{r.get('roe', 0):.1f}" if r.get("roe") is not None else "-"
                for r in reversed(fh)
            )
            np_yoy_trend = " → ".join(
                f"{r.get('np_yoy', 0):+.0f}%" if r.get("np_yoy") is not None else "-"
                for r in reversed(fh)
            )
            q_np_yoy_trend = " → ".join(
                f"{r.get('q_np_yoy', 0):+.0f}%" if r.get("q_np_yoy") is not None else "-"
                for r in reversed(fh)
            )
            lines.append(f"- 📈 财务趋势(老→新):")
            lines.append(f"    报告期: {period_seq}")
            lines.append(f"    ROE(%): {roe_trend}  ⚠️不同报告期口径不同,见报告期标签")
            lines.append(f"    累计净利同比: {np_yoy_trend}")
            lines.append(f"    单季净利同比(可跨期对比): {q_np_yoy_trend}")

        # 持仓
        if s.get("cost_price") is not None:
            lines.append(f"- 持仓: 成本 {s.get('cost_price')} | 盈亏 {fmt_pct(s.get('pnl_pct'))}" + (f" ({s.get('pnl_amount'):+.0f}元)" if s.get('pnl_amount') else ""))

        # 风险
        lines.append(f"- 风险等级: {s.get('risk_level')}")
        lines.append(f"- 提示: {'; '.join(s.get('alerts') or []) or '无'}")
        lines.append("")

    # ## 四、赛道择时(取代旧"热门赛道扫描"位置; 赛道契约在报告里的落点)
    lines.append("## 四、赛道择时(独立体系, 不并入 macro regime)")
    if track_results:
        for tr in track_results:
            lines.append(render_track_section(tr))
            lines.append("")
    else:
        lines.append("无赛道信号")
        lines.append("")

    # 分析方向引导
    lines.append("## 六、请重点分析以下方向")
    lines.append("")
    lines.append("1. **大盘环境**:今天是普涨还是结构性?涨跌家数比例是否健康?北向资金态度?当前是哪种regime(动量/价值/恐慌)?")
    lines.append("2. **🌐 宏观环境(v1.3新增)**:")
    lines.append("   - 综合 Macro Regime(看多/中性/看空)是什么?基于哪几个 ✅/❌ 信号?")
    lines.append("   - ERP 当前在历史什么位置?σ倍数说明什么?")
    lines.append("   - M1 同比和环比变化是加速还是减速?对市场流动性的判断")
    lines.append("   - 全A宽度(MA60/MA200)反映短期/长期市场是超跌还是过热?")
    lines.append("   - **与短期v1.2 regime 叠加,给出仓位建议**(见上方Regime叠加表)")
    lines.append("3. **美股参考**:结合美股数据,判断今日A股科技/医疗/AI链的外部情绪是顺风还是逆风")
    lines.append("3. **板块轮动**:")
    lines.append("   - 今日强势板块是否可持续?是新主线还是短期题材?")
    lines.append("   - 持仓/观察池所在板块的相对强弱?")
    lines.append("4. **个股层面**:")
    lines.append("   - 持仓:用v1.1评分为主+业绩/股东户数趋势辅助,判断止盈/止损/加仓")
    lines.append("   - 观察池:优先看 right_side_score >= 2.0 的标的")
    lines.append("5. **🚀 AI赛道择时(独立体系)**:")
    lines.append("   - 见上方'四、赛道择时': 景气/海外闸门/情绪/拥挤度 四维 + 三道硬否决")
    lines.append("   - 赛道仓位档位与三道否决是否触发?与主体系叠加怎么配仓")
    lines.append("6. **风险预警**:")
    lines.append("   - 高位高估值+主力流出的标的(警惕)")
    lines.append("   - 跌破关键均线+空头排列的标的(趋势恶化)")
    return "\n".join(lines)
