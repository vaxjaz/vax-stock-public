# -*- coding: utf-8 -*-

import pandas as pd

from vaxstock.sources.tushare_src import TushareSource


def _source(rows):
    source = TushareSource.__new__(TushareSource)
    source.points_level = 2000
    source.code_to_ts = lambda code: f"{code}.SH"
    cache = {}
    calls = []
    source._cache_get = lambda key, ttl: cache.get(key)
    source._cache_set = lambda key, data: cache.__setitem__(key, data)
    source._safe_call = lambda name, **kwargs: (
        calls.append((name, kwargs)) or pd.DataFrame(rows)
    )
    return source, cache, calls


def test_event_cache_refreshes_on_new_collection_day_even_with_long_ttl():
    source, cache, calls = _source([
        {"ts_code": "601138.SH", "end_date": "20260630", "ann_date": "20260727"},
    ])

    first = source.get_express("601138", periods=2, refresh_bucket="20260727")
    same_day = source.get_express("601138", periods=2, refresh_bucket="20260727")
    next_day = source.get_express("601138", periods=2, refresh_bucket="20260728")

    assert first == same_day == next_day
    assert len(calls) == 2
    assert sorted(cache) == [
        "express_601138_2_20260727",
        "express_601138_2_20260728",
    ]


def test_force_refresh_bypasses_same_bucket_cache():
    source, _, calls = _source([
        {"ts_code": "601138.SH", "end_date": "20260630", "ann_date": "20260727"},
    ])
    source.get_express("601138", refresh_bucket="preopen")
    source.get_express("601138", refresh_bucket="preopen", force_refresh=True)
    assert len(calls) == 2


def test_empty_event_result_is_cached_for_the_bucket():
    source, cache, calls = _source([])
    source._safe_call = lambda name, **kwargs: (
        calls.append((name, kwargs)) or pd.DataFrame(columns=["end_date"])
    )
    assert source.get_express("601138", refresh_bucket="20260727") == []
    assert source.get_express("601138", refresh_bucket="20260727") == []
    assert len(calls) == 1
    assert cache["express_601138_4_20260727"] == []
