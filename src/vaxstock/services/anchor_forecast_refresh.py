# -*- coding: utf-8 -*-
"""Materialize the research-only AI external-anchor probability forecast."""

from __future__ import annotations

import argparse
import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from vaxstock import config
from vaxstock.research.anchor_trend_forecast import (
    DEFAULT_HORIZONS,
    FORECAST_VERSION,
    build_anchor_trend_forecast,
)
from vaxstock.research.global_anchor_dimension import (
    ANCHOR_CONTEXT_FACTOR_ID,
    ANCHOR_CONTEXT_FACTOR_VERSION,
    DIMENSION as GLOBAL_ANCHOR_DIMENSION,
)
from vaxstock.research.point_in_time_store import (
    StoreError,
    StorePaths,
    default_store_paths,
    read_jsonl_strict,
)
from vaxstock.services.eval_recorder import RESULTS_FILE, SNAPSHOTS_FILE


logger = logging.getLogger(__name__)
ANCHOR_FORECASTS_DIR = (
    config.STATE_DIR / "research" / "anchor_forecasts"
)


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


def _write_immutable(path: Path, audit: Mapping[str, Any]) -> str:
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
    target = Path(path)
    with _exclusive_target_lock(target):
        if target.exists():
            current = target.read_text(encoding="utf-8")
            try:
                stored = json.loads(current)
            except json.JSONDecodeError as exc:
                raise StoreError(
                    f"invalid anchor forecast audit: {target}"
                ) from exc
            if not isinstance(stored, dict):
                raise StoreError(
                    f"anchor forecast root must be an object: {target}"
                )
            if current != payload:
                raise StoreError(
                    f"anchor forecast changed for immutable target: {target}"
                )
            return "already_complete"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    return "written"


def _anchor_factor_rows(
    paths: StorePaths,
    *,
    through: str,
) -> list[Dict[str, Any]]:
    rows = []
    if not paths.factors.exists():
        return rows
    for partition in sorted(paths.factors.glob("*.jsonl")):
        if (
            len(partition.stem) != 8
            or not partition.stem.isdigit()
            or partition.stem > through
        ):
            continue
        rows.extend(
            row
            for row in read_jsonl_strict(partition)
            if (
                row.get("dimension") == GLOBAL_ANCHOR_DIMENSION
                and row.get("factor_id") == ANCHOR_CONTEXT_FACTOR_ID
                and row.get("factor_version")
                == ANCHOR_CONTEXT_FACTOR_VERSION
            )
        )
    return rows


def _stable_decision_at(
    anchor_rows: Sequence[Mapping[str, Any]],
    *,
    as_of_trade_date: str,
) -> Optional[str]:
    """Use the frozen current-date factor timestamp, never the rerun wall clock."""

    candidates = [
        str(row.get("calculated_at") or "").strip()
        for row in anchor_rows
        if (
            str(row.get("as_of_trade_date") or "") == as_of_trade_date
            and str(row.get("calculated_at") or "").strip()
        )
    ]
    return max(candidates) if candidates else None


def run_anchor_forecast_refresh(
    *,
    as_of_trade_date: str,
    decision_at: Optional[str] = None,
    research_paths: Optional[StorePaths] = None,
    snapshots_path: Optional[Path] = None,
    results_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> Dict[str, Any]:
    """Build and freeze one current-date anchor probability estimate."""

    paths = research_paths or default_store_paths()
    anchor_rows = _anchor_factor_rows(
        paths,
        through=str(as_of_trade_date),
    )
    snapshots = read_jsonl_strict(
        Path(snapshots_path or SNAPSHOTS_FILE)
    )
    results = read_jsonl_strict(
        Path(results_path or RESULTS_FILE)
    )
    if not anchor_rows:
        return {
            "status": "blocked",
            "reason": "global_anchor_factors_empty",
            "as_of_trade_date": str(as_of_trade_date),
        }
    calculated_at = decision_at or _stable_decision_at(
        anchor_rows,
        as_of_trade_date=str(as_of_trade_date),
    )
    if calculated_at is None:
        return {
            "status": "blocked",
            "reason": "current_global_anchor_factor_missing",
            "as_of_trade_date": str(as_of_trade_date),
        }
    if not snapshots or not results:
        return {
            "status": "blocked",
            "reason": "legacy_outcome_inputs_empty",
            "as_of_trade_date": str(as_of_trade_date),
        }
    audit = build_anchor_trend_forecast(
        as_of_trade_date=str(as_of_trade_date),
        decision_at=calculated_at,
        anchor_factor_rows=anchor_rows,
        snapshots=snapshots,
        factor_result_rows=results,
        horizons=horizons,
    )
    target_dir = Path(output_dir or ANCHOR_FORECASTS_DIR)
    target = target_dir / (
        f"anchor_trend_forecast_{audit['as_of_trade_date']}"
        f"__{FORECAST_VERSION}.json"
    )
    write_status = _write_immutable(target, audit)
    available = sum(
        row.get("status") == "estimated"
        for row in audit["horizons"].values()
    )
    result = {
        "status": "estimated" if available else "abstain",
        "write_status": write_status,
        "as_of_trade_date": audit["as_of_trade_date"],
        "audit_path": str(target),
        "horizons": audit["horizons"],
        "production_eligible": False,
    }
    logger.info("Anchor trend forecast: %s", result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build AI external-anchor probability forecast"
    )
    parser.add_argument("--research-dir", type=Path)
    parser.add_argument("--snapshots", type=Path)
    parser.add_argument("--results", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--decision-at")
    args = parser.parse_args(argv)
    result = run_anchor_forecast_refresh(
        as_of_trade_date=args.trade_date,
        decision_at=args.decision_at,
        research_paths=(
            default_store_paths(args.research_dir)
            if args.research_dir
            else None
        ),
        snapshots_path=args.snapshots,
        results_path=args.results,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in {"estimated", "abstain"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
