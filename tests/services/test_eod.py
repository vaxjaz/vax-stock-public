# -*- coding: utf-8 -*-
"""services.eod 测试: 依赖守卫(ast) + 编排顺序/透传 + 邮件门控(全 monkeypatch, 零网络)。

跑法: /opt/stock-reportv2/venv/bin/python -m pytest tests/services/test_eod.py -q
     PYTHONPATH=src python3 tests/services/test_eod.py   # 无 pytest
"""

import ast
import pathlib

from vaxstock import config
from vaxstock.research import layer2_eval as l2_mod
from vaxstock.services import eod as eod_mod

_REPO = pathlib.Path(__file__).resolve().parents[2]

# canned 数据(seam 替身的返回值)
_PAYLOAD = {"generated_at": "2026-06-25 16:00", "stocks": [], "market_regime": "panic"}
_TRACKS = [{"track_name": "AI算力", "date": "2026-06-25", "available": False,
            "signals": {}, "summary_lines": [], "vetoes": [],
            "position_ceiling": "待验证(数据缺失, 不出仓位结论)", "pending": ["stub"]}]
_CLAUDE = {"generated_at": "2026-06-25 16:00", "_compact": True}
_MD = "MARKDOWN_BODY"
_DIGEST = "DIGEST_BODY"
_PATHS = {"payload": "/r/2026-06-25/payload.json",
          "claude_json": "/r/2026-06-25/claude.json",
          "claude_md": "/r/2026-06-25/claude.md"}

_SEAMS = ["TushareSource", "collect_payload", "compact_for_claude",
          "build_claude_markdown", "build_email_digest", "store_report", "send_email",
          "record_and_backfill"]


def _install_spies(secrets=None):
    """把 eod 内引用的所有 seam 换成记录型替身; 可选覆盖 config.SECRETS。返回 (rec, restore)。"""
    saved = {n: getattr(eod_mod, n) for n in _SEAMS}
    saved_secrets = config.SECRETS
    # run_layer2 是 run_eod 内的局部 import(from research.layer2_eval import run_layer2),
    # 在其源模块上打桩才拦得住; 否则真跑会读真 var/eval/ 并落 layer2_report 文件(测试不该有副作用)。
    saved_l2 = l2_mod.run_layer2
    rec = {"send_calls": []}

    l2_mod.run_layer2 = lambda **k: rec.__setitem__("layer2_called", True) or ""

    eod_mod.TushareSource = lambda token: {"_stub": True, "token": token}

    def _collect(source):
        rec["collect_source"] = source
        return _PAYLOAD, _TRACKS
    eod_mod.collect_payload = _collect

    def _compact(payload):
        rec["compact_in"] = payload
        return _CLAUDE
    eod_mod.compact_for_claude = _compact

    def _build(claude_data, track_results=None):
        rec["build_in"] = {"claude_data": claude_data, "track_results": track_results}
        return _MD
    eod_mod.build_claude_markdown = _build

    def _digest(claude_data, track_results=None):
        rec["digest_in"] = {"claude_data": claude_data, "track_results": track_results}
        return _DIGEST
    eod_mod.build_email_digest = _digest

    def _store(payload, claude_data, markdown, report_dir=None):
        rec["store_in"] = {"payload": payload, "claude_data": claude_data, "markdown": markdown}
        return _PATHS
    eod_mod.store_report = _store

    def _send(body, attachments, smtp_conf, subject=None, is_html=False):
        rec["send_calls"].append({"body": body, "attachments": attachments,
                                  "smtp_conf": smtp_conf, "is_html": is_html})
        return True
    eod_mod.send_email = _send

    def _eval(payload, source):
        rec["eval_call"] = {"payload": payload, "source": source}
        return {"snapshots": 0, "backfilled": 0}
    eod_mod.record_and_backfill = _eval

    if secrets is not None:
        config.SECRETS = secrets

    def restore():
        for n, v in saved.items():
            setattr(eod_mod, n, v)
        config.SECRETS = saved_secrets
        l2_mod.run_layer2 = saved_l2

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
        # digest 收到 compact 的 claude_data + collect 的 tracks(邮件正文走 digest, 非完整 markdown)
        assert rec["digest_in"]["claude_data"] is _CLAUDE
        assert rec["digest_in"]["track_results"] is _TRACKS
        # build 收到的 claude_data 是 compact 的输出
        assert rec["build_in"]["claude_data"] is _CLAUDE
        # run_eod 返回 store_report 的 paths
        assert paths == _PATHS
        # collect 收到的 source 即 eod.TushareSource(token) 构造出的那个(stub)
        assert rec["collect_source"]["_stub"] is True
        # MR-Eval: record_and_backfill 收到 payload + 同一 source(快照地基接入)
        assert rec["eval_call"]["payload"] is _PAYLOAD
        assert rec["eval_call"]["source"]["_stub"] is True
        # Layer2(E2): record_and_backfill 之后被调(顺带分析)
        assert rec.get("layer2_called") is True
    finally:
        restore()


# ── c. 邮件门控 ──
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


def test_email_gate_enabled_smtp_conf_mapping():
    rec, restore = _install_spies(secrets={"email_enabled": True, "email_user": "u@qq.com",
                                           "email_authcode": "pw", "email_to": "t@163.com"})
    try:
        eod_mod.run_eod()
        assert len(rec["send_calls"]) == 1
        conf = rec["send_calls"][0]["smtp_conf"]
        assert conf["sender_email"] == "u@qq.com"
        assert conf["sender_password"] == "pw"
        assert conf["receiver_email"] == "t@163.com"
        assert conf["smtp_server"] == "smtp.qq.com"   # 缺省固定 QQ
        assert conf["smtp_port"] == 465
        assert conf["bcc_email"] is None              # 本次不启用 BCC
        assert rec["send_calls"][0]["is_html"] is False  # v2 纯文本
        assert rec["send_calls"][0]["body"] == _DIGEST   # 邮件正文 = 精简摘要 digest(非完整 markdown)
    finally:
        restore()


def test_email_cc_passthrough_unsplit():
    rec, restore = _install_spies(secrets={"email_enabled": True, "email_user": "u@qq.com",
                                           "email_authcode": "pw", "email_to": "t@163.com",
                                           "email_cc": "x@a.com,y@b.com"})
    try:
        eod_mod.run_eod()
        conf = rec["send_calls"][0]["smtp_conf"]
        # 整串透传, 本层不拆(拆分交给 mailer._normalize_emails)
        assert conf["cc_email"] == "x@a.com,y@b.com"
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
