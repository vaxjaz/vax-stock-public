# -*- coding: utf-8 -*-

from datetime import datetime, timedelta, timezone

import pytest

from vaxstock.research.contextual_group import (
    GROUP_VERSION,
    STOCK_GROUP_FACTOR_ID,
    GroupParameters,
    build_contextual_group_run,
    factor_series_id,
    group_version,
    materialize_group_id,
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


def _inputs():
    observations = [
        _observation(
            "market",
            "CN-A",
            "market_context",
            "market_snapshot",
            {"regime": "panic", "macro_regime": None},
        )
    ]
    factors = []
    for index in range(9):
        code = f"6000{index:02d}"
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
