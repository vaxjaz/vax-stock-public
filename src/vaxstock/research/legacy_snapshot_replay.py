# -*- coding: utf-8 -*-
"""Normalize legacy wide factor snapshots into the v2 point-in-time store.

This is a compatibility bridge, not a semantic relabeling exercise.  Existing
metric names are preserved under ``dimension=legacy_snapshot`` until a source-
verified A..N registry assigns them a newer factor version.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from vaxstock import config
from vaxstock.research.contracts import (
    FACTOR_VALUE_SCHEMA_VERSION,
    OBSERVATION_SCHEMA_VERSION,
    RUN_MANIFEST_SCHEMA_VERSION,
    ContractError,
    canonical_digest,
    make_factor_value_id,
    make_observation_id,
    make_run_id,
)
from vaxstock.research.point_in_time_store import (
    StorePaths,
    append_run,
    append_runs,
    default_store_paths,
    read_jsonl_strict,
)


LEGACY_SNAPSHOT_SOURCE = "legacy.factor_snapshots"
LEGACY_SOURCE_REF = "var/eval/factor_snapshots.jsonl"
LEGACY_FEATURE_SET_VERSION = "legacy_snapshot_long_v1"
LEGACY_FACTOR_VERSION = "legacy_snapshot_v1"
NOT_EXECUTED = "not_executed"
CHINA_TZ = timezone(timedelta(hours=8))


def _trade_date(value: Any) -> str:
    text = str(value or "").strip()
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ContractError("legacy snapshot trade_date must be YYYYMMDD") from exc
    return text


def _capture_timestamp(value: Any) -> Tuple[str, bool]:
    """Return an aware system-capture timestamp and whether timezone was legacy."""

    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("legacy snapshot_ts must be ISO-8601") from exc
    inferred_timezone = parsed.tzinfo is None or parsed.utcoffset() is None
    if inferred_timezone:
        # eval_recorder._now_iso historically wrote a naive server-local stamp;
        # this deployment's configured trading timezone is Asia/Shanghai.
        parsed = parsed.replace(tzinfo=CHINA_TZ)
    return parsed.isoformat(timespec="seconds"), inferred_timezone


def _observation(
    *,
    entity_type: str,
    entity_id: str,
    dimension: str,
    field: str,
    value: Any,
    trade_date: str,
    captured_at: str,
    source_ref: str,
    revision_id: str,
) -> Dict[str, Any]:
    row = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "observation_id": "",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "dimension": dimension,
        "field": field,
        "value": value,
        "effective_date": trade_date,
        "available_at": captured_at,
        "retrieved_at": captured_at,
        "source": LEGACY_SNAPSHOT_SOURCE,
        "source_ref": source_ref,
        "revision_id": revision_id,
        "quality": "missing" if value is None else "observed",
    }
    row["observation_id"] = make_observation_id(row)
    return row


def _factor_from_observation(
    observation: Mapping[str, Any],
    *,
    factor_id: str,
    factor_version: str,
    value: Any,
) -> Dict[str, Any]:
    input_ids = [str(observation["observation_id"])]
    row = {
        "schema_version": FACTOR_VALUE_SCHEMA_VERSION,
        "factor_value_id": "",
        "entity_type": observation["entity_type"],
        "entity_id": observation["entity_id"],
        "dimension": observation["dimension"],
        "factor_id": factor_id,
        "factor_version": factor_version,
        "value": value,
        "as_of_trade_date": observation["effective_date"],
        "effective_date": observation["effective_date"],
        "available_at": observation["available_at"],
        "calculated_at": observation["retrieved_at"],
        "input_observation_ids": input_ids,
        "input_digest": canonical_digest(sorted(input_ids)),
        "quality": "missing" if value is None else "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def build_legacy_snapshot_run(
    snapshots: Iterable[Mapping[str, Any]],
    *,
    mode: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Build one deterministic run for one legacy snapshot trade date."""

    rows = [dict(row) for row in snapshots]
    if not rows:
        raise ContractError("legacy snapshot run requires at least one row")
    if mode not in {"live", "replay", "backtest"}:
        raise ContractError("mode must be live/replay/backtest")

    dates = {_trade_date(row.get("trade_date")) for row in rows}
    if len(dates) != 1:
        raise ContractError("one run cannot mix legacy snapshot trade dates")
    trade_date = next(iter(dates))

    by_code: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("code") or "").strip()
        if not code:
            raise ContractError("legacy snapshot code is required")
        previous = by_code.get(code)
        if previous is not None and canonical_digest(previous) != canonical_digest(row):
            raise ContractError(f"conflicting legacy snapshots for {trade_date}/{code}")
        by_code[code] = row
    ordered = [by_code[code] for code in sorted(by_code)]

    input_digest = canonical_digest(ordered)
    universe_codes = sorted(by_code)
    universe_id = f"user_universe_{canonical_digest(universe_codes)[:16]}"

    captures: Dict[str, str] = {}
    inferred_timezone = False
    for row in ordered:
        captured_at, inferred = _capture_timestamp(row.get("snapshot_ts"))
        captures[str(row["code"])] = captured_at
        inferred_timezone = inferred_timezone or inferred

    observations: List[Dict[str, Any]] = []
    factors: List[Dict[str, Any]] = []
    market_digests = {canonical_digest(row.get("market") or {}) for row in ordered}
    if len(market_digests) != 1:
        raise ContractError(f"legacy market context conflicts within {trade_date}")

    first = ordered[0]
    batch_capture = max(
        captures.values(),
        key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
    )
    market_revision = f"legacy_market_{next(iter(market_digests))}"
    observations.append(
        _observation(
            entity_type="market",
            entity_id="CN-A",
            dimension="market_context",
            field="market_snapshot",
            value=first.get("market") or {},
            trade_date=trade_date,
            captured_at=batch_capture,
            source_ref=f"{LEGACY_SOURCE_REF}#{trade_date}:market",
            revision_id=market_revision,
        )
    )

    for row in ordered:
        code = str(row["code"])
        captured_at = captures[code]
        revision_id = f"legacy_snapshot_{canonical_digest(row)}"
        base_ref = f"{LEGACY_SOURCE_REF}#{trade_date}:{code}"
        observations.append(
            _observation(
                entity_type="stock",
                entity_id=code,
                dimension="universe",
                field="membership",
                value={
                    "name": row.get("name"),
                    "group": row.get("group"),
                    "concepts": row.get("concepts") or [],
                },
                trade_date=trade_date,
                captured_at=captured_at,
                source_ref=f"{base_ref}:membership",
                revision_id=revision_id,
            )
        )

        price_observation = _observation(
            entity_type="stock",
            entity_id=code,
            dimension="market_data",
            field="price_at_snapshot",
            value=row.get("price_at_snapshot"),
            trade_date=trade_date,
            captured_at=captured_at,
            source_ref=f"{base_ref}:price_at_snapshot",
            revision_id=revision_id,
        )
        observations.append(price_observation)

        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            raise ContractError(f"legacy snapshot metrics must be an object: {trade_date}/{code}")
        metrics_observation = _observation(
            entity_type="stock",
            entity_id=code,
            dimension="legacy_snapshot",
            field="metrics",
            value=metrics,
            trade_date=trade_date,
            captured_at=captured_at,
            source_ref=f"{base_ref}:metrics",
            revision_id=revision_id,
        )
        observations.append(metrics_observation)
        for metric_name in sorted(metrics):
            factors.append(
                _factor_from_observation(
                    metrics_observation,
                    factor_id=f"legacy.{metric_name}",
                    factor_version=LEGACY_FACTOR_VERSION,
                    value=metrics[metric_name],
                )
            )

    generated_at = batch_capture
    manifest = {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": "",
        "mode": mode,
        "as_of_trade_date": trade_date,
        "universe_id": universe_id,
        "feature_set_version": LEGACY_FEATURE_SET_VERSION,
        "group_version": NOT_EXECUTED,
        "select_version": NOT_EXECUTED,
        "forecast_version": NOT_EXECUTED,
        "input_digest": input_digest,
        "generated_at": generated_at,
        "notes": [
            "snapshot_ingestion_only; group/select/forecast were not executed",
            "legacy metric names and values preserved; A..N semantics were not inferred",
            (
                "legacy naive snapshot_ts interpreted as Asia/Shanghai system-capture time"
                if inferred_timezone
                else "legacy snapshot_ts already included timezone"
            ),
        ],
        "stage": "snapshot_ingestion",
        "source_refs": [LEGACY_SOURCE_REF],
        "observation_count": len(observations),
        "factor_value_count": len(factors),
        "observation_digest": canonical_digest(
            sorted(row["observation_id"] for row in observations)
        ),
        "factor_value_digest": canonical_digest(
            sorted(row["factor_value_id"] for row in factors)
        ),
    }
    manifest["run_id"] = make_run_id(manifest)
    return manifest, observations, factors


def record_legacy_snapshot_trade_date(
    trade_date: str,
    *,
    mode: str = "live",
    snapshots_path: Optional[Path] = None,
    paths: Optional[StorePaths] = None,
) -> Dict[str, Any]:
    """Normalize and append one trade date from the legacy compatibility file."""

    td = _trade_date(trade_date)
    source_path = Path(snapshots_path or (config.STATE_DIR / "eval" / "factor_snapshots.jsonl"))
    selected = [
        row for row in read_jsonl_strict(source_path)
        if str(row.get("trade_date") or "").strip() == td
    ]
    if not selected:
        return {
            "status": "blocked",
            "trade_date": td,
            "reason": "legacy_snapshot_missing",
            "observations_written": 0,
            "factors_written": 0,
            "manifests_written": 0,
        }
    manifest, observations, factors = build_legacy_snapshot_run(selected, mode=mode)
    result = append_run(
        manifest,
        observations,
        factors,
        paths=paths or default_store_paths(),
    )
    result["trade_date"] = td
    return result


def replay_legacy_snapshots(
    *,
    snapshots_path: Optional[Path] = None,
    paths: Optional[StorePaths] = None,
    start_trade_date: Optional[str] = None,
    end_trade_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Replay legacy history into v2; retries are idempotent."""

    start = _trade_date(start_trade_date) if start_trade_date else None
    end = _trade_date(end_trade_date) if end_trade_date else None
    if start and end and start > end:
        raise ContractError("start_trade_date cannot be after end_trade_date")

    source_path = Path(snapshots_path or (config.STATE_DIR / "eval" / "factor_snapshots.jsonl"))
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in read_jsonl_strict(source_path):
        td = _trade_date(row.get("trade_date"))
        if start and td < start:
            continue
        if end and td > end:
            continue
        grouped[td].append(row)

    totals = {
        "status": "complete",
        "trade_dates": 0,
        "runs_written": 0,
        "runs_already_complete": 0,
        "observations_written": 0,
        "factors_written": 0,
    }
    if not grouped:
        totals["status"] = "blocked"
        totals["reason"] = "no_legacy_snapshots_in_range"
        return totals

    bundles = [
        build_legacy_snapshot_run(grouped[td], mode="replay")
        for td in sorted(grouped)
    ]
    result = append_runs(bundles, paths=paths or default_store_paths())
    totals["trade_dates"] = len(grouped)
    totals["runs_written"] = result["manifests_written"]
    totals["runs_already_complete"] = len(grouped) - result["manifests_written"]
    totals["observations_written"] = result["observations_written"]
    totals["factors_written"] = result["factors_written"]
    return totals


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay legacy snapshots into research v2")
    parser.add_argument("--snapshots", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--from-date", dest="start_trade_date")
    parser.add_argument("--to-date", dest="end_trade_date")
    args = parser.parse_args(argv)
    result = replay_legacy_snapshots(
        snapshots_path=args.snapshots,
        paths=default_store_paths(args.output_dir) if args.output_dir else None,
        start_trade_date=args.start_trade_date,
        end_trade_date=args.end_trade_date,
    )
    print(result)
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
