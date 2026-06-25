# -*- coding: utf-8 -*-
"""板块/赛道分析(analysis 层)。

⚠️ 真实断点(MR3 减法的后果, 如实报告, 非臆造):
    原 build_sector_analysis 的"板块强弱榜"(涨幅/跌幅前 N + 主力净流入)100% 依赖东财
    get_em_sector_ranking —— 该函数已在 MR3 随 eastmoney.py 删除。Tushare 2000 积分
    无板块排行等价数据源(limit_list_d / moneyflow_mkt_dc 无权限, 且 MR3 已明确板块排行不迁移)。

    按 CLAUDE.md P0(缺数据源标"待验证", 绝不臆造/硬接/给默认值污染决策):
    本函数暂返回空榜单 + available=False + 待验证日志, 待找到可信板块数据源后再补。

    focus_sectors(原全局 HOT_SECTORS_FOCUS, 来自 watchlist 配置)只是"关注清单"配置,
    不是需要数据源的行情数据, 故改为入参显式传入并原样回显(消除全局态)。

    输出键 top_up_sectors / top_down_sectors / focus_sectors 与原结构兼容,
    下游 render_sector_section 渲染空榜单即可, 无需改动。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def build_sector_analysis(focus_sectors: Optional[List[str]] = None) -> Dict[str, Any]:
    """构建赛道分析。

    板块强弱榜数据源(东财)已于 MR3 移除且无 Tushare 替代, 按 P0 返回空榜单 + available=False,
    不臆造数据。focus_sectors 为关注清单配置, 原样回显。
    """
    logger.warning(
        "[赛道] 板块强弱榜暂不可用(待验证): 东财 get_em_sector_ranking 已于 MR3 移除, "
        "Tushare 2000积分无板块排行等价数据源; 按 P0 不臆造/硬接, 返回空榜单。"
    )
    return {
        "top_up_sectors": [],
        "top_down_sectors": [],
        "focus_sectors": list(focus_sectors or []),
        "available": False,
        "note": "板块强弱榜数据源缺失(东财已移除, 无 Tushare 替代), 待验证/待补数据源",
    }
