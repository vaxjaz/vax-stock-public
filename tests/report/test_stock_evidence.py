# -*- coding: utf-8 -*-

from vaxstock.report.stock_evidence import format_earnings, format_live_history


def test_formats_real_live_history_without_relabeling_rate():
    text = format_live_history({
        "available": True, "evaluated": 6, "avg_excess": 0.0076,
        "positive_excess_count": 4,
    })
    assert text == "live已核验6次，平均超额+0.76%，4/6次跑赢指数"


def test_formats_financials_and_scheduled_disclosure():
    text = format_earnings({
        "latest_report": {
            "period": "20260331", "net_profit_yoy": 102.5485,
            "revenue_yoy": None, "roe": 6.1778, "gross_margin": 7.3505,
        },
        "next_report": {"period": "20260630", "expected_ann_date": "20260812", "status": "scheduled"},
    })
    assert "财报 2026Q1" in text
    assert "净利同比+102.55%" in text
    assert "营收同比" not in text
    assert "预计披露 2026-08-12（2026H1，交易所预约，可能修订）" in text


def test_missing_disclosure_is_explicit():
    assert format_earnings({}) == "财报待验证；预计披露待公布"