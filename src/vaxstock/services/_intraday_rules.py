# -*- coding: utf-8 -*-
"""盘中铁律输出层硬校验器(纯函数, 零依赖; C2a 建, C线 forecast 升级)。

不靠 codex 自觉: 对 codex 研判的 `reasoning` 字段做输出层硬校验, 命中越界则文末追加标注
(不删原文, 保留可追溯), 无命中则确保文末含"盘中未定论"。

【C线升级 · 昨日限定词白名单】引入 T-1 基准后, codex 引用"昨日/T-1/EOD/基准"的评分与资金是
合法的(那是定稿值)。故评分/资金断言: 前文带白名单限定词 -> 放行; 无限定词的盘中**新生成**评分/
资金断言 -> 仍拦截。买卖价格指令一律拦(不分限定词)。
"""

import re

_PENDING_MARK = "盘中未定论"
_VIOLATION_NOTE = "⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论"

# 昨日限定词白名单: 命中点前文窗口内含其一 -> 该评分/资金引用合法(定稿值)
_QUALIFIERS = ("昨日", "T-1", "T1", "EOD", "基准", "昨收", "T-1定稿")
_QUALIFIER_WINDOW = 14  # 命中点前看多少字符判定是否带限定词

# ① 评分: "评分: 2.8" / "2.8分"(0-3) / right_side_score 字样
_SCORE_RES = [
    re.compile(r"评分\s*[:：]?\s*[0-3]\.\d"),
    re.compile(r"[0-3]\.\d\s*分"),
    re.compile(r"right_side_score", re.IGNORECASE),
]
# ② 买卖价格指令: 买入价/卖出价/止损价/目标价 紧跟数字(一律拦, 不分限定词)
_PRICE_RES = [
    re.compile(r"(买入价|卖出价|止损价|目标价|建议买入价|建议卖出价)\s*[:：]?\s*[¥$]?\d"),
    re.compile(r"(止损|止盈)\s*(在|价|位)?\s*[:：]?\s*[¥$]?\d"),
]
# ③ 资金方向断言: 主力/资金/北向/游资 ... 流入/流出/净买卖
_FUND_RES = [
    re.compile(r"(主力|资金|北向|游资|大单).{0,6}(流入|流出|净买|净卖|净流入|净流出)"),
    re.compile(r"(净流入|净流出)"),
]


def _hit(text: str, patterns) -> bool:
    return any(p.search(text) for p in patterns)


def _has_qualifier_before(text: str, idx: int) -> bool:
    """命中点 idx 前 _QUALIFIER_WINDOW 字符内是否含昨日限定词(合法引用定稿值)。"""
    pre = text[max(0, idx - _QUALIFIER_WINDOW):idx]
    return any(q in pre for q in _QUALIFIERS)


def _has_unqualified(text: str, patterns) -> bool:
    """patterns 任一命中, 且命中点前文无昨日限定词 -> 视为盘中新生成(违规)。"""
    for p in patterns:
        for m in p.finditer(text):
            if not _has_qualifier_before(text, m.start()):
                return True
    return False


def enforce_intraday_rules(text: str) -> str:
    """盘中铁律硬校验(作用于 reasoning 字段)。

    越界 = 买卖价指令(一律) ∪ 无限定词的盘中新评分 ∪ 无限定词的资金断言。
    命中 -> 文末追加越界标注(原文保留); 无命中 -> 确保文末含"盘中未定论"。
    """
    if not isinstance(text, str):
        return text

    violated = (_hit(text, _PRICE_RES)                    # 买卖价一律拦
                or _has_unqualified(text, _SCORE_RES)     # 无限定词的新评分
                or _has_unqualified(text, _FUND_RES))     # 无限定词的资金断言
    if violated:
        return f"{text.rstrip()}\n{_VIOLATION_NOTE}"

    if _PENDING_MARK not in text:
        return f"{text.rstrip()}\n({_PENDING_MARK})"
    return text
