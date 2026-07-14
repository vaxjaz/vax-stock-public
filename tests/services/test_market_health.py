# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path

from vaxstock.services.market_health import (
    evaluate_market_health,
    render_market_health_notification,
    run_market_health_check,
)


def _holdings(ai=True):
    return {
        "600001": {"name": "A", "concepts": ["AI算力"] if ai else []},
        "600002": {"name": "B", "concepts": ["AIDC"] if ai else []},
        "600003": {"name": "C", "concepts": []},
        "600004": {"name": "D", "concepts": []},
    }


def _quotes(changes, trade_date="2026-07-14", trade_time="10:00:00"):
    out = {}
    for index, (code, change) in enumerate(sorted(changes.items())):
        out[code] = {
            "code": code,
            "name": chr(ord("A") + index),
            "trade_date": trade_date,
            "trade_time": trade_time,
            "price": 100 + change,
            "change_pct": change,
            "amplitude_pct": abs(change) + 1,
            "amount": 1e8,
            "source": "sina",
        }
    return out


def test_evaluate_market_health_detects_portfolio_and_ai_cluster_from_real_quote_fields():
    result = evaluate_market_health(
        quotes=_quotes({
            "600001": -4.0, "600002": -3.5,
            "600003": -3.2, "600004": 0.0,
        }),
        holdings=_holdings(),
    )
    assert result["status"] == "evaluated"
    assert result["trade_date"] == "20260714"
    assert set(result["signals"]) == {
        "portfolio_synchronized_drop",
        "ai_holdings_synchronized_drop",
    }
    portfolio = result["signals"]["portfolio_synchronized_drop"]
    assert portfolio["severity"] == "high"
    assert portfolio["evidence"]["matched_count"] == 3
    assert portfolio["evidence"]["matched_ratio"] == 0.75
    assert result["quality"]["quote_coverage_ratio"] == 1.0


def test_evaluate_market_health_rejects_mixed_trade_dates_without_fallback():
    quotes = _quotes({
        "600001": -4.0, "600002": -3.5,
        "600003": -3.2, "600004": 0.0,
    })
    quotes["600004"]["trade_date"] = "20260713"
    result = evaluate_market_health(quotes=quotes, holdings=_holdings())
    assert result["status"] == "insufficient_data"
    assert result["trade_date"] is None
    assert result["signals"] == {}
    assert result["quality"]["reason"] == "quote_trade_date_missing_or_mixed"


def test_market_health_state_transitions_are_idempotent_and_reopen_new_episode():
    holdings = _holdings(ai=False)
    falling = _quotes({
        "600001": -4.0, "600002": -3.5,
        "600003": -3.2, "600004": 0.0,
    })
    recovered = _quotes({code: 0.0 for code in holdings}, trade_time="10:30:00")
    reopened_quotes = _quotes({
        "600001": -4.0, "600002": -3.5,
        "600003": -3.2, "600004": 0.0,
    }, trade_time="10:45:00")
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "current.json"
        events = Path(tmp) / "events.jsonl"
        first = run_market_health_check(
            quotes=falling, holdings=holdings,
            market_ctx_loader=lambda: {"regime": "momentum"},
            observed_at="2026-07-14T10:00:00", force=True,
            state_path=state, events_path=events,
        )
        throttled = run_market_health_check(
            quotes=falling, holdings=holdings,
            market_ctx_loader=lambda: {"regime": "momentum"},
            observed_at="2026-07-14T10:05:00",
            state_path=state, events_path=events,
        )
        unchanged = run_market_health_check(
            quotes=falling, holdings=holdings,
            market_ctx_loader=lambda: {"regime": "momentum"},
            observed_at="2026-07-14T10:15:00", force=True,
            state_path=state, events_path=events,
        )
        closed = run_market_health_check(
            quotes=recovered, holdings=holdings,
            market_ctx_loader=lambda: {"regime": "momentum"},
            observed_at="2026-07-14T10:30:00", force=True,
            state_path=state, events_path=events,
        )
        reopened = run_market_health_check(
            quotes=reopened_quotes, holdings=holdings,
            market_ctx_loader=lambda: {"regime": "momentum"},
            observed_at="2026-07-14T10:45:00", force=True,
            state_path=state, events_path=events,
        )
        rows = [
            json.loads(line)
            for line in events.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    assert first["written"] == 1
    assert len(first["notifications"]) == 1
    assert throttled["status"] == "throttled"
    assert unchanged["status"] == "no_change"
    assert closed["written"] == 1
    assert closed["events"][0]["status"] == "recovered"
    assert closed["notifications"] == []
    assert reopened["written"] == 1
    assert reopened["events"][0]["episode"] == 2
    assert len(rows) == 3
    assert len({row["event_id"] for row in rows}) == 3
    assert all(row["evaluation"]["user_execution_used"] is False for row in rows)


def test_regime_transition_is_not_fabricated_on_first_observation():
    holdings = _holdings(ai=False)
    stable = _quotes({code: 0.0 for code in holdings})
    regimes = iter(("momentum", "panic"))
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "current.json"
        events = Path(tmp) / "events.jsonl"
        first = run_market_health_check(
            quotes=stable, holdings=holdings,
            market_ctx_loader=lambda: {"regime": next(regimes)},
            observed_at="2026-07-14T10:00:00", force=True,
            state_path=state, events_path=events,
        )
        second = run_market_health_check(
            quotes=stable, holdings=holdings,
            market_ctx_loader=lambda: {"regime": next(regimes)},
            observed_at="2026-07-14T10:15:00", force=True,
            state_path=state, events_path=events,
        )

    assert first["written"] == 0
    assert second["written"] == 1
    event = second["events"][0]
    assert event["event_type"] == "market_regime_change"
    assert event["severity"] == "high"
    assert event["evidence"]["overview_used_for_trigger"] is False
    assert second["notifications"] == [event]


def test_c_direction_contradiction_and_extreme_holding_shock_are_separate_evidence():
    tasks = [{
        "code": "600001",
        "evidence_pack": {
            "C_prediction": {
                "prediction": {"action": "watch", "direction": "up", "confidence": 0.6},
            },
        },
    }]
    result = evaluate_market_health(
        quotes=_quotes({
            "600001": -7.5, "600002": 0.0,
            "600003": 0.0, "600004": 0.0,
        }),
        holdings=_holdings(ai=False),
        tasks=tasks,
    )
    assert "holding_shock:600001" in result["signals"]
    assert "c_direction_contradiction:600001" in result["signals"]
    assert result["signals"]["holding_shock:600001"]["severity"] == "high"
    assert result["signals"]["c_direction_contradiction:600001"]["severity"] == "medium"


def test_market_health_notification_is_human_readable():
    body = render_market_health_notification([{
        "summary": "3/4只持仓同步下跌至少3.0%",
        "severity": "high",
        "evidence": {"matched_codes": ["600001", "600002", "600003"]},
    }])
    assert "主动盘面体检" in body
    assert "不是自动交易指令" in body
    assert "600001, 600002, 600003" in body
    assert "用户成交不参与触发" in body

def test_non_finite_quote_is_not_counted_as_valid_data():
    quotes = _quotes({
        "600001": -4.0, "600002": -3.5,
        "600003": -3.2, "600004": 0.0,
    })
    quotes["600001"]["price"] = float("nan")
    quotes["600002"]["change_pct"] = float("inf")
    result = evaluate_market_health(quotes=quotes, holdings=_holdings(ai=False))
    assert result["status"] == "insufficient_data"
    assert result["quality"]["valid_quote_count"] == 2
    assert result["quality"]["reason"] == "holding_quote_coverage_insufficient"


def test_corrupt_event_history_blocks_new_conclusion():
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "current.json"
        events = Path(tmp) / "events.jsonl"
        events.write_text("not-json\n", encoding="utf-8")
        result = run_market_health_check(
            quotes=_quotes({
                "600001": -4.0, "600002": -3.5,
                "600003": -3.2, "600004": 0.0,
            }),
            holdings=_holdings(ai=False),
            observed_at="2026-07-14T10:00:00",
            force=True,
            state_path=state,
            events_path=events,
        )
    assert result["status"] == "invalid_events"
    assert result["written"] == 0
    assert result["notifications"] == []

def test_stale_quote_is_rejected_before_any_signal():
    result = evaluate_market_health(
        quotes=_quotes({
            "600001": -4.0, "600002": -3.5,
            "600003": -3.2, "600004": 0.0,
        }),
        holdings=_holdings(ai=False),
        observed_at="2026-07-14T10:30:01",
    )
    assert result["status"] == "insufficient_data"
    assert result["signals"] == {}
    assert result["quality"]["valid_quote_count"] == 0
    assert result["quality"]["stale_quote_codes"] == [
        "600001", "600002", "600003", "600004",
    ]
