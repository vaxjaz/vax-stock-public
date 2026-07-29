# -*- coding: utf-8 -*-

import json

from vaxstock.services.research_eod_mail import send_research_eod_email


def _artifacts(tmp_path, target="20260728"):
    report = tmp_path / "claude.md"
    payload = tmp_path / "payload.json"
    report.write_text(
        f"# 新研究 EOD {target}\n\n- **ABSTAIN**\n",
        encoding="utf-8",
    )
    payload.write_text('{"ok": true}\n', encoding="utf-8")
    return {
        "claude_md": str(report),
        "payload": str(payload),
    }, report.read_text(encoding="utf-8")


def _smtp():
    return {
        "smtp_server": "smtp.example.com",
        "smtp_port": 465,
        "sender_email": "sender@example.com",
        "sender_password": "secret",
        "receiver_email": "receiver@example.com",
    }


def test_research_eod_mail_is_idempotent_per_trade_date(tmp_path):
    paths, markdown = _artifacts(tmp_path)
    state_path = tmp_path / "mail_state.json"
    calls = []

    def _send(**kwargs):
        calls.append(kwargs)
        return True

    first = send_research_eod_email(
        trade_date="20260728",
        markdown=markdown,
        report_paths=paths,
        state_path=state_path,
        smtp_conf=_smtp(),
        send_func=_send,
    )
    second = send_research_eod_email(
        trade_date="20260728",
        markdown=markdown,
        report_paths=paths,
        state_path=state_path,
        smtp_conf=_smtp(),
        send_func=_send,
    )

    assert first["status"] == "sent"
    assert first["sent"] is True
    assert second["status"] == "already_sent"
    assert second["sent"] is False
    assert len(calls) == 1
    assert calls[0]["subject"] == "[新研究EOD] 20260728"
    assert calls[0]["body"] == markdown
    assert [row[0] for row in calls[0]["attachments"]] == [
        "research_eod_20260728.md",
        "payload_20260728.json",
    ]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["sent_targets"]["20260728"]["content_digest"]


def test_failed_delivery_is_retryable_and_not_marked_sent(tmp_path):
    paths, markdown = _artifacts(tmp_path)
    state_path = tmp_path / "mail_state.json"
    attempts = []

    failed = send_research_eod_email(
        trade_date="20260728",
        markdown=markdown,
        report_paths=paths,
        state_path=state_path,
        smtp_conf=_smtp(),
        send_func=lambda **kwargs: attempts.append("failed") or False,
    )
    assert failed["status"] == "failed"
    assert not state_path.exists()

    retried = send_research_eod_email(
        trade_date="20260728",
        markdown=markdown,
        report_paths=paths,
        state_path=state_path,
        smtp_conf=_smtp(),
        send_func=lambda **kwargs: attempts.append("sent") or True,
    )

    assert retried["status"] == "sent"
    assert attempts == ["failed", "sent"]


def test_disabled_or_invalid_delivery_never_writes_state(tmp_path):
    paths, markdown = _artifacts(tmp_path)
    state_path = tmp_path / "mail_state.json"

    disabled = send_research_eod_email(
        trade_date="20260728",
        markdown=markdown,
        report_paths=paths,
        state_path=state_path,
        smtp_conf={},
    )
    invalid = send_research_eod_email(
        trade_date="2026-07",
        markdown=markdown,
        report_paths=paths,
        state_path=state_path,
        smtp_conf=_smtp(),
        send_func=lambda **kwargs: True,
    )

    assert disabled["status"] == "disabled"
    assert invalid["status"] == "blocked"
    assert not state_path.exists()


def test_missing_artifact_blocks_before_smtp(tmp_path):
    _, markdown = _artifacts(tmp_path)
    calls = []
    result = send_research_eod_email(
        trade_date="20260728",
        markdown=markdown,
        report_paths={
            "claude_md": str(tmp_path / "missing.md"),
            "payload": str(tmp_path / "missing.json"),
        },
        state_path=tmp_path / "mail_state.json",
        smtp_conf=_smtp(),
        send_func=lambda **kwargs: calls.append(kwargs) or True,
    )

    assert result["status"] == "blocked"
    assert result["reason"].startswith("report_artifact_missing:")
    assert calls == []
