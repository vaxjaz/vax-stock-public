# -*- coding: utf-8 -*-

from vaxstock.analysis.daily_action import (
    _history_evidence_verdict, build_daily_action_plan,
)
from vaxstock.report.daily_action import render_daily_action_markdown


def _task(code, action, direction):
    return {
        "task_id": f"task_{code}",
        "code": code,
        "name": code,
        "baseline_trade_date": "20260710",
        "target_trade_date": "20260713",
        "evidence_pack": {
            "baseline_trade_date": "20260710",
            "A_eod": {
                "price": 10.0,
                "metrics": {"ma5": 10.0, "ma20": 9.0},
                "market": {
                    "market_regime": "value",
                    "macro_regime": "中性",
                    "ai_track": {"position_ceiling": "减档"}
                }
            },
            "B_prediction_history_summary": {
                "available": True, "evaluated": 6, "avg_ret": 0.0076,
                "positive_ret_count": 4,
            },
            "E_context": {"earnings": {
                "latest_report": {"period": "20260331", "net_profit_yoy": 30.5},
                "next_report": {"period": "20260630", "expected_ann_date": "20260812", "status": "scheduled"},
            }},            "C_prediction": {
                "prediction": {
                    "action": action,
                    "direction": direction,
                    "confidence": 0.6
                }
            }
        },
        "observation": {
            "trigger_blueprints": [
                {
                    "trigger_type": "reclaim_confirm",
                    "condition": {"all": [{"field": "price_vs_ma5_pct", "op": ">=", "value": 0}]}
                },
                {
                    "trigger_type": "breakdown_confirm",
                    "condition": {"all": [{"field": "price_vs_ma20_pct", "op": "<", "value": -5}]}
                }
            ]
        }
    }


def _policy():
    return {
        "policy_version": "discipline_v1",
        "trade_rules": {"buy_lot_size": 100},
        "action_rules": {
            "conditional_add_unit": "half_unit",
            "risk_reduce_unit": "unit",
            "c_actions_eligible_for_conditional_add": ["watch"],
            "positive_trigger_types": ["reclaim_confirm"],
            "risk_trigger_types": ["breakdown_confirm"]
        }
    }


def _capacity():
    return {
        "account": {
            "as_of_trade_date": "20260713",
            "source": "broker_screenshot_user_confirmed",
            "available_cash": 50000.0,
            "reported_position_pct": 50.0,
            "unit_amounts": {"half_unit": 2500.0, "unit": 5000.0}
        },
        "holdings": {
            "600001": {
                "available": True, "tier": "ordinary", "shares": 1000,
                "reference_price": 10.0, "current_weight_pct": 10.0, "cap_pct": 20.0,
                "unit_capacity": {"half_unit": {"estimated_shares": 200, "estimated_amount": 2000.0}}
            },
            "600002": {
                "available": True, "tier": "ordinary", "shares": 500,
                "reference_price": 10.0, "current_weight_pct": 5.0, "cap_pct": 10.0,
                "unit_capacity": {"half_unit": {"estimated_shares": 200, "estimated_amount": 2000.0}}
            }
        }
    }


def test_daily_action_requires_d_confirmation_and_keeps_avoid_as_no_add():
    snapshot = {
        "target_trade_dates": ["20260713"],
        "tasks": [_task("600001", "watch", "up"), _task("600002", "avoid", "neutral")]
    }
    holdings = {
        "600001": {"name": "A", "shares": 1000, "cost": 12.0},
        "600002": {"name": "B", "shares": 500, "cost": 8.0}
    }
    plan = build_daily_action_plan(snapshot, holdings, _capacity(), _policy())
    assert plan["available"] is True
    by_code = {row["code"]: row for row in plan["holdings"]}
    assert by_code["600001"]["action"] == "持有，等待加仓确认"
    assert by_code["600001"]["conditional_add"]["estimated_shares"] == 200
    assert by_code["600001"]["risk_reduce"]["estimated_shares"] == 500
    assert by_code["600001"]["pnl_pct"] == -16.6667
    assert by_code["600001"]["pnl_amount_estimate"] == -2000.0
    assert by_code["600002"]["action"] == "持有观察，不加仓"
    assert by_code["600002"]["conditional_add"] is None

    markdown = render_daily_action_markdown(plan)
    assert "收复确认" in markdown
    assert "破位确认" in markdown
    assert "20日均线下方5%阈值" in markdown
    assert "今日不开新仓" in markdown
    assert "**2. 当前实际盈亏**: -16.67%（估算-2,000.00元；成本12.000/参考价10.000）。" in markdown
    assert "live已核验6次，平均收益+0.76%，4/6次收益为正" in markdown
    assert "预计披露 2026-08-12" in markdown
    labels = [
        "**1. 今天做什么**",
        "**2. 当前实际盈亏**",
        "**3. 历史策略表现**",
        "**4. 历史结果是否改变今天动作**",
    ]
    positions = [markdown.index(label) for label in labels]
    assert positions == sorted(positions)


def test_matching_c_history_conflict_blocks_add_but_not_risk_reduce():
    task = _task("600001", "watch", "up")
    task["evidence_pack"]["C_matching_history_summary"] = {
        "available": True,
        "scope": "matching_current_action",
        "horizons": {
            "1": {
                "evaluated": 6,
                "avg_ret": -0.005,
                "absolute_action_expectation": "positive",
                "absolute_action_evaluated": 6,
                "absolute_action_hit_count": 2,
                "absolute_action_hit_rate": 2 / 6,
            }
        },
    }
    snapshot = {"target_trade_dates": ["20260713"], "tasks": [task]}
    holdings = {"600001": {"name": "A", "shares": 1000}}
    capacity = _capacity()
    capacity["holdings"] = {"600001": capacity["holdings"]["600001"]}

    plan = build_daily_action_plan(snapshot, holdings, capacity, _policy())
    row = plan["holdings"][0]
    assert row["history_verdict"]["verdict"] == "preliminary_conflict"
    assert row["action"] == "持有观察，不加仓"
    assert row["conditional_add"] is None
    assert row["risk_reduce"] is not None
    markdown = render_daily_action_markdown(plan)
    assert "初步反对今天动作" in markdown


def test_t5_conflict_blocks_add_and_stable_t10_requests_position_review():
    task = _task("600001", "watch", "up")
    task["evidence_pack"]["C_matching_history_summary"] = {
        "available": True,
        "scope": "matching_current_action",
        "horizons": {
            "1": {"evaluated": 6, "avg_ret": 0.01, "absolute_action_expectation": "positive", "absolute_action_evaluated": 6, "absolute_action_hit_count": 4, "absolute_action_hit_rate": 4 / 6},
            "5": {"evaluated": 6, "avg_ret": -0.02, "absolute_action_expectation": "positive", "absolute_action_evaluated": 6, "absolute_action_hit_count": 2, "absolute_action_hit_rate": 2 / 6},
            "10": {"evaluated": 20, "avg_ret": -0.03, "absolute_action_expectation": "positive", "absolute_action_evaluated": 20, "absolute_action_hit_count": 6, "absolute_action_hit_rate": 0.30},
        },
    }
    snapshot = {"target_trade_dates": ["20260713"], "tasks": [task]}
    holdings = {"600001": {"name": "A", "shares": 1000}}
    capacity = _capacity()
    capacity["holdings"] = {"600001": capacity["holdings"]["600001"]}

    plan = build_daily_action_plan(snapshot, holdings, capacity, _policy())
    row = plan["holdings"][0]
    assert row["history_verdict"]["blocked_horizons"] == ["5"]
    assert row["history_verdict"]["review_horizons"] == ["10"]
    assert row["history_position_review"] is True
    assert row["action"] == "持有观察，不加仓"
    assert row["risk_reduce"] is not None
    markdown = render_daily_action_markdown(plan)
    assert "T+10达到稳定证据，仓位规则待人工复盘" in markdown


def test_long_horizon_conflict_requests_review_without_blocking_add():
    summary = {
        "horizons": {
            "10": {"evaluated": 20, "avg_ret": -0.03, "absolute_action_expectation": "positive", "absolute_action_evaluated": 20, "absolute_action_hit_count": 6, "absolute_action_hit_rate": 0.30},
        }
    }
    verdict = _history_evidence_verdict(summary, _policy()["action_rules"])
    assert verdict["verdict"] == "insufficient"
    assert verdict["blocks_add"] is False
    assert verdict["review_horizons"] == ["10"]


def test_missing_dline_task_makes_row_pending_instead_of_guessing_action():
    snapshot = {"target_trade_dates": ["20260713"], "tasks": [_task("600001", "watch", "up")]}
    holdings = {"600001": {"name": "A", "shares": 1000}, "600002": {"name": "B", "shares": 500}}
    plan = build_daily_action_plan(snapshot, holdings, _capacity(), _policy())
    assert plan["available"] is False
    row = {x["code"]: x for x in plan["holdings"]}["600002"]
    assert row["action"] == "数据待确认，不操作"
    assert "dline.task" in row["pending"]

def test_degraded_plan_disables_all_conditional_adds():
    snapshot = {"target_trade_dates": ["20260713"], "tasks": [_task("600001", "watch", "up")]}
    holdings = {"600001": {"name": "A", "shares": 1000}}
    capacity = _capacity()
    capacity["holdings"] = {"600001": capacity["holdings"]["600001"]}
    plan = build_daily_action_plan(snapshot, holdings, capacity, _policy(), degraded=True)
    row = plan["holdings"][0]
    assert row["action"] == "持有，不加仓"
    assert row["conditional_add"] is None
    assert "降级模式" in render_daily_action_markdown(plan)

def test_history_verdict_uses_absolute_return_not_benchmark_excess():
    summary = {
        "horizons": {
            "1": {
                "evaluated": 6,
                "avg_ret": -0.01,
                "absolute_action_expectation": "positive",
                "absolute_action_evaluated": 6,
                "absolute_action_hit_count": 2,
                "absolute_action_hit_rate": 2 / 6,
                "avg_excess": 0.10,
                "positive_excess_rate": 1.0,
            },
        }
    }
    verdict = _history_evidence_verdict(summary, _policy()["action_rules"])
    assert verdict["verdict"] == "preliminary_conflict"
    assert verdict["blocks_add"] is True

def test_avoid_action_is_supported_by_non_positive_absolute_returns():
    summary = {
        "horizons": {
            "1": {
                "evaluated": 5,
                "avg_ret": -0.02,
                "absolute_action_expectation": "non_positive",
                "absolute_action_evaluated": 5,
                "absolute_action_hit_count": 4,
                "absolute_action_hit_rate": 0.8,
            },
        },
    }
    verdict = _history_evidence_verdict(summary, _policy()["action_rules"])
    assert verdict["verdict"] == "preliminary_support"
    assert verdict["blocks_add"] is False

def test_close_review_risk_trigger_overrides_add_and_marks_execution_unconfirmed():
    task = _task("600001", "watch", "up")
    snapshot = {"target_trade_dates": ["20260713"], "tasks": [task]}
    holdings = {"600001": {"name": "A", "shares": 1000, "cost": 12.0}}
    capacity = _capacity()
    capacity["holdings"] = {"600001": capacity["holdings"]["600001"]}
    facts = {"600001": [
        {
            "code": "600001", "task_id": "task_600001",
            "trigger_type": "reclaim_confirm", "severity": "medium",
            "trade_time": "09:31:00", "price": 10.2, "occurrences": 1,
        },
        {
            "code": "600001", "task_id": "task_600001",
            "trigger_type": "breakdown_confirm", "severity": "high",
            "trade_time": "10:15:00", "price": 8.0, "occurrences": 2,
        },
    ]}

    plan = build_daily_action_plan(
        snapshot, holdings, capacity, _policy(),
        dline_trigger_facts=facts, phase="close_review",
    )
    row = plan["holdings"][0]
    assert plan["phase"] == "close_review"
    assert row["action"] == "风险条件已触发，减仓执行待确认"
    assert row["conditional_add"] is None
    assert row["risk_reduce"]["triggered"] is True
    assert row["risk_reduce"]["estimated_shares"] == 600
    assert row["risk_reduce"]["estimated_amount"] == 4800.0
    markdown = render_daily_action_markdown(plan)
    assert "# 20260713 收盘操作复盘" in markdown
    assert "10:15:00触发破位确认，触发价8.00，风险级别高" in markdown
    assert "同一任务重复记录2次，本报告按首次触发" in markdown
    assert "风险结果: 条件已触发" in markdown
    assert "实际成交待确认" in markdown


def test_close_review_marks_untriggered_conditions_without_inventing_execution():
    task = _task("600001", "watch", "up")
    snapshot = {"target_trade_dates": ["20260713"], "tasks": [task]}
    holdings = {"600001": {"name": "A", "shares": 1000, "cost": 12.0}}
    capacity = _capacity()
    capacity["holdings"] = {"600001": capacity["holdings"]["600001"]}

    plan = build_daily_action_plan(
        snapshot, holdings, capacity, _policy(),
        dline_trigger_facts={}, phase="close_review",
    )
    row = plan["holdings"][0]
    assert row["action"] == "D线观察证据不足，不操作"
    assert row["conditional_add"]["triggered"] is None
    assert row["conditional_add"]["trigger_record_status"] == "coverage_missing"
    assert row["risk_reduce"]["triggered"] is None
    assert row["risk_reduce"]["trigger_record_status"] == "coverage_missing"
    assert "dline.coverage" in row["pending"]
    markdown = render_daily_action_markdown(plan)
    assert "D线观察: 无与当前任务匹配的有效观察记录" in markdown
    assert "加仓结果: D线观察记录不足" in markdown
    assert "风险结果: D线观察记录不足" in markdown
    assert "已经买入" not in markdown
    assert "已经减仓" not in markdown

def test_premarket_plan_ignores_same_day_dline_trigger_facts():
    task = _task("600001", "watch", "up")
    snapshot = {"target_trade_dates": ["20260713"], "tasks": [task]}
    holdings = {"600001": {"name": "A", "shares": 1000, "cost": 12.0}}
    capacity = _capacity()
    capacity["holdings"] = {"600001": capacity["holdings"]["600001"]}
    facts = {"600001": [{
        "code": "600001", "task_id": "task_600001",
        "trigger_type": "breakdown_confirm", "severity": "high",
        "trade_time": "10:15:00", "price": 8.0,
    }]}

    plan = build_daily_action_plan(
        snapshot, holdings, capacity, _policy(), dline_trigger_facts=facts,
    )
    row = plan["holdings"][0]
    assert plan["phase"] == "pre_market"
    assert row["risk_reduce"]["triggered"] is None
    assert "执行待确认" not in row["action"]

def test_close_review_uses_verified_observation_coverage_for_not_recorded():
    task = _task("600001", "watch", "up")
    snapshot = {"target_trade_dates": ["20260713"], "tasks": [task]}
    holdings = {"600001": {"name": "A", "shares": 1000, "cost": 12.0}}
    capacity = _capacity()
    capacity["holdings"] = {"600001": capacity["holdings"]["600001"]}
    coverage = {
        "status": "available", "target_trade_date": "20260713",
        "by_code": {"600001": [{
            "task_id": "task_600001", "code": "600001",
            "observation_count": 12,
            "first_quote_trade_time": "09:35:00",
            "last_quote_trade_time": "14:58:00",
            "last_price": 10.2,
        }]},
    }

    plan = build_daily_action_plan(
        snapshot, holdings, capacity, _policy(), dline_trigger_facts={},
        dline_coverage=coverage, phase="close_review",
    )
    row = plan["holdings"][0]
    assert row["action"] == "D线已观察，未记录加仓触发，不执行系统加仓"
    assert row["conditional_add"]["trigger_record_status"] == "not_recorded"
    assert row["risk_reduce"]["trigger_record_status"] == "not_recorded"
    assert row["pending"] == []
    markdown = render_daily_action_markdown(plan)
    assert "D线观察: 有效观察12次，首笔09:35:00，末笔14:58:00，最后价10.20" in markdown
    assert "加仓结果: D线未记录到" in markdown
    assert "风险结果: D线未记录到" in markdown


def test_t_now_is_exposed_without_changing_decision_horizons():
    summary = {
        "latest_horizon": "7",
        "horizons": {
            "1": {"evaluated": 4, "avg_ret": -0.01, "positive_ret_rate": 0.25},
            "7": {"evaluated": 1, "avg_ret": -0.08, "positive_ret_rate": 0.0},
        },
    }
    verdict = _history_evidence_verdict(summary, _policy()["action_rules"])
    assert verdict["latest_horizon"] == "7"
    assert verdict["horizon_verdicts"]["7"]["avg_ret"] == -0.08
    assert verdict["blocks_add"] is False
