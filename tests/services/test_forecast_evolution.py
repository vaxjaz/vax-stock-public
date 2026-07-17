# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path

from vaxstock.services.forecast_evolution import (
    finalize_evolutions,
    record_evolution_observation,
    restore_active_evolutions,
    start_trigger_evolution,
)


def _task():
    return {
        "task_id": "20260713_20260714_601138_d_observe_llm_v2",
        "code": "601138",
        "name": "FII",
        "target_trade_date": "20260714",
        "plan_version": "d_observe_llm_v2",
    }


def _quote(trade_time, price):
    return {
        "code": "601138",
        "trade_date": "2026-07-14",
        "trade_time": trade_time,
        "price": price,
        "change_pct": price - 100,
        "amount": 1.2e9,
        "source": "sina",
    }


def test_evolution_records_fixed_checkpoints_and_finalizes_idempotently():
    with tempfile.TemporaryDirectory() as tmp:
        status = Path(tmp) / "current.json"
        history = Path(tmp) / "evolution.jsonl"
        started = start_trigger_evolution(
            _task(), "reclaim_confirm", _quote("10:00:00", 100.0),
            forecast_ts="2026-07-14T10:00:02",
            status_path=status, history_path=history,
        )
        duplicate_start = start_trigger_evolution(
            _task(), "reclaim_confirm", _quote("10:00:00", 100.0),
            status_path=status, history_path=history,
        )
        ten = record_evolution_observation(
            _task(), _quote("10:10:00", 102.0), status_path=status,
        )
        fifteen = record_evolution_observation(
            _task(), _quote("10:16:00", 103.0), status_path=status,
        )
        thirty = record_evolution_observation(
            _task(), _quote("10:31:00", 98.0), status_path=status,
        )
        duplicate_quote = record_evolution_observation(
            _task(), _quote("10:31:00", 98.0), status_path=status,
        )
        close = record_evolution_observation(
            _task(), _quote("14:55:00", 101.0), status_path=status,
        )
        first = finalize_evolutions(
            "20260714", status_path=status, history_path=history,
            finalized_at="2026-07-14T15:03:00",
        )
        second = finalize_evolutions(
            "20260714", status_path=status, history_path=history,
            finalized_at="2026-07-14T15:04:00",
        )
        rows = [
            json.loads(line)
            for line in history.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    assert started["status"] == "written"
    assert duplicate_start["status"] == "duplicate"
    assert ten["status"] == fifteen["status"] == thirty["status"] == "written"
    assert duplicate_quote["status"] == "duplicate"
    assert close["status"] == "written"
    assert first["written"] == 1
    assert second["written"] == 0
    assert second["skipped"] == 1
    assert len(rows) == 1
    row = rows[0]
    assert row["quality"]["complete"] is True
    assert row["checkpoints"]["15m"]["price"] == 103.0
    assert row["checkpoints"]["30m"]["price"] == 98.0
    assert row["checkpoints"]["close"]["price"] == 101.0
    assert round(row["checkpoints"]["15m"]["return_from_trigger"], 6) == 0.03
    assert round(row["path"]["min_return_from_trigger"], 6) == -0.02
    assert round(row["path"]["max_return_from_trigger"], 6) == 0.03
    assert row["evaluation"]["user_execution_used"] is False
    assert row["evaluation"]["official_eod_close_used"] is False


def test_evolution_uses_trading_minutes_across_lunch_and_does_not_fake_missed_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        status = Path(tmp) / "current.json"
        start_trigger_evolution(
            _task(), "reclaim_confirm", _quote("11:25:00", 100.0),
            status_path=status,
        )
        before_15 = record_evolution_observation(
            _task(), _quote("13:09:00", 101.0), status_path=status,
        )
        at_15 = record_evolution_observation(
            _task(), _quote("13:10:00", 102.0), status_path=status,
        )
        late = record_evolution_observation(
            _task(), _quote("13:31:00", 103.0), status_path=status,
        )
        state = json.loads(status.read_text(encoding="utf-8"))
        row = next(iter(state["evolutions"].values()))

    assert before_15["status"] == at_15["status"] == late["status"] == "written"
    assert row["checkpoints"]["15m"]["trade_time"] == "13:10:00"
    assert "30m" not in row["checkpoints"]


def test_late_trigger_marks_unreachable_checkpoints_not_applicable():
    with tempfile.TemporaryDirectory() as tmp:
        status = Path(tmp) / "current.json"
        history = Path(tmp) / "evolution.jsonl"
        start_trigger_evolution(
            _task(), "breakdown_confirm", _quote("14:47:48", 100.0),
            status_path=status, history_path=history,
        )
        record_evolution_observation(
            _task(), _quote("14:58:03", 99.0), status_path=status,
        )
        finalized = finalize_evolutions(
            "20260714", status_path=status, history_path=history,
            finalized_at="2026-07-14T15:03:00",
        )
        row = json.loads(history.read_text(encoding="utf-8").strip())

    assert finalized["written"] == 1
    assert row["quality"]["complete"] is True
    assert row["quality"]["checkpoint_15m_required"] is False
    assert row["quality"]["checkpoint_30m_required"] is False
    assert row["quality"]["not_applicable_checkpoints"] == ["15m", "30m"]
    assert row["checkpoints"]["close"]["price"] == 99.0


def test_evolution_rejects_unverified_time_and_wrong_trade_date():
    with tempfile.TemporaryDirectory() as tmp:
        status = Path(tmp) / "current.json"
        midday = start_trigger_evolution(
            _task(), "reclaim_confirm", _quote("12:00:00", 100.0),
            status_path=status,
        )
        wrong = _quote("10:00:00", 100.0)
        wrong["trade_date"] = "20260713"
        stale = start_trigger_evolution(
            _task(), "reclaim_confirm", wrong, status_path=status,
        )

    assert midday == {"status": "skipped", "reason": "quote_time_invalid"}
    assert stale == {"status": "skipped", "reason": "quote_trade_date_mismatch"}
    assert not status.exists()


def test_restore_rebuilds_active_evolution_from_frozen_forecast():
    task = _task()
    forecast = {
        "schema_version": 1,
        "forecast_ts": "2026-07-14T10:00:02",
        "trade_date": "20260714",
        "code": "601138",
        "inputs_ref": {
            "dline_task_id": task["task_id"],
            "dline_plan_version": "d_observe_llm_v2",
            "trigger_blueprint": {"trigger_type": "reclaim_confirm"},
            "quote_snapshot": _quote("10:00:00", 100.0),
        },
        "structured": {
            "source": "dline_task_blueprint",
            "task_id": task["task_id"],
            "trigger_type": "reclaim_confirm",
        },
    }
    with tempfile.TemporaryDirectory() as tmp:
        forecasts = Path(tmp) / "forecasts.jsonl"
        status = Path(tmp) / "current.json"
        forecasts.write_text(json.dumps(forecast) + "\n", encoding="utf-8")
        first = restore_active_evolutions(
            [task], forecasts_path=forecasts, status_path=status,
        )
        second = restore_active_evolutions(
            [task], forecasts_path=forecasts, status_path=status,
        )
        state = json.loads(status.read_text(encoding="utf-8"))

    assert first == {"written": 1, "duplicates": 0, "skipped": 0}
    assert second == {"written": 0, "duplicates": 1, "skipped": 0}
    assert len(state["evolutions"]) == 1
