# -*- coding: utf-8 -*-

import pandas as pd

from vaxstock.sources.tushare_src import TushareSource
from vaxstock.sources.us_market import normalise_history_frame


def _source_with_frame(frame):
    source = TushareSource.__new__(TushareSource)
    source.enabled = True
    source.code_to_ts = TushareSource.code_to_ts
    source._cache_get = lambda *_: None
    source._cache_set = lambda *_: None
    calls = []

    def safe_call(name, **kwargs):
        calls.append((name, kwargs))
        return frame.copy()

    source._safe_call = safe_call
    return source, calls


def test_adjustment_history_uses_explicit_range_and_real_fields():
    frame = pd.DataFrame([{
        "ts_code": "601138.SH",
        "trade_date": "20260728",
        "adj_factor": 1.234,
    }])
    source, calls = _source_with_frame(frame)

    rows = source.get_adj_factor_history_range(
        "601138",
        start_date="20200101",
        end_date="20260728",
    )

    assert rows[0]["adj_factor"] == 1.234
    assert calls == [(
        "adj_factor",
        {
            "ts_code": "601138.SH",
            "start_date": "20200101",
            "end_date": "20260728",
            "fields": "ts_code,trade_date,adj_factor",
        },
    )]


def test_yfinance_multisymbol_frame_is_normalised_without_guessing_close():
    index = pd.to_datetime(["2026-07-27", "2026-07-28"])
    columns = pd.MultiIndex.from_product(
        [["NVDA", "SOXX"], ["Close", "Volume"]]
    )
    frame = pd.DataFrame(
        [
            [100.0, 1000, 200.0, 2000],
            [101.0, 1100, 198.0, 2100],
        ],
        index=index,
        columns=columns,
    )

    rows = normalise_history_frame(frame, ["NVDA", "SOXX"])

    assert rows == [
        {
            "session_date": "20260727",
            "symbol": "NVDA",
            "adj_close": 100.0,
            "volume": 1000.0,
            "source": "yfinance.download(auto_adjust=True)",
        },
        {
            "session_date": "20260727",
            "symbol": "SOXX",
            "adj_close": 200.0,
            "volume": 2000.0,
            "source": "yfinance.download(auto_adjust=True)",
        },
        {
            "session_date": "20260728",
            "symbol": "NVDA",
            "adj_close": 101.0,
            "volume": 1100.0,
            "source": "yfinance.download(auto_adjust=True)",
        },
        {
            "session_date": "20260728",
            "symbol": "SOXX",
            "adj_close": 198.0,
            "volume": 2100.0,
            "source": "yfinance.download(auto_adjust=True)",
        },
    ]
