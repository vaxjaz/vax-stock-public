# -*- coding: utf-8 -*-

from copy import deepcopy

import pytest

from vaxstock.research.contextual_group import (
    GROUP_VERSION,
    STOCK_GROUP_FACTOR_ID,
    STOCK_GROUP_FACTOR_VERSION,
)
from vaxstock.research.contracts import (
    ContractError,
    canonical_digest,
    make_factor_value_id,
    validate_group_outcome_sample,
)
from vaxstock.research.group_outcome import (
    build_group_outcome_samples,
    merge_legacy_factor_results,
    select_eod_group_assignments,
)


BASELINE = "20260724"
CODE = "601138"


def _group_factor(*, calculated_at="2026-07-25T05:03:11+08:00", eod=True):
    series = (
        "legacy_snapshot::legacy.rsi_14::legacy_snapshot_v1"
        if eod
        else "E::seller_consensus_eps_median_90d.2026Q4::e_v1"
    )
    inputs = ["obs_membership"]
    row = {
        "schema_version": 1,
        "factor_value_id": "",
        "entity_type": "stock",
        "entity_id": CODE,
        "dimension": "research_group",
        "factor_id": STOCK_GROUP_FACTOR_ID,
        "factor_version": STOCK_GROUP_FACTOR_VERSION,
        "value": {
            "group_version": GROUP_VERSION,
            "label_usage": "none",
            "factor_groups": {
                series: {
                    "cross_section": {
                        "status": "available",
                        "rank_pct": 0.8,
                        "bucket": "high",
                    },
                    "curve_state_vector": [None, None, None, None, None],
                    "track_relation_vectors": {},
                }
            },
        },
        "as_of_trade_date": BASELINE,
        "effective_date": BASELINE,
        "available_at": calculated_at,
        "calculated_at": calculated_at,
        "input_observation_ids": inputs,
        "input_digest": canonical_digest(inputs),
        "quality": "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _result_rows():
    return [
        {
            "trade_date": BASELINE,
            "code": CODE,
            "ret": {"1": 0.03},
            "mkt_ret": {"1": 0.01},
            "excess": {"1": 0.02},
            "filled_ts": "2026-07-28T05:00:00",
        },
        {
            "trade_date": BASELINE,
            "code": CODE,
            "horizon_trade_dates": {"1": "20260727"},
            "filled_ts": "2026-07-28T05:01:00",
        },
        {
            "trade_date": BASELINE,
            "code": CODE,
            "ret": {"1": 0.03},
            "mkt_ret": {"1": 0.01},
            "excess": {"1": 0.02},
            "horizon_trade_dates": {"1": "20260727"},
            "filled_ts": "2026-07-29T05:00:00",
        },
    ]


def test_incremental_result_merge_freezes_first_complete_availability():
    outcomes, audit = merge_legacy_factor_results(_result_rows())
    outcome = outcomes[(BASELINE, CODE, 1)]

    assert outcome["outcome_available_at"] == "2026-07-28T05:01:00+08:00"
    assert outcome["first_complete_row_number"] == 2
    assert outcome["availability_timezone_inferred"] is True
    assert outcome["excess_ret"] == pytest.approx(0.02)
    assert audit == {
        "raw_rows": 3,
        "raw_field_entries": 8,
        "duplicate_field_entries": 4,
        "merged_keys": 1,
        "mature_outcomes": 1,
        "incomplete_horizons": 0,
        "inferred_timezone_rows": 3,
        "horizon_counts": {"1": 1},
        "merge_policy": "field_horizon_strict_first_complete_v1",
    }


def test_incremental_result_merge_rejects_conflicts_and_bad_excess():
    conflict = _result_rows()
    conflict[-1]["ret"]["1"] = 0.031
    with pytest.raises(ContractError, match="conflicting"):
        merge_legacy_factor_results(conflict)

    bad_excess = _result_rows()
    for row in bad_excess:
        if row.get("excess"):
            row["excess"]["1"] = 0.03
    with pytest.raises(ContractError, match="excess mismatch"):
        merge_legacy_factor_results(bad_excess)


def test_join_uses_earliest_eod_aligned_group_and_not_preopen_e_only():
    preopen = _group_factor(
        calculated_at="2026-07-24T08:36:02+08:00",
        eod=False,
    )
    eod = _group_factor()
    later_eod = _group_factor(
        calculated_at="2026-07-25T05:04:11+08:00"
    )
    groups, audit = select_eod_group_assignments(
        [preopen, later_eod, eod]
    )

    assert groups[(BASELINE, CODE)]["factor_value_id"] == eod["factor_value_id"]
    assert audit["eod_groups_selected"] == 1
    assert audit["multiple_eod_candidates"] == 1
    assert audit["rejected_non_eod"] == 1

    samples, summary = build_group_outcome_samples(
        group_factor_rows=[preopen, later_eod, eod],
        factor_result_rows=_result_rows(),
    )
    assert len(samples) == 1
    validate_group_outcome_sample(samples[0])
    assert samples[0]["group_factor_value_id"] == eod["factor_value_id"]
    assert samples[0]["horizon_sessions"] == 1
    assert samples[0]["benchmark_code"] == "000001.SH"
    assert samples[0]["benchmark_kind"] == "legacy_market_index"
    assert samples[0]["return_unit"] == "decimal_return"
    assert summary["status"] == "complete"
    assert summary["independent_trade_dates"] == 1
    assert summary["selection_status"] == "not_executed"


def test_join_rejects_group_created_after_outcome_was_available():
    late_group = _group_factor(
        calculated_at="2026-07-28T06:00:00+08:00"
    )
    with pytest.raises(ContractError, match="before its group"):
        build_group_outcome_samples(
            group_factor_rows=[late_group],
            factor_result_rows=_result_rows(),
        )


def test_missing_group_is_partial_not_a_fabricated_sample():
    rows = deepcopy(_result_rows())
    samples, summary = build_group_outcome_samples(
        group_factor_rows=[],
        factor_result_rows=rows,
    )
    assert samples == []
    assert summary["status"] == "partial"
    assert summary["missing_group_samples"] == 1
    assert summary["missing_group_by_trade_date"] == {BASELINE: 1}

