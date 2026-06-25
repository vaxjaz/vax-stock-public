# -*- coding: utf-8 -*-
"""盘中六铁律输出层硬校验器(纯函数, 零依赖; C2a 建, C2d 复用)。

不靠 codex 自觉: 对 codex 盘中研判文本做输出层硬校验, 命中越界则在文末追加红色标注(不删原文,
保留可追溯), 无命中则确保文末含"盘中未定论"。扫描三类越界:
  ① 评分数字(right_side_score / 0-3.5 分制表述)
  ② 买卖价格指令(买入价/卖出价/止损价/目标价 + 数字)
  ③ 资金方向断言(主力/资金 流入/流出/净买卖 —— lite 快照无资金数据, 不得臆测)
"""

import re

_PENDING_MARK = "盘中未定论"
_VIOLATION_NOTE = "⚠️[铁律校验] 检测到疑似越界(评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论"

# ① 评分: "评分: 2.8" / "2.8分"(0-3) / right_side_score 字样
_SCORE_RES = [
    re.compile(r"评分\s*[:：]?\s*[0-3]\.\d"),
    re.compile(r"[0-3]\.\d\s*分"),
    re.compile(r"right_side_score", re.IGNORECASE),
]
# ② 买卖价格指令: 买入价/卖出价/止损价/目标价 紧跟数字
_PRICE_RES = [
    re.compile(r"(买入价|卖出价|止损价|目标价|建议买入价|建议卖出价)\s*[:：]?\s*[¥$]?\d"),
    re.compile(r"(止损|止盈)\s*(在|价|位)?\s*[:：]?\s*[¥$]?\d"),
]
# ③ 资金方向断言: 主力/资金/北向/游资 ... 流入/流出/净买/净卖
_FUND_RES = [
    re.compile(r"(主力|资金|北向|游资|大单).{0,6}(流入|流出|净买|净卖|净流入|净流出)"),
    re.compile(r"(净流入|净流出)"),
]


def _hit(text: str, patterns) -> bool:
    return any(p.search(text) for p in patterns)


def enforce_intraday_rules(text: str) -> str:
    """盘中铁律硬校验。命中任一越界 -> 文末追加越界标注(原文保留); 无命中 -> 确保文末含'盘中未定论'。"""
    if not isinstance(text, str):
        return text

    violated = (_hit(text, _SCORE_RES) or _hit(text, _PRICE_RES) or _hit(text, _FUND_RES))
    if violated:
        # 不删原文, 末尾追加越界标注(该标注本身含"盘中未定论")
        return f"{text.rstrip()}\n{_VIOLATION_NOTE}"

    if _PENDING_MARK not in text:
        return f"{text.rstrip()}\n({_PENDING_MARK})"
    return text
