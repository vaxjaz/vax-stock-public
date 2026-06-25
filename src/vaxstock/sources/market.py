# -*- coding: utf-8 -*-
"""大盘数据源(Tushare)。

MR3: 东财(eastmoney)迁移到 Tushare, 从数据流中移除东财依赖。
本模块用 Tushare 实现原东财大盘相关函数的等价数据, 输出字段结构与原函数兼容,
下游(render_index_table / detect_market_regime 等)无需改动。

提供:
    get_index_quotes(source)    指数行情, 替代原 get_sina_index / 东财指数(pro.index_daily)
    get_market_overview(source) 涨跌家数 + 涨跌停, 替代 get_em_market_overview(pro.daily 全市场)

约束:
    - 所有 Tushare 调用均经 TushareSource 的 _safe_call(daemon线程 + join 墙钟超时)容错
    - 取不到数据返回空/跳过(P0 标"待验证"), 绝不臆造
    - import 本模块不触发网络(顶层只定义常量与函数)
"""

import logging
from typing import Any, Dict, List, Optional

from vaxstock import config
from vaxstock.sources.tushare_src import TushareSource
from vaxstock.util import safe_float

logger = logging.getLogger(__name__)

# 涨跌停阈值: 主板等 ±10%(阈值 9.8 容忍四舍五入); 创业板/科创 ±20%(阈值 19.5)
LIMIT_THRESH_10 = (9.8, -9.8)
LIMIT_THRESH_20 = (19.5, -19.5)

# ts_code 数字前缀属于 ±20% 涨跌停的板块: 创业板(300/301) / 科创板(688)
_PCT20_PREFIXES = ("300", "301", "688")


def _sina_to_ts_index(sina_symbol: str) -> str:
    """config.INDEX_LIST 的新浪式代码(sh000001/sz399006) 转 Tushare 指数代码(000001.SH/399006.SZ)。"""
    s = str(sina_symbol).strip().lower()
    if s.startswith("sh"):
        return f"{s[2:]}.SH"
    if s.startswith("sz"):
        return f"{s[2:]}.SZ"
    return sina_symbol  # 已是 ts_code 或未知格式, 原样返回


def _board_limit_thresholds(ts_code: str):
    """按 ts_code 前缀返回 (涨停阈值, 跌停阈值): 创业板/科创 ±20%, 其余 ±10%。"""
    head = str(ts_code).split(".")[0]
    if head.startswith(_PCT20_PREFIXES):
        return LIMIT_THRESH_20
    return LIMIT_THRESH_10


def get_index_quotes(source: Optional[TushareSource]) -> List[Dict[str, Any]]:
    """用 Tushare index_daily 取 config.INDEX_LIST 各指数行情。

    替代原 get_sina_index / 东财指数。index_daily 直接返回 pct_chg, 取最近交易日该值即可。
    输出字段对齐原结构: {symbol, name, price, change_pct, volume, amount, source}。
    单只指数取不到则跳过(不臆造)。
    """
    results: List[Dict[str, Any]] = []
    if source is None:
        logger.warning("  ⚠️ Tushare未启用, 无法获取指数行情(待验证)")
        return results

    for sina_sym, name in config.INDEX_LIST:
        ts_code = _sina_to_ts_index(sina_sym)
        row = source.get_index_daily(ts_code)  # 走 _safe_call
        if not row:
            logger.debug(f"  指数 {name}({ts_code}) 无数据, 跳过(待验证)")
            continue
        results.append({
            "symbol": sina_sym,
            "name": name,
            "price": safe_float(row.get("close"), None),
            "change_pct": safe_float(row.get("pct_chg"), None),
            "volume": safe_float(row.get("vol"), None),
            "amount": safe_float(row.get("amount"), None),
            "source": "tushare",
        })
    return results


def get_market_overview(source: Optional[TushareSource]) -> Dict[str, Any]:
    """用 Tushare 全市场 daily 聚合涨跌家数 + 涨跌停, 替代 get_em_market_overview。

    流程:
      1. 取基准指数(上证 000001.SH)的最近交易日;
      2. pro.daily(trade_date=该日) 一次取全市场(经 _safe_call);
      3. 本地聚合, 涨跌停按 ts_code 前缀区分主板±10 / 创业板·科创±20。

    输出字段与原东财兼容(喂给 detect_market_regime 的 panic 判定, 字段名不变):
      {up_count, down_count, flat_count, limit_up_count, limit_down_count, total, trade_date, source}
    取不到数据返回 {}(待验证, 不臆造)。
    """
    if source is None:
        logger.warning("  ⚠️ Tushare未启用, 无法获取大盘涨跌统计(待验证)")
        return {}

    # 1. 最近交易日: 取基准指数的 trade_date(index_daily 已返回该字段)
    bench = source.get_index_daily("000001.SH")
    if not bench or not bench.get("trade_date"):
        logger.warning("  ⚠️ 无法确定最近交易日(基准指数无数据), 大盘统计待验证")
        return {}
    trade_date = str(bench.get("trade_date")).strip()
    if trade_date.endswith(".0"):
        trade_date = trade_date[:-2]

    # 2. 全市场单日 daily
    rows = source.get_market_daily(trade_date)
    if not rows:
        logger.warning(f"  ⚠️ 全市场 daily({trade_date}) 无数据, 大盘统计待验证")
        return {}

    # 3. 本地聚合(涨跌停 ⊂ 涨/跌, 与原东财计数口径一致)
    up = down = flat = limit_up = limit_down = 0
    for r in rows:
        chg = safe_float(r.get("pct_chg"), None)
        if chg is None:
            continue
        up_lim, down_lim = _board_limit_thresholds(r.get("ts_code", ""))
        if chg >= up_lim:
            limit_up += 1
            up += 1
        elif chg <= down_lim:
            limit_down += 1
            down += 1
        elif chg > 0:
            up += 1
        elif chg < 0:
            down += 1
        else:
            flat += 1

    total = up + down + flat
    logger.info(f"  ✅ 大盘涨跌统计(Tushare {trade_date}): 总{total} "
                f"涨{up} 跌{down} 平{flat} 涨停{limit_up} 跌停{limit_down}")

    return {
        "up_count": up,
        "down_count": down,
        "flat_count": flat,
        "limit_up_count": limit_up,
        "limit_down_count": limit_down,
        "total": total,
        "trade_date": trade_date,
        "source": "tushare",
    }
