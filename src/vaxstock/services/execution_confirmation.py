# -*- coding: utf-8 -*-
"""Persist and reconcile explicitly user-confirmed broker executions."""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from vaxstock import config
from vaxstock.analysis.execution import (
    build_holdings_projection, build_portfolio_projection,
    reconcile_execution, validate_execution_confirmation,
)
from vaxstock.report.execution_review import render_execution_review


STRATEGY_DIR = config.STATE_DIR / "strategy"
EXECUTION_RECORDS_FILE = STRATEGY_DIR / "execution_records.jsonl"
HOLDINGS_BASE_FILE = config.HOLDINGS_BASE_FILE
HOLDINGS_STATE_FILE = config.HOLDINGS_STATE_FILE
PORTFOLIO_STATE_FILE = config.PORTFOLIO_STATE_FILE


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _read_json(path: Path, *, missing_ok: bool = False) -> Dict[str, Any]:
    if not path.exists():
        if missing_ok:
            return {}
        raise ValueError(f"required_json_missing:{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid_json:{path}:{type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"json_root_not_object:{path}")
    return data


def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _canonical_hash(data: Mapping[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_records(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"execution_records_invalid_json_line:{line_no}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"execution_records_line_not_object:{line_no}")
        rows.append(row)
    return rows


def _append_record(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _date_key(value: Any) -> Optional[str]:
    text = str(value or "").strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return dt.datetime.strptime(text, "%Y%m%d").strftime("%Y%m%d")
    except ValueError:
        return None


def _projection_guard(document: Mapping[str, Any], confirmation: Mapping[str, Any],
                      label: str) -> Optional[str]:
    current_id = str(document.get("last_execution_confirmation_id") or "").strip()
    confirmation_id = str(confirmation.get("confirmation_id") or "")
    if current_id == confirmation_id:
        return None
    target = _date_key(confirmation.get("trade_date"))
    current_date = _date_key(document.get("as_of_trade_date"))
    if target and current_date and current_date > target:
        return f"{label}.newer_projection_exists"
    if current_id:
        supersedes = str(confirmation.get("supersedes_confirmation_id") or "").strip()
        if supersedes != current_id:
            return f"{label}.supersedes_confirmation_id_mismatch"
    return None


def _load_plan(strategy_dir: Path, trade_date: str, plan_path=None):
    candidates = [Path(plan_path)] if plan_path else [
        strategy_dir / f"close_review_{trade_date}.json",
        strategy_dir / f"daily_action_{trade_date}.json",
    ]
    for path in candidates:
        if path.exists():
            return _read_json(path), path
    return {}, None


def _review_paths(strategy_dir: Path, trade_date: str):
    return {
        "dated_json": strategy_dir / f"execution_review_{trade_date}.json",
        "latest_json": strategy_dir / "execution_review_latest.json",
        "dated_md": strategy_dir / f"execution_review_{trade_date}.md",
        "latest_md": strategy_dir / "execution_review_latest.md",
    }


def apply_execution_confirmation(input_data, *, records_path=None, holdings_path=None,
                                 portfolio_path=None, strategy_dir=None, plan_path=None,
                                 dry_run: bool = False) -> Dict[str, Any]:
    raw = _read_json(Path(input_data)) if isinstance(input_data, (str, Path)) else dict(input_data or {})
    records_file = Path(records_path or EXECUTION_RECORDS_FILE)
    holdings_file = Path(holdings_path or HOLDINGS_STATE_FILE)
    prior_holdings_file = holdings_file if holdings_file.exists() else Path(HOLDINGS_BASE_FILE)
    portfolio_file = Path(portfolio_path or PORTFOLIO_STATE_FILE)
    out_dir = Path(strategy_dir or STRATEGY_DIR)
    input_hash = _canonical_hash(raw)
    confirmation_id = str(raw.get("confirmation_id") or "").strip()

    try:
        records = _read_records(records_file)
        holdings_document = _read_json(prior_holdings_file)
        portfolio_document = _read_json(portfolio_file)
    except ValueError as exc:
        return {"status": "invalid_state", "errors": [str(exc)], "written": 0}

    existing = next(
        (row for row in records if str(row.get("confirmation_id") or "") == confirmation_id), None
    )
    if existing is None:
        recorded_execution_ids = {}
        for row in records:
            recorded_confirmation_id = str(row.get("confirmation_id") or "")
            for trade in ((row.get("confirmation") or {}).get("trades") or []):
                execution_id = str(trade.get("execution_id") or "").strip()
                if execution_id:
                    recorded_execution_ids[execution_id] = recorded_confirmation_id
        duplicate_execution_ids = sorted({
            str(trade.get("execution_id") or "").strip()
            for trade in (raw.get("trades") or []) if isinstance(trade, Mapping)
            if str(trade.get("execution_id") or "").strip() in recorded_execution_ids
        })
        if duplicate_execution_ids:
            return {
                "status": "execution_id_conflict",
                "confirmation_id": confirmation_id or None,
                "errors": [
                    f"execution_id_already_recorded:{execution_id}:"
                    f"{recorded_execution_ids[execution_id]}"
                    for execution_id in duplicate_execution_ids
                ],
                "written": 0,
            }
    if existing is not None:
        if existing.get("input_sha256") != input_hash:
            return {
                "status": "confirmation_id_conflict",
                "confirmation_id": confirmation_id,
                "errors": ["same_confirmation_id_has_different_payload"],
                "written": 0,
            }
        confirmation = existing.get("confirmation") or {}
        validation = {"valid": True, "errors": [], "warnings": existing.get("warnings") or []}
        journal_status = "already_recorded"
    else:
        validation = validate_execution_confirmation(raw, holdings_document.get("holdings") or {})
        if not validation["valid"]:
            return {
                "status": "invalid_confirmation",
                "confirmation_id": confirmation_id or None,
                "errors": validation["errors"],
                "warnings": validation["warnings"],
                "written": 0,
            }
        confirmation = validation["confirmation"]
        journal_status = "validated"

    plan, used_plan_path = _load_plan(out_dir, confirmation.get("trade_date"), plan_path=plan_path)
    review = reconcile_execution(plan, confirmation)
    holdings_projection = build_holdings_projection(holdings_document, confirmation)
    portfolio_projection = build_portfolio_projection(portfolio_document, confirmation)
    guard_errors = []
    if holdings_projection is not None:
        for document, label in ((holdings_document, "holdings"), (portfolio_document, "portfolio")):
            error = _projection_guard(document, confirmation, label)
            if error:
                guard_errors.append(error)

    if dry_run:
        return {
            "status": "dry_run_valid" if not guard_errors else "dry_run_projection_blocked",
            "confirmation_id": confirmation.get("confirmation_id"),
            "errors": guard_errors,
            "warnings": validation.get("warnings") or [],
            "journal_status": journal_status,
            "projection_status": "would_apply" if holdings_projection is not None and not guard_errors else (
                "not_required" if holdings_projection is None else "blocked"
            ),
            "review": review,
            "plan_path": str(used_plan_path) if used_plan_path else None,
            "written": 0,
        }

    if existing is None:
        _append_record(records_file, {
            "schema_version": 1,
            "confirmation_id": confirmation.get("confirmation_id"),
            "trade_date": confirmation.get("trade_date"),
            "recorded_at": _now_iso(),
            "input_sha256": input_hash,
            "warnings": validation.get("warnings") or [],
            "confirmation": confirmation,
        })
        journal_status = "recorded"

    projection_status = "not_required"
    if holdings_projection is not None:
        if guard_errors:
            projection_status = "blocked"
        else:
            already_applied = (
                holdings_document.get("last_execution_confirmation_id") == confirmation.get("confirmation_id")
                and portfolio_document.get("last_execution_confirmation_id") == confirmation.get("confirmation_id")
            )
            _write_json_atomic(holdings_file, holdings_projection)
            _write_json_atomic(portfolio_file, portfolio_projection)
            projection_status = "already_applied" if already_applied else "applied"

    review_document = dict(review)
    review_document.update({
        "generated_at": _now_iso(),
        "journal_status": journal_status,
        "projection_status": projection_status,
        "projection_errors": guard_errors,
        "plan_path": str(used_plan_path) if used_plan_path else None,
    })
    markdown = render_execution_review(review_document, projection_status=projection_status)
    paths = _review_paths(out_dir, confirmation.get("trade_date"))
    for key in ("dated_json", "latest_json"):
        _write_json_atomic(paths[key], review_document)
    for key in ("dated_md", "latest_md"):
        _write_text_atomic(paths[key], markdown)

    return {
        "status": "written" if not guard_errors else "recorded_projection_blocked",
        "confirmation_id": confirmation.get("confirmation_id"),
        "errors": guard_errors,
        "warnings": validation.get("warnings") or [],
        "journal_status": journal_status,
        "projection_status": projection_status,
        "review": review_document,
        "markdown": markdown,
        "records_path": str(records_file),
        "holdings_path": str(holdings_file),
        "portfolio_path": str(portfolio_file),
        "review_paths": {key: str(value) for key, value in paths.items()},
        "written": 4 + (2 if holdings_projection is not None and not guard_errors else 0),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Apply a user-confirmed broker execution bundle")
    parser.add_argument("--input", required=True, help="Confirmed execution JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Validate and reconcile without writes")
    parser.add_argument("--records")
    parser.add_argument("--holdings")
    parser.add_argument("--portfolio")
    parser.add_argument("--strategy-dir")
    parser.add_argument("--plan")
    args = parser.parse_args(argv)
    result = apply_execution_confirmation(
        args.input,
        records_path=args.records,
        holdings_path=args.holdings,
        portfolio_path=args.portfolio,
        strategy_dir=args.strategy_dir,
        plan_path=args.plan,
        dry_run=args.dry_run,
    )
    print(json.dumps({k: v for k, v in result.items() if k not in {"review", "markdown"}}, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"written", "dry_run_valid"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
