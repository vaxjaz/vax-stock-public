# -*- coding: utf-8 -*-

from vaxstock.services.history_summary import summarize_live_history


def test_history_summary_uses_only_evaluated_live_rows_before_cutoff():
    predictions = [
        {"prediction_id": "p1", "generation_mode": "live", "baseline_trade_date": "20260701", "code": "601138"},
        {"prediction_id": "p2", "generation_mode": "live", "baseline_trade_date": "20260702", "code": "601138"},
        {"prediction_id": "p3", "generation_mode": "replay", "baseline_trade_date": "20260702", "code": "601138"},
        {"prediction_id": "p4", "generation_mode": "live", "baseline_trade_date": "20260704", "code": "601138"},
        {"prediction_id": "pending", "generation_mode": "live", "baseline_trade_date": "20260702", "code": "601138"},
    ]
    results = [
        {"prediction_id": "p1", "generation_mode": "live", "horizon": "1", "actual": {"ret": 0.02, "excess": 0.01}},
        {"prediction_id": "p2", "generation_mode": "live", "horizon": "1", "actual": {"ret": -0.01, "excess": -0.02}},
        {"prediction_id": "p3", "generation_mode": "replay", "horizon": "1", "actual": {"ret": 9, "excess": 9}},
        {"prediction_id": "p4", "generation_mode": "live", "horizon": "1", "actual": {"ret": 8, "excess": 8}},
    ]
    summary = summarize_live_history(predictions, results, cutoff_trade_date="20260703")["601138"]
    assert summary["evaluated"] == 2
    assert summary["avg_ret"] == 0.005
    assert summary["avg_excess"] == -0.005
    assert summary["positive_excess_count"] == 1


def test_history_summary_returns_no_row_without_real_results():
    predictions = [{"prediction_id": "pending", "generation_mode": "live", "baseline_trade_date": "20260701", "code": "601138"}]
    assert summarize_live_history(predictions, []) == {}