# -*- coding: utf-8 -*-

from vaxstock.report.research_eod import build_research_eod_markdown


def _data():
    return {
        "generated_at": "2026-07-29 05:00:12",
        "market_regime": "panic",
        "regime_audit": {
            "raw_regime": "panic",
            "reason": "limit_down_count=62 > 50",
        },
        "market_overview": {
            "trade_date": "20260728",
            "up_count": 2603,
            "down_count": 2769,
            "limit_up_count": 71,
            "limit_down_count": 62,
        },
        "indices": [
            {"name": "上证指数", "price": 3813.31, "change_pct": -1.16},
        ],
        "freshness": {"status": "ready"},
        "stocks": [
            {
                "group": "holding",
                "code": "601138",
                "right_side_score": 2.0,
            },
            {
                "group": "watchlist",
                "code": "002475",
                "right_side_score": 3.5,
            },
        ],
    }


def _blocked_summary():
    return {
        "as_of_trade_date": "20260728",
        "status": "blocked",
        "production_eligible": False,
        "blocking_stage": "select",
        "reason": "group_outcomes_empty",
        "stages": {
            "snapshot": {
                "status": "written",
                "metrics": {"observations": 125, "factors": 2214},
            },
            "curve": {
                "status": "written",
                "metrics": {"outputs": 63, "candidate_hits": 0},
            },
            "group": {
                "status": "written",
                "metrics": {
                    "stocks": 41,
                    "memberships": 42,
                    "systemic_event_state": "none",
                    "systemic_event_direction": None,
                    "event_stock_breadth": 0.0,
                    "systemic_event_families": 0,
                },
            },
            "outcome": {
                "status": "empty",
                "metrics": {"samples_ready": 0, "samples_written": 0},
            },
            "select": {
                "status": "blocked",
                "reason": "group_outcomes_empty",
                "metrics": {},
            },
        },
    }


def test_research_eod_never_renders_legacy_scoring_fallback():
    markdown = build_research_eod_markdown(
        _data(),
        research_summary=_blocked_summary(),
    )

    assert "# 新研究 EOD 20260728" in markdown
    assert "**ABSTAIN" in markdown
    assert "group_outcomes_empty" in markdown
    assert "量化框架 v1.4" not in markdown
    assert "因子有效性排名" not in markdown
    assert "强买入信号" not in markdown
    assert "可考虑介入" not in markdown
    assert "评分2.0" not in markdown
    assert "601138" not in markdown


def test_research_eod_exposes_pipeline_and_data_facts():
    markdown = build_research_eod_markdown(
        _data(),
        research_summary=_blocked_summary(),
    )

    assert "涨2603 / 跌2769 / 涨停71 / 跌停62" in markdown
    assert "基础快照: **written**" in markdown
    assert "observations=125" in markdown
    assert "连续曲线: **written**" in markdown
    assert "动态分组: **written**" in markdown
    assert "因子选择: **blocked**" in markdown
    assert "blocking_stage: select" in markdown
    assert "持仓1 / 观察池1 / 合计2" in markdown


def test_research_eod_anchors_track_section_to_report_trade_date():
    markdown = build_research_eod_markdown(
        _data(),
        research_summary=_blocked_summary(),
        track_results=[{
            "track_name": "AI算力",
            "date": "2026-07-29",
            "available": True,
            "position_ceiling": "待验证",
        }],
    )

    assert "# 新研究 EOD 20260728" in markdown
    assert "source_date=20260729（与报告交易日不一致）" in markdown
