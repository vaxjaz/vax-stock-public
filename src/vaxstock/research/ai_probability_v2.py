# -*- coding: utf-8 -*-
"""Causal AI-track probability model with an explicit no-edge outcome.

The v1 nearest-state model remains available for audit.  This module is a
parallel research challenger.  It changes the decision logic, not the frozen
raw dataset:

* ``group`` is a pre-registered semantic feature map, including causal
  first-difference features for turning-point detection;
* ``select`` compares only three pre-registered ridge-logit candidates inside
  the historical window available at the forecast date;
* ``forecast`` must beat both expanding and rolling positive-rate baselines in
  inner validation, otherwise it abstains;
* the final publication gate is evaluated on the full nested outer ledger.

No function in this module performs network or filesystem I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from vaxstock.research.ai_historical_probability import (
    HistoricalProbabilityError,
)


MODEL_VERSION = "ai_probability_edge_v2_1"
GROUP_VERSION = "ai_semantic_groups_with_derivatives_v2"
SELECT_VERSION = "nested_purged_candidate_select_v2_1"
BACKTEST_VERSION = "ai_daily_nested_walk_forward_v2_1"

DEFAULT_HORIZON = 20
DEFAULT_TRAINING_WINDOW = 756
DEFAULT_RESELECT_INTERVAL = 20
DEFAULT_INNER_FOLDS = 3
DEFAULT_INNER_BLOCK = 60
DEFAULT_MINIMUM_FIT_ROWS = 180
DEFAULT_BOOTSTRAP_REPETITIONS = 1000


RAW_GROUPS: Dict[str, tuple[str, ...]] = {
    "internal_trend": (
        "track_return_5d",
        "track_return_20d",
        "track_excess_5d",
        "track_excess_20d",
        "breadth_positive_1d",
        "breadth_above_ma20",
        "track_drawdown_60d",
    ),
    "crowding_valuation": (
        "cross_section_dispersion_5d",
        "track_volatility_20d",
        "turnover_z_60d",
        "pe_ttm_percentile_252d",
    ),
    "external_ai_anchor": (
        "nvda_return_1d",
        "nvda_return_5d",
        "soxx_return_1d",
        "soxx_return_5d",
        "qqq_return_5d",
    ),
    "external_macro_risk": (
        "vix_level",
        "vix_return_5d",
        "tnx_return_5d",
        "dxy_return_5d",
    ),
}

DERIVATIVE_SPECS: Dict[str, tuple[str, int]] = {
    "d_track_return_5d": ("track_return_5d", 5),
    "d_track_excess_5d": ("track_excess_5d", 5),
    "d_breadth_above_ma20_5d": ("breadth_above_ma20", 5),
    "d_dispersion_5d": ("cross_section_dispersion_5d", 5),
    "d_turnover_z_5d": ("turnover_z_60d", 5),
}

GROUPS: Dict[str, tuple[str, ...]] = {
    **RAW_GROUPS,
    "turning_point": tuple(DERIVATIVE_SPECS),
}


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    groups: tuple[str, ...]
    ridge_penalty: float


CANDIDATES: tuple[CandidateSpec, ...] = (
    CandidateSpec(
        "internal_state",
        ("internal_trend", "turning_point"),
        12.0,
    ),
    CandidateSpec(
        "internal_plus_ai_anchor",
        ("internal_trend", "turning_point", "external_ai_anchor"),
        18.0,
    ),
    CandidateSpec(
        "full_state_with_risk",
        (
            "internal_trend",
            "turning_point",
            "crowding_valuation",
            "external_ai_anchor",
            "external_macro_risk",
        ),
        28.0,
    ),
)


def build_v2_feature_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Append point-in-time derivative features without changing raw inputs."""

    if panel.empty:
        raise HistoricalProbabilityError("AI track panel is empty")
    result = panel.copy()
    for output_field, (source_field, periods) in DERIVATIVE_SPECS.items():
        if source_field not in result:
            result[output_field] = np.nan
            continue
        values = pd.to_numeric(result[source_field], errors="coerce")
        result[output_field] = values - values.shift(int(periods))
    return result


def _candidate_fields(candidate: CandidateSpec) -> tuple[str, ...]:
    fields = []
    for group_id in candidate.groups:
        fields.extend(GROUPS[group_id])
    return tuple(dict.fromkeys(fields))


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _fit_ridge_logit(
    matrix: np.ndarray,
    labels: np.ndarray,
    *,
    ridge_penalty: float,
    maximum_iterations: int = 60,
) -> np.ndarray:
    """Fit deterministic ridge logistic regression with Newton updates."""

    if matrix.ndim != 2 or labels.ndim != 1:
        raise HistoricalProbabilityError("invalid logistic input shape")
    if len(matrix) != len(labels) or len(matrix) == 0:
        raise HistoricalProbabilityError("empty/misaligned logistic input")
    design = np.column_stack([np.ones(len(matrix)), matrix])
    coefficients = np.zeros(design.shape[1], dtype=float)
    positive_rate = float(np.mean(labels))
    positive_rate = min(1.0 - 1e-6, max(1e-6, positive_rate))
    coefficients[0] = math.log(positive_rate / (1.0 - positive_rate))
    penalty = np.diag(
        np.array([0.0] + [float(ridge_penalty)] * matrix.shape[1])
    )
    for _ in range(int(maximum_iterations)):
        probability = _sigmoid(design @ coefficients)
        variance = np.maximum(probability * (1.0 - probability), 1e-6)
        gradient = design.T @ (labels - probability) - penalty @ coefficients
        hessian = (design.T * variance) @ design + penalty
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(hessian, gradient, rcond=None)[0]
        coefficients += step
        if float(np.max(np.abs(step))) < 1e-7:
            break
    return coefficients


def _prepare_fit(
    training: pd.DataFrame,
    *,
    fields: Sequence[str],
    target_field: str,
    minimum_rows: int,
) -> Optional[Dict[str, Any]]:
    existing = [field for field in fields if field in training]
    if len(existing) != len(fields):
        return None
    usable = training[[*fields, target_field]].replace(
        [np.inf, -np.inf], np.nan
    ).dropna()
    if len(usable) < int(minimum_rows):
        return None
    labels = (usable[target_field].to_numpy(float) > 0).astype(float)
    if len(np.unique(labels)) < 2:
        return None
    raw = usable[list(fields)].astype(float)
    median = raw.median()
    scale = raw.quantile(0.75) - raw.quantile(0.25)
    active_fields = [
        field for field in fields
        if pd.notna(scale[field]) and float(scale[field]) > 1e-12
    ]
    if not active_fields:
        return None
    standardised = (
        (raw[active_fields] - median[active_fields])
        / scale[active_fields]
    ).clip(-4.0, 4.0)
    return {
        "usable": usable,
        "labels": labels,
        "matrix": standardised.to_numpy(float),
        "fields": active_fields,
        "median": median[active_fields],
        "scale": scale[active_fields],
    }


def _fit_candidate(
    training: pd.DataFrame,
    *,
    current: pd.Series,
    candidate: CandidateSpec,
    target_field: str,
    minimum_rows: int,
) -> Optional[Dict[str, Any]]:
    fields = _candidate_fields(candidate)
    if any(field not in current or pd.isna(current[field]) for field in fields):
        return None
    prepared = _prepare_fit(
        training,
        fields=fields,
        target_field=target_field,
        minimum_rows=minimum_rows,
    )
    if prepared is None:
        return None
    coefficients = _fit_ridge_logit(
        prepared["matrix"],
        prepared["labels"],
        ridge_penalty=candidate.ridge_penalty,
    )
    active_fields = prepared["fields"]
    vector = (
        (current[active_fields].astype(float) - prepared["median"])
        / prepared["scale"]
    ).clip(-4.0, 4.0).to_numpy(float)
    probability = float(_sigmoid(
        np.array([coefficients[0] + vector @ coefficients[1:]])
    )[0])
    weights = {
        field: float(value)
        for field, value in zip(active_fields, coefficients[1:])
    }
    return {
        "probability": probability,
        "fit_rows": len(prepared["usable"]),
        "active_fields": list(active_fields),
        "coefficients": weights,
        "intercept": float(coefficients[0]),
    }


def _base_probabilities(
    training: pd.DataFrame,
    *,
    target_field: str,
    rolling_window: int,
) -> Dict[str, float]:
    labels = (training[target_field].astype(float) > 0).astype(float)
    return {
        "expanding": float(labels.mean()),
        "rolling": float(labels.tail(int(rolling_window)).mean()),
    }


def _brier(probabilities: Sequence[float], labels: Sequence[float]) -> float:
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(labels, dtype=float)
    return float(np.mean(np.square(p - y)))


def _inner_folds(
    history: pd.DataFrame,
    *,
    target_date_field: str,
    minimum_fit_rows: int,
    fold_count: int,
    validation_block: int,
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    folds = []
    total_validation = int(fold_count) * int(validation_block)
    first_start = max(int(minimum_fit_rows), len(history) - total_validation)
    for start in range(
        first_start,
        len(history),
        int(validation_block),
    ):
        stop = min(len(history), start + int(validation_block))
        if stop - start < max(20, int(validation_block) // 2):
            continue
        validation = history.iloc[start:stop]
        validation_start = validation.index[0]
        training = history.iloc[:start]
        training = training[
            training[target_date_field].notna()
            & (training[target_date_field] <= validation_start)
        ]
        if len(training) < int(minimum_fit_rows):
            continue
        folds.append((training, validation))
    return folds[-int(fold_count):]


def _evaluate_candidate_inner(
    history: pd.DataFrame,
    *,
    candidate: CandidateSpec,
    target_field: str,
    target_date_field: str,
    rolling_window: int,
    minimum_fit_rows: int,
    fold_count: int,
    validation_block: int,
) -> Dict[str, Any]:
    folds = _inner_folds(
        history,
        target_date_field=target_date_field,
        minimum_fit_rows=minimum_fit_rows,
        fold_count=fold_count,
        validation_block=validation_block,
    )
    rows = []
    fold_metrics = []
    for fold_number, (training, validation) in enumerate(folds, start=1):
        full_training = training
        fit_training = full_training.tail(int(rolling_window))
        first = validation.iloc[0]
        fitted = _fit_candidate(
            fit_training,
            current=first,
            candidate=candidate,
            target_field=target_field,
            minimum_rows=minimum_fit_rows,
        )
        if fitted is None:
            continue
        # The fold uses one model/scaler frozen at the fold boundary.  This is
        # deliberately stricter than refitting on labels inside the block.
        fields = fitted["active_fields"]
        prepared = _prepare_fit(
            fit_training,
            fields=_candidate_fields(candidate),
            target_field=target_field,
            minimum_rows=minimum_fit_rows,
        )
        if prepared is None:
            continue
        coefficients = np.array(
            [fitted["intercept"]]
            + [fitted["coefficients"][field] for field in fields],
            dtype=float,
        )
        usable_validation = validation[
            [*fields, target_field]
        ].replace([np.inf, -np.inf], np.nan).dropna()
        if len(usable_validation) < 10:
            continue
        matrix = (
            (
                usable_validation[fields].astype(float)
                - prepared["median"][fields]
            )
            / prepared["scale"][fields]
        ).clip(-4.0, 4.0).to_numpy(float)
        probability = _sigmoid(
            coefficients[0] + matrix @ coefficients[1:]
        )
        labels = (
            usable_validation[target_field].to_numpy(float) > 0
        ).astype(float)
        bases = _base_probabilities(
            full_training,
            target_field=target_field,
            rolling_window=rolling_window,
        )
        model_brier = _brier(probability, labels)
        expanding_brier = _brier(
            np.full(len(labels), bases["expanding"]),
            labels,
        )
        rolling_brier = _brier(
            np.full(len(labels), bases["rolling"]),
            labels,
        )
        strongest_base = min(expanding_brier, rolling_brier)
        skill = (
            1.0 - model_brier / strongest_base
            if strongest_base > 0 else None
        )
        fold_metrics.append({
            "fold": fold_number,
            "validation_start": usable_validation.index[0].strftime("%Y%m%d"),
            "validation_end": usable_validation.index[-1].strftime("%Y%m%d"),
            "validation_rows": len(labels),
            "brier_score": model_brier,
            "expanding_base_brier": expanding_brier,
            "rolling_base_brier": rolling_brier,
            "brier_skill_vs_strongest_base": skill,
        })
        rows.extend({
            "probability": float(p),
            "actual": float(y),
            "expanding_base": bases["expanding"],
            "rolling_base": bases["rolling"],
        } for p, y in zip(probability, labels))
    if not rows:
        return {
            "candidate_id": candidate.candidate_id,
            "status": "insufficient",
            "folds": fold_metrics,
        }
    model_brier = _brier(
        [row["probability"] for row in rows],
        [row["actual"] for row in rows],
    )
    expanding_brier = _brier(
        [row["expanding_base"] for row in rows],
        [row["actual"] for row in rows],
    )
    rolling_brier = _brier(
        [row["rolling_base"] for row in rows],
        [row["actual"] for row in rows],
    )
    strongest_base = min(expanding_brier, rolling_brier)
    skill = (
        1.0 - model_brier / strongest_base
        if strongest_base > 0 else None
    )
    positive_folds = sum(
        (row["brier_skill_vs_strongest_base"] or -math.inf) > 0
        for row in fold_metrics
    )
    eligible = (
        len(fold_metrics) >= 2
        and skill is not None
        and skill > 0
        and positive_folds >= math.ceil(len(fold_metrics) / 2)
    )
    return {
        "candidate_id": candidate.candidate_id,
        "status": "eligible" if eligible else "rejected",
        "groups": list(candidate.groups),
        "feature_count": len(_candidate_fields(candidate)),
        "ridge_penalty": candidate.ridge_penalty,
        "validation_rows": len(rows),
        "brier_score": model_brier,
        "expanding_base_brier": expanding_brier,
        "rolling_base_brier": rolling_brier,
        "brier_skill_vs_strongest_base": skill,
        "positive_skill_folds": positive_folds,
        "fold_count": len(fold_metrics),
        "folds": fold_metrics,
    }


def select_candidate(
    history: pd.DataFrame,
    *,
    target_field: str,
    target_date_field: str,
    rolling_window: int = DEFAULT_TRAINING_WINDOW,
    minimum_fit_rows: int = DEFAULT_MINIMUM_FIT_ROWS,
    fold_count: int = DEFAULT_INNER_FOLDS,
    validation_block: int = DEFAULT_INNER_BLOCK,
) -> Dict[str, Any]:
    """Select one pre-registered candidate using past-only inner folds."""

    evaluations = [
        _evaluate_candidate_inner(
            history,
            candidate=candidate,
            target_field=target_field,
            target_date_field=target_date_field,
            rolling_window=rolling_window,
            minimum_fit_rows=minimum_fit_rows,
            fold_count=fold_count,
            validation_block=validation_block,
        )
        for candidate in CANDIDATES
    ]
    eligible = [
        row for row in evaluations if row.get("status") == "eligible"
    ]
    if not eligible:
        return {
            "status": "abstain",
            "reason": "no_candidate_beats_both_inner_baselines",
            "candidate_evaluations": evaluations,
        }
    winner = sorted(
        eligible,
        key=lambda row: (
            -float(row["brier_skill_vs_strongest_base"]),
            int(row["feature_count"]),
            str(row["candidate_id"]),
        ),
    )[0]
    return {
        "status": "selected",
        "candidate_id": winner["candidate_id"],
        "selection_metrics": winner,
        "candidate_evaluations": evaluations,
    }


def _metrics(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    settled = [
        row for row in rows
        if row.get("evaluation_status") == "settled"
        and row.get("probability_positive") is not None
    ]
    if not settled:
        return {"status": "insufficient", "sample_n": 0}
    actual = np.array(
        [float(bool(row["actual_positive"])) for row in settled]
    )
    model = np.array(
        [float(row["probability_positive"]) for row in settled]
    )
    expanding = np.array(
        [float(row["expanding_base_probability"]) for row in settled]
    )
    rolling = np.array(
        [float(row["rolling_base_probability"]) for row in settled]
    )
    model_brier = _brier(model, actual)
    expanding_brier = _brier(expanding, actual)
    rolling_brier = _brier(rolling, actual)
    strongest = min(expanding_brier, rolling_brier)
    return {
        "status": "evaluated",
        "sample_n": len(settled),
        "brier_score": model_brier,
        "expanding_base_brier_score": expanding_brier,
        "rolling_base_brier_score": rolling_brier,
        "brier_skill_vs_expanding_base": (
            1.0 - model_brier / expanding_brier
            if expanding_brier > 0 else None
        ),
        "brier_skill_vs_rolling_base": (
            1.0 - model_brier / rolling_brier
            if rolling_brier > 0 else None
        ),
        "brier_skill_vs_strongest_base": (
            1.0 - model_brier / strongest if strongest > 0 else None
        ),
        "mean_probability": float(np.mean(model)),
        "realized_positive_rate": float(np.mean(actual)),
        "mean_edge_vs_rolling_base": float(np.mean(model - rolling)),
    }


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
    ]
    if len(settled) < max(40, horizon * 2) or repetitions <= 0:
        return {"status": "insufficient", "sample_n": len(settled)}
    n = len(settled)
    rng = np.random.default_rng(int(seed))
    model = np.array([
        float(row["probability_positive"]) for row in settled
    ])
    expanding = np.array([
        float(row["expanding_base_probability"]) for row in settled
    ])
    rolling = np.array([
        float(row["rolling_base_probability"]) for row in settled
    ])
    actual = np.array([
        float(bool(row["actual_positive"])) for row in settled
    ])
    block = max(1, int(horizon))
    skills = []
    for _ in range(int(repetitions)):
        positions = []
        while len(positions) < n:
            start = int(rng.integers(0, max(1, n - block + 1)))
            positions.extend(range(start, min(n, start + block)))
        idx = np.asarray(positions[:n], dtype=int)
        model_brier = _brier(model[idx], actual[idx])
        expanding_brier = _brier(expanding[idx], actual[idx])
        rolling_brier = _brier(rolling[idx], actual[idx])
        strongest = min(expanding_brier, rolling_brier)
        if strongest > 0:
            skills.append(1.0 - model_brier / strongest)
    if not skills:
        return {"status": "insufficient", "sample_n": n}
    return {
        "status": "evaluated",
        "sample_n": n,
        "block_length_sessions": block,
        "repetitions": int(repetitions),
        "brier_skill_vs_strongest_base_p05_p50_p95": [
            float(np.quantile(skills, quantile))
            for quantile in (0.05, 0.50, 0.95)
        ],
    }


def _publication_gate(
    *,
    overall: Mapping[str, Any],
    cohort_stability: Mapping[str, Any],
    bootstrap: Mapping[str, Any],
) -> Dict[str, Any]:
    checks = {
        "minimum_120_settled_predictions": (
            int(overall.get("sample_n") or 0) >= 120
        ),
        "positive_skill_vs_expanding_base": (
            (overall.get("brier_skill_vs_expanding_base") or -math.inf) > 0
        ),
        "positive_skill_vs_rolling_base": (
            (overall.get("brier_skill_vs_rolling_base") or -math.inf) > 0
        ),
        "majority_positive_offset_cohorts": (
            int(cohort_stability.get("positive_skill_cohorts") or 0)
            >= math.ceil(
                int(cohort_stability.get("evaluated_cohorts") or 0) / 2
            )
            and int(cohort_stability.get("evaluated_cohorts") or 0) > 0
        ),
        "positive_block_bootstrap_median": (
            (
                bootstrap.get(
                    "brier_skill_vs_strongest_base_p05_p50_p95"
                ) or [-math.inf, -math.inf]
            )[1] > 0
        ),
    }
    publish = all(checks.values())
    robust = publish and (
        bootstrap[
            "brier_skill_vs_strongest_base_p05_p50_p95"
        ][0] > 0
    )
    return {
        "status": (
            "robust_numeric_edge"
            if robust
            else ("research_numeric_edge" if publish else "abstain")
        ),
        "publish_numeric_probability": publish,
        "robust_evidence": robust,
        "checks": checks,
        "failed_checks": [
            name for name, passed in checks.items() if not passed
        ],
        "semantics": (
            "numeric probability may enter analyst output only when every "
            "pre-registered check passes; otherwise the analyst conclusion "
            "is no proven edge"
        ),
    }


def run_v2_daily_backtest(
    panel: pd.DataFrame,
    *,
    horizon: int = DEFAULT_HORIZON,
    training_window: int = DEFAULT_TRAINING_WINDOW,
    reselect_interval: int = DEFAULT_RESELECT_INTERVAL,
    minimum_fit_rows: int = DEFAULT_MINIMUM_FIT_ROWS,
    inner_folds: int = DEFAULT_INNER_FOLDS,
    inner_validation_block: int = DEFAULT_INNER_BLOCK,
    bootstrap_repetitions: int = DEFAULT_BOOTSTRAP_REPETITIONS,
    bootstrap_seed: int = 20260730,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Run the nested outer day-by-day backtest for T+N benchmark excess."""

    horizon = int(horizon)
    if horizon <= 0:
        raise HistoricalProbabilityError("horizon must be positive")
    features = build_v2_feature_panel(panel)
    target_field = f"target_excess_return_{horizon}"
    target_date_field = f"target_date_{horizon}"
    if target_field not in features or target_date_field not in features:
        raise HistoricalProbabilityError(
            f"panel missing T+{horizon} excess label fields"
        )
    rows = []
    selections = []
    active_selection: Optional[Dict[str, Any]] = None
    active_selection_id: Optional[int] = None
    candidate_positions = list(range(int(minimum_fit_rows), len(features)))
    total = len(candidate_positions)
    for sequence, position in enumerate(candidate_positions, start=1):
        as_of = features.index[position]
        if progress is not None:
            progress(sequence, total, as_of.strftime("%Y%m%d"))
        history = features.loc[features.index < as_of].copy()
        history = history[
            history[target_date_field].notna()
            & (history[target_date_field] <= as_of)
            & history[target_field].notna()
        ]
        if (
            active_selection is None
            or position % int(reselect_interval) == 0
        ):
            active_selection = select_candidate(
                history,
                target_field=target_field,
                target_date_field=target_date_field,
                rolling_window=training_window,
                minimum_fit_rows=minimum_fit_rows,
                fold_count=inner_folds,
                validation_block=inner_validation_block,
            )
            active_selection_id = len(selections)
            selections.append({
                "selection_id": active_selection_id,
                "as_of_trade_date": as_of.strftime("%Y%m%d"),
                **active_selection,
            })
        target_date_value = features.at[as_of, target_date_field]
        actual_value = features.at[as_of, target_field]
        settled = (
            pd.notna(target_date_value)
            and pd.Timestamp(target_date_value) <= features.index[-1]
            and pd.notna(actual_value)
        )
        row: Dict[str, Any] = {
            "forecast_trade_date": as_of.strftime("%Y%m%d"),
            "target_trade_date": (
                pd.Timestamp(target_date_value).strftime("%Y%m%d")
                if pd.notna(target_date_value) else None
            ),
            "session_position": position,
            "cohort_offset": position % horizon,
            "selection_id": active_selection_id,
            "evaluation_status": "settled" if settled else "pending",
            "actual_return": float(actual_value) if settled else None,
            "actual_positive": (
                bool(float(actual_value) > 0) if settled else None
            ),
        }
        if (
            active_selection is None
            or active_selection.get("status") != "selected"
        ):
            row.update({
                "forecast_status": "abstain",
                "abstain_reason": (
                    (active_selection or {}).get("reason")
                    or "no_active_selection"
                ),
            })
            rows.append(row)
            continue
        candidate = next(
            item for item in CANDIDATES
            if item.candidate_id == active_selection["candidate_id"]
        )
        fit_history = history.tail(int(training_window))
        fitted = _fit_candidate(
            fit_history,
            current=features.loc[as_of],
            candidate=candidate,
            target_field=target_field,
            minimum_rows=minimum_fit_rows,
        )
        if fitted is None:
            row.update({
                "forecast_status": "abstain",
                "abstain_reason": "selected_candidate_cannot_fit_current_data",
            })
            rows.append(row)
            continue
        bases = _base_probabilities(
            history,
            target_field=target_field,
            rolling_window=training_window,
        )
        row.update({
            "forecast_status": "estimated",
            "candidate_id": candidate.candidate_id,
            "probability_positive": fitted["probability"],
            "expanding_base_probability": bases["expanding"],
            "rolling_base_probability": bases["rolling"],
            "probability_edge_vs_rolling_base": (
                fitted["probability"] - bases["rolling"]
            ),
            "fit_rows": fitted["fit_rows"],
            "active_fields": fitted["active_fields"],
        })
        rows.append(row)

    estimated = [
        row for row in rows if row.get("forecast_status") == "estimated"
    ]
    settled = [
        row for row in estimated
        if row.get("evaluation_status") == "settled"
    ]
    overall = _metrics(settled)
    cohorts = []
    cohort_skills = []
    for offset in range(horizon):
        metrics = _metrics([
            row for row in settled if row["cohort_offset"] == offset
        ])
        metrics["cohort_offset"] = offset
        cohorts.append(metrics)
        skill = metrics.get("brier_skill_vs_strongest_base")
        if skill is not None:
            cohort_skills.append(float(skill))
    cohort_stability = {
        "evaluated_cohorts": len(cohort_skills),
        "positive_skill_cohorts": sum(value > 0 for value in cohort_skills),
        "non_positive_skill_cohorts": sum(
            value <= 0 for value in cohort_skills
        ),
        "median_brier_skill_vs_strongest_base": (
            float(np.median(cohort_skills)) if cohort_skills else None
        ),
    }
    bootstrap = _moving_block_bootstrap(
        settled,
        horizon=horizon,
        repetitions=bootstrap_repetitions,
        seed=bootstrap_seed,
    )
    gate = _publication_gate(
        overall=overall,
        cohort_stability=cohort_stability,
        bootstrap=bootstrap,
    )
    return {
        "schema_version": 1,
        "backtest_version": BACKTEST_VERSION,
        "model_version": MODEL_VERSION,
        "group_version": GROUP_VERSION,
        "select_version": SELECT_VERSION,
        "horizon_sessions": horizon,
        "target_kind": "benchmark_excess",
        "group_contract": {
            group_id: list(fields) for group_id, fields in GROUPS.items()
        },
        "candidate_contract": [
            {
                "candidate_id": candidate.candidate_id,
                "groups": list(candidate.groups),
                "fields": list(_candidate_fields(candidate)),
                "ridge_penalty": candidate.ridge_penalty,
            }
            for candidate in CANDIDATES
        ],
        "selection_contract": {
            "training_window_sessions": int(training_window),
            "reselect_interval_sessions": int(reselect_interval),
            "inner_folds": int(inner_folds),
            "inner_validation_block_sessions": int(inner_validation_block),
            "minimum_fit_rows": int(minimum_fit_rows),
            "purge_semantics": (
                "a label enters training only when target_trade_date is not "
                "after the simulated forecast date/fold boundary"
            ),
        },
        "attempted_daily_dates": len(rows),
        "estimated_daily_predictions": len(estimated),
        "settled_daily_predictions": len(settled),
        "pending_daily_predictions": sum(
            row.get("evaluation_status") == "pending" for row in estimated
        ),
        "abstained_daily_dates": sum(
            row.get("forecast_status") == "abstain" for row in rows
        ),
        "overall_nested_metrics": overall,
        "offset_cohorts": cohorts,
        "cohort_stability": cohort_stability,
        "moving_block_bootstrap": bootstrap,
        "publication_gate": gate,
        "selections": selections,
        "rows": rows,
    }
