# -*- coding: utf-8 -*-
"""技术指标: 均线(EMA) / MACD / RSI。

从单体脚本 script/stock_report_enhanced.py 原样搬运, 逻辑零改动。
"""

from typing import Dict, List, Optional


def calc_ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(alpha * v + (1 - alpha) * ema[-1])
    return ema


def calc_macd(closes: List[float], short: int = 12, long: int = 26, signal: int = 9) -> Dict[str, Optional[float]]:
    if len(closes) < long + signal:
        return {"dif": None, "dea": None, "macd": None}
    ema_short = calc_ema(closes, short)
    ema_long = calc_ema(closes, long)
    dif = [a - b for a, b in zip(ema_short, ema_long)]
    dea = calc_ema(dif, signal)
    macd = [(d - de) * 2 for d, de in zip(dif, dea)]
    return {
        "dif": round(dif[-1], 3),
        "dea": round(dea[-1], 3),
        "macd": round(macd[-1], 3),
    }


def calc_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)
