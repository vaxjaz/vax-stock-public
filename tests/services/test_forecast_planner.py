# -*- coding: utf-8 -*-
"""D线 observation planner 测试: A/B/C evidence pack + LLM schema 校验 + append-only 落盘。"""

import json
import pathlib
import shutil
import tempfile

from vaxstock.services import forecast_planner as fp
from vaxstock.sources.codex import CodexCallError


def _payload():
    return {
        "market_overview": {
            "trade_date": "20260703",
            "up_count": 1800,
            "down_count": 3000,
            "limit_up_count": 35,
            "limit_down_count": 12,
        },
        "market_regime": "value",
        "macro": {"macro_regime": "中性偏弱"},
        "tracks": [{"track_name": "AI算力", "available": True, "position_ceiling": "防守档"}],
        "stocks": [
            {
                "group": "holding",
                "code": "002475",
                "configured_name": "立讯精密",
                "concepts": ["消费电子", "AI硬件"],
                "realtime": {"name": "立讯精密", "price": 60.9},
                "metrics": {
                    "right_side_score": 3.0,
                    "right_side_grade": "可考虑介入",
                    "position_20d_pct": 1.5,
                    "main_inflow_10d_yuan": -2275209400,
                    "price_vs_ma20_pct": -10.6,
                    "volume_ratio_5d": 0.9,
                    "rsi_14": 45.5,
                },
            }
        ],
    }


def _c_prediction():
    return {
        "prediction_id": "20260703_20260706_002475_zz800_seed_v1_live",
        "baseline_trade_date": "20260703",
        "target_trade_date": "20260706",
        "code": "002475",
        "prediction": {
            "action": "watch",
            "direction": "up",
            "confidence": 0.6,
            "reason": "评分≥2,需盘中确认",
        },
    }


def _factor_results():
    return [
        {
            "trade_date": "20260701",
            "code": "002475",
            "ret": {"1": -0.02},
            "mkt_ret": {"1": -0.005},
            "excess": {"1": -0.015},
            "complete": False,
        }
    ]


def _plan():
    return {
        "observe_intent": "验证 C线 watch 是否被盘中破位证伪",
        "primary_risk": "低位继续破位会削弱 C线 watch",
        "watch_points": [
            {"name": "破位证伪", "why": "低位继续跌破中期均线", "signals": ["price_vs_ma20_pct"]},
        ],
        "trigger_blueprints": [
            {
                "trigger_type": "breakdown_confirm",
                "severity": "high",
                "condition": {
                    "all": [
                        {"field": "price_vs_ma20_pct", "op": "<", "value": -2.0},
                        {"field": "position_20d_pct", "op": "<", "value": 20},
                    ],
                    "any": [
                        {"field": "volume_ratio_5d", "op": ">", "value": 1.2},
                        {"field": "amplitude_pct", "op": ">", "value": 5},
                    ],
                },
                "why": "触发后说明 C线 watch 需要复核",
                "expected_feedback_to_c": "watch -> avoid_review",
            }
        ],
        "c_line_feedback_focus": "watch/action/confidence",
        "falsify_if": "若快速收回 MA20 且量能改善,本观察失效",
    }


def _rows(path):
    return [json.loads(line) for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _payload_with_watchlist():
    payload = _payload()
    payload["stocks"] = list(payload["stocks"]) + [
        {
            "group": "watchlist",
            "code": "002371",
            "configured_name": "WatchA",
            "concepts": ["semi", "ai"],
            "realtime": {"name": "WatchA", "price": 500.0},
            "metrics": {"right_side_score": 2.5, "price_vs_ma20_pct": 3.2},
        },
        {
            "group": "watchlist",
            "code": "600522",
            "configured_name": "WatchB",
            "concepts": ["ai", "optical"],
            "realtime": {"name": "WatchB", "price": 18.0},
            "metrics": {"right_side_score": 1.0},
        },
    ]
    return payload


def test_select_observation_task_codes_merges_holdings_and_task_pool():
    codes = fp.select_observation_task_codes(
        _payload_with_watchlist(),
        task_pool={
            "002371": {"active": True},
            "600522": {"active": False},
        },
    )
    assert codes == ["002475", "002371"]


def test_generate_observation_tasks_filters_to_task_codes():
    tasks = fp.generate_observation_tasks(
        _payload_with_watchlist(),
        "20260706",
        c_predictions=[_c_prediction()],
        factor_results=_factor_results(),
        task_codes=["002371"],
        planner_func=lambda evidence: _plan(),
        generated_at="2026-07-04T05:00:00",
    )
    assert len(tasks) == 1
    assert tasks[0]["code"] == "002371"


def test_enqueue_and_run_observation_job_consumes_current_job():
    d = tempfile.mkdtemp(prefix="vax_dline_job_")
    try:
        payload_path = pathlib.Path(d) / "payload.json"
        jobs = pathlib.Path(d) / "observation_jobs.jsonl"
        current_job = pathlib.Path(d) / "current_job.json"
        task_hist = pathlib.Path(d) / "observation_tasks.jsonl"
        current_tasks = pathlib.Path(d) / "current_tasks.json"
        payload_path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")

        queued = fp.enqueue_observation_job(
            payload_path,
            "20260706",
            c_predictions=[_c_prediction()],
            baseline_trade_date="20260703",
            job_path=jobs,
            current_job_path=current_job,
        )
        assert queued["queued"] == 1
        queued2 = fp.enqueue_observation_job(
            payload_path,
            "20260706",
            c_predictions=[_c_prediction()],
            baseline_trade_date="20260703",
            job_path=jobs,
            current_job_path=current_job,
        )
        assert queued2["skipped"] == 1

        stats = fp.run_observation_job(
            planner_func=lambda evidence: _plan(),
            current_job_path=current_job,
            history_path=task_hist,
            current_tasks_path=current_tasks,
        )
        assert stats["status"] == "done"
        assert stats["generated"] == 1
        assert stats["written"] == 1
        cur = json.loads(current_job.read_text(encoding="utf-8"))
        assert cur["status"] == "done"
        assert cur["task_codes"] == ["002475"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_run_observation_job_partial_failed_preserves_success_and_remaining():
    d = tempfile.mkdtemp(prefix="vax_dline_partial_")
    saved_task_pool = fp.config.load_task_pool
    try:
        fp.config.load_task_pool = lambda: {"002371": {"active": True}}
        payload_path = pathlib.Path(d) / "payload.json"
        jobs = pathlib.Path(d) / "observation_jobs.jsonl"
        current_job = pathlib.Path(d) / "current_job.json"
        task_hist = pathlib.Path(d) / "observation_tasks.jsonl"
        current_tasks = pathlib.Path(d) / "current_tasks.json"
        payload_path.write_text(json.dumps(_payload_with_watchlist(), ensure_ascii=False), encoding="utf-8")

        fp.enqueue_observation_job(
            payload_path,
            "20260706",
            c_predictions=[_c_prediction()],
            baseline_trade_date="20260703",
            job_path=jobs,
            current_job_path=current_job,
        )

        def _planner(evidence):
            code = evidence["stock"]["code"]
            if code == "002475":
                return _plan()
            raise CodexCallError(
                "auth_unavailable: no auth available",
                status_code=503,
                code="internal_server_error",
                error_type="provider_unavailable",
                retryable=True,
            )

        stats = fp.run_observation_job(
            planner_func=_planner,
            current_job_path=current_job,
            history_path=task_hist,
            current_tasks_path=current_tasks,
        )
        assert stats["status"] == "partial_failed"
        assert stats["generated"] == 1
        assert stats["written"] == 1
        assert stats["remaining"] == 1
        assert [r["code"] for r in _rows(task_hist)] == ["002475"]
        cur = json.loads(current_job.read_text(encoding="utf-8"))
        assert cur["status"] == "partial_failed"
        assert cur["done_codes"] == ["002475"]
        assert cur["remaining_codes"] == ["002371"]
        assert cur["error"]["failed_code"] == "002371"
        assert cur["error"]["type"] == "provider_unavailable"
        current = json.loads(current_tasks.read_text(encoding="utf-8"))
        assert [t["code"] for t in current["tasks"]] == ["002475"]
    finally:
        fp.config.load_task_pool = saved_task_pool
        shutil.rmtree(d, ignore_errors=True)


def test_run_observation_job_resumes_remaining_codes():
    d = tempfile.mkdtemp(prefix="vax_dline_resume_")
    saved_task_pool = fp.config.load_task_pool
    try:
        fp.config.load_task_pool = lambda: {"002371": {"active": True}}
        payload = _payload_with_watchlist()
        payload_path = pathlib.Path(d) / "payload.json"
        jobs = pathlib.Path(d) / "observation_jobs.jsonl"
        current_job = pathlib.Path(d) / "current_job.json"
        task_hist = pathlib.Path(d) / "observation_tasks.jsonl"
        current_tasks = pathlib.Path(d) / "current_tasks.json"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        existing_task = fp.generate_observation_tasks(
            payload,
            "20260706",
            c_predictions=[_c_prediction()],
            factor_results=[] ,
            task_codes=["002475"],
            planner_func=lambda evidence: _plan(),
            generated_at="2026-07-04T05:00:00",
        )[0]
        fp.record_observation_tasks([existing_task], history_path=task_hist, current_path=current_tasks)

        fp.enqueue_observation_job(
            payload_path,
            "20260706",
            c_predictions=[_c_prediction()],
            baseline_trade_date="20260703",
            job_path=jobs,
            current_job_path=current_job,
        )
        stats = fp.run_observation_job(
            planner_func=lambda evidence: _plan(),
            current_job_path=current_job,
            history_path=task_hist,
            current_tasks_path=current_tasks,
        )
        assert stats["status"] == "done"
        assert stats["generated"] == 1
        assert stats["written"] == 1
        assert stats["remaining"] == 0
        assert [r["code"] for r in _rows(task_hist)] == ["002475", "002371"]
        cur = json.loads(current_job.read_text(encoding="utf-8"))
        assert cur["status"] == "done"
        assert cur["done_codes"] == ["002475", "002371"]
        assert cur["remaining_codes"] == []
        current = json.loads(current_tasks.read_text(encoding="utf-8"))
        assert sorted(t["code"] for t in current["tasks"]) == ["002371", "002475"]
    finally:
        fp.config.load_task_pool = saved_task_pool
        shutil.rmtree(d, ignore_errors=True)
def test_codex_plan_runtime_config_uses_dline_overrides():
    runtime = fp._codex_plan_runtime_config({
        "codex_url": "http://127.0.0.1:8317/v1/chat/completions",
        "codex_model": "gpt-5.5",
        "codex_timeout": 30,
        "codex_dline_model": "gpt-5.4-mini",
        "codex_dline_timeout": 90,
        "codex_token": "token",
    })
    assert runtime["model"] == "gpt-5.4-mini"
    assert runtime["timeout"] == 90


def test_codex_plan_runtime_config_falls_back_to_shared_config():
    runtime = fp._codex_plan_runtime_config({
        "codex_url": "http://127.0.0.1:8317/v1/chat/completions",
        "codex_model": "gpt-5.5",
        "codex_timeout": 30,
        "codex_token": "token",
    })
    assert runtime["model"] == "gpt-5.5"
    assert runtime["timeout"] == 30


def test_build_observation_evidence_includes_abc_contract():
    evs = fp.build_observation_evidence(
        _payload(),
        "20260706",
        c_predictions=[_c_prediction()],
        factor_results=_factor_results(),
        generated_at="2026-07-04T05:00:00",
    )
    assert len(evs) == 1
    ev = evs[0]
    assert ev["line"] == "D"
    assert ev["baseline_trade_date"] == "20260703"
    assert ev["target_trade_date"] == "20260706"
    assert ev["stock"]["code"] == "002475"
    assert ev["A_eod"]["metrics"]["right_side_score"] == 3.0
    assert ev["A_eod"]["market"]["market_regime"] == "value"
    assert ev["B_factor_history"][0]["excess"]["1"] == -0.015
    assert ev["C_prediction"]["prediction"]["action"] == "watch"
    assert "price_vs_ma20_pct" in ev["D_contract"]["allowed_trigger_fields"]
    assert ev["D_contract"]["notification_role"] == "objective_evaluation_for_user_decision"


def test_generate_observation_tasks_validates_llm_plan():
    tasks = fp.generate_observation_tasks(
        _payload(),
        "20260706",
        c_predictions=[_c_prediction()],
        factor_results=_factor_results(),
        planner_func=lambda evidence: _plan(),
        generated_at="2026-07-04T05:00:00",
    )
    assert len(tasks) == 1
    task = tasks[0]
    assert task["task_id"] == "20260703_20260706_002475_d_observe_llm_v1"
    assert task["line"] == "D"
    assert task["source"] == "codex_llm"
    assert task["observation"]["observe_intent"].startswith("验证 C线")
    trigger = task["observation"]["trigger_blueprints"][0]
    assert trigger["trigger_type"] == "breakdown_confirm"
    assert trigger["condition"]["all"][0] == {"field": "price_vs_ma20_pct", "op": "<", "value": -2.0}
    assert task["evidence_pack"]["C_prediction"]["prediction"]["confidence"] == 0.6


def test_generate_observation_tasks_skips_invalid_trigger_field():
    bad = _plan()
    bad["trigger_blueprints"][0]["condition"] = {
        "all": [{"field": "made_up_intraday_money", "op": ">", "value": 1}],
        "any": [{"field": "another_fake_field", "op": "<", "value": 0}],
    }
    tasks = fp.generate_observation_tasks(
        _payload(),
        "20260706",
        c_predictions=[_c_prediction()],
        factor_results=[],
        planner_func=lambda evidence: bad,
    )
    assert tasks == []


def test_record_observation_tasks_idempotent_and_current_snapshot():
    d = tempfile.mkdtemp(prefix="vax_dline_")
    try:
        hist = pathlib.Path(d) / "observation_tasks.jsonl"
        current = pathlib.Path(d) / "current_tasks.json"
        task = fp.generate_observation_tasks(
            _payload(),
            "20260706",
            c_predictions=[_c_prediction()],
            factor_results=[],
            planner_func=lambda evidence: _plan(),
            generated_at="2026-07-04T05:00:00",
        )[0]

        stats = fp.record_observation_tasks([task], history_path=hist, current_path=current)
        assert stats == {"written": 1, "skipped": 0, "current": 1}
        assert len(_rows(hist)) == 1
        cur = json.loads(current.read_text(encoding="utf-8"))
        assert cur["target_trade_dates"] == ["20260706"]
        assert cur["tasks"][0]["task_id"] == task["task_id"]

        stats2 = fp.record_observation_tasks([task], history_path=hist, current_path=current)
        assert stats2 == {"written": 0, "skipped": 1, "current": 1}
        assert len(_rows(hist)) == 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    import sys
    fns = sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f))
    failed = 0
    for name, fn in fns:
        try:
            fn(); print(f"  [PASS] {name}")
        except AssertionError as e:
            failed += 1; print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            failed += 1; print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
