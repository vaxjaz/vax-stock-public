# -*- coding: utf-8 -*-
"""Orchestration for label-free point-in-time research grouping."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from vaxstock.research.causal_curve import is_curve_eligible
from vaxstock.research.contextual_group import (
    GROUP_DIMENSION,
    build_contextual_group_run,
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


def _load_group_observations(paths: StorePaths) -> List[Dict[str, Any]]:
    return [
        row
        for row in read_jsonl_strict(paths.observations)
        if (
            (
                row.get("entity_type") == "stock"
                and row.get("dimension") == "universe"
                and row.get("field") == "membership"
            )
            or (
                row.get("entity_type") == "market"
                and row.get("dimension") == "market_context"
                and row.get("field") == "market_snapshot"
            )
        )
    ]


def _current_partition(paths: StorePaths, trade_date: str) -> List[Dict[str, Any]]:
    return read_jsonl_strict(paths.factors / f"{trade_date}.jsonl")


def run_group_refresh(
    *,
    as_of_trade_date: str,
    decision_at: Optional[str] = None,
    mode: str = "live",
    paths: Optional[StorePaths] = None,
) -> Dict[str, Any]:
    """Build and append one group run from already committed Research v2 facts."""

    target_paths = paths or default_store_paths()
    calculated_at = decision_at or datetime.now(CHINA_TZ).isoformat(
        timespec="seconds"
    )
    factors = _current_partition(target_paths, str(as_of_trade_date))
    observations = _load_group_observations(target_paths)
    try:
        manifest, outputs, summary = build_contextual_group_run(
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
        logger.info("Contextual group refresh: %s", result)
        return result
    stored = append_run(manifest, [], outputs, paths=target_paths)
    result = {
        "status": stored["status"],
        "run_id": stored["run_id"],
        "summary": summary,
        "stored": stored,
    }
    logger.info("Contextual group refresh: %s", result)
    return result


def replay_group_features(
    *,
    paths: Optional[StorePaths] = None,
    start_trade_date: Optional[str] = None,
    end_trade_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Replay label-free groups by trade date; retries are idempotent."""

    target_paths = paths or default_store_paths()
    start = _trade_date_arg(start_trade_date, "start_trade_date")
    end = _trade_date_arg(end_trade_date, "end_trade_date")
    if start and end and start > end:
        raise ContractError("start_trade_date cannot be after end_trade_date")
    dates = [
        trade_date
        for trade_date in _factor_partition_dates(
            target_paths, through=end or "99991231"
        )
        if not start or trade_date >= start
    ]
    all_factors = {
        trade_date: _current_partition(target_paths, trade_date)
        for trade_date in dates
    }
    observations = _load_group_observations(target_paths)
    for row in observations:
        validate_atomic_observation(row)
    for rows in all_factors.values():
        for row in rows:
            validate_factor_value(row)

    totals: Dict[str, Any] = {
        "status": "complete",
        "trade_dates": 0,
        "runs_written": 0,
        "runs_already_complete": 0,
        "blocked": [],
        "factors_written": 0,
        "label_usage": "none",
    }
    bundles = []
    for trade_date in dates:
        rows = all_factors[trade_date]
        native_base = [
            row for row in rows
            if (
                str(row.get("as_of_trade_date") or "") == trade_date
                and is_curve_eligible(row)
            )
        ]
        if not native_base:
            continue
        relevant = [
            row for row in rows
            if row.get("dimension") != GROUP_DIMENSION
        ]
        latest = max(
            datetime.fromisoformat(
                str(row["calculated_at"]).replace("Z", "+00:00")
            )
            for row in relevant
        )
        try:
            manifest, outputs, _ = build_contextual_group_run(
                as_of_trade_date=trade_date,
                calculated_at=(latest + timedelta(seconds=1)).isoformat(
                    timespec="seconds"
                ),
                factor_rows=relevant,
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
    parser = argparse.ArgumentParser(description="Build point-in-time groups")
    parser.add_argument("--trade-date")
    parser.add_argument("--decision-at")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    paths = default_store_paths(args.output_dir) if args.output_dir else None
    if args.replay:
        result = replay_group_features(
            paths=paths,
            start_trade_date=args.from_date,
            end_trade_date=args.to_date,
        )
    else:
        if not args.trade_date:
            parser.error("--trade-date is required unless --replay is used")
        result = run_group_refresh(
            as_of_trade_date=args.trade_date,
            decision_at=args.decision_at,
            paths=paths,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return (
        0
        if result.get("status")
        in {"written", "already_complete", "complete"}
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
