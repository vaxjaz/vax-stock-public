# -*- coding: utf-8 -*-

from datetime import datetime, timedelta, timezone

import pytest

from vaxstock.research.contextual_group import (
    GROUP_CONTEXT_FACTOR_ID,
    GROUP_VERSION,
    STOCK_GROUP_FACTOR_ID,
    GroupParameters,
    build_contextual_group_run,
    factor_series_id,
    group_version,
    materialize_group_id,
)
from vaxstock.research.causal_curve import (
    CURVE_FACTOR_VERSION,
    STOCK_CURVE_VECTOR_FACTOR_ID,
)
from vaxstock.research.contracts import (
    ContractError,
    canonical_digest,
    factor_input_digest,
    make_factor_value_id,
    make_observation_id,
    validate_factor_value,
    validate_run_manifest,
)


CHINA_TZ = timezone(timedelta(hours=8))
TRADE_DATE = "20260724"


def _timestamp(trade_date=TRADE_DATE, hour=18, minute=0):
    return datetime.strptime(trade_date, "%Y%m%d").replace(
        hour=hour, minute=minute, tzinfo=CHINA_TZ
    ).isoformat(timespec="seconds")


def _observation(entity_type, entity_id, dimension, field, value, trade_date=TRADE_DATE):
    timestamp = _timestamp(trade_date)
    row = {
        "schema_version": 1,
        "observation_id": "",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "dimension": dimension,
        "field": field,
        "value": value,
        "effective_date": trade_date,
        "available_at": timestamp,
        "retrieved_at": timestamp,
        "source": "test.fixture",
        "source_ref": f"fixture:{trade_date}:{entity_type}:{entity_id}:{field}",
        "revision_id": f"{trade_date}:{entity_type}:{entity_id}:{field}",
        "quality": "observed",
    }
    row["observation_id"] = make_observation_id(row)
    return row


def _factor(code, value, observation, trade_date=TRADE_DATE):
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


def _curve_factor(code, base_factor, events):
    refs = [{
        "factor_value_id": base_factor["factor_value_id"],
        "as_of_trade_date": base_factor["as_of_trade_date"],
    }]
    series_id = factor_series_id(base_factor)
    row = {
        "schema_version": 1,
        "factor_value_id": "",
        "entity_type": "stock",
        "entity_id": code,
        "dimension": "causal_curve",
        "factor_id": STOCK_CURVE_VECTOR_FACTOR_ID,
        "factor_version": CURVE_FACTOR_VERSION,
        "value": {
            "series": {
                series_id: {
                    "sample_count": 20,
                    "slope_recent": 1.0,
                    "acceleration": 1.0,
                    "turning_candidate": (
                        "up" if "turning_up" in events else None
                    ),
                    "anomaly_candidate": None,
                    "change_point_candidate": None,
                    "innovation_robust_z": 0.0,
                    "innovation_zero_scale_break": False,
                    "candidate_events": list(events),
                }
            },
            "candidate_events": list(events),
        },
        "as_of_trade_date": TRADE_DATE,
        "effective_date": TRADE_DATE,
        "available_at": base_factor["available_at"],
        "calculated_at": _timestamp(minute=1),
        "input_observation_ids": [],
        "input_factor_refs": refs,
        "input_digest": factor_input_digest([], refs),
        "quality": "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _inputs():
    codes = [f"6000{index:02d}" for index in range(9)]
    observations = [
        _observation(
            "market",
            "CN-A",
            "universe",
            "universe_snapshot",
            {
                "active_codes": codes,
                "active_count": len(codes),
                "membership_semantics": "exact_frozen_rows",
                "upstream_completeness": "test_fixture",
            },
        ),
        _observation(
            "market",
            "CN-A",
            "market_context",
            "market_snapshot",
            {"regime": "panic", "macro_regime": None},
        )
    ]
    factors = []
    for index, code in enumerate(codes):
        observations.append(
            _observation(
                "stock",
                code,
                "universe",
                "membership",
                {
                    "name": code,
                    "group": "holding" if index == 0 else "watchlist",
                    "concepts": ["AI算力"],
                },
            )
        )
        metric = _observation(
            "stock",
            code,
            "legacy_snapshot",
            "metrics",
            {"rsi_14": index + 1},
        )
        observations.append(metric)
        factors.append(_factor(code, index + 1, metric))
    return observations, factors


def test_group_is_label_free_multiview_and_missing_is_not_neutral():
    observations, factors = _inputs()
    manifest, outputs, summary = build_contextual_group_run(
        as_of_trade_date=TRADE_DATE,
        calculated_at=_timestamp(minute=2),
        factor_rows=factors,
        observations=observations,
        mode="replay",
    )

    validate_run_manifest(manifest)
    for row in outputs:
        validate_factor_value(row)
    assert manifest["group_version"] == GROUP_VERSION
    assert manifest["select_version"] == "not_executed"
    assert manifest["forecast_version"] == "not_executed"
    assert manifest["label_usage"] == "none"
    assert summary["label_usage"] == "none"
    assert summary["effectiveness_status"] == "not_evaluated"
    assert summary["stock_group_vectors"] == 9

    context = outputs[0]["value"]
    series_id = factor_series_id(factors[0])
    cross = context["cross_sections"][series_id]
    assert cross["status"] == "available"
    assert cross["method"] == "empirical_midrank_tertiles"
    assert cross["bucket_counts"] == {"low": 3, "middle": 3, "high": 3}
    assert context["market"]["states"]["regime"]["state"] == "panic"
    assert context["market"]["states"]["macro_regime"] == {
        "state": None,
        "status": "source_missing",
    }
    assert context["tracks"]["AI算力"]["status"] == (
        "eligible_factor_coverage_missing"
    )

    holding = next(
        row for row in outputs
        if (
            row["factor_id"] == STOCK_GROUP_FACTOR_ID
            and row["entity_id"] == "600000"
        )
    )
    assert holding["value"]["role"]["audit_only"] is True
    assert holding["value"]["role"]["value"] == "holding"
    assert holding["value"]["statistical_membership_count"] == 2
    stock_cross = holding["value"]["factor_groups"][series_id]["cross_section"]
    assert stock_cross["bucket"] == "low"
    assert stock_cross["rank_pct"] == pytest.approx(0.0)
    assert all(
        state is None
        for state in holding["value"]["factor_groups"][series_id][
            "curve_state_vector"
        ]
    )


def test_future_membership_and_factor_are_excluded_at_decision_time():
    observations, factors = _inputs()
    future_date = "20260727"
    future_membership = _observation(
        "stock",
        "601999",
        "universe",
        "membership",
        {"name": "future", "group": "watchlist", "concepts": ["AI算力"]},
        future_date,
    )
    future_metric = _observation(
        "stock",
        "601999",
        "legacy_snapshot",
        "metrics",
        {"rsi_14": 100},
        future_date,
    )
    observations.extend([future_membership, future_metric])
    factors.append(_factor("601999", 100, future_metric, future_date))

    _, outputs, summary = build_contextual_group_run(
        as_of_trade_date=TRADE_DATE,
        calculated_at=_timestamp(minute=2),
        factor_rows=factors,
        observations=observations,
        mode="replay",
    )
    assert summary["universe_count"] == 9
    assert all(row["entity_id"] != "601999" for row in outputs)


def test_dynamic_universe_allows_entry_and_excludes_historical_exit():
    observations, factors = _inputs()
    new_code = "601999"
    removed_code = "600999"
    observations[0] = _observation(
        "market",
        "CN-A",
        "universe",
        "universe_snapshot",
        {
            "active_codes": [
                *[f"6000{index:02d}" for index in range(9)],
                new_code,
            ],
            "active_count": 10,
            "membership_semantics": "exact_frozen_rows",
            "upstream_completeness": "test_fixture",
        },
    )
    observations.append(
        _observation(
            "stock",
            new_code,
            "universe",
            "membership",
            {
                "name": "new",
                "group": "watchlist",
                "concepts": ["AI绠楀姏"],
            },
        )
    )
    observations.append(
        _observation(
            "stock",
            removed_code,
            "universe",
            "membership",
            {
                "name": "removed",
                "group": "watchlist",
                "concepts": ["AI绠楀姏"],
            },
            "20260723",
        )
    )

    _, outputs, summary = build_contextual_group_run(
        as_of_trade_date=TRADE_DATE,
        calculated_at=_timestamp(minute=2),
        factor_rows=factors,
        observations=observations,
        mode="replay",
    )

    stock_outputs = {
        row["entity_id"]: row
        for row in outputs
        if row["factor_id"] == STOCK_GROUP_FACTOR_ID
    }
    assert summary["universe_count"] == 10
    assert set(stock_outputs) == {
        *[f"6000{index:02d}" for index in range(9)],
        new_code,
    }
    assert removed_code not in stock_outputs
    assert stock_outputs[new_code]["value"]["status"] == (
        "no_eligible_current_factors"
    )
    assert stock_outputs[new_code]["value"]["factor_groups"] == {}


def test_many_raw_turning_points_become_a_broad_event_candidate():
    observations, factors = _inputs()
    curve_factors = [
        _curve_factor(
            factor["entity_id"],
            factor,
            ["turning_up"] if index < 6 else [],
        )
        for index, factor in enumerate(factors)
    ]
    _, outputs, summary = build_contextual_group_run(
        as_of_trade_date=TRADE_DATE,
        calculated_at=_timestamp(minute=2),
        factor_rows=[*factors, *curve_factors],
        observations=observations,
        mode="replay",
    )

    context = next(
        row
        for row in outputs
        if row["factor_id"] == GROUP_CONTEXT_FACTOR_ID
    )
    event_field = context["value"]["event_field"]
    assert summary["systemic_event_state"] == "broad"
    assert summary["systemic_event_direction"] == "up"
    assert summary["systemic_event_families"] == 1
    assert summary["event_stock_breadth"] == pytest.approx(6 / 9)
    assert event_field["event_count"] == 6
    cluster = next(
        row
        for row in event_field["clusters"]
        if row["event"] == "turning_up"
    )
    assert cluster["member_count"] == 6
    assert cluster["breadth"] == pytest.approx(6 / 9)
    assert cluster["systemic_candidate"] is True
    family = next(
        row
        for row in event_field["event_family_clusters"]
        if row["event"] == "turning_up"
    )
    assert family["member_count"] == 6
    assert family["systemic_candidate"] is True
    assert event_field["thresholds"]["threshold_status"] == (
        "structural_candidate_not_effective_claim"
    )
    context_ref_ids = {
        row["factor_value_id"] for row in context["input_factor_refs"]
    }
    assert {
        row["factor_value_id"] for row in curve_factors
    }.issubset(context_ref_ids)
    assert curve_factors[0]["value"]["series"][
        factor_series_id(factors[0])
    ]["candidate_events"] == ["turning_up"]
    stock_group = next(
        row
        for row in outputs
        if (
            row["factor_id"] == STOCK_GROUP_FACTOR_ID
            and row["entity_id"] == factors[0]["entity_id"]
        )
    )
    stock_series = stock_group["value"]["factor_groups"][
        factor_series_id(factors[0])
    ]
    assert stock_series["curve_candidate_events"] == ["turning_up"]
    assert stock_series["curve_event_detection_ready"] is True
    assert stock_group["value"]["selection_context"][
        "systemic_event_direction"
    ] == "up"


def test_group_identity_is_stable_across_wall_clock_retries():
    observations, factors = _inputs()
    first_manifest, first_outputs, _ = build_contextual_group_run(
        as_of_trade_date=TRADE_DATE,
        calculated_at=_timestamp(minute=2),
        factor_rows=factors,
        observations=observations,
        mode="replay",
    )
    retry_manifest, retry_outputs, _ = build_contextual_group_run(
        as_of_trade_date=TRADE_DATE,
        calculated_at=_timestamp(minute=3),
        factor_rows=factors,
        observations=observations,
        mode="replay",
    )

    assert retry_manifest["run_id"] == first_manifest["run_id"]
    assert (
        retry_manifest["factor_value_digest"]
        == first_manifest["factor_value_digest"]
    )
    assert [row["factor_value_id"] for row in retry_outputs] == [
        row["factor_value_id"] for row in first_outputs
    ]
    assert {row["calculated_at"] for row in first_outputs} == {
        _timestamp(minute=2)
    }
    assert {row["calculated_at"] for row in retry_outputs} == {
        _timestamp(minute=3)
    }


def test_group_parameters_change_version_and_live_late_run_is_rejected():
    assert group_version(GroupParameters(minimum_cross_section=12)) != GROUP_VERSION
    base_id = materialize_group_id(
        GROUP_VERSION,
        axis="factor.cross_section_tertile",
        state="low",
        series_id="legacy_snapshot::legacy.rsi_14::legacy_snapshot_v1",
    )
    assert base_id == materialize_group_id(
        GROUP_VERSION,
        axis="factor.cross_section_tertile",
        state="low",
        series_id="legacy_snapshot::legacy.rsi_14::legacy_snapshot_v1",
    )
    assert base_id != materialize_group_id(
        GROUP_VERSION,
        axis="factor.cross_section_tertile",
        state="high",
        series_id="legacy_snapshot::legacy.rsi_14::legacy_snapshot_v1",
    )
    with pytest.raises(ContractError, match="quantile boundaries"):
        group_version(GroupParameters(lower_quantile=0.8, upper_quantile=0.2))

    observations, factors = _inputs()
    with pytest.raises(ContractError, match="outside"):
        build_contextual_group_run(
            as_of_trade_date=TRADE_DATE,
            calculated_at="2026-07-27T09:00:00+08:00",
            factor_rows=factors,
            observations=observations,
            mode="live",
        )
