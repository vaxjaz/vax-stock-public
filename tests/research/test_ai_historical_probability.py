# -*- coding: utf-8 -*-

import math

import numpy as np
import pandas as pd

from vaxstock.research.ai_historical_probability import (
    build_ai_probability_forecast,
    build_ai_stock_panels,
    build_ai_stock_probability_forecasts,
    build_ai_track_panel,
    run_daily_walk_forward_backtest,
    select_stable_factors,
)


def _fixture_history(session_count=520):
    dates = pd.bdate_range("2024-01-02", periods=session_count)
    codes = [f"6000{i:02d}" for i in range(8)]
    rng = np.random.default_rng(7)
    common = rng.normal(0.0008, 0.012, len(dates))
    stock_rows = []
    for code_index, code in enumerate(codes):
        # The last member is a later IPO.  Its absent pre-listing history must
        # not invalidate all earlier concept dates.
        start = 80 if code_index == len(codes) - 1 else 0
        returns = common + rng.normal(0, 0.006, len(dates))
        close = 20.0 * np.cumprod(1.0 + returns)
        factor = np.where(np.arange(len(dates)) < 250, 1.0, 2.0)
        raw_close = close / factor
        for i in range(start, len(dates)):
            stock_rows.append({
                "trade_date": dates[i].strftime("%Y%m%d"),
                "code": code,
                "close": raw_close[i],
                "adj_factor": factor[i],
                "turnover_rate": 2.0 + abs(returns[i]) * 40,
                "pe_ttm": 25.0 + code_index + math.sin(i / 30),
                "pb": 3.0 + code_index / 10,
                "total_mv": 100000 + code_index * 1000,
            })
    benchmark_close = 100.0 * np.cumprod(1.0 + common * 0.45)
    benchmark_rows = [
        {
            "trade_date": date.strftime("%Y%m%d"),
            "close": benchmark_close[i],
        }
        for i, date in enumerate(dates)
    ]
    anchor_dates = pd.bdate_range(
        dates[0] - pd.Timedelta(days=2),
        dates[-1],
    )
    anchor_rows = []
    for symbol_index, symbol in enumerate(
        ("NVDA", "SOXX", "QQQ", "^VIX", "^TNX", "DX-Y.NYB")
    ):
        anchor_returns = np.resize(common, len(anchor_dates))
        if symbol == "^VIX":
            anchor_returns = -anchor_returns
        close = (100 + symbol_index) * np.cumprod(1 + anchor_returns)
        anchor_rows.extend({
            "session_date": date.strftime("%Y%m%d"),
            "symbol": symbol,
            "adj_close": close[i],
        } for i, date in enumerate(anchor_dates))
    return codes, stock_rows, benchmark_rows, anchor_rows


def test_panel_is_reconstructed_from_adjusted_history_and_allows_later_ipo():
    codes, stocks, benchmark, anchors = _fixture_history(320)
    panel, audit = build_ai_track_panel(
        stock_rows=stocks,
        benchmark_rows=benchmark,
        anchor_rows=anchors,
        universe_codes=codes,
        horizons=[1, 5],
    )

    assert audit["configured_member_count"] == 8
    assert audit["membership_semantics"].startswith(
        "current_constituent_historical_proxy"
    )
    assert panel["track_return_1d"].iloc[250] < 0.20
    assert panel["member_count"].iloc[20] == 7
    assert panel["member_count"].iloc[100] == 8
    assert panel["target_abs_return_5"].notna().sum() > 250
    assert panel.index.equals(panel.index.sort_values())


def test_stable_select_caps_each_semantic_family():
    codes, stocks, benchmark, anchors = _fixture_history(420)
    panel, _ = build_ai_track_panel(
        stock_rows=stocks,
        benchmark_rows=benchmark,
        anchor_rows=anchors,
        universe_codes=codes,
        horizons=[5],
    )
    training = panel[
        panel["target_abs_return_5"].notna()
    ]
    selected = select_stable_factors(
        training,
        target_field="target_abs_return_5",
        horizon=5,
    )

    family_counts = {}
    for row in selected:
        family_counts[row["family"]] = family_counts.get(row["family"], 0) + 1
    assert len(selected) <= 6
    assert max(family_counts.values(), default=0) <= 2
    assert all(row["independent_sessions"] > 0 for row in selected)


def test_forecast_uses_historical_panel_not_legacy_evidence_lines():
    codes, stocks, benchmark, anchors = _fixture_history()
    panel, audit = build_ai_track_panel(
        stock_rows=stocks,
        benchmark_rows=benchmark,
        anchor_rows=anchors,
        universe_codes=codes,
        horizons=[1, 5],
    )
    result = build_ai_probability_forecast(
        panel=panel,
        panel_audit=audit,
        horizons=[1, 5],
        run_validation=False,
    )

    assert result["as_of_trade_date"] == panel.index[-1].strftime("%Y%m%d")
    assert result["current_member_count"] == 8
    assert result["production_eligible"] is False
    assert result["evidence_status"] == "historical_walk_forward_research"
    for horizon in ("1", "5"):
        absolute = result["horizons"][horizon]["absolute_direction"]
        excess = result["horizons"][horizon]["benchmark_excess"]
        assert absolute["status"] in {"estimated", "abstain"}
        assert excess["status"] in {"estimated", "abstain"}
        if absolute["status"] == "estimated":
            assert 0 <= absolute["probability_positive"] <= 1
            assert absolute["selected_factors"]


def test_one_fresh_anchor_cannot_hide_another_anchor_becoming_stale():
    codes, stocks, benchmark, anchors = _fixture_history(120)
    last_date = benchmark[-1]["trade_date"]
    stale_soxx = [
        row for row in anchors
        if not (
            row["symbol"] == "SOXX"
            and row["session_date"] > benchmark[-8]["trade_date"]
        )
    ]
    panel, audit = build_ai_track_panel(
        stock_rows=stocks,
        benchmark_rows=benchmark,
        anchor_rows=stale_soxx,
        universe_codes=codes,
        horizons=[1],
    )

    assert panel.loc[pd.Timestamp(last_date), "nvda_return_1d"] == (
        panel.loc[pd.Timestamp(last_date), "nvda_return_1d"]
    )
    assert pd.isna(panel.loc[pd.Timestamp(last_date), "soxx_return_1d"])
    assert audit["anchor_alignment"]["per_symbol"]["SOXX"][
        "stale_a_share_dates"
    ] > 0


def test_stock_layer_estimates_excess_against_ai_track_not_market_benchmark():
    codes, stocks, benchmark, anchors = _fixture_history(420)
    panel, _ = build_ai_track_panel(
        stock_rows=stocks,
        benchmark_rows=benchmark,
        anchor_rows=anchors,
        universe_codes=codes,
        horizons=[5],
    )
    stock_panels = build_ai_stock_panels(
        stock_rows=stocks,
        track_panel=panel,
        universe_codes=codes,
        horizons=[5],
    )
    forecasts = build_ai_stock_probability_forecasts(
        stock_panels=stock_panels,
        as_of_trade_date=panel.index[-1].strftime("%Y%m%d"),
        horizons=[5],
    )

    assert set(forecasts) == set(codes)
    row = forecasts[codes[0]]["horizons"]["5"]
    assert "ai_track_excess" in row
    assert row["validation_status"] == "not_run_for_stock_layer_v1"
    assert forecasts[codes[0]]["production_eligible"] is False


def test_daily_backtest_keeps_every_date_and_builds_offset_cohorts():
    codes, stocks, benchmark, anchors = _fixture_history(360)
    panel, _ = build_ai_track_panel(
        stock_rows=stocks,
        benchmark_rows=benchmark,
        anchor_rows=anchors,
        universe_codes=codes,
        horizons=[5],
    )

    result = run_daily_walk_forward_backtest(
        panel,
        horizon=5,
        target_kind="excess",
        bootstrap_repetitions=20,
    )

    assert result["attempted_daily_dates"] == len(panel) - 120
    assert result["estimated_daily_predictions"] > 100
    assert result["settled_daily_predictions"] > 100
    assert result["pending_daily_predictions"] == 5
    assert len(result["offset_cohorts"]) == 5
    estimated_rows = [
        row for row in result["rows"]
        if row["forecast_status"] == "estimated"
    ]
    assert len({
        row["forecast_trade_date"] for row in estimated_rows
    }) == len(estimated_rows)
    for offset in range(5):
        positions = [
            row["session_position"] for row in estimated_rows
            if row["evaluation_status"] == "settled"
            and row["cohort_offset"] == offset
        ]
        assert all(
            right - left == 5
            for left, right in zip(positions, positions[1:])
        )


def test_daily_backtest_excludes_labels_not_known_at_forecast_time():
    codes, stocks, benchmark, anchors = _fixture_history(360)
    panel, _ = build_ai_track_panel(
        stock_rows=stocks,
        benchmark_rows=benchmark,
        anchor_rows=anchors,
        universe_codes=codes,
        horizons=[5],
    )
    cutoff = panel.index[260]
    kwargs = {
        "horizon": 5,
        "target_kind": "excess",
        "start_trade_date": cutoff.strftime("%Y%m%d"),
        "end_trade_date": cutoff.strftime("%Y%m%d"),
        "bootstrap_repetitions": 0,
    }
    original = run_daily_walk_forward_backtest(panel, **kwargs)
    poisoned = panel.copy()
    illegal = (
        (poisoned.index < cutoff)
        & (poisoned["target_date_5"] > cutoff)
    )
    poisoned.loc[illegal, "target_excess_return_5"] = 999.0
    replayed = run_daily_walk_forward_backtest(poisoned, **kwargs)

    original_row = original["rows"][0]
    replayed_row = replayed["rows"][0]
    assert original_row["forecast_status"] == "estimated"
    assert replayed_row["forecast_status"] == "estimated"
    assert (
        original_row["probability_positive"]
        == replayed_row["probability_positive"]
    )
    assert (
        original_row["selected_factor_ids"]
        == replayed_row["selected_factor_ids"]
    )
