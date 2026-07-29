# -*- coding: utf-8 -*-
"""Idempotent delivery for the human-facing Research v2 EOD report."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from vaxstock import config
from vaxstock.report.mailer import send_email


MAIL_STATE_FILE = (
    config.STATE_DIR / "strategy" / "research_eod_mail_state.json"
)


def _trade_date(value: Any) -> str:
    text = str(value or "").strip().replace("-", "")
    return text if len(text) == 8 and text.isdigit() else ""


def _read_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _write_state(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _smtp_conf() -> Dict[str, Any]:
    secrets = config.SECRETS
    if not (
        secrets.get("email_enabled")
        and secrets.get("email_user")
        and secrets.get("email_authcode")
        and secrets.get("email_to")
    ):
        return {}
    return {
        "smtp_server": secrets.get("smtp_server", "smtp.qq.com"),
        "smtp_port": secrets.get("smtp_port", 465),
        "sender_email": secrets["email_user"],
        "sender_password": secrets["email_authcode"],
        "receiver_email": secrets["email_to"],
        "cc_email": secrets.get("email_cc"),
        "bcc_email": None,
    }


def send_research_eod_email(
    *,
    trade_date: Any,
    markdown: str,
    report_paths: Mapping[str, Any],
    state_path: Optional[Path] = None,
    smtp_conf: Optional[Mapping[str, Any]] = None,
    send_func: Optional[Callable[..., bool]] = None,
) -> Dict[str, Any]:
    """Send one new-format EOD email per exact market trade date.

    Failed or disabled deliveries never create a sent marker, so a later EOD
    retry can deliver the report.  A successful target is never resent by an
    ordinary idempotent rerun.
    """

    target = _trade_date(trade_date)
    if not target:
        return {
            "status": "blocked",
            "sent": False,
            "reason": "invalid_trade_date",
            "target_trade_date": None,
        }
    body = str(markdown or "")
    if not body.strip() or target not in body:
        return {
            "status": "blocked",
            "sent": False,
            "reason": "report_body_trade_date_mismatch",
            "target_trade_date": target,
        }

    state_file = Path(state_path or MAIL_STATE_FILE)
    state = _read_state(state_file)
    sent_targets = state.get("sent_targets")
    sent_targets = sent_targets if isinstance(sent_targets, dict) else {}
    if target in sent_targets:
        return {
            "status": "already_sent",
            "sent": False,
            "target_trade_date": target,
            "content_digest": sent_targets[target].get("content_digest"),
        }

    conf = dict(smtp_conf) if smtp_conf is not None else _smtp_conf()
    if not conf:
        return {
            "status": "disabled",
            "sent": False,
            "reason": "email_config_missing_or_disabled",
            "target_trade_date": target,
        }

    attachment_specs = (
        (
            f"research_eod_{target}.md",
            report_paths.get("claude_md"),
            "octet-stream",
        ),
        (
            f"payload_{target}.json",
            report_paths.get("payload"),
            "json",
        ),
    )
    attachments = []
    for filename, raw_path, subtype in attachment_specs:
        path = Path(str(raw_path or ""))
        if not raw_path or not path.is_file():
            return {
                "status": "blocked",
                "sent": False,
                "reason": f"report_artifact_missing:{filename}",
                "target_trade_date": target,
            }
        attachments.append((filename, str(path), subtype))

    subject = f"[新研究EOD] {target}"
    sender = send_func or send_email
    delivered = bool(sender(
        body=body,
        attachments=attachments,
        smtp_conf=conf,
        subject=subject,
        is_html=False,
    ))
    if not delivered:
        return {
            "status": "failed",
            "sent": False,
            "target_trade_date": target,
            "subject": subject,
        }

    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    sent_targets[target] = {
        "sent_at": dt.datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "subject": subject,
        "content_digest": digest,
        "report_path": str(report_paths.get("claude_md") or ""),
    }
    _write_state(state_file, {
        "schema_version": 1,
        "sent_targets": sent_targets,
        "updated_at": dt.datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
    })
    return {
        "status": "sent",
        "sent": True,
        "target_trade_date": target,
        "subject": subject,
        "content_digest": digest,
    }
