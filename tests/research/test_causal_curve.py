# -*- coding: utf-8 -*-

from datetime import datetime, timedelta, timezone

import pytest

from vaxstock.research.causal_curve import (
    CURVE_FACTOR_VERSION,
    CurveParameters,
    ELIGIBILITY_VERSION,
    STOCK_CURVE_VECTOR_FACTOR_ID,
    TRACK_CURVE_VECTOR_FACTOR_ID,
    TRACK_FACTOR_VERSION,
    build_causal_curve_run,
    compute_causal_curve,
    curve_factor_version,
    is_curve_eligible,
    track_factor_version,
)
from vaxstock.research.contracts import (
    ContractError,
    canonical_digest,
    make_factor_value_id,
    make_observation_id,
    validate_factor_value,
    validate_run_manifest,
)


CHINA_TZ = timezone(timedelta(hours=8))
DATES = [
    "20260706", "20260707", "20260708", "20260709", "20260710",
    "20260713", "20260714", "20260715", "20260716", "20260717",
]


def _timestamp(trade_date, hour=18, minute=0):
    day = datetime.strptime(trade_date, "%Y%m%d").replace(
        hour=hour, minute=minute, tzinfo=CHINA_TZ
    )
    return day.isoformat(timespec="seconds")


def _observation(code, trade_date, field, value, *, dimension="legacy_snapshot"):
    timestamp = _timestamp(trade_date)
    row = {
        "schema_version": 1,
        "observation_id": "",
        "entity_type": "stock",
        "entity_id": code,
        "dimension": dimension,
        "field": field,
        "value": value,
        "effective_date": trade_date,
        "available_at": timestamp,
        "retrieved_at": timestamp,
        "source": "test.fixture",
        "source_ref": f"fixture:{trade_date}:{code}:{dimension}:{field}",
        "revision_id": f"{trade_date}:{code}:{field}",
        "quality": "observed",
    }
    row["observation_id"] = make_observation_id(row)
    return row


def _factor(code, trade_date, value, observation):
    inputs = [observation["observation_id"]]
    row = {
        "schema_version": 1,
        "factor_value_id": "",
        "entity_type": "stock",
        "entity_id": code,
        "dimension": "legacy_snapshot",
        "factor_id": "legacy.rsi_14",
        "factor_version": "legacy_snapshot_v1",
        "value": float(value),
        "as_of_trade_date": trade_date,
        "effective_date": trade_date,
        "available_at": observation["available_at"],
        "calculated_at": _timestamp(trade_date, minute=1),
        "input_observation_ids": inputs,
        "input_digest": canonical_digest(inputs),
        "quality": "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _history():
    observations = []
    factors = []
    for index, trade_date in enumerate(DATES):
        for code, offset in (
            ("601138", 0.0),
            ("002475", 2.0),
            ("600276", 4.0),
        ):
            membership = _observation(
                code,
                trade_date,
                "membership",
                {"name": code, "group": "watchlist", "concepts": ["AI算力"]},
                dimension="universe",
            )
            metric = _observation(
                code, trade_date, "metrics", {"rsi_14": index + 1 + offset}
            )
            observations.extend([membership, metric])
            factors.append(
                _factor(code, trade_date, index + 1 + offset, metric)
            )
    return observations, factors


def test_curve_detectors_separate_trend_reversal_anomaly_and_shift():
    linear = compute_causal_curve(list(range(1, 16)))
    assert linear["slope_recent"] == pytest.approx(1.0)
    assert linear["slope_prior"] == pytest.approx(1.0)
    assert linear["acceleration"] == pytest.approx(0.0)
    assert linear["candidate_events"] == []
    assert linear["level_shift_detrended"] == pytest.approx(0.0)

    reversal = compute_causal_curve([10, 9, 8, 7, 6, 7, 8, 9, 10, 11])
    assert reversal["turning_candidate"] == "up"
    assert "turning_up" in reversal["candidate_events"]

    spike = compute_causal_curve([1.0] * 15 + [5.0])
    assert spike["anomaly_candidate"] == "positive"
    assert spike["innovation_zero_scale_break"] is True

    shift = compute_causal_curve([1.0] * 5 + [5.0] * 5)
    assert shift["change_point_candidate"] == "up"
    assert shift["level_shift_zero_scale_break"] is True


def test_short_history_marks_features_unavailable_instead_of_neutral_values():
    curve = compute_causal_curve([1.0])
    assert curve["delta_1"] is None
    assert curve["slope_recent"] is None
    assert curve["innovation_robust_z"] is None
    assert curve["change_point_candidate"] is None
    assert curve["unavailable"]


def test_parameter_change_has_a_distinct_factor_version():
    changed = CurveParameters(anomaly_z_threshold=4.0)
    assert curve_factor_version(changed) != CURVE_FACTOR_VERSION
    assert compute_causal_curve([1.0, 2.0], parameters=changed)[
        "parameter_version"
    ] == curve_factor_version(changed)
    assert track_factor_version(
        CurveParameters(minimum_track_members=4)
    ) != TRACK_FACTOR_VERSION
    with pytest.raises(ContractError, match="thresholds"):
        compute_causal_curve(
            [1.0, 2.0],
            parameters=CurveParameters(anomaly_z_threshold=float("nan")),
        )
    with pytest.raises(ContractError, match="finite numbers"):
        compute_causal_curve(["1.0", "2.0"])


def test_eligibility_is_semantic_registry_not_all_numeric_fields():
    base = {
        "entity_type": "stock",
        "dimension": "E",
        "factor_id": "seller_consensus_eps_median_90d.2026Q4",
        "value": 3.2,
        "quality": "calculated",
    }
    assert is_curve_eligible(base) is True
    assert is_curve_eligible(
        dict(base, factor_id="future_unreviewed_numeric_field")
    ) is False


def test_builds_stock_and_point_in_time_track_curves_with_dependency_roots():
    observations, factors = _history()
    manifest, outputs, summary = build_causal_curve_run(
        as_of_trade_date=DATES[-1],
        calculated_at=_timestamp(DATES[-1], minute=2),
        factor_rows=factors,
        observations=observations,
        mode="replay",
    )

    validate_run_manifest(manifest)
    for row in outputs:
        validate_factor_value(row)
    assert manifest["group_version"] == "not_executed"
    assert manifest["select_version"] == "not_executed"
    assert manifest["forecast_version"] == "not_executed"
    assert manifest["eligibility_version"] == ELIGIBILITY_VERSION
    assert summary == {
        "as_of_trade_date": DATES[-1],
        "eligible_base_rows": 30,
        "current_stock_factor_series": 3,
        "track_aggregates": 1,
        "stock_curves": 3,
        "track_curves": 1,
        "stock_curve_series": 3,
        "track_aggregate_series": 1,
        "track_curve_series": 1,
        "outputs": 5,
        "session_count": 10,
        "candidate_hits": 0,
        "detector_status": "candidate_not_validated",
    }

    aggregate = next(
        row for row in outputs
        if row["dimension"] == "track_aggregate"
    )
    assert aggregate["entity_id"] == "AI算力"
    assert aggregate["factor_version"] == TRACK_FACTOR_VERSION
    series_id = "legacy_snapshot::legacy.rsi_14::legacy_snapshot_v1"
    aggregate_series = aggregate["value"]["series"][series_id]
    assert aggregate_series["level"] == pytest.approx(12.0)
    assert aggregate_series["member_count"] == 3
    assert aggregate_series["member_codes"] == ["002475", "600276", "601138"]
    assert len(aggregate["input_factor_refs"]) == 3
    assert len(aggregate["input_observation_ids"]) == 3

    stock_curve = next(
        row for row in outputs
        if row["dimension"] == "causal_curve"
        and row["entity_type"] == "stock"
        and row["entity_id"] == "601138"
    )
    assert stock_curve["factor_id"] == STOCK_CURVE_VECTOR_FACTOR_ID
    assert stock_curve["factor_version"] == CURVE_FACTOR_VERSION
    assert stock_curve["value"]["series"][series_id]["sample_count"] == 10
    assert stock_curve["value"]["candidate_events"] == []
    assert len(stock_curve["input_factor_refs"]) == 10

    track_curve = next(
        row for row in outputs
        if row["dimension"] == "causal_curve"
        and row["entity_type"] == "track"
    )
    assert track_curve["factor_id"] == TRACK_CURVE_VECTOR_FACTOR_ID
    assert track_curve["value"]["series"][series_id]["sample_count"] == 1
    assert track_curve["input_factor_refs"] == [{
        "factor_value_id": aggregate["factor_value_id"],
        "as_of_trade_date": DATES[-1],
    }]


def test_live_curve_rejects_late_historical_execution():
    observations, factors = _history()
    with pytest.raises(ContractError, match="outside"):
        build_causal_curve_run(
            as_of_trade_date=DATES[-1],
            calculated_at="2026-07-20T09:00:00+08:00",
            factor_rows=factors,
            observations=observations,
            mode="live",
        )
