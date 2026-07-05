# -*- coding: utf-8 -*-

import sys
import types

# The local bundled test Python may not include optional runtime dependency
# requests. stock_item imports sina at module import time, but this test patches
# get_sina_realtime before use, so a tiny import stub is enough here.
sys.modules.setdefault("requests", types.SimpleNamespace(get=lambda *args, **kwargs: None))

from vaxstock.analysis import stock_item


class FakeSource:
    points_level = 2000

    def __init__(self):
        self.calls = []

    def get_moneyflow_summary(self, code):
        self.calls.append(("moneyflow", code))
        return None

    def get_fina_indicator(self, code, periods=4):
        self.calls.append(("fina_indicator", code, periods))
        return [
            {
                "ts_code": "002475.SZ",
                "end_date": "20260331",
                "ann_date": "20260425",
                "roe": 10,
                "netprofit_yoy": 30.5,
                "or_yoy": 18.2,
            }
        ]

    def get_forecast(self, code, periods=4):
        self.calls.append(("forecast", code, periods))
        return [
            {
                "ts_code": "002475.SZ",
                "end_date": "20260630",
                "ann_date": "20260710",
                "type": "preincrease",
                "p_change_min": 50,
                "p_change_max": 80,
                "summary": "profit forecast",
            }
        ]

    def get_express(self, code, periods=4):
        self.calls.append(("express", code, periods))
        return [
            {
                "ts_code": "002475.SZ",
                "end_date": "20260331",
                "ann_date": "20260420",
                "yoy_net_profit": -5,
                "perf_summary": "express summary",
            }
        ]

    def get_holder_number(self, code, periods=2):
        self.calls.append(("holder_number", code, periods))
        return []

    def get_daily_basic(self, code):
        self.calls.append(("daily_basic", code))
        return {}

    def get_stock_concepts(self, code):
        self.calls.append(("stock_concepts", code))
        return []


def test_build_stock_item_carries_real_source_context_fields():
    src = FakeSource()
    saved = (
        stock_item.get_sina_realtime,
        stock_item.get_history_kline,
        stock_item.calc_derived_metrics,
        stock_item.calc_right_side_score,
    )
    try:
        stock_item.get_sina_realtime = lambda code, name: {
            "name": name,
            "price": 10.0,
            "change_pct": 0.1,
            "volume": 1000,
        }
        stock_item.get_history_kline = lambda source, code: []
        stock_item.calc_derived_metrics = lambda *args, **kwargs: {}
        stock_item.calc_right_side_score = lambda **kwargs: {"score": 0, "signals": [], "grade": "neutral"}

        item = stock_item.build_stock_item(
            "watchlist",
            "002475",
            "Luxshare",
            None,
            None,
            source=src,
            market_regime="momentum",
        )
    finally:
        (
            stock_item.get_sina_realtime,
            stock_item.get_history_kline,
            stock_item.calc_derived_metrics,
            stock_item.calc_right_side_score,
        ) = saved

    assert ("fina_indicator", "002475", 4) in src.calls
    assert ("forecast", "002475", 2) in src.calls
    assert ("express", "002475", 2) in src.calls
    assert item["forecast"]["source"] == "tushare.forecast"
    assert "p_change_min" in item["forecast"]["raw_fields"]
    assert item["express"]["source"] == "tushare.express"
    assert "yoy_net_profit" in item["express"]["raw_fields"]
    assert item["fina_history"][0]["source"] == "tushare.fina_indicator"
    assert "netprofit_yoy" in item["fina_history"][0]["raw_fields"]


if __name__ == "__main__":
    import sys

    tests = sorted((n, f) for n, f in globals().items() if n.startswith("test_"))
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  [FAIL] {name}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)