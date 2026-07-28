# -*- coding: utf-8 -*-
"""Explicit orchestration for causal stock/track curve candidate features."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from vaxstock.research.causal_curve import (
    CURVE_FACTOR_VERSION,
    DEFAULT_PARAMETERS,
    TRACK_FACTOR_VERSION,
    build_causal_curve_run,
    is_curve_eligible,
)
from vaxstock.research.contracts import (
    ContractError,
    validate_atomic_observation,
    validate_factor_value,
)
from vaxstock.research.point_in_time_store import (
    StorePaths,
    append_run,
    append_runs,
    default_store_paths,
    read_jsonl_strict,
)


logger = logging.getLogger(__name__)
CHINA_TZ = timezone(timedelta(hours=8))


def _trade_date_arg(value: Optional[str], field: str) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ContractError(f"{field} must be YYYYMMDD") from exc
    return text


def _factor_partition_dates(paths: StorePaths, *, through: str) -> List[str]:
    if not paths.factors.exists():
        return []
    return sorted(
        path.stem
        for path in paths.factors.glob("*.jsonl")
        if len(path.stem) == 8 and path.stem.isdigit() and path.stem <= through
    )


def _load_curve_window(paths: StorePaths, *, through: str) -> List[Dict[str, Any]]:
    dates = _factor_partition_dates(paths, through=through)
    # One extra session lets a full-length previous curve state prove that it
    # is contiguous with the current session before the state rolls forward.
    selected = dates[-(DEFAULT_PARAMETERS.maximum_history + 1):]
    return [
        row
        for trade_date in selected
        for row in read_jsonl_strict(paths.factors / f"{trade_date}.jsonl")
    ]


def _load_membership_observations(paths: StorePaths) -> List[Dict[str, Any]]:
    return [
        row
        for row in read_jsonl_strict(paths.observations)
        if (
            row.get("entity_type") == "stock"
            and row.get("dimension") == "universe"
            and row.get("field") == "membership"
        )
    ]


def run_curve_refresh(
    *,
    as_of_trade_date: str,
    decision_at: Optional[str] = None,
    mode: str = "live",
    paths: Optional[StorePaths] = None,
) -> Dict[str, Any]:
    """Build and append one current-date curve run from already stored facts."""

    target_paths = paths or default_store_paths()
    calculated_at = decision_at or datetime.now(CHINA_TZ).isoformat(timespec="seconds")
    factors = _load_curve_window(target_paths, through=str(as_of_trade_date))
    observations = _load_membership_observations(target_paths)
    try:
        manifest, outputs, summary = build_causal_curve_run(
            as_of_trade_date=str(as_of_trade_date),
            calculated_at=calculated_at,
            factor_rows=factors,
            observations=observations,
            mode=mode,
        )
    except ContractError as exc:
        result = {
            "status": "blocked",
            "as_of_trade_date": str(as_of_trade_date),
            "reason": str(exc),
        }
        logger.info("Causal curve refresh: %s", result)
        return result

    stored = append_run(
        manifest,
        [],
        outputs,
        paths=target_paths,
    )
    result = {
        "status": stored["status"],
        "run_id": stored["run_id"],
        "summary": summary,
        "stored": stored,
    }
    logger.info("Causal curve refresh: %s", result)
    return result


def _latest_native_base_calculation(
    rows: Iterable[Dict[str, Any]],
    trade_date: str,
) -> Optional[datetime]:
    candidates: List[datetime] = []
    target = datetime.strptime(trade_date, "%Y%m%d").date()
    for row in rows:
        validate_factor_value(row)
        if str(row.get("as_of_trade_date") or "") != trade_date:
            continue
        if not is_curve_eligible(row):
            continue
        parsed = datetime.fromisoformat(
            str(row["calculated_at"]).replace("Z", "+00:00")
        )
        local_date = parsed.astimezone(CHINA_TZ).date()
        if local_date in {target, target + timedelta(days=1)}:
            candidates.append(parsed)
    return max(candidates) if candidates else None


def replay_curve_features(
    *,
    paths: Optional[StorePaths] = None,
    start_trade_date: Optional[str] = None,
    end_trade_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Sequentially replay available native factor dates without look-ahead."""

    target_paths = paths or default_store_paths()
    start = _trade_date_arg(start_trade_date, "start_trade_date")
    end = _trade_date_arg(end_trade_date, "end_trade_date")
    if start and end and start > end:
        raise ContractError("start_trade_date cannot be after end_trade_date")
    partition_dates = _factor_partition_dates(
        target_paths,
        through=end or "99991231",
    )
    all_factors = [
        row
        for trade_date in partition_dates
        for row in read_jsonl_strict(
            target_paths.factors / f"{trade_date}.jsonl"
        )
    ]
    base_factors = [row for row in all_factors if is_curve_eligible(row)]
    native_dates = sorted({
        str(row["as_of_trade_date"])
        for row in base_factors
    })
    dates = [
        value for value in native_dates
        if not start or value >= start
    ]
    observations = _load_membership_observations(target_paths)
    for row in observations:
        validate_atomic_observation(row)
    for row in all_factors:
        validate_factor_value(row)
    working_factors = [
        row
        for row in all_factors
        if (
            is_curve_eligible(row)
            or (
                row.get("dimension") == "track_aggregate"
                and str(row.get("factor_version") or "").startswith(
                    TRACK_FACTOR_VERSION
                )
            )
            or (
                row.get("dimension") == "causal_curve"
                and str(row.get("factor_version") or "").startswith(
                    CURVE_FACTOR_VERSION
                )
            )
        )
    ]
    totals = {
        "status": "complete",
        "trade_dates": 0,
        "runs_written": 0,
        "runs_already_complete": 0,
        "blocked": [],
        "factors_written": 0,
    }
    bundles = []
    for trade_date in dates:
        session_index = native_dates.index(trade_date)
        exact_rows = [
            row for row in base_factors
            if str(row.get("as_of_trade_date") or "") == trade_date
        ]
        latest = _latest_native_base_calculation(exact_rows, trade_date)
        if latest is None:
            totals["blocked"].append(
                {"trade_date": trade_date, "reason": "no_native_eligible_base_factors"}
            )
            continue
        history_dates = set(
            native_dates[
                max(0, session_index - DEFAULT_PARAMETERS.maximum_history):
                session_index + 1
            ]
        )
        inputs = [
            row for row in working_factors
            if str(row.get("as_of_trade_date") or "") in history_dates
        ]
        try:
            manifest, outputs, _ = build_causal_curve_run(
                as_of_trade_date=trade_date,
                calculated_at=(
                    latest + timedelta(seconds=1)
                ).isoformat(timespec="seconds"),
                factor_rows=inputs,
                observations=observations,
                mode="replay",
                _inputs_validated=True,
            )
        except ContractError as exc:
            totals["blocked"].append(
                {"trade_date": trade_date, "reason": str(exc)}
            )
            continue
        bundles.append((manifest, [], outputs))
        working_factors.extend(outputs)
        totals["trade_dates"] += 1
    if bundles:
        stored = append_runs(bundles, paths=target_paths)
        totals["runs_written"] = int(stored["manifests_written"])
        totals["runs_already_complete"] = (
            totals["trade_dates"] - totals["runs_written"]
        )
        totals["factors_written"] = int(stored["factors_written"])
    if not totals["trade_dates"]:
        totals["status"] = "blocked"
    elif totals["blocked"]:
        totals["status"] = "partial"
    return totals


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build causal curve candidates")
    parser.add_argument("--trade-date")
    parser.add_argument("--decision-at")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    paths = default_store_paths(args.output_dir) if args.output_dir else None
    if args.replay:
        result = replay_curve_features(
            paths=paths,
            start_trade_date=args.from_date,
            end_trade_date=args.to_date,
        )
    else:
        if not args.trade_date:
            parser.error("--trade-date is required unless --replay is used")
        result = run_curve_refresh(
            as_of_trade_date=args.trade_date,
            decision_at=args.decision_at,
            paths=paths,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in {"written", "already_complete", "complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
