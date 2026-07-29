# -*- coding: utf-8 -*-

import json

import numpy as np
import pandas as pd

from vaxstock.services.ai_probability_refresh import (
    _ai_universe,
    load_dataset,
    run_ai_probability_refresh,
)


class FakeTushareSource:
    enabled = True

    def __init__(self, dates):
        self.dates = dates

    def get_daily_history_range(self, code, **_):
        index = int(str(code)[-2:]) % 7
        changes = np.sin(np.arange(len(self.dates)) / 13 + index) * 0.01
        adjusted = (20 + index) * np.cumprod(1 + changes)
        factor = np.where(np.arange(len(self.dates)) < 100, 1.0, 1.5)
        return [
            {
                "ts_code": f"{code}.SH",
                "trade_date": date.strftime("%Y%m%d"),
                "close": adjusted[i] / factor[i],
                "vol": 1000.0 + i,
                "amount": 10000.0 + i,
            }
            for i, date in enumerate(self.dates)
        ]

    def get_adj_factor_history_range(self, code, **_):
        factor = np.where(np.arange(len(self.dates)) < 100, 1.0, 1.5)
        return [
            {
                "ts_code": f"{code}.SH",
                "trade_date": date.strftime("%Y%m%d"),
                "adj_factor": factor[i],
            }
            for i, date in enumerate(self.dates)
        ]

    def get_daily_basic_history_range(self, code, **_):
        return [
            {
                "ts_code": f"{code}.SH",
                "trade_date": date.strftime("%Y%m%d"),
                "turnover_rate": 2.0 + i % 5,
                "pe_ttm": 20.0 + int(str(code)[-1]),
                "pb": 3.0,
                "total_mv": 100000.0,
            }
            for i, date in enumerate(self.dates)
        ]

    def get_index_daily_history_range(self, index_code, **_):
        close = 100 * np.cumprod(
            1 + np.sin(np.arange(len(self.dates)) / 17) * 0.004
        )
        return [
            {
                "ts_code": index_code,
                "trade_date": date.strftime("%Y%m%d"),
                "close": close[i],
            }
            for i, date in enumerate(self.dates)
        ]


def _anchors(dates):
    def fetcher(*, symbols, **_):
        rows = []
        base_returns = np.sin(np.arange(len(dates)) / 11) * 0.008
        for offset, symbol in enumerate(symbols):
            returns = -base_returns if symbol == "^VIX" else base_returns
            close = (100 + offset) * np.cumprod(1 + returns)
            rows.extend({
                "session_date": date.strftime("%Y%m%d"),
                "symbol": symbol,
                "adj_close": close[i],
                "source": "fixture",
            } for i, date in enumerate(dates))
        return rows

    return fetcher


def test_refresh_builds_immutable_historical_dataset_and_reuses_it(tmp_path):
    dates = pd.bdate_range("2025-01-02", periods=220)
    kwargs = {
        "start_date": dates[0].strftime("%Y%m%d"),
        "end_date": dates[-1].strftime("%Y%m%d"),
        "output_dir": tmp_path / "ai",
        "source": FakeTushareSource(dates),
        "anchor_fetcher": _anchors(dates),
        "run_validation": False,
        "horizons": [1, 5],
    }
    first = run_ai_probability_refresh(**kwargs)
    second = run_ai_probability_refresh(**kwargs)

    assert first["status"] == "complete"
    assert first["write_status"] == "written"
    assert second["write_status"] == "already_complete"
    assert first["dataset_digest"] == second["dataset_digest"]
    assert first["member_count"] == len(_ai_universe())
    assert (tmp_path / "ai" / "latest.json").exists()
    forecast = json.loads(
        open(first["forecast_path"], encoding="utf-8").read()
    )
    assert forecast["model_version"] == "ai_historical_probability_v1"
    assert forecast["production_eligible"] is False
    assert forecast["stock_probability_count"] == len(_ai_universe())
    assert len(forecast["stock_probabilities"]) == len(_ai_universe())
    assert "legacy" not in json.dumps(forecast).lower()

    stocks, benchmark, anchors, manifest = load_dataset(
        first["dataset_dir"]
    )
    assert stocks and benchmark and anchors
    assert manifest["dataset_digest"] == first["dataset_digest"]


def test_replay_from_dataset_does_not_call_network_source(tmp_path):
    dates = pd.bdate_range("2025-01-02", periods=180)
    first = run_ai_probability_refresh(
        start_date=dates[0].strftime("%Y%m%d"),
        end_date=dates[-1].strftime("%Y%m%d"),
        output_dir=tmp_path / "ai",
        source=FakeTushareSource(dates),
        anchor_fetcher=_anchors(dates),
        run_validation=False,
        horizons=[1],
    )
    replay = run_ai_probability_refresh(
        start_date=dates[0].strftime("%Y%m%d"),
        end_date=dates[-1].strftime("%Y%m%d"),
        output_dir=tmp_path / "ai",
        dataset_dir=first["dataset_dir"],
        run_validation=False,
        horizons=[1],
    )

    assert replay["status"] == "complete"
    assert replay["write_status"] == "already_complete"
    assert replay["dataset_digest"] == first["dataset_digest"]
