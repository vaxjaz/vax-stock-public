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
