# -*- coding: utf-8 -*-

from vaxstock.report.research_eod import build_research_eod_markdown


def test_research_eod_renders_shadow_anchor_probability_without_action():
    data = {
        "generated_at": "2026-07-29 05:00:00",
        "market_regime": "panic",
        "market_overview": {"trade_date": "20260728"},
        "stocks": [],
    }
    summary = {
        "as_of_trade_date": "20260728",
        "status": "blocked",
        "production_eligible": False,
        "stages": {
            "anchor": {
                "status": "written",
                "metrics": {
                    "anchors": 4,
                    "equity_majority_direction": "down",
                },
            },
            "anchor_forecast": {
                "status": "estimated",
                "metrics": {
                    "horizons": {
                        "1": {
                            "absolute_direction": "down",
                            "probability_positive_return": 0.33,
                            "direction": "negative_excess",
                            "probability_positive_excess": 0.42,
                            "base_probability_positive_excess": 0.51,
                            "primary_condition": {
                                "independent_dates": 8,
                            },
                            "evidence_label": (
                                "estimated_not_oos_validated"
                            ),
                        },
                    },
                },
            },
        },
    }

    markdown = build_research_eod_markdown(
        data,
        research_summary=summary,
    )

    assert "anchors=4" in markdown
    assert "equity_majority_direction=down" in markdown
    assert (
        "| T+1 | down | 33.0% | negative_excess | 42.0% | 8"
        in markdown
    )
    assert "estimated_not_oos_validated" in markdown
    assert "shadow" in markdown
