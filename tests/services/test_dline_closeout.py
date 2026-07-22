# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path

from vaxstock.services.dline_closeout import _audit_evidence, run_dline_closeout


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _task(code="600001", trigger_type="reclaim_confirm"):
    task_id = f"20260713_20260714_{code}_d_observe_llm_v2"
    return {
        "task_id": task_id,
        "code": code,
        "name": code,
        "baseline_trade_date": "20260713",
        "target_trade_date": "20260714",
        "plan_version": "d_observe_llm_v2",
        "evidence_pack": {
            "C_prediction": {
                "prediction": {
                    "rule_version": "c_v1",
                    "action": "candidate_buy",
                    "direction": "up",
                    "confidence": 0.7,
                }
            }
        },
        "observation": {
            "trigger_blueprints": [{
                "trigger_type": trigger_type,
                "severity": "medium",
                "condition": {
                    "all": [{"field": "price_vs_ma20_pct", "op": ">", "value": 0}],
                },
            }],
        },
    }


def _forecast(task, price=100.0):
    trigger_type = task["observation"]["trigger_blueprints"][0]["trigger_type"]
    return {
        "forecast_ts": "2026-07-14T10:00:01",
        "trade_date": "20260714",
        "code": task["code"],
        "inputs_ref": {
            "dline_task_id": task["task_id"],
            "dline_plan_version": "d_observe_llm_v2",
            "trigger_blueprint": {"trigger_type": trigger_type, "severity": "medium"},
            "quote_snapshot": {
                "trade_time": "10:00:00",
                "price": price,
                "change_pct": 1.0,
                "source": "sina",
            },
        },
        "structured": {
            "source": "dline_task_blueprint",
            "task_id": task["task_id"],
            "trigger_type": trigger_type,
        },
    }


def _coverage(task, qualified=True):
    return {
        "coverage_id": f"coverage-{task['task_id']}",
        "target_trade_date": "20260714",
        "task_id": task["task_id"],
        "code": task["code"],
        "quality": {"policy_version": "d_full_session_v1", "qualified": qualified},
    }


def _evolution(task, complete=True):
    trigger_type = task["observation"]["trigger_blueprints"][0]["trigger_type"]
    return {
        "evolution_id": f"evolution-{task['task_id']}-{trigger_type}",
        "target_trade_date": "20260714",
        "task_id": task["task_id"],
        "code": task["code"],
        "trigger_type": trigger_type,
        "quality": {"policy_version": "d_intraday_evolution_v1", "complete": complete},
        "evaluation": {"user_execution_used": False, "official_eod_close_used": False},
    }


def _paths(root: Path):
    return {
        "status_path": root / "current_closeout_status.json",
        "tasks_path": root / "observation_tasks.jsonl",
        "forecasts_path": root / "forecasts.jsonl",
        "coverage_path": root / "observation_coverage.jsonl",
        "observation_status_path": root / "current_observation_status.json",
        "evolution_path": root / "forecast_evolution.jsonl",
        "evolution_status_path": root / "current_evolution_status.json",
        "snapshots_path": root / "factor_snapshots.jsonl",
        "factor_results_path": root / "factor_results.jsonl",
        "results_path": root / "forecast_results.jsonl",
        "review_output_dir": root / "reviews",
        "review_state_path": root / "reviews" / "latest.json",
    }


def _seed_complete(paths, fired, quiet=None):
    tasks = [fired] + ([quiet] if quiet else [])
    _write_jsonl(paths["tasks_path"], tasks)
    _write_jsonl(paths["forecasts_path"], [_forecast(fired)])
    _write_jsonl(paths["coverage_path"], [_coverage(task) for task in tasks])
    _write_jsonl(paths["evolution_path"], [_evolution(fired)])
    _write_jsonl(paths["snapshots_path"], [
        {"trade_date": "20260714", "code": task["code"], "price_at_snapshot": 102.0}
        for task in tasks
    ])
    _write_jsonl(paths["factor_results_path"], [
        {
            "trade_date": "20260714",
            "code": task["code"],
            "ret": {"1": 0.03},
            "horizon_trade_dates": {"1": "20260715"},
        }
        for task in tasks
    ])


def test_closeout_audit_uses_latest_same_day_task_per_code():
    old = _task("600001")
    revised = _task("600001")
    revised["task_id"] += "_manual_v1"
    evidence = _audit_evidence(
        target="20260714",
        tasks=[old, revised],
        forecasts=[],
        coverage_rows=[],
        evolution_rows=[],
        result_rows=[],
        result_stage_ok=False,
    )

    assert evidence["task_count"] == 1
    coverage_gap = next(row for row in evidence["gaps"] if row["code"] == "coverage_missing")
    assert coverage_gap["examples"] == [revised["task_id"]]


def test_closeout_is_complete_and_idempotent_when_evidence_exists():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        fired = _task("600001")
        quiet = _task("600002")
        _seed_complete(paths, fired, quiet)
        notifications = []

        first = run_dline_closeout(
            trade_date="20260714",
            notifier=lambda title, body: notifications.append((title, body)),
            now="2026-07-15T05:00:00",
            **paths,
        )
        result_count = len(
            paths["results_path"].read_text(encoding="utf-8").splitlines()
        )
        second = run_dline_closeout(
            trade_date="20260714",
            notifier=lambda title, body: notifications.append((title, body)),
            now="2026-07-15T05:01:00",
            **paths,
        )
        second_count = len(
            paths["results_path"].read_text(encoding="utf-8").splitlines()
        )

    assert first["status"] == second["status"] == "done"
    assert first["evidence"]["task_count"] == 2
    assert first["evidence"]["trigger_count"] == 1
    assert first["evidence"]["qualified_coverage_count"] == 2
    assert first["evidence"]["complete_evolution_count"] == 1
    assert first["evidence"]["trigger_t0_result_count"] == 1
    assert first["evidence"]["gaps"] == []
    assert first["user_execution_used"] is False
    assert result_count == second_count == 3
    assert second["stages"]["result_backfill"]["written"] == 0
    assert notifications == []


def test_closeout_accepts_legacy_late_trigger_without_unreachable_checkpoints():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        task = _task("600001", "breakdown_confirm")
        _seed_complete(paths, task)
        legacy_late = _evolution(task, complete=False)
        legacy_late.update({
            "trigger": {"trade_time": "14:47:48", "price": 100.0},
            "checkpoints": {
                "trigger": {"trade_time": "14:47:48", "price": 100.0},
                "close": {"trade_time": "14:58:03", "price": 99.0},
            },
        })
        _write_jsonl(paths["evolution_path"], [legacy_late])
        notifications = []

        result = run_dline_closeout(
            trade_date="20260714",
            notifier=lambda title, body: notifications.append((title, body)),
            now="2026-07-15T05:00:00",
            **paths,
        )

    assert result["status"] == "done"
    assert result["evidence"]["complete_evolution_count"] == 1
    assert result["evidence"]["late_limited_evolution_count"] == 1
    assert result["evidence"]["gaps"] == []
    assert notifications == []


def test_closeout_reports_real_gaps_once_without_blocking_trigger_result():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        task = _task("600001")
        quiet = _task("600002")
        _write_jsonl(paths["tasks_path"], [task, quiet])
        _write_jsonl(paths["forecasts_path"], [_forecast(task)])
        _write_jsonl(paths["snapshots_path"], [
            {"trade_date": "20260714", "code": "600001", "price_at_snapshot": 102.0},
            {"trade_date": "20260714", "code": "600002", "price_at_snapshot": 52.0},
        ])
        _write_jsonl(paths["factor_results_path"], [])
        notifications = []
        notify = lambda title, body: notifications.append((title, body))

        first = run_dline_closeout(
            trade_date="20260714", notifier=notify,
            now="2026-07-15T05:00:00", **paths,
        )
        second = run_dline_closeout(
            trade_date="20260714", notifier=notify,
            now="2026-07-15T05:01:00", **paths,
        )

    codes = {row["code"] for row in first["evidence"]["gaps"]}
    assert first["status"] == second["status"] == "partial_data"
    assert codes == {"coverage_missing", "evolution_missing"}
    assert first["evidence"]["trigger_t0_result_count"] == 1
    assert first["errors"] == []
    assert len(notifications) == 1
    assert "D线异常" in notifications[0][0]


def test_failed_closeout_recovers_on_retry_and_sends_recovery_once():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = _paths(root)
        task = _task("600001")
        _seed_complete(paths, task)
        bad_results = root / "bad_results"
        bad_results.mkdir()
        notifications = []
        notify = lambda title, body: notifications.append((title, body))

        failed_paths = dict(paths)
        failed_paths["results_path"] = bad_results
        failed = run_dline_closeout(
            trade_date="20260714", notifier=notify,
            now="2026-07-15T05:00:00", **failed_paths,
        )
        recovered = run_dline_closeout(
            trade_date="20260714", notifier=notify,
            now="2026-07-15T05:02:00", **paths,
        )
        repeated = run_dline_closeout(
            trade_date="20260714", notifier=notify,
            now="2026-07-15T05:03:00", **paths,
        )

    assert failed["status"] == "failed"
    assert any(row["stage"] == "result_backfill" for row in failed["errors"])
    assert recovered["status"] == repeated["status"] == "done"
    assert recovered["errors"] == []
    assert len(notifications) == 2
    assert "D线异常" in notifications[0][0]
    assert "D线恢复" in notifications[1][0]

def test_notification_failure_is_retried_instead_of_silently_deduplicated():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        quiet = _task("600002")
        _write_jsonl(paths["tasks_path"], [quiet])
        _write_jsonl(paths["forecasts_path"], [])
        _write_jsonl(paths["snapshots_path"], [
            {"trade_date": "20260714", "code": "600002", "price_at_snapshot": 52.0},
        ])
        _write_jsonl(paths["factor_results_path"], [])
        calls = []

        def unavailable(title, body):
            calls.append((title, body))
            return {"email": False, "wechat": False}

        first = run_dline_closeout(
            trade_date="20260714", notifier=unavailable,
            now="2026-07-15T05:00:00", **paths,
        )
        second = run_dline_closeout(
            trade_date="20260714", notifier=unavailable,
            now="2026-07-15T05:01:00", **paths,
        )

    assert first["status"] == second["status"] == "partial_data"
    assert first["notification"]["status"] == "attempted_no_delivery"
    assert second["notification"]["status"] == "attempted_no_delivery"
    assert first["last_alert_signature"] is None
    assert second["last_alert_signature"] is None
    assert len(calls) == 2

def test_failed_recovery_notification_is_retried_until_delivered():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        quiet = _task("600002")
        _write_jsonl(paths["tasks_path"], [quiet])
        _write_jsonl(paths["forecasts_path"], [])
        _write_jsonl(paths["snapshots_path"], [
            {"trade_date": "20260714", "code": "600002", "price_at_snapshot": 52.0},
        ])
        _write_jsonl(paths["factor_results_path"], [])
        deliveries = iter([
            {"email": True},
            {"email": False, "wechat": False},
            {"email": True},
        ])
        calls = []

        def notify(title, body):
            calls.append((title, body))
            return next(deliveries)

        abnormal = run_dline_closeout(
            trade_date="20260714", notifier=notify,
            now="2026-07-15T05:00:00", **paths,
        )
        _write_jsonl(paths["coverage_path"], [_coverage(quiet)])
        first_recovery = run_dline_closeout(
            trade_date="20260714", notifier=notify,
            now="2026-07-15T05:01:00", **paths,
        )
        second_recovery = run_dline_closeout(
            trade_date="20260714", notifier=notify,
            now="2026-07-15T05:02:00", **paths,
        )

    assert abnormal["status"] == "partial_data"
    assert abnormal["last_alert_status"] == "partial_data"
    assert first_recovery["status"] == "done"
    assert first_recovery["notification"]["status"] == "attempted_no_delivery"
    assert first_recovery["last_alert_status"] == "partial_data"
    assert second_recovery["notification"]["status"] == "sent"
    assert second_recovery["last_alert_status"] == "recovered"
    assert len(calls) == 3
