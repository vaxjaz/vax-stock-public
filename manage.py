#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""观察池管理 CLI 兜底(SSH 直接用; GET-API 之外的本地通道)。

用法(仓库根):
  python manage.py list
  python manage.py add 600519 白酒,消费
  python manage.py remove 600519
  python manage.py concepts 600519 白酒,消费,食品饮料
  python manage.py focus AI算力,光模块

写操作交互 y/N 确认。复用 services.pool_admin(与 GET-API 同一写路径 + 审计)。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from vaxstock import config                              # noqa: E402
from vaxstock.services import pool_admin                 # noqa: E402


def _split(s):
    return [c.strip() for c in (s or "").replace("，", ",").split(",") if c.strip()]


def _confirm(prompt):
    try:
        return input(f"{prompt} [y/N] ").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False


def _source():
    try:
        from vaxstock.sources.tushare_src import TushareSource
        return TushareSource(config.SECRETS.get("tushare_token"))
    except Exception:
        return None


def _print_pool():
    pool = pool_admin.list_pool()
    print(f"\n观察池 {pool['count']} 只 | focus: {pool['focus']}")
    for code, info in pool["watchlist"].items():
        print(f"  {code} {info['name']:<8} {info['concepts']}")
    if pool["holdings"]:
        print(f"持仓: {list(pool['holdings'])}")


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]

    if cmd == "list":
        _print_pool()
        return 0

    if cmd == "add":
        if len(argv) < 2:
            print("用法: add <code> [概念,逗号分隔]")
            return 1
        code = argv[1]
        cs = _split(argv[2]) if len(argv) > 2 else []
        preview = pool_admin.propose_add(code, cs, source=_source())
        print(f"将写入: {preview['code']} {preview['name']} concepts={preview['concepts']} "
              f"({preview['concepts_status']})")
        if not _confirm("确认写入?"):
            print("已取消")
            return 0
        try:
            pool_admin.commit_add(code, cs, source=_source())
            print("✅ 已写入"); _print_pool(); return 0
        except pool_admin.PoolError as e:
            print(f"❌ {e}"); return 1

    if cmd == "remove":
        if len(argv) < 2:
            print("用法: remove <code>"); return 1
        if not _confirm(f"确认从观察池删除 {argv[1]}?"):
            print("已取消"); return 0
        try:
            pool_admin.remove(argv[1]); print("✅ 已删除"); _print_pool(); return 0
        except pool_admin.PoolError as e:
            print(f"❌ {e}"); return 1

    if cmd == "concepts":
        if len(argv) < 3:
            print("用法: concepts <code> <概念,逗号分隔>"); return 1
        if not _confirm(f"确认改 {argv[1]} concepts 为 {_split(argv[2])}?"):
            print("已取消"); return 0
        try:
            pool_admin.update_concepts(argv[1], _split(argv[2]))
            print("✅ 已更新"); _print_pool(); return 0
        except pool_admin.PoolError as e:
            print(f"❌ {e}"); return 1

    if cmd == "focus":
        cs = _split(argv[1]) if len(argv) > 1 else []
        if not _confirm(f"确认设 focus(hot_sectors) 为 {cs}?"):
            print("已取消"); return 0
        pool_admin.set_focus(cs); print("✅ 已更新 focus"); _print_pool(); return 0

    print(f"未知命令: {cmd}\n{__doc__}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
