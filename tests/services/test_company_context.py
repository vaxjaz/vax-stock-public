# -*- coding: utf-8 -*-

from vaxstock.services import company_context as cc


def _payload():
    return {
        "market_overview": {"trade_date": "20260703"},
        "tracks": [{"track_name": "AI", "available": True, "position_ceiling": "medium"}],
    }


def test_pending_source_is_explicit_and_not_available():
    item = {
        "code": "002475",
        "configured_name": "Luxshare",
        "concepts": ["AI hardware"],
        "metrics": {"np_yoy": 12.3},
        "realtime": {"name": "Luxshare"},
    }

    ctx = cc.build_context_from_payload_item(item, _payload(), "20260706")

    assert ctx["line"] == "E_context"
    assert ctx["earnings"]["available"] is False
    assert ctx["earnings"]["source_status"] == "pending_source"
    assert ctx["earnings"]["metric_snapshot"]["np_yoy"] == 12.3
    assert ctx["company_events"]["available"] is False
    assert ctx["company_events"]["source_status"] == "pending_source"
    assert ctx["industry_forward"]["source_status"] == "concept_tags_only"


def test_explicit_earnings_events_and_industry_points_are_preserved():
    item = {
        "code": "002475",
        "configured_name": "Luxshare",
        "concepts": ["AI hardware"],
        "metrics": {"np_yoy": 12.3},
        "company_context": {
            "earnings": {
                "source": "manual_fixture",
                "latest_report": {
                    "period": "2026Q1",
                    "ann_date": "20260430",
                    "net_profit_yoy": 20.5,
                },
                "next_report": {
                    "period": "2026H1",
                    "expected_ann_date": "20260825",
                    "status": "scheduled",
                },
            },
            "company_events": [
                {
                    "event_type": "order",
                    "event_date": "20260701",
                    "source": "manual_fixture",
                    "title": "new order",
                    "summary": "signed order",
                    "impact_hint": "positive",
                    "confidence": 0.8,
                }
            ],
            "industry_forward": {
                "forward_points": [
                    {
                        "topic": "AI server demand",
                        "source": "manual_fixture",
                        "summary": "demand remains strong",
                        "impact_hint": "positive",
                        "confidence": 0.7,
                    }
                ]
            },
        },
    }

    ctx = cc.build_context_from_payload_item(item, _payload(), "20260706")
    summary = cc.summarize_context(ctx)

    assert ctx["earnings"]["available"] is True
    assert ctx["earnings"]["source_status"] == "provided"
    assert ctx["earnings"]["latest_report"]["period"] == "2026Q1"
    assert ctx["earnings"]["next_report"]["expected_ann_date"] == "20260825"
    assert ctx["company_events"]["events"][0]["event_type"] == "order"
    assert ctx["industry_forward"]["forward_points"][0]["topic"] == "AI server demand"
    assert summary == {
        "earnings_status": "provided",
        "next_report_date": "20260825",
        "company_event_count": 1,
        "industry_status": "provided",
    }


def test_context_uses_real_tushare_fields_from_payload_item():
    item = {
        "code": "002475",
        "configured_name": "Luxshare",
        "concepts": ["AI hardware"],
        "metrics": {"np_yoy": 12.3},
        "fina_history": [
            {
                "end_date": "20260331",
                "ann_date": "20260425",
                "source": "tushare.fina_indicator",
                "raw_fields": ["ts_code", "end_date", "ann_date", "netprofit_yoy", "or_yoy"],
                "period_type": "Q1",
                "np_yoy": 30.5,
                "or_yoy": 18.2,
            }
        ],
        "forecast": {
            "source": "tushare.forecast",
            "raw_fields": ["ts_code", "ann_date", "end_date", "type", "p_change_min", "p_change_max"],
            "end_date": "20260630",
            "ann_date": "20260710",
            "type": "preincrease",
            "p_change_min": 50,
            "p_change_max": 80,
            "summary": "profit forecast",
        },
        "disclosure_schedule": [
            {
                "ts_code": "002475.SZ",
                "ann_date": "20260701",
                "end_date": "20260630",
                "pre_date": "20260820",
                # Tushare DataFrame.to_dict() returns an IEEE NaN for this
                # empty production field rather than Python None.
                "actual_date": float("nan"),
                "modify_date": "20260701",
            }
        ],
        "express": {
            "source": "tushare.express",
            "raw_fields": ["ts_code", "ann_date", "end_date", "yoy_net_profit", "perf_summary"],
            "end_date": "20260331",
            "ann_date": "20260420",
            "yoy_net_profit": -5.0,
            "perf_summary": "express summary",
        },
    }

    ctx = cc.build_context_from_payload_item(item, _payload(), "20260706")

    assert ctx["earnings"]["available"] is True
    assert ctx["earnings"]["source"] == "tushare.fina_indicator"
    latest = ctx["earnings"]["latest_report"]
    assert latest["period"] == "20260331"
    assert latest["ann_date"] == "20260425"
    assert latest["raw_fields"] == ["ts_code", "end_date", "ann_date", "netprofit_yoy", "or_yoy"]
    assert ctx["earnings"]["next_report"]["status"] == "scheduled"
    assert ctx["earnings"]["next_report"]["expected_ann_date"] == "20260820"
    assert ctx["earnings"]["next_report"]["actual_ann_date"] is None
    assert ctx["earnings"]["next_report"]["source"] == "tushare.disclosure_date"

    events = ctx["company_events"]["events"]
    assert [event["source"] for event in events] == ["tushare.forecast", "tushare.express"]
    assert [event["event_type"] for event in events] == ["guidance", "earnings"]
    assert events[0]["impact_hint"] == "positive"
    assert events[1]["impact_hint"] == "negative"
    assert events[0]["raw_fields"] == ["ts_code", "ann_date", "end_date", "type", "p_change_min", "p_change_max"]
def test_normalized_context_round_trips_from_snapshot():
    item = {"code": "002475", "configured_name": "Luxshare", "metrics": {}}
    ctx = cc.build_context_from_payload_item(item, _payload(), "20260706")
    snap_ctx = cc.build_context_from_snapshot(
        {"trade_date": "20260703", "code": "002475", "company_context": ctx},
        "20260706",
    )

    assert snap_ctx == ctx


if __name__ == "__main__":
    import sys

    tests = sorted((n, f) for n, f in globals().items() if n.startswith("test_"))
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  [FAIL] {name}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
