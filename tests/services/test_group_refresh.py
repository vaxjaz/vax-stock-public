# -*- coding: utf-8 -*-

import json

import pytest

from vaxstock.research.contracts import ContractError
from vaxstock.research.legacy_snapshot_replay import replay_legacy_snapshots
from vaxstock.research.point_in_time_store import (
    default_store_paths,
    read_jsonl_strict,
)
from vaxstock.services.curve_refresh import replay_curve_features
from vaxstock.services.group_refresh import (
    replay_group_features,
    run_group_refresh,
)


DATES = [
    "20260701", "20260702", "20260703", "20260706", "20260707",
    "20260708", "20260709", "20260710", "20260713", "20260714",
    "20260715", "20260716",
]


def _snapshots():
    rows = []
    for date_index, trade_date in enumerate(DATES):
        for stock_index in range(9):
            code = f"6000{stock_index:02d}"
            rows.append({
                "schema_version": 1,
                "snapshot_ts": (
                    f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
                    "T18:00:00+08:00"
                ),
                "trade_date": trade_date,
                "code": code,
                "name": code,
                "group": "holding" if stock_index == 0 else "watchlist",
                "concepts": ["AI算力"],
                "price_at_snapshot": 60.0 + date_index + stock_index,
                "metrics": {
                    "rsi_14": 40.0 + date_index + stock_index,
                    "ma5": 60.0 + date_index + stock_index,
                },
                "market": {
                    "regime": "momentum",
                    "macro_regime": "neutral",
                },
            })
    return rows


def test_group_replay_is_label_free_and_idempotent(tmp_path):
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
    replay_curve_features(paths=paths)

    first = replay_group_features(paths=paths)
    second = replay_group_features(paths=paths)

    assert first == {
        "status": "complete",
        "trade_dates": len(DATES),
        "runs_written": len(DATES),
        "runs_already_complete": 0,
        "blocked": [],
        "factors_written": len(DATES) * 10,
        "label_usage": "none",
    }
    assert second["status"] == "complete"
    assert second["runs_written"] == 0
    assert second["runs_already_complete"] == len(DATES)
    assert second["factors_written"] == 0
    assert second["label_usage"] == "none"

    latest = [
        row
        for row in read_jsonl_strict(paths.factors / f"{DATES[-1]}.jsonl")
        if row.get("dimension") == "research_group"
    ]
    assert len(latest) == 10
    assert sum(row["entity_type"] == "stock" for row in latest) == 9
    assert all(row["value"]["label_usage"] == "none" for row in latest)


def test_group_replay_rejects_invalid_or_reversed_date_ranges(tmp_path):
    paths = default_store_paths(tmp_path / "research")
    with pytest.raises(ContractError, match="YYYYMMDD"):
        replay_group_features(paths=paths, start_trade_date="2026-07-01")
    with pytest.raises(ContractError, match="cannot be after"):
        replay_group_features(
            paths=paths,
            start_trade_date="20260702",
            end_trade_date="20260701",
        )


def test_live_group_refresh_appends_after_curve_and_is_idempotent(tmp_path):
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
    replay_curve_features(paths=paths)

    first = run_group_refresh(
        as_of_trade_date=DATES[-1],
        decision_at="2026-07-16T18:05:00+08:00",
        mode="live",
        paths=paths,
    )
    second = run_group_refresh(
        as_of_trade_date=DATES[-1],
        decision_at="2026-07-16T18:05:00+08:00",
        mode="live",
        paths=paths,
    )

    assert first["status"] == "written"
    assert first["stored"]["factors_written"] == 10
    assert first["summary"]["label_usage"] == "none"
    assert second["status"] == "already_complete"
    assert second["stored"]["factors_written"] == 0
