# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd

from vaxstock.research.ai_probability_v2 import (
    CANDIDATES,
    DERIVATIVE_SPECS,
    build_v2_feature_panel,
    run_v2_daily_backtest,
    select_candidate,
)


def _signal_panel(session_count=760, horizon=5):
    dates = pd.bdate_range("2022-01-03", periods=session_count)
    rng = np.random.default_rng(17)
    latent = np.sin(np.arange(session_count) / 18.0)
    panel = pd.DataFrame(index=dates)
    panel["track_return_5d"] = latent * 0.03
    panel["track_return_20d"] = latent * 0.06
    panel["track_excess_5d"] = latent * 0.02
    panel["track_excess_20d"] = latent * 0.04
    panel["breadth_positive_1d"] = 0.5 + latent * 0.2
    panel["breadth_above_ma20"] = 0.5 + latent * 0.3
    panel["track_drawdown_60d"] = -0.1 + latent * 0.05
    panel["cross_section_dispersion_5d"] = 0.03 - latent * 0.005
    panel["track_volatility_20d"] = 0.3 - latent * 0.03
    panel["turnover_z_60d"] = latent + rng.normal(0, 0.1, session_count)
    panel["pe_ttm_percentile_252d"] = 0.5 + latent * 0.2
    panel["nvda_return_1d"] = latent * 0.02
    panel["nvda_return_5d"] = latent * 0.05
    panel["soxx_return_1d"] = latent * 0.015
    panel["soxx_return_5d"] = latent * 0.04
    panel["qqq_return_5d"] = latent * 0.025
    panel["vix_level"] = 20 - latent * 3
    panel["vix_return_5d"] = -latent * 0.05
    panel["tnx_return_5d"] = -latent * 0.01
    panel["dxy_return_5d"] = -latent * 0.01
    forward = np.roll(latent, -horizon) * 0.03
    forward += rng.normal(0, 0.004, session_count)
    forward[-horizon:] = np.nan
    panel[f"target_excess_return_{horizon}"] = forward
    panel[f"target_date_{horizon}"] = pd.Series(
        dates, index=dates
    ).shift(-horizon)
    return panel


def test_derivatives_use_only_current_and_past_values():
    panel = _signal_panel(300)
    cutoff = panel.index[220]
    original = build_v2_feature_panel(panel)
    poisoned = panel.copy()
    poisoned.loc[poisoned.index > cutoff, "breadth_above_ma20"] = 999.0
    replayed = build_v2_feature_panel(poisoned)

    assert original.loc[
        :cutoff, "d_breadth_above_ma20_5d"
    ].equals(replayed.loc[:cutoff, "d_breadth_above_ma20_5d"])
    assert set(DERIVATIVE_SPECS).issubset(original.columns)


def test_select_uses_only_pre_registered_candidate_contract():
    panel = build_v2_feature_panel(_signal_panel())
    cutoff = panel.index[650]
    history = panel.loc[panel.index < cutoff]
    history = history[
        history["target_date_5"].notna()
        & (history["target_date_5"] <= cutoff)
    ]
    result = select_candidate(
        history,
        target_field="target_excess_return_5",
        target_date_field="target_date_5",
        minimum_fit_rows=120,
        validation_block=40,
    )

    assert result["status"] in {"selected", "abstain"}
    evaluated_ids = {
        row["candidate_id"] for row in result["candidate_evaluations"]
    }
    assert evaluated_ids == {candidate.candidate_id for candidate in CANDIDATES}


def test_outer_backtest_excludes_labels_unknown_at_forecast_date():
    panel = _signal_panel(620)
    cutoff = panel.index[500]
    kwargs = {
        "horizon": 5,
        "minimum_fit_rows": 120,
        "inner_validation_block": 40,
        "bootstrap_repetitions": 10,
    }
    original = run_v2_daily_backtest(panel.loc[:cutoff], **kwargs)
    poisoned = panel.loc[:cutoff].copy()
    illegal = poisoned["target_date_5"] > cutoff
    poisoned.loc[illegal, "target_excess_return_5"] = 999.0
    replayed = run_v2_daily_backtest(poisoned, **kwargs)

    original_row = original["rows"][-1]
    replayed_row = replayed["rows"][-1]
    assert original_row["forecast_status"] == replayed_row["forecast_status"]
    assert original_row.get("candidate_id") == replayed_row.get("candidate_id")
    assert original_row.get("probability_positive") == (
        replayed_row.get("probability_positive")
    )


def test_publication_gate_is_explicit_and_never_defaults_to_neutral():
    result = run_v2_daily_backtest(
        _signal_panel(640),
        horizon=5,
        minimum_fit_rows=120,
        inner_validation_block=40,
        bootstrap_repetitions=20,
    )

    assert result["attempted_daily_dates"] == 520
    assert result["publication_gate"]["status"] in {
        "abstain",
        "research_numeric_edge",
        "robust_numeric_edge",
    }
    assert set(result["publication_gate"]["checks"]) == {
        "minimum_120_settled_predictions",
        "positive_skill_vs_expanding_base",
        "positive_skill_vs_rolling_base",
        "majority_positive_offset_cohorts",
        "positive_block_bootstrap_median",
    }
    assert all(
        row.get("probability_positive") is None
        for row in result["rows"]
        if row["forecast_status"] == "abstain"
    )

