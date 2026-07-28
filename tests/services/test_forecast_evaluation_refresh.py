# -*- coding: utf-8 -*-

import json
from pathlib import Path

from vaxstock.research.conditional_forecast import (
    FORECAST_VERSION,
    build_forecast_audit,
)
from vaxstock.research.contracts import (
    validate_forecast_calibration_audit,
)
from vaxstock.research.point_in_time_store import (
    default_store_paths,
    read_jsonl_strict,
)
from vaxstock.research.walk_forward_select import SELECT_VERSION
from vaxstock.services.forecast_evaluation_refresh import (
    run_forecast_evaluation_refresh,
)


def _abstain_selection():
    selection = {
        "select_version": SELECT_VERSION,
        "status": "abstain",
        "abstain_reason": "insufficient_independent_oos_dates",
        "promotion_status": "manual_review_required",
        "production_eligible": False,
        "horizon_sessions": 5,
        "policy": {
            "min_side_stocks": 3,
            "min_train_dates": 40,
            "min_oos_dates": 20,
            "top_k": 3,
            "embargo_sessions": None,
            "effective_embargo_sessions": 5,
        },
        "policy_digest": "policy_5",
        "independent_dates_available": 10,
        "candidate_tests_total": 1,
        "candidate_tests_reaching_train_minimum": 0,
        "current_candidate_tests": 0,
        "current_candidates": [],
        "oos_independent_dates": 0,
        "oos_summary": None,
        "folds": [],
        "leakage_controls": {},
        "evidence_label": "insufficient_history",
    }
    return {
        "schema_version": 1,
        "as_of_trade_date": "20260724",
        "decision_at": "2026-07-25T05:03:13+08:00",
        "select_version": SELECT_VERSION,
        "input_digest": "selection_digest",
        "horizons": {
            "5": {
                "build": {"horizon_sessions": 5},
                "selection": selection,
            }
        },
        "status_counts": {"abstain": 1},
        "production_eligible": False,
        "promotion_status": "manual_review_required",
    }


def _write_object(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False),
        encoding="utf-8",
    )


def test_forecast_evaluation_refresh_is_immutable_and_idempotent(tmp_path):
    forecasts = tmp_path / "forecasts"
    selections = tmp_path / "selections"
    results = tmp_path / "forecast_results.jsonl"
    calibrations = tmp_path / "calibrations"
    selection = _abstain_selection()
    forecast = build_forecast_audit(selection)
    _write_object(
        selections
        / f"selection_audit_20260724__{SELECT_VERSION}.json",
        selection,
    )
    _write_object(
        forecasts
        / (
            f"forecast_audit_20260724"
            f"__{SELECT_VERSION}__{FORECAST_VERSION}.json"
        ),
        forecast,
    )

    kwargs = {
        "research_paths": default_store_paths(tmp_path / "research"),
        "forecasts_dir": forecasts,
        "selections_dir": selections,
        "outcomes_path": tmp_path / "outcomes.jsonl",
        "results_path": results,
        "calibrations_dir": calibrations,
        "as_of_trade_date": "20260724",
        "decision_at": "2026-07-25T05:03:13+08:00",
    }
    first = run_forecast_evaluation_refresh(**kwargs)
    second = run_forecast_evaluation_refresh(**kwargs)

    assert first["status"] == "written"
    assert first["summary"] == {
        "forecast_audits": 1,
        "available_forecasts": 0,
        "abstain_forecasts": 1,
        "evaluated_forecasts": 0,
        "pending_forecasts": 0,
    }
    assert first["stored"] == {
        "existing": 0,
        "written": 0,
        "skipped": 0,
    }
    assert first["calibration_status"] == "no_available_forecasts"
    assert first["production_eligible"] is False
    assert second["status"] == "already_complete"
    assert second["calibration_path"] == first["calibration_path"]
    calibration = json.loads(
        Path(first["calibration_path"]).read_text(encoding="utf-8")
    )
    validate_forecast_calibration_audit(calibration)
    assert calibration["horizons"]["5"]["abstain_forecasts"] == 1
    assert "T+5" in Path(
        first["calibration_markdown_path"]
    ).read_text(encoding="utf-8")
    assert read_jsonl_strict(results) == []


def test_forecast_evaluation_refresh_blocks_without_forecasts(tmp_path):
    result = run_forecast_evaluation_refresh(
        forecasts_dir=tmp_path / "missing",
        selections_dir=tmp_path / "selections",
        as_of_trade_date="20260724",
        decision_at="2026-07-25T05:03:13+08:00",
    )
    assert result == {
        "status": "blocked",
        "reason": "forecast_audits_missing",
    }
