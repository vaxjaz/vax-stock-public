# -*- coding: utf-8 -*-

from vaxstock.analysis.freshness import assess_eod_freshness


def _payload():
    return {
        "market_overview": {"trade_date": "20260727"},
        "indices": [
            {"symbol": "sh000001", "trade_date": "20260727"},
            {"symbol": "sz399006", "trade_date": "20260727"},
        ],
        "stocks": [
            {
                "code": "601138",
                "history_tail": [
                    {"trade_date": "20260724"},
                    {"trade_date": "20260727"},
                ],
            },
            {
                "code": "002475",
                "history_tail": [{"trade_date": "20260727"}],
            },
        ],
    }


def test_freshness_ready_when_critical_trade_dates_align():
    result = assess_eod_freshness(_payload())
    assert result["status"] == "ready"
    assert result["forecast_eligible"] is True
    assert result["trade_date"] == "20260727"
    assert result["critical_failures"] == []
    assert len(result["input_digest"]) == 64


def test_freshness_blocks_mixed_index_date_without_wall_clock_fallback():
    payload = _payload()
    payload["indices"][1]["trade_date"] = "20260724"
    result = assess_eod_freshness(payload)
    assert result["status"] == "blocked"
    assert result["forecast_eligible"] is False
    assert result["critical_failures"][0]["check"] == "indices"
    assert "20260724" in result["critical_failures"][0]["data_dates"]


def test_freshness_blocks_stale_or_missing_stock_history():
    payload = _payload()
    payload["stocks"][0]["history_tail"] = [{"trade_date": "20260724"}]
    payload["stocks"][1]["history_tail"] = []
    result = assess_eod_freshness(payload)
    assert result["forecast_eligible"] is False
    failure = next(
        item for item in result["critical_failures"]
        if item["check"] == "stock_history"
    )
    assert failure["blocked_codes"] == ["002475", "601138"]


def test_freshness_degrades_only_stale_target_when_other_targets_are_ready():
    payload = _payload()
    payload["stocks"][0]["history_tail"] = [{"trade_date": "20260724"}]
    result = assess_eod_freshness(payload)
    assert result["status"] == "degraded"
    assert result["forecast_eligible"] is True
    assert result["eligible_codes"] == ["002475"]
    assert result["blocked_targets"] == [{
        "code": "601138",
        "reason": "history_trade_date_missing_or_mismatch",
        "data_date": "20260724",
        "expected_trade_date": "20260727",
    }]


def test_freshness_blocks_missing_market_trade_date_instead_of_using_today():
    payload = _payload()
    payload["market_overview"] = {}
    result = assess_eod_freshness(payload)
    assert result["forecast_eligible"] is False
    assert result["trade_date"] is None
    assert result["critical_failures"][0] == {
        "check": "market_overview",
        "reason": "trade_date_missing_or_invalid",
    }


def test_freshness_digest_changes_when_input_dates_change():
    ready = assess_eod_freshness(_payload())
    changed_payload = _payload()
    changed_payload["stocks"][0]["history_tail"][-1]["trade_date"] = "20260728"
    changed = assess_eod_freshness(changed_payload)
    assert changed["input_digest"] != ready["input_digest"]
