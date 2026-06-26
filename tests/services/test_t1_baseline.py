# -*- coding: utf-8 -*-
"""services._t1_baseline 测试(C线: 取最新交易日 EOD claude.json 的 T-1 基准, 零网络, tmp)。"""

import json
import pathlib
import shutil
import tempfile

from vaxstock import config
from vaxstock.services import _t1_baseline as t1


def _write_claude(dir_path, stocks):
    dir_path.mkdir(parents=True, exist_ok=True)
    with open(dir_path / "claude.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": "x", "stocks": stocks}, f, ensure_ascii=False)


def test_load_t1_baseline_latest_dir_and_fields():
    base = pathlib.Path(tempfile.mkdtemp(prefix="vaxt1_"))
    saved = config.REPORTS_DIR
    try:
        config.REPORTS_DIR = base
        # 旧日(不该被选)
        _write_claude(base / "2026-06-24", [{"code": "002475", "right_side_score": 1.0}])
        # 最新交易日(应被选)
        _write_claude(base / "2026-06-25", [
            {"code": "002475", "group": "watchlist", "right_side_score": 2.5,
             "right_side_grade": "可考虑介入", "position_20d_pct": 80,
             "main_inflow_10d_yuan": 1.0e8, "np_yoy": 30.0},
        ])
        (base / "misc").mkdir()   # 非日期目录, 应跳过

        out = t1.load_t1_baseline("002475")
        assert out is not None
        assert out["baseline_date"] == "2026-06-25"          # 取最新交易日, 非 24 日
        assert out["score"] == 2.5 and out["grade"] == "可考虑介入"
        assert out["position_20d_pct"] == 80
        assert out["main_inflow_10d"] == 1.0e8 and out["np_yoy"] == 30.0
    finally:
        config.REPORTS_DIR = saved
        shutil.rmtree(base, ignore_errors=True)


def test_load_t1_baseline_unknown_code_returns_none():
    base = pathlib.Path(tempfile.mkdtemp(prefix="vaxt1_"))
    saved = config.REPORTS_DIR
    try:
        config.REPORTS_DIR = base
        _write_claude(base / "2026-06-25", [{"code": "002475", "right_side_score": 2.5}])
        assert t1.load_t1_baseline("000001") is None    # 乱编 code -> None(不臆造)
    finally:
        config.REPORTS_DIR = saved
        shutil.rmtree(base, ignore_errors=True)


def test_load_t1_baseline_no_dir_or_no_json_returns_none():
    base = pathlib.Path(tempfile.mkdtemp(prefix="vaxt1_"))
    saved = config.REPORTS_DIR
    try:
        config.REPORTS_DIR = base
        assert t1.load_t1_baseline("002475") is None       # 无任何日期目录 -> None
        (base / "2026-06-25").mkdir()                       # 有目录但无 claude.json
        assert t1.load_t1_baseline("002475") is None
    finally:
        config.REPORTS_DIR = saved
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    import sys
    fns = sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f))
    failed = 0
    for name, fn in fns:
        try:
            fn(); print(f"  [PASS] {name}")
        except AssertionError as e:
            failed += 1; print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            failed += 1; print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
