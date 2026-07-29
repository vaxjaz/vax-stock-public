# -*- coding: utf-8 -*-

from copy import deepcopy

from vaxstock.research.contracts import (
    validate_atomic_observation,
    validate_factor_value,
    validate_run_manifest,
)
from vaxstock.research.global_anchor_dimension import (
    ANCHOR_CONTEXT_FACTOR_ID,
    build_global_anchor_run,
)
from vaxstock.research.point_in_time_store import (
    append_run,
    default_store_paths,
    read_jsonl_strict,
)


AS_OF = "20260728"
RETRIEVED = "2026-07-29T05:00:00+08:00"


def _payload():
    return {
        "indices": [{
            "symbol": "^VIX",
            "price": 18.21,
            "prev_close": 18.67,
            "change_pct": -2.46,
            "volume": 0,
            "date": "2026-07-28",
        }],
        "etfs": [
            {
                "symbol": "SOXX",
                "price": 491.46,
                "prev_close": 516.23,
                "change_pct": -4.80,
                "volume": 100,
                "date": "2026-07-28",
            },
            {
                "symbol": "QQQ",
                "price": 675.49,
                "prev_close": 682.12,
                "change_pct": -0.97,
                "volume": 100,
                "date": "2026-07-28",
            },
        ],
        "stocks": [{
            "symbol": "NVDA",
            "price": 197.01,
            "prev_close": 196.51,
            "change_pct": 0.25,
            "volume": 100,
            "date": "2026-07-28",
        }],
        "macro": [],
    }


def _build(*, payload=None, existing=()):
    return build_global_anchor_run(
        as_of_trade_date=AS_OF,
        retrieved_at=RETRIEVED,
        us_market=payload or _payload(),
        existing_observations=existing,
        mode="replay",
    )


def test_complete_anchor_run_is_traceable_and_uses_equity_majority():
    manifest, observations, factors, summary = _build()

    validate_run_manifest(manifest)
    for row in observations:
        validate_atomic_observation(row)
    for row in factors:
        validate_factor_value(row)

    context = next(
        row for row in factors
        if row["factor_id"] == ANCHOR_CONTEXT_FACTOR_ID
    )
    assert summary["status"] == "complete"
    assert summary["equity_majority_direction"] == "down"
    assert context["value"]["states"] == {
        "anchor_nvda_direction": "up",
        "anchor_soxx_direction": "down",
        "anchor_qqq_direction": "down",
        "anchor_vix_direction": "down",
        "anchor_equity_majority_direction": "down",
    }
    assert context["value"]["collection_complete"] is True
    assert context["available_at"] == RETRIEVED
    assert set(context["input_observation_ids"]) == {
        row["observation_id"] for row in observations
    }


def test_missing_or_conflicting_anchor_never_becomes_neutral():
    payload = deepcopy(_payload())
    payload["etfs"] = [
        row for row in payload["etfs"] if row["symbol"] != "QQQ"
    ]
    payload["stocks"][0]["change_pct"] = 9.0

    _, _, factors, summary = _build(payload=payload)
    context = next(
        row for row in factors
        if row["factor_id"] == ANCHOR_CONTEXT_FACTOR_ID
    )

    assert summary["status"] == "partial"
    assert summary["missing_symbols"] == ["QQQ"]
    assert summary["invalid_symbols"] == ["NVDA:return_mismatch"]
    assert summary["equity_majority_direction"] is None
    assert context["value"]["states"]["anchor_nvda_direction"] is None
    assert context["value"]["states"]["anchor_qqq_direction"] is None
    assert context["value"]["states"][
        "anchor_equity_majority_direction"
    ] is None


def test_retry_freezes_first_availability_and_is_idempotent(tmp_path):
    paths = default_store_paths(tmp_path / "research")
    manifest, observations, factors, _ = _build()
    first = append_run(
        manifest,
        observations,
        factors,
        paths=paths,
    )
    stored = read_jsonl_strict(paths.observations)
    retry_manifest, retry_observations, retry_factors, _ = (
        build_global_anchor_run(
            as_of_trade_date=AS_OF,
            retrieved_at="2026-07-29T05:30:00+08:00",
            us_market=_payload(),
            existing_observations=stored,
            mode="replay",
        )
    )
    second = append_run(
        retry_manifest,
        retry_observations,
        retry_factors,
        paths=paths,
    )

    assert first["status"] == "written"
    assert second["status"] == "already_complete"
    assert retry_manifest["run_id"] == manifest["run_id"]
    assert {
        row["available_at"] for row in retry_observations
    } == {RETRIEVED}

