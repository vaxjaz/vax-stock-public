# -*- coding: utf-8 -*-

from vaxstock.analysis.eod_market import build_eod_market_analysis


def _payload(day, step):
    date = f"202607{day:02d}"
    source_date = f"2026-07-{day:02d}"
    return {
        "market_regime": "value",
        "market_overview": {
            "trade_date": date, "up_count": 3000,
            "down_count": 2000, "flat_count": 0, "total": 5000,
            "limit_up_count": 80, "limit_down_count": 10,
        },
        "indices": [{
            "symbol": "sh000001", "name": "上证指数", "price": 3800 + step,
            "change_pct": 0.5, "trade_date": date, "source": "tushare",
        }],
        "regime_audit": {"inputs": {
            "sh_change_pct": 0.5, "growth_avg_change_pct": -0.2,
            "sh_minus_growth_pct": 0.7,
        }},
        "macro": {"indicators": {
            "breadth": {
                "above_ma60_pct": 20 + step * 2,
                "above_ma200_pct": 10 + step,
                "ma250_bias_pct": -5 + step,
                "latest_date": date,
            },
            "etf_net_sub": {
                "value_5d_yi": 200 - step * 100,
                "value_20d_yi": 900 - step * 80,
                "latest_date": date,
            },
            "margin_ratio": {
                "ratio_pct": 11 + step * 0.2,
                "percentile_3y": 98, "latest_date": date,
                "stale": False,
            },
            "turnover": {"percentile_3y": 55, "latest_date": date},
            "hs300_erp": {
                "pe_ttm": 14, "yield_10y_pct": 1.7, "erp_pct": 5,
                "percentile_5y": 25, "latest_date": date,
            },
            "m1_yoy": {"value_pct": 4, "mom_delta_pp": -1.5, "latest_month": "202606"},
            "sf_pulse": {"pulse_yoy_pct": -9, "accel_pp": -4, "latest_month": "202606"},
        }},
        "us_market": {
            "stocks": [{"symbol": "NVDA", "price": 100 + step, "change_pct": 1, "date": source_date}],
            "etfs": [
                {"symbol": "SOXX", "price": 500 + step, "change_pct": 1, "date": source_date},
                {"symbol": "QQQ", "price": 700 + step, "change_pct": 1, "date": source_date},
            ],
            "indices": [{"symbol": "^VIX", "price": 20 - step, "change_pct": -1, "date": source_date}],
            "macro": [
                {"symbol": "^TNX", "price": 4 + step / 100, "change_pct": 0.1, "date": source_date},
                {"symbol": "DX-Y.NYB", "price": 100 - step / 10, "change_pct": -0.1, "date": source_date},
            ],
        },
        "tracks": [{
            "track_name": "AI算力", "position_ceiling": "减档",
            "signals": {
                "prosperity": {"status": "已证实", "yoy_pct": 80, "qoq_pct": 10, "accel_pp": 1},
                "sox_gate": {"status": "已证实", "gate_open": False, "sox_close": 490, "sox_ma50": 500, "mom_1m_pct": -2},
                "qvix": {"qvix_300": 25 - step, "qvix_cyb": 45 - step},
                "crowding": {"turnover_pctile": 0.5 + step / 100, "basket_52w_pos": 0.4 + step / 100},
            },
        }],
    }


def test_recalculation_uses_t_minus_five_and_emits_directional_states():
    rows = [_payload(21 + index, index) for index in range(6)]
    result = build_eod_market_analysis(rows[-1], rows[:-1])

    assert result["history"]["five_session_reference_trade_date"] == "20260721"
    assert result["market"]["breadth"]["above_ma60_pct"]["change_5_sessions"] == 10
    assert result["market"]["margin"]["ratio_pct"]["change_5_sessions"] == 1
    assert result["states"] == {
        "breadth_state": "repairing_but_long_term_majority_below_ma200",
        "funding_state": "short_outflow_medium_inflow_divergence",
        "deleveraging_state": "not_deleveraging_high_leverage_fragility",
        "ai_state": "demand_proxy_intact_price_reversal_not_confirmed",
    }
    nvda = result["ai_anchors"]["price_anchors"][0]
    assert round(nvda["return_5_sessions_pct"], 6) == 5.0
    assert result["ai_anchors"]["capital_cycle"]["available"] is False


def test_missing_inputs_remain_none_and_never_become_neutral_defaults():
    payload = {"market_overview": {"trade_date": "20260728"}}
    result = build_eod_market_analysis(payload)

    assert result["market"]["breadth"]["above_ma60_pct"]["current"] is None
    assert result["market"]["margin"]["percentile_3y"] is None
    assert result["ai_anchors"]["price_anchors"][0]["status"] == "missing"
    assert result["states"]["ai_state"] == "insufficient_data"
