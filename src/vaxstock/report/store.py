# -*- coding: utf-8 -*-
"""report 层: 报告落盘(SSOT)+ 过期清理。

"step1 数据落盘 → step2 交叉验证"方案的地基: 把每日报告三件套落到 reports/{YYYY-MM-DD}/,
供 GPT5/Claude 重新读取做交叉验证, 也可回溯/重渲染。

职责单一: store 只做持久化, 不在内部调 compact/build(渲染由调用方先做好传进来)。
依赖只允许 util / config(不取数、不 import sources/analysis)。
"""

import datetime as dt
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from vaxstock import config

logger = logging.getLogger(__name__)


def _resolve_report_dir(report_dir: Optional[str]) -> Path:
    if report_dir is None:
        report_dir = config.SECRETS.get("report_dir", "./reports")
    return Path(report_dir)


def _parse_date_dir(name: str) -> Optional[dt.date]:
    """把 'YYYY-MM-DD' 目录名解析成 date; 非日期目录返回 None(清理时跳过)。"""
    try:
        return dt.datetime.strptime(name, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def store_report(payload: Dict[str, Any],
                 claude_data: Dict[str, Any],
                 markdown: str,
                 report_dir: Optional[str] = None) -> Dict[str, str]:
    """落盘三件套到 reports/{YYYY-MM-DD}/:
      - payload.json : 完整原始 payload(SSOT, 可回溯/重渲染)
      - claude.json  : compact 版 claude_data
      - claude.md    : markdown 字符串

    按日期分目录, 当日重跑覆盖(幂等)。report_dir 缺省取 config.SECRETS["report_dir"] (默认 ./reports)。
    返回三件套的绝对路径 dict: {"payload", "claude_json", "claude_md"}。
    """
    base = _resolve_report_dir(report_dir)
    date = str(dt.date.today())  # YYYY-MM-DD
    day_dir = base / date
    day_dir.mkdir(parents=True, exist_ok=True)

    payload_path = (day_dir / "payload.json").resolve()
    claude_json_path = (day_dir / "claude.json").resolve()
    claude_md_path = (day_dir / "claude.md").resolve()

    # default=str: 兜底 numpy/Decimal/datetime 等非原生可序列化类型, 防止 SSOT 落盘崩溃
    with open(payload_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    with open(claude_json_path, "w", encoding="utf-8") as f:
        json.dump(claude_data, f, ensure_ascii=False, indent=2, default=str)
    with open(claude_md_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    logger.info(f"📁 报告已落盘: {day_dir} (payload.json / claude.json / claude.md)")
    return {
        "payload": str(payload_path),
        "claude_json": str(claude_json_path),
        "claude_md": str(claude_md_path),
    }


def cleanup(days_to_keep: int = 7,
            report_dir: Optional[str] = None,
            dry_run: bool = False) -> Dict[str, Any]:
    """删除 reports/ 下日期早于 days_to_keep 天的整个 YYYY-MM-DD 目录。

    保留最近 days_to_keep 天(含今天)。非日期目录一律跳过(不误删)。
    返回 {"dirs_removed", "dirs_kept", "removed": [目录名...]}。dry_run=True 只统计不删。
    """
    base = _resolve_report_dir(report_dir)
    stats: Dict[str, Any] = {"dirs_removed": 0, "dirs_kept": 0, "removed": []}
    if not base.is_dir():
        return stats

    cutoff = dt.date.today() - dt.timedelta(days=days_to_keep)
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        d = _parse_date_dir(child.name)
        if d is None:
            continue  # 非日期目录, 跳过
        if d < cutoff:
            if not dry_run:
                shutil.rmtree(child, ignore_errors=True)
            stats["dirs_removed"] += 1
            stats["removed"].append(child.name)
        else:
            stats["dirs_kept"] += 1

    action = "将删除(试运行)" if dry_run else "已清理"
    logger.info(f"🧹 {action}: 删除目录 {stats['dirs_removed']} 个 / 保留 {stats['dirs_kept']} 个")
    return stats
