# -*- coding: utf-8 -*-

from vaxstock.services.history_summary import (
    _enrich_result_trade_dates, summarize_live_history,
)


def test_history_summary_uses_only_evaluated_live_rows_before_cutoff():
    predictions = [
        {"prediction_id": "p1", "generation_mode": "live", "baseline_trade_date": "20260701", "target_trade_date": "20260702", "code": "601138", "rule_version": "v1", "prediction": {"action": "watch", "direction": "up", "horizon": "T+1"}, "features_ref": {"market_regime": "value", "macro_regime": "neutral"}},
        {"prediction_id": "p2", "generation_mode": "live", "baseline_trade_date": "20260702", "target_trade_date": "20260703", "code": "601138", "rule_version": "v1", "prediction": {"action": "watch", "direction": "up", "horizon": "T+1"}, "features_ref": {"market_regime": "value", "macro_regime": "neutral"}},
        {"prediction_id": "p3", "generation_mode": "replay", "baseline_trade_date": "20260702", "code": "601138"},
        {"prediction_id": "p4", "generation_mode": "live", "baseline_trade_date": "20260704", "code": "601138"},
        {"prediction_id": "pending", "generation_mode": "live", "baseline_trade_date": "20260702", "code": "601138"},
    ]
    results = [
        {"prediction_id": "p1", "generation_mode": "live", "horizon": "1", "actual": {"ret": 0.02, "excess": 0.01}},
        {"prediction_id": "p2", "generation_mode": "live", "horizon": "1", "actual": {"ret": -0.01, "excess": -0.02}},
        {"prediction_id": "p1", "generation_mode": "live", "horizon": "5", "actual": {"ret": 0.08, "excess": 0.05}},
        {"prediction_id": "p2", "generation_mode": "live", "horizon": "5", "actual": {"ret": 0.02, "excess": -0.01}},
        {"prediction_id": "p3", "generation_mode": "replay", "horizon": "1", "actual": {"ret": 9, "excess": 9}},
        {"prediction_id": "p4", "generation_mode": "live", "horizon": "1", "actual": {"ret": 8, "excess": 8}},
    ]
    summary = summarize_live_history(predictions, results, cutoff_trade_date="20260703")["601138"]
    assert summary["evaluated"] == 2
    assert summary["avg_ret"] == 0.005
    assert summary["positive_ret_count"] == 1
    assert summary["positive_ret_rate"] == 0.5
    assert summary["avg_excess"] == -0.005
    assert summary["positive_excess_count"] == 1
    assert summary["absolute_action_expectation"] == "positive"
    assert summary["absolute_action_evaluated"] == 2
    assert summary["absolute_action_hit_count"] == 1
    assert summary["absolute_action_hit_rate"] == 0.5
    assert summary["prediction_count"] == 3
    assert summary["max_horizon"] == 5
    assert summary["horizons"]["5"]["evaluated"] == 2
    assert summary["horizons"]["5"]["avg_ret"] == 0.05
    assert summary["horizons"]["5"]["positive_ret_count"] == 2
    assert summary["horizons"]["5"]["positive_ret_rate"] == 1.0
    assert summary["horizons"]["5"]["avg_excess"] == 0.02
    assert summary["horizons"]["5"]["positive_excess_count"] == 1


def test_matching_history_uses_same_action_and_direction_not_market_context():
    predictions = [
        {"prediction_id": "same", "generation_mode": "live", "baseline_trade_date": "20260701",
         "target_trade_date": "20260702", "code": "601138", "rule_version": "v1",
         "prediction": {"action": "watch", "direction": "up", "horizon": "T+1"},
         "features_ref": {"market_regime": "value", "macro_regime": "neutral"}},
        {"prediction_id": "same_other_context", "generation_mode": "live",
         "baseline_trade_date": "20260702", "target_trade_date": "20260703",
         "code": "601138", "rule_version": "v1",
         "prediction": {"action": "watch", "direction": "up", "horizon": "T+1"},
         "features_ref": {"market_regime": "panic", "macro_regime": "bearish"}},
        {"prediction_id": "other", "generation_mode": "live", "baseline_trade_date": "20260701",
         "target_trade_date": "20260702", "code": "601138", "rule_version": "v1",
         "prediction": {"action": "avoid", "direction": "neutral", "horizon": "T+1"},
         "features_ref": {"market_regime": "value", "macro_regime": "neutral"}},
    ]
    results = [
        {"prediction_id": "same", "generation_mode": "live", "horizon": "1",
         "actual": {"trade_date": "20260702", "ret": 0.01, "excess": 0.02}},
        {"prediction_id": "same", "generation_mode": "live", "horizon": "2",
         "actual": {"trade_date": "20260706", "ret": 0.03, "excess": 0.04}},
        {"prediction_id": "same_other_context", "generation_mode": "live", "horizon": "1",
         "actual": {"trade_date": "20260703", "ret": 0.02, "excess": None}},
        {"prediction_id": "other", "generation_mode": "live", "horizon": "1",
         "actual": {"trade_date": "20260702", "ret": -0.10, "excess": -0.10}},
    ]
    current = predictions[0]
    summary = summarize_live_history(
        predictions,
        results,
        cutoff_trade_date="20260703",
        current_signals={"601138": current},
        require_result_trade_date=True,
    )["601138"]
    assert summary["scope"] == "matching_current_action"
    assert summary["cohort"] == {
        "rule_version": "v1", "action": "watch", "direction": "up",
    }
    cell = summary["horizons"]["1"]
    assert cell["evaluated"] == 2
    assert cell["absolute_action_hit_count"] == 2
    assert cell["absolute_action_hit_rate"] == 1.0
    assert cell["absolute_action_sample_dates"] == ["20260701", "20260702"]
    assert "2" not in summary["horizons"]


def test_absolute_action_review_does_not_require_excess():
    predictions = [{
        "prediction_id": "p1", "generation_mode": "live",
        "baseline_trade_date": "20260701", "target_trade_date": "20260702",
        "code": "601138", "rule_version": "v1",
        "prediction": {"action": "watch", "direction": "up", "horizon": "T+1"},
    }]
    results = [{
        "prediction_id": "p1", "generation_mode": "live", "horizon": "1",
        "actual": {"trade_date": "20260702", "ret": 0.01},
    }]
    summary = summarize_live_history(predictions, results)["601138"]
    assert summary["avg_excess"] is None
    assert summary["absolute_action_hit_count"] == 1

def test_old_c_path_recovers_actual_trade_date_from_b_line():
    predictions = [{
        "prediction_id": "p1", "baseline_trade_date": "20260701", "code": "601138",
    }]
    results = [{
        "prediction_id": "p1", "horizon": "5", "actual": {"ret": 0.1, "excess": 0.05},
    }]
    factors = [{
        "trade_date": "20260701", "code": "601138",
        "horizon_trade_dates": {"5": "20260708"},
    }]
    enriched = _enrich_result_trade_dates(predictions, results, factors)
    assert enriched[0]["actual"]["trade_date"] == "20260708"
    assert "trade_date" not in results[0]["actual"]


def test_history_summary_returns_no_row_without_real_results():
    predictions = [{"prediction_id": "pending", "generation_mode": "live", "baseline_trade_date": "20260701", "code": "601138"}]
    assert summarize_live_history(predictions, []) == {}