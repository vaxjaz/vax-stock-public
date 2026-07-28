# -*- coding: utf-8 -*-
"""Materialize strict MR5-group / legacy-outcome joins for MR6 research."""

from __future__ import annotations

import argparse
import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from vaxstock import config
from vaxstock.research.contextual_group import (
    GROUP_DIMENSION,
    STOCK_GROUP_FACTOR_ID,
)
from vaxstock.research.contracts import (
    ContractError,
    canonical_digest,
    validate_group_outcome_sample,
)
from vaxstock.research.group_outcome import build_group_outcome_samples
from vaxstock.research.point_in_time_store import (
    StoreError,
    StorePaths,
    default_store_paths,
    read_jsonl_strict,
)
from vaxstock.services.eval_recorder import RESULTS_FILE


logger = logging.getLogger(__name__)
OUTCOMES_DIR = config.STATE_DIR / "research" / "outcomes"
GROUP_OUTCOMES_FILE = OUTCOMES_DIR / "group_outcomes.jsonl"


def _stable_digest(row: Mapping[str, Any]) -> str:
    return canonical_digest(dict(row))


@contextmanager
def _exclusive_append_lock(path: Path):
    """Serialize manual replay and EOD appenders for one outcome ledger."""

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


def _append_new_samples(
    path: Path,
    samples: Iterable[Mapping[str, Any]],
) -> Dict[str, int]:
    target = Path(path)
    with _exclusive_append_lock(target):
        existing_rows = read_jsonl_strict(target)
        existing = {}
        for row in existing_rows:
            validate_group_outcome_sample(row)
            identity = str(row["outcome_id"])
            previous = existing.get(identity)
            if (
                previous is not None
                and _stable_digest(previous) != _stable_digest(row)
            ):
                raise StoreError(f"stored group outcome conflict: {identity}")
            existing[identity] = row

        new_rows: List[Dict[str, Any]] = []
        skipped = 0
        for raw in samples:
            row = dict(raw)
            validate_group_outcome_sample(row)
            identity = str(row["outcome_id"])
            previous = existing.get(identity)
            if previous is not None:
                if _stable_digest(previous) != _stable_digest(row):
                    raise StoreError(
                        "group outcome changed without a new identity: "
                        f"{identity}"
                    )
                skipped += 1
                continue
            existing[identity] = row
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


def _result_trade_dates(rows: Iterable[Mapping[str, Any]]) -> List[str]:
    return sorted({
        str(row.get("trade_date") or "").strip()
        for row in rows
        if len(str(row.get("trade_date") or "").strip()) == 8
        and str(row.get("trade_date") or "").strip().isdigit()
    })


def _load_group_factors(
    *,
    paths: StorePaths,
    trade_dates: Iterable[str],
) -> List[Dict[str, Any]]:
    rows = []
    for trade_date in sorted(set(trade_dates)):
        partition = paths.factors / f"{trade_date}.jsonl"
        rows.extend(
            row
            for row in read_jsonl_strict(partition)
            if (
                row.get("dimension") == GROUP_DIMENSION
                and row.get("factor_id") == STOCK_GROUP_FACTOR_ID
            )
        )
    return rows


def run_group_outcome_refresh(
    *,
    research_paths: Optional[StorePaths] = None,
    factor_results_path: Optional[Path] = None,
    samples_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Join every currently mature horizon and append only unseen samples."""

    paths = research_paths or default_store_paths()
    result_path = Path(factor_results_path or RESULTS_FILE)
    target_path = Path(samples_path or GROUP_OUTCOMES_FILE)
    factor_results = read_jsonl_strict(result_path)
    if not factor_results:
        return {
            "status": "blocked",
            "reason": "factor_results_empty",
            "samples_path": str(target_path),
        }
    group_factors = _load_group_factors(
        paths=paths,
        trade_dates=_result_trade_dates(factor_results),
    )
    samples, summary = build_group_outcome_samples(
        group_factor_rows=group_factors,
        factor_result_rows=factor_results,
    )
    stored = _append_new_samples(target_path, samples)
    status = summary["status"]
    if status == "complete":
        status = "written" if stored["written"] else "already_complete"
    result = {
        "status": status,
        "samples_path": str(target_path),
        "summary": summary,
        "stored": stored,
    }
    logger.info("Group outcome refresh: %s", result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Materialize MR5 group / mature outcome joins"
    )
    parser.add_argument("--research-dir", type=Path)
    parser.add_argument("--factor-results", type=Path)
    parser.add_argument("--samples-path", type=Path)
    args = parser.parse_args(argv)
    paths = (
        default_store_paths(args.research_dir)
        if args.research_dir
        else None
    )
    result = run_group_outcome_refresh(
        research_paths=paths,
        factor_results_path=args.factor_results,
        samples_path=args.samples_path,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return (
        0
        if result.get("status") in {"written", "already_complete"}
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
