# -*- coding: utf-8 -*-
"""新浪财经数据源。

从单体脚本 script/stock_report_enhanced.py 原样搬运, 逻辑零改动。
搬运时的调整(均不改变行为):
    - logger 改用 logging.getLogger(__name__)
    - SINA_HEADERS 改为引用 config.SINA_HEADERS
    - safe_float / safe_int 改为从 vaxstock.util 显式导入

注意: import 本模块不触发任何网络请求(顶层只定义函数)。
"""

import logging
from typing import Any, Dict, Optional

import requests

from vaxstock import config
from vaxstock.util import safe_float, safe_int

logger = logging.getLogger(__name__)


def code_to_sina(code: str) -> str:
    if code.startswith(("sh", "sz")):
        return code
    prefix = "sh" if code.startswith(("6", "9")) else "sz"
    return f"{prefix}{code}"


def get_sina_realtime(code: str, expected_name: str = "") -> Optional[Dict[str, Any]]:
    try:
        symbol = code_to_sina(code)
        url = f"https://hq.sinajs.cn/list={symbol}"
        response = requests.get(url, headers=config.SINA_HEADERS, timeout=8)
        response.encoding = "gbk"
        text = response.text
        if '"' not in text:
            return None

        data_str = text.split('"')[1]
        fields = data_str.split(",")
        if len(fields) < 32 or not fields[0]:
            return None

        open_price = safe_float(fields[1])
        pre_close = safe_float(fields[2])
        current_price = safe_float(fields[3])
        high = safe_float(fields[4])
        low = safe_float(fields[5])

        if not current_price or current_price <= 0:
            current_price = pre_close

        change_amount = current_price - pre_close if current_price is not None and pre_close else 0.0
        change_pct = change_amount / pre_close * 100 if pre_close else 0.0
        amplitude_pct = (high - low) / pre_close * 100 if high and low and pre_close else 0.0

        return {
            "code": code,
            "symbol": symbol,
            "name": fields[0] or expected_name,
            "open": open_price,
            "pre_close": pre_close,
            "price": current_price,
            "high": high,
            "low": low,
            "volume": safe_int(fields[8]),
            "amount": safe_float(fields[9]),
            "change_amount": change_amount,
            "change_pct": change_pct,
            "amplitude_pct": amplitude_pct,
            "trade_date": fields[30] if len(fields) > 30 else "",
            "trade_time": fields[31] if len(fields) > 31 else "",
            "source": "sina",
        }
    except Exception as e:
        logger.warning(f"  ⚠️ {code} 新浪实时数据获取失败: {str(e)[:80]}")
        return None


def get_sina_index(symbol: str, name: str) -> Optional[Dict[str, Any]]:
    try:
        url = f"https://hq.sinajs.cn/list=s_{symbol}"
        response = requests.get(url, headers=config.SINA_HEADERS, timeout=8)
        response.encoding = "gbk"
        text = response.text
        if '"' not in text:
            return None

        data_str = text.split('"')[1]
        fields = data_str.split(",")
        if len(fields) < 4:
            return None

        return {
            "symbol": symbol,
            "name": name,
            "price": safe_float(fields[1]),
            "change_amount": safe_float(fields[2]),
            "change_pct": safe_float(fields[3]),
            "volume": safe_float(fields[4]) if len(fields) > 4 else None,
            "amount": safe_float(fields[5]) if len(fields) > 5 else None,
            "source": "sina",
        }
    except Exception as e:
        logger.warning(f"  ⚠️ {name} 指数获取失败: {str(e)[:80]}")
        return None
