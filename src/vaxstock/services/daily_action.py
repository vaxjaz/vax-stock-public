# -*- coding: utf-8 -*-
"""每日操作清单生成与唯一邮件发送；不修改 A-D 事实文件。"""

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict

from vaxstock import config
from vaxstock.analysis.daily_action import build_daily_action_plan
from vaxstock.analysis.position_plan import build_position_capacity, revalue_portfolio_state
from vaxstock.report.daily_action import render_daily_action_markdown
from vaxstock.report.mailer import send_email
from vaxstock.services.history_summary import load_live_history

CURRENT_TASKS_FILE = config.STATE_DIR / "forecast" / "current_tasks.json"
STRATEGY_DIR = config.STATE_DIR / "strategy"
MAIL_STATE_FILE = STRATEGY_DIR / "daily_action_mail_state.json"


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _read_json(path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path, data: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


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


def _snapshot_for_target(snapshot: Dict[str, Any], target_trade_date: str | None) -> Dict[str, Any]:
    if not target_trade_date:
        return snapshot
    target = str(target_trade_date)
    snapshot_targets = {str(x) for x in (snapshot.get("target_trade_dates") or []) if x}
    if target not in snapshot_targets:
        return {"target_trade_dates": [target], "tasks": []}
    filtered = dict(snapshot)
    filtered["target_trade_dates"] = [target]
    filtered["tasks"] = [
        task for task in (snapshot.get("tasks") or [])
        if str(task.get("target_trade_date") or "") == target
    ]
    return filtered


def _enrich_history(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    tasks = snapshot.get("tasks") or []
    baselines = {
        str(task.get("baseline_trade_date") or (task.get("evidence_pack") or {}).get("baseline_trade_date") or "")
        for task in tasks if isinstance(task, dict)
    }
    baseline = next(iter(baselines)) if len(baselines) == 1 else None
    history = load_live_history(cutoff_trade_date=baseline)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        code = str(task.get("code") or "")
        evidence = task.setdefault("evidence_pack", {})
        evidence["B_prediction_history_summary"] = history.get(code) or {
            "available": False,
            "source": "eod_predictions+eod_prediction_results",
            "generation_mode": "live",
            "horizon": "1",
            "cutoff_trade_date": baseline,
            "evaluated": 0,
        }
    return snapshot


def load_daily_strategy_row(code: str, target_trade_date: str | None = None,
                            plan_path=None) -> Dict[str, Any]:
    plan = _read_json(plan_path or (STRATEGY_DIR / "daily_action_latest.json"))
    target = str((plan.get("background") or {}).get("target_trade_date") or "")
    if target_trade_date and target != str(target_trade_date):
        return {}
    for row in plan.get("holdings") or []:
        if str(row.get("code") or "") == str(code):
            return row
    return {}


def refresh_daily_action(*, tasks_path=None, output_dir=None,
                         target_trade_date=None, degraded: bool = False,
                         holdings_data=None, portfolio_state=None,
                         policy_data=None) -> Dict[str, Any]:
    snapshot = _enrich_history(_snapshot_for_target(
        _read_json(tasks_path or CURRENT_TASKS_FILE),
        str(target_trade_date) if target_trade_date else None,
    ))
    holdings = holdings_data if holdings_data is not None else config.load_holdings()
    portfolio = portfolio_state if portfolio_state is not None else config.load_portfolio_state()
    policy = policy_data if policy_data is not None else config.load_strategy_policy()

    tasks = snapshot.get("tasks") or []
    first = tasks[0] if tasks else {}
    evidence = (first.get("evidence_pack") or {}) if isinstance(first, dict) else {}
    baseline = str(evidence.get("baseline_trade_date") or first.get("baseline_trade_date") or "")
    snapshot_date = str(portfolio.get("as_of_trade_date") or "")
    if baseline and len(baseline) == 8 and baseline >= snapshot_date:
        task_prices = {}
        for task in tasks:
            code = str(task.get("code") or "")
            price = ((task.get("evidence_pack") or {}).get("A_eod") or {}).get("price")
            if code and price is not None:
                task_prices[code] = price
        portfolio = revalue_portfolio_state(
            portfolio, holdings, task_prices, as_of_trade_date=baseline
        )

    capacity = build_position_capacity(portfolio, holdings, policy)
    plan = build_daily_action_plan(snapshot, holdings, capacity, policy, degraded=degraded)
    markdown = render_daily_action_markdown(plan)
    target = (plan.get("background") or {}).get("target_trade_date")
    if not target:
        return {"status": "pending", "written": 0, "plan": plan, "markdown": markdown}

    out_dir = Path(output_dir or STRATEGY_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    dated = out_dir / f"daily_action_{target}.md"
    latest = out_dir / "daily_action_latest.md"
    dated_json = out_dir / f"daily_action_{target}.json"
    latest_json = out_dir / "daily_action_latest.json"
    dated.write_text(markdown, encoding="utf-8")
    latest.write_text(markdown, encoding="utf-8")
    _write_json(dated_json, plan)
    _write_json(latest_json, plan)
    return {
        "status": "written",
        "written": 4,
        "target_trade_date": target,
        "degraded": degraded,
        "dated_path": str(dated),
        "latest_path": str(latest),
        "dated_json_path": str(dated_json),
        "latest_json_path": str(latest_json),
        "plan": plan,
        "markdown": markdown,
    }


def send_daily_action_email(action_result: Dict[str, Any], *, mail_state_path=None,
                            send_func=None) -> Dict[str, Any]:
    target = str(action_result.get("target_trade_date") or "")
    if action_result.get("status") != "written" or not target:
        return {"status": "pending", "sent": False, "target_trade_date": target or None}

    state_path = Path(mail_state_path or MAIL_STATE_FILE)
    state = _read_json(state_path)
    sent_targets = state.get("sent_targets") or {}
    if target in sent_targets:
        return {"status": "already_sent", "sent": False, "target_trade_date": target}

    smtp_conf = _smtp_conf()
    if not smtp_conf:
        return {"status": "disabled", "sent": False, "target_trade_date": target}

    degraded = bool(action_result.get("degraded"))
    subject = f"[每日操作{'-降级' if degraded else ''}] {target}"
    sender = send_func or send_email
    try:
        ok = bool(sender(
            action_result.get("markdown") or "",
            [],
            smtp_conf,
            subject=subject,
            is_html=False,
        ))
    except Exception as exc:
        return {
            "status": "failed", "sent": False, "target_trade_date": target,
            "error": f"{type(exc).__name__}: {str(exc)[:160]}",
        }
    if not ok:
        return {"status": "failed", "sent": False, "target_trade_date": target}

    sent_targets[target] = {
        "sent_at": _now_iso(),
        "mode": "degraded" if degraded else "normal",
        "subject": subject,
    }
    _write_json(state_path, {
        "schema_version": 1,
        "sent_targets": sent_targets,
        "updated_at": _now_iso(),
    })
    return {"status": "sent", "sent": True, "target_trade_date": target, "subject": subject}


def refresh_and_send_daily_action(*, target_trade_date=None, degraded: bool = False,
                                  mail_state_path=None, send_func=None, **refresh_kwargs) -> Dict[str, Any]:
    action_result = refresh_daily_action(
        target_trade_date=target_trade_date,
        degraded=degraded,
        **refresh_kwargs,
    )
    mail_result = send_daily_action_email(
        action_result,
        mail_state_path=mail_state_path,
        send_func=send_func,
    )
    return {"action": action_result, "mail": mail_result}


if __name__ == "__main__":
    result = refresh_daily_action()
    print(json.dumps({k: v for k, v in result.items() if k not in {"plan", "markdown"}}, ensure_ascii=False))
