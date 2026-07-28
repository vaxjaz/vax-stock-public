# -*- coding: utf-8 -*-

import json

from vaxstock.research.contextual_group import (
    GROUP_VERSION,
    STOCK_GROUP_FACTOR_ID,
    STOCK_GROUP_FACTOR_VERSION,
)
from vaxstock.research.contracts import canonical_digest, make_factor_value_id
from vaxstock.research.point_in_time_store import (
    default_store_paths,
    read_jsonl_strict,
)
from vaxstock.services.group_outcome_refresh import run_group_outcome_refresh


BASELINE = "20260724"
CODE = "601138"


def _group_factor():
    inputs = ["obs_membership"]
    row = {
        "schema_version": 1,
        "factor_value_id": "",
        "entity_type": "stock",
        "entity_id": CODE,
        "dimension": "research_group",
        "factor_id": STOCK_GROUP_FACTOR_ID,
        "factor_version": STOCK_GROUP_FACTOR_VERSION,
        "value": {
            "group_version": GROUP_VERSION,
            "label_usage": "none",
            "factor_groups": {
                "legacy_snapshot::legacy.rsi_14::legacy_snapshot_v1": {
                    "cross_section": {
                        "status": "available",
                        "rank_pct": 0.8,
                        "bucket": "high",
                    },
                    "curve_state_vector": [None, None, None, None, None],
                    "track_relation_vectors": {},
                }
            },
        },
        "as_of_trade_date": BASELINE,
        "effective_date": BASELINE,
        "available_at": "2026-07-25T05:03:11+08:00",
        "calculated_at": "2026-07-25T05:03:11+08:00",
        "input_observation_ids": inputs,
        "input_digest": canonical_digest(inputs),
        "quality": "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _result_rows():
    return [
        {
            "trade_date": BASELINE,
            "code": CODE,
            "ret": {"1": 0.03},
            "mkt_ret": {"1": 0.01},
            "excess": {"1": 0.02},
            "filled_ts": "2026-07-28T05:00:00",
        },
        {
            "trade_date": BASELINE,
            "code": CODE,
            "horizon_trade_dates": {"1": "20260727"},
            "filled_ts": "2026-07-28T05:01:00",
        },
        {
            "trade_date": BASELINE,
            "code": CODE,
            "ret": {"1": 0.03},
            "mkt_ret": {"1": 0.01},
            "excess": {"1": 0.02},
            "horizon_trade_dates": {"1": "20260727"},
            "filled_ts": "2026-07-29T05:00:00",
        },
    ]


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def test_group_outcome_refresh_is_append_only_and_idempotent(tmp_path):
    paths = default_store_paths(tmp_path / "research")
    _write_jsonl(
        paths.factors / f"{BASELINE}.jsonl",
        [_group_factor()],
    )
    results = tmp_path / "factor_results.jsonl"
    samples = tmp_path / "group_outcomes.jsonl"
    _write_jsonl(results, _result_rows())

    first = run_group_outcome_refresh(
        research_paths=paths,
        factor_results_path=results,
        samples_path=samples,
    )
    second = run_group_outcome_refresh(
        research_paths=paths,
        factor_results_path=results,
        samples_path=samples,
    )

    assert first["status"] == "written"
    assert first["stored"] == {"existing": 0, "written": 1, "skipped": 0}
    assert second["status"] == "already_complete"
    assert second["stored"] == {"existing": 1, "written": 0, "skipped": 1}
    stored = read_jsonl_strict(samples)
    assert len(stored) == 1
    assert stored[0]["outcome_first_complete_row_number"] == 2


def test_group_outcome_refresh_reports_missing_group_without_writing(tmp_path):
    paths = default_store_paths(tmp_path / "research")
    results = tmp_path / "factor_results.jsonl"
    samples = tmp_path / "group_outcomes.jsonl"
    _write_jsonl(results, _result_rows())

    result = run_group_outcome_refresh(
        research_paths=paths,
        factor_results_path=results,
        samples_path=samples,
    )
    assert result["status"] == "partial"
    assert result["summary"]["missing_group_samples"] == 1
    assert result["stored"]["written"] == 0
    assert not samples.exists()
