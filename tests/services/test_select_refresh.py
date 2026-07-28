# -*- coding: utf-8 -*-

import json

from vaxstock.research.contextual_group import (
    GROUP_VERSION,
    STOCK_GROUP_FACTOR_ID,
    STOCK_GROUP_FACTOR_VERSION,
)
from vaxstock.research.contracts import (
    canonical_digest,
    make_factor_value_id,
    make_group_outcome_id,
)
from vaxstock.research.point_in_time_store import (
    default_store_paths,
    read_jsonl_strict,
)
from vaxstock.services.select_refresh import run_select_refresh
from vaxstock.research.walk_forward_select import SELECT_VERSION


SERIES = "legacy_snapshot::legacy.rsi_14::legacy_snapshot_v1"


def _group(trade_date, code, side, calculated_at):
    inputs = [f"obs_{trade_date}_{code}"]
    row = {
        "schema_version": 1,
        "factor_value_id": "",
        "entity_type": "stock",
        "entity_id": code,
        "dimension": "research_group",
        "factor_id": STOCK_GROUP_FACTOR_ID,
        "factor_version": STOCK_GROUP_FACTOR_VERSION,
        "value": {
            "group_version": GROUP_VERSION,
            "label_usage": "none",
            "factor_groups": {
                SERIES: {
                    "cross_section": {
                        "status": "available",
                        "bucket": side,
                        "rank_pct": 0.9 if side == "high" else 0.1,
                    },
                    "curve_state_vector": [None, None, None, None, None],
                    "track_relation_vectors": {},
                }
            },
        },
        "as_of_trade_date": trade_date,
        "effective_date": trade_date,
        "available_at": calculated_at,
        "calculated_at": calculated_at,
        "input_observation_ids": inputs,
        "input_digest": canonical_digest(inputs),
        "quality": "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _outcome(group, excess):
    row = {
        "schema_version": 1,
        "outcome_id": "",
        "as_of_trade_date": group["as_of_trade_date"],
        "code": group["entity_id"],
        "group_factor_value_id": group["factor_value_id"],
        "group_factor_version": group["factor_version"],
        "group_version": GROUP_VERSION,
        "group_available_at": group["available_at"],
        "group_calculated_at": group["calculated_at"],
        "horizon_sessions": 1,
        "outcome_trade_date": "20260702",
        "outcome_available_at": "2026-07-03T05:00:00+08:00",
        "ret": excess + 0.01,
        "benchmark_ret": 0.01,
        "excess_ret": excess,
        "benchmark_code": "000001.SH",
        "benchmark_kind": "legacy_market_index",
        "source": "legacy.factor_results",
        "source_ref": (
            "var/eval/factor_results.jsonl#"
            f"20260701:{group['entity_id']}:T+1"
        ),
        "independent_session_id": "20260701",
        "input_digest": "",
    }
    row["input_digest"] = canonical_digest({
        "group_factor_value_id": row["group_factor_value_id"],
        "horizon_sessions": row["horizon_sessions"],
        "outcome_trade_date": row["outcome_trade_date"],
        "outcome_available_at": row["outcome_available_at"],
        "ret": row["ret"],
        "benchmark_ret": row["benchmark_ret"],
        "excess_ret": row["excess_ret"],
        "benchmark_code": row["benchmark_code"],
        "source": row["source"],
    })
    row["outcome_id"] = make_group_outcome_id(row)
    return row


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in rows
        ),
        encoding="utf-8",
    )


def test_select_refresh_is_point_in_time_immutable_and_idempotent(tmp_path):
    paths = default_store_paths(tmp_path / "research")
    historical = []
    current = []
    outcomes = []
    for index in range(6):
        code = f"6000{index:02d}"
        side = "high" if index < 3 else "low"
        old_group = _group(
            "20260701",
            code,
            side,
            "2026-07-02T05:00:00+08:00",
        )
        historical.append(old_group)
        outcomes.append(
            _outcome(
                old_group,
                0.03 if side == "high" else -0.01,
            )
        )
        current.append(
            _group(
                "20260703",
                code,
                side,
                "2026-07-04T05:00:00+08:00",
            )
        )
    _write_jsonl(paths.factors / "20260701.jsonl", historical)
    _write_jsonl(paths.factors / "20260703.jsonl", current)
    outcome_path = tmp_path / "group_outcomes.jsonl"
    selections = tmp_path / "selections"
    _write_jsonl(outcome_path, outcomes)

    first = run_select_refresh(
        research_paths=paths,
        outcomes_path=outcome_path,
        selections_dir=selections,
        as_of_trade_date="20260703",
    )
    second = run_select_refresh(
        research_paths=paths,
        outcomes_path=outcome_path,
        selections_dir=selections,
        as_of_trade_date="20260703",
    )

    assert first["status"] == "abstain"
    assert first["write_status"] == "written"
    assert first["production_eligible"] is False
    assert second["write_status"] == "already_complete"
    stored = json.loads(
        (
            selections
            / f"selection_audit_20260703__{SELECT_VERSION}.json"
        ).read_text(
            encoding="utf-8"
        )
    )
    assert stored["status_counts"] == {"abstain": 5}
    assert stored["horizons"]["1"]["build"][
        "complete_outcome_trade_dates"
    ] == 1
    assert stored["horizons"]["1"]["selection"][
        "independent_dates_available"
    ] == 1
    assert read_jsonl_strict(outcome_path) == outcomes

    future = [
        _group(
            "20260706",
            f"6000{index:02d}",
            "high" if index < 3 else "low",
            "2026-07-07T05:00:00+08:00",
        )
        for index in range(6)
    ]
    _write_jsonl(paths.factors / "20260706.jsonl", future)
    historical_rerun = run_select_refresh(
        research_paths=paths,
        outcomes_path=outcome_path,
        selections_dir=selections,
        as_of_trade_date="20260703",
    )
    assert historical_rerun["write_status"] == "already_complete"
