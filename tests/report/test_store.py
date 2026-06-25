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
from pathlib import Path

from vaxstock import config
from vaxstock.report.store import cleanup, store_report


# ── 落盘根目录解析: 显式入参 > SECRETS["report_dir"] > 缺省 config.REPORTS_DIR(绝对 var/reports) ──
def test_default_dir_uses_config_reports_dir():
    """缺省(不传 report_dir 且 SECRETS 无 report_dir)-> 落到绝对 config.REPORTS_DIR, 非相对 ./reports。"""
    tmp = tempfile.mkdtemp(prefix="vaxstore_rd_")
    saved_dir, saved_sec = config.REPORTS_DIR, config.SECRETS
    try:
        config.REPORTS_DIR = Path(tmp)
        config.SECRETS = {}  # 无 report_dir
        paths = store_report({"generated_at": "x"}, {}, "md")  # 不传 report_dir
        assert paths["payload"].startswith(str(Path(tmp).resolve())), paths["payload"]
        assert os.path.isabs(paths["payload"])
    finally:
        config.REPORTS_DIR, config.SECRETS = saved_dir, saved_sec
        shutil.rmtree(tmp, ignore_errors=True)


def test_explicit_arg_overrides():
    """显式 report_dir 优先于 SECRETS 与缺省。"""
    tmp_arg = tempfile.mkdtemp(prefix="vaxstore_arg_")
    tmp_cfg = tempfile.mkdtemp(prefix="vaxstore_cfg_")
    saved_dir, saved_sec = config.REPORTS_DIR, config.SECRETS
    try:
        config.REPORTS_DIR = Path(tmp_cfg)
        config.SECRETS = {"report_dir": tmp_cfg}
        paths = store_report({"generated_at": "x"}, {}, "md", report_dir=tmp_arg)
        assert paths["payload"].startswith(str(Path(tmp_arg).resolve()))
        assert not paths["payload"].startswith(str(Path(tmp_cfg).resolve()))
    finally:
        config.REPORTS_DIR, config.SECRETS = saved_dir, saved_sec
        shutil.rmtree(tmp_arg, ignore_errors=True)
        shutil.rmtree(tmp_cfg, ignore_errors=True)


def test_secrets_report_dir_over_default_under_arg():
    """SECRETS["report_dir"] 优先于缺省 config.REPORTS_DIR、低于显式入参。"""
    tmp_sec = tempfile.mkdtemp(prefix="vaxstore_sec_")
    tmp_def = tempfile.mkdtemp(prefix="vaxstore_def_")
    saved_dir, saved_sec = config.REPORTS_DIR, config.SECRETS
    try:
        config.REPORTS_DIR = Path(tmp_def)
        config.SECRETS = {"report_dir": tmp_sec}
        # 不传入参 -> 用 SECRETS 的 report_dir(覆盖缺省)
        paths = store_report({"generated_at": "x"}, {}, "md")
        assert paths["payload"].startswith(str(Path(tmp_sec).resolve()))
        assert not paths["payload"].startswith(str(Path(tmp_def).resolve()))
    finally:
        config.REPORTS_DIR, config.SECRETS = saved_dir, saved_sec
        shutil.rmtree(tmp_sec, ignore_errors=True)
        shutil.rmtree(tmp_def, ignore_errors=True)


def test_default_dir_idempotent_same_day():
    """缺省路径下同日两次落盘 -> 目录文件数不增(覆盖, 幂等)。"""
    tmp = tempfile.mkdtemp(prefix="vaxstore_idem_")
    saved_dir, saved_sec = config.REPORTS_DIR, config.SECRETS
    try:
        config.REPORTS_DIR = Path(tmp)
        config.SECRETS = {}
        store_report({"generated_at": "x", "v": 1}, {}, "md1")
        day_dir = os.path.dirname(store_report({"generated_at": "x", "v": 2}, {}, "md2")["payload"])
        files = sorted(os.listdir(day_dir))
        assert files == ["claude.json", "claude.md", "payload.json"], files  # 仅三件套, 不增
    finally:
        config.REPORTS_DIR, config.SECRETS = saved_dir, saved_sec
        shutil.rmtree(tmp, ignore_errors=True)


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
