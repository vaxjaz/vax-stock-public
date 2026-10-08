"""Daily EOD contract: bounded runtime inputs, macro-only delivery, no research."""
import ast
import json
from pathlib import Path

import pytest
from vaxstock import config
from vaxstock.services import eod


@pytest.fixture
def daily(monkeypatch, tmp_path):
    payload = {"market_overview": {"trade_date": "20260703"}, "stocks": [
        {"code": "002475"}, {"code": "600519"}], "macro": {"macro_regime": "中性"}}
    calls = []
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    monkeypatch.setattr(eod, "TushareSource", lambda token: object())
    monkeypatch.setattr(eod, "collect_payload", lambda source: (payload, []))
    monkeypatch.setattr(eod, "assess_eod_freshness", lambda p: {
        "forecast_eligible": True, "eligible_codes": ["002475"]})
    monkeypatch.setattr(eod, "compact_for_claude", lambda p: dict(p))
    monkeypatch.setattr(eod, "_next_trade_date", lambda s, baseline: "20260706")
    monkeypatch.setattr(eod, "predictions_from_payload", lambda p, t, **kw:
                        calls.append(("predict", [s["code"] for s in p["stocks"]])) or [])
    monkeypatch.setattr(eod, "enqueue_observation_job", lambda *a, **kw: calls.append(("job", kw)))
    monkeypatch.setattr(eod, "send_macro_email", lambda **kw: calls.append(("mail", kw)) or {"sent": True})
    return payload, calls, tmp_path


def test_eod_keeps_only_latest_inputs_and_live_task_context(daily):
    payload, calls, path = daily
    eod.run_eod()
    assert calls[0] == ("predict", ["002475"])
    assert calls[1][1]["current_only"] is True
    assert calls[1][1]["baseline_trade_date"] == "20260703"
    assert "600519" not in calls[2][1]["body"]
    payload["market_overview"]["trade_date"] = "20260706"
    eod.run_eod()
    assert json.loads((path / "eod/current_payload.json").read_text())["market_overview"]["trade_date"] == "20260706"
    assert sorted(p.name for p in path.rglob('*') if p.is_file()) == ["current_baseline.json", "current_payload.json"]


def test_eod_missing_date_never_writes_or_sends(daily):
    payload, calls, path = daily
    payload["market_overview"] = {}
    with pytest.raises(ValueError):
        eod.run_eod()
    assert calls == []
    assert not list(path.iterdir())


def test_eod_email_failure_does_not_block_planning(daily, monkeypatch):
    _, calls, _ = daily
    def fail(**kw):
        raise OSError("smtp unavailable")
    monkeypatch.setattr(eod, "send_macro_email", fail)
    assert eod.run_eod()["mail"]["status"] == "failed"
    assert calls[1][0] == "job"


def test_stale_global_data_clears_old_job(daily, monkeypatch):
    _, calls, path = daily
    from vaxstock.services import forecast_planner as fp
    monkeypatch.setattr(fp, "CURRENT_OBSERVATION_JOB_FILE", path / "job.json")
    monkeypatch.setattr(fp, "CURRENT_TASKS_FILE", path / "tasks.json")
    monkeypatch.setattr(eod, "assess_eod_freshness", lambda p: {"forecast_eligible": False})
    eod.run_eod()
    assert [c[0] for c in calls] == ["mail"]
    assert json.loads((path / "job.json").read_text()) == {}
    assert json.loads((path / "tasks.json").read_text())["tasks"] == []


def test_eod_has_no_cumulative_research_dependencies():
    tree = ast.parse(Path(eod.__file__).read_text())
    modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any("research" in m or any(x in m for x in (
        "eval_recorder", "prediction_evaluator", "evidence_", "dline_closeout", "report.store")) for m in modules)


def test_next_trade_date_uses_real_calendar():
    import pandas as pd
    class Source:
        def _safe_call(self, name, **kw):
            assert name == "trade_cal"
            assert kw['start_date'] == '20260704'
            return pd.DataFrame([{"cal_date": "20260705", "is_open": 0},
                                 {"cal_date": "20260706", "is_open": 1}])
    assert eod._next_trade_date(Source(), "20260703") == "20260706"
    assert eod._next_trade_date(object(), "20260703") is None
