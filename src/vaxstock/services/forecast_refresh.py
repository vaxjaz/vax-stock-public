# -*- coding: utf-8 -*-
"""Materialize immutable MR7 conditional forecast audits."""

from __future__ import annotations

import argparse
import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from vaxstock import config
from vaxstock.research.conditional_forecast import build_forecast_audit
from vaxstock.research.conditional_forecast import FORECAST_VERSION
from vaxstock.research.contracts import (
    validate_forecast_audit,
    validate_selection_audit,
)
from vaxstock.research.point_in_time_store import StoreError
from vaxstock.services.select_refresh import SELECTIONS_DIR
from vaxstock.research.walk_forward_select import SELECT_VERSION


logger = logging.getLogger(__name__)
FORECASTS_DIR = config.STATE_DIR / "research" / "forecasts"


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


def _read_object(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StoreError(f"invalid JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise StoreError(f"JSON root must be an object: {path}")
    return value


def _write_immutable_audit(path: Path, audit: Mapping[str, Any]) -> str:
    validate_forecast_audit(audit)
    target = Path(path)
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
            stored = _read_object(target)
            validate_forecast_audit(stored)
            if target.read_text(encoding="utf-8") != payload:
                raise StoreError(
                    f"forecast audit changed for immutable target: {target}"
                )
            return "already_complete"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    return "written"


def _resolve_selection_path(
    *,
    selections_dir: Path,
    as_of_trade_date: Optional[str],
    selection_path: Optional[Path],
) -> Optional[Path]:
    if selection_path is not None:
        return Path(selection_path)
    if as_of_trade_date:
        return (
            Path(selections_dir)
            / (
                f"selection_audit_{as_of_trade_date}"
                f"__{SELECT_VERSION}.json"
            )
        )
    candidates = sorted(
        Path(selections_dir).glob(
            f"selection_audit_????????__{SELECT_VERSION}.json"
        )
    )
    return candidates[-1] if candidates else None


def run_forecast_refresh(
    *,
    selections_dir: Optional[Path] = None,
    forecasts_dir: Optional[Path] = None,
    as_of_trade_date: Optional[str] = None,
    selection_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build the forecast matching one immutable selection decision."""

    source_dir = Path(selections_dir or SELECTIONS_DIR)
    selection_path = _resolve_selection_path(
        selections_dir=source_dir,
        as_of_trade_date=as_of_trade_date,
        selection_path=selection_path,
    )
    if selection_path is None or not selection_path.exists():
        return {
            "status": "blocked",
            "reason": "selection_audit_missing",
            "as_of_trade_date": as_of_trade_date,
        }
    selection_audit = _read_object(selection_path)
    validate_selection_audit(selection_audit)
    if (
        as_of_trade_date
        and str(selection_audit["as_of_trade_date"]) != str(as_of_trade_date)
    ):
        raise StoreError(
            "selection audit trade date does not match requested trade date"
        )
    audit = build_forecast_audit(selection_audit)
    target_date = str(audit["as_of_trade_date"])
    target_dir = Path(forecasts_dir or FORECASTS_DIR)
    target = target_dir / (
        f"forecast_audit_{target_date}"
        f"__{audit['select_version']}__{FORECAST_VERSION}.json"
    )
    write_status = _write_immutable_audit(target, audit)
    status = (
        "shadow_available"
        if audit["status_counts"].get("available")
        else "abstain"
    )
    result = {
        "status": status,
        "write_status": write_status,
        "as_of_trade_date": target_date,
        "selection_path": str(selection_path),
        "audit_path": str(target),
        "status_counts": audit["status_counts"],
        "production_eligible": False,
    }
    logger.info("Research v2 forecast audit: %s", result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build immutable conditional forecast audit"
    )
    parser.add_argument("--selections-dir", type=Path)
    parser.add_argument("--forecasts-dir", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--trade-date")
    args = parser.parse_args(argv)
    result = run_forecast_refresh(
        selections_dir=args.selections_dir,
        forecasts_dir=args.forecasts_dir,
        as_of_trade_date=args.trade_date,
        selection_path=args.selection,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return (
        0
        if result.get("status") in {"abstain", "shadow_available"}
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
