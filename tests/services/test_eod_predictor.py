# -*- coding: utf-8 -*-
"""services.eod_predictor 测试(EOD Prediction E4-1/E4-2, 零网络,jsonl 落 tmp)。"""

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


def test_prediction_from_snapshot_skips_missing_required_fields_and_validates_mode():
    assert ep.prediction_from_snapshot({"trade_date": "20260701"}, "20260702") is None
    try:
        ep.prediction_from_snapshot(_snapshot(), "20260702", generation_mode="bad")
    except ValueError as e:
        assert "generation_mode" in str(e)
    else:
        raise AssertionError("bad generation_mode should raise")



def test_replay_predictions_from_snapshots_targets_next_observed_trade_date():
    s1 = _snapshot(score=2.3)
    s1["trade_date"] = "20260701"
    s1["code"] = "002475"
    s2 = _snapshot(score=0.2)
    s2["trade_date"] = "20260701"
    s2["code"] = "601318"
    s3 = _snapshot(score=3.6)
    s3["trade_date"] = "20260703"  # 0702 可为周末/节假日/缺样本, 不用自然日臆造
    s3["code"] = "600519"

    preds = ep.replay_predictions_from_snapshots(
        [s1, s2, s3, {"code": "bad"}],
        generated_at="2026-07-04T05:10:00",
    )

    assert len(preds) == 2  # 最后一个 trade_date 没有已证实下一交易日 -> 跳过
    by = {p["code"]: p for p in preds}
    assert by["002475"]["baseline_trade_date"] == "20260701"
    assert by["002475"]["target_trade_date"] == "20260703"
    assert by["002475"]["generation_mode"] == "replay"
    assert by["002475"]["prediction_id"] == "20260701_20260703_002475_zz800_seed_v1_replay"
    assert by["601318"]["target_trade_date"] == "20260703"
    assert "600519" not in by


def test_bootstrap_replay_predictions_idempotent_writes_tmp():
    d = tempfile.mkdtemp(prefix="vaxpred_boot_")
    try:
        snapshots_path = pathlib.Path(d) / "factor_snapshots.jsonl"
        output_path = pathlib.Path(d) / "prediction" / "eod_predictions.jsonl"
        rows = []
        s1 = _snapshot(score=2.3)
        s1["trade_date"] = "20260701"
        s1["code"] = "002475"
        s2 = _snapshot(score=0.2)
        s2["trade_date"] = "20260701"
        s2["code"] = "601318"
        s3 = _snapshot(score=3.6)
        s3["trade_date"] = "20260703"
        s3["code"] = "600519"
        rows.extend([s1, s2, s3])
        snapshots_path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )

        stats = ep.bootstrap_replay_predictions(
            snapshots_path=snapshots_path,
            output_path=output_path,
            generated_at="2026-07-04T05:10:00",
        )
        assert stats == {
            "written": 2,
            "skipped": 0,
            "source_snapshots": 3,
            "source_trade_dates": 2,
            "generated": 2,
            "last_trade_date_skipped": "20260703",
        }
        written_rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        assert len(written_rows) == 2
        assert {r["generation_mode"] for r in written_rows} == {"replay"}

        # 重跑同一批 -> prediction_id 已存在,只 skipped,文件不追加
        stats2 = ep.bootstrap_replay_predictions(
            snapshots_path=snapshots_path,
            output_path=output_path,
            generated_at="2026-07-04T05:10:00",
        )
        assert stats2["written"] == 0
        assert stats2["skipped"] == 2
        assert len([line for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]) == 2
    finally:
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
