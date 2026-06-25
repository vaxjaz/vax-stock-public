# -*- coding: utf-8 -*-
"""市场环境分类器(regime)。

从单体脚本 script/stock_report_enhanced.py 原样搬运。
唯一改动: 状态文件路径由 os.path.dirname(__file__)/regime_history.json
          改为 config.REGIME_STATE_FILE (var/regime_history.json), 逻辑不变。
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from vaxstock import config

logger = logging.getLogger(__name__)


def detect_market_regime(indices: List[Dict[str, Any]], market_overview: Dict[str, Any]) -> str:
    """
    市场环境自动分类器 v1.2（含平滑逻辑）

    v1.2变化: 单日判断噪音大(创业板单日跑赢2%就切momentum),
    改为状态平滑——momentum/value互切需连续2日同向原始信号;
    panic安全优先,单日立即生效;panic解除也需连续2日非panic。

    - "momentum": 动量市,创业板/科创跑赢主板>=2%。反转因子失效。
    - "value":    价值市,主板跑赢。反转因子启用。
    - "panic":    恐慌市,跌停>50。优质低位股豁免,其余观望。
    """
    # ---- 第一步: 计算今日原始信号(与v1.1逻辑相同) ----
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

    # ---- 第二步: 状态平滑 ----
    state_file = config.REGIME_STATE_FILE
    history = []
    current = "momentum"
    try:
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            history = state.get("raw_history", [])[-4:]  # 保留最近4条
            current = state.get("current_regime", "momentum")
    except Exception:
        pass

    today = datetime.now().strftime("%Y-%m-%d")
    # 防止同日重复运行污染历史: 同日只保留最后一次
    history = [h for h in history if h.get("date") != today]
    history.append({"date": today, "raw": raw})

    # 切换规则
    if raw == "panic":
        new_regime = "panic"  # 恐慌单日立即生效(安全优先)
    elif current == "panic":
        # 恐慌解除: 需连续2日非panic
        recent = [h["raw"] for h in history[-2:]]
        if len(recent) >= 2 and all(r != "panic" for r in recent):
            new_regime = raw
        else:
            new_regime = "panic"
    elif raw != current:
        # momentum<->value互切: 需连续2日同向
        recent = [h["raw"] for h in history[-2:]]
        if len(recent) >= 2 and all(r == raw for r in recent):
            new_regime = raw
        else:
            new_regime = current  # 维持原状态,防单日噪音
    else:
        new_regime = current

    # 保存状态
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({
                "current_regime": new_regime,
                "raw_history": history,
                "last_updated": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"regime状态保存失败: {e}")

    if new_regime != raw:
        logger.info(f"  📊 regime平滑: 今日原始信号={raw}, 维持={new_regime}(待连续确认)")

    return new_regime
