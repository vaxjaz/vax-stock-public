# -*- coding: utf-8 -*-

from vaxstock.sources.tushare_src import TushareSource


_FIELDS = ["ts_code", "ann_date", "end_date", "pre_date", "actual_date", "modify_date"]


class _Frame:
    def __init__(self, rows, columns=None):
        self.rows = rows
        self.columns = columns or list(_FIELDS)

    def __len__(self):
        return len(self.rows)

    def sort_values(self, *args, **kwargs):
        return self

    def head(self, count):
        return _Frame(self.rows[:count], self.columns)

    def to_dict(self, orient):
        assert orient == "records"
        return list(self.rows)


def _source(frame):
    source = TushareSource.__new__(TushareSource)
    source.points_level = 2000
    source.code_to_ts = lambda code: f"{code}.SH"
    source._cache_get = lambda *args: None
    source._cache_set = lambda *args: None
    calls = []
    source._safe_call = lambda name, **kwargs: calls.append((name, kwargs)) or frame
    return source, calls


def test_disclosure_schedule_uses_official_fields_and_preserves_dates():
    row = {
        "ts_code": "601138.SH",
        "ann_date": "20260701",
        "end_date": "20260630",
        "pre_date": "20260812",
        "actual_date": None,
        "modify_date": "20260701",
    }
    source, calls = _source(_Frame([row]))
    result = source.get_disclosure_schedule("601138", periods=8)
    assert result == [row]
    assert calls == [("disclosure_date", {
        "ts_code": "601138.SH",
        "fields": ",".join(_FIELDS),
    })]


def test_disclosure_schedule_rejects_incomplete_runtime_schema():
    source, _ = _source(_Frame([], columns=["ts_code", "pre_date"]))
    assert source.get_disclosure_schedule("601138") is None