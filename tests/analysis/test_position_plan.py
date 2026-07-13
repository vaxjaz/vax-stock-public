# -*- coding: utf-8 -*-

import json
from pathlib import Path

from vaxstock import config
from vaxstock.analysis.position_plan import build_position_capacity


def _policy():
    return json.loads((config.CONFIG_DIR / "strategy_policy.json").read_text(encoding="utf-8"))


def _state():
    return {
        "as_of_trade_date": "20260713",
        "captured_at": "2026-07-13T09:30:00+08:00",
        "source": "broker_screenshot_user_confirmed",
        "total_assets": 100000.0,
        "market_value": 70000.0,
        "available_cash": 30000.0,
        "position_pct": 70.0,
        "reference_prices": {
            "601138": 20.0,
            "002475": 30.0,
            "600276": 20.0
        }
    }


def _holdings():
    return {
        "601138": {"name": "工业富联", "shares": 1400, "cost": 18.0},
        "002475": {"name": "立讯精密", "shares": 400, "cost": 25.0},
        "600276": {"name": "恒瑞医药", "shares": 600, "cost": 18.0}
    }


def test_real_snapshot_units_tiers_caps_and_lot_rounding():
    result = build_position_capacity(_state(), _holdings(), _policy())
    assert result["available"] is True
    assert result["account"]["unit_amounts"] == {"half_unit": 2500.0, "unit": 5000.0}

    fii = result["holdings"]["601138"]
    assert fii["tier"] == "strategic_core"
    assert fii["cap_pct"] == 30.0
    assert fii["current_weight_pct"] == 28.0
    assert fii["max_add_amount"] == 2000.0
    assert fii["unit_capacity"]["half_unit"]["estimated_shares"] == 100
    assert fii["unit_capacity"]["half_unit"]["status"] == "clipped_by_position_cap_or_cash"

    luxshare = result["holdings"]["002475"]
    assert luxshare["tier"] == "ordinary"
    assert luxshare["over_cap"] is True
    assert luxshare["max_add_amount"] == 0.0

    hengrui = result["holdings"]["600276"]
    assert hengrui["tier"] == "core"
    assert hengrui["cap_pct"] == 20.0
    assert hengrui["unit_capacity"]["half_unit"]["estimated_shares"] == 100
    assert hengrui["unit_capacity"]["half_unit"]["estimated_amount"] == 2000.0


def test_missing_account_data_never_fabricates_amount_or_shares():
    result = build_position_capacity({}, _holdings(), _policy(), reference_prices={"601138": 20.0})
    assert result["available"] is False
    assert "portfolio.total_assets" in result["pending"]
    assert result["account"]["unit_amounts"]["half_unit"] is None
    assert result["holdings"]["601138"]["available"] is False
    assert "unit_capacity" not in result["holdings"]["601138"]


def test_unclassified_holding_stays_pending_instead_of_defaulting_to_ordinary():
    holdings = {"600000": {"name": "新持仓", "shares": 100}}
    state = _state()
    state["reference_prices"] = {"600000": 10.0}
    result = build_position_capacity(state, holdings, _policy())
    row = result["holdings"]["600000"]
    assert result["available"] is False
    assert row["available"] is False
    assert row["tier"] is None
    assert "policy.stock_tier" in row["pending"]


def test_config_loaders_are_local_and_honest(tmp_path: Path):
    missing = tmp_path / "missing.json"
    assert config.load_portfolio_state(missing) == {}
    assert config.load_strategy_policy(missing) == {}

    state_path = tmp_path / "portfolio.json"
    state_path.write_text('{"total_assets": 123.45}', encoding="utf-8")
    assert config.load_portfolio_state(state_path) == {"total_assets": 123.45}


def test_invalid_policy_percent_order_disables_capacity():
    policy = _policy()
    policy["position_caps_pct"] = {"ordinary": 30, "core": 20, "strategic_core": 10}
    result = build_position_capacity(_state(), _holdings(), policy)
    assert result["available"] is False
    assert "policy.position_caps_pct.order_invalid" in result["pending"]

def test_eod_revaluation_uses_confirmed_cash_and_requires_all_prices():
    from vaxstock.analysis.position_plan import revalue_portfolio_state

    state = {"available_cash": 50.0, "captured_at": "snapshot"}
    holdings = {"600001": {"shares": 10}, "600002": {"shares": 20}}
    out = revalue_portfolio_state(state, holdings, {"600001": 5.0, "600002": 2.5}, as_of_trade_date="20260713")
    assert out["market_value"] == 100.0
    assert out["total_assets"] == 150.0
    assert out["position_pct"] == 66.67
    assert out["revaluation_pending"] == []

    missing = revalue_portfolio_state(state, holdings, {"600001": 5.0}, as_of_trade_date="20260713")
    assert missing["total_assets"] is None
    assert "reference_price.600002" in missing["revaluation_pending"]