# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path

from vaxstock.services.observation_coverage import (
    finalize_observation_coverage, load_observation_coverage,
    record_task_observation,
)


def _task():
    return {
        "task_id": "20260710_20260713_601138_d_observe_llm_v2",
        "code": "601138",
        "target_trade_date": "20260713",
    }


def _quote():
    return {
        "code": "601138", "trade_date": "2026-07-13",
        "trade_time": "09:35:00", "price": 65.3,
        "change_pct": -1.2, "amount": 1.2e9, "source": "sina",
    }


def test_observation_coverage_is_same_session_and_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "coverage.json"
        first = record_task_observation(
            _task(), _quote(), observed_at="2026-07-13T09:35:01", status_path=path,
        )
        duplicate = record_task_observation(
            _task(), _quote(), observed_at="2026-07-13T09:35:01", status_path=path,
        )
        second_quote = _quote()
        second_quote["trade_time"] = "09:40:00"
        second_quote["price"] = 65.5
        second = record_task_observation(
            _task(), second_quote, observed_at="2026-07-13T09:40:01", status_path=path,
        )
        loaded = load_observation_coverage("2026-07-13", status_path=path)

    assert first["status"] == "written"
    assert duplicate["status"] == "duplicate"
    assert second["observation_count"] == 2
    row = loaded["by_code"]["601138"][0]
    assert loaded["status"] == "available"
    assert row["observation_count"] == 2
    assert row["first_quote_trade_time"] == "09:35:00"
    assert row["last_quote_trade_time"] == "09:40:00"
    assert row["last_price"] == 65.5


def test_observation_coverage_rejects_stale_quote_and_exposes_corruption():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "coverage.json"
        stale = _quote()
        stale["trade_date"] = "20260710"
        result = record_task_observation(
            _task(), stale, observed_at="2026-07-13T09:35:01", status_path=path,
        )
        assert result["status"] == "skipped"
        assert result["reason"] == "quote_trade_date_mismatch"
        assert not path.exists()

        path.write_text("{broken", encoding="utf-8")
        loaded = load_observation_coverage("20260713", status_path=path)
        assert loaded["status"] == "invalid"
        write = record_task_observation(
            _task(), _quote(), observed_at="2026-07-13T09:35:01", status_path=path,
        )
        assert write["status"] == "error"
        assert path.read_text(encoding="utf-8") == "{broken"


def test_observation_coverage_reports_target_mismatch_without_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "coverage.json"
        path.write_text(json.dumps({
            "target_trade_date": "20260710", "tasks": {},
        }), encoding="utf-8")
        loaded = load_observation_coverage("20260713", status_path=path)
    assert loaded == {
        "status": "target_mismatch",
        "target_trade_date": "20260713",
        "observed_trade_date": "20260710",
        "by_code": {},
    }

def test_observation_coverage_rejects_valid_json_with_invalid_tasks_schema():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "coverage.json"
        original = json.dumps({
            "target_trade_date": "20260713", "tasks": [],
        })
        path.write_text(original, encoding="utf-8")
        loaded = load_observation_coverage("20260713", status_path=path)
        written = record_task_observation(
            _task(), _quote(), observed_at="2026-07-13T09:35:01", status_path=path,
        )
        assert loaded["status"] == "invalid"
        assert loaded["detail"] == "tasks_not_object"
        assert written["status"] == "error"
        assert written["detail"] == "tasks_not_object"
        assert path.read_text(encoding="utf-8") == original


def test_full_session_coverage_is_versioned_and_archived_idempotently():
    with tempfile.TemporaryDirectory() as tmp:
        status = Path(tmp) / "current.json"
        history = Path(tmp) / "coverage.jsonl"
        times = []
        start = __import__("datetime").datetime(2026, 7, 13, 9, 30)
        times.extend(start + __import__("datetime").timedelta(minutes=8 * i) for i in range(15))
        start = __import__("datetime").datetime(2026, 7, 13, 13, 5)
        times.extend(start + __import__("datetime").timedelta(minutes=8 * i) for i in range(15))
        for index, stamp in enumerate(times):
            quote = _quote()
            quote["trade_time"] = stamp.strftime("%H:%M:%S")
            quote["price"] = 65.0 + index / 100
            result = record_task_observation(
                _task(), quote,
                observed_at=stamp.isoformat(timespec="seconds"),
                status_path=status, history_path=history,
            )
            assert result["status"] == "written"

        first = finalize_observation_coverage(
            "20260713", status_path=status, history_path=history,
            finalized_at="2026-07-13T15:03:00",
        )
        second = finalize_observation_coverage(
            "20260713", status_path=status, history_path=history,
            finalized_at="2026-07-13T15:04:00",
        )
        rows = [
            json.loads(line)
            for line in history.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    assert first["written"] == 1
    assert second["written"] == 0
    assert second["skipped"] == 1
    assert len(rows) == 1
    assert rows[0]["quality"]["policy_version"] == "d_full_session_v1"
    assert rows[0]["quality"]["qualified"] is True
    assert rows[0]["observation"]["morning_observation_count"] == 15
    assert rows[0]["observation"]["afternoon_observation_count"] == 15


def test_partial_coverage_is_not_a_valid_no_trigger_sample():
    row = {
        "morning_observation_count": 15,
        "afternoon_observation_count": 15,
        "first_morning_quote_time": "09:30:00",
        "last_morning_quote_time": "11:22:00",
        "first_afternoon_quote_time": "13:05:00",
        "last_afternoon_quote_time": "14:57:00",
        "max_morning_gap_seconds": 2400,
        "max_afternoon_gap_seconds": 480,
    }
    from vaxstock.services.observation_coverage import assess_observation_coverage
    quality = assess_observation_coverage(row)
    assert quality["qualified"] is False
    assert quality["checks"]["morning_gap"] is False