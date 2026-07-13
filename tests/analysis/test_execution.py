# -*- coding: utf-8 -*-

from vaxstock.analysis.execution import (
    build_holdings_projection, build_portfolio_projection,
    reconcile_execution, validate_execution_confirmation,
)


def _prior_holdings():
    return {
        "600001": {"name": "A", "shares": 1000, "cost": 11.0, "concepts": ["x"]},
        "600002": {"name": "B", "shares": 500, "cost": 19.0},
        "600003": {"name": "C", "shares": 300, "cost": 30.0},
    }


def _confirmation():
    return {
        "schema_version": 1,
        "confirmation_id": "confirm-20260713-001",
        "trade_date": "20260713",
        "confirmed_at": "2026-07-13T15:30:00+08:00",
        "source": "broker_screenshot_user_confirmed",
        "user_confirmed": True,
        "no_trade_confirmed": False,
        "trades": [
            {
                "execution_id": "broker-fill-001", "code": "600001", "name": "A",
                "side": "sell", "shares": 100, "executed_price": 9.9,
                "executed_at": "2026-07-13T10:00:00+08:00", "status": "filled",
            },
            {
                "execution_id": "broker-fill-002", "code": "600002", "name": "B",
                "side": "buy", "shares": 100, "executed_price": 20.2,
                "executed_at": "2026-07-13T10:05:00+08:00", "status": "filled",
            },
        ],
        "post_trade_snapshot": {
            "captured_at": "2026-07-13T15:20:00+08:00",
            "holdings_snapshot_complete": True,
            "total_assets": 40000.0,
            "market_value": 30000.0,
            "available_cash": 10000.0,
            "position_pct": 75.0,
            "reference_prices": {"600001": 10.0, "600002": 20.0, "600003": 30.0},
            "holdings": {
                "600001": {"name": "A", "shares": 900, "available_shares": 900, "cost": 11.0},
                "600002": {"name": "B", "shares": 600, "available_shares": 500, "cost": 19.2},
                "600003": {"name": "C", "shares": 300, "available_shares": 300, "cost": 30.0},
            },
        },
    }


def _plan():
    return {
        "background": {"target_trade_date": "20260713"},
        "holdings": [
            {
                "code": "600001", "name": "A", "conditional_add": None,
                "risk_reduce": {
                    "trigger_record_status": "recorded", "estimated_shares": 100,
                    "trigger_fact": {"price": 10.0},
                },
            },
            {
                "code": "600002", "name": "B", "risk_reduce": None,
                "conditional_add": {
                    "trigger_record_status": "recorded", "estimated_shares": 200,
                    "trigger_fact": {"price": 20.0},
                },
            },
            {
                "code": "600003", "name": "C", "conditional_add": None,
                "risk_reduce": {
                    "trigger_record_status": "recorded", "estimated_shares": 100,
                    "trigger_fact": {"price": 30.0},
                },
            },
        ],
    }


def test_confirmation_validation_projection_and_reconciliation_are_mechanical():
    result = validate_execution_confirmation(_confirmation(), _prior_holdings())
    assert result["valid"] is True
    assert result["errors"] == []
    confirmation = result["confirmation"]
    assert all(row["status"] == "consistent" for row in confirmation["share_consistency"])

    holdings = build_holdings_projection({"holdings": _prior_holdings()}, confirmation)
    portfolio = build_portfolio_projection({"schema_version": 1}, confirmation)
    assert holdings["holdings"]["600001"]["shares"] == 900
    assert holdings["holdings"]["600001"]["concepts"] == ["x"]
    assert holdings["holdings"]["600002"]["cost"] == 19.2
    assert portfolio["available_cash"] == 10000.0
    assert portfolio["last_execution_confirmation_id"] == "confirm-20260713-001"

    review = reconcile_execution(_plan(), confirmation)
    rows = {row["code"]: row for row in review["rows"]}
    assert rows["600001"]["status"] == "executed"
    assert rows["600001"]["adverse_slippage_pct"] == 1.0
    assert rows["600002"]["status"] == "partial_execution"
    assert rows["600002"]["adverse_slippage_pct"] == 1.0
    assert rows["600003"]["status"] == "not_executed"


def test_trade_requires_complete_snapshot_and_explicit_user_confirmation():
    data = _confirmation()
    data["user_confirmed"] = False
    data.pop("post_trade_snapshot")
    result = validate_execution_confirmation(data, _prior_holdings())
    assert result["valid"] is False
    assert "user_confirmed.must_be_true" in result["errors"]
    assert "post_trade_snapshot.required_when_trades_exist" in result["errors"]


def test_share_mismatch_requires_explicit_snapshot_replacement_confirmation():
    data = _confirmation()
    data["post_trade_snapshot"]["holdings"]["600001"]["shares"] = 800
    data["post_trade_snapshot"]["holdings"]["600001"]["available_shares"] = 800
    data["post_trade_snapshot"]["market_value"] = 29000.0
    data["post_trade_snapshot"]["total_assets"] = 39000.0
    data["post_trade_snapshot"]["position_pct"] = round(29000 / 39000 * 100, 4)
    blocked = validate_execution_confirmation(data, _prior_holdings())
    assert blocked["valid"] is False
    assert "post_trade_snapshot.share_mismatch_requires_replace_prior_state_confirmed" in blocked["errors"]

    data["replace_prior_state_confirmed"] = True
    allowed = validate_execution_confirmation(data, _prior_holdings())
    assert allowed["valid"] is True
    assert allowed["warnings"] == [
        "prior_holdings_replaced_by_user_confirmed_complete_snapshot"
    ]


def test_actual_forbidden_board_trade_is_recorded_as_policy_violation():
    confirmation = {
        "confirmation_id": "confirm-20260713-688001",
        "trade_date": "20260713",
        "trades": [{
            "execution_id": "broker-fill-688001", "code": "688001", "name": "X",
            "side": "buy", "shares": 100, "executed_price": 10.0,
            "executed_at": "2026-07-13T10:00:00+08:00", "status": "filled",
        }],
    }
    review = reconcile_execution({}, confirmation)
    assert review["rows"][0]["status"] == "unplanned_execution"
    assert review["rows"][0]["policy_violation"] == "forbidden_board_execution"


def test_new_buy_is_reconciled_from_zero_prior_shares():
    data = _confirmation()
    data["trades"].append({
        "execution_id": "broker-fill-004", "code": "600004", "name": "D",
        "side": "buy", "shares": 100, "executed_price": 10.0,
        "executed_at": "2026-07-13T10:10:00+08:00", "status": "filled",
    })
    snapshot = data["post_trade_snapshot"]
    snapshot["holdings"]["600004"] = {
        "name": "D", "shares": 100, "available_shares": 0, "cost": 10.0,
    }
    snapshot["reference_prices"]["600004"] = 10.0
    snapshot["market_value"] = 31000.0
    snapshot["total_assets"] = 41000.0
    snapshot["position_pct"] = round(31000 / 41000 * 100, 4)
    result = validate_execution_confirmation(data, _prior_holdings())
    assert result["valid"] is True
    by_code = {row["code"]: row for row in result["confirmation"]["share_consistency"]}
    assert by_code["600004"]["prior_shares"] == 0
    assert by_code["600004"]["status"] == "consistent"


def test_snapshot_capture_date_must_match_execution_trade_date():
    data = _confirmation()
    data["post_trade_snapshot"]["captured_at"] = "2026-07-14T09:00:00+08:00"
    result = validate_execution_confirmation(data, _prior_holdings())
    assert result["valid"] is False
    assert "post_trade_snapshot.captured_at.trade_date_mismatch" in result["errors"]