# -*- coding: utf-8 -*-
"""Evidence convergence: session independence, environment shifts and mail section."""

import json
import tempfile
from pathlib import Path

from vaxstock.report.daily_action import render_daily_action_markdown
from vaxstock.services.daily_action import _load_evidence_convergence
from vaxstock.services.evidence_convergence import (
    build_evidence_convergence,
    render_evidence_convergence,
)


def _policy():
    return {
        "action_rules": {
            "history_evidence": {
                "minimum_preliminary_samples": 5,
                "minimum_stable_samples": 20,
                "support_min_absolute_action_hit_rate": 0.6,
                "conflict_max_absolute_action_hit_rate": 0.4,
            }
        }
    }


def _payload():
    return {
        "market_overview": {
            "trade_date": "20260713",
            "up_count": 801,
            "down_count": 4683,
            "total": 5524,
            "limit_down_count": 211,
        },
        "market_regime": "panic",
        "macro": {
            "macro_regime": "中性",
            "indicators": {
                "breadth": {"above_ma60_pct": 10.55},
                "margin_ratio": {"latest_date": "20260710", "stale": True},
            },
        },
        "tracks": [{
            "track_name": "AI算力",
            "available": True,
            "position_ceiling": "进攻档",
            "vetoes": [],
            "pending": [],
        }],
    }


def _row(index, *, triggered, complete=0, late_limited=0, t1=0.01, t5=None):
    fixed = {
        "1": {
            "status": "mature",
            "horizon": "1",
            "actual_trade_date": "20260713",
            "ret": t1,
            "absolute_action_hit": t1 > 0,
        },
        "5": {"status": "pending", "horizon": "5"},
    }
    if t5 is not None:
        fixed["5"] = {
            "status": "mature",
            "horizon": "5",
            "actual_trade_date": "20260713",
            "ret": t5,
            "absolute_action_hit": t5 > 0,
        }
    return {
        "evidence_id": f"ev-{index}",
        "evidence_role": "decision_evidence",
        "identity": {
            "target_trade_date": "20260713",
            "rule_version": "rule-v1",
            "code": f"60{index:04d}",
        },
        "stock": {"code": f"60{index:04d}", "name": f"样本{index}"},
        "frozen_c_prediction": {
            "action": "watch",
            "direction": "up",
            "features_ref": {"market_regime": "value"},
        },
        "c_outcomes": {
            "fixed_horizons": fixed,
            "t_plus_now": fixed["5"] if t5 is not None else fixed["1"],
        },
        "d_evidence": {
            "status": "partial_data" if triggered and not complete else "no_trigger_observed",
            "task_id": f"task-{index}",
            "trigger_count": 1 if triggered else 0,
            "complete_evolution_count": complete,
            "late_limited_evolution_count": late_limited,
        },
    }


def test_same_day_triggers_are_one_environment_event_and_not_13_samples():
    rows = [
        _row(index, triggered=index < 13)
        for index in range(17)
    ]
    report = build_evidence_convergence(
        rows,
        as_of_trade_date="20260713",
        payload=_payload(),
        strategy_policy=_policy(),
    )
    assert report["facts"]["dline_selected_stocks"] == 17
    assert report["facts"]["dline_triggered_stocks"] == 13
    assert report["facts"]["dline_missing_evolution_paths"] == 13
    codes = {row["code"] for row in report["special_findings"]}
    assert "decision_outcome_environment_shift" in codes
    assert "same_day_correlated_trigger_event" in codes
    assert "dline_post_trigger_path_missing" in codes
    change_text = report["convergence"]["changes"][0]["summary"]
    assert "最多1个独立交易日" in change_text
    assert "尚未达到5日初步证据门槛" in change_text
    group = report["convergence"]["groups"][0]
    assert group["observations"] == 17
    assert group["independent_sessions"] == 1
    assert group["verdict"] == "accumulating"
    cluster = next(
        row for row in report["special_findings"]
        if row["code"] == "same_day_correlated_trigger_event"
    )
    assert cluster["effective_environment_event_count"] == 1
    assert report["source_contract"]["user_execution_used"] is False
    assert report["strategy_effect"]["automatic_rule_change"] is False
    repeated = build_evidence_convergence(
        rows,
        as_of_trade_date="20260713",
        payload=_payload(),
        strategy_policy=_policy(),
    )
    assert repeated == report
    assert repeated["facts_digest"] == report["facts_digest"]


def test_t1_t5_reversal_is_explicit_and_rendered():
    report = build_evidence_convergence(
        [_row(1, triggered=False, t1=0.03, t5=-0.04)],
        as_of_trade_date="20260713",
        payload=_payload(),
        strategy_policy=_policy(),
    )
    assert report["facts"]["horizon_reversal_new"] == 1
    assert "t1_t5_sign_reversal" in {
        row["code"] for row in report["special_findings"]
    }
    markdown = render_evidence_convergence(report)
    assert "T+1与T+5收益方向反转" in markdown


def test_daily_action_mail_contains_convergence_chapter():
    convergence = build_evidence_convergence(
        [_row(1, triggered=True, complete=1, late_limited=1)],
        as_of_trade_date="20260713",
        payload=_payload(),
        strategy_policy=_policy(),
    )
    markdown = render_daily_action_markdown({
        "phase": "pre_market",
        "background": {
            "baseline_trade_date": "20260713",
            "target_trade_date": "20260714",
        },
        "account": {"unit_amounts": {}},
        "holdings": [],
        "evidence_convergence": convergence,
    })
    assert "## 证据收敛" in markdown
    assert "**1. 今天新增什么证据**" in markdown
    assert "**4. 是否改变今天动作**" in markdown
    assert "可评价演变1条（其中晚盘触发仅检查可达节点1条）" in markdown


def test_daily_action_only_loads_matching_baseline_convergence():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "convergence_latest.json").write_text(
            json.dumps({"status": "ready", "as_of_trade_date": "20260714"}),
            encoding="utf-8",
        )
        missing = _load_evidence_convergence("20260713", convergence_dir=root)
        assert missing["status"] == "unavailable"
        assert missing["reason"] == "matching_convergence_report_missing"

        expected = {
            "status": "ready",
            "as_of_trade_date": "20260713",
            "facts": {"new_matured_c_results": 1},
        }
        (root / "convergence_20260713.json").write_text(
            json.dumps(expected, ensure_ascii=False),
            encoding="utf-8",
        )
        assert _load_evidence_convergence(
            "20260713", convergence_dir=root,
        ) == expected


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"evidence convergence tests: {len(tests)} PASS")
