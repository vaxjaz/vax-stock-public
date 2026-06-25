# -*- coding: utf-8 -*-
"""report.store 测试(用临时目录, 零网络)。

跑法: PYTHONPATH=src python3 -m pytest tests/report/test_store.py
     PYTHONPATH=src python3 tests/report/test_store.py   # 无 pytest
"""

import datetime as dt
import json
import os
import shutil
import tempfile

from vaxstock.report.store import cleanup, store_report


def test_store_report_writes_three_files():
    base = tempfile.mkdtemp(prefix="vaxstore_")
    try:
        payload = {"generated_at": "2026-06-25 16:00", "stocks": [{"code": "002475"}], "x": 1}
        claude_data = {"generated_at": "2026-06-25 16:00", "stocks": []}
        markdown = "# 报告\n内容"
        paths = store_report(payload, claude_data, markdown, report_dir=base)

        # 返回三件套路径
        assert set(paths) == {"payload", "claude_json", "claude_md"}
        for p in paths.values():
            assert os.path.isfile(p), f"文件未生成: {p}"
            assert os.path.isabs(p), f"应为绝对路径: {p}"

        # 目录名是当天日期
        today = str(dt.date.today())
        assert os.path.basename(os.path.dirname(paths["payload"])) == today

        # json 可重新 load 回来(SSOT 可回溯)
        with open(paths["payload"], encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["stocks"][0]["code"] == "002475"
        with open(paths["claude_json"], encoding="utf-8") as f:
            assert json.load(f)["generated_at"] == "2026-06-25 16:00"
        with open(paths["claude_md"], encoding="utf-8") as f:
            assert f.read() == markdown

        # 当日重跑覆盖(幂等): 再写一次不报错, 内容更新
        paths2 = store_report({"generated_at": "x", "v": 2}, {}, "# 覆盖", report_dir=base)
        assert paths2["payload"] == paths["payload"]
        with open(paths2["payload"], encoding="utf-8") as f:
            assert json.load(f)["v"] == 2
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_store_default_serializes_nonstandard():
    """default=str 兜底: payload 含 date 等非原生可序列化对象不崩。"""
    base = tempfile.mkdtemp(prefix="vaxstore_")
    try:
        payload = {"generated_at": "x", "d": dt.date(2026, 6, 25)}  # date 非 json 原生
        paths = store_report(payload, {}, "md", report_dir=base)
        with open(paths["payload"], encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["d"] == "2026-06-25"  # 被 default=str 序列化
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_cleanup_removes_old_keeps_recent():
    base = tempfile.mkdtemp(prefix="vaxstore_")
    try:
        today = dt.date.today()
        old = today - dt.timedelta(days=30)
        recent = today - dt.timedelta(days=2)
        # 造三个日期目录 + 一个非日期目录
        for d in (today, recent, old):
            os.makedirs(os.path.join(base, str(d)))
            with open(os.path.join(base, str(d), "payload.json"), "w") as f:
                f.write("{}")
        os.makedirs(os.path.join(base, "misc"))  # 非日期目录, 不应被删

        stats = cleanup(days_to_keep=7, report_dir=base)

        assert str(old) in stats["removed"], stats
        assert stats["dirs_removed"] == 1
        assert not os.path.isdir(os.path.join(base, str(old))), "30天前目录应被删"
        assert os.path.isdir(os.path.join(base, str(today))), "当日目录应保留"
        assert os.path.isdir(os.path.join(base, str(recent))), "近2天目录应保留"
        assert os.path.isdir(os.path.join(base, "misc")), "非日期目录不应被删"
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_cleanup_dry_run():
    base = tempfile.mkdtemp(prefix="vaxstore_")
    try:
        old = dt.date.today() - dt.timedelta(days=30)
        os.makedirs(os.path.join(base, str(old)))
        stats = cleanup(days_to_keep=7, report_dir=base, dry_run=True)
        assert stats["dirs_removed"] == 1
        assert os.path.isdir(os.path.join(base, str(old))), "dry_run 不应真删"
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    import sys
    fns = sorted((n, f) for n, f in globals().items()
                 if n.startswith("test_") and callable(f))
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  [PASS] {name}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
