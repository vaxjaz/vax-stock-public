# -*- coding: utf-8 -*-
"""services.eod 测试: 依赖守卫(ast) + 编排顺序/透传 + 邮件门控(全 monkeypatch, 零网络)。

跑法: /opt/stock-reportv2/venv/bin/python -m pytest tests/services/test_eod.py -q
     PYTHONPATH=src python3 tests/services/test_eod.py   # 无 pytest
"""

import ast
import copy
import pathlib
import sys
import types

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    sys.modules["requests"] = types.SimpleNamespace()

from vaxstock import config
from vaxstock.research import layer2_eval as l2_mod
from vaxstock.research import prediction_eval as pred_l2_mod
from vaxstock.research import factor_weight_review as factor_review_mod
from vaxstock.research import rule_suggester as rule_mod
from vaxstock.services import regime_auditor as regime_audit_mod
from vaxstock.services import eod as eod_mod

_REPO = pathlib.Path(__file__).resolve().parents[2]

# canned 数据(seam 替身的返回值)
_PAYLOAD = {
    "generated_at": "2026-06-25 16:00",
    "stocks": [{"code": "601138", "history_tail": [{"trade_date": "20260625"}]}],
    "indices": [{"symbol": "sh000001", "trade_date": "20260625"}],
    "market_regime": "panic",
    "market_overview": {"trade_date": "20260625"},
}
_TRACKS = [{"track_name": "AI算力", "date": "2026-06-25", "available": False,
            "signals": {}, "summary_lines": [], "vetoes": [],
            "position_ceiling": "待验证(数据缺失, 不出仓位结论)", "pending": ["stub"]}]
_CLAUDE = {"generated_at": "2026-06-25 16:00", "_compact": True}
_MD = "MARKDOWN_BODY"
_PATHS = {"payload": "/r/2026-06-25/payload.json",
          "claude_json": "/r/2026-06-25/claude.json",
          "claude_md": "/r/2026-06-25/claude.md"}

_SEAMS = ["TushareSource", "collect_payload", "compact_for_claude",
          "build_claude_markdown", "store_report",
          "record_and_backfill", "record_legacy_snapshot_trade_date",
          "run_curve_refresh", "run_group_refresh", "run_group_outcome_refresh",
          "run_dline_closeout", "run_evidence_ledger",
          "run_evidence_convergence", "evaluate_from_files", "predictions_from_payload",
          "record_predictions", "enqueue_observation_job",
          "_next_trade_date"]


def _install_spies(secrets=None, payload=None, next_trade_date="20260626"):
    """把 eod 内引用的所有 seam 换成记录型替身; 可选覆盖 config.SECRETS。返回 (rec, restore)。"""
    saved = {n: getattr(eod_mod, n) for n in _SEAMS}
    saved_secrets = config.SECRETS
    # run_layer2 是 run_eod 内的局部 import(from research.layer2_eval import run_layer2),
    # 在其源模块上打桩才拦得住; 否则真跑会读真 var/eval/ 并落 layer2_report 文件(测试不该有副作用)。
    saved_l2 = l2_mod.run_layer2
    saved_pred_l2 = pred_l2_mod.run_prediction_layer2
    saved_factor_review = factor_review_mod.run_factor_weight_review
    saved_pred_summary = pred_l2_mod.summarize_prediction_check
    saved_rule = rule_mod.run_rule_suggestions
    saved_regime_audit = regime_audit_mod.record_regime_audit
    rec = {"send_calls": [], "order": []}
    run_payload = payload if payload is not None else _PAYLOAD

    def _layer2(**k):
        rec["order"].append("layer2")
        rec["layer2_called"] = True
        return ""
    l2_mod.run_layer2 = _layer2

    def _prediction_layer2(**k):
        rec["order"].append("prediction_layer2")
        rec["prediction_layer2_called"] = True
        return ""
    pred_l2_mod.run_prediction_layer2 = _prediction_layer2

    def _factor_review(**k):
        rec["order"].append("factor_weight_review")
        rec["factor_weight_review_called"] = True
        return ""
    factor_review_mod.run_factor_weight_review = _factor_review

    def _regime_audit(payload, **k):
        rec["order"].append("regime_audit")
        rec["regime_audit_call"] = payload
        return {"written": 1, "skipped": 0}
    regime_audit_mod.record_regime_audit = _regime_audit

    def _rule_suggestions(**k):
        rec["order"].append("rule_suggestions")
        rec["rule_suggestions_called"] = True
        return ""
    rule_mod.run_rule_suggestions = _rule_suggestions

    def _prediction_summary(target_trade_date=None, **k):
        rec["order"].append("pred_summary")
        rec["summary_call"] = {"target_trade_date": target_trade_date}
        return {"available": True, "target_trade_date": target_trade_date,
                "predictions": 2, "evaluated": 1, "pending": 1,
                "avg_excess": 0.02, "positive_excess_rate": 1.0,
                "action_hit_rate": 1.0, "direction_hit_rate": 1.0,
                "generation_modes": {"live": {"predictions": 2, "evaluated": 1, "pending": 1}},
                "actions": []}
    pred_l2_mod.summarize_prediction_check = _prediction_summary

    eod_mod.TushareSource = lambda token: {"_stub": True, "token": token}

    def _collect(source):
        rec["collect_source"] = source
        return run_payload, _TRACKS
    eod_mod.collect_payload = _collect

    def _compact(payload):
        rec["compact_in"] = payload
        _CLAUDE.pop("prediction_summary", None)
        return _CLAUDE
    eod_mod.compact_for_claude = _compact

    def _build(claude_data, track_results=None):
        rec["build_in"] = {"claude_data": claude_data, "track_results": track_results}
        return _MD
    eod_mod.build_claude_markdown = _build


    def _store(payload, claude_data, markdown, report_dir=None):
        rec["order"].append("store")
        rec["store_in"] = {"payload": payload, "claude_data": claude_data, "markdown": markdown}
        return _PATHS
    eod_mod.store_report = _store


    def _eval(payload, source):
        rec["order"].append("e1")
        rec["eval_call"] = {"payload": payload, "source": source}
        return {"snapshots": 0, "backfilled": 0}
    eod_mod.record_and_backfill = _eval

    def _research_v2(trade_date, **kwargs):
        rec["order"].append("research_v2")
        rec["research_v2_call"] = {"trade_date": trade_date, **kwargs}
        return {
            "status": "written",
            "observations_written": 1,
            "factors_written": 1,
            "manifests_written": 1,
        }
    eod_mod.record_legacy_snapshot_trade_date = _research_v2

    def _curve_v2(*, as_of_trade_date, mode):
        rec["order"].append("curve_v2")
        rec["curve_v2_call"] = {
            "as_of_trade_date": as_of_trade_date,
            "mode": mode,
        }
        return {
            "status": "written",
            "summary": {"outputs": 1, "candidate_hits": 0},
        }
    eod_mod.run_curve_refresh = _curve_v2

    def _group_v2(*, as_of_trade_date, mode):
        rec["order"].append("group_v2")
        rec["group_v2_call"] = {
            "as_of_trade_date": as_of_trade_date,
            "mode": mode,
        }
        return {
            "status": "written",
            "summary": {
                "stock_group_vectors": 1,
                "statistical_memberships": 2,
                "label_usage": "none",
            },
        }
    eod_mod.run_group_refresh = _group_v2

    def _group_outcomes_v2():
        rec["order"].append("group_outcomes_v2")
        rec["group_outcomes_v2_called"] = True
        return {
            "status": "written",
            "stored": {"written": 1},
            "summary": {"samples_ready": 1},
        }
    eod_mod.run_group_outcome_refresh = _group_outcomes_v2

    def _dline_closeout(*, trade_date, **kwargs):
        rec["order"].append("d_closeout")
        rec["dline_closeout_call"] = {"trade_date": trade_date, **kwargs}
        return {
            "status": "done",
            "evidence": {"task_count": 0, "trigger_count": 0, "gaps": []},
            "errors": [],
        }
    eod_mod.run_dline_closeout = _dline_closeout

    def _pred_eval():
        rec["order"].append("pred_eval")
        rec["pred_eval_called"] = True
        return {"written": 0, "skipped": 0, "source_predictions": 0,
                "source_factor_results": 0, "generated": 0, "missing_or_pending": 0}
    eod_mod.evaluate_from_files = _pred_eval

    def _next(source, baseline):
        rec["order"].append("next_trade")
        rec["next_trade_call"] = {"source": source, "baseline": baseline}
        return next_trade_date
    eod_mod._next_trade_date = _next

    def _preds(payload, target_trade_date, generation_mode="live"):
        rec["order"].append("pred_live")
        rec["preds_call"] = {"payload": payload, "target_trade_date": target_trade_date,
                              "generation_mode": generation_mode}
        return [{"prediction_id": "p1"}]
    eod_mod.predictions_from_payload = _preds

    def _record(predictions):
        rec["order"].append("pred_record")
        rec["record_predictions_call"] = list(predictions)
        return {"written": 1, "skipped": 0}
    eod_mod.record_predictions = _record

    def _evidence(*, as_of_trade_date, **kwargs):
        rec["order"].append("evidence")
        rec["evidence_call"] = {"as_of_trade_date": as_of_trade_date, **kwargs}
        return {
            "build": {"ready": 1}, "ledger": {"written": 1, "skipped": 0},
            "hydrated": 1,
        }
    eod_mod.run_evidence_ledger = _evidence

    def _convergence(*, as_of_trade_date, payload, **kwargs):
        rec["order"].append("convergence")
        rec["convergence_call"] = {
            "as_of_trade_date": as_of_trade_date,
            "payload": payload,
            **kwargs,
        }
        return {
            "status": "ready", "facts": {"new_matured_c_results": 1},
            "special_findings": 0,
        }
    eod_mod.run_evidence_convergence = _convergence

    def _enqueue(payload_path, target_trade_date, c_predictions=None,
                 baseline_trade_date=None, task_codes=None, **kwargs):
        rec["order"].append("d_enqueue")
        rec["d_enqueue_call"] = {
            "payload_path": payload_path,
            "target_trade_date": target_trade_date,
            "c_predictions": list(c_predictions or []),
            "baseline_trade_date": baseline_trade_date,
            "task_codes": list(task_codes or []),
        }
        return {"queued": 1, "skipped": 0, "job_id": "j1"}
    eod_mod.enqueue_observation_job = _enqueue

    if secrets is not None:
        config.SECRETS = secrets

    def restore():
        _PAYLOAD.pop("freshness", None)
        for n, v in saved.items():
            setattr(eod_mod, n, v)
        config.SECRETS = saved_secrets
        l2_mod.run_layer2 = saved_l2
        pred_l2_mod.run_prediction_layer2 = saved_pred_l2
        factor_review_mod.run_factor_weight_review = saved_factor_review
        pred_l2_mod.summarize_prediction_check = saved_pred_summary
        rule_mod.run_rule_suggestions = saved_rule
        regime_audit_mod.record_regime_audit = saved_regime_audit

    return rec, restore


# ── a. 依赖守卫(ast 静态, 不用运行时 sys.modules)──
def test_eod_no_forbidden_imports():
    src = (_REPO / "src" / "vaxstock" / "services" / "eod.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    tokens = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            tokens.append(node.module or "")
            tokens.extend(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            tokens.extend(a.name for a in node.names)
    forbidden = ["eastmoney", "opportunity_scanner", "hot_sector_scanner", "macro_indicators"]
    offenders = [t for t in tokens if any(fb in t for fb in forbidden)]
    assert offenders == [], f"eod.py 不应 import 东财/未迁模块: {offenders}"


# ── b. 编排顺序 + 透传 ──
def test_eod_orchestration_and_passthrough():
    rec, restore = _install_spies(secrets={"email_enabled": False})  # 关邮件, 聚焦串联
    try:
        paths = eod_mod.run_eod()
        # build 收到的 track_results 即 collect 返回那个列表(透传, 同一对象)
        assert rec["build_in"]["track_results"] is _TRACKS
        # compact 收到 collect 的 payload
        assert rec["compact_in"] is _PAYLOAD
        # store 收到 (payload, claude_data, markdown) —— 落盘仍是完整 markdown(claude.md 附件不变)
        assert rec["store_in"]["payload"] is _PAYLOAD
        assert rec["store_in"]["claude_data"] is _CLAUDE
        assert rec["store_in"]["markdown"] == _MD
        assert "summary_call" not in rec
        assert "prediction_summary" not in rec["store_in"]["claude_data"]
        # EOD 只落盘并排队 D 线，不再构造或发送旧摘要邮件。
        assert "digest_in" not in rec
        assert rec["send_calls"] == []
        # build 收到的 claude_data 是 compact 的输出
        assert rec["build_in"]["claude_data"] is _CLAUDE
        # run_eod 返回 store_report 的 paths
        assert paths == _PATHS
        # collect 收到的 source 即 eod.TushareSource(token) 构造出的那个(stub)
        assert rec["collect_source"]["_stub"] is True
        # MR-Eval: record_and_backfill 收到 payload + 同一 source(快照地基接入)
        assert rec["eval_call"]["payload"] is _PAYLOAD
        assert rec["eval_call"]["source"]["_stub"] is True
        assert rec["research_v2_call"] == {
            "trade_date": "20260625",
            "mode": "live",
            "snapshots_path": eod_mod.SNAPSHOTS_FILE,
        }
        assert rec["curve_v2_call"] == {
            "as_of_trade_date": "20260625",
            "mode": "live",
        }
        assert rec["group_v2_call"] == {
            "as_of_trade_date": "20260625",
            "mode": "live",
        }
        assert rec["group_outcomes_v2_called"] is True
        assert rec["regime_audit_call"] is _PAYLOAD
        assert rec["dline_closeout_call"] == {"trade_date": "20260625"}
        # E4: E1 后先核验旧 predictions,再生成下一交易日 live predictions
        assert rec["next_trade_call"] == {"source": rec["collect_source"], "baseline": "20260625"}
        assert rec["preds_call"] == {"payload": _PAYLOAD, "target_trade_date": "20260626",
                                      "generation_mode": "live"}
        assert rec["record_predictions_call"] == [{"prediction_id": "p1"}]
        assert rec["evidence_call"] == {"as_of_trade_date": "20260625"}
        assert rec["convergence_call"] == {
            "as_of_trade_date": "20260625",
            "payload": _PAYLOAD,
        }
        assert rec["d_enqueue_call"] == {"payload_path": _PATHS["payload"],
                                         "target_trade_date": "20260626",
                                         "c_predictions": [{"prediction_id": "p1"}],
                                         "baseline_trade_date": "20260625",
                                         "task_codes": ["601138"]}
        assert rec["order"] == [
            "regime_audit", "e1", "research_v2", "curve_v2", "group_v2",
            "group_outcomes_v2",
            "d_closeout", "pred_eval", "next_trade",
            "pred_live", "pred_record", "evidence", "convergence", "store",
            "d_enqueue",
        ]
        assert rec.get("layer2_called") is None
        assert rec.get("factor_weight_review_called") is None
        assert rec.get("prediction_layer2_called") is None
        assert rec.get("rule_suggestions_called") is None
    finally:
        restore()


def test_research_v2_failure_is_visible_but_does_not_block_eod():
    rec, restore = _install_spies(secrets={"email_enabled": False})
    try:
        def _fail(*args, **kwargs):
            rec["order"].append("research_v2_failed")
            raise RuntimeError("store conflict")

        eod_mod.record_legacy_snapshot_trade_date = _fail
        assert eod_mod.run_eod() == _PATHS
        assert "research_v2_failed" in rec["order"]
        assert "d_closeout" in rec["order"]
        assert "store" in rec["order"]
    finally:
        restore()


def test_legacy_research_can_be_explicitly_enabled_for_audit():
    rec, restore = _install_spies(secrets={
        "email_enabled": False,
        "legacy_prediction_report_enabled": True,
        "legacy_daily_research_enabled": True,
    })
    try:
        assert eod_mod.run_eod() == _PATHS
        assert rec["summary_call"] == {"target_trade_date": "20260625"}
        assert rec["store_in"]["claude_data"]["prediction_summary"]["predictions"] == 2
        assert rec["order"][-5:] == [
            "d_enqueue", "layer2", "factor_weight_review",
            "prediction_layer2", "rule_suggestions",
        ]
    finally:
        restore()


# ── c. EOD Prediction 接入边界 ──
def test_eod_prediction_skips_live_without_trade_date():
    payload = {"generated_at": "2026-06-25 16:00", "stocks": [], "market_regime": "panic"}
    rec, restore = _install_spies(secrets={"email_enabled": False}, payload=payload)
    try:
        assert eod_mod.run_eod() == _PATHS
        assert "pred_eval" in rec["order"]
        assert "next_trade" not in rec["order"]
        assert "pred_live" not in rec["order"]
        assert "pred_record" not in rec["order"]
        assert "d_enqueue" not in rec["order"]
    finally:
        restore()


def test_eod_prediction_skips_live_without_next_trade_date():
    rec, restore = _install_spies(secrets={"email_enabled": False}, next_trade_date=None)
    try:
        assert eod_mod.run_eod() == _PATHS
        assert "pred_eval" in rec["order"]
        assert "next_trade" in rec["order"]
        assert "pred_live" not in rec["order"]
        assert "pred_record" not in rec["order"]
        assert "d_enqueue" not in rec["order"]
    finally:
        restore()


def test_eod_freshness_filters_stale_target_without_blocking_ready_target():
    payload = copy.deepcopy(_PAYLOAD)
    payload["stocks"].append({
        "code": "002475",
        "history_tail": [{"trade_date": "20260624"}],
    })
    rec, restore = _install_spies(
        secrets={"email_enabled": False},
        payload=payload,
    )
    try:
        assert eod_mod.run_eod() == _PATHS
        assert payload["freshness"]["status"] == "degraded"
        assert payload["freshness"]["eligible_codes"] == ["601138"]
        predicted_codes = [
            row["code"] for row in rec["preds_call"]["payload"]["stocks"]
        ]
        assert predicted_codes == ["601138"]
        assert [row["code"] for row in payload["stocks"]] == ["601138", "002475"]
    finally:
        restore()


def test_next_trade_date_uses_trade_cal_and_skips_closed_days():
    calls = []

    class _Cal:
        columns = ["cal_date", "is_open"]

        def __init__(self, rows):
            self.rows = rows

        def sort_values(self, *a, **k):
            self.rows = sorted(self.rows, key=lambda r: r["cal_date"])
            return self

        def to_dict(self, kind):
            assert kind == "records"
            return self.rows

    class _Source:
        def _safe_call(self, name, **kwargs):
            calls.append((name, kwargs))
            return _Cal([
                {"cal_date": "20260704", "is_open": 0},
                {"cal_date": "20260705", "is_open": 0},
                {"cal_date": "20260706", "is_open": 1},
            ])

    assert eod_mod._next_trade_date(_Source(), "20260703") == "20260706"
    assert calls == [("trade_cal", {"exchange": "", "start_date": "20260704", "end_date": "20260718"})]


# ── d. 邮件门控 ──
def test_email_gate_disabled():
    rec, restore = _install_spies(secrets={"email_enabled": False, "email_user": "u@qq.com",
                                           "email_authcode": "pw", "email_to": "t@163.com"})
    try:
        eod_mod.run_eod()
        assert rec["send_calls"] == [], "email_enabled=False 不应发送"
    finally:
        restore()


def test_email_gate_missing_creds():
    # enabled 但缺 authcode -> 不发
    rec, restore = _install_spies(secrets={"email_enabled": True, "email_user": "u@qq.com",
                                           "email_authcode": None, "email_to": "t@163.com"})
    try:
        eod_mod.run_eod()
        assert rec["send_calls"] == [], "缺凭据不应发送"
    finally:
        restore()


def test_eod_never_sends_legacy_email_even_with_complete_credentials():
    rec, restore = _install_spies(secrets={"email_enabled": True, "email_user": "u@qq.com",
                                           "email_authcode": "pw", "email_to": "t@163.com",
                                           "email_cc": "x@a.com,y@b.com"})
    try:
        eod_mod.run_eod()
        assert rec["send_calls"] == [], "EOD 邮件必须等待 D-line worker 统一发送"
        assert "digest_in" not in rec
    finally:
        restore()

if __name__ == "__main__":
    import sys
    fns = sorted((n, f) for n, f in globals().items()
                 if n.startswith("test_") and callable(f))
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  [PASS] {name}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
