# -*- coding: utf-8 -*-

import ast
from pathlib import Path

import pytest

from vaxstock.research.contracts import (
    ContractError,
    assert_available_as_of,
    assert_factor_available_as_of,
    canonical_digest,
    make_factor_value_id,
    make_observation_id,
    make_run_id,
    validate_atomic_observation,
    validate_factor_value,
    validate_forecast_output,
    validate_run_manifest,
)


_ROOT = Path(__file__).resolve().parents[2]


def _observation():
    row = {
        "schema_version": 1,
        "observation_id": "",
        "entity_type": "stock",
        "entity_id": "601138",
        "dimension": "E",
        "field": "consensus_eps",
        "value": 3.21,
        "effective_date": "20261231",
        "available_at": "2026-07-27T18:30:00+08:00",
        "retrieved_at": "2026-07-27T18:35:00+08:00",
        "source": "vendor",
        "source_ref": "vendor:601138:20261231",
        "revision_id": "20260727T183000+0800",
        "quality": "observed",
    }
    row["observation_id"] = make_observation_id(row)
    return row


def _factor():
    inputs = [_observation()["observation_id"]]
    row = {
        "schema_version": 1,
        "factor_value_id": "",
        "entity_type": "stock",
        "entity_id": "601138",
        "dimension": "E",
        "factor_id": "consensus_eps_revision",
        "factor_version": "e-consensus-v1",
        "value": 0.08,
        "as_of_trade_date": "20260727",
        "effective_date": "20261231",
        "available_at": "2026-07-27T18:35:00+08:00",
        "calculated_at": "2026-07-27T18:36:00+08:00",
        "input_observation_ids": inputs,
        "input_digest": canonical_digest(sorted(inputs)),
        "quality": "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _manifest():
    row = {
        "schema_version": 1,
        "run_id": "",
        "mode": "replay",
        "as_of_trade_date": "20260727",
        "universe_id": "watchlist:abc",
        "feature_set_version": "features-v1",
        "group_version": "not_executed",
        "select_version": "not_executed",
        "forecast_version": "not_executed",
        "input_digest": "abc",
        "generated_at": "2026-07-27T19:00:00+08:00",
        "notes": ["ingestion only"],
    }
    row["run_id"] = make_run_id(row)
    return row


def _forecast(status="available"):
    row = {
        "schema_version": 1,
        "status": status,
        "as_of_trade_date": "20260727",
        "target": "601138",
        "strategy": "expectation_revision",
        "horizon": "event_window_5d",
        "direction": "up",
        "expected_excess_return": 0.03,
        "confidence": 0.64,
        "primary_benchmark": "sector_equal_weight",
        "secondary_benchmark": "CSI800",
        "group_version": "g0",
        "select_version": "s0",
        "forecast_version": "f0",
        "feature_set_version": "features-v1",
        "input_digest": "abc",
        "generated_at": "2026-07-27T19:00:00+08:00",
        "abstain_reason": None,
    }
    if status == "abstain":
        row.update({
            "direction": None,
            "expected_excess_return": None,
            "confidence": None,
            "abstain_reason": "critical_input_stale",
        })
    return row


def test_contract_module_is_standard_library_leaf():
    source = (_ROOT / "src" / "vaxstock" / "research" / "contracts.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= {"__future__", "datetime", "hashlib", "json", "math", "typing"}


def test_canonical_digest_is_order_independent_and_rejects_nan():
    assert canonical_digest({"b": 2, "a": [1]}) == canonical_digest({"a": [1], "b": 2})
    with pytest.raises(ContractError, match="canonical JSON"):
        canonical_digest({"bad": float("nan")})


def test_observation_requires_provenance_and_timezone():
    row = _observation()
    validate_atomic_observation(row)

    no_source = dict(row, source_ref="")
    with pytest.raises(ContractError, match="source_ref"):
        validate_atomic_observation(no_source)

    naive_time = dict(row, available_at="2026-07-27T18:30:00")
    with pytest.raises(ContractError, match="timezone"):
        validate_atomic_observation(naive_time)

    changed_value = dict(row, value=3.22)
    validate_atomic_observation(changed_value)
    assert changed_value["observation_id"] == row["observation_id"]


def test_point_in_time_guard_rejects_lookahead():
    row = _observation()
    assert_available_as_of(row, "2026-07-27T18:31:00+08:00")
    with pytest.raises(ContractError, match="look-ahead"):
        assert_available_as_of(row, "2026-07-27T18:29:59+08:00")


def test_factor_and_run_identities_are_versioned_and_deterministic():
    factor = _factor()
    validate_factor_value(factor)
    validate_run_manifest(_manifest())
    assert_factor_available_as_of(factor, "2026-07-27T18:36:00+08:00")
    with pytest.raises(ContractError, match="look-ahead"):
        assert_factor_available_as_of(factor, "2026-07-27T18:35:30+08:00")

    changed = dict(factor, value=0.09)
    validate_factor_value(changed)
    assert changed["factor_value_id"] == factor["factor_value_id"]

    bad_inputs = dict(factor, input_digest="wrong")
    with pytest.raises(ContractError, match="input_digest"):
        validate_factor_value(bad_inputs)

    wrong_id = dict(_manifest(), run_id="run_wrong")
    with pytest.raises(ContractError, match="run_id"):
        validate_run_manifest(wrong_id)


def test_forecast_contract_supports_prediction_and_explicit_abstention():
    validate_forecast_output(_forecast())
    validate_forecast_output(_forecast("abstain"))

    invalid = _forecast("abstain")
    invalid["confidence"] = 0.5
    with pytest.raises(ContractError, match="numeric prediction"):
        validate_forecast_output(invalid)
