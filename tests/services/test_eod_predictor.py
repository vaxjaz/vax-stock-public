# -*- coding: utf-8 -*-
"""services.eod_predictor 测试(EOD Prediction E4-1, 零网络,jsonl 落 tmp)。"""

import json
import pathlib
import shutil
import tempfile

from vaxstock.services import eod_predictor as ep


def _set_tmp(d):
    saved = ep.PREDICTIONS_FILE
    ep.PREDICTIONS_FILE = pathlib.Path(d) / "prediction" / "eod_predictions.jsonl"
    return saved


def _restore(saved):
    ep.PREDICTIONS_FILE = saved


def _rows():
    if not ep.PREDICTIONS_FILE.exists():
        return []
    return [json.loads(line) for line in ep.PREDICTIONS_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _snapshot(score=2.3, regime="momentum", macro="🔴 看空"):
    return {
        "trade_date": "20260701",
        "code": "002475",
        "name": "立讯精密",
        "group": "watchlist",
        "concepts": ["消费电子", "AI"],
        "price_at_snapshot": 68.2,
        "metrics": {
            "right_side_score": score,
            "right_side_grade": None,
            "main_inflow_10d": 123000000,
            "np_yoy": 35.2,
            "holder_change_pct": -3.1,
            "position_20d_pct": 42.0,
        },
        "market": {
            "regime": regime,
            "macro_regime": macro,
            "ai_track": {"position_ceiling": "中性"},
        },
    }


def _payload():
    return {
        "market_overview": {"trade_date": "20260701"},
        "market_regime": "panic",
        "macro": {"macro_regime": "🔴 看空"},
        "tracks": [{"track_name": "AI算力", "position_ceiling": "防守档", "available": True}],
        "stocks": [
            {"group": "holding", "code": "002475", "configured_name": "立讯精密",
             "concepts": ["消费电子"], "realtime": {"name": "立讯精密", "price": 68.2},
             "metrics": {"right_side_score": 3.6, "main_inflow_10d": 1}},
            {"group": "watchlist", "code": "601318", "configured_name": "中国平安",
             "concepts": [], "realtime": {"name": "中国平安", "price": 50.0},
             "metrics": {"right_side_score": 0.2}},
        ],
    }


def test_prediction_from_snapshot_freezes_schema_and_features():
    pred = ep.prediction_from_snapshot(
        _snapshot(),
        "20260702",
        generation_mode="replay",
        generated_at="2026-07-02T05:10:00",
    )
    assert pred["schema_version"] == 1
    assert pred["prediction_id"] == "20260701_20260702_002475_zz800_seed_v1_replay"
    assert pred["generation_mode"] == "replay"
    assert pred["baseline_trade_date"] == "20260701"
    assert pred["target_trade_date"] == "20260702"
    assert pred["rule_version"] == "zz800_seed_v1"
    assert pred["model_version"] == "manual_rules_v1"
    assert pred["features_ref"]["price_at_baseline"] == 68.2
    assert pred["features_ref"]["right_side_score"] == 2.3
    assert pred["features_ref"]["right_side_grade"] == "可考虑介入"
    assert pred["features_ref"]["main_inflow_10d"] == 123000000
    assert pred["features_ref"]["np_yoy"] == 35.2
    assert pred["features_ref"]["holder_change_pct"] == -3.1
    assert pred["features_ref"]["market_regime"] == "momentum"
    assert pred["features_ref"]["macro_regime"] == "🔴 看空"
    assert pred["features_ref"]["ai_position_ceiling"] == "中性"
    assert pred["prediction"]["action"] == "watch"
    assert pred["prediction"]["direction"] == "up"
    assert pred["prediction"]["confidence"] == 0.55   # 宏观看空降置信
    assert "macro_bearish_reduce_confidence" in pred["prediction"]["reason_codes"]
    # 写入前 schema 校验必须通过; 后续 evaluator/layer2 依赖这些字段 join 与分桶
    ep.validate_prediction(pred)


def test_infer_prediction_action_buckets():
    assert ep.infer_prediction({"right_side_score": 3.6}, {"regime": "momentum"})["action"] == "candidate_buy"
    assert ep.infer_prediction({"right_side_score": 3.6}, {"regime": "panic"})["action"] == "watch_only"
    assert ep.infer_prediction({"right_side_score": 1.0}, {"regime": "panic"})["action"] == "panic_rebound_watch"
    assert ep.infer_prediction({"right_side_score": 0.2}, {"regime": "panic"})["action"] == "panic_rebound_probe"
    assert ep.infer_prediction({"right_side_score": 0.2}, {"regime": "momentum"})["action"] == "avoid"
    assert ep.infer_prediction({}, {"regime": "momentum"})["action"] == "no_prediction"


def test_record_predictions_idempotent_append_only():
    d = tempfile.mkdtemp(prefix="vaxpred_")
    saved = _set_tmp(d)
    try:
        pred = ep.prediction_from_snapshot(_snapshot(), "20260702", generation_mode="replay")
        stats = ep.record_predictions([pred])
        assert stats == {"written": 1, "skipped": 0}
        first_text = ep.PREDICTIONS_FILE.read_text(encoding="utf-8")
        assert len(_rows()) == 1

        # 同 prediction_id 重写 -> 跳过, 文件不变
        stats2 = ep.record_predictions([pred])
        assert stats2 == {"written": 0, "skipped": 1}
        assert ep.PREDICTIONS_FILE.read_text(encoding="utf-8") == first_text

        # 同 baseline/target/code/rule 但 live 样本性质不同 -> 可并存
        live = ep.prediction_from_snapshot(_snapshot(), "20260702", generation_mode="live")
        stats3 = ep.record_predictions([live])
        assert stats3 == {"written": 1, "skipped": 0}
        assert len(_rows()) == 2
    finally:
        _restore(saved)
        shutil.rmtree(d, ignore_errors=True)


def test_record_predictions_rejects_bad_schema_without_writing():
    d = tempfile.mkdtemp(prefix="vaxpred_")
    saved = _set_tmp(d)
    try:
        pred = ep.prediction_from_snapshot(_snapshot(), "20260702", generation_mode="replay")
        bad = dict(pred)
        bad["prediction_id"] = "wrong_id"
        try:
            ep.record_predictions([bad])
        except ValueError as e:
            assert "prediction_id 不匹配" in str(e)
        else:
            raise AssertionError("bad prediction_id should raise")
        assert not ep.PREDICTIONS_FILE.exists()  # append-only 文件不允许落入坏数据

        bad2 = json.loads(json.dumps(pred, ensure_ascii=False))
        bad2["prediction"]["confidence"] = 1.5
        try:
            ep.record_predictions([bad2])
        except ValueError as e:
            assert "confidence" in str(e)
        else:
            raise AssertionError("bad confidence should raise")
        assert not ep.PREDICTIONS_FILE.exists()

        bad3 = json.loads(json.dumps(pred, ensure_ascii=False))
        del bad3["features_ref"]["market_regime"]
        try:
            ep.record_predictions([bad3])
        except ValueError as e:
            assert "features_ref 缺字段" in str(e)
        else:
            raise AssertionError("missing feature should raise")
        assert not ep.PREDICTIONS_FILE.exists()
    finally:
        _restore(saved)
        shutil.rmtree(d, ignore_errors=True)


def test_predictions_from_payload_uses_payload_market_context():
    preds = ep.predictions_from_payload(
        _payload(),
        "20260702",
        generation_mode="live",
        generated_at="2026-07-02T05:10:00",
    )
    assert len(preds) == 2
    by = {p["code"]: p for p in preds}
    assert by["002475"]["baseline_trade_date"] == "20260701"
    assert by["002475"]["target_trade_date"] == "20260702"
    assert by["002475"]["features_ref"]["market_regime"] == "panic"
    assert by["002475"]["features_ref"]["macro_regime"] == "🔴 看空"
    assert by["002475"]["features_ref"]["ai_position_ceiling"] == "防守档"
    assert by["002475"]["prediction"]["action"] == "watch_only"  # 高分但 panic 降级
    assert by["601318"]["prediction"]["action"] == "panic_rebound_probe"


def test_generate_predictions_from_snapshots_skips_incomplete_rows_and_validates_all():
    rows = [
        _snapshot(score=3.6, regime="momentum"),
        {"trade_date": "20260701", "name": "缺code"},
        _snapshot(score=None, regime="momentum"),
    ]
    preds = ep.generate_predictions_from_snapshots(
        rows,
        "20260702",
        generation_mode="replay",
        generated_at="2026-07-02T05:10:00",
    )
    assert len(preds) == 2
    assert preds[0]["prediction"]["action"] == "candidate_buy"
    assert preds[1]["prediction"]["action"] == "no_prediction"
    for p in preds:
        ep.validate_prediction(p)


def test_read_jsonl_skips_bad_lines():
    d = tempfile.mkdtemp(prefix="vaxpred_")
    try:
        p = pathlib.Path(d) / "bad.jsonl"
        p.write_text('{"ok": 1}\nnot-json\n{"ok": 2}\n', encoding="utf-8")
        rows = ep._read_jsonl(p)
        assert rows == [{"ok": 1}, {"ok": 2}]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_prediction_from_snapshot_skips_missing_required_fields_and_validates_mode():
    assert ep.prediction_from_snapshot({"trade_date": "20260701"}, "20260702") is None
    try:
        ep.prediction_from_snapshot(_snapshot(), "20260702", generation_mode="bad")
    except ValueError as e:
        assert "generation_mode" in str(e)
    else:
        raise AssertionError("bad generation_mode should raise")


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
