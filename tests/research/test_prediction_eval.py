# -*- coding: utf-8 -*-
"""research.prediction_eval tests (MR-Eval E4-5, zero network).

Run:
  PYTHONPATH=src python tests/research/test_prediction_eval.py
"""

import json
import pathlib
import shutil
import tempfile

import vaxstock.research.prediction_eval as peval


def _append(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _pred(pid, *, mode="replay", action="buy", direction="up", confidence=0.75,
          concepts=None, target="20260626", regime="momentum", macro="bull"):
    return {
        "schema_version": 1,
        "prediction_id": pid,
        "generation_mode": mode,
        "baseline_trade_date": "20260625",
        "target_trade_date": target,
        "code": pid[-6:],
        "name": pid,
        "group": "watchlist",
        "concepts": concepts if concepts is not None else ["AI"],
        "features_ref": {
            "market_regime": regime,
            "macro_regime": macro,
            "right_side_score": 3.6,
        },
        "prediction": {
            "action": action,
            "direction": direction,
            "confidence": confidence,
            "horizon": "T+1",
            "expected_excess_bucket": "positive",
        },
        "rule_version": "test_rule",
        "model_version": "test_model",
    }


def _result(pid, *, ret=0.03, excess=0.02, action_hit=True, direction_hit=True):
    return {
        "schema_version": 1,
        "prediction_id": pid,
        "generation_mode": "replay",
        "baseline_trade_date": "20260625",
        "target_trade_date": "20260626",
        "code": pid[-6:],
        "horizon": "1",
        "actual": {"ret": ret, "mkt_ret": 0.01, "excess": excess, "source": "factor_results"},
        "evaluation": {
            "direction_hit": direction_hit,
            "positive_excess": excess > 0,
            "action_hit": action_hit,
            "deviation": "as_expected" if action_hit else "miss",
            "error_type": None,
        },
    }


def test_load_joined_marks_pending():
    d = pathlib.Path(tempfile.mkdtemp(prefix="vaxpredl2_"))
    try:
        preds = d / "eod_predictions.jsonl"
        results = d / "eod_prediction_results.jsonl"
        _append(preds, _pred("P000001"))
        _append(preds, _pred("P000002", mode="live", target="20260703"))
        _append(results, _result("P000001"))

        joined = peval.load_joined(predictions_path=preds, results_path=results)
        assert len(joined) == 2
        by_id = {row["prediction"]["prediction_id"]: row for row in joined}
        assert by_id["P000001"]["result"]["actual"]["excess"] == 0.02
        assert by_id["P000002"]["result"] is None
        assert by_id["P000002"]["horizon"] == "1"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_analyze_buckets_and_pending_without_sample_gate():
    joined = [
        {"prediction": _pred("P000001", action="buy", direction="up", confidence=0.75,
                             concepts=["AI", "robot"]), "result": _result("P000001"),
         "horizon": "1"},
        {"prediction": _pred("P000002", action="avoid", direction="down", confidence=0.55,
                             concepts=["AI"]), "result": _result("P000002", ret=0.01, excess=-0.01,
                                                                  action_hit=True, direction_hit=False),
         "horizon": "1"},
        {"prediction": _pred("P000003", mode="live", action="watch", direction="neutral",
                             confidence=0.40, concepts=[], target="20260703"),
         "result": None, "horizon": "1"},
    ]

    stats = peval.analyze(joined)
    replay = stats["modes"]["replay"]
    assert replay["predictions"] == 2
    assert replay["evaluated"] == 2
    assert replay["pending"] == 0
    assert abs(replay["avg_excess"] - 0.005) < 1e-12
    assert replay["positive_excess_rate"] == 0.5
    assert replay["action_hit_rate"] == 1.0
    assert replay["direction_hit_rate"] == 0.5

    live = stats["modes"]["live"]
    assert live["predictions"] == 1
    assert live["evaluated"] == 0
    assert live["pending"] == 1
    assert live["avg_excess"] is None

    assert stats["buckets"]["replay"]["confidence_bucket"]["high(>=0.70)"]["evaluated"] == 1
    assert stats["buckets"]["replay"]["confidence_bucket"]["medium(>=0.50)"]["evaluated"] == 1
    assert stats["buckets"]["live"]["confidence_bucket"]["low(<0.50)"]["pending"] == 1
    assert stats["buckets"]["replay"]["concept"]["AI"]["predictions"] == 2
    assert stats["buckets"]["replay"]["concept"]["robot"]["predictions"] == 1
    assert stats["buckets"]["live"]["concept"]["concept待验证"]["pending"] == 1

    report = peval.render_report(stats)
    assert "样本不足" not in report
    assert "pending" in report
    assert "## 术语说明" in report
    assert "`confidence`: 规则先验置信度" in report
    assert "概念 concept 分桶采用一票多桶" in report



def test_summarize_prediction_check_filters_target_trade_date():
    joined = [
        {"prediction": _pred("P000001", target="20260626", action="watch"),
         "result": _result("P000001", excess=0.03, action_hit=True, direction_hit=True),
         "horizon": "1"},
        {"prediction": _pred("P000002", target="20260626", action="avoid"),
         "result": _result("P000002", ret=-0.01, excess=-0.02,
                           action_hit=True, direction_hit=False),
         "horizon": "1"},
        {"prediction": _pred("P000003", target="20260626", mode="live", action="watch"),
         "result": None, "horizon": "1"},
        {"prediction": _pred("P000004", target="20260627", action="watch"),
         "result": _result("P000004", excess=0.20), "horizon": "1"},
    ]

    summary = peval.summarize_prediction_check(target_trade_date="20260626", joined=joined)
    assert summary["available"] is True
    assert summary["target_trade_date"] == "20260626"
    assert summary["predictions"] == 3
    assert summary["evaluated"] == 2
    assert summary["pending"] == 1
    assert abs(summary["avg_excess"] - 0.005) < 1e-12
    assert summary["positive_excess_rate"] == 0.5
    assert summary["action_hit_rate"] == 1.0
    assert summary["direction_hit_rate"] == 0.5
    by_action = {row["action"]: row for row in summary["actions"]}
    assert by_action["watch"]["predictions"] == 2
    assert by_action["watch"]["pending"] == 1
    assert by_action["avoid"]["evaluated"] == 1


def test_summarize_prediction_check_no_predictions():
    summary = peval.summarize_prediction_check(target_trade_date="20260699", joined=[])
    assert summary["available"] is False
    assert summary["target_trade_date"] == "20260699"
    assert "待积累" in summary["message"]

def test_run_prediction_layer2_writes_latest_target_report():
    d = pathlib.Path(tempfile.mkdtemp(prefix="vaxpredl2_"))
    try:
        preds = d / "eod_predictions.jsonl"
        results = d / "eod_prediction_results.jsonl"
        _append(preds, _pred("P000001", target="20260626"))
        _append(preds, _pred("P000002", mode="live", target="20260703", concepts=[]))
        _append(results, _result("P000001"))

        report = peval.run_prediction_layer2(
            write=True,
            predictions_path=preds,
            results_path=results,
            output_dir=d,
        )
        out = d / "prediction_layer2_report_20260703.md"
        assert out.is_file()
        text = out.read_text(encoding="utf-8")
        assert "# EOD Prediction Layer2 评估报告" in report
        assert "generation_mode: replay" in text
        assert "generation_mode: live" in text
        assert "| bucket | predictions | evaluated | pending |" in text
    finally:
        shutil.rmtree(d, ignore_errors=True)


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
