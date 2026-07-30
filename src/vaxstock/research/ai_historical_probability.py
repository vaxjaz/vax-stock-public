# -*- coding: utf-8 -*-
"""Historical probability model for the A-share AI infrastructure basket.

This module is intentionally independent from the legacy A/B/C/D evidence
lines.  Its only inputs are reconstructable historical market rows:

* adjusted A-share closes and daily valuation/liquidity fields;
* an adjusted benchmark close;
* completed overseas-session closes for pre-registered anchors.

The module performs no network or filesystem I/O.  It builds an equal-weight
AI basket from whichever fixed-proxy members were actually listed on each
date, derives a small semantic feature set, selects factors using historical
stability, and estimates direction probabilities from similar past states.
All labels are forward returns derived from adjusted closes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd


MODEL_VERSION = "ai_historical_probability_v1"
GROUP_VERSION = "ai_semantic_state_v1"
SELECT_VERSION = "stable_rank_select_v1"
UNIVERSE_VERSION = "current_ai_members_fixed_proxy_v1"
DEFAULT_HORIZONS = (1, 5, 20)
MINIMUM_MEMBERS = 5
MINIMUM_TRAINING_SESSIONS = 120
MAX_SELECTED_FACTORS = 6
MAX_FACTORS_PER_FAMILY = 2
PRIOR_STRENGTH = 8.0
DAILY_BACKTEST_VERSION = "ai_daily_walk_forward_v1"

ANCHOR_SYMBOLS = ("NVDA", "SOXX", "QQQ", "^VIX", "^TNX", "DX-Y.NYB")
ANCHOR_KEYS = {
    "NVDA": "nvda",
    "SOXX": "soxx",
    "QQQ": "qqq",
    "^VIX": "vix",
    "^TNX": "tnx",
    "DX-Y.NYB": "dxy",
}


@dataclass(frozen=True)
class FeatureSpec:
    family: str
    description: str


FEATURE_REGISTRY: Dict[str, FeatureSpec] = {
    "track_return_1d": FeatureSpec("track_trend", "AI等权组合1日收益"),
    "track_return_5d": FeatureSpec("track_trend", "AI等权组合5日收益"),
    "track_return_20d": FeatureSpec("track_trend", "AI等权组合20日收益"),
    "track_excess_5d": FeatureSpec("relative_trend", "AI组合相对沪深300的5日收益"),
    "track_excess_20d": FeatureSpec("relative_trend", "AI组合相对沪深300的20日收益"),
    "breadth_positive_1d": FeatureSpec("internal_breadth", "AI成分当日上涨比例"),
    "breadth_above_ma20": FeatureSpec("internal_breadth", "AI成分站上20日均线比例"),
    "cross_section_dispersion_5d": FeatureSpec("internal_risk", "成分5日收益离散度"),
    "track_volatility_20d": FeatureSpec("internal_risk", "AI组合20日年化波动"),
    "track_drawdown_60d": FeatureSpec("internal_risk", "AI组合相对60日高点回撤"),
    "turnover_median": FeatureSpec("liquidity", "AI成分换手率中位数"),
    "turnover_z_60d": FeatureSpec("liquidity", "组合换手率相对60日历史的Z值"),
    "pe_ttm_median": FeatureSpec("valuation", "AI成分PE-TTM中位数"),
    "pe_ttm_percentile_252d": FeatureSpec("valuation", "组合PE中位数252日分位"),
    "pb_median": FeatureSpec("valuation", "AI成分PB中位数"),
    "nvda_return_1d": FeatureSpec("external_ai", "英伟达最近完成交易日收益"),
    "nvda_return_5d": FeatureSpec("external_ai", "英伟达5日收益"),
    "soxx_return_1d": FeatureSpec("external_ai", "SOXX最近完成交易日收益"),
    "soxx_return_5d": FeatureSpec("external_ai", "SOXX 5日收益"),
    "qqq_return_1d": FeatureSpec("external_risk", "QQQ最近完成交易日收益"),
    "qqq_return_5d": FeatureSpec("external_risk", "QQQ 5日收益"),
    "vix_level": FeatureSpec("external_risk", "VIX收盘水平"),
    "vix_return_5d": FeatureSpec("external_risk", "VIX 5日变化"),
    "tnx_return_5d": FeatureSpec("external_macro", "美国10年期收益率5日变化"),
    "dxy_return_5d": FeatureSpec("external_macro", "美元指数5日变化"),
    "stock_return_5d": FeatureSpec("stock_trend", "个股5日收益"),
    "stock_return_20d": FeatureSpec("stock_trend", "个股20日收益"),
    "stock_excess_track_5d": FeatureSpec("stock_relative", "个股相对AI组合5日收益"),
    "stock_excess_track_20d": FeatureSpec("stock_relative", "个股相对AI组合20日收益"),
    "stock_volatility_20d": FeatureSpec("stock_risk", "个股20日年化波动"),
    "stock_drawdown_60d": FeatureSpec("stock_risk", "个股相对60日高点回撤"),
    "stock_turnover_z_60d": FeatureSpec("stock_liquidity", "个股换手率60日Z值"),
    "stock_pe_percentile_252d": FeatureSpec("stock_valuation", "个股PE-TTM 252日分位"),
}


class HistoricalProbabilityError(ValueError):
    """Raised when raw historical inputs cannot support an honest model."""


def _date_series(frame: pd.DataFrame, field: str) -> pd.Series:
    if field not in frame:
        raise HistoricalProbabilityError(f"missing required field: {field}")
    parsed = pd.to_datetime(
        frame[field].astype(str),
        format="%Y%m%d",
        errors="coerce",
    )
    if parsed.isna().any():
        raise HistoricalProbabilityError(f"{field} contains invalid YYYYMMDD")
    return parsed


def _number_series(frame: pd.DataFrame, field: str) -> pd.Series:
    if field not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[field], errors="coerce")


def _normalise_stock_rows(
    rows: Iterable[Mapping[str, Any]],
    universe_codes: Sequence[str],
) -> pd.DataFrame:
    frame = pd.DataFrame([dict(row) for row in rows])
    if frame.empty:
        raise HistoricalProbabilityError("stock history is empty")
    frame["trade_date"] = _date_series(frame, "trade_date")
    code_field = "code" if "code" in frame else "ts_code"
    if code_field not in frame:
        raise HistoricalProbabilityError("stock history missing code/ts_code")
    frame["code"] = (
        frame[code_field].astype(str).str.split(".").str[0].str.zfill(6)
    )
    allowed = {str(code).split(".")[0].zfill(6) for code in universe_codes}
    frame = frame[frame["code"].isin(allowed)].copy()
    if frame.empty:
        raise HistoricalProbabilityError("no stock rows match AI universe")

    close = _number_series(frame, "adj_close")
    if close.isna().all():
        raw_close = _number_series(frame, "close")
        factor = _number_series(frame, "adj_factor")
        close = raw_close * factor
    frame["adj_close"] = close
    if (frame["adj_close"].dropna() <= 0).any():
        raise HistoricalProbabilityError("adjusted closes must be positive")
    for field in ("turnover_rate", "pe_ttm", "pb", "total_mv"):
        frame[field] = _number_series(frame, field)
    frame = frame.drop_duplicates(["trade_date", "code"], keep="last")
    return frame.sort_values(["trade_date", "code"])


def _normalise_benchmark_rows(
    rows: Iterable[Mapping[str, Any]],
) -> pd.DataFrame:
    frame = pd.DataFrame([dict(row) for row in rows])
    if frame.empty:
        raise HistoricalProbabilityError("benchmark history is empty")
    frame["trade_date"] = _date_series(frame, "trade_date")
    close = _number_series(frame, "adj_close")
    if close.isna().all():
        close = _number_series(frame, "close")
    frame["adj_close"] = close
    frame = frame.dropna(subset=["adj_close"])
    frame = frame[frame["adj_close"] > 0]
    frame = frame.drop_duplicates(["trade_date"], keep="last")
    if frame.empty:
        raise HistoricalProbabilityError("benchmark has no valid close")
    return frame.sort_values("trade_date")


def _normalise_anchor_rows(
    rows: Iterable[Mapping[str, Any]],
) -> pd.DataFrame:
    frame = pd.DataFrame([dict(row) for row in rows])
    if frame.empty:
        raise HistoricalProbabilityError("anchor history is empty")
    date_field = "session_date" if "session_date" in frame else "trade_date"
    frame["session_date"] = _date_series(frame, date_field)
    if "symbol" not in frame:
        raise HistoricalProbabilityError("anchor history missing symbol")
    frame["symbol"] = frame["symbol"].astype(str)
    close = _number_series(frame, "adj_close")
    if close.isna().all():
        close = _number_series(frame, "close")
    frame["adj_close"] = close
    frame = frame[
        frame["symbol"].isin(ANCHOR_SYMBOLS)
        & frame["adj_close"].notna()
        & (frame["adj_close"] > 0)
    ].copy()
    frame = frame.drop_duplicates(["session_date", "symbol"], keep="last")
    if frame.empty:
        raise HistoricalProbabilityError("no valid registered anchor rows")
    return frame.sort_values(["session_date", "symbol"])


def _rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    def _last_rank(values: np.ndarray) -> float:
        valid = values[np.isfinite(values)]
        if len(valid) < max(20, window // 4):
            return np.nan
        last = valid[-1]
        return float(np.mean(valid <= last))

    return series.rolling(window, min_periods=max(20, window // 4)).apply(
        _last_rank,
        raw=True,
    )


def _anchor_features(
    anchor_frame: pd.DataFrame,
    a_dates: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    close = anchor_frame.pivot(
        index="session_date",
        columns="symbol",
        values="adj_close",
    ).sort_index()
    aligned = pd.DataFrame(index=a_dates)
    stale_audit: Dict[str, Any] = {}
    for symbol, key in ANCHOR_KEYS.items():
        if symbol not in close:
            continue
        symbol_close = close[symbol].dropna()
        raw_features = pd.DataFrame(index=symbol_close.index)
        raw_features[f"{key}_return_1d"] = symbol_close.pct_change(
            fill_method=None
        )
        raw_features[f"{key}_return_5d"] = symbol_close.pct_change(
            5, fill_method=None
        )
        if symbol == "^VIX":
            raw_features["vix_level"] = symbol_close
        union = raw_features.index.union(a_dates).sort_values()
        symbol_aligned = raw_features.reindex(union).ffill().reindex(a_dates)
        source_dates = pd.Series(
            symbol_close.index,
            index=symbol_close.index,
        )
        source_dates = source_dates.reindex(union).ffill().reindex(a_dates)
        stale_days = (
            pd.Series(a_dates, index=a_dates) - source_dates
        ).dt.days.astype("float")
        # A completed US session on the same calendar date is available at
        # the following A-share pre-open decision.  More than four calendar
        # days is stale; the test is per symbol, never hidden by another
        # anchor having a newer session.
        symbol_aligned.loc[stale_days > 4, :] = np.nan
        for field in symbol_aligned:
            aligned[field] = symbol_aligned[field]
        stale_audit[symbol] = {
            "first_session": symbol_close.index[0].strftime("%Y%m%d"),
            "last_session": symbol_close.index[-1].strftime("%Y%m%d"),
            "stale_a_share_dates": int((stale_days > 4).sum()),
        }
    audit = {
        "registered_symbols": list(ANCHOR_SYMBOLS),
        "available_symbols": sorted(set(close.columns)),
        "missing_symbols": sorted(set(ANCHOR_SYMBOLS) - set(close.columns)),
        "max_alignment_stale_calendar_days": 4,
        "per_symbol": stale_audit,
    }
    return aligned, audit


def build_ai_track_panel(
    *,
    stock_rows: Iterable[Mapping[str, Any]],
    benchmark_rows: Iterable[Mapping[str, Any]],
    anchor_rows: Iterable[Mapping[str, Any]],
    universe_codes: Sequence[str],
    minimum_members: int = MINIMUM_MEMBERS,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """Build one reconstructable daily AI track panel.

    Membership semantics are explicit: this is a fixed *current constituent*
    proxy, but a member only contributes after it has a valid listed-market
    return.  Missing pre-IPO rows therefore do not invalidate the date.
    """

    codes = sorted({str(code).split(".")[0].zfill(6) for code in universe_codes})
    if len(codes) < minimum_members:
        raise HistoricalProbabilityError(
            f"AI universe has {len(codes)} members < {minimum_members}"
        )
    stocks = _normalise_stock_rows(stock_rows, codes)
    benchmark = _normalise_benchmark_rows(benchmark_rows)
    anchors = _normalise_anchor_rows(anchor_rows)

    close = stocks.pivot(
        index="trade_date", columns="code", values="adj_close"
    ).sort_index()
    benchmark_close = benchmark.set_index("trade_date")["adj_close"].sort_index()
    dates = close.index.intersection(benchmark_close.index).sort_values()
    close = close.reindex(dates)
    benchmark_close = benchmark_close.reindex(dates)
    stock_returns = close.pct_change(fill_method=None)
    valid_member_count = stock_returns.notna().sum(axis=1)
    basket_return = stock_returns.mean(axis=1, skipna=True).where(
        valid_member_count >= minimum_members
    )
    first_valid = basket_return.first_valid_index()
    if first_valid is None:
        raise HistoricalProbabilityError("no date meets minimum AI members")
    basket_index = (1.0 + basket_return.fillna(0.0)).cumprod()
    basket_index.loc[basket_index.index < first_valid] = np.nan
    benchmark_return = benchmark_close.pct_change(fill_method=None)
    benchmark_index = benchmark_close / benchmark_close.dropna().iloc[0]

    panel = pd.DataFrame(index=dates)
    panel["member_count"] = valid_member_count
    panel["universe_coverage"] = valid_member_count / len(codes)
    panel["track_return_1d"] = basket_return
    panel["track_return_5d"] = basket_index.pct_change(5, fill_method=None)
    panel["track_return_20d"] = basket_index.pct_change(20, fill_method=None)
    panel["track_excess_5d"] = (
        panel["track_return_5d"]
        - benchmark_index.pct_change(5, fill_method=None)
    )
    panel["track_excess_20d"] = (
        panel["track_return_20d"]
        - benchmark_index.pct_change(20, fill_method=None)
    )
    panel["breadth_positive_1d"] = (
        stock_returns.gt(0).sum(axis=1) / valid_member_count.replace(0, np.nan)
    )
    ma20 = close.rolling(20, min_periods=20).mean()
    ma_valid = (close.notna() & ma20.notna()).sum(axis=1)
    panel["breadth_above_ma20"] = (
        (close > ma20).sum(axis=1) / ma_valid.replace(0, np.nan)
    )
    stock_return_5d = close.pct_change(5, fill_method=None)
    panel["cross_section_dispersion_5d"] = stock_return_5d.std(axis=1)
    panel["track_volatility_20d"] = basket_return.rolling(
        20, min_periods=20
    ).std() * math.sqrt(252)
    panel["track_drawdown_60d"] = (
        basket_index / basket_index.rolling(60, min_periods=20).max() - 1.0
    )

    for raw_field, output_field in (
        ("turnover_rate", "turnover_median"),
        ("pe_ttm", "pe_ttm_median"),
        ("pb", "pb_median"),
    ):
        values = stocks.pivot(
            index="trade_date", columns="code", values=raw_field
        ).reindex(dates)
        panel[output_field] = values.median(axis=1, skipna=True)
    turnover_mean = panel["turnover_median"].rolling(60, min_periods=20).mean()
    turnover_std = panel["turnover_median"].rolling(60, min_periods=20).std()
    panel["turnover_z_60d"] = (
        (panel["turnover_median"] - turnover_mean)
        / turnover_std.replace(0, np.nan)
    )
    panel["pe_ttm_percentile_252d"] = _rolling_percentile(
        panel["pe_ttm_median"], 252
    )

    aligned_anchors, anchor_audit = _anchor_features(anchors, dates)
    for field in FEATURE_REGISTRY:
        if field in aligned_anchors:
            panel[field] = aligned_anchors[field]

    for raw_horizon in horizons:
        horizon = int(raw_horizon)
        if horizon <= 0:
            raise HistoricalProbabilityError("horizons must be positive")
        panel[f"target_date_{horizon}"] = pd.Series(
            panel.index, index=panel.index
        ).shift(-horizon)
        forward_track = basket_index.shift(-horizon) / basket_index - 1.0
        forward_benchmark = (
            benchmark_index.shift(-horizon) / benchmark_index - 1.0
        )
        panel[f"target_abs_return_{horizon}"] = forward_track
        panel[f"target_excess_return_{horizon}"] = (
            forward_track - forward_benchmark
        )

    audit = {
        "model_version": MODEL_VERSION,
        "universe_version": UNIVERSE_VERSION,
        "membership_semantics": (
            "current_constituent_historical_proxy; members enter when a "
            "valid listed-market return first exists"
        ),
        "universe_codes": codes,
        "configured_member_count": len(codes),
        "minimum_members": minimum_members,
        "first_eligible_trade_date": first_valid.strftime("%Y%m%d"),
        "last_trade_date": dates[-1].strftime("%Y%m%d"),
        "trade_dates": len(dates),
        "anchor_alignment": anchor_audit,
        "label_semantics": (
            "adjusted close-to-close direction from A-share T close; "
            "overseas session T is available at the next A-share pre-open"
        ),
    }
    return panel, audit


def _non_overlapping(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if frame.empty or horizon <= 1:
        return frame
    positions = list(range(len(frame) - 1, -1, -horizon))
    return frame.iloc[sorted(positions)]


def _spearman(x: pd.Series, y: pd.Series) -> float:
    valid = pd.concat([x, y], axis=1).dropna()
    if len(valid) < 10:
        return math.nan
    if valid.iloc[:, 0].nunique() < 2 or valid.iloc[:, 1].nunique() < 2:
        return math.nan
    value = valid.iloc[:, 0].rank().corr(valid.iloc[:, 1].rank())
    return float(value) if pd.notna(value) else math.nan


def select_stable_factors(
    training: pd.DataFrame,
    *,
    target_field: str,
    horizon: int,
    max_factors: int = MAX_SELECTED_FACTORS,
) -> list[Dict[str, Any]]:
    """Select a small, semantically capped set with chronological stability."""

    independent = _non_overlapping(training.sort_index(), horizon)
    candidates = []
    for factor_id, spec in FEATURE_REGISTRY.items():
        if factor_id not in independent:
            continue
        usable = independent[[factor_id, target_field]].dropna()
        if len(usable) < max(30, MINIMUM_TRAINING_SESSIONS // horizon):
            continue
        fold_positions = np.array_split(
            np.arange(len(usable)),
            min(3, len(usable) // 20),
        )
        folds = [
            usable.iloc[positions]
            for positions in fold_positions
            if len(positions) >= 20
        ]
        fold_corrs = [
            _spearman(fold[factor_id], fold[target_field])
            for fold in folds
        ]
        fold_corrs = [value for value in fold_corrs if math.isfinite(value)]
        if not fold_corrs:
            continue
        overall = _spearman(usable[factor_id], usable[target_field])
        if not math.isfinite(overall) or overall == 0:
            continue
        sign = 1 if overall > 0 else -1
        stability = sum(
            (value > 0) == (sign > 0) for value in fold_corrs
        ) / len(fold_corrs)
        if stability < (2.0 / 3.0):
            continue
        coverage = len(usable) / max(1, len(independent))
        score = abs(overall) * stability * math.sqrt(coverage)
        candidates.append({
            "factor_id": factor_id,
            "family": spec.family,
            "description": spec.description,
            "independent_sessions": len(usable),
            "spearman": overall,
            "fold_spearman": fold_corrs,
            "sign_stability": stability,
            "coverage": coverage,
            "selection_score": score,
        })

    selected = []
    family_counts: Dict[str, int] = {}
    for row in sorted(
        candidates,
        key=lambda item: (
            -item["selection_score"],
            item["factor_id"],
        ),
    ):
        family = row["family"]
        if family_counts.get(family, 0) >= MAX_FACTORS_PER_FAMILY:
            continue
        selected.append(row)
        family_counts[family] = family_counts.get(family, 0) + 1
        if len(selected) >= max_factors:
            break
    return selected


def _weighted_quantile(
    values: np.ndarray,
    weights: np.ndarray,
    quantile: float,
) -> float:
    order = np.argsort(values)
    sorted_values = values[order]
    sorted_weights = weights[order]
    cumulative = np.cumsum(sorted_weights)
    threshold = quantile * cumulative[-1]
    return float(sorted_values[np.searchsorted(cumulative, threshold)])


def _state_label(
    value: float,
    history: pd.Series,
) -> str:
    valid = history.dropna()
    if len(valid) < 20:
        return "insufficient_history"
    low, high = valid.quantile([0.33, 0.67])
    if value <= low:
        return "low"
    if value >= high:
        return "high"
    return "middle"


def _estimate_at(
    panel: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
    horizon: int,
    target_kind: str,
    minimum_training_sessions: int,
) -> Dict[str, Any]:
    target_field = (
        f"target_abs_return_{horizon}"
        if target_kind == "absolute"
        else f"target_excess_return_{horizon}"
    )
    target_date_field = f"target_date_{horizon}"
    history = panel.loc[panel.index < as_of].copy()
    history = history[
        history[target_date_field].notna()
        & (history[target_date_field] <= as_of)
        & history[target_field].notna()
    ]
    current = panel.loc[as_of]
    if len(history) < minimum_training_sessions:
        return {
            "status": "abstain",
            "reason": "insufficient_historical_sessions",
            "training_sessions": len(history),
            "minimum_training_sessions": minimum_training_sessions,
        }

    selected = select_stable_factors(
        history,
        target_field=target_field,
        horizon=horizon,
    )
    selected = [
        row for row in selected
        if pd.notna(current.get(row["factor_id"]))
    ]
    if not selected:
        return {
            "status": "abstain",
            "reason": "no_stable_current_factor",
            "training_sessions": len(history),
        }

    fields = [row["factor_id"] for row in selected]
    usable = history[[*fields, target_field]].dropna()
    independent = _non_overlapping(usable, horizon)
    if len(independent) < max(20, minimum_training_sessions // horizon):
        return {
            "status": "abstain",
            "reason": "insufficient_independent_sessions",
            "training_sessions": len(usable),
            "independent_sessions": len(independent),
            "selected_factors": selected,
        }

    matrix = independent[fields].astype(float)
    median = matrix.median()
    scale = matrix.quantile(0.75) - matrix.quantile(0.25)
    valid_fields = [
        field for field in fields
        if pd.notna(scale[field]) and float(scale[field]) > 0
    ]
    if not valid_fields:
        return {
            "status": "abstain",
            "reason": "selected_factors_have_zero_scale",
            "selected_factors": selected,
        }
    matrix = matrix[valid_fields]
    current_vector = current[valid_fields].astype(float)
    scaled = (matrix - median[valid_fields]) / scale[valid_fields]
    scaled_current = (
        current_vector - median[valid_fields]
    ) / scale[valid_fields]
    distances = np.sqrt(
        np.square(scaled - scaled_current).mean(axis=1).to_numpy(float)
    )
    k = min(
        len(independent),
        max(20, min(80, int(round(math.sqrt(len(independent)) * 4)))),
    )
    nearest_positions = np.argsort(distances)[:k]
    nearest = independent.iloc[nearest_positions]
    nearest_distances = distances[nearest_positions]
    positive_scale = np.median(nearest_distances[nearest_distances > 0])
    if not math.isfinite(positive_scale):
        positive_scale = 1.0
    weights = np.exp(-nearest_distances / max(positive_scale, 1e-9))
    outcomes = nearest[target_field].to_numpy(float)
    wins = (outcomes > 0).astype(float)
    base_probability = float((independent[target_field] > 0).mean())
    alpha = float(np.dot(weights, wins) + PRIOR_STRENGTH * base_probability)
    beta = float(
        np.dot(weights, 1.0 - wins)
        + PRIOR_STRENGTH * (1.0 - base_probability)
    )
    probability = alpha / (alpha + beta)
    posterior_variance = (
        alpha * beta
        / ((alpha + beta) ** 2 * (alpha + beta + 1.0))
    )
    z90 = NormalDist().inv_cdf(0.95)
    interval = [
        max(0.0, probability - z90 * math.sqrt(posterior_variance)),
        min(1.0, probability + z90 * math.sqrt(posterior_variance)),
    ]
    neighbour_mean = float(np.average(outcomes, weights=weights))
    historical_mean = float(independent[target_field].mean())
    expected_return = (
        np.sum(weights) * neighbour_mean
        + PRIOR_STRENGTH * historical_mean
    ) / (np.sum(weights) + PRIOR_STRENGTH)
    direction = (
        "up"
        if probability >= 0.55
        else ("down" if probability <= 0.45 else "neutral")
    )
    effective_n = float(
        np.square(np.sum(weights)) / np.sum(np.square(weights))
    )
    selected_by_id = {row["factor_id"]: row for row in selected}
    current_states = {
        field: {
            "value": float(current[field]),
            "state": _state_label(float(current[field]), history[field]),
            "family": selected_by_id[field]["family"],
        }
        for field in valid_fields
    }
    return {
        "status": "estimated",
        "direction": direction,
        "probability_positive": probability,
        "probability_negative": 1.0 - probability,
        "probability_interval_90": interval,
        "expected_return": float(expected_return),
        "similar_history_return_range": {
            "p10": _weighted_quantile(outcomes, weights, 0.10),
            "p50": _weighted_quantile(outcomes, weights, 0.50),
            "p90": _weighted_quantile(outcomes, weights, 0.90),
        },
        "base_probability_positive": base_probability,
        "training_sessions": len(usable),
        "independent_sessions": len(independent),
        "neighbour_sessions": len(nearest),
        "effective_neighbour_sessions": effective_n,
        "nearest_trade_dates": [
            value.strftime("%Y%m%d") for value in nearest.index
        ],
        "selected_factors": [
            selected_by_id[field] for field in valid_fields
        ],
        "current_factor_states": current_states,
        "method": (
            "semantic-family-capped stable Spearman select + robust "
            "nearest-state Beta shrinkage"
        ),
    }


def walk_forward_validate(
    panel: pd.DataFrame,
    *,
    horizon: int,
    target_kind: str,
    minimum_training_sessions: int = MINIMUM_TRAINING_SESSIONS,
    max_validation_points: int = 60,
) -> Dict[str, Any]:
    """Run the legacy single-offset diagnostic sample.

    This preserves the original v1 forecast artifact contract.  It is not an
    effectiveness backtest because it uses only one of the ``horizon`` possible
    offsets and caps the result at ``max_validation_points``.  Use
    :func:`run_daily_walk_forward_backtest` for model evaluation.
    """

    target_field = (
        f"target_abs_return_{horizon}"
        if target_kind == "absolute"
        else f"target_excess_return_{horizon}"
    )
    eligible_dates = panel.index[
        panel[target_field].notna()
        & (np.arange(len(panel)) >= minimum_training_sessions)
    ]
    # Non-overlapping validation labels keep the reported N honest.
    validation_dates = list(eligible_dates[::-max(1, horizon)])
    validation_dates = sorted(validation_dates[:max_validation_points])
    predictions = []
    for trade_date in validation_dates:
        estimate = _estimate_at(
            panel,
            as_of=trade_date,
            horizon=horizon,
            target_kind=target_kind,
            minimum_training_sessions=minimum_training_sessions,
        )
        if estimate.get("status") != "estimated":
            continue
        actual_return = float(panel.at[trade_date, target_field])
        training = panel.loc[panel.index < trade_date]
        available = training[
            training[f"target_date_{horizon}"].notna()
            & (training[f"target_date_{horizon}"] <= trade_date)
            & training[target_field].notna()
        ]
        base_probability = float((available[target_field] > 0).mean())
        predictions.append({
            "trade_date": trade_date.strftime("%Y%m%d"),
            "probability": float(estimate["probability_positive"]),
            "base_probability": base_probability,
            "actual_positive": actual_return > 0,
            "actual_return": actual_return,
        })
    if not predictions:
        return {
            "status": "insufficient",
            "independent_predictions": 0,
        }
    probability = np.array([row["probability"] for row in predictions])
    base = np.array([row["base_probability"] for row in predictions])
    actual = np.array(
        [float(row["actual_positive"]) for row in predictions]
    )
    brier = float(np.mean(np.square(probability - actual)))
    base_brier = float(np.mean(np.square(base - actual)))
    skill = 1.0 - brier / base_brier if base_brier > 0 else None
    return {
        "status": "evaluated",
        "effectiveness_eligible": False,
        "sampling_semantics": (
            "legacy single-offset non-overlapping diagnostic capped at "
            f"{int(max_validation_points)} points; not a full backtest"
        ),
        "independent_predictions": len(predictions),
        "brier_score": brier,
        "expanding_base_brier_score": base_brier,
        "brier_skill_vs_expanding_base": skill,
        "direction_hit_rate": float(
            np.mean((probability >= 0.5) == (actual > 0.5))
        ),
        "mean_forecast_probability": float(np.mean(probability)),
        "realized_positive_rate": float(np.mean(actual)),
        "first_prediction_date": predictions[0]["trade_date"],
        "last_prediction_date": predictions[-1]["trade_date"],
        "predictions": predictions,
    }


def _backtest_metrics(
    rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    settled = [
        row for row in rows
        if row.get("evaluation_status") == "settled"
        and row.get("probability_positive") is not None
        and row.get("expanding_base_probability") is not None
        and row.get("actual_positive") is not None
    ]
    if not settled:
        return {
            "status": "insufficient",
            "settled_predictions": 0,
        }
    probability = np.array([
        float(row["probability_positive"]) for row in settled
    ])
    base = np.array([
        float(row["expanding_base_probability"]) for row in settled
    ])
    actual = np.array([
        float(bool(row["actual_positive"])) for row in settled
    ])
    returns = np.array([
        float(row["actual_return"]) for row in settled
    ])
    brier = float(np.mean(np.square(probability - actual)))
    base_brier = float(np.mean(np.square(base - actual)))
    skill = 1.0 - brier / base_brier if base_brier > 0 else None
    predicted_positive = probability >= 0.5
    actionable = (probability <= 0.45) | (probability >= 0.55)
    metrics: Dict[str, Any] = {
        "status": "evaluated",
        "settled_predictions": len(settled),
        "brier_score": brier,
        "expanding_base_brier_score": base_brier,
        "brier_skill_vs_expanding_base": skill,
        "direction_hit_rate": float(
            np.mean(predicted_positive == (actual > 0.5))
        ),
        "mean_forecast_probability": float(np.mean(probability)),
        "realized_positive_rate": float(np.mean(actual)),
        "mean_actual_return": float(np.mean(returns)),
        "median_actual_return": float(np.median(returns)),
        "first_prediction_date": settled[0]["forecast_trade_date"],
        "last_prediction_date": settled[-1]["forecast_trade_date"],
        "actionable_predictions": int(np.sum(actionable)),
    }
    if np.any(actionable):
        metrics["actionable_direction_hit_rate"] = float(np.mean(
            predicted_positive[actionable] == (actual[actionable] > 0.5)
        ))
    else:
        metrics["actionable_direction_hit_rate"] = None
    return metrics


def _calibration_table(
    rows: Sequence[Mapping[str, Any]],
) -> list[Dict[str, Any]]:
    settled = [
        row for row in rows
        if row.get("evaluation_status") == "settled"
        and row.get("probability_positive") is not None
        and row.get("actual_positive") is not None
    ]
    output = []
    for lower_int in range(0, 100, 10):
        lower = lower_int / 100.0
        upper = (lower_int + 10) / 100.0
        selected = [
            row for row in settled
            if float(row["probability_positive"]) >= lower
            and (
                float(row["probability_positive"]) < upper
                or (
                    upper == 1.0
                    and float(row["probability_positive"]) <= upper
                )
            )
        ]
        if not selected:
            continue
        output.append({
            "lower_inclusive": lower,
            "upper_exclusive": None if upper == 1.0 else upper,
            "upper_inclusive": upper if upper == 1.0 else None,
            "sample_n": len(selected),
            "mean_forecast_probability": float(np.mean([
                float(row["probability_positive"]) for row in selected
            ])),
            "realized_positive_rate": float(np.mean([
                float(bool(row["actual_positive"])) for row in selected
            ])),
            "mean_actual_return": float(np.mean([
                float(row["actual_return"]) for row in selected
            ])),
            "median_actual_return": float(np.median([
                float(row["actual_return"]) for row in selected
            ])),
        })
    return output


def _moving_block_bootstrap(
    rows: Sequence[Mapping[str, Any]],
    *,
    horizon: int,
    repetitions: int,
    seed: int,
) -> Dict[str, Any]:
    settled = [
        row for row in rows
        if row.get("evaluation_status") == "settled"
        and row.get("probability_positive") is not None
        and row.get("expanding_base_probability") is not None
        and row.get("actual_positive") is not None
    ]
    block_length = max(1, int(horizon))
    if repetitions <= 0 or len(settled) < block_length * 2:
        return {
            "status": "insufficient",
            "sample_n": len(settled),
            "block_length_sessions": block_length,
            "repetitions": int(repetitions),
        }
    probability = np.array([
        float(row["probability_positive"]) for row in settled
    ])
    base = np.array([
        float(row["expanding_base_probability"]) for row in settled
    ])
    actual = np.array([
        float(bool(row["actual_positive"])) for row in settled
    ])
    rng = np.random.default_rng(seed)
    block_starts = len(settled) - block_length + 1
    block_count = int(math.ceil(len(settled) / block_length))
    skills = []
    hits = []
    for _ in range(int(repetitions)):
        starts = rng.integers(0, block_starts, size=block_count)
        positions = np.concatenate([
            np.arange(start, start + block_length) for start in starts
        ])[:len(settled)]
        sample_probability = probability[positions]
        sample_base = base[positions]
        sample_actual = actual[positions]
        brier = float(np.mean(np.square(
            sample_probability - sample_actual
        )))
        base_brier = float(np.mean(np.square(
            sample_base - sample_actual
        )))
        if base_brier > 0:
            skills.append(1.0 - brier / base_brier)
        hits.append(float(np.mean(
            (sample_probability >= 0.5) == (sample_actual > 0.5)
        )))

    def interval(values: Sequence[float]) -> Optional[list[float]]:
        if not values:
            return None
        return [
            float(np.quantile(values, 0.05)),
            float(np.quantile(values, 0.50)),
            float(np.quantile(values, 0.95)),
        ]

    return {
        "status": "evaluated",
        "sample_n": len(settled),
        "block_length_sessions": block_length,
        "repetitions": int(repetitions),
        "seed": int(seed),
        "interval_semantics": ["p05", "p50", "p95"],
        "brier_skill_interval_90": interval(skills),
        "direction_hit_rate_interval_90": interval(hits),
    }


def run_daily_walk_forward_backtest(
    panel: pd.DataFrame,
    *,
    horizon: int = 20,
    target_kind: str = "excess",
    minimum_training_sessions: int = MINIMUM_TRAINING_SESSIONS,
    start_trade_date: Optional[str] = None,
    end_trade_date: Optional[str] = None,
    bootstrap_repetitions: int = 1000,
    bootstrap_seed: int = 20260730,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Replay one forecast on every eligible session.

    Daily T+N outcomes are deliberately retained.  They are dependent, so the
    report evaluates them both as a continuous ledger and as N staggered
    offset cohorts whose labels do not overlap within a cohort.  Cohort sample
    counts must not be added together and called independent N.
    """

    horizon = int(horizon)
    if horizon <= 0:
        raise HistoricalProbabilityError("horizon must be positive")
    if target_kind not in {"absolute", "excess"}:
        raise HistoricalProbabilityError(
            "target_kind must be absolute or excess"
        )
    if panel.empty:
        raise HistoricalProbabilityError("AI track panel is empty")
    target_field = (
        f"target_abs_return_{horizon}"
        if target_kind == "absolute"
        else f"target_excess_return_{horizon}"
    )
    target_date_field = f"target_date_{horizon}"
    if target_field not in panel or target_date_field not in panel:
        raise HistoricalProbabilityError(
            f"panel missing horizon fields for T+{horizon}"
        )
    start = (
        pd.to_datetime(start_trade_date, format="%Y%m%d")
        if start_trade_date else None
    )
    end = (
        pd.to_datetime(end_trade_date, format="%Y%m%d")
        if end_trade_date else None
    )
    if start is not None and end is not None and start > end:
        raise HistoricalProbabilityError(
            "start_trade_date cannot be after end_trade_date"
        )
    candidate_positions = [
        position
        for position, trade_date in enumerate(panel.index)
        if position >= int(minimum_training_sessions)
        and (start is None or trade_date >= start)
        and (end is None or trade_date <= end)
    ]
    rows: list[Dict[str, Any]] = []
    abstain_reasons: Dict[str, int] = {}
    total = len(candidate_positions)
    for sequence, position in enumerate(candidate_positions, start=1):
        as_of = panel.index[position]
        if progress is not None:
            progress(sequence, total, as_of.strftime("%Y%m%d"))
        estimate = _estimate_at(
            panel,
            as_of=as_of,
            horizon=horizon,
            target_kind=target_kind,
            minimum_training_sessions=int(minimum_training_sessions),
        )
        target_date_value = panel.at[as_of, target_date_field]
        target_date = (
            None
            if pd.isna(target_date_value)
            else pd.Timestamp(target_date_value).strftime("%Y%m%d")
        )
        actual_value = panel.at[as_of, target_field]
        settled = pd.notna(actual_value) and target_date is not None
        row: Dict[str, Any] = {
            "forecast_trade_date": as_of.strftime("%Y%m%d"),
            "target_trade_date": target_date,
            "horizon_sessions": horizon,
            "target_kind": target_kind,
            "session_position": int(position),
            "cohort_offset": int(position % horizon),
            "forecast_status": estimate.get("status"),
            "evaluation_status": "settled" if settled else "pending",
            "actual_return": float(actual_value) if settled else None,
            "actual_positive": (
                bool(float(actual_value) > 0) if settled else None
            ),
        }
        if estimate.get("status") != "estimated":
            reason = str(estimate.get("reason") or "unknown")
            row["abstain_reason"] = reason
            row["evaluation_status"] = "abstained"
            abstain_reasons[reason] = abstain_reasons.get(reason, 0) + 1
            rows.append(row)
            continue
        training = panel.loc[panel.index < as_of]
        available = training[
            training[target_date_field].notna()
            & (training[target_date_field] <= as_of)
            & training[target_field].notna()
        ]
        expanding_base = (
            float((available[target_field] > 0).mean())
            if not available.empty else None
        )
        row.update({
            "direction": estimate["direction"],
            "probability_positive": float(
                estimate["probability_positive"]
            ),
            "probability_interval_90": list(
                estimate["probability_interval_90"]
            ),
            "expected_return": float(estimate["expected_return"]),
            "expanding_base_probability": expanding_base,
            "model_prior_probability": float(
                estimate["base_probability_positive"]
            ),
            "training_sessions": int(estimate["training_sessions"]),
            "independent_training_sessions": int(
                estimate["independent_sessions"]
            ),
            "neighbour_sessions": int(estimate["neighbour_sessions"]),
            "effective_neighbour_sessions": float(
                estimate["effective_neighbour_sessions"]
            ),
            "selected_factor_ids": [
                str(factor["factor_id"])
                for factor in estimate["selected_factors"]
            ],
            "nearest_trade_dates": list(
                estimate["nearest_trade_dates"]
            ),
        })
        rows.append(row)

    estimated = [
        row for row in rows
        if row.get("forecast_status") == "estimated"
    ]
    settled = [
        row for row in estimated
        if row.get("evaluation_status") == "settled"
    ]
    cohorts = []
    cohort_skills = []
    for offset in range(horizon):
        cohort_rows = [
            row for row in settled
            if int(row["cohort_offset"]) == offset
        ]
        metrics = _backtest_metrics(cohort_rows)
        metrics["cohort_offset"] = offset
        metrics["independence_semantics"] = (
            f"forecast positions differ by {horizon} sessions; "
            "forward-return labels do not overlap within this cohort"
        )
        cohorts.append(metrics)
        skill = metrics.get("brier_skill_vs_expanding_base")
        if skill is not None:
            cohort_skills.append(float(skill))
    by_year = []
    years = sorted({
        str(row["forecast_trade_date"])[:4] for row in settled
    })
    for year in years:
        metrics = _backtest_metrics([
            row for row in settled
            if str(row["forecast_trade_date"]).startswith(year)
        ])
        metrics["year"] = year
        metrics["dependency_warning"] = (
            "daily T+N labels overlap inside this yearly view"
        )
        by_year.append(metrics)
    cohort_stability = {
        "evaluated_cohorts": len(cohort_skills),
        "positive_skill_cohorts": sum(
            value > 0 for value in cohort_skills
        ),
        "non_positive_skill_cohorts": sum(
            value <= 0 for value in cohort_skills
        ),
        "median_brier_skill": (
            float(np.median(cohort_skills)) if cohort_skills else None
        ),
        "minimum_brier_skill": (
            float(np.min(cohort_skills)) if cohort_skills else None
        ),
        "maximum_brier_skill": (
            float(np.max(cohort_skills)) if cohort_skills else None
        ),
        "warning": (
            "cohorts are offset sensitivity views; their sample counts "
            "must not be summed and called independent N"
        ),
    }
    return {
        "schema_version": 1,
        "backtest_version": DAILY_BACKTEST_VERSION,
        "model_version": MODEL_VERSION,
        "group_version": GROUP_VERSION,
        "select_version": SELECT_VERSION,
        "universe_version": UNIVERSE_VERSION,
        "horizon_sessions": horizon,
        "target_kind": target_kind,
        "minimum_training_sessions": int(minimum_training_sessions),
        "attempted_daily_dates": len(rows),
        "estimated_daily_predictions": len(estimated),
        "settled_daily_predictions": len(settled),
        "pending_daily_predictions": sum(
            row.get("evaluation_status") == "pending" for row in estimated
        ),
        "abstained_daily_dates": sum(abstain_reasons.values()),
        "abstain_reasons": dict(sorted(abstain_reasons.items())),
        "first_attempted_date": (
            rows[0]["forecast_trade_date"] if rows else None
        ),
        "last_attempted_date": (
            rows[-1]["forecast_trade_date"] if rows else None
        ),
        "overall_daily_dependent_metrics": _backtest_metrics(settled),
        "probability_calibration": _calibration_table(settled),
        "offset_cohorts": cohorts,
        "cohort_stability": cohort_stability,
        "by_year": by_year,
        "moving_block_bootstrap": _moving_block_bootstrap(
            settled,
            horizon=horizon,
            repetitions=int(bootstrap_repetitions),
            seed=int(bootstrap_seed),
        ),
        "dependency_semantics": (
            "all daily predictions are retained; T+N outcomes overlap across "
            "adjacent dates, so daily N is descriptive rather than independent"
        ),
        "rows": rows,
    }


def build_ai_probability_forecast(
    *,
    panel: pd.DataFrame,
    panel_audit: Mapping[str, Any],
    as_of_trade_date: Optional[str] = None,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    run_validation: bool = True,
    minimum_training_sessions: int = MINIMUM_TRAINING_SESSIONS,
) -> Dict[str, Any]:
    """Build the current AI track probability report from historical data."""

    if panel.empty:
        raise HistoricalProbabilityError("AI track panel is empty")
    if as_of_trade_date:
        as_of = pd.to_datetime(as_of_trade_date, format="%Y%m%d")
        if as_of not in panel.index:
            raise HistoricalProbabilityError(
                f"as_of_trade_date not in panel: {as_of_trade_date}"
            )
    else:
        as_of = panel.index.max()
    forecasts: Dict[str, Any] = {}
    for raw_horizon in horizons:
        horizon = int(raw_horizon)
        absolute = _estimate_at(
            panel,
            as_of=as_of,
            horizon=horizon,
            target_kind="absolute",
            minimum_training_sessions=minimum_training_sessions,
        )
        excess = _estimate_at(
            panel,
            as_of=as_of,
            horizon=horizon,
            target_kind="excess",
            minimum_training_sessions=minimum_training_sessions,
        )
        validation = {}
        if run_validation:
            validation = {
                "absolute": walk_forward_validate(
                    panel,
                    horizon=horizon,
                    target_kind="absolute",
                    minimum_training_sessions=minimum_training_sessions,
                ),
                "excess": walk_forward_validate(
                    panel,
                    horizon=horizon,
                    target_kind="excess",
                    minimum_training_sessions=minimum_training_sessions,
                ),
            }
        forecasts[str(horizon)] = {
            "horizon_sessions": horizon,
            "absolute_direction": absolute,
            "benchmark_excess": excess,
            "walk_forward_validation": validation,
        }
    current = panel.loc[as_of]
    per_symbol_anchor = (
        (panel_audit.get("anchor_alignment") or {}).get("per_symbol") or {}
    )
    current_anchor_sessions = {
        symbol: (per_symbol_anchor.get(symbol) or {}).get("last_session")
        for symbol in ANCHOR_SYMBOLS
    }
    equity_anchor_current = all(
        current_anchor_sessions.get(symbol) == as_of.strftime("%Y%m%d")
        for symbol in ("NVDA", "SOXX", "QQQ")
    )
    return {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "group_version": GROUP_VERSION,
        "select_version": SELECT_VERSION,
        "universe_version": UNIVERSE_VERSION,
        "as_of_trade_date": as_of.strftime("%Y%m%d"),
        "target": "AI current-constituent proxy equal-weight basket",
        "benchmark": "000300.SH",
        "current_member_count": int(current["member_count"]),
        "current_universe_coverage": float(current["universe_coverage"]),
        "current_anchor_sessions": current_anchor_sessions,
        "decision_readiness": (
            "completed_same_date_overseas_session"
            if equity_anchor_current
            else "lagged_anchor_or_run_before_overseas_close"
        ),
        "panel_audit": dict(panel_audit),
        "horizons": forecasts,
        "evidence_status": "historical_walk_forward_research",
        "production_eligible": False,
        "limitations": [
            "current constituent history is a proxy, not point-in-time concept membership",
            "slow capex/debt and consensus-revision anchors are not yet in v1",
            "probabilities are research estimates and do not create stock actions",
        ],
    }


def build_ai_stock_panels(
    *,
    stock_rows: Iterable[Mapping[str, Any]],
    track_panel: pd.DataFrame,
    universe_codes: Sequence[str],
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> Dict[str, pd.DataFrame]:
    """Build per-stock panels conditioned on the already built AI state."""

    codes = sorted({str(code).split(".")[0].zfill(6) for code in universe_codes})
    stocks = _normalise_stock_rows(stock_rows, codes)
    close = stocks.pivot(
        index="trade_date", columns="code", values="adj_close"
    ).sort_index()
    close = close.reindex(track_panel.index)
    turnover = stocks.pivot(
        index="trade_date", columns="code", values="turnover_rate"
    ).reindex(track_panel.index)
    pe_ttm = stocks.pivot(
        index="trade_date", columns="code", values="pe_ttm"
    ).reindex(track_panel.index)
    track_index = (
        1.0 + track_panel["track_return_1d"].fillna(0.0)
    ).cumprod()
    panels: Dict[str, pd.DataFrame] = {}
    shared_fields = [
        field for field in FEATURE_REGISTRY
        if field in track_panel
    ]
    for code in codes:
        if code not in close or close[code].dropna().empty:
            continue
        stock_close = close[code]
        stock_panel = track_panel[shared_fields].copy()
        stock_panel["stock_return_5d"] = stock_close.pct_change(
            5, fill_method=None
        )
        stock_panel["stock_return_20d"] = stock_close.pct_change(
            20, fill_method=None
        )
        stock_panel["stock_excess_track_5d"] = (
            stock_panel["stock_return_5d"]
            - track_index.pct_change(5, fill_method=None)
        )
        stock_panel["stock_excess_track_20d"] = (
            stock_panel["stock_return_20d"]
            - track_index.pct_change(20, fill_method=None)
        )
        stock_daily_return = stock_close.pct_change(fill_method=None)
        stock_panel["stock_volatility_20d"] = stock_daily_return.rolling(
            20, min_periods=20
        ).std() * math.sqrt(252)
        stock_panel["stock_drawdown_60d"] = (
            stock_close / stock_close.rolling(60, min_periods=20).max() - 1.0
        )
        stock_turnover = turnover[code]
        turnover_mean = stock_turnover.rolling(60, min_periods=20).mean()
        turnover_std = stock_turnover.rolling(60, min_periods=20).std()
        stock_panel["stock_turnover_z_60d"] = (
            (stock_turnover - turnover_mean)
            / turnover_std.replace(0, np.nan)
        )
        stock_panel["stock_pe_percentile_252d"] = _rolling_percentile(
            pe_ttm[code], 252
        )
        for raw_horizon in horizons:
            horizon = int(raw_horizon)
            stock_panel[f"target_date_{horizon}"] = pd.Series(
                stock_panel.index,
                index=stock_panel.index,
            ).shift(-horizon)
            stock_forward = (
                stock_close.shift(-horizon) / stock_close - 1.0
            )
            track_forward = (
                track_index.shift(-horizon) / track_index - 1.0
            )
            stock_panel[f"target_abs_return_{horizon}"] = stock_forward
            stock_panel[f"target_excess_return_{horizon}"] = (
                stock_forward - track_forward
            )
        panels[code] = stock_panel
    return panels


def build_ai_stock_probability_forecasts(
    *,
    stock_panels: Mapping[str, pd.DataFrame],
    as_of_trade_date: str,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    minimum_training_sessions: int = MINIMUM_TRAINING_SESSIONS,
) -> Dict[str, Any]:
    """Estimate each member's direction and excess probability conditional on AI."""

    as_of = pd.to_datetime(as_of_trade_date, format="%Y%m%d")
    output: Dict[str, Any] = {}
    for code, panel in sorted(stock_panels.items()):
        if as_of not in panel.index:
            continue
        if pd.isna(panel.at[as_of, "stock_return_5d"]):
            continue
        horizon_rows = {}
        for raw_horizon in horizons:
            horizon = int(raw_horizon)
            absolute = _estimate_at(
                panel,
                as_of=as_of,
                horizon=horizon,
                target_kind="absolute",
                minimum_training_sessions=minimum_training_sessions,
            )
            track_excess = _estimate_at(
                panel,
                as_of=as_of,
                horizon=horizon,
                target_kind="excess",
                minimum_training_sessions=minimum_training_sessions,
            )
            horizon_rows[str(horizon)] = {
                "horizon_sessions": horizon,
                "absolute_direction": absolute,
                "ai_track_excess": track_excess,
                "validation_status": "not_run_for_stock_layer_v1",
            }
        output[code] = {
            "code": code,
            "as_of_trade_date": as_of_trade_date,
            "conditioning": (
                "stock own state plus contemporaneous AI track and "
                "overseas-anchor state"
            ),
            "horizons": horizon_rows,
            "production_eligible": False,
        }
    return output
