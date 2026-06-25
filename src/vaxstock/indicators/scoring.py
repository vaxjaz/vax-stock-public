# -*- coding: utf-8 -*-
"""评分与衍生指标(纯计算, indicators 层)。

从单体脚本 script/stock_report_enhanced.py 原样搬运, 逻辑零改动。
搬运时的调整(均不改变行为):
    - logger 改用 logging.getLogger(__name__)
    - 工具/常量改为显式导入: util(safe_float/fmt_pct/fmt_num)、config(ALERT_RULES)、
      indicators(technical/valuation 的纯函数)
    - 不引入任何模块级全局状态; calc_right_side_score 的 market_regime 本就是入参

依赖方向: indicators → config, util  (calc_derived_metrics 复用同层 technical/valuation)
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from vaxstock.config import ALERT_RULES
from vaxstock.indicators.technical import calc_macd, calc_rsi
from vaxstock.indicators.valuation import (
    calc_inflow_slope,
    calc_pe_pb_percentile,
    calc_turnover_zscore,
)
from vaxstock.util import fmt_num, fmt_pct, safe_float

logger = logging.getLogger(__name__)


def calc_right_side_score(
        price: Optional[float],
        ma5: Optional[float],
        volume_ratio_5d: Optional[float],
        change_pct: Optional[float],
        turnover_zscore: Optional[float],
        inflow_slope: Optional[float],  # v1.1: 保留参数但不再使用
        inflow_10d: Optional[float],
        holder_change_pct: Optional[float],
        position_20d_pct: Optional[float],  # 价值市/恐慌豁免时使用
        np_yoy: Optional[float],
        pe_percentile_1y: Optional[float] = None,
        market_regime: str = "momentum",  # "momentum" / "value" / "panic"
        circ_mv_yi: Optional[float] = None,  # v1.2新增: 流通市值(亿),用于资金流归一化
) -> Dict[str, Any]:
    """右侧确认信号综合评分 v1.2

    v1.2 变化（2026-06-12）:
      ① 资金流市值归一化分档: 10日净流入/流通市值,大小盘公平比较
         (v1.1的二值逻辑作为无市值数据时的回退)
      ② 恐慌市优质豁免: 业绩>20%+PE历史<20%+20日低位<30% 三条件同时满足时
         恐慌惩罚归零(解决"恐慌底系统性回避"的设计矛盾)
      ⚠️ 分档阈值为逻辑设定,待9月回测验证后再校准

    评分阈值:
      >= 3.5 强买入信号 | >= 2.0 可考虑介入 | >= 0.5 观察等待 | < 0.5 回避
    """
    score = 0.0
    signals = []

    # ① 核心因子1: 10日主力净流入（v1.4 回测校准分档）
    # 【校准 2026-06-19】阈值由 zz800(1080只)回测确定, 替换旧拍脑袋值 0.5%/0.1%。
    #   依据: inflow_10d_ratio 10分位收益, 区分力集中在最高档(>1.28%收益跳升至1.0%);
    #         0.13%~1.28%温和(0.56-0.60%); 0~0.13%各档差异小且全为正。
    #   改为加分制: 回测显示净流出档未来收益仍为正(bin0=0.51%), 故流出不扣分(旧版误扣-1.0)。
    #   注: 该因子全市场多空仅+1.49%(非最强), 净利同比+4.70%才是最强; 但大盘股样本仍有效。
    if inflow_10d is not None:
        if circ_mv_yi and circ_mv_yi > 0:
            # 归一化: 流入占流通市值百分比
            ratio_pct = inflow_10d / (circ_mv_yi * 1e8) * 100
            if ratio_pct >= 1.28:
                score += 1.5
                signals.append(f"✅10日强流入+{inflow_10d/1e8:.2f}亿(占市值{ratio_pct:.2f}%)")
            elif ratio_pct >= 0.13:
                score += 1.0
                signals.append(f"✅10日中等流入+{inflow_10d/1e8:.2f}亿(占{ratio_pct:.2f}%)")
            elif ratio_pct > 0:
                score += 0.5
                signals.append(f"➕10日弱流入+{inflow_10d/1e8:.2f}亿(占{ratio_pct:.2f}%)")
            else:
                # 净流出: 回测显示流出档收益仍为正, 不扣分, 仅标注
                signals.append(f"➖10日净流出{inflow_10d/1e8:+.2f}亿(占{ratio_pct:.2f}%,中性不扣分)")
        else:
            # 回退逻辑（无市值数据时, 无法归一化, 仅按方向给弱信号）
            if inflow_10d > 0:
                score += 0.5
                signals.append(f"➕10日主力净流入+{inflow_10d/1e8:.2f}亿(无市值数据,弱信号)")
            else:
                signals.append(f"➖10日资金流{inflow_10d/1e8:+.2f}亿(无市值数据,中性)")

    # ① 核心因子2: 净利同比（第2强因子,IC=0.0201）
    if np_yoy is not None:
        if np_yoy > 50:
            score += 1.5
            signals.append(f"✅业绩大幅增长 净利同比+{np_yoy:.0f}%")
        elif np_yoy > 20:
            score += 1.0
            signals.append(f"✅业绩高增长 净利同比+{np_yoy:.0f}%")
        elif np_yoy > 0:
            score += 0.3
            signals.append(f"➕业绩微增 净利同比+{np_yoy:.0f}%")
        elif np_yoy < -20:
            score -= 0.5
            signals.append(f"🚨业绩恶化 净利同比{np_yoy:.0f}%")

    # ① 核心因子3: 股东户数变化（ICIR最稳定2.77）
    if holder_change_pct is not None:
        if holder_change_pct < -2:
            score += 1.0
            signals.append(f"✅股东强集中{holder_change_pct:+.1f}%")
        elif holder_change_pct < 0:
            score += 0.5
            signals.append(f"⚠️股东轻微集中{holder_change_pct:+.1f}%")
        elif holder_change_pct > 10:
            score -= 0.5
            signals.append(f"🚨股东强分散{holder_change_pct:+.1f}%")
        else:
            signals.append(f"➖股东基本稳定{holder_change_pct:+.1f}%")

    # ② 辅助因子: MA5偏离度（v1.1方向反转,低于MA5是低吸机会）
    if price and ma5 and ma5 > 0:
        ma5_dev = (price - ma5) / ma5 * 100
        if ma5_dev < -3:
            score += 0.5
            signals.append(f"✅低于MA5 {ma5_dev:.1f}%(低吸机会)")
        elif ma5_dev > 5:
            signals.append(f"⚠️高于MA5 {ma5_dev:.1f}%(注意追高)")

    # ② 辅助因子: 换手异常
    if turnover_zscore is not None:
        if turnover_zscore > 2.0:
            score -= 1.0
            signals.append(f"🚨换手异常Z={turnover_zscore:.1f}(警惕派发)")

    # ③ 市场环境过滤（regime filter, v1.2含恐慌豁免）
    if market_regime == "value":
        if pe_percentile_1y is not None and pe_percentile_1y < 30:
            score += 0.5
            signals.append(f"✅PE历史低位{pe_percentile_1y:.0f}%(价值市)")
        if position_20d_pct is not None and position_20d_pct < 30:
            score += 0.5
            signals.append(f"✅20日低位{position_20d_pct:.0f}%(价值市)")
    elif market_regime == "panic":
        # v1.2: 优质低位股豁免恐慌惩罚
        is_quality_dip = (
                np_yoy is not None and np_yoy > 20
                and pe_percentile_1y is not None and pe_percentile_1y < 20
                and position_20d_pct is not None and position_20d_pct < 30
        )
        if is_quality_dip:
            signals.append("💎恐慌市优质低位(业绩+估值+位置三重确认),左侧关注")
        else:
            score -= 1.0
            signals.append("⚠️恐慌市,建议观望")
    # else: 动量市,反转因子不参与评分

    score = round(score, 1)

    if score >= 3.5:
        grade = "强买入信号"
    elif score >= 2.0:
        grade = "可考虑介入"
    elif score >= 0.5:
        grade = "观察等待"
    else:
        grade = "回避"

    return {"score": score, "signals": signals, "grade": grade}


def calc_derived_metrics(
        realtime: Optional[Dict[str, Any]],
        history: Optional[List[Dict[str, Any]]],
        cost_price: Optional[float],
        shares: Optional[int] = None,
        money_flow: Optional[Dict[str, Any]] = None,
        quarterly: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {
        "ma5": None, "ma10": None, "ma20": None, "ma60": None,
        "price_vs_ma5_pct": None, "price_vs_ma10_pct": None,
        "price_vs_ma20_pct": None, "price_vs_ma60_pct": None,
        "ma_trend": None,  # bullish/bearish/neutral
        "volume_ratio_5d": None, "volume_ratio_20d": None,
        "turnover_pct": None,
        "pe_ttm": None, "pb_mrq": None, "ps_ttm": None, "pcf_ncf_ttm": None,
        "pe_percentile_1y": None, "pb_percentile_1y": None,
        "range_20d_high": None, "range_20d_low": None, "position_20d_pct": None,
        "range_52w_high": None, "range_52w_low": None, "position_52w_pct": None,
        "recent_5d_change_pct": None, "recent_20d_change_pct": None, "ytd_change_pct": None,
        "macd_dif": None, "macd_dea": None, "macd_hist": None,
        "rsi_14": None,
        "pnl_pct": None, "pnl_amount": None,
        # 资金流向
        "main_inflow_today": None, "main_inflow_today_pct": None,
        "main_inflow_5d": None, "main_inflow_10d": None,
        # 量化新增指标(v1.0)
        "turnover_zscore": None,
        "inflow_slope": None,
        "right_side_score": None,
        "right_side_signals": [],
        "right_side_grade": None,
        # 业绩
        "revenue_yoy": None, "np_yoy": None, "roe_avg": None,
        "gross_margin": None, "report_date": None,
        "risk_level": "UNKNOWN", "alerts": [],
    }

    if not realtime:
        metrics["alerts"].append("实时行情获取失败")
        metrics["risk_level"] = "DATA_MISSING"
        return metrics

    price = realtime.get("price")
    if cost_price and price:
        metrics["pnl_pct"] = (price - cost_price) / cost_price * 100
        if shares:
            metrics["pnl_amount"] = (price - cost_price) * shares

    if history:
        closes = [safe_float(x.get("close"), None) for x in history]
        closes = [x for x in closes if x is not None]
        volumes = [safe_float(x.get("volume"), None) for x in history]
        volumes = [x for x in volumes if x is not None]
        highs = [safe_float(x.get("high"), None) for x in history]
        highs = [x for x in highs if x is not None]
        lows = [safe_float(x.get("low"), None) for x in history]
        lows = [x for x in lows if x is not None]

        def avg_last(n: int, arr: List[float]) -> Optional[float]:
            if len(arr) < n:
                return None
            return sum(arr[-n:]) / n

        metrics["ma5"] = avg_last(5, closes)
        metrics["ma10"] = avg_last(10, closes)
        metrics["ma20"] = avg_last(20, closes)
        metrics["ma60"] = avg_last(60, closes)

        for key in ["ma5", "ma10", "ma20", "ma60"]:
            ma = metrics[key]
            if ma and price:
                metrics[f"price_vs_{key}_pct"] = (price - ma) / ma * 100

        # 均线趋势判断
        if all(metrics[k] is not None for k in ["ma5", "ma10", "ma20", "ma60"]):
            if metrics["ma5"] > metrics["ma10"] > metrics["ma20"] > metrics["ma60"]:
                metrics["ma_trend"] = "强多头(多头排列)"
            elif metrics["ma5"] < metrics["ma10"] < metrics["ma20"] < metrics["ma60"]:
                metrics["ma_trend"] = "强空头(空头排列)"
            elif metrics["ma5"] > metrics["ma20"] and metrics["ma20"] > metrics["ma60"]:
                metrics["ma_trend"] = "弱多头"
            elif metrics["ma5"] < metrics["ma20"] and metrics["ma20"] < metrics["ma60"]:
                metrics["ma_trend"] = "弱空头"
            else:
                metrics["ma_trend"] = "震荡"

        avg_volume_5 = avg_last(5, volumes)
        avg_volume_20 = avg_last(20, volumes)
        if avg_volume_5 and realtime.get("volume"):
            metrics["volume_ratio_5d"] = realtime["volume"] / avg_volume_5
        if avg_volume_20 and realtime.get("volume"):
            metrics["volume_ratio_20d"] = realtime["volume"] / avg_volume_20

        # 20日区间
        if highs and lows:
            high_20 = max(highs[-20:])
            low_20 = min(lows[-20:])
            metrics["range_20d_high"] = high_20
            metrics["range_20d_low"] = low_20
            if high_20 > low_20 and price:
                metrics["position_20d_pct"] = (price - low_20) / (high_20 - low_20) * 100

        # 52周(250个交易日)区间
        if len(highs) >= 200:
            high_52w = max(highs[-250:])
            low_52w = min(lows[-250:])
            metrics["range_52w_high"] = high_52w
            metrics["range_52w_low"] = low_52w
            if high_52w > low_52w and price:
                metrics["position_52w_pct"] = (price - low_52w) / (high_52w - low_52w) * 100

        # 近期涨跌幅
        if len(closes) >= 6:
            metrics["recent_5d_change_pct"] = (closes[-1] - closes[-6]) / closes[-6] * 100 if closes[-6] else None
        if len(closes) >= 21:
            metrics["recent_20d_change_pct"] = (closes[-1] - closes[-21]) / closes[-21] * 100 if closes[-21] else None

        # YTD: 年初首个交易日收盘价
        if history:
            year_start = datetime.now().strftime("%Y-01")
            year_first_close = None
            for h in history:
                d = h.get("date", "")
                if d.startswith(year_start) or d.startswith(datetime.now().strftime("%Y-02")):
                    year_first_close = safe_float(h.get("close"), None)
                    if year_first_close:
                        break
            if year_first_close and price:
                metrics["ytd_change_pct"] = (price - year_first_close) / year_first_close * 100

        # MACD / RSI
        macd = calc_macd(closes)
        metrics["macd_dif"] = macd["dif"]
        metrics["macd_dea"] = macd["dea"]
        metrics["macd_hist"] = macd["macd"]
        metrics["rsi_14"] = calc_rsi(closes, 14)

        # 估值
        last = history[-1]
        metrics["turnover_pct"] = safe_float(last.get("turn"), None)
        metrics["pe_ttm"] = safe_float(last.get("peTTM"), None)
        metrics["pb_mrq"] = safe_float(last.get("pbMRQ"), None)
        metrics["ps_ttm"] = safe_float(last.get("psTTM"), None)
        metrics["pcf_ncf_ttm"] = safe_float(last.get("pcfNcfTTM"), None)

        # 估值历史百分位
        percentiles = calc_pe_pb_percentile(history, metrics["pe_ttm"], metrics["pb_mrq"])
        metrics["pe_percentile_1y"] = percentiles["pe_percentile"]
        metrics["pb_percentile_1y"] = percentiles["pb_percentile"]

    # 资金流向
    if money_flow:
        metrics["main_inflow_today"] = money_flow.get("main_inflow_today")
        metrics["main_inflow_today_pct"] = money_flow.get("main_inflow_today_pct")
        metrics["main_inflow_5d"] = money_flow.get("main_inflow_5d")
        metrics["main_inflow_10d"] = money_flow.get("main_inflow_10d")

    # 量化新增指标(v1.0) —— holder_change_pct 在 build_stock_item 层回填，此处先算无需户数的部分
    if history:
        metrics["turnover_zscore"] = calc_turnover_zscore(history, metrics.get("turnover_pct"))
    metrics["inflow_slope"] = calc_inflow_slope(
        metrics.get("main_inflow_5d"),
        metrics.get("main_inflow_10d"),
    )
    # right_side_score 先算一次（无户数版），build_stock_item 拿到 holder_change 后会重算
    _rss = calc_right_side_score(
        price=price,
        ma5=metrics.get("ma5"),
        volume_ratio_5d=metrics.get("volume_ratio_5d"),
        change_pct=realtime.get("change_pct") if realtime else None,
        turnover_zscore=metrics.get("turnover_zscore"),
        inflow_slope=metrics.get("inflow_slope"),
        inflow_10d=metrics.get("main_inflow_10d"),
        holder_change_pct=None,
        position_20d_pct=metrics.get("position_20d_pct"),
        np_yoy=metrics.get("np_yoy"),
        pe_percentile_1y=metrics.get("pe_percentile_1y"),
        market_regime="momentum",  # 默认动量市,build_stock_item 层会用真实regime重算
    )
    metrics["right_side_score"] = _rss["score"]
    metrics["right_side_signals"] = _rss["signals"]
    metrics["right_side_grade"] = _rss["grade"]

    # 业绩
    if quarterly:
        metrics["np_yoy"] = quarterly.get("np_yoy")
        metrics["roe_avg"] = quarterly.get("roe_avg")
        metrics["gross_margin"] = quarterly.get("gross_margin")
        metrics["report_date"] = quarterly.get("stat_date")

    # 警报
    alerts: List[str] = []
    if abs(realtime.get("change_pct") or 0) >= ALERT_RULES["price_change_pct"]:
        alerts.append(f"单日涨跌幅{fmt_pct(realtime.get('change_pct'))}")
    if (realtime.get("amplitude_pct") or 0) >= ALERT_RULES["amplitude_pct"]:
        alerts.append(f"日内振幅{fmt_num(realtime.get('amplitude_pct'), 2, '%')}")
    if metrics.get("volume_ratio_5d") and metrics["volume_ratio_5d"] >= ALERT_RULES["volume_ratio"]:
        alerts.append(f"放量{metrics['volume_ratio_5d']:.2f}倍(5日)")
    if metrics.get("position_20d_pct") is not None:
        if metrics["position_20d_pct"] >= ALERT_RULES["position_high_pct"]:
            alerts.append(f"接近20日高位({metrics['position_20d_pct']:.0f}%)")
        elif metrics["position_20d_pct"] <= ALERT_RULES["position_low_pct"]:
            alerts.append(f"接近20日低位({metrics['position_20d_pct']:.0f}%)")
    # 资金流向警报
    if metrics.get("main_inflow_today"):
        inflow_yi = metrics["main_inflow_today"] / 1e8
        if inflow_yi >= ALERT_RULES["main_inflow_yi"]:
            alerts.append(f"主力净流入{inflow_yi:.2f}亿")
        elif inflow_yi <= ALERT_RULES["main_outflow_yi"]:
            alerts.append(f"主力净流出{abs(inflow_yi):.2f}亿")
    # 估值历史位置警报
    if metrics.get("pe_percentile_1y") is not None:
        if metrics["pe_percentile_1y"] >= 90:
            alerts.append(f"PE历史高位({metrics['pe_percentile_1y']:.0f}%)")
        elif metrics["pe_percentile_1y"] <= 10:
            alerts.append(f"PE历史低位({metrics['pe_percentile_1y']:.0f}%)")
    # MACD金叉死叉提示
    if metrics.get("macd_hist") is not None:
        if metrics["macd_hist"] > 0 and metrics.get("macd_dif", 0) > metrics.get("macd_dea", 0):
            pass  # 多头不重复提示
        elif metrics["macd_hist"] < -0.5:
            alerts.append("MACD空头加速")
    # RSI 超买超卖
    if metrics.get("rsi_14"):
        if metrics["rsi_14"] >= 80:
            alerts.append(f"RSI超买({metrics['rsi_14']:.0f})")
        elif metrics["rsi_14"] <= 20:
            alerts.append(f"RSI超卖({metrics['rsi_14']:.0f})")
    # XD除息
    if realtime.get("name") and "XD" in realtime["name"]:
        alerts.append("今日除息XD")
    # 持仓盈亏
    if cost_price is not None and metrics.get("pnl_pct") is not None:
        alerts.append(f"持仓盈亏{fmt_pct(metrics['pnl_pct'])}")

    metrics["alerts"] = alerts
    if any("涨跌幅" in x or "振幅" in x or "放量" in x or "净流入" in x or "净流出" in x for x in alerts):
        metrics["risk_level"] = "HIGH_ATTENTION"
    elif alerts:
        metrics["risk_level"] = "WATCH"
    else:
        metrics["risk_level"] = "NORMAL"

    return metrics
