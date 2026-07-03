# -*- coding: utf-8 -*-
"""services.prediction_evaluator 测试(EOD Prediction E4-3, 零网络,jsonl 落 tmp)。"""

import json
import pathlib
import shutil
import tempfile

from vaxstock.services import prediction_evaluator as pe


def _prediction(code="002475", action="watch", direction="up", bucket="positive"):
    return {
        "prediction_id": f"20260701_20260702_{code}_zz800_seed_v1_replay",
        "generation_mode": "replay",
        "baseline_trade_date": "20260701",
        "target_trade_date": "20260702",
        "code": code,
        "prediction": {
            "action": action,
            "direction": direction,
            "confidence": 0.6,
            "horizon": "T+1",
            "expected_excess_bucket": bucket,
        },
    }


def _factor_result(code="002475", ret=0.03, mkt_ret=0.01, excess=0.02):
    return {
        "trade_date": "20260701",
        "code": code,
        "ret": {"1": ret},
        "mkt_ret": {"1": mkt_ret},
        "excess": {"1": excess},
    }


def _read_rows(path):
    return [json.loads(line) for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def test_evaluate_prediction_positive_bucket_hit():
    idx = pe.build_factor_result_index([_factor_result(ret=0.03, mkt_ret=0.01, excess=0.02)])
    row = pe.evaluate_prediction(_prediction(), idx, evaluated_at="2026-07-03T05:10:00")
    assert row["prediction_id"] == "20260701_20260702_002475_zz800_seed_v1_replay"
    assert row["horizon"] == "1"
    assert row["actual"] == {
        "ret": 0.03,
        "mkt_ret": 0.01,
        "excess": 0.02,
        "source": "factor_results",
    }
    assert row["evaluation"]["direction_hit"] is True
    assert row["evaluation"]["positive_excess"] is True
    assert row["evaluation"]["action_hit"] is True
    assert row["evaluation"]["deviation"] == "as_expected"


def test_evaluate_prediction_non_positive_bucket_missed_positive_excess():
    idx = pe.build_factor_result_index([_factor_result(ret=0.01, mkt_ret=-0.01, excess=0.02)])
    pred = _prediction(action="avoid", direction="neutral", bucket="non_positive")
    row = pe.evaluate_prediction(pred, idx)
    assert row["evaluation"]["direction_hit"] is None
    assert row["evaluation"]["positive_excess"] is True
    assert row["evaluation"]["action_hit"] is False
    assert row["evaluation"]["deviation"] == "missed_positive_excess"


def test_evaluate_prediction_skips_missing_or_incomplete_result():
    pred = _prediction()
    assert pe.evaluate_prediction(pred, pe.build_factor_result_index([])) is None
    # 有 ret 但缺 excess, 不写假 action 核验
    idx = pe.build_factor_result_index([{"trade_date": "20260701", "code": "002475", "ret": {"1": 0.01}}])
    assert pe.evaluate_prediction(pred, idx) is None


def test_evaluate_predictions_merges_incremental_factor_results():
    rows = [
        {"trade_date": "20260701", "code": "002475", "ret": {"1": 0.01}},
        {"trade_date": "20260701", "code": "002475", "mkt_ret": {"1": -0.01}, "excess": {"1": 0.02}},
    ]
    out = pe.evaluate_predictions([_prediction()], rows)
    assert len(out) == 1
    assert out[0]["actual"]["ret"] == 0.01
    assert out[0]["actual"]["excess"] == 0.02


def test_evaluate_from_files_idempotent_writes_tmp():
    d = tempfile.mkdtemp(prefix="vaxpred_eval_")
    try:
        pred_path = pathlib.Path(d) / "eod_predictions.jsonl"
        fact_path = pathlib.Path(d) / "factor_results.jsonl"
        out_path = pathlib.Path(d) / "eod_prediction_results.jsonl"
        preds = [
            _prediction(code="002475", bucket="positive", direction="up"),
            _prediction(code="600900", action="avoid", direction="neutral", bucket="non_positive"),
            _prediction(code="000001", bucket="positive", direction="up"),  # 无结果 -> 不写
        ]
        facts = [
            _factor_result(code="002475", ret=0.03, mkt_ret=0.01, excess=0.02),
            _factor_result(code="600900", ret=-0.01, mkt_ret=0.01, excess=-0.02),
        ]
        pred_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in preds) + "\n",
                             encoding="utf-8")
        fact_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in facts) + "\n",
                             encoding="utf-8")

        stats = pe.evaluate_from_files(
            predictions_path=pred_path,
            factor_results_path=fact_path,
            output_path=out_path,
            evaluated_at="2026-07-03T05:10:00",
        )
        assert stats == {
            "written": 2,
            "skipped": 0,
            "source_predictions": 3,
            "source_factor_results": 2,
            "generated": 2,
            "missing_or_pending": 1,
        }
        assert len(_read_rows(out_path)) == 2

        stats2 = pe.evaluate_from_files(
            predictions_path=pred_path,
            factor_results_path=fact_path,
            output_path=out_path,
            evaluated_at="2026-07-03T05:10:00",
        )
        assert stats2["written"] == 0
        assert stats2["skipped"] == 2
        assert len(_read_rows(out_path)) == 2
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
