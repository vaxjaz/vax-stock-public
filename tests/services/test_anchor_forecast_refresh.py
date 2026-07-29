# -*- coding: utf-8 -*-

import json

from vaxstock.research.global_anchor_dimension import build_global_anchor_run
from vaxstock.research.point_in_time_store import (
    append_run,
    default_store_paths,
)
from vaxstock.services.anchor_forecast_refresh import (
    run_anchor_forecast_refresh,
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


def _append_anchor(paths, trade_date, retrieved_at):
    manifest, observations, factors, _ = build_global_anchor_run(
        as_of_trade_date=trade_date,
        retrieved_at=retrieved_at,
        us_market=_us_market(trade_date),
        mode="replay",
    )
    append_run(manifest, observations, factors, paths=paths)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def test_service_rerun_uses_frozen_factor_time_and_is_idempotent(tmp_path):
    paths = default_store_paths(tmp_path / "research")
    _append_anchor(
        paths,
        "20260724",
        "2026-07-25T05:00:00+08:00",
    )
    _append_anchor(
        paths,
        "20260728",
        "2026-07-29T05:00:00+08:00",
    )
    snapshots_path = tmp_path / "factor_snapshots.jsonl"
    results_path = tmp_path / "factor_results.jsonl"
    snapshots = [
        {
            "trade_date": trade_date,
            "code": code,
            "concepts": ["AI算力"],
        }
        for trade_date in ("20260724", "20260728")
        for code in ("600001", "600002", "600003")
    ]
    results = [
        {
            "trade_date": "20260724",
            "code": code,
            "ret": {"1": -0.01},
            "mkt_ret": {"1": 0.01},
            "excess": {"1": -0.02},
            "horizon_trade_dates": {"1": "20260725"},
            "filled_ts": "2026-07-26T05:00:00+08:00",
        }
        for code in ("600001", "600002", "600003")
    ]
    _write_jsonl(snapshots_path, snapshots)
    _write_jsonl(results_path, results)

    kwargs = {
        "as_of_trade_date": "20260728",
        "research_paths": paths,
        "snapshots_path": snapshots_path,
        "results_path": results_path,
        "output_dir": tmp_path / "forecasts",
        "horizons": [1],
    }
    first = run_anchor_forecast_refresh(**kwargs)
    second = run_anchor_forecast_refresh(**kwargs)
    audit = json.loads(
        (tmp_path / "forecasts" / (
            "anchor_trend_forecast_20260728"
            "__anchor_ai_track_probability_v1.json"
        )).read_text(encoding="utf-8")
    )

    assert first["status"] == "estimated"
    assert first["write_status"] == "written"
    assert second["write_status"] == "already_complete"
    assert audit["decision_at"] == "2026-07-29T05:00:00+08:00"
    assert audit["production_eligible"] is False
