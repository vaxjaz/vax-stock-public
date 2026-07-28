# -*- coding: utf-8 -*-

from copy import deepcopy

import pytest

from vaxstock.research.conditional_forecast import (
    FORECAST_VERSION,
    build_forecast_audit,
)
from vaxstock.research.contracts import (
    ContractError,
    validate_forecast_audit,
    validate_selection_audit,
)
from vaxstock.research.walk_forward_select import SELECT_VERSION


def _selection_audit(*, status="shadow_candidate", values=None):
    values = list(values or [0.01, 0.03, -0.01, 0.05])
    selection = {
        "select_version": SELECT_VERSION,
        "status": status,
        "abstain_reason": (
            None
            if status == "shadow_candidate"
            else "insufficient_independent_oos_dates"
        ),
        "promotion_status": "manual_review_required",
        "production_eligible": False,
        "horizon_sessions": 5,
        "policy": {
            "min_side_stocks": 3,
            "min_train_dates": 2,
            "min_oos_dates": 3,
            "top_k": 1,
            "embargo_sessions": None,
            "effective_embargo_sessions": 5,
        },
        "policy_digest": "policy_5",
        "independent_dates_available": 10,
        "candidate_tests_total": 2,
        "candidate_tests_reaching_train_minimum": 2,
        "current_candidate_tests": 2,
        "current_candidates": (
            [{
                "candidate_id": "candidate_a",
                "series_id": "legacy_snapshot::legacy.rsi_14::legacy_snapshot_v1",
                "axis": "cross_section_bucket",
                "concept": None,
                "condition": {"market_regime": "panic"},
                "direction": 1,
                "ranking_score": 0.02,
                "training": {
                    "independent_dates": 8,
                    "mean_spread": 0.02,
                    "median_spread": 0.02,
                },
            }]
            if status == "shadow_candidate"
            else []
        ),
        "oos_independent_dates": (
            len(values) if status == "shadow_candidate" else 0
        ),
        "oos_summary": None,
        "folds": (
            [
                {
                    "validation_trade_date": f"202607{10 + index:02d}",
                    "strategy_oos_spread": value,
                }
                for index, value in enumerate(values)
            ]
            if status == "shadow_candidate"
            else []
        ),
        "leakage_controls": {},
        "evidence_label": (
            "candidate_not_validated"
            if status == "shadow_candidate"
            else "insufficient_history"
        ),
    }
    audit = {
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
        "status_counts": {status: 1},
        "production_eligible": False,
        "promotion_status": "manual_review_required",
    }
    validate_selection_audit(audit)
    return audit


def test_shadow_selection_becomes_empirical_conditional_distribution():
    audit = build_forecast_audit(_selection_audit())
    forecast = audit["forecasts"]["5"]

    assert audit["forecast_version"] == FORECAST_VERSION
    assert audit["status_counts"] == {"available": 1}
    assert audit["production_eligible"] is False
    assert forecast["status"] == "available"
    assert forecast["direction"] == "positive_spread"
    assert forecast["expected_excess_return"] == pytest.approx(0.02)
    assert forecast["confidence"] == pytest.approx(0.75)
    assert forecast["distribution"]["independent_oos_dates"] == 4
    assert forecast["distribution"]["q25"] == pytest.approx(0.005)
    assert forecast["distribution"]["q75"] == pytest.approx(0.035)
    assert forecast["current_candidates"][0]["candidate_id"] == "candidate_a"
    assert forecast["current_candidates"][0]["condition"] == {
        "market_regime": "panic"
    }
    assert "not stock price target" in audit["scope"]
    validate_forecast_audit(audit)


def test_select_abstention_propagates_without_numeric_forecast():
    audit = build_forecast_audit(
        _selection_audit(status="abstain")
    )
    forecast = audit["forecasts"]["5"]

    assert audit["status_counts"] == {"abstain": 1}
    assert forecast["status"] == "abstain"
    assert forecast["direction"] is None
    assert forecast["expected_excess_return"] is None
    assert forecast["confidence"] is None
    assert forecast["distribution"] is None
    assert forecast["current_candidates"] == []
    assert forecast["abstain_reason"].startswith("select_abstain:")


def test_negative_distribution_is_reported_not_relabelled_positive():
    audit = build_forecast_audit(
        _selection_audit(values=[-0.05, -0.03, 0.01, -0.01])
    )
    forecast = audit["forecasts"]["5"]
    assert forecast["direction"] == "negative_spread"
    assert forecast["expected_excess_return"] == pytest.approx(-0.02)
    assert forecast["confidence"] == pytest.approx(0.75)


def test_zero_oos_median_forces_abstention():
    audit = build_forecast_audit(
        _selection_audit(values=[-0.01, 0.0, 0.01])
    )
    forecast = audit["forecasts"]["5"]
    assert forecast["status"] == "abstain"
    assert forecast["abstain_reason"] == "zero_oos_median"


def test_forecast_contract_rejects_distribution_mismatch():
    audit = build_forecast_audit(_selection_audit())
    broken = deepcopy(audit)
    broken["forecasts"]["5"]["expected_excess_return"] = 0.5
    with pytest.raises(ContractError, match="distribution median"):
        validate_forecast_audit(broken)

    production = deepcopy(audit)
    production["production_eligible"] = True
    with pytest.raises(ContractError, match="production eligible"):
        validate_forecast_audit(production)

    digest_mismatch = deepcopy(audit)
    digest_mismatch["input_digest"] = "tampered"
    with pytest.raises(ContractError, match="input_digest mismatch"):
        validate_forecast_audit(digest_mismatch)
