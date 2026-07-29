# -*- coding: utf-8 -*-

from vaxstock.research.anchor_trend_forecast import (
    build_anchor_trend_forecast,
)
from vaxstock.research.contracts import (
    canonical_digest,
    factor_input_digest,
    make_factor_value_id,
)
from vaxstock.research.global_anchor_dimension import (
    ANCHOR_CONTEXT_ENTITY_ID,
    ANCHOR_CONTEXT_FACTOR_ID,
    ANCHOR_CONTEXT_FACTOR_VERSION,
    DIMENSION,
)


DECISION_AT = "2026-07-29T05:00:00+08:00"


def _anchor(trade_date, majority, *, calculated_at=DECISION_AT):
    states = {
        "anchor_nvda_direction": majority,
        "anchor_soxx_direction": majority,
        "anchor_qqq_direction": majority,
        "anchor_vix_direction": (
            "down" if majority == "up" else "up"
        ),
        "anchor_equity_majority_direction": majority,
    }
    inputs = [f"obs_{trade_date}"]
    row = {
        "schema_version": 1,
        "factor_value_id": "",
        "entity_type": "market",
        "entity_id": ANCHOR_CONTEXT_ENTITY_ID,
        "dimension": DIMENSION,
        "factor_id": ANCHOR_CONTEXT_FACTOR_ID,
        "factor_version": ANCHOR_CONTEXT_FACTOR_VERSION,
        "value": {"states": states},
        "as_of_trade_date": trade_date,
        "effective_date": trade_date,
        "available_at": calculated_at,
        "calculated_at": calculated_at,
        "input_observation_ids": inputs,
        "input_digest": factor_input_digest(inputs),
        "quality": "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _snapshots(trade_dates, codes=("600001", "600002", "600003")):
    return [
        {
            "trade_date": trade_date,
            "code": code,
            "concepts": ["AI算力"],
        }
        for trade_date in trade_dates
        for code in codes
    ]


def _result(trade_date, code, excess, *, filled_ts=DECISION_AT):
    benchmark = 0.01
    horizon_date = str(int(trade_date) + 1)
    return {
        "trade_date": trade_date,
        "code": code,
        "ret": {"1": benchmark + excess},
        "mkt_ret": {"1": benchmark},
        "excess": {"1": excess},
        "horizon_trade_dates": {"1": horizon_date},
        "filled_ts": filled_ts,
    }


def test_probability_uses_complete_independent_dates_and_shrinks():
    historical_dates = [
        "20260720",
        "20260721",
        "20260722",
        "20260723",
        "20260724",
        "20260725",
    ]
    anchors = [
        _anchor("20260720", "down"),
        _anchor("20260721", "down"),
        _anchor("20260722", "down"),
        _anchor("20260723", "down"),
        _anchor("20260724", "down"),
        _anchor("20260725", "up"),
        _anchor("20260728", "down"),
    ]
    results = [
        _result(trade_date, code, excess)
        for trade_date, excess in (
            ("20260720", -0.02),
            ("20260721", -0.01),
            ("20260722", -0.02),
            ("20260723", -0.01),
            ("20260724", -0.02),
            ("20260725", 0.03),
        )
        for code in ("600001", "600002", "600003")
    ]

    audit = build_anchor_trend_forecast(
        as_of_trade_date="20260728",
        decision_at=DECISION_AT,
        anchor_factor_rows=anchors,
        snapshots=_snapshots([*historical_dates, "20260728"]),
        factor_result_rows=results,
        horizons=[1],
    )
    forecast = audit["horizons"]["1"]

    assert forecast["status"] == "estimated"
    assert forecast["direction"] == "negative_excess"
    assert forecast["base_independent_dates"] == 6
    assert forecast["primary_condition"]["independent_dates"] == 5
    assert forecast["primary_condition"]["positive_dates"] == 0
    assert 0 < forecast["probability_positive_excess"] < (
        forecast["base_probability_positive_excess"]
    )
    assert forecast["session_coverage"]["complete_dates"] == 6
    assert forecast["absolute_direction"] == "down"
    assert forecast["probability_positive_return"] is not None
    assert forecast["production_eligible"] is False


def test_incomplete_track_date_is_excluded_not_smoothed():
    anchors = [
        _anchor("20260724", "down"),
        _anchor("20260728", "down"),
    ]
    results = [
        _result("20260724", "600001", -0.02),
        _result("20260724", "600002", -0.02),
    ]

    audit = build_anchor_trend_forecast(
        as_of_trade_date="20260728",
        decision_at=DECISION_AT,
        anchor_factor_rows=anchors,
        snapshots=_snapshots(["20260724", "20260728"]),
        factor_result_rows=results,
        horizons=[1],
    )
    forecast = audit["horizons"]["1"]

    assert forecast["status"] == "abstain"
    assert forecast["probability_positive_excess"] is None
    assert forecast["base_independent_dates"] == 0
    assert forecast["session_coverage"][
        "excluded_incomplete_outcomes"
    ][0]["missing_codes"] == ["600003"]


def test_no_matching_current_state_abstains_instead_of_using_base_rate():
    anchors = [
        _anchor("20260724", "up"),
        _anchor("20260728", "down"),
    ]
    results = [
        _result("20260724", code, 0.02)
        for code in ("600001", "600002", "600003")
    ]

    audit = build_anchor_trend_forecast(
        as_of_trade_date="20260728",
        decision_at=DECISION_AT,
        anchor_factor_rows=anchors,
        snapshots=_snapshots(["20260724", "20260728"]),
        factor_result_rows=results,
        horizons=[1],
    )
    forecast = audit["horizons"]["1"]

    assert forecast["status"] == "abstain"
    assert forecast["abstain_reason"] == "no_matching_history"
    assert forecast["probability_positive_excess"] is None
    assert forecast["base_probability_positive_excess"] > 0
    assert audit["input_digest"] == canonical_digest({
        "as_of_trade_date": "20260728",
        "decision_at": DECISION_AT,
        "forecast_version": audit["forecast_version"],
        "select_version": audit["select_version"],
        "group_version": audit["group_version"],
        "current_anchor_factor_value_id": (
            audit["current_anchor_factor_value_id"]
        ),
        "current_track_codes": ["600001", "600002", "600003"],
        "used_sessions": [{
            "horizon": 1,
            "trade_date": "20260724",
            "member_count": 3,
            "member_codes": ["600001", "600002", "600003"],
            "track_return": 0.03,
            "track_excess_return": 0.02,
            "anchor_factor_value_id": anchors[0]["factor_value_id"],
        }],
    })


def test_missing_current_track_membership_blocks_current_probability():
    anchors = [
        _anchor("20260724", "down"),
        _anchor("20260728", "down"),
    ]
    results = [
        _result("20260724", code, -0.02)
        for code in ("600001", "600002", "600003")
    ]

    audit = build_anchor_trend_forecast(
        as_of_trade_date="20260728",
        decision_at=DECISION_AT,
        anchor_factor_rows=anchors,
        snapshots=_snapshots(["20260724"]),
        factor_result_rows=results,
        horizons=[1],
    )
    forecast = audit["horizons"]["1"]

    assert audit["current_track_membership"]["status"] == (
        "insufficient_members"
    )
    assert forecast["status"] == "abstain"
    assert forecast["probability_positive_return"] is None
    assert forecast["probability_positive_excess"] is None
    assert forecast["abstain_reason"] == (
        "current_track_membership_insufficient"
    )
