# -*- coding: utf-8 -*-
"""Append-only storage for point-in-time observations, factors, and runs.

The legacy ``var/eval/factor_snapshots.jsonl`` files remain untouched.  This
module is the normalized v2 store used by replay and future factor versions.
All writes are explicit; importing the module performs no filesystem or
network I/O.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from vaxstock import config
from vaxstock.research.contracts import (
    ContractError,
    assert_available_as_of,
    assert_factor_available_as_of,
    canonical_digest,
    validate_atomic_observation,
    validate_factor_value,
    validate_run_manifest,
)


class StoreError(RuntimeError):
    """Raised when the append-only store is corrupt or internally inconsistent."""


@dataclass(frozen=True)
class StorePaths:
    observations: Path
    factors: Path
    manifests: Path


def default_store_paths(root: Optional[Path] = None) -> StorePaths:
    base = Path(root) if root is not None else config.STATE_DIR / "research"
    return StorePaths(
        observations=base / "observations.jsonl",
        factors=base / "factor_values",
        manifests=base / "run_manifests.jsonl",
    )


def read_jsonl_strict(path: Path) -> List[Dict[str, Any]]:
    """Read JSONL without silently discarding malformed research evidence."""

    path = Path(path)
    if not path.exists():
        return []
    if path.is_dir():
        rows: List[Dict[str, Any]] = []
        for child in sorted(path.glob("*.jsonl")):
            rows.extend(read_jsonl_strict(child))
        return rows
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise StoreError(f"{path}:{line_number}: invalid JSONL") from exc
            if not isinstance(row, dict):
                raise StoreError(f"{path}:{line_number}: JSONL row must be an object")
            rows.append(row)
    return rows


def _append_rows(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    materialized = [
        json.dumps(
            dict(row),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
        for row in rows
    ]
    if not materialized:
        return 0
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.writelines(materialized)
        handle.flush()
        os.fsync(handle.fileno())
    return len(materialized)


def factor_partition_path(paths: StorePaths, as_of_trade_date: str) -> Path:
    text = str(as_of_trade_date or "").strip()
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ContractError("as_of_trade_date must be YYYYMMDD") from exc
    return paths.factors / f"{text}.jsonl"


@contextmanager
def _exclusive_store_lock(paths: StorePaths):
    """Serialize writers across EOD, replay, and manual backfill processes."""

    lock_path = paths.manifests.parent / ".write.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
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
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _append_factor_rows(paths: StorePaths, rows: Iterable[Mapping[str, Any]]) -> int:
    by_date: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        trade_date = str(row.get("as_of_trade_date") or "").strip()
        by_date.setdefault(trade_date, []).append(row)
    return sum(
        _append_rows(factor_partition_path(paths, trade_date), by_date[trade_date])
        for trade_date in sorted(by_date)
    )


def _semantic_digest(row: Mapping[str, Any], *, volatile_fields=()) -> str:
    stable = {key: value for key, value in row.items() if key not in volatile_fields}
    return canonical_digest(stable)


def _deduplicate_new_rows(
    *,
    existing: Iterable[Mapping[str, Any]],
    incoming: Iterable[Mapping[str, Any]],
    id_field: str,
    volatile_fields=(),
) -> List[Dict[str, Any]]:
    known: Dict[str, Mapping[str, Any]] = {}
    for row in existing:
        identity = str(row.get(id_field) or "").strip()
        if not identity:
            raise StoreError(f"stored row missing {id_field}")
        previous = known.get(identity)
        if previous is not None and _semantic_digest(
            previous, volatile_fields=volatile_fields
        ) != _semantic_digest(row, volatile_fields=volatile_fields):
            raise StoreError(f"stored {id_field} conflict: {identity}")
        known[identity] = row

    new_rows: List[Dict[str, Any]] = []
    for raw in incoming:
        row = dict(raw)
        identity = str(row.get(id_field) or "").strip()
        if not identity:
            raise ContractError(f"{id_field} is required")
        previous = known.get(identity)
        if previous is not None:
            if _semantic_digest(
                previous, volatile_fields=volatile_fields
            ) != _semantic_digest(row, volatile_fields=volatile_fields):
                raise StoreError(
                    f"{id_field}={identity} changed without a new revision/version"
                )
            continue
        known[identity] = row
        new_rows.append(row)
    return new_rows


def append_run(
    manifest: Mapping[str, Any],
    observations: Iterable[Mapping[str, Any]],
    factors: Iterable[Mapping[str, Any]],
    *,
    paths: Optional[StorePaths] = None,
) -> Dict[str, Any]:
    """Append one idempotent run, committing its manifest last.

    A retry can safely fill observations/factors left by an interrupted prior
    attempt.  The manifest is the completion marker and is appended only after
    all referenced inputs pass validation.
    """

    manifest_row = dict(manifest)
    result = append_runs(
        [(manifest_row, observations, factors)],
        paths=paths,
    )
    written_manifests = result["manifests_written"]
    return {
        "status": "written" if written_manifests else "already_complete",
        "run_id": manifest_row["run_id"],
        "observations_written": result["observations_written"],
        "factors_written": result["factors_written"],
        "manifests_written": written_manifests,
    }


def append_runs(
    runs: Iterable[
        tuple[
            Mapping[str, Any],
            Iterable[Mapping[str, Any]],
            Iterable[Mapping[str, Any]],
        ]
    ],
    *,
    paths: Optional[StorePaths] = None,
) -> Dict[str, Any]:
    """Serialize, validate, and append multiple replay runs in one store scan."""

    paths = paths or default_store_paths()
    with _exclusive_store_lock(paths):
        return _append_runs_locked(runs, paths=paths)


def _append_runs_locked(
    runs: Iterable[
        tuple[
            Mapping[str, Any],
            Iterable[Mapping[str, Any]],
            Iterable[Mapping[str, Any]],
        ]
    ],
    *,
    paths: StorePaths,
) -> Dict[str, Any]:
    manifest_rows: List[Dict[str, Any]] = []
    observation_rows: List[Dict[str, Any]] = []
    factor_rows: List[Dict[str, Any]] = []
    for manifest, observations, factors in runs:
        manifest_row = dict(manifest)
        run_observations = [dict(row) for row in observations]
        run_factors = [dict(row) for row in factors]
        validate_run_manifest(manifest_row)
        for row in run_observations:
            validate_atomic_observation(row)
        for row in run_factors:
            validate_factor_value(row)
            if row["as_of_trade_date"] != manifest_row["as_of_trade_date"]:
                raise ContractError(
                    "factor as_of_trade_date must match its run manifest"
                )
        expected_observation_count = manifest_row.get("observation_count")
        if (
            expected_observation_count is not None
            and expected_observation_count != len(run_observations)
        ):
            raise ContractError("manifest observation_count does not match outputs")
        expected_factor_count = manifest_row.get("factor_value_count")
        if expected_factor_count is not None and expected_factor_count != len(run_factors):
            raise ContractError("manifest factor_value_count does not match outputs")
        expected_observation_digest = manifest_row.get("observation_digest")
        actual_observation_digest = canonical_digest(
            sorted(row["observation_id"] for row in run_observations)
        )
        if (
            expected_observation_digest is not None
            and expected_observation_digest != actual_observation_digest
        ):
            raise ContractError("manifest observation_digest does not match outputs")
        expected_factor_digest = manifest_row.get("factor_value_digest")
        actual_factor_digest = canonical_digest(
            sorted(row["factor_value_id"] for row in run_factors)
        )
        if (
            expected_factor_digest is not None
            and expected_factor_digest != actual_factor_digest
        ):
            raise ContractError("manifest factor_value_digest does not match outputs")
        manifest_rows.append(manifest_row)
        observation_rows.extend(run_observations)
        factor_rows.extend(run_factors)

    existing_observations = read_jsonl_strict(paths.observations)
    factor_dates = sorted(
        {str(row.get("as_of_trade_date") or "").strip() for row in factor_rows}
    )
    existing_factors = [
        row
        for trade_date in factor_dates
        for row in read_jsonl_strict(factor_partition_path(paths, trade_date))
    ]
    existing_manifests = read_jsonl_strict(paths.manifests)
    for row in existing_observations:
        validate_atomic_observation(row)
    for row in existing_factors:
        validate_factor_value(row)
    for row in existing_manifests:
        validate_run_manifest(row)

    new_observations = _deduplicate_new_rows(
        existing=existing_observations,
        incoming=observation_rows,
        id_field="observation_id",
        volatile_fields=("retrieved_at",),
    )
    known_observation_ids = {
        str(row["observation_id"])
        for row in [*existing_observations, *new_observations]
    }
    for factor in factor_rows:
        missing_inputs = sorted(
            set(factor["input_observation_ids"]) - known_observation_ids
        )
        if missing_inputs:
            raise StoreError(
                f"factor {factor['factor_value_id']} references unknown observations: "
                f"{missing_inputs[:3]}"
            )

    new_factors = _deduplicate_new_rows(
        existing=existing_factors,
        incoming=factor_rows,
        id_field="factor_value_id",
        volatile_fields=("calculated_at",),
    )
    new_manifests = _deduplicate_new_rows(
        existing=existing_manifests,
        incoming=manifest_rows,
        id_field="run_id",
        volatile_fields=("generated_at",),
    )

    # Manifests are completion markers and therefore always commit last.
    written_observations = _append_rows(paths.observations, new_observations)
    written_factors = _append_factor_rows(paths, new_factors)
    written_manifests = _append_rows(paths.manifests, new_manifests)
    return {
        "observations_written": written_observations,
        "factors_written": written_factors,
        "manifests_written": written_manifests,
        "run_ids": [row["run_id"] for row in manifest_rows],
        "new_run_ids": [row["run_id"] for row in new_manifests],
    }


def factor_values_as_of(
    as_of_trade_date: str,
    decision_at: str,
    *,
    paths: Optional[StorePaths] = None,
    entity_ids: Optional[Iterable[str]] = None,
    factor_versions: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """Return only factor rows that were legally available at ``decision_at``."""

    paths = paths or default_store_paths()
    entities = set(entity_ids or [])
    versions = set(factor_versions or [])
    rows: List[Dict[str, Any]] = []
    for row in read_jsonl_strict(factor_partition_path(paths, str(as_of_trade_date))):
        validate_factor_value(row)
        if str(row.get("as_of_trade_date")) != str(as_of_trade_date):
            continue
        if entities and row.get("entity_id") not in entities:
            continue
        if versions and row.get("factor_version") not in versions:
            continue
        try:
            assert_factor_available_as_of(row, decision_at)
        except ContractError as exc:
            if "look-ahead" in str(exc):
                continue
            raise
        rows.append(row)
    return rows


def observations_as_of(
    decision_at: str,
    *,
    paths: Optional[StorePaths] = None,
    entity_ids: Optional[Iterable[str]] = None,
    dimensions: Optional[Iterable[str]] = None,
    sources: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """Return source facts legally available at a simulated decision time."""

    paths = paths or default_store_paths()
    entities = set(entity_ids or [])
    dimension_set = set(dimensions or [])
    source_set = set(sources or [])
    rows: List[Dict[str, Any]] = []
    for row in read_jsonl_strict(paths.observations):
        validate_atomic_observation(row)
        if entities and row.get("entity_id") not in entities:
            continue
        if dimension_set and row.get("dimension") not in dimension_set:
            continue
        if source_set and row.get("source") not in source_set:
            continue
        try:
            assert_available_as_of(row, decision_at)
        except ContractError as exc:
            if "look-ahead" in str(exc):
                continue
            raise
        rows.append(row)
    return rows
