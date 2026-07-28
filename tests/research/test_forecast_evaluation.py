# -*- coding: utf-8 -*-

from copy import deepcopy

import pytest

from vaxstock.research.conditional_forecast import build_forecast_audit
from vaxstock.research.contextual_group import (
    GROUP_VERSION,
    STOCK_GROUP_FACTOR_ID,
    STOCK_GROUP_FACTOR_VERSION,
)
from vaxstock.research.contracts import (
    ContractError,
    canonical_digest,
    make_factor_value_id,
    make_group_outcome_id,
    validate_forecast_calibration_audit,
    validate_forecast_result,
)
from vaxstock.research.forecast_evaluation import (
    build_calibration_audit,
    evaluate_forecast_audit,
    render_calibration_markdown,
)
from vaxstock.research.walk_forward_select import SELECT_VERSION


BASELINE = "20260724"
SERIES = "legacy_snapshot::legacy.rsi_14::legacy_snapshot_v1"
CANDIDATE = "candidate_" + canonical_digest({
    "axis": "cross_section_bucket",
    "series_id": SERIES,
})


def _selection_audit(*, status="shadow_candidate"):
    values = [0.01, 0.03, -0.01, 0.05]
    candidate = {
        "candidate_id": CANDIDATE,
        "series_id": SERIES,
        "axis": "cross_section_bucket",
        "direction": 1,
        "ranking_score": 0.02,
        "training": {
            "independent_dates": 8,
            "mean_spread": 0.02,
            "median_spread": 0.02,
        },
    }
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
        "horizon_sessions": 1,
        "policy": {
            "min_side_stocks": 3,
            "min_train_dates": 2,
            "min_oos_dates": 3,
            "top_k": 1,
            "embargo_sessions": None,
            "effective_embargo_sessions": 1,
        },
        "policy_digest": "policy_1",
        "independent_dates_available": 10,
        "candidate_tests_total": 1,
        "candidate_tests_reaching_train_minimum": 1,
        "current_candidate_tests": 1,
        "current_candidates": (
            [candidate] if status == "shadow_candidate" else []
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
    return {
        "schema_version": 1,
        "as_of_trade_date": BASELINE,
        "decision_at": "2026-07-25T05:03:13+08:00",
        "select_version": SELECT_VERSION,
        "input_digest": "selection_digest",
        "horizons": {
            "1": {
                "build": {"horizon_sessions": 1},
                "selection": selection,
            }
        },
        "status_counts": {status: 1},
        "production_eligible": False,
        "promotion_status": "manual_review_required",
    }


def _group(code, side):
    inputs = [f"obs_{BASELINE}_{code}"]
    row = {
        "schema_version": 1,
        "factor_value_id": "",
        "entity_type": "stock",
        "entity_id": code,
        "dimension": "research_group",
        "factor_id": STOCK_GROUP_FACTOR_ID,
        "factor_version": STOCK_GROUP_FACTOR_VERSION,
        "value": {
            "group_version": GROUP_VERSION,
            "label_usage": "none",
            "factor_groups": {
                SERIES: {
                    "cross_section": {
                        "status": "available",
                        "bucket": side,
                        "rank_pct": 0.9 if side == "high" else 0.1,
                    },
                    "curve_state_vector": [None, None, None, None, None],
                    "track_relation_vectors": {},
                }
            },
        },
        "as_of_trade_date": BASELINE,
        "effective_date": BASELINE,
        "available_at": "2026-07-25T05:03:11+08:00",
        "calculated_at": "2026-07-25T05:03:11+08:00",
        "input_observation_ids": inputs,
        "input_digest": canonical_digest(inputs),
        "quality": "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _outcome(group, excess):
    row = {
        "schema_version": 1,
        "outcome_id": "",
        "as_of_trade_date": BASELINE,
        "code": group["entity_id"],
        "group_factor_value_id": group["factor_value_id"],
        "group_factor_version": group["factor_version"],
        "group_version": GROUP_VERSION,
        "group_available_at": group["available_at"],
        "group_calculated_at": group["calculated_at"],
        "horizon_sessions": 1,
        "outcome_trade_date": "20260727",
        "outcome_available_at": "2026-07-28T05:01:00+08:00",
        "ret": excess + 0.01,
        "benchmark_ret": 0.01,
        "excess_ret": excess,
        "benchmark_code": "000001.SH",
        "benchmark_kind": "legacy_market_index",
        "source": "legacy.factor_results",
        "source_ref": (
            "var/eval/factor_results.jsonl#"
            f"{BASELINE}:{group['entity_id']}:T+1"
        ),
        "independent_session_id": BASELINE,
        "input_digest": "",
    }
    row["input_digest"] = canonical_digest({
        "group_factor_value_id": row["group_factor_value_id"],
        "horizon_sessions": 1,
        "outcome_trade_date": row["outcome_trade_date"],
        "outcome_available_at": row["outcome_available_at"],
        "ret": row["ret"],
        "benchmark_ret": row["benchmark_ret"],
        "excess_ret": row["excess_ret"],
        "benchmark_code": row["benchmark_code"],
        "source": row["source"],
    })
    row["outcome_id"] = make_group_outcome_id(row)
    return row


def _cross_section():
    groups = []
    outcomes = []
    for index in range(6):
        side = "high" if index < 3 else "low"
        group = _group(f"6000{index:02d}", side)
        groups.append(group)
        outcomes.append(
            _outcome(group, 0.03 if side == "high" else -0.01)
        )
    return groups, outcomes


def test_available_forecast_evaluates_complete_daily_cross_section():
    selection = _selection_audit()
    forecast = build_forecast_audit(selection)
    groups, outcomes = _cross_section()

    results, audit = evaluate_forecast_audit(
        forecast_audit=forecast,
        selection_audit=selection,
        group_factor_rows=groups,
        outcome_rows=outcomes,
    )

    assert audit["evaluated_forecasts"] == 1
    assert audit["pending_forecasts"] == 0
    assert len(results) == 1
    result = results[0]
    assert result["actual_selected_group_spread"] == pytest.approx(0.04)
    assert result["expected_spread"] == pytest.approx(0.02)
    assert result["signed_error"] == pytest.approx(0.02)
    assert result["direction_hit"] is True
    assert result["within_q25_q75"] is False
    assert result["within_q10_q90"] is True
    assert len(result["group_outcome_ids"]) == 6
    validate_forecast_result(result)


def test_partial_cross_section_remains_pending_without_result():
    selection = _selection_audit()
    forecast = build_forecast_audit(selection)
    groups, outcomes = _cross_section()

    results, audit = evaluate_forecast_audit(
        forecast_audit=forecast,
        selection_audit=selection,
        group_factor_rows=groups,
        outcome_rows=outcomes[:-1],
    )

    assert results == []
    assert audit["pending_forecasts"] == 1
    assert audit["pending"]["1"]["available_stock_outcomes"] == 5
    assert audit["pending"]["1"]["expected_stock_outcomes"] == 6


def test_candidate_without_two_sided_current_group_is_rejected():
    selection = _selection_audit()
    forecast = build_forecast_audit(selection)
    groups, outcomes = _cross_section()
    one_sided_groups = [
        _group(group["entity_id"], "high") for group in groups
    ]
    one_sided_outcomes = [
        _outcome(group, 0.03) for group in one_sided_groups
    ]

    with pytest.raises(
        ContractError,
        match="lacks a complete current cross-section",
    ):
        evaluate_forecast_audit(
            forecast_audit=forecast,
            selection_audit=selection,
            group_factor_rows=one_sided_groups,
            outcome_rows=one_sided_outcomes,
        )


def test_calibration_is_per_horizon_and_point_in_time():
    selection = _selection_audit()
    forecast = build_forecast_audit(selection)
    groups, outcomes = _cross_section()
    results, _ = evaluate_forecast_audit(
        forecast_audit=forecast,
        selection_audit=selection,
        group_factor_rows=groups,
        outcome_rows=outcomes,
    )
    calibration = build_calibration_audit(
        forecast_audits=[forecast],
        result_rows=results,
        as_of_trade_date="20260727",
        decision_at="2026-07-28T05:02:00+08:00",
        select_version=forecast["select_version"],
        forecast_version=forecast["forecast_version"],
    )

    metrics = calibration["horizons"]["1"]
    assert calibration["status"] == "insufficient_evaluated_dates"
    assert metrics["forecast_dates"] == 1
    assert metrics["evaluated_dates"] == 1
    assert metrics["direction_hit_rate"] == 1.0
    assert metrics["mean_absolute_error"] == pytest.approx(0.02)
    assert calibration["production_eligible"] is False
    assert "| T+1 | 1 | 1 | 0 | 1 | 0 |" in (
        render_calibration_markdown(calibration)
    )
    validate_forecast_calibration_audit(calibration)

    tampered = deepcopy(calibration)
    tampered["horizons"]["1"]["evaluated_dates"] = 2
    with pytest.raises(ContractError, match="evaluated/pending"):
        validate_forecast_calibration_audit(tampered)


def test_calibration_does_not_read_a_result_before_it_was_available():
    selection = _selection_audit()
    forecast = build_forecast_audit(selection)
    groups, outcomes = _cross_section()
    results, _ = evaluate_forecast_audit(
        forecast_audit=forecast,
        selection_audit=selection,
        group_factor_rows=groups,
        outcome_rows=outcomes,
    )

    calibration = build_calibration_audit(
        forecast_audits=[forecast],
        result_rows=results,
        as_of_trade_date="20260727",
        decision_at="2026-07-27T15:30:00+08:00",
        select_version=forecast["select_version"],
        forecast_version=forecast["forecast_version"],
    )

    metrics = calibration["horizons"]["1"]
    assert metrics["available_forecasts"] == 1
    assert metrics["evaluated_dates"] == 0
    assert metrics["pending_available"] == 1
    assert metrics["direction_hit_rate"] is None


def test_abstain_forecast_is_counted_but_never_given_a_result():
    selection = _selection_audit(status="abstain")
    forecast = build_forecast_audit(selection)
    groups, outcomes = _cross_section()
    results, evaluation = evaluate_forecast_audit(
        forecast_audit=forecast,
        selection_audit=selection,
        group_factor_rows=groups,
        outcome_rows=outcomes,
    )
    calibration = build_calibration_audit(
        forecast_audits=[forecast],
        result_rows=results,
        as_of_trade_date="20260727",
        decision_at="2026-07-28T05:02:00+08:00",
        select_version=forecast["select_version"],
        forecast_version=forecast["forecast_version"],
    )

    assert results == []
    assert evaluation["abstain_forecasts"] == 1
    assert calibration["status"] == "no_available_forecasts"
    assert calibration["horizons"]["1"]["abstain_forecasts"] == 1
    assert calibration["horizons"]["1"]["evaluated_dates"] == 0
