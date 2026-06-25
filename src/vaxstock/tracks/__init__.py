# -*- coding: utf-8 -*-
"""赛道(tracks)层 —— 赛道择时体系的统一契约与各赛道实现。

地基(MR-Track #1): contract.py 定义 TrackResult 统一口子(纯 DTO + 校验)。
contract 是只 import typing 的叶子节点, 故 report 层与各赛道模块均可 import 它
而不破坏单向分层。
"""

from vaxstock.tracks.contract import (
    PENDING_CEILING,
    STATUS_CONFIRMED,
    STATUS_CONFLICT,
    STATUS_PARTIAL_PREFIX,
    STATUS_PENDING,
    STATUS_SINGLE_SOURCE,
    VALID_CEILING_PREFIXES,
    VALID_STATUSES,
    CEILING_DEFENSE,
    CEILING_FORBIDDEN,
    CEILING_LIQUIDATE,
    CEILING_NEUTRAL,
    CEILING_OFFENSE,
    CEILING_REDUCE,
    Signal,
    TrackResult,
    is_valid_ceiling,
    is_valid_status,
    pending_result,
    validate,
)

__all__ = [
    "TrackResult",
    "Signal",
    "pending_result",
    "validate",
    "is_valid_status",
    "is_valid_ceiling",
    "PENDING_CEILING",
    "STATUS_CONFIRMED",
    "STATUS_PENDING",
    "STATUS_SINGLE_SOURCE",
    "STATUS_CONFLICT",
    "STATUS_PARTIAL_PREFIX",
    "VALID_STATUSES",
    "VALID_CEILING_PREFIXES",
    "CEILING_OFFENSE",
    "CEILING_NEUTRAL",
    "CEILING_REDUCE",
    "CEILING_DEFENSE",
    "CEILING_LIQUIDATE",
    "CEILING_FORBIDDEN",
]
