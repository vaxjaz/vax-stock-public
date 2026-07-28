# -*- coding: utf-8 -*-
"""Materialize MR7 forecast results and calibration snapshots."""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from vaxstock import config
from vaxstock.research.conditional_forecast import FORECAST_VERSION
from vaxstock.research.contextual_group import (
    GROUP_DIMENSION,
    STOCK_GROUP_FACTOR_ID,
)
from vaxstock.research.contracts import (
    canonical_digest,
    validate_forecast_audit,
    validate_forecast_calibration_audit,
    validate_forecast_result,
    validate_group_outcome_sample,
    validate_selection_audit,
)
from vaxstock.research.forecast_evaluation import (
    build_calibration_audit,
    evaluate_forecast_audit,
    render_calibration_markdown,
)
from vaxstock.research.point_in_time_store import (
    StoreError,
    StorePaths,
    default_store_paths,
    read_jsonl_strict,
)
from vaxstock.research.walk_forward_select import SELECT_VERSION
from vaxstock.services.forecast_refresh import FORECASTS_DIR
from vaxstock.services.group_outcome_refresh import GROUP_OUTCOMES_FILE
from vaxstock.services.select_refresh import SELECTIONS_DIR


logger = logging.getLogger(__name__)
EVALUATION_DIR = config.STATE_DIR / "research" / "forecast_evaluation"
FORECAST_RESULTS_FILE = EVALUATION_DIR / "forecast_results.jsonl"
CALIBRATIONS_DIR = EVALUATION_DIR / "calibrations"


def _aware(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StoreError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StoreError(f"{field} must include a timezone offset")
    return parsed


def _read_object(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StoreError(f"invalid JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise StoreError(f"JSON root must be an object: {path}")
    return value


@contextmanager
def _exclusive_lock(path: Path):
    lock_path = Path(str(path) + ".lock")
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


def _stable_digest(row: Mapping[str, Any]) -> str:
    return canonical_digest(dict(row))


def _append_results(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
) -> Dict[str, int]:
    target = Path(path)
    incoming = [dict(row) for row in rows]
    for row in incoming:
        validate_forecast_result(row)
    with _exclusive_lock(target):
        existing_rows = read_jsonl_strict(target)
        known = {}
        for row in existing_rows:
            validate_forecast_result(row)
            identity = str(row["result_id"])
            previous = known.get(identity)
            if (
                previous is not None
                and _stable_digest(previous) != _stable_digest(row)
            ):
                raise StoreError(
                    f"stored forecast result conflict: {identity}"
                )
            known[identity] = row
        new_rows: List[Dict[str, Any]] = []
        skipped = 0
        for row in incoming:
            identity = str(row["result_id"])
            previous = known.get(identity)
            if previous is not None:
                if _stable_digest(previous) != _stable_digest(row):
                    raise StoreError(
                        "forecast result changed without a new identity: "
                        f"{identity}"
                    )
                skipped += 1
                continue
            known[identity] = row
            new_rows.append(row)
        if new_rows:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8", newline="\n") as handle:
                for row in new_rows:
                    handle.write(
                        json.dumps(
                            row,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                        + "\n"
                    )
                handle.flush()
                os.fsync(handle.fileno())
        return {
            "existing": len(existing_rows),
            "written": len(new_rows),
            "skipped": skipped,
        }


def _write_calibration_pair(
    *,
    json_path: Path,
    markdown_path: Path,
    audit: Mapping[str, Any],
) -> str:
    validate_forecast_calibration_audit(audit)
    json_payload = (
        json.dumps(
            dict(audit),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )
    markdown_payload = render_calibration_markdown(audit)
    target = Path(json_path)
    markdown_target = Path(markdown_path)
    with _exclusive_lock(target):
        existing_json = target.exists()
        existing_markdown = markdown_target.exists()
        if existing_json and target.read_text(
            encoding="utf-8"
        ) != json_payload:
            raise StoreError(
                f"calibration audit changed for immutable target: {target}"
            )
        if existing_markdown and markdown_target.read_text(
            encoding="utf-8"
        ) != markdown_payload:
            raise StoreError(
                "calibration markdown changed for immutable target: "
                f"{markdown_target}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        if not existing_json:
            with target.open(
                "x", encoding="utf-8", newline="\n"
            ) as handle:
                handle.write(json_payload)
                handle.flush()
                os.fsync(handle.fileno())
        if not existing_markdown:
            with markdown_target.open(
                "x", encoding="utf-8", newline="\n"
            ) as handle:
                handle.write(markdown_payload)
                handle.flush()
                os.fsync(handle.fileno())
    return (
        "already_complete"
        if existing_json and existing_markdown
        else "written"
    )


def _forecast_paths(forecasts_dir: Path) -> List[Path]:
    return sorted(
        Path(forecasts_dir).glob(
            "forecast_audit_????????"
            f"__{SELECT_VERSION}__{FORECAST_VERSION}.json"
        )
    )


def _load_group_rows(
    paths: StorePaths,
    trade_date: str,
) -> List[Dict[str, Any]]:
    return [
        row
        for row in read_jsonl_strict(
            paths.factors / f"{trade_date}.jsonl"
        )
        if (
            row.get("dimension") == GROUP_DIMENSION
            and row.get("factor_id") == STOCK_GROUP_FACTOR_ID
        )
    ]


def run_forecast_evaluation_refresh(
    *,
    research_paths: Optional[StorePaths] = None,
    forecasts_dir: Optional[Path] = None,
    selections_dir: Optional[Path] = None,
    outcomes_path: Optional[Path] = None,
    results_path: Optional[Path] = None,
    calibrations_dir: Optional[Path] = None,
    as_of_trade_date: Optional[str] = None,
    decision_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate visible forecasts and freeze one calibration snapshot."""

    paths = research_paths or default_store_paths()
    source_forecasts = Path(forecasts_dir or FORECASTS_DIR)
    source_selections = Path(selections_dir or SELECTIONS_DIR)
    target_results = Path(results_path or FORECAST_RESULTS_FILE)
    target_calibrations = Path(calibrations_dir or CALIBRATIONS_DIR)
    forecast_paths = _forecast_paths(source_forecasts)
    if not forecast_paths:
        return {
            "status": "blocked",
            "reason": "forecast_audits_missing",
        }
    audits = []
    for path in forecast_paths:
        audit = _read_object(path)
        validate_forecast_audit(audit)
        audits.append((path, audit))
    target_date = str(
        as_of_trade_date
        or max(str(audit["as_of_trade_date"]) for _, audit in audits)
    )
    try:
        datetime.strptime(target_date, "%Y%m%d")
    except ValueError as exc:
        raise StoreError("as_of_trade_date must be YYYYMMDD") from exc
    if decision_at is None:
        target_decisions = [
            str(audit["decision_at"])
            for _, audit in audits
            if str(audit["as_of_trade_date"]) == target_date
        ]
        if not target_decisions:
            return {
                "status": "blocked",
                "reason": "current_forecast_audit_missing",
                "as_of_trade_date": target_date,
            }
        decision_at = max(
            target_decisions,
            key=lambda value: _aware(value, "decision_at"),
        )
    cutoff = _aware(decision_at, "decision_at")
    visible = [
        (path, audit)
        for path, audit in audits
        if (
            str(audit["as_of_trade_date"]) <= target_date
            and _aware(audit["decision_at"], "forecast decision_at")
            <= cutoff
        )
    ]
    outcomes = read_jsonl_strict(
        Path(outcomes_path or GROUP_OUTCOMES_FILE)
    )
    outcomes_by_baseline = defaultdict(list)
    for outcome in outcomes:
        validate_group_outcome_sample(outcome)
        outcomes_by_baseline[
            str(outcome["as_of_trade_date"])
        ].append(outcome)
    candidate_results = []
    evaluations = []
    for _, forecast_audit in visible:
        baseline = str(forecast_audit["as_of_trade_date"])
        selection_path = source_selections / (
            f"selection_audit_{baseline}"
            f"__{forecast_audit['select_version']}.json"
        )
        if not selection_path.exists():
            raise StoreError(
                f"selection source is missing for forecast: {selection_path}"
            )
        selection_audit = _read_object(selection_path)
        validate_selection_audit(selection_audit)
        group_rows = _load_group_rows(paths, baseline)
        results, evaluation = evaluate_forecast_audit(
            forecast_audit=forecast_audit,
            selection_audit=selection_audit,
            group_factor_rows=group_rows,
            outcome_rows=outcomes_by_baseline.get(baseline, []),
        )
        candidate_results.extend(results)
        evaluations.append(evaluation)

    stored = _append_results(target_results, candidate_results)
    all_results = read_jsonl_strict(target_results)
    calibration = build_calibration_audit(
        forecast_audits=[audit for _, audit in visible],
        result_rows=all_results,
        as_of_trade_date=target_date,
        decision_at=cutoff.isoformat(timespec="seconds"),
        select_version=SELECT_VERSION,
        forecast_version=FORECAST_VERSION,
    )
    suffix = calibration["input_digest"][:12]
    basename = (
        f"forecast_calibration_{target_date}"
        f"__{SELECT_VERSION}__{FORECAST_VERSION}__{suffix}"
    )
    calibration_path = target_calibrations / f"{basename}.json"
    markdown_path = target_calibrations / f"{basename}.md"
    calibration_write = _write_calibration_pair(
        json_path=calibration_path,
        markdown_path=markdown_path,
        audit=calibration,
    )
    summary = {
        "forecast_audits": len(visible),
        "available_forecasts": sum(
            row["available_forecasts"] for row in evaluations
        ),
        "abstain_forecasts": sum(
            row["abstain_forecasts"] for row in evaluations
        ),
        "evaluated_forecasts": sum(
            row["evaluated_forecasts"] for row in evaluations
        ),
        "pending_forecasts": sum(
            row["pending_forecasts"] for row in evaluations
        ),
    }
    result = {
        "status": (
            "written"
            if stored["written"] or calibration_write == "written"
            else "already_complete"
        ),
        "as_of_trade_date": target_date,
        "decision_at": cutoff.isoformat(timespec="seconds"),
        "summary": summary,
        "stored": stored,
        "results_path": str(target_results),
        "calibration_status": calibration["status"],
        "calibration_write_status": calibration_write,
        "calibration_path": str(calibration_path),
        "calibration_markdown_path": str(markdown_path),
        "production_eligible": False,
    }
    logger.info("Research v2 forecast evaluation: %s", result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Research v2 forecast audits"
    )
    parser.add_argument("--research-dir", type=Path)
    parser.add_argument("--forecasts-dir", type=Path)
    parser.add_argument("--selections-dir", type=Path)
    parser.add_argument("--outcomes-path", type=Path)
    parser.add_argument("--results-path", type=Path)
    parser.add_argument("--calibrations-dir", type=Path)
    parser.add_argument("--trade-date")
    parser.add_argument("--decision-at")
    args = parser.parse_args(argv)
    paths = (
        default_store_paths(args.research_dir)
        if args.research_dir
        else None
    )
    result = run_forecast_evaluation_refresh(
        research_paths=paths,
        forecasts_dir=args.forecasts_dir,
        selections_dir=args.selections_dir,
        outcomes_path=args.outcomes_path,
        results_path=args.results_path,
        calibrations_dir=args.calibrations_dir,
        as_of_trade_date=args.trade_date,
        decision_at=args.decision_at,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in {
        "written",
        "already_complete",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
