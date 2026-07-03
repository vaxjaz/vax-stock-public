# -*- coding: utf-8 -*-
"""research.factor_weight_review tests (MR-Eval E3, zero network)."""

import json
import pathlib
import shutil
import tempfile

import vaxstock.research.factor_weight_review as fw


def _append(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _snap(code, value=None, *, td="20260625", metric="alpha"):
    metrics = {metric: value} if value is not None else {}
    return {
        "schema_version": 1,
        "trade_date": td,
        "code": code,
        "name": code,
        "metrics": metrics,
        "market": {"regime": "momentum", "macro_regime": "bull"},
    }


def _res(code, excess, *, td="20260625"):
    return {
        "trade_date": td,
        "code": code,
        "ret": {"1": excess + 0.01},
        "mkt_ret": {"1": 0.01},
        "excess": {"1": excess},
        "complete": False,
    }


def test_analyze_factor_high_low_spread_for_manual_review():
    joined = []
    excesses = [-0.03, -0.02, -0.01, 0.01, 0.02, 0.03]
    for idx, (value, excess) in enumerate(zip([1, 2, 3, 4, 5, 6], excesses), 1):
        code = f"00000{idx}"
        joined.append({"snapshot": _snap(code, value), "result": _res(code, excess)})
    joined.append({"snapshot": _snap("000007"), "result": _res("000007", 0.05)})
    joined.append({"snapshot": _snap("000008", 8), "result": None})

    stats = fw.analyze(
        joined,
        factors=({"metric": "alpha", "label": "alpha"},),
        min_reference=3,
        spread_threshold=0.01,
    )
    row = stats["factors"][0]

    assert stats["total_snapshots"] == 8
    assert stats["evaluated_rows"] == 7
    assert stats["pending_or_unfilled"] == 1
    assert row["evaluated"] == 6
    assert row["missing_metric"] == 1
    assert row["low"]["n"] == 2
    assert row["high"]["n"] == 2
    assert abs(row["high_minus_low_excess"] - 0.05) < 1e-12
    assert row["review_action"] == "consider_up_weight_for_high_value"
    assert row["evidence_strength"] == "medium"

    text = fw.render_report(stats)
    assert "# Factor Weight Review 20260625" in text
    assert "alpha" in text
    assert "consider_up_weight_for_high_value" in text
    assert "## 术语说明" in text
    assert "`high-low`: 高值桶平均超额减低值桶平均超额" in text


def test_load_joined_merges_incremental_factor_results():
    d = pathlib.Path(tempfile.mkdtemp(prefix="vaxfw_"))
    try:
        snaps = d / "factor_snapshots.jsonl"
        results = d / "factor_results.jsonl"
        _append(snaps, _snap("000001", 1.0, metric="alpha"))
        _append(results, {
            "trade_date": "20260625", "code": "000001",
            "ret": {"1": 0.03}, "mkt_ret": {"1": 0.01}, "excess": {"1": 0.02},
            "complete": False,
        })
        _append(results, {
            "trade_date": "20260625", "code": "000001",
            "ret": {"3": 0.05}, "mkt_ret": {"3": 0.01}, "excess": {"3": 0.04},
            "complete": False,
        })

        joined = fw.load_joined(snapshots_path=snaps, results_path=results)
        result = joined[0]["result"]
        assert result["excess"]["1"] == 0.02
        assert result["excess"]["3"] == 0.04
        stats = fw.analyze(
            joined,
            horizon=1,
            factors=({"metric": "alpha", "label": "alpha"},),
            min_reference=1,
        )
        assert stats["evaluated_rows"] == 1
        assert stats["factors"][0]["evaluated"] == 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_run_factor_weight_review_writes_latest_trade_date_report():
    d = pathlib.Path(tempfile.mkdtemp(prefix="vaxfw_"))
    try:
        snaps = d / "factor_snapshots.jsonl"
        results = d / "factor_results.jsonl"
        for idx, (td, score, excess) in enumerate([
            ("20260625", 0.5, -0.02),
            ("20260625", 1.5, 0.00),
            ("20260626", 3.0, 0.03),
        ], 1):
            code = f"00000{idx}"
            _append(snaps, _snap(code, score, td=td, metric="right_side_score"))
            _append(results, _res(code, excess, td=td))

        report = fw.run_factor_weight_review(
            write=True,
            snapshots_path=snaps,
            results_path=results,
            output_dir=d,
            min_reference=1,
        )
        out = d / "factor_weight_review_20260626.md"
        assert out.is_file()
        assert "right_side_score" in report
        assert "Factor Weight Review 20260626" in out.read_text(encoding="utf-8")
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
