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


def test_record_dline_forecast_refreshes_markdown_summary():
    d = tempfile.mkdtemp(prefix="vaxfc_md_")
    saved = _set_tmp(d)
    try:
        inputs_ref = {
            "baseline_date": "20260703",
            "dline_task_id": "20260703_20260706_002475_d_observe_llm_v2",
            "dline_plan_version": fr.DLINE_PLAN_VERSION,
            "trigger_blueprint": {
                "trigger_type": "breakdown_confirm",
                "severity": "high",
                "why": "盘中价格继续低于MA20超过2%",
                "expected_feedback_to_c": "watch -> avoid_review",
            },
            "trigger_values": {
                "amount_yi": 2.0,
                "price_vs_ma5_pct": -2.04,
                "price_vs_ma20_pct": -4.0,
                "price_vs_ma60_pct": -12.73,
            },
            "quote_snapshot": {
                "code": "002475",
                "name": "立讯精密",
                "price": 96.0,
                "change_pct": -1.5,
                "amplitude_pct": 3.2,
                "trade_time": "10:00:00",
            },
            "evidence_pack": {
                "C_prediction": {"prediction": {"action": "watch", "direction": "up", "confidence": 0.6}}
            },
        }
        structured = {
            "verdict": "breakdown_confirm",
            "direction": "up",
            "confidence": 0.6,
            "horizon": "intraday",
            "source": "dline_task_blueprint",
        }
        ok = fr.record_forecast("002475", "20260706", "D-line breakdown_confirm", inputs_ref,
                                structured, "这是客观观察, 盘中未定论", "重新站回MA20")
        assert ok is True

        current = pathlib.Path(d) / "current_triggers.md"
        summary = pathlib.Path(d) / "trigger_summary_20260706.md"
        assert current.exists() and summary.exists()
        md = current.read_text(encoding="utf-8")
        assert "# D线盘中触发汇总" in md
        assert "现价=96.00" in md
        assert "涨跌幅=-1.50%" in md
        assert "MA20=-4.00%" in md
        assert "C线原始预测" in md
        assert "LLM客观评价" in md
        assert "expected_feedback_to_c=watch -> avoid_review" in md
        assert fr.refresh_trigger_markdown("20260706")["count"] == 1
    finally:
        fr.FORECASTS_FILE = saved
        shutil.rmtree(d, ignore_errors=True)


def test_load_dline_trigger_facts_normalizes_date_and_deduplicates_task():
    d = tempfile.mkdtemp(prefix="vaxfc_facts_")
    try:
        path = pathlib.Path(d) / "forecasts.jsonl"
        base = {
            "schema_version": 1,
            "code": "002475",
            "inputs_ref": {
                "dline_plan_version": fr.DLINE_PLAN_VERSION,
                "dline_task_id": "20260710_20260713_002475_d_observe_llm_v2",
                "trigger_blueprint": {
                    "trigger_type": "breakdown_confirm",
                    "severity": "high",
                    "expected_feedback_to_c": "watch -> avoid_review",
                },
                "quote_snapshot": {
                    "code": "002475", "trade_time": "09:35:38", "price": 60.9,
                },
            },
            "structured": {
                "source": "dline_task_blueprint", "trigger_type": "breakdown_confirm",
                "fire_count": 1,
            },
        }
        duplicate = json.loads(json.dumps(base))
        duplicate["trade_date"] = "20260713"
        duplicate["forecast_ts"] = "2026-07-13T09:40:00"
        duplicate["inputs_ref"]["quote_snapshot"]["trade_time"] = "09:40:00"
        duplicate["inputs_ref"]["quote_snapshot"]["price"] = 60.5
        first = json.loads(json.dumps(base))
        first["trade_date"] = "2026-07-13"
        first["forecast_ts"] = "2026-07-13T09:35:38"
        ignored = json.loads(json.dumps(base))
        ignored["trade_date"] = "2026-07-12"
        ignored["forecast_ts"] = "2026-07-12T09:35:38"
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in (duplicate, ignored, first)) + "\n", encoding="utf-8")

        facts = fr.load_dline_trigger_facts("20260713", forecasts_path=path)
        assert list(facts) == ["002475"]
        assert len(facts["002475"]) == 1
        fact = facts["002475"][0]
        assert fact["trade_date"] == "20260713"
        assert fact["trade_time"] == "09:35:38"
        assert fact["price"] == 60.9
        assert fact["occurrences"] == 2
    finally:
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
