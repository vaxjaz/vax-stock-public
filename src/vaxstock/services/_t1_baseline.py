# -*- coding: utf-8 -*-
"""T-1 EOD 基准读取(C线 forecast 用)。

盘中物理上算不出评分/资金(lite 快照无), 但"昨日定稿"的 EOD 结论可引用。本模块从最新交易日
EOD 报告(claude.json)取该票的 T-1 定稿基准, 喂给 codex 做"今日行为 vs 昨日 thesis"的假设检验,
并冻结进 forecast 的 inputs_ref。

锚交易日铁律(§9.1): 目录名 YYYY-MM-DD 解析取最新, 不用 now() 推日期(自动跳过周末/节假日)。
P0: 找不到目录/code/解析失败 -> None(不抛、不臆造)。只读 claude.json(已含所需字段), 不回退 payload.json。
"""

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Optional

from vaxstock import config

logger = logging.getLogger(__name__)


def _latest_report_dir() -> Optional[Path]:
    """config.REPORTS_DIR 下取目录名为合法 YYYY-MM-DD 的最新目录(字典序=时间序)。无则 None。"""
    base = Path(config.REPORTS_DIR)
    if not base.is_dir():
        return None
    dated = []
    for child in base.iterdir():
        if not child.is_dir():
            continue
        try:
            dt.datetime.strptime(child.name, "%Y-%m-%d")
        except (ValueError, TypeError):
            continue  # 非日期目录跳过
        dated.append(child)
    return max(dated, key=lambda p: p.name) if dated else None


def load_t1_baseline(code) -> Optional[dict]:
    """取最新交易日 EOD claude.json 中该 code 的 T-1 定稿基准。

    返回 {score, grade, position_20d_pct, main_inflow_10d, np_yoy, baseline_date};
    找不到目录/code/解析失败 -> None(P0: 不抛、不臆造)。
    """
    d = _latest_report_dir()
    if d is None:
        return None
    cj = d / "claude.json"
    if not cj.exists():
        return None
    try:
        with open(cj, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"T-1 基准 claude.json 解析失败({d.name}): {str(e)[:80]}")
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
                "baseline_date": d.name,
            }
    return None
