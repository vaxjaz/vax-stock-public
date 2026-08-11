# -*- coding: utf-8 -*-

from vaxstock.report.research_eod import build_research_eod_markdown
from tests.report.test_research_eod import _data


def test_unvalidated_shadow_probability_is_not_rendered():
    data = _data()
    summary = {
        "stages": {
            "anchor_forecast": {
                "status": "estimated",
                "metrics": {
                    "horizons": {
                        "1": {
                            "probability_positive_return": 0.66,
                            "evidence_label": "estimated_not_oos_validated",
                        }
                    }
                },
            }
        }
    }

    markdown = build_research_eod_markdown(data, research_summary=summary)

    assert "66.0%" not in markdown
    assert "shadow" not in markdown
    assert "estimated_not_oos_validated" not in markdown
    assert "NVDA" in markdown
    assert "SOX价格闸门" in markdown
