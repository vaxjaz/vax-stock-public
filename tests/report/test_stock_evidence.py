# -*- coding: utf-8 -*-

from vaxstock.report.stock_evidence import (
    format_earnings, format_history_verdict, format_live_history,
)


def test_formats_real_live_history_without_relabeling_rate():
    text = format_live_history({
        "available": True, "evaluated": 6, "avg_ret": 0.0063,
        "positive_ret_count": 4,
    })
    assert text == "全部C线历史：live已核验6次，平均收益+0.63%，4/6次收益为正"


def test_formats_key_c_line_path_horizons():
    text = format_live_history({
        "available": True,
        "evaluated": 6,
        "avg_ret": 0.0063,
        "positive_ret_count": 4,
        "latest_horizon": "5",
        "key_horizons": ["1", "5", "10", "30"],
        "horizons": {
            "1": {"evaluated": 6, "avg_ret": 0.0063, "positive_ret_count": 4},
            "2": {"evaluated": 5, "avg_ret": 0.0080, "positive_ret_count": 3},
            "5": {"evaluated": 2, "avg_ret": -0.0080, "positive_ret_count": 0},
        },
    })

    assert text == (
        "全部C线历史：T+1 6次，平均收益+0.63%，4/6次收益为正"
        "；T+now（当前T+5） 2次，平均收益-0.80%，0/2次收益为正"
    )


def test_formats_latest_t_now_even_beyond_t30():
    text = format_live_history({
        "available": True,
        "evaluated": 6,
        "latest_horizon": "47",
        "key_horizons": ["1", "5", "10", "30"],
        "horizons": {
            "1": {"evaluated": 6, "avg_ret": 0.01, "positive_ret_count": 4},
            "30": {"evaluated": 2, "avg_ret": 0.03, "positive_ret_count": 2},
            "47": {"evaluated": 1, "avg_ret": -0.02, "positive_ret_count": 0},
        },
    })
    assert "T+30 2次" in text
    assert "T+now（当前T+47） 1次" in text


def test_formats_matching_history_verdict_plainly():
    text = format_history_verdict({
        "latest_horizon": "1",
        "horizon_verdicts": {
            "1": {
                "path_evaluated": 2,
                "evaluated": 2,
                "all_evaluated": 7,
                "avg_ret": 0.019,
                "absolute_action_hit_count": 2,
                "absolute_action_hit_rate": 1.0,
                "sample_dates": ["20260706", "20260707"],
            },
        },
        "verdict": "insufficient",
    })
    assert text == (
        "与今天相同动作的C线历史：T+now（当前T+1） 同动作2/7次/平均收益+1.90%/"
        "动作命中2/2（100.00%）/样本日20260706、20260707；样本不足，不改变今天动作"
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

def test_old_summary_does_not_invent_positive_return_count():
    text = format_live_history({
        "available": True, "evaluated": 2, "avg_ret": -0.01,
    })
    assert text == "全部C线历史：live已核验2次，平均收益-1.00%"
    assert "0/2" not in text


def test_matching_history_verdict_always_shows_t_now():
    text = format_history_verdict({
        "latest_horizon": "7",
        "horizon_verdicts": {
            "1": {
                "evaluated": 4,
                "avg_ret": -0.01,
                "positive_ret_rate": 0.25,
            },
            "7": {
                "evaluated": 1,
                "avg_ret": -0.08,
                "positive_ret_rate": 0.0,
            },
        },
        "verdict": "insufficient",
    })
    assert "T+1 同动作4次" in text
    assert "T+now（当前T+7） 同动作1次" in text
    assert "样本不足，不改变今天动作" in text
