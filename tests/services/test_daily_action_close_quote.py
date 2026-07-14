# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path

from vaxstock.services.daily_action import refresh_daily_action, validate_close_quotes


def _task():
    return {
        "task_id": "task_600001",
        "code": "600001",
        "name": "A",
        "baseline_trade_date": "20260710",
        "target_trade_date": "20260713",
        "evidence_pack": {
            "baseline_trade_date": "20260710",
            "A_eod": {
                "price": 9.5,
                "metrics": {"ma5": 10.0, "ma20": 10.0},
                "market": {"market_regime": "value", "macro_regime": "neutral"},
            },
            "C_prediction": {"prediction": {"action": "watch", "direction": "up"}},
        },
        "observation": {"trigger_blueprints": []},
    }


def _policy():
    return {
        "policy_version": "test_v1",
        "position_units_pct": {"half_unit": 2.5, "unit": 5.0},
        "position_caps_pct": {"ordinary": 10.0, "core": 20.0, "strategic_core": 30.0},
        "stock_tiers": {"600001": "ordinary"},
        "max_strategic_core_count": 1,
        "trade_rules": {"buy_lot_size": 100},
        "action_rules": {
            "conditional_add_unit": "half_unit",
            "risk_reduce_unit": "unit",
            "c_actions_eligible_for_conditional_add": ["watch"],
            "positive_trigger_types": ["reclaim_confirm"],
            "risk_trigger_types": ["breakdown_confirm"],
        },
    }


def _portfolio():
    return {
        "as_of_trade_date": "20260713",
        "captured_at": "2026-07-13T10:04:00+08:00",
        "source": "broker_screenshot_user_confirmed",
        "total_assets": 15000.0,
        "market_value": 10000.0,
        "available_cash": 5000.0,
        "position_pct": 66.67,
        "reference_prices": {"600001": 10.0},
    }


def _refresh(root: Path, quote):
    tasks = root / "tasks.json"
    tasks.write_text(json.dumps({
        "target_trade_dates": ["20260713"], "tasks": [_task()],
    }), encoding="utf-8")
    return refresh_daily_action(
        tasks_path=tasks, output_dir=root / "strategy",
        target_trade_date="20260713", phase="close_review",
        holdings_data={"600001": {"name": "A", "shares": 1000, "cost": 12.0}},
        portfolio_state=_portfolio(), policy_data=_policy(),
        reference_quotes={"600001": quote},
        forecasts_path=root / "forecasts.jsonl",
        observation_status_path=root / "coverage.json",
    )


def test_close_review_uses_same_day_quote_instead_of_portfolio_snapshot_price():
    with tempfile.TemporaryDirectory() as tmp:
        result = _refresh(Path(tmp), {
            "price": 8.0, "trade_date": "2026-07-13",
            "trade_time": "15:34:59", "source": "sina",
        })
    row = result["plan"]["holdings"][0]
    account = result["plan"]["account"]
    assert row["reference_price"] == 8.0
    assert row["pnl_pct"] == -33.3333
    assert row["pnl_amount_estimate"] == -4000.0
    assert account["as_of_trade_date"] == "20260713"
    assert account["source"] == "close_quote_revalued_from_confirmed_cash_and_holdings"
    assert account["price_source"] == "stock-api /quote (sina)"
    assert "收盘行情: 日期 20260713；来源 stock-api /quote (sina)" in result["markdown"]


def test_close_review_rejects_stale_quote_without_falling_back_to_snapshot_price():
    with tempfile.TemporaryDirectory() as tmp:
        result = _refresh(Path(tmp), {
            "price": 8.0, "trade_date": "2026-07-10",
            "trade_time": "15:00:00", "source": "sina",
        })
    row = result["plan"]["holdings"][0]
    assert row["reference_price"] is None
    assert row["pnl_pct"] is None
    assert row["pnl_amount_estimate"] is None
    assert "reference_price" in row["pending"]
    assert "收盘行情: 日期 待确认；来源 待确认" in result["markdown"]


def test_close_quote_validator_requires_target_date_source_and_positive_price():
    result = validate_close_quotes({
        "600001": {"price": 8.0, "trade_date": "2026-07-13", "source": "sina"},
        "600002": {"price": 9.0, "trade_date": "2026-07-12", "source": "sina"},
        "600003": {"price": 0, "trade_date": "2026-07-13", "source": "sina"},
        "600004": {"price": 10.0, "trade_date": "2026-07-13", "source": "unknown"},
    }, "20260713", ["600001", "600002", "600003", "600004", "600005"])
    assert result["prices"] == {"600001": 8.0}
    assert result["complete"] is False
    assert result["pending"] == [
        "close_quote.600002.trade_date_mismatch",
        "close_quote.600003.price_invalid",
        "close_quote.600004.source_invalid",
        "close_quote.600005.missing",
    ]
