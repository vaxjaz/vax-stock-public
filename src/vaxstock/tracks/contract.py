# -*- coding: utf-8 -*-
"""赛道契约(TrackResult)—— 赛道体系的统一口子。

MR-Track 地基: 纯 DTO + 校验, 无运行逻辑、无 IO、无包内依赖。
本模块是【叶子节点】: 只 import typing, 不依赖 vaxstock 任何其他模块,
因此 report 层与各赛道模块都能 import 它而不破坏单向分层
(config -> sources -> indicators -> analysis -> report -> services; tracks 在最底层叶子)。

P0 铁律落地:
  - 每个信号必须带非空、合法的 status(已证实/待验证/单源待交叉验证/双源冲突待验证/部分缺失(N)),
    保证结论可追溯, 不允许"无状态"信号混入。
  - 数据不足时走 pending_result: available=False、仓位强制 PENDING_CEILING、pending 非空,
    绝不臆造仓位结论。
  - validate() 强制 available 与 position_ceiling/pending 的交叉一致性。
"""

from typing import Dict, List, Optional, Tuple, TypedDict


# ==================== 类型契约 ====================

class Signal(TypedDict, total=False):
    """单条赛道信号。

    运行期是普通 dict, 赛道可附带任意描述字段(value/source/note/raw 等),
    但【必须】带一个非空且合法的 status 字段(P0 可追溯核心约束, 由 validate 强制)。
    """
    status: str


class TrackResult(TypedDict):
    """赛道分析的统一返回契约(8 字段)。"""
    track_name: str                      # 非空, 渲染标题
    date: str                            # YYYY-MM-DD
    available: bool                      # signals 是否足以支撑仓位结论
    signals: Dict[str, "Signal"]         # 每个信号 dict 必须带非空 status(P0)
    summary_lines: List[str]             # 赛道自产显示行, 供通用 render 直接打印
    vetoes: List[Tuple[str, str]]        # (否决名, 原因)
    position_ceiling: str                # 仓位档位(有效档位前缀 或 PENDING_CEILING)
    pending: List[str]                   # 待验证维度


# ==================== status 词表 ====================

STATUS_CONFIRMED = "已证实"
STATUS_PENDING = "待验证"
STATUS_SINGLE_SOURCE = "单源待交叉验证"
STATUS_CONFLICT = "双源冲突待验证"
# 动态前缀: 实际形如 "部分缺失(3)"; 校验用前缀判定
STATUS_PARTIAL_PREFIX = "部分缺失"

# 固定合法 status 集合(动态前缀单独判定)
VALID_STATUSES = (
    STATUS_CONFIRMED,
    STATUS_PENDING,
    STATUS_SINGLE_SOURCE,
    STATUS_CONFLICT,
)


# ==================== 仓位档位词表 ====================

CEILING_OFFENSE = "进攻档"
CEILING_NEUTRAL = "中性档"
CEILING_REDUCE = "减档"
CEILING_DEFENSE = "防御档"
CEILING_LIQUIDATE = "清仓档"
CEILING_FORBIDDEN = "禁区"

# 有效档位前缀(档位字符串后面可带括号说明, 故用前缀判定)
VALID_CEILING_PREFIXES = (
    CEILING_OFFENSE,
    CEILING_NEUTRAL,
    CEILING_REDUCE,
    CEILING_DEFENSE,
    CEILING_LIQUIDATE,
    CEILING_FORBIDDEN,
)

# 哨兵: 数据缺失时的仓位占位, 与任何有效档位前缀互斥
PENDING_CEILING = "待验证(数据缺失, 不出仓位结论)"

# TrackResult 必备字段
_REQUIRED_FIELDS = (
    "track_name", "date", "available", "signals",
    "summary_lines", "vetoes", "position_ceiling", "pending",
)


# ==================== 词表判定(前缀) ====================

def is_valid_status(status: str) -> bool:
    """status 是否合法: 固定词表之一, 或动态前缀 '部分缺失(...)'。"""
    if not isinstance(status, str) or not status.strip():
        return False
    if status in VALID_STATUSES:
        return True
    return status.startswith(STATUS_PARTIAL_PREFIX)


def is_valid_ceiling(ceiling: str) -> bool:
    """是否为有效仓位档位(前缀判定, 不含 PENDING_CEILING)。"""
    if not isinstance(ceiling, str):
        return False
    return any(ceiling.startswith(p) for p in VALID_CEILING_PREFIXES)


def _is_valid_date(s: object) -> bool:
    """YYYY-MM-DD 校验(纯字符串判定, 不 import datetime/re, 保持叶子节点)。"""
    if not isinstance(s, str) or len(s) != 10:
        return False
    if s[4] != "-" or s[7] != "-":
        return False
    y, m, d = s[0:4], s[5:7], s[8:10]
    if not (y.isdigit() and m.isdigit() and d.isdigit()):
        return False
    mm, dd = int(m), int(d)
    return 1 <= mm <= 12 and 1 <= dd <= 31


# ==================== 工厂 ====================

def pending_result(
        track_name: str,
        date: str,
        reason: str,
        pending_dims: Optional[List[str]] = None,
        signals: Optional[Dict[str, "Signal"]] = None,
) -> "TrackResult":
    """产出 available=False 的合规 TrackResult。

    强制: position_ceiling=PENDING_CEILING、pending 非空, 绝不臆造仓位结论。
    pending_dims 缺省时回退到 [reason](再不行回退到 [STATUS_PENDING]), 保证 pending 非空。
    """
    dims: List[str] = [d for d in (pending_dims or []) if isinstance(d, str) and d.strip()]
    if not dims:
        if isinstance(reason, str) and reason.strip():
            dims = [reason]
        else:
            dims = [STATUS_PENDING]

    summary: List[str] = []
    if isinstance(reason, str) and reason.strip():
        summary = [f"[{track_name}] {STATUS_PENDING}: {reason}"]

    return {
        "track_name": track_name,
        "date": date,
        "available": False,
        "signals": dict(signals) if isinstance(signals, dict) else {},
        "summary_lines": summary,
        "vetoes": [],
        "position_ceiling": PENDING_CEILING,
        "pending": dims,
    }


# ==================== 校验 ====================

def validate(result: "TrackResult") -> List[str]:
    """校验 TrackResult, 返回错误列表(不抛异常; 由 services 层决定记日志/升级)。

    强制:
      - 8 字段齐全、类型正确
      - 每个信号带非空且合法的 status(P0 可追溯核心约束)
      - P0 交叉约束:
          available=False -> position_ceiling 必须 == PENDING_CEILING 且 pending 非空
          available=True  -> position_ceiling 必须是有效档位前缀, 不能是 PENDING_CEILING
    """
    errors: List[str] = []
    if not isinstance(result, dict):
        return ["result 必须是 dict / TrackResult"]

    def _present(key: str) -> bool:
        if key not in result:
            errors.append(f"缺字段: {key}")
            return False
        return True

    # ---- 字段齐全 + 类型 ----
    if _present("track_name"):
        v = result["track_name"]
        if not isinstance(v, str) or not v.strip():
            errors.append("track_name 必须是非空 str")

    if _present("date"):
        if not _is_valid_date(result["date"]):
            errors.append("date 必须是 YYYY-MM-DD 字符串")

    if _present("available"):
        if not isinstance(result["available"], bool):
            errors.append("available 必须是 bool")

    if _present("signals"):
        sig = result["signals"]
        if not isinstance(sig, dict):
            errors.append("signals 必须是 Dict[str, Signal]")
        else:
            for k, s in sig.items():
                if not isinstance(s, dict):
                    errors.append(f"signal[{k}] 必须是 dict")
                    continue
                status = s.get("status")
                if not isinstance(status, str) or not status.strip():
                    errors.append(f"signal[{k}] 缺非空 status (P0 可追溯)")
                elif not is_valid_status(status):
                    errors.append(f"signal[{k}] status 非法: {status!r}")

    if _present("summary_lines"):
        sl = result["summary_lines"]
        if not isinstance(sl, list) or not all(isinstance(x, str) for x in sl):
            errors.append("summary_lines 必须是 List[str]")

    if _present("vetoes"):
        vs = result["vetoes"]
        # 同时接受 tuple 和 list: JSON 落盘往返(json.dumps→json.loads)会把元组转成列表,
        # store.py 报告落盘后重载做 GPT5/Claude 交叉验证必经此路径, 故 list 也合法。
        if not isinstance(vs, list) or not all(
            isinstance(t, (tuple, list)) and len(t) == 2 and all(isinstance(x, str) for x in t)
            for t in vs
        ):
            errors.append("vetoes 必须是 List[Tuple[str, str]] (元素 tuple/list 均可, 长度2、两元素皆 str)")

    if _present("position_ceiling"):
        pc = result["position_ceiling"]
        if not isinstance(pc, str) or not pc.strip():
            errors.append("position_ceiling 必须是非空 str")

    if _present("pending"):
        p = result["pending"]
        if not isinstance(p, list) or not all(isinstance(x, str) for x in p):
            errors.append("pending 必须是 List[str]")

    # ---- P0 交叉约束(仅在 available/position_ceiling 类型正确时判定)----
    avail = result.get("available")
    pc = result.get("position_ceiling")
    pending = result.get("pending")
    if isinstance(avail, bool) and isinstance(pc, str):
        if avail is False:
            if pc != PENDING_CEILING:
                errors.append(
                    f"P0: available=False 时 position_ceiling 必须为 PENDING_CEILING, 实际 {pc!r}"
                )
            if not (isinstance(pending, list) and len(pending) > 0):
                errors.append("P0: available=False 时 pending 必须非空")
        else:
            if pc == PENDING_CEILING:
                errors.append("P0: available=True 时 position_ceiling 不能是 PENDING_CEILING")
            elif not is_valid_ceiling(pc):
                errors.append(f"P0: available=True 时 position_ceiling 必须是有效档位前缀, 实际 {pc!r}")

    return errors
