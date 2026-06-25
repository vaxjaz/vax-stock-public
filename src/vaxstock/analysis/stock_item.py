# -*- coding: utf-8 -*-
"""单票组装(analysis 层核心)。

从单体脚本 script/stock_report_enhanced.py 搬运 build_stock_item。行为(逻辑)保持一致,
仅做以下"消除全局态 + 改 import 引用"的必要改造:

  消除 monolith 模块级全局(新包不应有隐式全局态), 改为显式入参/走 config:
    - 全局 TUSHARE             -> 入参 source: Optional[TushareSource]
    - 全局 _CURRENT_MARKET_REGIME -> 入参 market_regime: str = "momentum"
                                    (贯穿 build_stock_item -> calc_right_side_score)
    - 全局 STOCK_CONCEPTS.get(code) -> 入参 manual_concepts: Optional[List[str]]
    - 全局 DATA_SOURCES_CONFIG    -> 读 config.SECRETS(配置层, import 安全)

  数据源/指标改为显式导入: sources.sina / sources.tushare_src / indicators.scoring
    - 历史K线: get_history_kline(source, code)  (MR2 起 source 显式传入)
    - 资金流: source.get_moneyflow_summary(Tushare)。MR3 已移除东财兜底——
             Tushare 取不到时 money_flow 保持 None(P0 标"待验证"), 不再 fallback 东财
    - _to_float -> util.to_float(仅函数名规整, 逻辑不变)

依赖方向: analysis → indicators / sources / config / util
"""

import logging
from typing import Any, Dict, List, Optional

from vaxstock import config
from vaxstock.indicators.scoring import calc_derived_metrics, calc_right_side_score
from vaxstock.sources.sina import get_sina_realtime
from vaxstock.sources.tushare_src import TushareSource, get_history_kline
from vaxstock.util import to_float

logger = logging.getLogger(__name__)


def build_stock_item(
        group: str,
        code: str,
        name: str,
        cost: Optional[float],
        shares: Optional[int],
        source: Optional[TushareSource] = None,
        market_regime: str = "momentum",
        manual_concepts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    import concurrent.futures as _f

    has_ts = source is not None and source.points_level >= 2000
    use_concepts = (source is not None
                    and config.SECRETS.get("auto_concept_sync", False))

    # ---- 并发拉取所有相互独立的数据源 ----
    # 原实现串行 8~9 次网络调用(冷缓存可达 90s 超时)。各调用彼此独立、无共享状态,
    # 改为并发后墙钟≈最慢单项。⚠️ Tushare 并发安全性需在 VPS 上 `--once` 实测确认无误后再常驻。
    tasks = {}
    with _f.ThreadPoolExecutor(max_workers=8) as ex:
        tasks["realtime"] = ex.submit(get_sina_realtime, code, name)
        tasks["history"]  = ex.submit(get_history_kline, source, code)
        if has_ts:
            tasks["money_flow"]  = ex.submit(source.get_moneyflow_summary, code)
            tasks["fina"]        = ex.submit(source.get_fina_indicator, code, 4)
            tasks["forecast"]    = ex.submit(source.get_forecast, code, 2)
            tasks["holder"]      = ex.submit(source.get_holder_number, code, 2)
            tasks["daily_basic"] = ex.submit(source.get_daily_basic, code)
        if use_concepts:
            tasks["concepts"] = ex.submit(source.get_stock_concepts, code)

        def _res(key, default=None):
            fut = tasks.get(key)
            if fut is None:
                return default
            try:
                return fut.result()
            except Exception as e:
                logger.debug(f"  ⚠️ {code} {key} 取数失败: {e}")
                return default

        realtime    = _res("realtime")
        history     = _res("history")
        money_flow  = _res("money_flow")
        fina_recs   = _res("fina")
        forecasts   = _res("forecast")
        holders     = _res("holder")
        daily_basic = _res("daily_basic")
        ts_concepts = _res("concepts")

    # 资金流向: MR3 已移除东财兜底, 仅走 Tushare(money_flow 来自 source.get_moneyflow_summary)。
    # Tushare 无数据/无权限时 money_flow 保持 None —— 按 P0 标"待验证", 不再 fallback 东财。

    # 业绩: 复用 periods=4 首条(去掉原先 periods=1 的重复拉取, 字段完全一致)
    quarterly = None
    if fina_recs:
        lf = fina_recs[0]
        quarterly = {
            "stat_date": lf.get("end_date"),
            "pub_date": lf.get("ann_date"),
            "roe_avg": to_float(lf.get("roe")),
            "roe_dt": to_float(lf.get("roe_dt")),
            "gross_margin": to_float(lf.get("grossprofit_margin")),
            "net_margin": to_float(lf.get("netprofit_margin")),
            "debt_to_assets": to_float(lf.get("debt_to_assets")),
            "eps": to_float(lf.get("eps")),
            "ocfps": to_float(lf.get("ocfps")),
            "np_yoy": to_float(lf.get("netprofit_yoy")),
            "or_yoy": to_float(lf.get("or_yoy")),
            "op_yoy": to_float(lf.get("op_yoy")),
            "q_np_yoy": to_float(lf.get("q_npincome_yoy")),
            "q_or_yoy": to_float(lf.get("q_sales_yoy")),
        }

    metrics = calc_derived_metrics(realtime, history, cost, shares, money_flow, quarterly)

    # 业绩预告
    forecast_info = None
    if forecasts:
        latest = forecasts[0]
        forecast_info = {
            "end_date": latest.get("end_date"),
            "ann_date": latest.get("ann_date"),
            "type": latest.get("type"),
            "p_change_min": to_float(latest.get("p_change_min")),
            "p_change_max": to_float(latest.get("p_change_max")),
            "net_profit_min_wan": to_float(latest.get("net_profit_min")),
            "net_profit_max_wan": to_float(latest.get("net_profit_max")),
            "summary": latest.get("summary"),
        }

    # 股东户数变化(筹码集中度)
    holder_change = None
    if holders and len(holders) >= 2:
        latest_count = to_float(holders[0].get("holder_num"))
        prev_count = to_float(holders[1].get("holder_num"))
        if latest_count and prev_count:
            holder_change = {
                "latest_date": holders[0].get("end_date"),
                "latest_count": latest_count,
                "prev_date": holders[1].get("end_date"),
                "prev_count": prev_count,
                "change_pct": (latest_count - prev_count) / prev_count * 100,
                "interpretation": "筹码集中(利好)" if latest_count < prev_count else "筹码分散(警惕)",
            }

    # 财务4期历史(带报告期口径标签)
    fina_history = None
    if fina_recs:
        fina_history = []
        for r in fina_recs:
            end_date = str(r.get("end_date") or "")
            quarter_label = "?"
            if len(end_date) >= 8:
                mmdd = end_date[4:8]
                quarter_label = {
                    "0331": "Q1(单季)",
                    "0630": "H1(累计)",
                    "0930": "Q1-Q3(累计)",
                    "1231": "全年(累计)",
                }.get(mmdd, "?")
            fina_history.append({
                "end_date": end_date,
                "period_type": quarter_label,
                "roe": to_float(r.get("roe")),
                "gross_margin": to_float(r.get("grossprofit_margin")),
                "net_margin": to_float(r.get("netprofit_margin")),
                "np_yoy": to_float(r.get("netprofit_yoy")),
                "or_yoy": to_float(r.get("or_yoy")),
                "q_np_yoy": to_float(r.get("q_npincome_yoy")),
            })

    # 概念标签: 手动(入参) + Tushare合并
    manual_concepts = list(manual_concepts or [])
    final_concepts = list(manual_concepts)
    tushare_concepts_count = 0
    if ts_concepts:
        for c in ts_concepts:
            if c and c not in final_concepts:
                final_concepts.append(c)
                tushare_concepts_count += 1

    # 资金流分档明细注入metrics(供报告渲染)
    if money_flow and isinstance(money_flow, dict):
        for k in ["buy_elg_amount", "sell_elg_amount", "buy_lg_amount", "sell_lg_amount"]:
            if k in money_flow:
                metrics[k] = money_flow[k]

    hc_pct = holder_change.get("change_pct") if holder_change else None

    # v1.2: 流通市值(亿), 来自已并发取回的 daily_basic
    circ_mv_yi = None
    if daily_basic and daily_basic.get("circ_mv"):
        try:
            circ_mv_yi = float(daily_basic["circ_mv"]) / 1e4  # 万元→亿元
            metrics["circ_mv_yi"] = round(circ_mv_yi, 1)
        except Exception:
            pass

    _rss_final = calc_right_side_score(
        price=realtime.get("price") if realtime else None,
        ma5=metrics.get("ma5"),
        volume_ratio_5d=metrics.get("volume_ratio_5d"),
        change_pct=realtime.get("change_pct") if realtime else None,
        turnover_zscore=metrics.get("turnover_zscore"),
        inflow_slope=metrics.get("inflow_slope"),
        inflow_10d=metrics.get("main_inflow_10d"),
        holder_change_pct=hc_pct,
        position_20d_pct=metrics.get("position_20d_pct"),
        np_yoy=metrics.get("np_yoy"),
        pe_percentile_1y=metrics.get("pe_percentile_1y"),
        market_regime=market_regime,
        circ_mv_yi=circ_mv_yi,
    )
    metrics["right_side_score"] = _rss_final["score"]
    metrics["right_side_signals"] = _rss_final["signals"]
    metrics["right_side_grade"] = _rss_final["grade"]

    return {
        "group": group,
        "code": code,
        "configured_name": name,
        "cost_price": cost,
        "shares": shares,
        "concepts": final_concepts,
        "concepts_manual_count": len(manual_concepts),
        "concepts_tushare_count": tushare_concepts_count,
        "realtime": realtime,
        "metrics": metrics,
        "forecast": forecast_info,
        "holder_change": holder_change,
        "fina_history": fina_history,
        "history_tail": history[-5:] if history else [],
    }
