# -*- coding: utf-8 -*-
"""Materialize the MR6 walk-forward selection audit.

The output is research-only.  It cannot update scoring, D-line tasks, reports,
or portfolio actions.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from vaxstock import config
from vaxstock.research.contextual_group import (
    GROUP_DIMENSION,
    STOCK_GROUP_FACTOR_ID,
)
from vaxstock.research.contracts import validate_selection_audit
from vaxstock.research.group_outcome import select_eod_group_assignments
from vaxstock.research.point_in_time_store import (
    StoreError,
    StorePaths,
    default_store_paths,
    read_jsonl_strict,
)
from vaxstock.research.walk_forward_select import (
    DEFAULT_HORIZONS,
    SelectionPolicy,
    build_selection_audit,
)
from vaxstock.services.group_outcome_refresh import GROUP_OUTCOMES_FILE


logger = logging.getLogger(__name__)
SELECTIONS_DIR = config.STATE_DIR / "research" / "selections"


def _aware(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StoreError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StoreError(f"{field} must include a timezone offset")
    return parsed


@contextmanager
def _exclusive_target_lock(target: Path):
    lock_path = Path(str(target) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if lock_path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _group_rows_for_dates(
    *,
    paths: StorePaths,
    trade_dates: Iterable[str],
) -> List[Dict[str, Any]]:
    result = []
    for trade_date in sorted(set(trade_dates)):
        partition = paths.factors / f"{trade_date}.jsonl"
        result.extend(
            row
            for row in read_jsonl_strict(partition)
            if (
                row.get("dimension") == GROUP_DIMENSION
                and row.get("factor_id") == STOCK_GROUP_FACTOR_ID
            )
        )
    return result


def _write_immutable_audit(path: Path, audit: Mapping[str, Any]) -> str:
    target = Path(path)
    validate_selection_audit(audit)
    payload = (
        json.dumps(
            dict(audit),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )
    with _exclusive_target_lock(target):
        if target.exists():
            current = target.read_text(encoding="utf-8")
            try:
                stored = json.loads(current)
            except json.JSONDecodeError as exc:
                raise StoreError(
                    f"invalid stored selection audit: {target}"
                ) from exc
            if not isinstance(stored, dict):
                raise StoreError(
                    f"stored selection audit must be an object: {target}"
                )
            validate_selection_audit(stored)
            if current != payload:
                raise StoreError(
                    f"selection audit changed for immutable target: {target}"
                )
            return "already_complete"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    return "written"


def _discovery_summary(audit: Mapping[str, Any]) -> Dict[str, Any]:
    """Return only signal-bearing diagnostics, not the full audit ledger."""

    result = {}
    for horizon, raw in sorted(
        (audit.get("horizons") or {}).items(),
        key=lambda item: int(item[0]),
    ):
        if not isinstance(raw, Mapping):
            continue
        build = raw.get("build") or {}
        selection = raw.get("selection") or {}
        exploratory = selection.get("exploratory_diagnostics") or {}
        result[str(horizon)] = {
            "status": selection.get("status"),
            "independent_dates": selection.get(
                "independent_dates_available"
            ),
            "factor_series_total": build.get("factor_series_total"),
            "factor_series_tested": build.get("factor_series_tested"),
            "candidate_tests": build.get("candidate_tests"),
            "recent_reversal_count": exploratory.get(
                "recent_reversal_count"
            ),
            "direction_consistent_count": exploratory.get(
                "direction_consistent_count"
            ),
            "recent_reversals": list(
                exploratory.get("recent_reversals") or []
            )[:3],
            "direction_consistent_candidates": list(
                exploratory.get("direction_consistent_candidates") or []
            )[:3],
            "evidence_label": exploratory.get("evidence_label"),
            "forecast_eligible": False,
        }
    return result


def run_select_refresh(
    *,
    research_paths: Optional[StorePaths] = None,
    outcomes_path: Optional[Path] = None,
    selections_dir: Optional[Path] = None,
    as_of_trade_date: Optional[str] = None,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    policy: SelectionPolicy = SelectionPolicy(),
) -> Dict[str, Any]:
    """Build an immutable point-in-time selection audit for one group date."""

    paths = research_paths or default_store_paths()
    outcome_file = Path(outcomes_path or GROUP_OUTCOMES_FILE)
    outcomes = read_jsonl_strict(outcome_file)
    if not outcomes:
        return {
            "status": "blocked",
            "reason": "group_outcomes_empty",
            "outcomes_path": str(outcome_file),
        }
    factor_dates = {
        child.stem for child in paths.factors.glob("*.jsonl")
        if len(child.stem) == 8 and child.stem.isdigit()
    }
    if not factor_dates:
        return {
            "status": "blocked",
            "reason": "eod_group_factors_empty",
        }
    target_date = str(as_of_trade_date or "")
    target_groups = []
    search_dates = (
        [target_date]
        if target_date
        else sorted(factor_dates, reverse=True)
    )
    for candidate_date in search_dates:
        target_rows = _group_rows_for_dates(
            paths=paths,
            trade_dates=[candidate_date],
        )
        selected, _ = select_eod_group_assignments(target_rows)
        target_groups = [
            row for (trade_date, _), row in selected.items()
            if trade_date == candidate_date
        ]
        if target_groups:
            target_date = candidate_date
            break
    if not target_groups:
        return {
            "status": "blocked",
            "reason": "target_eod_group_missing",
            "as_of_trade_date": target_date,
        }
    decision_time = max(
        _aware(row["calculated_at"], "group calculated_at")
        for row in target_groups
    )
    decision_at = decision_time.isoformat(timespec="seconds")
    scoped_dates = {
        trade_date for trade_date in factor_dates
        if trade_date <= target_date
    }
    group_rows = [
        row for row in _group_rows_for_dates(
            paths=paths,
            trade_dates=scoped_dates,
        )
        if _aware(row.get("calculated_at"), "group calculated_at")
        <= decision_time
    ]
    outcomes = [
        row for row in outcomes
        if (
            str(row.get("as_of_trade_date") or "") < target_date
            and _aware(
                row.get("outcome_available_at"), "outcome_available_at"
            ) <= decision_time
        )
    ]
    _, group_audit = select_eod_group_assignments(group_rows)
    audit = build_selection_audit(
        group_factor_rows=group_rows,
        outcome_rows=outcomes,
        as_of_trade_date=target_date,
        decision_at=decision_at,
        horizons=horizons,
        policy=policy,
    )
    audit["group_selection_audit"] = group_audit
    target_dir = Path(selections_dir or SELECTIONS_DIR)
    target = (
        target_dir
        / f"selection_audit_{target_date}__{audit['select_version']}.json"
    )
    write_status = _write_immutable_audit(target, audit)
    statuses = set(audit["status_counts"])
    result_status = (
        "shadow_candidate"
        if "shadow_candidate" in statuses
        else "abstain"
    )
    result = {
        "status": result_status,
        "write_status": write_status,
        "as_of_trade_date": target_date,
        "decision_at": decision_at,
        "audit_path": str(target),
        "outcomes_path": str(outcome_file),
        "status_counts": audit["status_counts"],
        "discovery_summary": _discovery_summary(audit),
        "production_eligible": False,
    }
    logger.info("Research v2 select audit: %s", result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build point-in-time walk-forward selection audit"
    )
    parser.add_argument("--research-dir", type=Path)
    parser.add_argument("--outcomes", type=Path)
    parser.add_argument("--selections-dir", type=Path)
    parser.add_argument("--trade-date")
    args = parser.parse_args(argv)
    result = run_select_refresh(
        research_paths=(
            default_store_paths(args.research_dir)
            if args.research_dir
            else None
        ),
        outcomes_path=args.outcomes,
        selections_dir=args.selections_dir,
        as_of_trade_date=args.trade_date,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in {"abstain", "shadow_candidate"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
