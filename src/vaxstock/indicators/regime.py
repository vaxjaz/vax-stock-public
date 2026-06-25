# -*- coding: utf-8 -*-
"""市场环境分类器(regime)。

v2(纯重放幂等 + trade_date key):
  - 第一步 raw 计算: 自单体脚本字节级保留(limit_down>50→panic / 指数涨跌→momentum/value)。
  - 第二步平滑: 重构为纯函数 _transition + _replay。消除"回读 current_regime 当转移输入"的
    自引用——raw_history 是唯一 SSOT, 从冷启动种子 momentum 按时序 fold 整段, 故幂等。
  - 持久化 key 由 datetime.now() 改为 market_overview["trade_date"](真实交易日):
    非交易日跑时 trade_date 仍是上一交易日, 按它去重 → 不产生幽灵记录。
    trade_date 缺失/为空: P0 不臆造、不回退 now() —— 只读返回重放结果、不写盘(降级不污染)。

【已接受边界(P0 诚实, 不藏)】
  冷启动种子=momentum, 在 30 交易日窗口内会被"任一次连续2日同向确认"覆盖洗掉。唯一理论分歧:
  某 regime 经"严格逐日交替、30 日内从无连续2日确认"持续时, 重放可能偏向 momentum。
  A股实际不会逐日严格交替, 且下次连续2日确认即自愈, 影响仅限 reversal 因子启用档, 记为已知边界。

  - "momentum": 动量市, 创业板/科创跑赢主板>=2%。反转因子失效。
  - "value":    价值市, 主板跑赢。反转因子启用。
  - "panic":    恐慌市, 跌停>50。优质低位股豁免, 其余观望。
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from vaxstock import config

logger = logging.getLogger(__name__)

_SEED_REGIME = "momentum"      # 冷启动种子
_HISTORY_WINDOW = 30           # raw_history 保留窗口(交易日)


def _transition(prev_regime: str, raw_last2: List[str]) -> str:
    """单步状态转移(纯函数, 零 IO; 精确保留 v1.2 平滑语义)。

    raw_last2 = 截至当日的最近 1~2 个原始信号([昨, 今] 或仅 [今])。
    """
    raw_today = raw_last2[-1]
    if raw_today == "panic":
        return "panic"  # 恐慌单日立即生效(安全优先)
    if prev_regime == "panic":
        # 恐慌解除: 需连续2日非panic
        return raw_today if len(raw_last2) >= 2 and all(r != "panic" for r in raw_last2) else "panic"
    if raw_today != prev_regime:
        # momentum<->value 互切: 需连续2日同向
        return raw_today if len(raw_last2) >= 2 and all(r == raw_today for r in raw_last2) else prev_regime
    return prev_regime


def _replay(raw_history: List[Dict[str, Any]]) -> str:
    """从冷启动种子 momentum 起, 按时序 fold 整段 raw_history。纯函数, 幂等。"""
    regime = _SEED_REGIME
    raws = [h["raw"] for h in raw_history]
    for i in range(len(raws)):
        regime = _transition(regime, raws[max(0, i - 1): i + 1])
    return regime


def _normalize_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """整理 raw_history: 丢弃无有效 trade_date / 无 raw 的记录, 按 trade_date 去重(后者覆盖),
    按 trade_date 升序排列(Tushare 'YYYYMMDD' 字典序即时序)。

    丢弃无 trade_date 的记录 = 自然迁移旧 'date'-key 格式(不污染重放)。
    """
    by_date: Dict[str, Dict[str, Any]] = {}
    for h in history or []:
        if not isinstance(h, dict) or "raw" not in h:
            continue
        td = str(h.get("trade_date") or "").strip()
        if not td:
            continue
        by_date[td] = {"trade_date": td, "raw": h["raw"]}
    return [by_date[k] for k in sorted(by_date)]


def detect_market_regime(indices: List[Dict[str, Any]], market_overview: Dict[str, Any]) -> str:
    # ---- 第一步: 计算今日原始信号(字节级保留, 逻辑不许改) ----
    limit_down = (market_overview or {}).get("limit_down_count", 0)
    if limit_down and limit_down > 50:
        raw = "panic"
    else:
        chg_map = {}
        for idx in indices or []:
            name = idx.get("name", "")
            chg = idx.get("change_pct")
            if chg is not None:
                chg_map[name] = chg
        sh = chg_map.get("上证指数", 0)
        cyb = chg_map.get("创业板指", 0)
        kc50 = chg_map.get("科创50", 0)
        growth_avg = (cyb + kc50) / 2 if (cyb or kc50) else 0
        if growth_avg - sh >= 2.0:
            raw = "momentum"
        elif sh - growth_avg >= 1.0:
            raw = "value"
        else:
            raw = "momentum"  # 默认动量市(A股近年偏成长)

    # ---- 第二步: 纯重放平滑 ----
    state_file = config.REGIME_STATE_FILE

    # 读历史 raw_history(SSOT); 绝不回读 current_regime 当转移输入
    history: List[Dict[str, Any]] = []
    try:
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            history = state.get("raw_history", []) or []
    except Exception:
        history = []

    trade_date = (market_overview or {}).get("trade_date")
    trade_date = str(trade_date).strip() if trade_date not in (None, "") else ""

    if not trade_date:
        # P0: 无真实交易日 -> 不臆造、不回退 now()、不写盘; 只读返回历史重放结果(降级不污染)
        replayed = _replay(_normalize_history(history)[-_HISTORY_WINDOW:])
        logger.warning("  ⚠️ market_overview 无 trade_date, regime 降级为只读重放(不写盘): %s", replayed)
        return replayed

    # 按 trade_date 去重(同日只留最后一条 raw)、时序排列、保留窗口
    merged = _normalize_history(history + [{"trade_date": trade_date, "raw": raw}])[-_HISTORY_WINDOW:]
    new_regime = _replay(merged)

    # 保存状态: current_regime 仅作人读/调试字段, 绝不回读当转移输入; raw_history 是唯一 SSOT
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({
                "current_regime": new_regime,   # 仅人读/调试, 不参与计算
                "raw_history": merged,
                "last_updated": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"regime状态保存失败: {e}")

    if new_regime != raw:
        logger.info(f"  📊 regime平滑: 今日原始信号={raw}, 维持={new_regime}(待连续确认)")

    return new_regime
