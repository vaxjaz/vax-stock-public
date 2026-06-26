# -*- coding: utf-8 -*-
"""services.forecast_recorder 测试(C线 预测冻结写入, 零网络, jsonl 落 tmp)。"""

import json
import pathlib
import shutil
import tempfile

from vaxstock.services import forecast_recorder as fr


def _set_tmp(d):
    saved = fr.FORECASTS_FILE
    fr.FORECASTS_FILE = pathlib.Path(d) / "forecasts.jsonl"
    return saved


def _rows():
    return [json.loads(line) for line in fr.FORECASTS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_record_forecast_appends_frozen_row():
    d = tempfile.mkdtemp(prefix="vaxfc_")
    saved = _set_tmp(d)
    try:
        inputs_ref = {"baseline_date": "2026-06-25",
                      "t1_baseline": {"score": 2.5, "grade": "可考虑介入"},
                      "lite_snapshot": {"code": "002475", "price": 70.0},
                      "regime": "momentum"}
        structured = {"verdict": "确认", "direction": "看多", "confidence": 0.7,
                      "horizon": "3日", "thesis_tags": ["放量突破"], "news_refs": []}
        ok = fr.record_forecast("002475", "2026-06-26", "站上69", inputs_ref,
                                structured, "今日放量站稳", "跌破MA20")
        assert ok is True
        rows = _rows()
        assert len(rows) == 1
        r = rows[0]
        assert r["code"] == "002475" and r["trade_date"] == "2026-06-26"
        assert r["structured"]["verdict"] == "确认"
        assert r["falsify_if"] == "跌破MA20"
        # inputs_ref 冻结了当时输入(回测归因命门)
        assert r["inputs_ref"]["t1_baseline"]["score"] == 2.5
        assert r["inputs_ref"]["lite_snapshot"]["code"] == "002475"
        assert r["inputs_ref"]["regime"] == "momentum"
        assert "forecast_ts" in r and r["schema_version"] == 1

        # append-only: 再写一条 -> 2 行(只增不改)
        fr.record_forecast("600519", "2026-06-26", "破位", inputs_ref, structured, "x", "y")
        assert len(_rows()) == 2
    finally:
        fr.FORECASTS_FILE = saved
        shutil.rmtree(d, ignore_errors=True)


def test_record_forecast_skips_without_trade_date():
    d = tempfile.mkdtemp(prefix="vaxfc_")
    saved = _set_tmp(d)
    try:
        ok = fr.record_forecast("002475", None, "n", {}, {"verdict": "确认"}, "r", "f")
        assert ok is False                       # 缺 trade_date -> 跳过不写(不臆造日期)
        assert not fr.FORECASTS_FILE.exists()     # 未落任何行
    finally:
        fr.FORECASTS_FILE = saved
        shutil.rmtree(d, ignore_errors=True)


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
