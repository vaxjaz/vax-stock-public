# -*- coding: utf-8 -*-
"""Read the replaceable latest EOD baseline; never fall back to retired reports."""

import datetime as dt
import json
import logging
from typing import Optional

from vaxstock import config

logger = logging.getLogger(__name__)


def load_t1_baseline(code) -> Optional[dict]:
    """取覆盖更新的 current_baseline.json 中该 code 的 T-1 定稿基准。

    返回 {score, grade, position_20d_pct, main_inflow_10d, np_yoy, baseline_date};
    找不到当前快照/code/解析失败 -> None(P0: 不抛、不臆造)。
    """
    cj = config.STATE_DIR / "eod" / "current_baseline.json"
    if not cj.is_file():
        return None
    try:
        data = json.loads(cj.read_text(encoding="utf-8"))
        trade_date = str((data.get("market_overview") or {}).get("trade_date") or "")
        baseline_date = dt.datetime.strptime(trade_date, "%Y%m%d").strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError) as exc:
        logger.warning("Current T-1 baseline unavailable: %s", exc)
        return None
    # claude.json = compact_for_claude 输出: holdings+watchlist 统一在 stocks 列表(带 group)
    for s in data.get("stocks", []) or []:
        if s.get("code") == code:
            return {
                "score": s.get("right_side_score"),
                "grade": s.get("right_side_grade"),
                "position_20d_pct": s.get("position_20d_pct"),
                "main_inflow_10d": s.get("main_inflow_10d_yuan"),
                "np_yoy": s.get("np_yoy"),
                "baseline_date": baseline_date,
            }
    return None
