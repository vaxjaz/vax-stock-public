# -*- coding: utf-8 -*-
"""Finalize the D-line evidence chain for one explicit trade date.

The closeout is market-data-only.  User executions are deliberately excluded.
It is safe to retry: append-only writers keep their own evidence identities and
this service serializes concurrent closeouts with an OS file lock.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from vaxstock import config
from vaxstock.research.dline_review import REPORT_DIR, STATE_FILE, run_dline_review
from vaxstock.services.dline_evaluator import (
    FACTOR_RESULTS_FILE,
    FORECASTS_FILE,
    RESULTS_FILE,
    SNAPSHOTS_FILE,
    TASKS_FILE,
    backfill_dline_results,
)
from vaxstock.services.forecast_evolution import (
    CURRENT_EVOLUTION_FILE,
    EVOLUTION_HISTORY_FILE,
    finalize_evolutions,
)
from vaxstock.services.forecast_recorder import DLINE_PLAN_VERSION
from vaxstock.services.observation_coverage import (
    OBSERVATION_HISTORY_FILE,
    OBSERVATION_STATUS_FILE,
    finalize_observation_coverage,
)

logger = logging.getLogger(__name__)

FORECAST_DIR = config.STATE_DIR / "forecast"
CLOSEOUT_STATUS_FILE = FORECAST_DIR / "current_closeout_status.json"
SCHEMA_VERSION = 1
POLICY_VERSION = "dline_closeout_v1"
ABNORMAL_STATUSES = {"partial_data", "failed"}


def _trade_date_key(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    for pattern in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, pattern).strftime("%Y%m%d")
        except ValueError:
            continue
    return None


def _stamp(value=None) -> str:
    if isinstance(value, dt.datetime):
        return value.isoformat(timespec="seconds")
    text = str(value or "").strip()
    if text:
        dt.datetime.fromisoformat(text)
        return text
    return dt.datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def _read_jsonl_strict(path) -> List[Dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line_no, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL: {source} line {line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row is not an object: {source} line {line_no}")
        rows.append(row)
    return rows


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


@contextmanager
def _exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _trigger_index(rows: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: str(item.get("forecast_ts") or "")):
        inputs = (row or {}).get("inputs_ref") or {}
        structured = (row or {}).get("structured") or {}
        if structured.get("source") != "dline_task_blueprint":
            continue
        task_id = str(inputs.get("dline_task_id") or structured.get("task_id") or "").strip()
        blueprint = inputs.get("trigger_blueprint") or {}
        trigger_type = str(
            blueprint.get("trigger_type") or structured.get("trigger_type") or ""
        ).strip()
        if (
            task_id
            and trigger_type
            and str(inputs.get("dline_plan_version") or "").strip() == DLINE_PLAN_VERSION
        ):
            out.setdefault((task_id, trigger_type), row)
    return out


def _latest_by_task(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        task_id = str((row or {}).get("task_id") or "").strip()
        if task_id:
            out[task_id] = row
    return out


def _evolution_index(rows: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        key = (
            str((row or {}).get("task_id") or "").strip(),
            str((row or {}).get("trigger_type") or "").strip(),
        )
        if all(key):
            out[key] = row
    return out


def _result_trigger_keys(rows: Iterable[Dict[str, Any]], target: str) -> set:
    keys = set()
    for row in rows:
        if _trade_date_key(row.get("target_trade_date")) != target:
            continue
        if str(row.get("horizon") or "") != "0":
            continue
        if ((row.get("trigger") or {}).get("status")) != "triggered":
            continue
        key = (str(row.get("task_id") or "").strip(), str(row.get("trigger_type") or "").strip())
        if all(key):
            keys.add(key)
    return keys


def _gap(code: str, keys: Iterable[Any], detail: str) -> Dict[str, Any]:
    values = sorted("|".join(value) if isinstance(value, tuple) else str(value) for value in keys)
    return {"code": code, "count": len(values), "examples": values[:20], "detail": detail}


def _audit_evidence(*, target: str, tasks: List[Dict[str, Any]], forecasts: List[Dict[str, Any]],
                    coverage_rows: List[Dict[str, Any]], evolution_rows: List[Dict[str, Any]],
                    result_rows: List[Dict[str, Any]], result_stage_ok: bool) -> Dict[str, Any]:
    current_tasks = {
        str(row.get("task_id") or "").strip(): row
        for row in tasks
        if _trade_date_key(row.get("target_trade_date")) == target
        and str(row.get("plan_version") or "").strip() == DLINE_PLAN_VERSION
        and str(row.get("task_id") or "").strip()
    }
    task_ids = set(current_tasks)
    triggers = {
        key: row for key, row in _trigger_index(forecasts).items() if key[0] in task_ids
    }
    coverage = _latest_by_task(coverage_rows)
    evolutions = _evolution_index(evolution_rows)
    result_keys = _result_trigger_keys(result_rows, target)

    coverage_present = task_ids.intersection(coverage)
    coverage_unqualified = {
        task_id for task_id in coverage_present
        if not bool(((coverage[task_id].get("quality") or {}).get("qualified")))
    }
    trigger_keys = set(triggers)
    coverage_required = set()
    for task_id, task in current_tasks.items():
        blueprints = ((task.get("observation") or {}).get("trigger_blueprints") or [])
        blueprint_types = {
            str((blueprint or {}).get("trigger_type") or "").strip()
            for blueprint in blueprints
            if isinstance(blueprint, dict)
        }
        if any((task_id, trigger_type) not in trigger_keys for trigger_type in blueprint_types):
            coverage_required.add(task_id)
    evolution_present = trigger_keys.intersection(evolutions)
    evolution_missing = trigger_keys.difference(evolutions)
    evolution_incomplete = {
        key for key in evolution_present
        if not bool(((evolutions[key].get("quality") or {}).get("complete")))
    }

    gaps: List[Dict[str, Any]] = []
    if not task_ids:
        gaps.append({
            "code": "tasks_missing", "count": 1, "examples": [target],
            "detail": "目标交易日没有 D-line v2 观察任务",
        })
    required_coverage_missing = coverage_required.difference(coverage)
    required_coverage_unqualified = coverage_required.intersection(coverage_unqualified)
    if required_coverage_missing:
        gaps.append(_gap(
            "coverage_missing", required_coverage_missing,
            "存在未触发蓝图，但任务没有全天观察覆盖归档",
        ))
    if required_coverage_unqualified:
        gaps.append(_gap(
            "coverage_unqualified", required_coverage_unqualified,
            "存在未触发蓝图，但观察未达到全天覆盖标准",
        ))
    if evolution_missing:
        gaps.append(_gap("evolution_missing", evolution_missing, "触发后没有盘中演变归档"))
    if evolution_incomplete:
        gaps.append(_gap("evolution_incomplete", evolution_incomplete, "演变缺少 15m、30m 或收盘检查点"))
    if result_stage_ok:
        result_missing = trigger_keys.difference(result_keys)
        if result_missing:
            gaps.append(_gap("trigger_result_missing", result_missing, "触发样本尚无 T+0 官方收盘结果"))

    return {
        "target_trade_date": target,
        "task_count": len(task_ids),
        "trigger_count": len(trigger_keys),
        "coverage_required_task_count": len(coverage_required),
        "coverage_count": len(coverage_present),
        "qualified_coverage_count": len(coverage_present - coverage_unqualified),
        "evolution_count": len(evolution_present),
        "complete_evolution_count": len(evolution_present - evolution_incomplete),
        "trigger_t0_result_count": len(trigger_keys.intersection(result_keys)),
        "gaps": gaps,
        "user_execution_used": False,
    }

def _smtp_conf() -> Optional[Dict[str, Any]]:
    secrets = config.SECRETS
    if not (
        secrets.get("email_enabled")
        and secrets.get("email_user")
        and secrets.get("email_authcode")
        and secrets.get("email_to")
    ):
        return None
    return {
        "smtp_server": secrets.get("smtp_server", "smtp.qq.com"),
        "smtp_port": secrets.get("smtp_port", 465),
        "sender_email": secrets["email_user"],
        "sender_password": secrets["email_authcode"],
        "receiver_email": secrets["email_to"],
    }


def _default_notifier(title: str, content: str) -> Dict[str, bool]:
    from vaxstock.report.notify import push_email, push_wechat

    return {
        "wechat": push_wechat(
            title, content, pushplus_token=config.SECRETS.get("pushplus_token", ""),
        ),
        "email": push_email(title, content, smtp_conf=_smtp_conf()),
    }


def _alert_signature(target: str, status: str, gaps: List[Dict[str, Any]],
                     errors: List[Dict[str, Any]]) -> str:
    payload = {
        "target_trade_date": target,
        "status": status,
        "gaps": [
            {
                "code": row.get("code"),
                "count": row.get("count"),
                "examples": row.get("examples") or [],
            }
            for row in gaps
        ],
        "errors": [
            {
                "stage": row.get("stage"),
                "type": row.get("type"),
                "message": row.get("message"),
            }
            for row in errors
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()




def _delivery_succeeded(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        flags = [item for item in value.values() if isinstance(item, bool)]
        return any(flags) if flags else True
    return True

def _notification_text(status: str, target: str, evidence: Mapping[str, Any],
                       errors: List[Dict[str, Any]], *, recovered: bool = False) -> str:
    if recovered:
        return "\n".join([
            f"D线 {target} 日终结算已恢复。",
            f"任务 {evidence.get('task_count', 0)}，触发 {evidence.get('trigger_count', 0)}，"
            f"完整覆盖 {evidence.get('qualified_coverage_count', 0)}，"
            f"完整演变 {evidence.get('complete_evolution_count', 0)}。",
            "结果回填与策略复核已重新执行；未使用任何用户实际成交数据。",
        ])
    lines = [
        f"D线 {target} 日终结算状态：{status}",
        f"任务 {evidence.get('task_count', 0)}，触发 {evidence.get('trigger_count', 0)}，"
        f"完整覆盖 {evidence.get('qualified_coverage_count', 0)}，"
        f"完整演变 {evidence.get('complete_evolution_count', 0)}，"
        f"触发T+0结果 {evidence.get('trigger_t0_result_count', 0)}。",
    ]
    for gap in evidence.get("gaps") or []:
        lines.append(f"- 数据缺口 {gap.get('code')}: {gap.get('count')}；{gap.get('detail')}")
    for error in errors:
        lines.append(f"- 阶段失败 {error.get('stage')}: {error.get('type')} - {error.get('message')}")
    lines.extend([
        "数据修复后可幂等重试：",
        f"python -m vaxstock.services.dline_closeout --trade-date {target}",
        "D线结论仅基于市场数据；未使用任何用户实际成交数据。",
    ])
    return "\n".join(lines)


def run_dline_closeout(*, trade_date: str, status_path=None, tasks_path=None,
                       forecasts_path=None, coverage_path=None,
                       observation_status_path=None, evolution_path=None,
                       evolution_status_path=None, snapshots_path=None,
                       factor_results_path=None, results_path=None,
                       review_output_dir=None, review_state_path=None,
                       alert: bool = True,
                       notifier: Optional[Callable[[str, str], Any]] = None,
                       now=None) -> Dict[str, Any]:
    """Finalize, backfill, review and audit one D-line trade date."""
    target = _trade_date_key(trade_date)
    if not target:
        raise ValueError("trade_date must be an explicit YYYYMMDD or YYYY-MM-DD value")

    status_file = Path(status_path or CLOSEOUT_STATUS_FILE)
    lock_file = status_file.with_suffix(".lock")
    with _exclusive_lock(lock_file):
        started_at = _stamp(now)
        try:
            previous = _read_json(status_file)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            previous = {}
            logger.warning("D-line closeout previous status invalid: %s", exc)

        paths = {
            "tasks": Path(tasks_path or TASKS_FILE),
            "forecasts": Path(forecasts_path or FORECASTS_FILE),
            "coverage": Path(coverage_path or OBSERVATION_HISTORY_FILE),
            "observation_status": Path(observation_status_path or OBSERVATION_STATUS_FILE),
            "evolution": Path(evolution_path or EVOLUTION_HISTORY_FILE),
            "evolution_status": Path(evolution_status_path or CURRENT_EVOLUTION_FILE),
            "snapshots": Path(snapshots_path or SNAPSHOTS_FILE),
            "factor_results": Path(factor_results_path or FACTOR_RESULTS_FILE),
            "results": Path(results_path or RESULTS_FILE),
            "review_output": Path(review_output_dir or REPORT_DIR),
            "review_state": Path(review_state_path or STATE_FILE),
        }
        stages: Dict[str, Any] = {}
        errors: List[Dict[str, Any]] = []

        def fail(stage: str, exc: Exception) -> None:
            errors.append({
                "stage": stage,
                "type": type(exc).__name__,
                "message": str(exc)[:300],
            })
            stages[stage] = {"status": "failed", "detail": str(exc)[:300]}

        try:
            tasks = _read_jsonl_strict(paths["tasks"])
            forecasts = _read_jsonl_strict(paths["forecasts"])
            stages["source_validation"] = {
                "status": "done", "tasks": len(tasks), "forecasts": len(forecasts),
            }
        except Exception as exc:
            tasks, forecasts = [], []
            fail("source_validation", exc)

        try:
            finalization = finalize_observation_coverage(
                target,
                status_path=paths["observation_status"],
                history_path=paths["coverage"],
                finalized_at=started_at,
            )
            stages["coverage_finalization"] = finalization
            if finalization.get("status") == "invalid":
                errors.append({
                    "stage": "coverage_finalization",
                    "type": "InvalidRuntimeState",
                    "message": str(finalization.get("detail") or "invalid coverage state")[:300],
                })
        except Exception as exc:
            fail("coverage_finalization", exc)

        try:
            finalization = finalize_evolutions(
                target,
                status_path=paths["evolution_status"],
                history_path=paths["evolution"],
                finalized_at=started_at,
            )
            stages["evolution_finalization"] = finalization
            if finalization.get("status") == "invalid":
                errors.append({
                    "stage": "evolution_finalization",
                    "type": "InvalidRuntimeState",
                    "message": str(finalization.get("detail") or "invalid evolution state")[:300],
                })
        except Exception as exc:
            fail("evolution_finalization", exc)

        result_stage_ok = False
        try:
            _read_jsonl_strict(paths["snapshots"])
            _read_jsonl_strict(paths["factor_results"])
            stages["result_backfill"] = backfill_dline_results(
                as_of_trade_date=None,
                tasks_path=paths["tasks"],
                forecasts_path=paths["forecasts"],
                coverage_path=paths["coverage"],
                observation_status_path=paths["observation_status"],
                snapshots_path=paths["snapshots"],
                factor_results_path=paths["factor_results"],
                results_path=paths["results"],
                filled_at=started_at,
            )
            result_stage_ok = True
        except Exception as exc:
            fail("result_backfill", exc)

        if result_stage_ok:
            try:
                _read_jsonl_strict(paths["results"])
                _read_jsonl_strict(paths["evolution"])
                review = run_dline_review(
                    write=True,
                    results_path=paths["results"],
                    evolution_path=paths["evolution"],
                    output_dir=paths["review_output"],
                    state_path=paths["review_state"],
                    as_of_trade_date=target,
                )
                stages["strategy_review"] = {
                    "status": "done",
                    "cells": len(review.get("cells") or []),
                    "changes": len(review.get("changes") or []),
                }
            except Exception as exc:
                fail("strategy_review", exc)
        else:
            stages["strategy_review"] = {
                "status": "skipped_dependency",
                "dependency": "result_backfill",
            }

        try:
            coverage_rows = _read_jsonl_strict(paths["coverage"])
            evolution_rows = _read_jsonl_strict(paths["evolution"])
            result_rows = _read_jsonl_strict(paths["results"])
            evidence = _audit_evidence(
                target=target,
                tasks=tasks,
                forecasts=forecasts,
                coverage_rows=coverage_rows,
                evolution_rows=evolution_rows,
                result_rows=result_rows,
                result_stage_ok=result_stage_ok,
            )
            stages["evidence_audit"] = {"status": "done"}
        except Exception as exc:
            fail("evidence_audit", exc)
            evidence = {
                "target_trade_date": target,
                "task_count": 0,
                "trigger_count": 0,
                "coverage_required_task_count": 0,
                "coverage_count": 0,
                "qualified_coverage_count": 0,
                "evolution_count": 0,
                "complete_evolution_count": 0,
                "trigger_t0_result_count": 0,
                "gaps": [],
                "user_execution_used": False,
            }

        overall = "failed" if errors else (
            "partial_data" if evidence.get("gaps") else "done"
        )
        completed_at = _stamp(now)
        notification: Dict[str, Any] = {"status": "not_needed"}
        last_signature = previous.get("last_alert_signature")
        last_alert_status = previous.get("last_alert_status")
        if last_alert_status is None and last_signature:
            last_alert_status = previous.get("status")
        signature = _alert_signature(target, overall, evidence.get("gaps") or [], errors)
        previous_abnormal_same_target = (
            _trade_date_key(previous.get("target_trade_date")) == target
            and last_alert_status in ABNORMAL_STATUSES
        )
        notify = notifier or _default_notifier
        title = None
        body = None
        if alert and overall in ABNORMAL_STATUSES and signature != last_signature:
            title = f"[D线异常] {target} 日终结算 {overall}"
            body = _notification_text(overall, target, evidence, errors)
        elif alert and overall == "done" and previous_abnormal_same_target:
            signature = _alert_signature(target, "recovered", [], [])
            if signature != last_signature:
                title = f"[D线恢复] {target} 日终结算完成"
                body = _notification_text(overall, target, evidence, [], recovered=True)
        if title and body:
            try:
                delivery = notify(title, body)
                delivered = _delivery_succeeded(delivery)
                notification = {
                    "status": "sent" if delivered else "attempted_no_delivery",
                    "title": title,
                    "delivery": delivery,
                }
                if delivered:
                    last_signature = signature
                    last_alert_status = "recovered" if overall == "done" else overall
            except Exception as exc:
                notification = {
                    "status": "failed", "title": title,
                    "detail": f"{type(exc).__name__}: {str(exc)[:300]}",
                }

        state = {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "target_trade_date": target,
            "status": overall,
            "started_at": started_at,
            "completed_at": completed_at,
            "stages": stages,
            "evidence": evidence,
            "errors": errors,
            "notification": notification,
            "last_alert_signature": last_signature,
            "last_alert_status": last_alert_status,
            "retry_command": f"python -m vaxstock.services.dline_closeout --trade-date {target}",
            "user_execution_used": False,
        }
        _write_json_atomic(status_file, state)
        logger.info(
            "D-line closeout: target=%s status=%s tasks=%s triggers=%s gaps=%s errors=%s",
            target, overall, evidence.get("task_count"), evidence.get("trigger_count"),
            len(evidence.get("gaps") or []), len(errors),
        )
        return state


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Finalize one D-line trade date idempotently")
    parser.add_argument("--trade-date", required=True, help="Explicit market trade date: YYYYMMDD")
    parser.add_argument("--no-alert", action="store_true", help="Do not send anomaly/recovery notification")
    args = parser.parse_args(argv)
    result = run_dline_closeout(trade_date=args.trade_date, alert=not args.no_alert)
    print(json.dumps({
        "target_trade_date": result.get("target_trade_date"),
        "status": result.get("status"),
        "evidence": result.get("evidence"),
        "errors": result.get("errors"),
        "retry_command": result.get("retry_command"),
    }, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "done" else (2 if result.get("status") == "partial_data" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
