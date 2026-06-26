# -*- coding: utf-8 -*-
"""services 层: collect_payload —— EOD 数据采集编排器(取数 + 组装 payload)。

MR6 PR-A: 从 monolith stock_report_enhanced.py 迁入 collect_payload。EOD 串联/邮件/api/intraday
不在本 PR(留 PR-B/C)。

对接 main 真实签名(不臆造):
  detect_market_regime(indices, market_overview)  -> str        indicators.regime
  get_index_quotes(source) -> List[Dict]                        sources.market
  get_market_overview(source) -> Dict                           sources.market
  source.get_hsgt_flow(days=10)                                 sources.tushare_src
  fetch_us_market_data() -> Dict                                sources.us_market
  build_stock_item(group, code, name, cost, shares, source=, market_regime=, manual_concepts=)  analysis.stock_item
  AITrack(source=src).evaluate() -> TrackResult                 tracks.ai

铁律:
  1. 消全局: regime 算成局部变量, 逐票 build_stock_item(..., market_regime=regime) 显式传;
     无 _CURRENT_MARKET_REGIME。标的池经 config.load_watchlist/load_holdings 取局部, 不建全局。
  2. 东财砍除的诚实降级: sector_analysis/hot_sector_scan/opportunity_scan/macro 一律 available=False,
     绝不 import 未迁的 build_sector_analysis/hot_sector_scanner/opportunity_scanner/macro_indicators。
  3. data_sources 只留 sina_realtime + tushare_pro_lvN(无 eastmoney_*)。
  4. TrackResult 是纯 DTO(TypedDict), 经 dict(tr) 序列化进 payload["tracks"], payload.json 可脱离内存 replay。
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from vaxstock import config
from vaxstock.analysis.stock_item import build_stock_item
from vaxstock.indicators.regime import detect_market_regime
from vaxstock.sources.market import get_index_quotes, get_market_overview
from vaxstock.sources.us_market import fetch_us_market_data
from vaxstock.tracks.ai import AITrack
from vaxstock.tracks.contract import TrackResult
from vaxstock.util import to_float

logger = logging.getLogger(__name__)


def _collect_north_flow(source, market_trade_date=None) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    """北向资金(仅 Tushare 2000+); 返回 (north_flow, hsgt_flow_history)。
    单位/日期有效性校验逻辑自 monolith 原样迁入(_to_float -> util.to_float)。

    market_trade_date(YYYYMMDD): 市场交易日基准, 用于判定 is_today。EOD 改为次日凌晨05:00跑时,
    datetime.now() 是 T+1, 用它当"当日"会把 T 日北向误判为非今日。改对照真实交易日
    (market_overview.trade_date); 取不到才退 now() 兜底(见 CLAUDE.md §9 交易日锚定铁律)。"""
    if source is None or getattr(source, "points_level", 0) < 2000:
        return {
            "total_inflow": None, "hgt_inflow": None, "sgt_inflow": None,
            "note": "Tushare未启用,北向资金数据不可用",
        }, None

    hsgt = source.get_hsgt_flow(days=10)  # 多拉几天，应对T+1延迟
    if not hsgt:
        return {
            "total_inflow": None, "hgt_inflow": None, "sgt_inflow": None,
            "note": "Tushare北向资金接口返回空",
        }, None

    # Tushare moneyflow_hsgt 字段单位: 万元; 转亿元 = 万元 / 10000
    def to_yi(v):
        f = to_float(v)
        return round(f / 10000, 2) if f is not None else None

    # "当日"对照市场交易日(非自然日): 凌晨5点跑(now=T+1)时 T 日北向仍正确标 is_today。
    # 缺交易日基准才退 now() 兜底(P0: 不臆造一个错的基准)。
    today_str = str(market_trade_date) if market_trade_date else datetime.now().strftime("%Y%m%d")
    latest = None
    for row in reversed(hsgt):
        total_v = to_yi(row.get("north_money"))
        hgt_v = to_yi(row.get("hgt"))
        sgt_v = to_yi(row.get("sgt"))
        if any(v is not None and v != 0 for v in [total_v, hgt_v, sgt_v]):
            latest = row
            break

    if not latest:
        return {
            "total_inflow": None, "hgt_inflow": None, "sgt_inflow": None,
            "note": "Tushare返回数据均为空值(2024-08后交易所已停止实时披露)",
        }, None

    total_yi = to_yi(latest.get("north_money"))
    hgt_yi = to_yi(latest.get("hgt"))
    sgt_yi = to_yi(latest.get("sgt"))
    if total_yi is None and (hgt_yi is not None or sgt_yi is not None):
        total_yi = round((hgt_yi or 0) + (sgt_yi or 0), 2)

    data_date = str(latest.get("trade_date") or "")
    is_today = data_date == today_str
    staleness_note = None if is_today else f"数据日期{data_date}(非今日,交易所延迟披露)"

    # 单日北向资金通常 ±500亿以内, 超出视为单位异常, 置 None
    if total_yi is not None and abs(total_yi) > 500:
        logger.warning(f"  ⚠️ 北向资金数值异常({total_yi:.1f}亿)，可能单位仍有误，置为None")
        total_yi = hgt_yi = sgt_yi = None
        staleness_note = "数据异常，已屏蔽"

    north_flow = {
        "total_inflow": total_yi,
        "hgt_inflow": hgt_yi,
        "sgt_inflow": sgt_yi,
        "trade_date": data_date,
        "is_today": is_today,
        "note": staleness_note,
        "source": "tushare",
    }

    history = []
    for row in hsgt:
        t_yi = to_yi(row.get("north_money"))
        h_yi = to_yi(row.get("hgt"))
        s_yi = to_yi(row.get("sgt"))
        if any(v is not None for v in [t_yi, h_yi, s_yi]):
            history.append({
                "trade_date": row.get("trade_date"),
                "north_money_yi": t_yi, "hgt_yi": h_yi, "sgt_yi": s_yi,
            })

    if total_yi is not None:
        freshness = "今日" if is_today else f"延迟({data_date})"
        logger.info(f"  ✅ 北向资金({freshness}): {total_yi:+.2f}亿 | 沪{hgt_yi or 0:.1f} 深{sgt_yi or 0:.1f}")
    return north_flow, history


def collect_payload(source) -> Tuple[Dict[str, Any], List[TrackResult]]:
    """采集 EOD payload + 赛道结果。

    source: 已初始化的 TushareSource 实例(或 None)。显式传入, 不读全局。
    返回 (payload, track_results)。payload["tracks"] 是 track_results 的序列化 dict 列表(可 replay)。
    """
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    data_sources = ["sina_realtime"]
    if source is not None:
        data_sources.append(f"tushare_pro_lv{getattr(source, 'points_level', 0)}")

    payload: Dict[str, Any] = {
        "generated_at": generated_at,
        "data_sources": data_sources,
        "tushare_points_level": getattr(source, "points_level", 0) if source is not None else 0,
        "indices": [],
        "stocks": [],
        "market_overview": {},
        "north_flow": None,
        "hsgt_flow_history": None,
        "market_regime": "momentum",
    }

    logger.info("[1/5] 获取大盘指数(Tushare index_daily)...")
    payload["indices"] = get_index_quotes(source)

    logger.info("[2/5] 获取大盘涨跌家数/涨跌停(Tushare 全市场 daily)...")
    payload["market_overview"] = get_market_overview(source)

    # 市场环境: 局部变量, 不再写 _CURRENT_MARKET_REGIME 全局; 逐票显式传入
    regime = detect_market_regime(payload["indices"], payload["market_overview"])
    payload["market_regime"] = regime
    regime_label = {"momentum": "动量市(成长股占优)", "value": "价值市(主板占优)",
                    "panic": "恐慌市(警惕)"}.get(regime, regime)
    logger.info(f"  📊 当前市场环境: {regime_label}")

    logger.info("[3/5] 获取北向资金(Tushare)...")
    # market_overview 已在上一步取得, 把其 trade_date 作"当日"基准传入(锚交易日, 不用 now())
    payload["north_flow"], payload["hsgt_flow_history"] = _collect_north_flow(
        source, market_trade_date=(payload["market_overview"] or {}).get("trade_date"))

    # 东财已砍除且无 Tushare 替代: 诚实降级, 不 import 未迁模块、不臆造
    payload["sector_analysis"] = {"available": False, "pending": "东财砍除无Tushare替代,待验证"}
    payload["hot_sector_scan"] = {"available": False, "pending": "hot_sector_scanner 未迁包,待验证"}
    payload["opportunity_scan"] = {"available": False, "pending": "opportunity_scanner 未迁包,待验证"}

    # 宏观环境(MR-Macro B1+2): 接真值, 已迁 5 维(1/2/3/4/6); 维度5/社融留 B3/B4。
    # MacroIndicator 就近懒导入(其依赖 pandas/pyarrow, 不污染 collect 顶层); summary 内逐维容错。
    # 任何异常(含无 pandas 环境)降级为 available=False, 不崩 collect、不臆造(P0)。
    try:
        from vaxstock.indicators.macro import MacroIndicator
        payload["macro"] = MacroIndicator(source).summary()
    except Exception as e:
        logger.warning(f"  ⚠️ 宏观指标采集失败: {str(e)[:120]}")
        payload["macro"] = {"available": False, "pending": f"macro 采集异常: {str(e)[:80]}"}

    logger.info("[4/5] 获取持仓与观察池(逐票装配, regime 显式传参)...")
    holdings = config.load_holdings()
    watchlist, concepts_map = config.load_watchlist()
    seen = set()
    for code, info in holdings.items():
        item = build_stock_item("holding", code, info.get("name", ""),
                                info.get("cost"), info.get("shares"),
                                source=source, market_regime=regime,
                                manual_concepts=concepts_map.get(code))
        payload["stocks"].append(item)
        seen.add(code)
        logger.info(f"  ✅ 持仓 {code} {info.get('name', '')}")
        time.sleep(config.REQUEST_SLEEP_SECONDS)
    for code, name in watchlist.items():
        if code in seen:
            continue  # 持仓股(holdings⊂watchlist)已装配, 不重复取数
        item = build_stock_item("watchlist", code, name, None, None,
                                source=source, market_regime=regime,
                                manual_concepts=concepts_map.get(code))
        payload["stocks"].append(item)
        logger.info(f"  ✅ 观察 {code} {name}")
        time.sleep(config.REQUEST_SLEEP_SECONDS)

    logger.info("[5/5] 美股参考 + AI 赛道择时...")
    try:
        payload["us_market"] = fetch_us_market_data()
    except Exception as e:
        logger.warning(f"  ⚠️ 美股数据失败: {str(e)[:80]}")
        payload["us_market"] = None

    # 赛道: 显式传 source, evaluate 零参; 结果序列化进 payload(纯 DTO, 可 replay)
    track_results: List[TrackResult] = []
    try:
        ai_result = AITrack(source=source).evaluate()
        track_results.append(ai_result)
    except Exception as e:
        logger.warning(f"  ⚠️ AI 赛道评估失败: {str(e)[:120]}")

    # TrackResult 是 TypedDict(纯 dict), 直接 dict(tr) 序列化即可——不用 dataclasses.asdict(对 dict 会报错)
    payload["tracks"] = [dict(tr) for tr in track_results]

    return payload, track_results
