# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path

from vaxstock.services.observation_coverage import (
    load_observation_coverage, record_task_observation,
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
