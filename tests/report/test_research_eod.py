# -*- coding: utf-8 -*-

from vaxstock.report.research_eod import build_research_eod_markdown


def _context():
    metric = {
        "current": 40.0,
        "reference_5_sessions": 20.0,
        "change_5_sessions": 20.0,
        "reference_5_sessions_trade_date": "20260721",
    }
    return {
        "calculation_version": "eod_market_anchor_v1",
        "history": {
            "report_session_count": 6,
            "five_session_reference_trade_date": "20260721",
        },
        "states": {
            "breadth_state": "repairing_but_long_term_majority_below_ma200",
            "funding_state": "short_outflow_medium_inflow_divergence",
            "deleveraging_state": "not_deleveraging_high_leverage_fragility",
            "ai_state": "demand_proxy_intact_price_reversal_not_confirmed",
        },
        "market": {
            "indices": [{
                "symbol": "sh000001", "name": "上证指数",
                "price": 3800, "change_pct": 0.5,
                "source_trade_date": "20260728",
            }],
            "participation": {
                "up_count": 3000, "down_count": 2000,
                "up_ratio_pct": 60, "limit_up_count": 80,
                "limit_down_count": 10,
            },
            "style": {
                "sh_change_pct": 0.5,
                "growth_average_change_pct": -0.2,
                "sh_minus_growth_pp": 0.7,
            },
            "breadth": {
                "above_ma60_pct": metric,
                "above_ma200_pct": {**metric, "current": 18.0},
                "ma250_bias_pct": {**metric, "current": 0.2},
                "latest_date": "20260728",
                "valid_count_ma60": 4900,
                "valid_count_ma200": 4800,
            },
            "funding": {
                "etf_net_sub_5d_yi": -300,
                "etf_net_sub_20d_yi": 400,
                "latest_date": "20260728",
                "etf_net_sub_5d_history": metric,
                "etf_net_sub_20d_history": metric,
            },
            "margin": {
                "ratio_pct": {**metric, "current": 12.2},
                "percentile_3y": 98.9,
                "latest_date": "20260727",
                "stale": True,
            },
            "valuation_credit": {
                "erp_pct": 5.1, "erp_percentile_5y": 25.0,
                "hs300_pe_ttm": 14.5, "cn_10y_yield_pct": 1.7,
                "erp_latest_date": "20260728",
                "turnover_percentile_3y": 56,
                "turnover_latest_date": "20260728",
                "m1_yoy_pct": 4, "m1_mom_delta_pp": -1.5,
                "m1_latest_month": "202606",
                "social_financing_pulse_yoy_pct": -9.2,
                "social_financing_acceleration_pp": -4.7,
                "social_financing_latest_month": "202606",
            },
        },
        "ai_anchors": {
            "price_anchors": [{
                "symbol": "NVDA", "name": "英伟达", "price": 220,
                "daily_change_pct": -2.0, "return_5_sessions_pct": 5.0,
                "source_date": "20260728",
            }],
            "demand_proxy": {
                "revenue_yoy_pct": 85.2, "revenue_qoq_pct": 19.8,
                "revenue_acceleration_pp": 0.3,
                "latest_revenue_busd": 816.2,
            },
            "price_gate": {
                "gate_open": False, "sox_close": 12356,
                "sox_ma50": 12705, "sox_vs_ma50_pct": -2.75,
                "sox_momentum_1m_pct": -4.7,
            },
            "local_risk": {
                "qvix_300": metric,
                "qvix_cyb": {**metric, "current": 39.5},
                "basket_turnover_percentile_pct": metric,
                "basket_52w_position_pct": metric,
            },
            "position_ceiling": "减档",
            "capital_cycle": {
                "available": False,
                "missing": ["头部云厂point-in-time资本开支", "头部云厂自由现金流"],
                "conclusion_limit": "现有数据不能判断资本周期顶部",
            },
        },
    }


def _data():
    return {
        "generated_at": "2026-07-29 05:00:12",
        "market_overview": {"trade_date": "20260728"},
        "freshness": {"status": "ready"},
        "analyst_context": _context(),
        "stocks": [{"group": "holding", "code": "601138"}],
    }


def test_research_eod_is_conclusion_first_and_omits_stock_details():
    markdown = build_research_eod_markdown(_data())

    assert "# EOD市场与AI锚 20260728" in markdown
    assert "大盘修复是真实的" in markdown
    assert "当前不是“杀杠杆”" in markdown
    assert "价格锚没有确认真反转" in markdown
    assert "601138" not in markdown
    assert "新研究链路" not in markdown
    assert "right_side_score" not in markdown


def test_research_eod_renders_recalculated_environment_and_anchor_data():
    markdown = build_research_eod_markdown(_data())

    assert "全市场站上MA60 | 40.00% | 20.00% | +20.00pp" in markdown
    assert "ETF滚动5日净申赎 | -300.00亿元" in markdown
    assert "融资占比3年分位 | 98.90%" in markdown
    assert "英伟达 (NVDA) | 220.0000 | -2.00% | 5.00%" in markdown
    assert "AI需求景气代理（不是Capex）" in markdown
    assert "**未接入：** 头部云厂point-in-time资本开支" in markdown


def test_missing_analysis_never_falls_back_to_old_scores():
    markdown = build_research_eod_markdown({
        "generated_at": "2026-07-29 05:00:12",
        "market_overview": {"trade_date": "20260728"},
        "stocks": [{"code": "601138", "right_side_score": 5}],
    })

    assert "大环境与锚重算未完成" in markdown
    assert "未使用旧评分" in markdown
    assert "601138" not in markdown
    assert "5" not in markdown.replace("20260728", "")
