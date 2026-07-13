# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path

from vaxstock.analysis.execution import validate_execution_confirmation
from vaxstock.services import execution_confirmation as execution_service
from vaxstock.services.execution_confirmation import (
    _canonical_hash, apply_execution_confirmation,
)


def _documents(root: Path):
    holdings = root / "holdings.json"
    portfolio = root / "portfolio_state.json"
    strategy = root / "strategy"
    strategy.mkdir()
    holdings.write_text(json.dumps({
        "holdings": {
            "600001": {"name": "A", "shares": 1000, "cost": 11.0, "concepts": ["x"]},
            "600002": {"name": "B", "shares": 500, "cost": 19.0},
            "600003": {"name": "C", "shares": 300, "cost": 30.0},
        }
    }), encoding="utf-8")
    portfolio.write_text(json.dumps({
        "schema_version": 1, "as_of_trade_date": "20260710",
        "total_assets": 40000.0, "market_value": 30000.0,
        "available_cash": 10000.0, "position_pct": 75.0,
    }), encoding="utf-8")
    plan = strategy / "close_review_20260713.json"
    plan.write_text(json.dumps({
        "background": {"target_trade_date": "20260713"},
        "holdings": [
            {"code": "600001", "name": "A", "conditional_add": None,
             "risk_reduce": {"trigger_record_status": "recorded", "estimated_shares": 100,
                             "trigger_fact": {"price": 10.0}}},
            {"code": "600002", "name": "B", "risk_reduce": None,
             "conditional_add": {"trigger_record_status": "recorded", "estimated_shares": 200,
                                 "trigger_fact": {"price": 20.0}}},
            {"code": "600003", "name": "C", "conditional_add": None,
             "risk_reduce": {"trigger_record_status": "recorded", "estimated_shares": 100,
                             "trigger_fact": {"price": 30.0}}},
        ],
    }), encoding="utf-8")
    return holdings, portfolio, strategy, plan


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
            {"execution_id": "broker-fill-001", "code": "600001", "name": "A",
             "side": "sell", "shares": 100, "executed_price": 9.9,
             "executed_at": "2026-07-13T10:00:00+08:00", "status": "filled"},
            {"execution_id": "broker-fill-002", "code": "600002", "name": "B",
             "side": "buy", "shares": 100, "executed_price": 20.2,
             "executed_at": "2026-07-13T10:05:00+08:00", "status": "filled"},
        ],
        "post_trade_snapshot": {
            "captured_at": "2026-07-13T15:20:00+08:00",
            "holdings_snapshot_complete": True,
            "total_assets": 40000.0, "market_value": 30000.0,
            "available_cash": 10000.0, "position_pct": 75.0,
            "reference_prices": {"600001": 10.0, "600002": 20.0, "600003": 30.0},
            "holdings": {
                "600001": {"name": "A", "shares": 900, "available_shares": 900, "cost": 11.0},
                "600002": {"name": "B", "shares": 600, "available_shares": 500, "cost": 19.2},
                "600003": {"name": "C", "shares": 300, "available_shares": 300, "cost": 30.0},
            },
        },
    }


def _apply(root: Path, data, *, dry_run=False):
    holdings, portfolio, strategy, plan = _documents(root)
    records = strategy / "execution_records.jsonl"
    result = apply_execution_confirmation(
        data, records_path=records, holdings_path=holdings,
        portfolio_path=portfolio, strategy_dir=strategy,
        plan_path=plan, dry_run=dry_run,
    )
    return result, holdings, portfolio, strategy, records, plan


def test_apply_is_idempotent_and_updates_both_projections_from_broker_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result, holdings, portfolio, strategy, records, plan = _apply(root, _confirmation())
        assert result["status"] == "written"
        assert result["journal_status"] == "recorded"
        assert result["projection_status"] == "applied"
        assert len(records.read_text(encoding="utf-8").splitlines()) == 1
        holdings_data = json.loads(holdings.read_text(encoding="utf-8"))
        portfolio_data = json.loads(portfolio.read_text(encoding="utf-8"))
        assert holdings_data["holdings"]["600001"]["shares"] == 900
        assert holdings_data["holdings"]["600001"]["concepts"] == ["x"]
        assert holdings_data["holdings"]["600002"]["cost"] == 19.2
        assert portfolio_data["last_execution_confirmation_id"] == "confirm-20260713-001"
        review = json.loads((strategy / "execution_review_20260713.json").read_text(encoding="utf-8"))
        by_code = {row["code"]: row for row in review["rows"]}
        assert by_code["600001"]["status"] == "executed"
        assert by_code["600002"]["status"] == "partial_execution"
        assert by_code["600003"]["status"] == "not_executed"
        assert "部分执行" in result["markdown"]
        assert "条件触发但未执行" in result["markdown"]

        second = apply_execution_confirmation(
            _confirmation(), records_path=records, holdings_path=holdings,
            portfolio_path=portfolio, strategy_dir=strategy, plan_path=plan,
        )
        assert second["status"] == "written"
        assert second["journal_status"] == "already_recorded"
        assert second["projection_status"] == "already_applied"
        assert len(records.read_text(encoding="utf-8").splitlines()) == 1


def test_same_confirmation_id_with_changed_payload_is_blocked_without_writes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result, holdings, portfolio, strategy, records, plan = _apply(root, _confirmation())
        before_holdings = holdings.read_bytes()
        changed = _confirmation()
        changed["trades"][0]["executed_price"] = 9.8
        conflict = apply_execution_confirmation(
            changed, records_path=records, holdings_path=holdings,
            portfolio_path=portfolio, strategy_dir=strategy, plan_path=plan,
        )
        assert result["status"] == "written"
        assert conflict["status"] == "confirmation_id_conflict"
        assert len(records.read_text(encoding="utf-8").splitlines()) == 1
        assert holdings.read_bytes() == before_holdings


def test_dry_run_validates_and_reconciles_without_persistent_writes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result, holdings, portfolio, strategy, records, plan = _apply(
            root, _confirmation(), dry_run=True,
        )
        assert result["status"] == "dry_run_valid"
        assert result["projection_status"] == "would_apply"
        assert not records.exists()
        assert not (strategy / "execution_review_20260713.json").exists()
        assert json.loads(holdings.read_text(encoding="utf-8"))["holdings"]["600001"]["shares"] == 1000


def test_existing_journal_event_can_resume_missing_projections_after_interruption():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        holdings, portfolio, strategy, plan = _documents(root)
        records = strategy / "execution_records.jsonl"
        raw = _confirmation()
        prior = json.loads(holdings.read_text(encoding="utf-8"))["holdings"]
        validation = validate_execution_confirmation(raw, prior)
        assert validation["valid"] is True
        records.write_text(json.dumps({
            "schema_version": 1,
            "confirmation_id": raw["confirmation_id"],
            "trade_date": raw["trade_date"],
            "recorded_at": "2026-07-13T15:31:00+08:00",
            "input_sha256": _canonical_hash(raw),
            "warnings": [],
            "confirmation": validation["confirmation"],
        }) + "\n", encoding="utf-8")

        resumed = apply_execution_confirmation(
            raw, records_path=records, holdings_path=holdings,
            portfolio_path=portfolio, strategy_dir=strategy, plan_path=plan,
        )
        assert resumed["journal_status"] == "already_recorded"
        assert resumed["projection_status"] == "applied"
        assert json.loads(holdings.read_text(encoding="utf-8"))["holdings"]["600001"]["shares"] == 900
        assert len(records.read_text(encoding="utf-8").splitlines()) == 1

def test_same_broker_execution_id_cannot_be_recorded_under_new_confirmation_id():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result, holdings, portfolio, strategy, records, plan = _apply(root, _confirmation())
        duplicate = _confirmation()
        duplicate["confirmation_id"] = "confirm-20260713-002"
        conflict = apply_execution_confirmation(
            duplicate, records_path=records, holdings_path=holdings,
            portfolio_path=portfolio, strategy_dir=strategy, plan_path=plan,
        )
        assert result["status"] == "written"
        assert conflict["status"] == "execution_id_conflict"
        assert len(records.read_text(encoding="utf-8").splitlines()) == 1


def test_no_trade_confirmation_is_recorded_without_changing_portfolio():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        holdings, portfolio, strategy, plan = _documents(root)
        records = strategy / "execution_records.jsonl"
        before_holdings = holdings.read_bytes()
        before_portfolio = portfolio.read_bytes()
        no_trade = {
            "schema_version": 1,
            "confirmation_id": "confirm-20260713-no-trade",
            "trade_date": "20260713",
            "confirmed_at": "2026-07-13T15:30:00+08:00",
            "source": "broker_screenshot_user_confirmed",
            "user_confirmed": True,
            "no_trade_confirmed": True,
            "trades": [],
        }
        result = apply_execution_confirmation(
            no_trade, records_path=records, holdings_path=holdings,
            portfolio_path=portfolio, strategy_dir=strategy, plan_path=plan,
        )
        assert result["status"] == "written"
        assert result["projection_status"] == "not_required"
        assert holdings.read_bytes() == before_holdings
        assert portfolio.read_bytes() == before_portfolio
        review = {row["code"]: row for row in result["review"]["rows"]}
        assert review["600001"]["status"] == "not_executed"
        assert review["600002"]["status"] == "not_executed"


def test_default_holdings_projection_preserves_tracked_baseline():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        baseline, portfolio, strategy, plan = _documents(root)
        private_state = root / "holdings_state.json"
        records = strategy / "execution_records.jsonl"
        before_baseline = baseline.read_bytes()
        old_base = execution_service.HOLDINGS_BASE_FILE
        old_state = execution_service.HOLDINGS_STATE_FILE
        try:
            execution_service.HOLDINGS_BASE_FILE = baseline
            execution_service.HOLDINGS_STATE_FILE = private_state
            result = apply_execution_confirmation(
                _confirmation(), records_path=records,
                portfolio_path=portfolio, strategy_dir=strategy, plan_path=plan,
            )
        finally:
            execution_service.HOLDINGS_BASE_FILE = old_base
            execution_service.HOLDINGS_STATE_FILE = old_state

        assert result["status"] == "written"
        assert result["holdings_path"] == str(private_state)
        assert baseline.read_bytes() == before_baseline
        assert json.loads(private_state.read_text(encoding="utf-8"))["holdings"]["600001"]["shares"] == 900