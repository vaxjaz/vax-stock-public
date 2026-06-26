# -*- coding: utf-8 -*-
"""观察池写模块(pool admin): watchlist.json 的唯一写路径 + 审计。

watchlist.json 此前只读(config.load_watchlist), 无写路径。本模块新建写路径: 原子写
(tmp + os.replace), 保留文件内全部既有键(holdings/data_sources/hot_sectors/_说明 等), 只改
watchlist 段或 hot_sectors。每次写成功 append var/pool_audit.jsonl(append-only, {ts,action,
code,before,after}), 留操作痕迹。

二段式 confirm: propose_*(回显不写) → 用户确认 → commit_*(真写 + 审计)。

【结构隔离铁律】本模块绝不被 intraday.py / sources.codex / forecast_recorder import
(盘中链路与池管理物理隔离); 仅 api.py(GET 端点)与 manage.py(CLI 兜底)调用。
name/concepts 取数走 sources(services→sources 合规), 取不到诚实标"待确认"/空, 不臆造。
"""

import datetime as dt
import json
import logging
import os
from pathlib import Path
from typing import List, Optional

from vaxstock import config
from vaxstock.sources.sina import get_sina_realtime

logger = logging.getLogger(__name__)

# 写路径锚 config.CONFIG_DIR(与 load_watchlist 同一文件, 单一真相); 测试 monkeypatch 到 tmp
WATCHLIST_FILE = config.CONFIG_DIR / "watchlist.json"
AUDIT_FILE = config.STATE_DIR / "pool_audit.jsonl"


class PoolError(ValueError):
    """池写非法输入(如 concepts 为空); 由调用方转成 {ok:False, error}。"""


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _read_watchlist() -> dict:
    """读 watchlist.json 全量(保留所有键); 不存在/损坏 -> 最小骨架(不臆造既有数据)。"""
    p = Path(WATCHLIST_FILE)
    if not p.exists():
        return {"holdings": {}, "watchlist": {}, "hot_sectors": []}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("watchlist.json 顶层非 dict")
        data.setdefault("watchlist", {})
        data.setdefault("holdings", {})
        return data
    except Exception as e:
        raise PoolError(f"watchlist.json 读取/解析失败, 拒绝写(防覆盖损坏文件): {str(e)[:80]}")


def _write_watchlist(data: dict) -> None:
    """原子写回全量 watchlist.json(tmp + os.replace, 防写一半被读)。"""
    p = Path(WATCHLIST_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def _audit(action: str, code: Optional[str], before, after) -> None:
    """append-only 审计: {ts, action, code, before, after}。审计失败不影响已完成的写。"""
    try:
        ap = Path(AUDIT_FILE)
        ap.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": _now_iso(), "action": action, "code": code, "before": before, "after": after}
        with open(ap, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        logger.warning(f"pool 审计写入失败(不影响主写): {str(e)[:80]}")


def _clean_concepts(concepts) -> List[str]:
    if not concepts:
        return []
    return [c.strip() for c in concepts if isinstance(c, str) and c.strip()]


def _fetch_name(code: str) -> str:
    try:
        rt = get_sina_realtime(code, "")
        return (rt or {}).get("name") or ""
    except Exception:
        return ""


def _fetch_concepts_fallback(source, code: str) -> List[str]:
    """Tushare 概念兜底(用户没给概念时); source 为空/取不到 -> []。"""
    if source is None:
        return []
    try:
        return list(source.get_stock_concepts(code) or [])
    except Exception:
        return []


def _current_focus(data: dict) -> List[str]:
    return list(data.get("hot_sectors") or [])


# ==================== 读 ====================

def list_pool() -> dict:
    """持仓 + 观察池 + 各票 concepts + 当前 focus(hot_sectors)。"""
    data = _read_watchlist()
    wl = {}
    for code, info in (data.get("watchlist") or {}).items():
        info = info or {}
        wl[code] = {"name": info.get("name", ""), "concepts": list(info.get("concepts") or [])}
    return {
        "holdings": data.get("holdings") or {},
        "watchlist": wl,
        "focus": _current_focus(data),
        "count": len(wl),
    }


# ==================== 二段式: propose(回显不写) ====================

def propose_add(code: str, concepts=None, source=None) -> dict:
    """回显将写入的内容(不落盘)。name 实时拉; concepts 用户给则用, 没给则 Tushare 兜底标'待确认'。"""
    name = _fetch_name(code)
    given = _clean_concepts(concepts)
    if given:
        out, status = given, "用户提供"
    else:
        fb = _fetch_concepts_fallback(source, code)
        out, status = fb, ("Tushare兜底(待确认, commit前请核)" if fb else "无(commit需手动提供概念)")
    data = _read_watchlist()
    focus = _current_focus(data)
    return {
        "ok": True, "action": "add", "code": code, "name": name,
        "concepts": out, "concepts_status": status,
        "in_focus": [c for c in out if c in focus],
        "already_in_pool": code in (data.get("watchlist") or {}),
        "note": "preview, 未写入; 确认后调 /pool/commit",
    }


# ==================== 二段式: commit(真写 + 审计) ====================

def commit_add(code: str, concepts=None, source=None) -> bool:
    """写入 watchlist.json。concepts 用户给则用, 没给则 Tushare 兜底; 仍为空 -> 拒绝(PoolError)。"""
    given = _clean_concepts(concepts)
    if not given:
        given = _fetch_concepts_fallback(source, code)
    if not given:
        raise PoolError(f"{code} concepts 为空且 Tushare 无兜底, 拒绝写入(请手动提供概念)")
    name = _fetch_name(code) or code
    data = _read_watchlist()
    wl = data.setdefault("watchlist", {})
    before = wl.get(code)
    wl[code] = {"name": name, "concepts": given}
    _write_watchlist(data)
    _audit("add", code, before, wl[code])
    logger.info(f"pool add: {code} {name} concepts={given}")
    return True


def remove(code: str) -> bool:
    """从观察池删除该票; 不存在 -> PoolError。"""
    data = _read_watchlist()
    wl = data.setdefault("watchlist", {})
    if code not in wl:
        raise PoolError(f"{code} 不在观察池, 无可删")
    before = wl.pop(code)
    _write_watchlist(data)
    _audit("remove", code, before, None)
    logger.info(f"pool remove: {code}")
    return True


def update_concepts(code: str, concepts=None) -> bool:
    """改某票 concepts(必须非空; 该票须已在池内)。"""
    given = _clean_concepts(concepts)
    if not given:
        raise PoolError(f"{code} concepts 为空, 拒绝(update 必须显式给非空概念)")
    data = _read_watchlist()
    wl = data.setdefault("watchlist", {})
    if code not in wl:
        raise PoolError(f"{code} 不在观察池, 请先 add")
    before = dict(wl[code]) if wl.get(code) else None
    info = wl.get(code) or {}
    info["concepts"] = given
    info.setdefault("name", _fetch_name(code) or code)
    wl[code] = info
    _write_watchlist(data)
    _audit("update_concepts", code, before, wl[code])
    logger.info(f"pool update_concepts: {code} -> {given}")
    return True


def set_focus(concepts=None) -> bool:
    """改 watchlist.json 的 hot_sectors(关心的热门赛道); 空列表合法(=清空 focus)。"""
    given = _clean_concepts(concepts)
    data = _read_watchlist()
    before = _current_focus(data)
    data["hot_sectors"] = given
    _write_watchlist(data)
    _audit("set_focus", None, before, given)
    logger.info(f"pool set_focus: {given}")
    return True
