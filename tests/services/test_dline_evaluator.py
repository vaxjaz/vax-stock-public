# -*- coding: utf-8 -*-

from vaxstock.services import dline_evaluator as de


def _task(task_id, code):
    return {
        "task_id": task_id,
        "code": code,
        "name": code,
        "baseline_trade_date": "20260713",
        "target_trade_date": "20260714",
        "plan_version": "d_observe_llm_v2",
        "evidence_pack": {
            "C_prediction": {
                "prediction": {
                    "rule_version": "c_v1",
                    "action": "candidate_buy",
                    "direction": "up",
                    "confidence": 0.7,
                }
            }
        },
        "observation": {
            "trigger_blueprints": [{
                "trigger_type": "reclaim_confirm",
                "severity": "medium",
                "condition": {
                    "all": [{"field": "price_vs_ma20_pct", "op": ">", "value": 0}],
                },
            }],
        },
    }


def _forecast(task_id, code):
    return {
        "forecast_ts": "2026-07-14T10:00:01",
        "trade_date": "2026-07-14",
        "code": code,
        "inputs_ref": {
            "dline_task_id": task_id,
            "dline_plan_version": "d_observe_llm_v2",
            "trigger_blueprint": {
                "trigger_type": "reclaim_confirm",
                "severity": "medium",
            },
            "quote_snapshot": {
                "trade_time": "10:00:00",
                "price": 100.0,
                "change_pct": 1.0,
                "source": "sina",
            },
        },
        "structured": {
            "source": "dline_task_blueprint",
            "trigger_type": "reclaim_confirm",
        },
    }


def test_dline_results_score_trigger_and_qualified_no_trigger_without_execution():
    fired_id = "20260713_20260714_600001_d_observe_llm_v2"
    quiet_id = "20260713_20260714_600002_d_observe_llm_v2"
    missing_id = "20260713_20260714_600003_d_observe_llm_v2"
    tasks = [
        _task(fired_id, "600001"),
        _task(quiet_id, "600002"),
        _task(missing_id, "600003"),
    ]
    coverage = [{
        "coverage_id": "coverage-quiet",
        "task_id": quiet_id,
        "quality": {"policy_version": "d_full_session_v1", "qualified": True},
    }]
    snapshots = [
        {"trade_date": "20260714", "code": "600001", "price_at_snapshot": 102.0},
        {"trade_date": "20260714", "code": "600002", "price_at_snapshot": 50.0},
        {"trade_date": "20260714", "code": "600003", "price_at_snapshot": 30.0},
    ]
    factor_results = [
        {
            "trade_date": "20260714", "code": "600001",
            "ret": {"1": 0.05}, "horizon_trade_dates": {"1": "20260715"},
        },
        {
            "trade_date": "20260714", "code": "600002",
            "ret": {"1": -0.03}, "horizon_trade_dates": {"1": "20260715"},
        },
        {
            "trade_date": "20260714", "code": "600003",
            "ret": {"1": 0.02}, "horizon_trade_dates": {"1": "20260715"},
        },
    ]

    rows, stats = de.build_dline_results(
        tasks=tasks,
        forecasts=[_forecast(fired_id, "600001")],
        coverage_rows=coverage,
        snapshots=snapshots,
        factor_results=factor_results,
        filled_at="2026-07-15T05:00:00",
    )

    assert len(rows) == 3
    fired = {
        row["horizon"]: row for row in rows
        if row["task_id"] == fired_id
    }
    assert set(fired) == {"0", "1"}
    assert round(fired["0"]["outcome"]["ret_from_trigger"], 6) == 0.02
    assert round(fired["1"]["outcome"]["ret_from_trigger"], 6) == 0.071
    assert fired["1"]["outcome"]["ret_from_target_close"] == 0.05
    assert fired["1"]["evaluation"]["decision_hit"] is True
    assert fired["1"]["evaluation"]["user_execution_used"] is False

    quiet = next(row for row in rows if row["task_id"] == quiet_id)
    assert quiet["trigger"]["status"] == "qualified_not_triggered"
    assert quiet["outcome"]["evaluation_basis"] == "target_eod_close"
    assert quiet["outcome"]["evaluation_return"] == -0.03
    assert quiet["evaluation"]["decision_hit"] is True

    assert not any(row["task_id"] == missing_id for row in rows)
    assert stats["coverage_missing"] == 1


def test_dline_results_are_idempotent_by_sample_and_horizon():
    task_id = "20260713_20260714_600001_d_observe_llm_v2"
    kwargs = {
        "tasks": [_task(task_id, "600001")],
        "forecasts": [_forecast(task_id, "600001")],
        "coverage_rows": [],
        "snapshots": [
            {"trade_date": "20260714", "code": "600001", "price_at_snapshot": 102.0},
        ],
        "factor_results": [{
            "trade_date": "20260714", "code": "600001",
            "ret": {"1": 0.05}, "horizon_trade_dates": {"1": "20260715"},
        }],
        "filled_at": "2026-07-15T05:00:00",
    }
    first, _ = de.build_dline_results(**kwargs)
    second, stats = de.build_dline_results(existing_results=first, **kwargs)
    assert len(first) == 2
    assert second == []
    assert stats["skipped_existing"] == 2


def test_risk_trigger_uses_non_positive_absolute_return():
    assert de.trigger_expectation("breakdown_confirm") == "non_positive"
    assert de.dline_decision_hit("non_positive", "triggered", -0.01) is True
    assert de.dline_decision_hit("non_positive", "triggered", 0.01) is False
    assert de.dline_decision_hit(
        "non_positive", "qualified_not_triggered", 0.01,
    ) is True
