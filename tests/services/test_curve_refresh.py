# -*- coding: utf-8 -*-

import json

import pytest

from vaxstock.research.contracts import ContractError
from vaxstock.research.legacy_snapshot_replay import replay_legacy_snapshots
from vaxstock.research.point_in_time_store import (
    default_store_paths,
    read_jsonl_strict,
)
from vaxstock.services.curve_refresh import (
    replay_curve_features,
    run_curve_refresh,
)


DATES = [
    "20260701", "20260702", "20260703", "20260706", "20260707",
    "20260708", "20260709", "20260710", "20260713", "20260714",
    "20260715", "20260716",
]


def _snapshots():
    rows = []
    for index, trade_date in enumerate(DATES):
        for code, offset in (
            ("601138", 0.0),
            ("002475", 2.0),
            ("600276", 4.0),
        ):
            rows.append({
                "schema_version": 1,
                "snapshot_ts": (
                    f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
                    "T18:00:00+08:00"
                ),
                "trade_date": trade_date,
                "code": code,
                "name": code,
                "group": "holding",
                "concepts": ["AI算力"],
                "price_at_snapshot": 60.0 + index + offset,
                "metrics": {
                    "rsi_14": 40.0 + index + offset,
                    "ma5": 60.0 + index + offset,
                },
                "market": {"regime": "momentum"},
            })
    return rows


def test_curve_replay_is_sequential_causal_and_idempotent(tmp_path):
    source = tmp_path / "factor_snapshots.jsonl"
    source.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in _snapshots()
        ),
        encoding="utf-8",
    )
    paths = default_store_paths(tmp_path / "research")
    replay_legacy_snapshots(snapshots_path=source, paths=paths)

    first = replay_curve_features(paths=paths)
    second = replay_curve_features(paths=paths)

    assert first["status"] == "complete"
    assert first["trade_dates"] == len(DATES)
    assert first["runs_written"] == len(DATES)
    assert first["runs_already_complete"] == 0
    assert first["blocked"] == []
    assert first["factors_written"] == len(DATES) * 5
    assert second["runs_written"] == 0
    assert second["runs_already_complete"] == len(DATES)
    assert second["factors_written"] == 0

    latest = [
        row for row in read_jsonl_strict(paths.factors / f"{DATES[-1]}.jsonl")
        if row.get("dimension") == "causal_curve"
    ]
    assert len(latest) == 4
    assert {row["entity_type"] for row in latest} == {"stock", "track"}
    assert all(
        next(iter(row["value"]["series"].values()))["sample_count"] == len(DATES)
        for row in latest
    )
    assert all(row["value"]["candidate_events"] == [] for row in latest)
    assert all(
        len(row["input_factor_refs"]) == 2
        for row in latest
    )


def test_curve_replay_rejects_invalid_or_reversed_date_ranges(tmp_path):
    paths = default_store_paths(tmp_path / "research")
    with pytest.raises(ContractError, match="YYYYMMDD"):
        replay_curve_features(paths=paths, start_trade_date="2026-07-01")
    with pytest.raises(ContractError, match="cannot be after"):
        replay_curve_features(
            paths=paths,
            start_trade_date="20260702",
            end_trade_date="20260701",
        )


def test_live_curve_retry_with_later_wall_clock_is_idempotent(tmp_path):
    source = tmp_path / "factor_snapshots.jsonl"
    source.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in _snapshots()
        ),
        encoding="utf-8",
    )
    paths = default_store_paths(tmp_path / "research")
    replay_legacy_snapshots(snapshots_path=source, paths=paths)

    first = run_curve_refresh(
        as_of_trade_date=DATES[-1],
        decision_at="2026-07-16T18:05:00+08:00",
        mode="live",
        paths=paths,
    )
    second = run_curve_refresh(
        as_of_trade_date=DATES[-1],
        decision_at="2026-07-16T18:06:00+08:00",
        mode="live",
        paths=paths,
    )

    assert first["status"] == "written"
    assert first["stored"]["factors_written"] == 5
    assert second["status"] == "already_complete"
    assert second["stored"]["factors_written"] == 0
