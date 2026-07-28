# -*- coding: utf-8 -*-

import copy
import json
from pathlib import Path

import pytest

from vaxstock.research.contracts import (
    canonical_digest,
    factor_input_digest,
    make_factor_value_id,
    make_run_id,
)
from vaxstock.research.legacy_snapshot_replay import (
    LEGACY_FACTOR_VERSION,
    build_legacy_snapshot_run,
    replay_legacy_snapshots,
)
from vaxstock.research.point_in_time_store import (
    StoreError,
    append_run,
    default_store_paths,
    factor_partition_path,
    factor_values_as_of,
    observations_as_of,
    read_jsonl_strict,
)


def _snapshots():
    market = {
        "regime": "momentum",
        "breadth": {"up_count": 3100, "down_count": 1700},
        "index_snapshot": {"上证指数": {"close": 3500.0, "change_pct": 0.8}},
    }
    return [
        {
            "schema_version": 1,
            "snapshot_ts": "2026-06-26T05:10:00",
            "trade_date": "20260625",
            "code": "002475",
            "name": "立讯精密",
            "group": "holding",
            "concepts": ["消费电子"],
            "price_at_snapshot": 35.0,
            "metrics": {"ma5": 34.0, "rsi_14": 60.0, "missing_metric": None},
            "market": market,
        },
        {
            "schema_version": 1,
            "snapshot_ts": "2026-06-26T05:10:00+08:00",
            "trade_date": "20260625",
            "code": "601138",
            "name": "工业富联",
            "group": "holding",
            "concepts": ["AI算力"],
            "price_at_snapshot": 61.0,
            "metrics": {"ma5": 60.3, "rsi_14": 48.0},
            "market": market,
        },
    ]


def _write_jsonl(path: Path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_legacy_replay_is_long_form_idempotent_and_does_not_touch_source(tmp_path):
    snapshots_path = tmp_path / "factor_snapshots.jsonl"
    _write_jsonl(snapshots_path, _snapshots())
    before = snapshots_path.read_bytes()
    paths = default_store_paths(tmp_path / "research")

    first = replay_legacy_snapshots(snapshots_path=snapshots_path, paths=paths)
    second = replay_legacy_snapshots(snapshots_path=snapshots_path, paths=paths)

    assert first["trade_dates"] == 1
    assert first["runs_written"] == 1
    assert first["observations_written"] > first["factors_written"] == 5
    assert second == {
        "status": "complete",
        "trade_dates": 1,
        "runs_written": 0,
        "runs_already_complete": 1,
        "observations_written": 0,
        "factors_written": 0,
    }
    assert snapshots_path.read_bytes() == before

    observations = read_jsonl_strict(paths.observations)
    factors = read_jsonl_strict(paths.factors)
    manifests = read_jsonl_strict(paths.manifests)
    assert len({row["observation_id"] for row in observations}) == len(observations)
    assert len({row["factor_value_id"] for row in factors}) == len(factors)
    assert {row["factor_version"] for row in factors} == {LEGACY_FACTOR_VERSION}
    assert next(
        row for row in factors
        if row["entity_id"] == "002475" and row["factor_id"] == "legacy.missing_metric"
    )["quality"] == "missing"
    assert manifests[0]["group_version"] == "not_executed"
    assert "A..N semantics were not inferred" in " ".join(manifests[0]["notes"])


def test_new_factor_version_appends_to_historical_date_without_rewrite(tmp_path):
    paths = default_store_paths(tmp_path / "research")
    manifest, observations, factors = build_legacy_snapshot_run(_snapshots(), mode="replay")
    append_run(manifest, observations, factors, paths=paths)
    factor_path = factor_partition_path(paths, "20260625")
    old_factor_bytes = factor_path.read_bytes()

    source = next(
        row for row in observations
        if row["entity_id"] == "601138" and row["field"] == "metrics"
    )
    inputs = [source["observation_id"]]
    new_factor = {
        "schema_version": 1,
        "factor_value_id": "",
        "entity_type": "stock",
        "entity_id": "601138",
        "dimension": "technical",
        "factor_id": "rsi_centered",
        "factor_version": "technical_rsi_v2",
        "value": -2.0,
        "as_of_trade_date": "20260625",
        "effective_date": "20260625",
        "available_at": source["available_at"],
        "calculated_at": source["available_at"],
        "input_observation_ids": inputs,
        "input_digest": canonical_digest(sorted(inputs)),
        "quality": "calculated",
    }
    new_factor["factor_value_id"] = make_factor_value_id(new_factor)
    new_manifest = {
        "schema_version": 1,
        "run_id": "",
        "mode": "backtest",
        "as_of_trade_date": "20260625",
        "universe_id": "user_universe_601138",
        "feature_set_version": "technical_features_v2",
        "group_version": "not_executed",
        "select_version": "not_executed",
        "forecast_version": "not_executed",
        "input_digest": canonical_digest([source["observation_id"]]),
        "generated_at": source["available_at"],
        "notes": ["historical factor append"],
    }
    new_manifest["run_id"] = make_run_id(new_manifest)

    result = append_run(new_manifest, [], [new_factor], paths=paths)
    assert result["factors_written"] == 1
    assert factor_path.read_bytes().startswith(old_factor_bytes)
    assert len(read_jsonl_strict(paths.factors)) == len(factors) + 1

    conflict = copy.deepcopy(new_factor)
    conflict["value"] = 99.0
    with pytest.raises(StoreError, match="changed without a new revision/version"):
        append_run(new_manifest, [], [conflict], paths=paths)


def test_store_validates_cross_partition_factor_dependencies_and_time(tmp_path):
    paths = default_store_paths(tmp_path / "research")
    manifest, observations, factors = build_legacy_snapshot_run(
        _snapshots(), mode="replay"
    )
    append_run(manifest, observations, factors, paths=paths)
    upstream = next(
        row for row in factors
        if row["entity_id"] == "601138" and row["factor_id"] == "legacy.rsi_14"
    )
    refs = [{
        "factor_value_id": upstream["factor_value_id"],
        "as_of_trade_date": upstream["as_of_trade_date"],
    }]
    derived = {
        "schema_version": 1,
        "factor_value_id": "",
        "entity_type": "stock",
        "entity_id": "601138",
        "dimension": "causal_curve",
        "factor_id": "curve::legacy_snapshot::legacy.rsi_14",
        "factor_version": "curve-v1",
        "value": {"level": 48.0},
        "as_of_trade_date": "20260626",
        "effective_date": "20260626",
        "available_at": upstream["calculated_at"],
        "calculated_at": "2026-06-26T05:11:00+08:00",
        "input_observation_ids": [],
        "input_factor_refs": refs,
        "input_digest": factor_input_digest([], refs),
        "quality": "calculated",
    }
    derived["factor_value_id"] = make_factor_value_id(derived)
    derived_manifest = {
        "schema_version": 1,
        "run_id": "",
        "mode": "replay",
        "as_of_trade_date": "20260626",
        "universe_id": "curve-test",
        "feature_set_version": "curve-v1",
        "group_version": "not_executed",
        "select_version": "not_executed",
        "forecast_version": "not_executed",
        "input_digest": canonical_digest(refs),
        "generated_at": derived["calculated_at"],
        "notes": ["derived dependency test"],
        "observation_count": 0,
        "factor_value_count": 1,
        "observation_digest": canonical_digest([]),
        "factor_value_digest": canonical_digest([derived["factor_value_id"]]),
    }
    derived_manifest["run_id"] = make_run_id(derived_manifest)

    assert append_run(
        derived_manifest, [], [derived], paths=paths
    )["factors_written"] == 1

    unknown = copy.deepcopy(derived)
    unknown["factor_id"] = "curve::unknown"
    unknown["input_factor_refs"] = [{
        "factor_value_id": "factor_missing",
        "as_of_trade_date": "20260625",
    }]
    unknown["input_digest"] = factor_input_digest(
        [], unknown["input_factor_refs"]
    )
    unknown["factor_value_id"] = make_factor_value_id(unknown)
    unknown_manifest = copy.deepcopy(derived_manifest)
    unknown_manifest["feature_set_version"] = "curve-unknown-v1"
    unknown_manifest["factor_value_digest"] = canonical_digest(
        [unknown["factor_value_id"]]
    )
    unknown_manifest["run_id"] = make_run_id(unknown_manifest)
    with pytest.raises(StoreError, match="unknown upstream factor"):
        append_run(unknown_manifest, [], [unknown], paths=paths)

    too_early = copy.deepcopy(derived)
    too_early["factor_id"] = "curve::too-early"
    too_early["available_at"] = "2026-06-26T05:09:00+08:00"
    too_early["calculated_at"] = "2026-06-26T05:09:59+08:00"
    too_early["factor_value_id"] = make_factor_value_id(too_early)
    early_manifest = copy.deepcopy(derived_manifest)
    early_manifest["feature_set_version"] = "curve-early-v1"
    early_manifest["factor_value_digest"] = canonical_digest(
        [too_early["factor_value_id"]]
    )
    early_manifest["run_id"] = make_run_id(early_manifest)
    with pytest.raises(StoreError, match="upstream factor after calculated_at"):
        append_run(early_manifest, [], [too_early], paths=paths)

    future_observation = next(
        row for row in observations
        if row["entity_id"] == "601138" and row["field"] == "metrics"
    )
    bad_direct = copy.deepcopy(derived)
    bad_direct.pop("input_factor_refs")
    bad_direct["factor_id"] = "curve::future-observation"
    bad_direct["available_at"] = "2026-06-26T05:09:00+08:00"
    bad_direct["calculated_at"] = "2026-06-26T05:09:59+08:00"
    bad_direct["input_observation_ids"] = [future_observation["observation_id"]]
    bad_direct["input_digest"] = canonical_digest(
        bad_direct["input_observation_ids"]
    )
    bad_direct["factor_value_id"] = make_factor_value_id(bad_direct)
    direct_manifest = copy.deepcopy(derived_manifest)
    direct_manifest["feature_set_version"] = "curve-future-observation-v1"
    direct_manifest["factor_value_digest"] = canonical_digest(
        [bad_direct["factor_value_id"]]
    )
    direct_manifest["run_id"] = make_run_id(direct_manifest)
    with pytest.raises(StoreError, match="observation after calculated_at"):
        append_run(direct_manifest, [], [bad_direct], paths=paths)


def test_factor_query_enforces_point_in_time_availability(tmp_path):
    paths = default_store_paths(tmp_path / "research")
    manifest, observations, factors = build_legacy_snapshot_run(_snapshots(), mode="replay")
    append_run(manifest, observations, factors, paths=paths)

    assert factor_values_as_of(
        "20260625", "2026-06-26T05:09:59+08:00", paths=paths
    ) == []
    available = factor_values_as_of(
        "20260625",
        "2026-06-26T05:10:00+08:00",
        paths=paths,
        entity_ids=["601138"],
    )
    assert {row["factor_id"] for row in available} == {"legacy.ma5", "legacy.rsi_14"}


def test_observation_query_enforces_point_in_time_and_filters(tmp_path):
    paths = default_store_paths(tmp_path / "research")
    manifest, observations, factors = build_legacy_snapshot_run(
        _snapshots(), mode="replay"
    )
    append_run(manifest, observations, factors, paths=paths)

    assert observations_as_of(
        "2026-06-26T05:09:59+08:00", paths=paths
    ) == []
    available = observations_as_of(
        "2026-06-26T05:10:00+08:00",
        paths=paths,
        entity_ids=["601138"],
        dimensions=["legacy_snapshot"],
    )
    assert available
    assert {row["entity_id"] for row in available} == {"601138"}


def test_replay_rejects_conflicting_market_context(tmp_path):
    rows = _snapshots()
    rows[1]["market"] = copy.deepcopy(rows[1]["market"])
    rows[1]["market"]["regime"] = "panic"
    with pytest.raises(Exception, match="market context conflicts"):
        build_legacy_snapshot_run(rows, mode="replay")
