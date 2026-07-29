# -*- coding: utf-8 -*-

import json

from vaxstock.research.point_in_time_store import (
    default_store_paths,
    read_jsonl_strict,
)
from vaxstock.services.global_anchor_refresh import (
    replay_global_anchors,
)


def _us_market(trade_date):
    date = (
        f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    )
    return {
        "indices": [{
            "symbol": "^VIX",
            "price": 20.0,
            "prev_close": 19.0,
            "change_pct": 5.26,
            "date": date,
        }],
        "etfs": [
            {
                "symbol": "SOXX",
                "price": 95.0,
                "prev_close": 100.0,
                "change_pct": -5.0,
                "date": date,
            },
            {
                "symbol": "QQQ",
                "price": 99.0,
                "prev_close": 100.0,
                "change_pct": -1.0,
                "date": date,
            },
        ],
        "stocks": [{
            "symbol": "NVDA",
            "price": 101.0,
            "prev_close": 100.0,
            "change_pct": 1.0,
            "date": date,
        }],
        "macro": [],
    }


def _write_report(root, trade_date, generated_at):
    target = root / (
        f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    ) / "payload.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "market_overview": {"trade_date": trade_date},
                "us_market": _us_market(trade_date),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_saved_report_replay_is_point_in_time_and_idempotent(tmp_path):
    reports = tmp_path / "reports"
    paths = default_store_paths(tmp_path / "research")
    _write_report(
        reports,
        "20260724",
        "2026-07-25 05:00:00",
    )
    _write_report(
        reports,
        "20260728",
        "2026-07-29 05:00:00",
    )

    first = replay_global_anchors(
        reports_dir=reports,
        paths=paths,
    )
    second = replay_global_anchors(
        reports_dir=reports,
        paths=paths,
    )
    observations = read_jsonl_strict(paths.observations)

    assert first["status"] == "complete"
    assert first["trade_dates"] == 2
    assert first["factors_written"] == 10
    assert second["factors_written"] == 0
    assert second["manifests_written"] == 0
    first_date_rows = [
        row for row in observations
        if row["effective_date"] == "20260724"
    ]
    assert {
        row["available_at"] for row in first_date_rows
    } == {"2026-07-25T05:00:00+08:00"}

