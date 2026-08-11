# -*- coding: utf-8 -*-

from vaxstock.report.market_context import render_market_background_lines


def _background():
    return {
        "baseline_trade_date": "20260713",
        "market_regime_text": "恐慌防守",
        "breadth": {
            "up_count": 801,
            "down_count": 4683,
            "limit_up_count": 36,
            "limit_down_count": 211,
        },
        "macro_regime": "🟡 中性",
        "macro": {
            "macro_regime": "🟡 中性",
            "bullish_count": 5,
            "bearish_count": 8,
            "indicators": {
                "etf_net_sub": {
                    "value_5d_yi": 87.7574,
                    "value_20d_yi": -534.4934,
                    "signal_5d": "✅✅",
                    "signal_20d": "❌❌",
                    "latest_date": "20260710",
                },
                "margin_ratio": {
                    "ratio_pct": 11.8327,
                    "percentile_3y": 96.7985,
                    "signal": "❌❌",
                    "latest_date": "20260710",
                    "stale": True,
                },
                "turnover": {
                    "turnover_rate": 0.91,
                    "percentile_3y": 87.194,
                    "signal": "❌",
                    "proxy_code": "000300.SH",
                    "latest_date": "20260710",
                },
                "hs300_erp": {
                    "pe_ttm": 14.35,
                    "yield_10y_pct": 1.7398,
                    "yield_source": "akshare",
                    "erp_pct": 5.2288,
                    "percentile_5y": 27.1991,
                    "signal": "❌",
                    "latest_date": "20260710",
                },
                "breadth": {
                    "available": True,
                    "above_ma60_pct": 14.081,
                    "above_ma60_signal": "✅",
                    "above_ma200_pct": 19.3894,
                    "above_ma200_signal": "✅",
                    "ma250_bias_pct": 4.677,
                    "ma250_bias_signal": "❌",
                    "latest_date": "20260710",
                },
                "m1_yoy": {
                    "value_pct": 5.5,
                    "mom_delta_pp": 0.5,
                    "percentile_10y": 55.0,
                    "signal": "✅",
                    "latest_month": "202605",
                },
                "sf_pulse": {
                    "pulse_yoy_pct": -4.5635,
                    "accel_pp": -1.3403,
                    "signal": "❌",
                    "latest_month": "202605",
                },
            },
            "errors": [],
        },
        "ai_track": {
            "track_name": "AI算力",
            "available": True,
            "position_ceiling": "进攻档 (赛道上限~高位, 可加)",
            "summary_lines": [
                "【景气·NVDA营收代理】✅扩张加速  [已证实]",
                "【海外闸门·SOX】✅开放  收12967.2 / MA50 12578.6 / 近1月6.2%",
                "【本土情绪·QVIX】⚠️情绪偏紧  300ETF 23.15 / 创业板 42.63",
                "【篮子拥挤度】换手分位 70% / 篮子52周位置 62%  [已证实]",
            ],
            "vetoes": [],
            "pending": [],
        },
    }


def test_renders_frozen_market_macro_and_ai_evidence():
    text = " ".join(render_market_background_lines(_background()))
    assert "上涨801家；下跌4683家；涨停36家；跌停211家" in text
    assert "支持计数5，风险计数8" in text
    assert "近5日+87.76亿元(✅✅)" in text
    assert "融资买入额/沪深成交额: 11.83%" in text
    assert "数据日2026-07-10，数据滞后" in text
    assert "市场换手率代理: 0.91%" in text
    assert "沪深300风险溢价: ERP 5.23%" in text
    assert "站上MA60 14.08%(✅)" in text
    assert "M1同比: +5.50%" in text
    assert "社融脉冲: 同比-4.56%" in text
    assert "AI算力" in text
    assert "NVDA营收代理" in text
    assert "SOX" in text
    assert "QVIX" in text
    assert "篮子拥挤度" in text
    assert "否决项: 0项" in text
    assert "本段是赛道背景，不是买卖指令" in text


def test_missing_macro_and_ai_details_are_explicit():
    text = " ".join(render_market_background_lines({
        "baseline_trade_date": "20260713",
        "market_regime_text": "恐慌防守",
        "macro_regime": "🟡 中性",
        "ai_position_ceiling": "进攻档",
    }))
    assert "7维明细: 待确认" in text
    assert "当前任务未冻结AI赛道明细" in text
    assert "上涨待确认家" in text
