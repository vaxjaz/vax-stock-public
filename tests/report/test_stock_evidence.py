# -*- coding: utf-8 -*-

from vaxstock.report.stock_evidence import format_earnings, format_live_history


def test_formats_real_live_history_without_relabeling_rate():
    text = format_live_history({
        "available": True, "evaluated": 6, "avg_excess": 0.0076,
        "positive_excess_count": 4,
    })
    assert text == "live已核验6次，平均超额+0.76%，4/6次跑赢指数"


def test_formats_key_c_line_path_horizons():
    text = format_live_history({
        "available": True,
        "evaluated": 6,
        "avg_excess": 0.0076,
        "positive_excess_count": 4,
        "key_horizons": ["1", "5", "10", "30"],
        "horizons": {
            "1": {"evaluated": 6, "avg_excess": 0.0076, "positive_excess_count": 4},
            "2": {"evaluated": 5, "avg_excess": 0.0100, "positive_excess_count": 3},
            "5": {"evaluated": 2, "avg_excess": -0.0050, "positive_excess_count": 1},
        },
    })

    assert text == (
        "T+1 6\u6b21\uff0c\u5e73\u5747\u8d85\u989d+0.76%\uff0c4/6\u6b21\u8dd1\u8d62\u6307\u6570"
        "\uff1bT+5 2\u6b21\uff0c\u5e73\u5747\u8d85\u989d-0.50%\uff0c1/2\u6b21\u8dd1\u8d62\u6307\u6570"
    )


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