# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path

from vaxstock.services.strategy_validity_audit import (
    build_strategy_validity_audit,
    render_strategy_validity_audit,
    run_strategy_validity_audit,
)


def _policy():
    return {
        "action_rules": {
            "history_evidence": {
                "minimum_preliminary_samples": 5,
                "minimum_stable_samples": 20,
                "support_min_absolute_action_hit_rate": 0.6,
                "conflict_max_absolute_action_hit_rate": 0.4,
            }
        }
    }


def _prediction(pid, mode, target, generated, action="watch", direction="up"):
    return {
        "prediction_id": pid,
        "generation_mode": mode,
        "baseline_trade_date": "20260712",
        "target_trade_date": target,
        "generated_at": generated,
        "code": "601138",
        "prediction": {"action": action, "direction": direction, "horizon": "T+1"},
    }


def _prediction_result(pid, horizon, ret, target="20260713", mode="live"):
    return {
        "prediction_id": pid,
        "generation_mode": mode,
        "target_trade_date": target,
        "code": "601138",
        "horizon": str(horizon),
        "actual": {"trade_date": target, "ret": ret, "source": "factor_results"},
        "evaluation": {"path_absolute_action_alignment": ret > 0},
    }


def test_c_horizons_are_path_cells_not_independent_prediction_samples():
    report = build_strategy_validity_audit(
        as_of_trade_date="20260713",
        predictions=[
            _prediction("live-1", "live", "20260713", "2026-07-13T05:00:00"),
            _prediction("replay-1", "replay", "20260713", "2026-07-15T10:00:00"),
        ],
        prediction_results=[
            _prediction_result("live-1", 1, 0.02),
            _prediction_result("live-1", 5, -0.01),
            _prediction_result("replay-1", 1, 0.03, mode="replay"),
        ],
        forecast_results=[],
        forecast_evolution=[],
        strategy_policy=_policy(),
    )
    c_line = report["c_line"]
    assert c_line["identity_and_counting"]["unique_predictions"] == 2
    assert c_line["identity_and_counting"]["generation_modes"] == {
        "live": 1, "replay": 1,
    }
    assert c_line["by_mode_and_fixed_horizon"]["live_preopen:T+1"]["prediction_samples"] == 1
    assert c_line["by_mode_and_fixed_horizon"]["live_preopen:T+5"]["prediction_samples"] == 1
    assert c_line["t_plus_now_by_mode"]["live_preopen"]["prediction_samples"] == 1
    assert c_line["return_contract"]["operation_price_executable"] is False
    assert report["mail_policy"]["allow_c_operation_profit_claim"] is False


def test_live_prediction_after_open_is_exposed_not_counted_as_preopen():
    report = build_strategy_validity_audit(
        as_of_trade_date="20260713",
        predictions=[
            _prediction("late", "live", "20260713", "2026-07-13T09:35:00"),
        ],
        prediction_results=[_prediction_result("late", 1, 0.02)],
        forecast_results=[],
        forecast_evolution=[],
        strategy_policy=_policy(),
    )
    quality = report["c_line"]["identity_and_counting"]
    assert quality["live_generated_before_open"] == 0
    assert quality["live_generated_at_or_after_open"] == 1
    assert report["gates"][0]["status"] == "fail"


def test_unmapped_c_action_is_explicitly_unscored():
    report = build_strategy_validity_audit(
        as_of_trade_date="20260713",
        predictions=[_prediction(
            "probe", "live", "20260713", "2026-07-13T05:00:00",
            action="panic_rebound_probe", direction="up",
        )],
        prediction_results=[_prediction_result("probe", 1, 0.04)],
        forecast_results=[], forecast_evolution=[], strategy_policy=_policy(),
    )
    stats = report["c_line"]["live_t1_by_action"]["panic_rebound_probe"]
    assert stats["prediction_samples"] == 1
    assert stats["scored_cells"] == 0
    assert report["c_line"]["unscored_live_t1_actions"] == {
        "panic_rebound_probe": 1,
    }
    assert "动作含义未映射，不能评分" in render_strategy_validity_audit(report)


def test_dline_same_day_events_are_one_independent_date_and_timing_is_gross():
    evolution = []
    for index, (trigger_price, close_price) in enumerate(((10.0, 9.0), (20.0, 19.0))):
        evolution.append({
            "task_id": f"task-{index}",
            "trigger_type": "breakdown_confirm",
            "target_trade_date": "20260713",
            "code": f"60000{index}",
            "trigger": {"price": trigger_price},
            "checkpoints": {
                "15m": {"price": trigger_price - 0.2},
                "30m": {"price": trigger_price - 0.4},
                "close": {"price": close_price},
            },
        })
    report = build_strategy_validity_audit(
        as_of_trade_date="20260713",
        predictions=[], prediction_results=[], forecast_results=[],
        forecast_evolution=evolution,
        strategy_policy=_policy(),
    )
    d_line = report["d_line"]
    assert d_line["identity_and_counting"]["unique_trigger_events"] == 2
    assert d_line["identity_and_counting"]["triggered_stock_days"] == 2
    assert d_line["identity_and_counting"]["independent_target_dates"] == 1
    immediate = d_line["gross_timing_evidence"]["breakdown_confirm:immediate"]
    assert immediate["samples"] == 2
    assert immediate["positive_gross_benefit_rate"] == 1.0
    assert immediate["transaction_cost_included"] is False
    assert immediate["verdict"] == "evidence_insufficient"


def test_run_is_idempotent_for_same_finalized_inputs():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        paths = {name: root / f"{name}.jsonl" for name in (
            "predictions", "prediction_results", "forecast_results", "forecast_evolution",
        )}
        paths["predictions"].write_text(
            json.dumps(_prediction(
                "live-1", "live", "20260713", "2026-07-13T05:00:00",
            ), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        paths["prediction_results"].write_text(
            json.dumps(_prediction_result("live-1", 1, 0.02), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        paths["forecast_results"].write_text("", encoding="utf-8")
        paths["forecast_evolution"].write_text("", encoding="utf-8")
        kwargs = {
            "as_of_trade_date": "20260713",
            "predictions_path": paths["predictions"],
            "prediction_results_path": paths["prediction_results"],
            "forecast_results_path": paths["forecast_results"],
            "forecast_evolution_path": paths["forecast_evolution"],
            "output_dir": root / "out",
            "strategy_policy": _policy(),
        }
        first = run_strategy_validity_audit(**kwargs)
        content = Path(first["dated_json_path"]).read_text(encoding="utf-8")
        second = run_strategy_validity_audit(**kwargs)
        assert Path(second["dated_json_path"]).read_text(encoding="utf-8") == content
        markdown = Path(second["dated_md_path"]).read_text(encoding="utf-8")
        assert "T+1、T+5、T+now是同一次预测" in markdown


def test_render_states_strategy_is_not_proven():
    report = build_strategy_validity_audit(
        as_of_trade_date="20260713",
        predictions=[], prediction_results=[], forecast_results=[],
        forecast_evolution=[], strategy_policy=_policy(),
    )
    markdown = render_strategy_validity_audit(report)
    assert "尚不能证明整套策略能稳定提高实际交易收益" in markdown
    assert "未经审计通过的统计不得修改动作" in markdown
