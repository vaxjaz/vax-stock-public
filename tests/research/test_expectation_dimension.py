# -*- coding: utf-8 -*-

import pytest

from vaxstock.research.expectation_dimension import build_expectation_run
from vaxstock.research.point_in_time_store import (
    append_run,
    default_store_paths,
    read_jsonl_strict,
)


AS_OF = "20260728"
PREVIOUS = "20260727"
RETRIEVED = "2026-07-28T08:36:00+08:00"
REPORT_START = "20260429"
CODE = "601138"


def _report(
    *,
    report_date,
    org,
    eps,
    np_value,
    pe,
    title,
):
    return {
        "ts_code": "601138.SH",
        "name": "工业富联",
        "report_date": report_date,
        "report_title": title,
        "report_type": "一般报告",
        "classify": "一般报告",
        "org_name": org,
        "author_name": "analyst",
        "quarter": "2026Q4",
        "op_rt": 1000.0,
        "op_pr": 700.0,
        "tp": 650.0,
        "np": np_value,
        "eps": eps,
        "pe": pe,
        "rd": 1.0,
        "roe": 10.0,
        "ev_ebitda": 15.0,
        "rating": "买入",
        "max_price": 150.0,
        "min_price": 100.0,
        "imp_dg": "高",
        "create_time": f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:]} 21:00:00",
    }


def _report_result(*, complete=True):
    rows = [
        _report(
            report_date="20260720",
            org="A",
            eps=3.0,
            np_value=300.0,
            pe=20.0,
            title="A-old",
        ),
        _report(
            report_date="20260725",
            org="A",
            eps=4.0,
            np_value=400.0,
            pe=22.0,
            title="A-new",
        ),
        _report(
            report_date="20260724",
            org="B",
            eps=6.0,
            np_value=600.0,
            pe=18.0,
            title="B",
        ),
        _report(
            report_date="20260727",
            org="C",
            eps=10.0,
            np_value=1000.0,
            pe=10.0,
            title="C-after-guidance",
        ),
    ]
    return {
        "available": True,
        "complete": complete,
        "reason": None if complete else "page_limit_reached",
        "rows": rows,
        "fields": sorted(rows[0]),
        "actual_fields": sorted(rows[0]),
        "query": {
            "ts_code": None,
            "start_date": REPORT_START,
            "end_date": "20260727",
            "page_limit": 3000,
            "max_pages": 10,
        },
    }


def _forecast_result():
    row = {
        "ts_code": "601138.SH",
        "ann_date": "20260727",
        "end_date": "20261231",
        "type": "预增",
        "p_change_min": 10.0,
        "p_change_max": 20.0,
        "net_profit_min": 400.0,
        "net_profit_max": 600.0,
        "last_parent_net": 350.0,
        "first_ann_date": "20260727",
        "summary": "test",
        "change_reason": "test",
    }
    return {
        "available": True,
        "complete": True,
        "reason": None,
        "rows": [row],
        "fields": sorted(row),
        "actual_fields": sorted(row),
        "query": {
            "ts_code": "601138.SH",
            "start_date": "20250623",
            "end_date": AS_OF,
        },
    }


def _daily_result(*, trade_date=PREVIOUS):
    row = {
        "ts_code": "601138.SH",
        "trade_date": trade_date,
        "close": 120.0,
        "pe_ttm": 30.0,
        "total_share": 100.0,
        "total_mv": 12000.0,
    }
    return {
        "available": True,
        "complete": True,
        "reason": None,
        "rows": [row],
        "fields": sorted(row),
        "actual_fields": sorted(row),
        "query": {"ts_code": "601138.SH", "trade_date": trade_date},
    }


def _build(*, report_result=None, daily_result=None, existing=()):
    return build_expectation_run(
        as_of_trade_date=AS_OF,
        previous_trade_date=PREVIOUS,
        retrieved_at=RETRIEVED,
        universe_codes=[CODE],
        report_result=report_result or _report_result(),
        forecasts_by_code={CODE: _forecast_result()},
        daily_basic_by_code={CODE: daily_result or _daily_result()},
        existing_observations=existing,
    )


def _factor_map(factors):
    return {row["factor_id"]: row for row in factors}


def test_complete_window_builds_auditable_seller_guidance_and_valuation_factors():
    manifest, observations, factors, summary = _build()
    values = _factor_map(factors)

    assert summary["report_window_complete"] is True
    assert summary["report_required_start"] == REPORT_START
    assert values["seller_consensus_eps_median_90d.2026Q4"]["value"] == 6.0
    assert (
        values["seller_consensus_net_profit_median_wan_90d.2026Q4"]["value"]
        == 600.0
    )
    assert values["seller_consensus_eps_org_count_90d.2026Q4"]["value"] == 3
    assert values["seller_report_row_count_90d.2026Q4"]["value"] == 4
    assert values["seller_reported_forward_pe_median_90d.2026Q4"]["value"] == 18.0
    assert values["current_forward_pe_from_seller_consensus_eps.2026Q4"]["value"] == 20.0
    assert values["eps_required_at_seller_reported_pe_median.2026Q4"]["value"] == pytest.approx(
        120.0 / 18.0
    )
    assert values[
        "current_forward_pe_vs_seller_reported_pe_gap_pct.2026Q4"
    ]["value"] == pytest.approx((20.0 / 18.0 - 1.0) * 100.0)
    assert values["guidance_net_profit_mid_wan.20261231"]["value"] == 500.0
    assert values[
        "preannouncement_seller_net_profit_median_wan.20261231.20260727"
    ]["value"] == 500.0
    assert values[
        "guidance_vs_preannouncement_seller_net_profit_gap_pct.20261231.20260727"
    ]["value"] == 0.0
    assert manifest["group_version"] == "not_executed"
    assert manifest["select_version"] == "not_executed"
    assert manifest["forecast_version"] == "not_executed"

    status_id = next(
        row["observation_id"]
        for row in observations
        if row["field"] == "seller_consensus_query"
    )
    assert status_id in values[
        "seller_consensus_eps_median_90d.2026Q4"
    ]["input_observation_ids"]


def test_incomplete_seller_window_abstains_from_consensus_but_keeps_guidance_fact():
    _, _, factors, summary = _build(
        report_result=_report_result(complete=False)
    )
    values = _factor_map(factors)

    assert summary["report_window_complete"] is False
    assert set(values) == {"guidance_net_profit_mid_wan.20261231"}


def test_stale_daily_basic_never_creates_price_relative_factors():
    _, _, factors, _ = _build(
        daily_result=_daily_result(trade_date="20260724")
    )

    assert not any(
        row["factor_version"] == "E_price_relative_to_seller_estimates_v1"
        for row in factors
    )


def test_store_retry_is_idempotent_and_freezes_first_retrieval(tmp_path):
    paths = default_store_paths(tmp_path / "research")
    manifest, observations, factors, _ = _build()
    first = append_run(manifest, observations, factors, paths=paths)

    stored_observations = read_jsonl_strict(paths.observations)
    retry_manifest, retry_observations, retry_factors, _ = _build(
        existing=stored_observations
    )
    second = append_run(
        retry_manifest,
        retry_observations,
        retry_factors,
        paths=paths,
    )

    assert first["status"] == "written"
    assert second["status"] == "already_complete"
    assert second["observations_written"] == 0
    assert second["factors_written"] == 0
