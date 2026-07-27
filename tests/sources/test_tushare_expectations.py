# -*- coding: utf-8 -*-

from vaxstock.sources.tushare_src import TushareSource


FORECAST_FIELDS = [
    "ts_code", "ann_date", "end_date", "type", "p_change_min",
    "p_change_max", "net_profit_min", "net_profit_max", "last_parent_net",
    "first_ann_date", "summary", "change_reason",
]
REPORT_FIELDS = [
    "ts_code", "name", "report_date", "report_title", "report_type",
    "classify", "org_name", "author_name", "quarter", "op_rt", "op_pr",
    "tp", "np", "eps", "pe", "rd", "roe", "ev_ebitda", "rating",
    "max_price", "min_price", "imp_dg", "create_time",
]
DAILY_BASIC_FIELDS = [
    "ts_code", "trade_date", "close", "pe_ttm", "total_share", "total_mv",
]


class _Frame:
    def __init__(self, rows, columns):
        self.rows = list(rows)
        self.columns = list(columns)

    def __len__(self):
        return len(self.rows)

    def sort_values(self, *args, **kwargs):
        return self

    def to_dict(self, orient):
        assert orient == "records"
        return list(self.rows)


def _source(call):
    source = TushareSource.__new__(TushareSource)
    source.points_level = 2000
    source.code_to_ts = TushareSource.code_to_ts
    source._cache_get = lambda *args: None
    source._cache_set = lambda *args: None
    source._safe_call = call
    return source


def test_forecast_contract_distinguishes_empty_from_source_failure():
    calls = []

    def _call(name, **kwargs):
        calls.append((name, kwargs))
        return _Frame([], FORECAST_FIELDS)

    source = _source(_call)
    result = source.get_forecast_contract(
        "601138",
        start_date="20250701",
        end_date="20260727",
        refresh_bucket="20260728",
    )
    assert result["available"] is True
    assert result["complete"] is True
    assert result["rows"] == []
    assert calls[0][0] == "forecast"
    assert calls[0][1]["_allow_empty"] is True
    assert calls[0][1]["fields"].split(",") == FORECAST_FIELDS

    failed = _source(lambda name, **kwargs: None).get_forecast_contract(
        "601138",
        start_date="20250701",
        end_date="20260727",
    )
    assert failed["available"] is False
    assert failed["complete"] is False
    assert failed["reason"] == "source_call_failed"
    assert failed["query"]["ts_code"] == "601138.SH"


def test_forecast_contract_rejects_unverified_runtime_fields():
    source = _source(
        lambda name, **kwargs: _Frame([], ["ts_code", "ann_date", "end_date"])
    )
    result = source.get_forecast_contract(
        "601138", start_date="20250701", end_date="20260727"
    )
    assert result["available"] is False
    assert result["reason"] == "source_fields_missing"
    assert "net_profit_min" in result["missing_fields"]


def test_report_rc_paginates_and_requires_the_official_schema():
    rows = [
        {
            "ts_code": "601138.SH",
            "report_date": "20260727",
            "quarter": "2026Q4",
            "org_name": f"org-{index}",
            "eps": 3.0 + index,
            "pe": 20.0,
        }
        for index in range(3)
    ]
    calls = []

    def _call(name, **kwargs):
        calls.append((name, kwargs))
        offset = kwargs["offset"]
        return _Frame(rows[offset:offset + 2], REPORT_FIELDS)

    source = _source(_call)
    result = source.get_report_rc_window(
        start_date="20260721",
        end_date="20260727",
        page_limit=2,
        max_pages=3,
        refresh_bucket="20260728",
    )
    assert result["available"] is True
    assert result["complete"] is True
    assert len(result["rows"]) == 3
    assert [call[1]["offset"] for call in calls] == [0, 2]
    assert all(call[1]["fields"].split(",") == REPORT_FIELDS for call in calls)


def test_report_rc_marks_a_capped_window_incomplete():
    source = _source(
        lambda name, **kwargs: _Frame(
            [{"ts_code": "601138.SH", "report_date": "20260727"}] * 2,
            REPORT_FIELDS,
        )
    )
    result = source.get_report_rc_window(
        start_date="20260721",
        end_date="20260727",
        page_limit=2,
        max_pages=1,
    )
    assert result["available"] is True
    assert result["complete"] is False
    assert result["reason"] == "page_limit_reached"


def test_report_rc_rejects_unverified_runtime_fields():
    source = _source(
        lambda name, **kwargs: _Frame([], ["ts_code", "report_date", "eps"])
    )
    result = source.get_report_rc_window(
        start_date="20260429",
        end_date="20260727",
        page_limit=3000,
        max_pages=1,
    )

    assert result["available"] is False
    assert result["complete"] is False
    assert result["reason"] == "source_fields_missing"
    assert "np" in result["missing_fields"]
    assert result["query"]["start_date"] == "20260429"


def test_daily_basic_contract_requires_exact_identity_and_schema():
    calls = []

    def _call(name, **kwargs):
        calls.append((name, kwargs))
        return _Frame(
            [{
                "ts_code": "601138.SH",
                "trade_date": "20260727",
                "close": 61.0,
                "pe_ttm": 25.0,
                "total_share": 10000.0,
                "total_mv": 610000.0,
            }],
            DAILY_BASIC_FIELDS,
        )

    source = _source(_call)
    result = source.get_daily_basic_contract(
        "601138",
        trade_date="20260727",
        refresh_bucket="20260728",
    )

    assert result["available"] is True
    assert result["complete"] is True
    assert len(result["rows"]) == 1
    assert calls[0][0] == "daily_basic"
    assert calls[0][1]["trade_date"] == "20260727"
    assert calls[0][1]["_allow_empty"] is True
    assert calls[0][1]["fields"].split(",") == DAILY_BASIC_FIELDS


def test_daily_basic_contract_rejects_a_substituted_date():
    source = _source(
        lambda name, **kwargs: _Frame(
            [{
                "ts_code": "601138.SH",
                "trade_date": "20260726",
                "close": 60.0,
                "pe_ttm": 24.0,
                "total_share": 10000.0,
                "total_mv": 600000.0,
            }],
            DAILY_BASIC_FIELDS,
        )
    )
    result = source.get_daily_basic_contract(
        "601138", trade_date="20260727"
    )

    assert result["available"] is False
    assert result["complete"] is False
    assert result["reason"] == "unexpected_row_identity"


def test_daily_basic_contract_distinguishes_empty_from_failure():
    empty = _source(
        lambda name, **kwargs: _Frame([], DAILY_BASIC_FIELDS)
    ).get_daily_basic_contract("601138", trade_date="20260727")
    failed = _source(
        lambda name, **kwargs: None
    ).get_daily_basic_contract("601138", trade_date="20260727")

    assert empty["available"] is True
    assert empty["complete"] is True
    assert empty["rows"] == []
    assert failed["available"] is False
    assert failed["reason"] == "source_call_failed"
