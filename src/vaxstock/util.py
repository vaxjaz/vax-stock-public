# -*- coding: utf-8 -*-
"""无状态工具函数层。

均从单体脚本 script/stock_report_enhanced.py 原样搬运, 逻辑零改动。
(to_float 对应原文件中的 _to_float, 仅去掉前导下划线作为公开 API。)
"""

import math
from typing import Any, Optional


def safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        if value is None or value == "" or value == "-":
            return default
        v = float(value)
        if math.isnan(v):
            return default
        return v
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "" or value == "-":
            return default
        return int(float(value))
    except Exception:
        return default


def fmt_num(value: Optional[float], digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}{suffix}"


def fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "-"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def fmt_amount_yi(amount: Optional[float]) -> str:
    if amount is None:
        return "-"
    return f"{amount / 100000000:.2f}亿"


def to_float(v):
    """安全转float"""
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return None if (f != f) else f  # 排除NaN
    except (ValueError, TypeError):
        return None
