# -*- coding: utf-8 -*-

import json

import pytest

from vaxstock.research.contracts import validate_forecast_audit
from vaxstock.research.conditional_forecast import FORECAST_VERSION
from vaxstock.research.point_in_time_store import StoreError
from vaxstock.research.walk_forward_select import SELECT_VERSION
from vaxstock.services.forecast_refresh import run_forecast_refresh


def _abstain_selection():
    selection = {
        "select_version": SELECT_VERSION,
        "status": "abstain",
        "abstain_reason": "insufficient_independent_oos_dates",
        "promotion_status": "manual_review_required",
        "production_eligible": False,
        "horizon_sessions": 5,
        "policy": {
            "min_oos_dates": 20,
        },
        "policy_digest": "policy_5",
        "oos_independent_dates": 0,
        "current_candidates": [],
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


def test_forecast_refresh_is_immutable_and_idempotent(tmp_path):
    selections = tmp_path / "selections"
    forecasts = tmp_path / "forecasts"
    selections.mkdir()
    selection_path = selections / (
        f"selection_audit_20260724__{SELECT_VERSION}.json"
    )
    selection_path.write_text(
        json.dumps(_abstain_selection(), ensure_ascii=False),
        encoding="utf-8",
    )

    first = run_forecast_refresh(
        selections_dir=selections,
        forecasts_dir=forecasts,
        as_of_trade_date="20260724",
    )
    second = run_forecast_refresh(
        selections_dir=selections,
        forecasts_dir=forecasts,
        as_of_trade_date="20260724",
    )

    assert first["status"] == "abstain"
    assert first["write_status"] == "written"
    assert first["production_eligible"] is False
    assert second["write_status"] == "already_complete"
    stored = json.loads(
        (
            forecasts
            / (
                f"forecast_audit_20260724"
                f"__{SELECT_VERSION}__{FORECAST_VERSION}.json"
            )
        ).read_text(
            encoding="utf-8"
        )
    )
    validate_forecast_audit(stored)
    assert stored["status_counts"] == {"abstain": 1}
    forecast = stored["forecasts"]["5"]
    assert forecast["expected_excess_return"] is None
    assert forecast["distribution"] is None


def test_forecast_refresh_blocks_without_selection(tmp_path):
    result = run_forecast_refresh(
        selections_dir=tmp_path / "missing",
        forecasts_dir=tmp_path / "forecasts",
        as_of_trade_date="20260724",
    )
    assert result == {
        "status": "blocked",
        "reason": "selection_audit_missing",
        "as_of_trade_date": "20260724",
    }


def test_forecast_refresh_rejects_explicit_selection_date_mismatch(tmp_path):
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(
        json.dumps(_abstain_selection(), ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(StoreError, match="does not match requested"):
        run_forecast_refresh(
            selection_path=selection_path,
            forecasts_dir=tmp_path / "forecasts",
            as_of_trade_date="20260725",
        )
