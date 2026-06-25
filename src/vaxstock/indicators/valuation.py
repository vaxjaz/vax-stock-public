# -*- coding: utf-8 -*-
"""估值与资金面指标: PE/PB历史百分位 / 换手率Z-score / 资金流斜率。

从单体脚本 script/stock_report_enhanced.py 原样搬运, 逻辑零改动。
原文件中这些函数直接调用全局 safe_float, 此处改为显式 from vaxstock.util import safe_float。
"""

import math
from typing import Any, Dict, List, Optional

from vaxstock.util import safe_float


def calc_pe_pb_percentile(history: List[Dict[str, Any]], current_pe: Optional[float], current_pb: Optional[float]) -> Dict[str, Optional[float]]:
    """计算PE/PB在历史中的百分位(用过去250个交易日,约1年)"""
    if not history or len(history) < 60:
        return {"pe_percentile": None, "pb_percentile": None}

    pe_values = [safe_float(x.get("peTTM"), None) for x in history]
    pe_values = [x for x in pe_values if x is not None and x > 0]
    pb_values = [safe_float(x.get("pbMRQ"), None) for x in history]
    pb_values = [x for x in pb_values if x is not None and x > 0]

    def percentile(val, arr):
        if not val or not arr:
            return None
        sorted_arr = sorted(arr)
        below = sum(1 for x in sorted_arr if x < val)
        return round(below / len(sorted_arr) * 100, 1)

    return {
        "pe_percentile": percentile(current_pe, pe_values),
        "pb_percentile": percentile(current_pb, pb_values),
    }


def calc_turnover_zscore(history: Optional[List[Dict[str, Any]]], current_turn: Optional[float]) -> Optional[float]:
    """换手率 Z-score：今日换手率相对过去60日历史均值的标准差倍数。
    Z > 2.0  = 异常放量，大量筹码易手，高位警惕派发
    Z < -1.0 = 缩量，结合价格判断方向
    用Z-score替代绝对值，消除不同股票换手率基准差异。
    """
    if not history or current_turn is None:
        return None
    turns = []
    for x in history[-60:]:
        v = x.get("turn")
        if v is not None:
            try:
                f = float(v)
                if f > 0:
                    turns.append(f)
            except (ValueError, TypeError):
                pass
    if len(turns) < 20:
        return None
    mean = sum(turns) / len(turns)
    variance = sum((t - mean) ** 2 for t in turns) / len(turns)
    std = math.sqrt(variance)
    if std < 1e-6:
        return 0.0
    return round((current_turn - mean) / std, 2)


def calc_inflow_slope(inflow_5d: Optional[float], inflow_10d: Optional[float]) -> Optional[float]:
    """资金流动量斜率 = 近5日日均流入 - 近10日日均流入（元/日）。
    正值 = 资金流在改善（近期流入速度 > 长期均速），比10日累计早1-3天捕捉转折。
    负值 = 资金流在恶化。
    """
    if inflow_5d is None or inflow_10d is None:
        return None
    return round(inflow_5d / 5 - inflow_10d / 10, 2)
