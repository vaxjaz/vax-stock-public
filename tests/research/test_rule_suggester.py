# -*- coding: utf-8 -*-
"""research.rule_suggester tests (MR-Eval E4-7, zero network)."""

import json
import pathlib
import shutil
import tempfile

import vaxstock.research.rule_suggester as rs


def _pred(pid, *, action="watch", direction="up", target="20260626",
          regime="momentum", macro="neutral", concepts=None):
    return {
        "prediction_id": pid,
        "generation_mode": "replay",
        "baseline_trade_date": "20260625",
        "target_trade_date": target,
        "code": pid[-6:],
        "name": pid,
        "group": "watchlist",
        "concepts": concepts if concepts is not None else ["AI"],
        "features_ref": {
            "market_regime": regime,
            "macro_regime": macro,
            "right_side_score": 2.5,
        },
        "prediction": {
            "action": action,
            "direction": direction,
            "confidence": 0.60,
            "horizon": "T+1",
            "expected_excess_bucket": "positive",
        },
        "rule_version": "test_rule",
        "model_version": "test_model",
    }


def _result(pid, *, excess=0.02, ret=0.03, action_hit=True, direction_hit=True,
            target="20260626"):
    return {
        "prediction_id": pid,
        "generation_mode": "replay",
        "baseline_trade_date": "20260625",
        "target_trade_date": target,
        "code": pid[-6:],
        "horizon": "1",
        "actual": {"ret": ret, "mkt_ret": ret - excess, "excess": excess, "source": "factor_results"},
        "evaluation": {
            "direction_hit": direction_hit,
            "positive_excess": excess > 0,
            "action_hit": action_hit,
            "deviation": "as_expected" if action_hit else "miss",
            "error_type": None,
        },
    }


def _row(pid, **kwargs):
    result_kwargs = kwargs.pop("result", {})
    return {"prediction": _pred(pid, **kwargs), "result": _result(pid, **result_kwargs), "horizon": "1"}


def test_build_rule_suggestions_detects_good_and_bad_buckets():
    joined = [
        _row("P000001", action="panic_rebound_watch", regime="panic", macro="bear",
             concepts=["robot"], result={"excess": 0.03, "action_hit": True, "direction_hit": True}),
        _row("P000002", action="panic_rebound_watch", regime="panic", macro="bear",
             concepts=["robot"], result={"excess": 0.02, "action_hit": True, "direction_hit": True}),
        _row("P000003", action="panic_rebound_watch", regime="panic", macro="bear",
             concepts=["robot"], result={"excess": 0.01, "action_hit": True, "direction_hit": True}),
        _row("P000004", action="watch", regime="value", macro="neutral",
             concepts=["PCB"], result={"excess": -0.03, "action_hit": False, "direction_hit": False}),
        _row("P000005", action="watch", regime="value", macro="neutral",
             concepts=["PCB"], result={"excess": -0.02, "action_hit": False, "direction_hit": False}),
        _row("P000006", action="watch", regime="value", macro="neutral",
             concepts=["PCB"], result={"excess": -0.01, "action_hit": False, "direction_hit": False}),
        _row("P000007", action="candidate_buy", regime="momentum", macro="neutral",
             concepts=["AI"], result={"excess": 0.04, "action_hit": True, "direction_hit": True}),
    ]

    report = rs.build_rule_suggestions(joined=joined, min_evaluated=3)
    scopes = {s["scope"]: s for s in report["suggestions"]}
    assert report["report_date"] == "20260626"
    assert report["evaluated"] == 7
    assert "action:panic_rebound_watch" in scopes
    assert "market:panic|bear" in scopes
    assert "action:watch" in scopes
    assert "market:value|neutral" in scopes
    assert scopes["action:candidate_buy"]["evidence_strength"] == "thin"
    assert "不建议升级规则" in scopes["action:candidate_buy"]["suggestion"]

    text = rs.render_rule_suggestions(report)
    assert "只给规则升级建议" in text
    assert "不自动改参数" in text
    assert "panic 修复" in text
    assert "market:panic\\|bear" in text
    assert "收紧 watch" in text
    assert "| action |" not in text  # report uses evidence sections, not old prediction table


def test_run_rule_suggestions_writes_latest_evaluated_date():
    d = pathlib.Path(tempfile.mkdtemp(prefix="vaxrules_"))
    try:
        pred_path = d / "eod_predictions.jsonl"
        result_path = d / "eod_prediction_results.jsonl"
        pred_path.write_text(
            json.dumps(_pred("P000001", action="watch", target="20260626"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        result_path.write_text(
            json.dumps(_result("P000001", target="20260626", excess=-0.02, action_hit=False), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        text = rs.run_rule_suggestions(
            write=True,
            predictions_path=pred_path,
            results_path=result_path,
            output_dir=d,
            min_evaluated=2,
        )
        out = d / "rule_suggestions_20260626.md"
        assert out.is_file()
        assert "# Rule Suggestions 20260626" in text
        assert "source_predictions: 1" in out.read_text(encoding="utf-8")
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
