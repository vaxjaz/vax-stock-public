# -*- coding: utf-8 -*-
"""Evidence ledger: identity, T+now, D independence and idempotency."""

import json
import tempfile
from pathlib import Path

from vaxstock.services.evidence_ledger import (
    build_evidence_objects,
    build_evidence_review,
    hydrate_evidence_objects,
    record_evidence_objects,
    record_evidence_reviews,
    render_evidence_summary,
)


def _prediction(**overrides):
    row = {
        "prediction_id": "20260710_20260713_601138_rule_live",
        "generation_mode": "live",
        "baseline_trade_date": "20260710",
        "target_trade_date": "20260713",
        "code": "601138",
        "name": "工业富联",
        "group": "holding",
        "features_ref": {"price_at_baseline": 64.31, "market_regime": "panic"},
        "prediction": {
            "action": "panic_rebound_watch",
            "direction": "up",
            "confidence": 0.45,
            "horizon": "T+1",
            "reason_codes": ["panic_downgrade"],
            "reason": "只观察",
        },
        "rule_version": "rule",
        "model_version": "manual_rules_v1",
    }
    row.update(overrides)
    return row


def _snapshot(price=64.31):
    return {
        "trade_date": "20260710",
        "code": "601138",
        "name": "工业富联",
        "group": "holding",
        "price_at_snapshot": price,
        "metrics": {"ma20": 70.0},
    }


def _write_report(reports: Path, *, price=64.31, stock_date="20260710"):
    path = reports / "2026-07-10" / "payload.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "market_overview": {"trade_date": "20260710"},
        "stocks": [{
            "code": "601138",
            "configured_name": "工业富联",
            "realtime": {"price": price, "trade_date": stock_date},
            "metrics": {"ma20": 70.0},
        }],
    }, ensure_ascii=False), encoding="utf-8")


def _root():
    with tempfile.TemporaryDirectory() as temp:
        reports = Path(temp) / "reports"
        _write_report(reports)
        roots, stats = build_evidence_objects(
            [_prediction()], [_snapshot()],
            as_of_trade_date="20260713", reports_dir=reports,
        )
        assert stats["ready"] == 1
        return roots[0]


def test_root_requires_matching_a_b_c_identity():
    with tempfile.TemporaryDirectory() as temp:
        reports = Path(temp) / "reports"
        _write_report(reports)
        roots, stats = build_evidence_objects(
            [_prediction()], [_snapshot()],
            as_of_trade_date="20260713", reports_dir=reports,
        )
        assert len(roots) == 1
        assert roots[0]["evidence_quality"] == "exact_a_b_c_identity"
        assert roots[0]["identity_checks"] == {
            "a_report_trade_date": "20260710",
            "a_stock_trade_date": "20260710",
            "a_realtime_price": 64.31,
            "a_realtime_status": "aligned",
            "a_realtime_used_for_decision": False,
            "b_snapshot_price": 64.31,
            "c_frozen_price": 64.31,
            "b_c_prices_match": True,
            "a_b_c_prices_match": True,
            "decision_price_source": "B_factor_snapshot.price_at_snapshot",
        }
        assert roots[0]["review_contract"]["automatic_rule_change"] is False

        conflict, bad = build_evidence_objects(
            [_prediction()], [_snapshot(price=64.30)],
            as_of_trade_date="20260713", reports_dir=reports,
        )
        assert conflict == []
        assert bad["identity_conflict"] == 1


def test_root_marks_a_stock_date_drift_without_discarding_frozen_b_c():
    with tempfile.TemporaryDirectory() as temp:
        reports = Path(temp) / "reports"
        _write_report(reports, stock_date="20260713")
        roots, stats = build_evidence_objects(
            [_prediction()], [_snapshot()],
            as_of_trade_date="20260713", reports_dir=reports,
        )
        assert len(roots) == 1
        assert stats["a_realtime_drift"] == 1
        assert roots[0]["evidence_quality"] == "frozen_b_c_verified_with_a_realtime_drift"
        assert roots[0]["identity_checks"]["a_realtime_status"] == "drifted_late_or_overwritten"
        assert roots[0]["identity_checks"]["a_realtime_used_for_decision"] is False


def test_evidence_root_and_review_are_idempotent():
    root = _root()
    with tempfile.TemporaryDirectory() as temp:
        evidence_path = Path(temp) / "evidence.jsonl"
        assert record_evidence_objects([root], path=evidence_path) == {"written": 1, "skipped": 0}
        assert record_evidence_objects([root], path=evidence_path) == {"written": 0, "skipped": 1}
        changed = dict(root)
        changed["decision_facts_digest"] = "conflicting-frozen-facts"
        try:
            record_evidence_objects([changed], path=evidence_path)
        except ValueError as exc:
            assert "immutable evidence conflict" in str(exc)
        else:
            raise AssertionError("changed frozen facts must not be silently skipped")

        hydrated = hydrate_evidence_objects(
            [root], as_of_trade_date="20260713", prediction_results=[],
        )[0]
        review = build_evidence_review(
            hydrated,
            review_version="open_review_v1",
            reviewer="llm:test",
            analysis="样本尚未成熟，不形成规则结论。",
            data_limitations=["没有成熟收益点"],
        )
        assert review["facts_digest"] == hydrated["hydrated_facts_digest"]
        assert review["role"] == "interpretation_not_fact"
        assert review["automatic_rule_change"] is False
        review_path = Path(temp) / "reviews.jsonl"
        assert record_evidence_reviews([review], path=review_path) == {"written": 1, "skipped": 0}
        assert record_evidence_reviews([review], path=review_path) == {"written": 0, "skipped": 1}
        changed_review = build_evidence_review(
            hydrated,
            review_version="open_review_v1",
            reviewer="llm:test",
            analysis="同一版本却改变了解释正文。",
        )
        assert changed_review["review_id"] == review["review_id"]
        try:
            record_evidence_reviews([changed_review], path=review_path)
        except ValueError as exc:
            assert "immutable evidence review conflict" in str(exc)
        else:
            raise AssertionError("changed review text requires a new review_version")


def test_t_plus_now_uses_full_path_beyond_30_and_keeps_fixed_points():
    root = _root()
    pid = root["identity"]["prediction_id"]
    results = [
        {"prediction_id": pid, "horizon": "1", "actual": {"trade_date": "20260713", "ret": -0.02, "excess": -0.01}},
        {"prediction_id": pid, "horizon": "5", "actual": {"trade_date": "20260717", "ret": 0.03, "excess": 0.01}},
        {"prediction_id": pid, "horizon": "31", "actual": {"trade_date": "20260824", "ret": 0.12, "excess": 0.04}},
        {"prediction_id": pid, "horizon": "40", "actual": {"ret": 0.99, "excess": 0.50}},
    ]
    hydrated = hydrate_evidence_objects(
        [root], as_of_trade_date="20260824", prediction_results=results,
    )[0]
    outcome = hydrated["c_outcomes"]
    assert outcome["t_plus_now"]["horizon"] == "31"
    assert outcome["t_plus_now"]["ret"] == 0.12
    assert outcome["t_plus_now"]["absolute_action_hit"] is True
    assert outcome["fixed_horizons"]["1"]["ret"] == -0.02
    assert outcome["fixed_horizons"]["10"]["status"] == "pending"
    assert outcome["fixed_horizons"]["30"]["status"] == "pending"

    report = render_evidence_summary([hydrated], as_of_trade_date="20260824")
    assert "T+now T+31 +12.00%" in report
    assert "T+1 -2.00%" in report
    assert "T+10 待回填" in report
    assert "原始动作复核: 命中" in report


def test_dline_distinguishes_missing_not_selected_and_partial_without_execution():
    root = _root()
    missing = hydrate_evidence_objects(
        [root], as_of_trade_date="20260713", prediction_results=[],
    )[0]["d_evidence"]
    assert missing["status"] == "d_data_missing"

    other_task = {
        "task_id": "other", "target_trade_date": "20260713", "code": "000001",
        "plan_version": "d_observe_llm_v2",
    }
    not_selected = hydrate_evidence_objects(
        [root], as_of_trade_date="20260713", prediction_results=[],
        observation_tasks=[other_task],
    )[0]["d_evidence"]
    assert not_selected["status"] == "not_selected"

    task = {
        "task_id": "task-1", "target_trade_date": "20260713", "code": "601138",
        "plan_version": "d_observe_llm_v2",
    }
    partial = hydrate_evidence_objects(
        [root], as_of_trade_date="20260713", prediction_results=[],
        observation_tasks=[task], forecasts=[{"inputs_ref": {"dline_task_id": "task-1"}, "structured": {"trigger_type": "risk"}}],
    )[0]["d_evidence"]
    assert partial["status"] == "partial_data"
    assert partial["user_execution_used"] is False

    complete = hydrate_evidence_objects(
        [root], as_of_trade_date="20260713", prediction_results=[],
        observation_tasks=[task],
        forecasts=[{"inputs_ref": {"dline_task_id": "task-1"}, "structured": {"trigger_type": "risk"}}],
        forecast_evolution=[{"task_id": "task-1", "trigger_type": "risk", "quality": {"complete": True}}],
    )[0]["d_evidence"]
    assert complete["status"] == "triggered_complete"
    assert complete["user_execution_used"] is False


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"evidence ledger tests: {len(tests)} PASS")
