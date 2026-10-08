"""Attachment-free macro delivery; only the latest sent date is retained."""
from pathlib import Path
from vaxstock import config
from vaxstock.report.mailer import send_email
from vaxstock.services.research_eod_mail import _smtp_conf, _read_state, _write_state


def send_macro_email(*, trade_date, body, state_path=None, smtp_conf=None, send_func=None):
    target = str(trade_date or "").strip()
    if len(target) != 8 or not target.isdigit() or target not in body:
        return {"status": "blocked", "sent": False}
    path = Path(state_path or config.STATE_DIR / "eod" / "macro_mail_state.json")
    if _read_state(path).get("trade_date") == target:
        return {"status": "already_sent", "sent": False}
    conf = _smtp_conf() if smtp_conf is None else dict(smtp_conf)
    if not conf:
        return {"status": "disabled", "sent": False}
    sent = bool((send_func or send_email)(body=body, attachments=[], smtp_conf=conf,
                                       subject=f"[宏观环境] {target}", is_html=False))
    if sent:
        _write_state(path, {"trade_date": target})
    return {"status": "sent" if sent else "failed", "sent": sent}
