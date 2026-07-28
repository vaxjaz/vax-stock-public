# -*- coding: utf-8 -*-

from datetime import datetime, timedelta, timezone

from vaxstock.research.point_in_time_store import (
    default_store_paths,
    read_jsonl_strict,
)
from vaxstock.services import expectation_refresh as refresh


CHINA_TZ = timezone(timedelta(hours=8))


class _Frame:
    columns = ["cal_date", "is_open"]

    def __init__(self, rows):
        self.rows = list(rows)

    def sort_values(self, field, ascending=True):
        rows = sorted(self.rows, key=lambda row: row[field], reverse=not ascending)
        return _Frame(rows)

    def to_dict(self, orient):
        assert orient == "records"
        return list(self.rows)


class _Source:
    def __init__(self, calendar_rows=None):
        self.calls = []
        self.calendar_rows = calendar_rows or [
            {"cal_date": "20260727", "is_open": 1},
            {"cal_date": "20260728", "is_open": 1},
        ]

    @staticmethod
    def code_to_ts(code):
        return f"{code}.SH"

    def _safe_call(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return _Frame(self.calendar_rows)

    def get_report_rc_window(self, **kwargs):
        self.calls.append(("report_rc", kwargs))
        return {
            "available": True,
            "complete": True,
            "reason": None,
            "rows": [],
            "fields": [],
            "actual_fields": [],
            "query": {"ts_code": None, **kwargs},
        }

    def get_forecast_contract(self, code, **kwargs):
        self.calls.append(("forecast", {"code": code, **kwargs}))
        return {
            "available": True,
            "complete": True,
            "reason": None,
            "rows": [],
            "fields": [],
            "actual_fields": [],
            "query": {"ts_code": self.code_to_ts(code), **kwargs},
        }

    def get_daily_basic_contract(self, code, **kwargs):
        self.calls.append(("daily_basic", {"code": code, **kwargs}))
        trade_date = kwargs["trade_date"]
        row = {
            "ts_code": self.code_to_ts(code),
            "trade_date": trade_date,
            "close": 61.0,
            "pe_ttm": 25.0,
            "total_share": 10000.0,
            "total_mv": 610000.0,
        }
        return {
            "available": True,
            "complete": True,
            "reason": None,
            "rows": [row],
            "fields": sorted(row),
            "actual_fields": sorted(row),
            "query": {"ts_code": self.code_to_ts(code), **kwargs},
        }


def test_preopen_service_uses_calendar_verified_dates_and_is_idempotent(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(refresh, "_universe", lambda: {"601138": "工业富联"})
    source = _Source()
    paths = default_store_paths(tmp_path / "research")
    started = datetime(2026, 7, 28, 8, 35, tzinfo=CHINA_TZ)
    completed = datetime(2026, 7, 28, 8, 36, tzinfo=CHINA_TZ)

    first = refresh.run_expectation_refresh(
        source=source,
        now=started,
        completed_at=completed,
        paths=paths,
    )
    second = refresh.run_expectation_refresh(
        source=source,
        now=started,
        completed_at=completed,
        paths=paths,
    )

    assert first["status"] == "written"
    assert second["status"] == "already_complete"
    report_call = next(call for call in source.calls if call[0] == "report_rc")
    assert report_call[1]["start_date"] == "20260429"
    assert report_call[1]["end_date"] == "20260727"
    assert report_call[1]["max_pages"] == 10
    assert len(read_jsonl_strict(paths.manifests)) == 1


def test_preopen_preserves_committed_expectation_facts_when_curve_fails(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(refresh, "_universe", lambda: {"601138": "工业富联"})
    monkeypatch.setattr(
        refresh,
        "run_curve_refresh",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("curve store failed")),
    )
    paths = default_store_paths(tmp_path / "research")
    result = refresh.run_expectation_refresh(
        source=_Source(),
        now=datetime(2026, 7, 28, 8, 35, tzinfo=CHINA_TZ),
        completed_at=datetime(2026, 7, 28, 8, 36, tzinfo=CHINA_TZ),
        paths=paths,
    )

    assert result["status"] == "written"
    assert result["curve_refresh"]["status"] == "failed"
    assert "curve store failed" in result["curve_refresh"]["reason"]
    assert len(read_jsonl_strict(paths.manifests)) == 1


def test_preopen_preserves_prior_stages_when_group_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(refresh, "_universe", lambda: {"601138": "工业富联"})
    monkeypatch.setattr(
        refresh,
        "run_group_refresh",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("group store failed")),
    )
    paths = default_store_paths(tmp_path / "research")
    result = refresh.run_expectation_refresh(
        source=_Source(),
        now=datetime(2026, 7, 28, 8, 35, tzinfo=CHINA_TZ),
        completed_at=datetime(2026, 7, 28, 8, 36, tzinfo=CHINA_TZ),
        paths=paths,
    )

    assert result["status"] == "written"
    assert result["group_refresh"]["status"] == "failed"
    assert "group store failed" in result["group_refresh"]["reason"]
    assert len(read_jsonl_strict(paths.manifests)) == 1


def test_service_blocks_before_calls_when_started_after_cutoff(tmp_path):
    source = _Source()
    result = refresh.run_expectation_refresh(
        source=source,
        now=datetime(2026, 7, 28, 9, 25, tzinfo=CHINA_TZ),
        paths=default_store_paths(tmp_path / "research"),
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "after_preopen_cutoff"
    assert source.calls == []


def test_service_discards_collection_that_finishes_after_cutoff(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(refresh, "_universe", lambda: {"601138": "工业富联"})
    source = _Source()
    paths = default_store_paths(tmp_path / "research")
    result = refresh.run_expectation_refresh(
        source=source,
        now=datetime(2026, 7, 28, 8, 35, tzinfo=CHINA_TZ),
        completed_at=datetime(2026, 7, 28, 9, 25, tzinfo=CHINA_TZ),
        paths=paths,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "collection_completed_after_preopen_cutoff"
    assert not paths.manifests.exists()


def test_market_holiday_is_distinct_from_trade_cal_failure(tmp_path):
    closed = _Source(calendar_rows=[
        {"cal_date": "20260727", "is_open": 1},
        {"cal_date": "20260728", "is_open": 0},
    ])
    closed_result = refresh.run_expectation_refresh(
        source=closed,
        now=datetime(2026, 7, 28, 8, 35, tzinfo=CHINA_TZ),
        paths=default_store_paths(tmp_path / "closed"),
    )

    class FailedCalendar(_Source):
        def _safe_call(self, name, **kwargs):
            return None

    failed_result = refresh.run_expectation_refresh(
        source=FailedCalendar(),
        now=datetime(2026, 7, 28, 8, 35, tzinfo=CHINA_TZ),
        paths=default_store_paths(tmp_path / "failed"),
    )

    assert closed_result["reason"] == "market_closed"
    assert failed_result["reason"] == "trade_cal_source_failed"


def test_main_treats_expected_calendar_skip_as_success(monkeypatch):
    monkeypatch.setattr(
        refresh,
        "run_expectation_refresh",
        lambda **kwargs: {"status": "blocked", "reason": "market_closed"},
    )

    assert refresh.main([]) == 0
