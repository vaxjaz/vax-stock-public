# -*- coding: utf-8 -*-
"""C线 forecast 数据层: 盘中触发结构化预测的冻结写入(append-only)。

C线 = EOD(B线全截面) ∪ Layer2(解读) 之上的"预测线": 盘中触发那一刻, 把 codex 的结构化研判
(verdict/direction/confidence/horizon/falsify_if)连同**当时输入**(T-1 基准+lite 快照+regime)一起
冻结入库, 供日后 T+k 回测归因。

铁律(CLAUDE.md §7):
  - 预测先于结果冻结、append-only(只增不改); inputs_ref 必须存当时输入(回测归因命门)。
  - trade_date 锚触发当日交易日(由调用方从触发数据取, 非 now()); 缺则跳过不写(不臆造日期)。
  - 本 PR 只做"预测冻结写入"; 结果回填(forecast_results.jsonl + T+k)留后续 PR。
  - C线(A 盯盘触发样本)与 B线(eval 全截面)分开存/分开写入时点(§9.7)。
"""

import datetime as dt
import json
import logging
from pathlib import Path

from vaxstock import config

logger = logging.getLogger(__name__)

FORECAST_DIR = config.STATE_DIR / "forecast"
FORECASTS_FILE = FORECAST_DIR / "forecasts.jsonl"
SCHEMA_VERSION = 1


def _now_iso() -> str:
    """生成时刻戳(ISO); 仅作记录时刻, 非交易日基准(§9.1)。"""
    return dt.datetime.now().isoformat(timespec="seconds")


def _append_jsonl(path, row) -> None:
    """原子 append 一行 JSON(同 eval_recorder 写法; 只增不改)。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def record_forecast(code, trade_date, trigger_note, inputs_ref, structured,
                    reasoning, falsify_if) -> bool:
    """冻结写入一条盘中触发预测(append-only)。返回是否写入。

    inputs_ref: {baseline_date, t1_baseline, lite_snapshot, regime} —— 冻结当时输入(回测归因命门)。
    structured: {verdict, direction, confidence, horizon, thesis_tags, news_refs}。
    trade_date 缺失 -> warning + 跳过不写(不臆造日期, §9.1)。
    """
    if not trade_date:
        logger.warning(f"forecast 缺 trade_date(code={code}), 跳过不写(不臆造日期)")
        return False
    row = {
        "schema_version": SCHEMA_VERSION,
        "forecast_ts": _now_iso(),
        "trade_date": str(trade_date),
        "code": code,
        "trigger_note": trigger_note,
        "inputs_ref": inputs_ref,
        "structured": structured,
        "reasoning": reasoning,
        "falsify_if": falsify_if,
    }
    _append_jsonl(FORECASTS_FILE, row)
    logger.info(f"forecast 冻结: {trade_date} {code} "
                f"verdict={(structured or {}).get('verdict')} "
                f"dir={(structured or {}).get('direction')} "
                f"conf={(structured or {}).get('confidence')}")
    return True
