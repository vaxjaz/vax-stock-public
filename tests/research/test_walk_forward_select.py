# -*- coding: utf-8 -*-

from copy import deepcopy
from datetime import datetime, timedelta, timezone

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
    make_group_outcome_id,
    validate_selection_audit,
)
from vaxstock.research.walk_forward_select import (
    SelectionPolicy,
    _candidate_states,
    build_candidate_sessions,
    build_selection_audit,
    run_walk_forward_select,
)


TZ = timezone(timedelta(hours=8))
SERIES = "legacy_snapshot::legacy.rsi_14::legacy_snapshot_v1"


def _group(
    trade_date,
    code,
    side,
    calculated_at,
    *,
    all_axes=False,
    selection_context=None,
    include_unavailable_series=False,
    curve_events=None,
):
    inputs = [f"obs_{trade_date}_{code}"]
    factor_groups = {
        SERIES: {
            "cross_section": {
                "status": "available",
                "bucket": side,
                "rank_pct": 0.9 if side == "high" else 0.1,
            },
            "curve_state_vector": (
                [
                    "up",
                    "up",
                    "up",
                    "positive",
                    "up",
                ]
                if all_axes and side == "high"
                else (
                    [
                        "down",
                        "down",
                        "down",
                        "negative",
                        "down",
                    ]
                    if all_axes
                    else [
                        "up" if side == "high" else "down",
                        None,
                        None,
                        None,
                        None,
                    ]
                )
            ),
            "curve_candidate_events": list(curve_events or []),
            "curve_event_detection_ready": bool(all_axes),
            "track_relation_vectors": (
                {
                    "AI": (
                        ["above", "above"]
                        if side == "high"
                        else ["below", "below"]
                    )
                }
                if all_axes
                else {}
            ),
        }
    }
    if include_unavailable_series:
        factor_groups["legacy_snapshot::legacy.roe_avg::legacy_snapshot_v1"] = {
            "cross_section": {
                "status": "thin_cross_section",
                "bucket": None,
                "rank_pct": None,
            },
            "curve_state_vector": [None, None, None, None, None],
            "curve_candidate_events": [],
            "curve_event_detection_ready": False,
            "track_relation_vectors": {},
        }
    row = {
        "schema_version": 1,
        "factor_value_id": "",
        "entity_type": "stock",
        "entity_id": code,
        "dimension": "research_group",
        "factor_id": STOCK_GROUP_FACTOR_ID,
        "factor_version": STOCK_GROUP_FACTOR_VERSION,
        "value": {
            "group_version": GROUP_VERSION,
            "label_usage": "none",
            "selection_context": dict(selection_context or {}),
            "factor_groups": factor_groups,
        },
        "as_of_trade_date": trade_date,
        "effective_date": trade_date,
        "available_at": calculated_at,
        "calculated_at": calculated_at,
        "input_observation_ids": inputs,
        "input_digest": canonical_digest(inputs),
        "quality": "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _outcome(group, outcome_date, available_at, excess, horizon=1):
    row = {
        "schema_version": 1,
        "outcome_id": "",
        "as_of_trade_date": group["as_of_trade_date"],
        "code": group["entity_id"],
        "group_factor_value_id": group["factor_value_id"],
        "group_factor_version": group["factor_version"],
        "group_version": GROUP_VERSION,
        "group_available_at": group["available_at"],
        "group_calculated_at": group["calculated_at"],
        "horizon_sessions": horizon,
        "outcome_trade_date": outcome_date,
        "outcome_available_at": available_at,
        "ret": excess + 0.01,
        "benchmark_ret": 0.01,
        "excess_ret": excess,
        "benchmark_code": "000001.SH",
        "benchmark_kind": "legacy_market_index",
        "source": "legacy.factor_results",
        "source_ref": (
            "var/eval/factor_results.jsonl#"
            f"{group['as_of_trade_date']}:{group['entity_id']}:T+{horizon}"
        ),
        "independent_session_id": group["as_of_trade_date"],
        "input_digest": "",
    }
    row["input_digest"] = canonical_digest({
        "group_factor_value_id": row["group_factor_value_id"],
        "horizon_sessions": row["horizon_sessions"],
        "outcome_trade_date": row["outcome_trade_date"],
        "outcome_available_at": row["outcome_available_at"],
        "ret": row["ret"],
        "benchmark_ret": row["benchmark_ret"],
        "excess_ret": row["excess_ret"],
        "benchmark_code": row["benchmark_code"],
        "source": row["source"],
    })
    row["outcome_id"] = make_group_outcome_id(row)
    return row


def _cross_section(
    trade_date="20260701",
    outcome_date="20260702",
    *,
    missing_code=None,
    late_code=None,
):
    group_time = (
        datetime.strptime(trade_date, "%Y%m%d")
        .replace(tzinfo=TZ)
        + timedelta(days=1, hours=5)
    ).isoformat(timespec="seconds")
    outcome_time = (
        datetime.strptime(outcome_date, "%Y%m%d")
        .replace(tzinfo=TZ)
        + timedelta(days=1, hours=5)
    ).isoformat(timespec="seconds")
    groups = []
    outcomes = []
    for index in range(6):
        code = f"6000{index:02d}"
        side = "high" if index < 3 else "low"
        group = _group(trade_date, code, side, group_time)
        groups.append(group)
        if code == missing_code:
            continue
        available = (
            "2026-08-01T05:00:00+08:00"
            if code == late_code
            else outcome_time
        )
        outcomes.append(
            _outcome(
                group,
                outcome_date,
                available,
                0.03 if side == "high" else -0.01,
            )
        )
    return groups, outcomes


def test_candidate_sessions_use_complete_daily_cross_section_not_stock_rows():
    groups, outcomes = _cross_section()
    sessions, audit = build_candidate_sessions(
        group_factor_rows=groups,
        outcome_rows=outcomes,
        horizon_sessions=1,
        decision_at="2026-07-03T06:00:00+08:00",
    )

    assert len(sessions) == 2
    assert {row["axis"] for row in sessions} == {
        "cross_section_bucket",
        "curve_slope",
    }
    assert all(row["spread"] == pytest.approx(0.04) for row in sessions)
    assert all(row["positive_n"] == 3 for row in sessions)
    assert audit["complete_outcome_trade_dates"] == 1
    assert audit["candidate_tests"] == 2
    assert audit["statistical_unit"] == "complete_daily_cross_section"


def test_partial_or_not_yet_available_outcome_excludes_entire_date():
    groups, outcomes = _cross_section(missing_code="600005")
    sessions, audit = build_candidate_sessions(
        group_factor_rows=groups,
        outcome_rows=outcomes,
        horizon_sessions=1,
        decision_at="2026-07-03T06:00:00+08:00",
    )
    assert sessions == []
    assert audit["incomplete_by_trade_date"]["20260701"] == {
        "expected": 6,
        "available": 5,
    }

    groups, outcomes = _cross_section(late_code="600005")
    sessions, audit = build_candidate_sessions(
        group_factor_rows=groups,
        outcome_rows=outcomes,
        horizon_sessions=1,
        decision_at="2026-07-03T06:00:00+08:00",
    )
    assert sessions == []
    assert audit["incomplete_by_trade_date"]["20260701"] == {
        "expected": 6,
        "available": 5,
    }


def test_superseded_group_outcome_version_is_retained_but_not_mixed():
    groups, outcomes = _cross_section()
    old_group = deepcopy(groups[0])
    old_group["factor_version"] = "stock_group_vector_v1"
    old_group["value"]["group_version"] = "contextual_multiview_group_v1"
    old_group["factor_value_id"] = make_factor_value_id(old_group)
    old_outcome = _outcome(
        old_group,
        outcomes[0]["outcome_trade_date"],
        outcomes[0]["outcome_available_at"],
        outcomes[0]["excess_ret"],
    )
    old_outcome["group_version"] = "contextual_multiview_group_v1"

    sessions, audit = build_candidate_sessions(
        group_factor_rows=groups,
        outcome_rows=[old_outcome, *outcomes],
        horizon_sessions=1,
        decision_at="2026-07-03T06:00:00+08:00",
    )

    assert len(sessions) == 2
    assert audit["superseded_outcomes_excluded"] == 1
    assert audit["outcome_conflicts"] == 0


def test_select_covers_all_available_axes_and_reports_untestable_series():
    context = {
        "market_regime": "panic",
        "macro_regime": "contraction",
        "systemic_event_state": "broad",
        "systemic_event_direction": "mixed",
    }
    group_time = "2026-07-02T05:00:00+08:00"
    outcome_time = "2026-07-03T05:00:00+08:00"
    rich_groups = []
    rich_outcomes = []
    for index in range(12):
        code = f"6001{index:02d}"
        side = "high" if index < 6 else "low"
        if index < 3:
            events = ["turning_up"]
        elif index < 6:
            events = []
        elif index < 9:
            events = ["turning_down"]
        else:
            events = []
        rebuilt = _group(
            "20260701",
            code,
            side,
            group_time,
            all_axes=True,
            selection_context=context,
            include_unavailable_series=True,
            curve_events=events,
        )
        rich_groups.append(rebuilt)
        rich_outcomes.append(
            _outcome(
                rebuilt,
                "20260702",
                outcome_time,
                0.03 if side == "high" else -0.01,
            )
        )

    sessions, audit = build_candidate_sessions(
        group_factor_rows=rich_groups,
        outcome_rows=rich_outcomes,
        horizon_sessions=1,
        decision_at="2026-07-03T06:00:00+08:00",
    )

    assert len(sessions) == 50
    assert {row["axis"] for row in sessions} == {
        "cross_section_bucket",
        "curve_slope",
        "curve_acceleration",
        "curve_turning",
        "curve_anomaly",
        "curve_change_point",
        "curve_event_presence",
        "curve_event_direction",
        "track_level_relation",
        "track_slope_relation",
    }
    assert {tuple(sorted(row["condition"].items())) for row in sessions} == {
        (),
        (("market_regime", "panic"),),
        (("macro_regime", "contraction"),),
        (("systemic_event_state", "broad"),),
        (("systemic_event_direction", "mixed"),),
    }
    assert audit["factor_series_total"] == 2
    assert audit["factor_series_tested"] == 1
    assert audit["factor_series_untested"] == 1
    coverage = {
        row["series_id"]: row for row in audit["factor_coverage"]
    }
    assert coverage[SERIES]["candidate_axes_seen"] == sorted({
        "cross_section_bucket",
        "curve_slope",
        "curve_acceleration",
        "curve_turning",
        "curve_anomaly",
        "curve_change_point",
        "curve_event_presence",
        "curve_event_direction",
        "track_level_relation",
        "track_slope_relation",
    })
    assert coverage[
        "legacy_snapshot::legacy.roe_avg::legacy_snapshot_v1"
    ]["status"] == "unavailable_or_one_sided"


def test_anchor_conditions_only_attach_to_registered_track_relations():
    context = {
        "market_regime": "panic",
        "anchor_nvda_direction": "down",
        "anchor_equity_majority_direction": "down",
    }
    group = _group(
        "20260701",
        "600001",
        "high",
        "2026-07-02T05:00:00+08:00",
        all_axes=True,
        selection_context=context,
    )
    relation = group["value"]["factor_groups"][SERIES][
        "track_relation_vectors"
    ].pop("AI")
    group["value"]["factor_groups"][SERIES][
        "track_relation_vectors"
    ]["AI算力"] = relation
    candidates = list(_candidate_states(group))

    cross_conditions = [
        row["condition"]
        for row in candidates
        if row["axis"] == "cross_section_bucket"
    ]
    track_conditions = [
        row["condition"]
        for row in candidates
        if (
            row["axis"] == "track_level_relation"
            and row["concept"] == "AI算力"
        )
    ]
    assert {"market_regime": "panic"} in cross_conditions
    assert not any(
        set(condition) & {
            "anchor_nvda_direction",
            "anchor_equity_majority_direction",
        }
        for condition in cross_conditions
    )
    assert {"anchor_nvda_direction": "down"} in track_conditions
    assert {
        "anchor_equity_majority_direction": "down"
    } in track_conditions


def _candidate_rows(count=8):
    rows = []
    base = datetime(2026, 7, 1, tzinfo=TZ)
    for index in range(count):
        baseline = (base + timedelta(days=index)).strftime("%Y%m%d")
        outcome = (base + timedelta(days=index + 1)).strftime("%Y%m%d")
        rows.append({
            "candidate_id": "candidate_a",
            "series_id": SERIES,
            "axis": "cross_section_bucket",
            "positive_state": "high",
            "negative_state": "low",
            "as_of_trade_date": baseline,
            "outcome_trade_date": outcome,
            "outcome_available_at": (
                base + timedelta(days=index + 1, hours=5)
            ).isoformat(timespec="seconds"),
            "decision_at": (
                base + timedelta(days=index + 1, hours=6)
            ).isoformat(timespec="seconds"),
            "horizon_sessions": 1,
            "positive_n": 3,
            "negative_n": 3,
            "positive_mean_excess": 0.02,
            "negative_mean_excess": 0.0,
            "spread": 0.02,
            "statistical_unit": "complete_daily_cross_section",
        })
    return rows


def test_walk_forward_purges_future_labels_and_applies_embargo():
    result = run_walk_forward_select(
        candidate_sessions=_candidate_rows(),
        horizon_sessions=1,
        policy=SelectionPolicy(
            min_side_stocks=3,
            min_train_dates=2,
            min_oos_dates=1,
            top_k=1,
            embargo_sessions=1,
        ),
    )
    assert result["status"] == "shadow_candidate"
    assert result["production_eligible"] is False
    assert result["promotion_status"] == "manual_review_required"
    assert result["folds"][0]["validation_trade_date"] == "20260705"
    assert result["folds"][0]["selected"][0]["training"][
        "independent_dates"
    ] == 2
    assert result["leakage_controls"]["embargo_sessions"] == 1


def test_walk_forward_freezes_current_candidates_for_forecast():
    result = run_walk_forward_select(
        candidate_sessions=_candidate_rows(10),
        horizon_sessions=1,
        policy=SelectionPolicy(
            min_side_stocks=3,
            min_train_dates=2,
            min_oos_dates=1,
            top_k=1,
            embargo_sessions=1,
        ),
        current_as_of_trade_date="20260711",
        current_decision_at="2026-07-12T06:00:00+08:00",
    )

    assert result["status"] == "shadow_candidate"
    assert result["current_candidate_tests"] == 1
    assert len(result["current_candidates"]) == 1
    assert result["current_candidates"][0]["candidate_id"] == "candidate_a"
    assert result["current_candidates"][0]["training"][
        "independent_dates"
    ] == 8


def test_default_policy_abstains_on_short_history():
    result = run_walk_forward_select(
        candidate_sessions=_candidate_rows(21),
        horizon_sessions=1,
    )
    assert result["status"] == "abstain"
    assert result["abstain_reason"] == "insufficient_independent_oos_dates"
    assert result["independent_dates_available"] == 21
    assert result["oos_independent_dates"] == 0
    assert result["evidence_label"] == "insufficient_history"
    diagnostics = result["exploratory_diagnostics"]
    assert diagnostics["candidate_count"] == 1
    assert diagnostics["direction_consistent_count"] == 1
    assert diagnostics["forecast_eligible"] is False
    candidate = diagnostics["direction_consistent_candidates"][0]
    assert candidate["independent_dates"] == 21
    assert candidate["rolling_windows"]["5"]["direction"] == "positive"
    assert candidate["evidence_status"] == (
        "exploratory_below_training_minimum"
    )


def test_exploratory_diagnostics_exposes_recent_reversal_without_smoothing():
    rows = _candidate_rows(21)
    for row in rows[-5:]:
        row["spread"] = -0.04
        row["positive_mean_excess"] = -0.02
        row["negative_mean_excess"] = 0.02

    result = run_walk_forward_select(
        candidate_sessions=rows,
        horizon_sessions=1,
    )

    diagnostics = result["exploratory_diagnostics"]
    assert diagnostics["recent_reversal_count"] == 1
    reversal = diagnostics["recent_reversals"][0]
    assert reversal["full_history"]["direction"] == "positive"
    assert reversal["rolling_windows"]["5"]["direction"] == "negative"
    assert reversal["recent_reversal"] is True
    assert reversal["forecast_eligible"] is False


def test_selection_audit_never_promotes_to_production():
    groups, outcomes = _cross_section()
    audit = build_selection_audit(
        group_factor_rows=groups,
        outcome_rows=outcomes,
        as_of_trade_date="20260702",
        decision_at="2026-07-03T06:00:00+08:00",
        horizons=[1],
        policy=SelectionPolicy(
            min_side_stocks=3,
            min_train_dates=2,
            min_oos_dates=1,
            top_k=1,
            embargo_sessions=0,
        ),
    )
    assert audit["production_eligible"] is False
    assert audit["promotion_status"] == "manual_review_required"
    assert audit["status_counts"] == {"abstain": 1}
    validate_selection_audit(audit)
    with pytest.raises(ContractError, match="production eligible"):
        validate_selection_audit(dict(audit, production_eligible=True))
