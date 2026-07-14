# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path

from vaxstock.research import dline_review as dr


def _row(index, status, ret, hit=True):
    return {
        "sample_id": f"sample-{status}-{index}",
        "plan_version": "d_observe_llm_v2",
        "trigger_type": "reclaim_confirm",
        "expectation": "positive",
        "horizon": "5",
        "horizon_trade_date": "20260721",
        "trigger": {"status": status},
        "outcome": {"ret_from_target_close": ret},
        "evaluation": {"decision_hit": hit, "user_execution_used": False},
    }


def test_dline_review_requires_both_triggered_and_no_trigger_counterfactuals():
    rows = [
        *[_row(i, "triggered", 0.05) for i in range(5)],
        *[_row(i, "qualified_not_triggered", -0.02) for i in range(5)],
    ]
    report = dr.build_dline_review(rows, as_of_trade_date="20260721")
    cell = report["cells"][0]

    assert cell["triggered"] == 5
    assert cell["qualified_not_triggered"] == 5
    assert cell["decision_hit_rate"] == 1.0
    assert round(cell["incremental_separation"], 6) == 0.07
    assert cell["verdict"] == "preliminary_support"
    assert cell["suggestion"] == "keep_rule"
    assert report["basis"]["user_execution_used"] is False
    assert report["basis"]["automatic_parameter_change"] is False


def test_dline_review_does_not_recommend_change_without_counterfactual_group():
    rows = [_row(i, "triggered", 0.05) for i in range(20)]
    cell = dr.build_dline_review(rows)["cells"][0]
    assert cell["verdict"] == "insufficient_counterfactual"
    assert cell["suggestion"] == "collect_counterfactual"


def test_dline_review_records_only_verdict_state_changes():
    rows = [
        *[_row(i, "triggered", 0.05) for i in range(5)],
        *[_row(i, "qualified_not_triggered", -0.02) for i in range(5)],
    ]
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        results = directory / "results.jsonl"
        results.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
        state = directory / "latest.json"
        state.write_text(json.dumps({
            "cells": [{
                "cell_key": "d_observe_llm_v2|reclaim_confirm|5",
                "verdict": "insufficient_counterfactual",
            }],
        }), encoding="utf-8")
        report = dr.run_dline_review(
            write=True,
            results_path=results,
            output_dir=directory,
            state_path=state,
            as_of_trade_date="20260721",
        )
        markdown = (directory / "dline_review_20260721.md").read_text(
            encoding="utf-8"
        )

    assert report["changes"] == [{
        "cell_key": "d_observe_llm_v2|reclaim_confirm|5",
        "before": "insufficient_counterfactual",
        "after": "preliminary_support",
        "suggestion": "keep_rule",
    }]
    assert "?????????D????" in markdown
