# -*- coding: utf-8 -*-
"""Company event / earnings context schema.

This layer is non-scoring context for C-line predictions and D-line LLM tasks.
It does not fetch data and it does not invent missing events.  When no verified
source is present, fields stay explicit as pending_source so downstream prompts
can use the absence honestly.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


SCHEMA_VERSION = 1
LINE_NAME = "E_context"

ALLOWED_EVENT_TYPES = {
    "earnings",
    "guidance",
    "product",
    "order",
    "policy",
    "financing",
    "shareholder",
    "litigation",
    "industry",
    "other",
}

REQUIRED_EVENT_FIELDS = [
    "event_type",
    "event_date",
    "source",
    "title",
    "summary",
    "impact_hint",
    "confidence",
]


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return None


def _metric_snapshot(metrics: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "source": "A_eod.metrics",
        "period": "unknown",
        "note": "These are existing EOD factors, not a verified earnings-calendar node.",
    }
    has_value = False
    for key in ("np_yoy", "holder_change_pct", "pe_percentile", "pb_percentile"):
        if key in metrics:
            out[key] = metrics.get(key)
            has_value = True
    out["available"] = has_value
    return out


def _normalize_report_node(raw: Dict[str, Any]) -> Dict[str, Any]:
    node = _as_dict(raw)
    return {
        "period": _first_non_empty(node.get("period"), node.get("report_period")),
        "report_type": _clean_text(node.get("report_type")),
        "ann_date": _first_non_empty(node.get("ann_date"), node.get("announcement_date")),
        "source": _clean_text(node.get("source")),
        "net_profit_yoy": node.get("net_profit_yoy"),
        "revenue_yoy": node.get("revenue_yoy"),
        "deducted_net_profit_yoy": node.get("deducted_net_profit_yoy"),
    }


def _normalize_next_report(raw: Dict[str, Any]) -> Dict[str, Any]:
    node = _as_dict(raw)
    return {
        "expected_ann_date": _first_non_empty(node.get("expected_ann_date"), node.get("ann_date")),
        "period": _first_non_empty(node.get("period"), node.get("report_period")),
        "source": _clean_text(node.get("source")),
        "status": _clean_text(node.get("status")) or "pending_source",
        "near_target_window": node.get("near_target_window"),
        "distance_calendar_days": node.get("distance_calendar_days"),
        "note": _clean_text(node.get("note")),
    }


def normalize_earnings(raw: Any, metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    earnings = _as_dict(raw)
    explicit_source = _first_non_empty(
        earnings.get("source"),
        _as_dict(earnings.get("latest_report")).get("source"),
        _as_dict(earnings.get("next_report")).get("source"),
    )
    available = bool(explicit_source or earnings.get("latest_report") or earnings.get("next_report"))
    return {
        "available": available,
        "source_status": "provided" if available else "pending_source",
        "source": explicit_source,
        "latest_report": _normalize_report_node(earnings.get("latest_report") or {}),
        "next_report": _normalize_next_report(earnings.get("next_report") or {}),
        "metric_snapshot": _metric_snapshot(metrics or {}),
        "usage": "context_only_not_scoring",
    }


def normalize_company_events(raw: Any) -> Dict[str, Any]:
    events = []
    for idx, event in enumerate(_as_list(raw)):
        src = _as_dict(event)
        event_type = _clean_text(src.get("event_type")) or "other"
        if event_type not in ALLOWED_EVENT_TYPES:
            event_type = "other"
        events.append({
            "event_id": _clean_text(src.get("event_id")) or f"event_{idx + 1}",
            "event_type": event_type,
            "event_date": _first_non_empty(src.get("event_date"), src.get("ann_date")),
            "source": _clean_text(src.get("source")),
            "title": _clean_text(src.get("title")),
            "summary": _clean_text(src.get("summary")),
            "impact_hint": _clean_text(src.get("impact_hint")) or "unknown",
            "confidence": src.get("confidence"),
            "url": _clean_text(src.get("url")),
        })
    return {
        "available": bool(events),
        "source_status": "provided" if events else "pending_source",
        "required_event_fields": list(REQUIRED_EVENT_FIELDS),
        "events": events,
        "usage": "context_only_not_scoring",
    }


def normalize_industry_forward(raw: Any, *, concepts: Optional[Iterable[str]] = None,
                               tracks: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Any]:
    data = _as_dict(raw)
    points = []
    for point in _as_list(data.get("forward_points")):
        p = _as_dict(point)
        points.append({
            "topic": _clean_text(p.get("topic")),
            "source": _clean_text(p.get("source")),
            "summary": _clean_text(p.get("summary")),
            "impact_hint": _clean_text(p.get("impact_hint")) or "unknown",
            "confidence": p.get("confidence"),
        })
    track_context = []
    for track in tracks or []:
        if not isinstance(track, dict):
            continue
        track_context.append({
            "track_name": track.get("track_name"),
            "available": track.get("available"),
            "position_ceiling": track.get("position_ceiling"),
            "summary_lines": track.get("summary_lines"),
        })
    return {
        "available": bool(points),
        "source_status": "provided" if points else "concept_tags_only",
        "concept_tags": list(concepts or []),
        "track_context": track_context,
        "forward_points": points,
        "note": "Concept tags and track context are routing context; forward points require explicit sources.",
        "usage": "context_only_not_scoring",
    }


def build_context_from_payload_item(item: Dict[str, Any], payload: Dict[str, Any],
                                    target_trade_date: str) -> Dict[str, Any]:
    item = _as_dict(item)
    payload = _as_dict(payload)
    raw = _as_dict(item.get("company_context") or item.get("event_context"))
    rt = _as_dict(item.get("realtime"))
    metrics = _as_dict(item.get("metrics"))
    baseline = _clean_text(_as_dict(payload.get("market_overview")).get("trade_date"))
    return {
        "schema_version": SCHEMA_VERSION,
        "line": LINE_NAME,
        "purpose": "non_scoring_context_for_c_and_d_llm",
        "baseline_trade_date": baseline,
        "target_trade_date": _clean_text(target_trade_date),
        "stock": {
            "code": _clean_text(item.get("code")),
            "name": _first_non_empty(rt.get("name"), item.get("configured_name")),
        },
        "earnings": normalize_earnings(raw.get("earnings"), metrics=metrics),
        "company_events": normalize_company_events(raw.get("company_events")),
        "industry_forward": normalize_industry_forward(
            raw.get("industry_forward"),
            concepts=item.get("concepts") or [],
            tracks=payload.get("tracks") or [],
        ),
    }


def build_context_from_snapshot(snapshot: Dict[str, Any], target_trade_date: str) -> Dict[str, Any]:
    snapshot = _as_dict(snapshot)
    raw = _as_dict(snapshot.get("company_context") or snapshot.get("context_ref"))
    if raw.get("schema_version") == SCHEMA_VERSION and raw.get("line") == LINE_NAME:
        ctx = dict(raw)
        ctx["target_trade_date"] = ctx.get("target_trade_date") or _clean_text(target_trade_date)
        return ctx
    market = _as_dict(snapshot.get("market"))
    ai_track = _as_dict(market.get("ai_track"))
    tracks = [ai_track] if ai_track else []
    return {
        "schema_version": SCHEMA_VERSION,
        "line": LINE_NAME,
        "purpose": "non_scoring_context_for_c_and_d_llm",
        "baseline_trade_date": _clean_text(snapshot.get("trade_date")),
        "target_trade_date": _clean_text(target_trade_date),
        "stock": {
            "code": _clean_text(snapshot.get("code")),
            "name": _clean_text(snapshot.get("name")),
        },
        "earnings": normalize_earnings(raw.get("earnings"), metrics=_as_dict(snapshot.get("metrics"))),
        "company_events": normalize_company_events(raw.get("company_events")),
        "industry_forward": normalize_industry_forward(
            raw.get("industry_forward"),
            concepts=snapshot.get("concepts") or [],
            tracks=tracks,
        ),
    }


def summarize_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """Small human-readable summary for D-line markdown/current snapshot."""
    ctx = _as_dict(context)
    earnings = _as_dict(ctx.get("earnings"))
    events = _as_dict(ctx.get("company_events"))
    industry = _as_dict(ctx.get("industry_forward"))
    next_report = _as_dict(earnings.get("next_report"))
    return {
        "earnings_status": earnings.get("source_status") or "pending_source",
        "next_report_date": next_report.get("expected_ann_date"),
        "company_event_count": len(_as_list(events.get("events"))),
        "industry_status": industry.get("source_status") or "pending_source",
    }
