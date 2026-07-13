# -*- coding: utf-8 -*-
"""Company event / earnings context schema.

This layer is non-scoring context for C-line predictions and D-line LLM tasks.
It does not fetch data and it does not invent missing events.  When no verified
source is present, fields stay explicit as pending_source so downstream prompts
can use the absence honestly.
"""

from __future__ import annotations

import math
from numbers import Real
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
    if isinstance(value, Real) and math.isnan(float(value)):
        return None
    text = str(value).strip()
    return text or None


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return None


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        elif value not in (None, {}, []):
            out[key] = value
    return out


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
        "roe": node.get("roe"),
        "gross_margin": node.get("gross_margin"),
        "raw_fields": list(node.get("raw_fields") or []),
        "raw": _as_dict(node.get("raw")) or None,
    }


def _normalize_next_report(raw: Dict[str, Any]) -> Dict[str, Any]:
    node = _as_dict(raw)
    return {
        "expected_ann_date": _first_non_empty(node.get("expected_ann_date"), node.get("pre_date"), node.get("ann_date")),
        "actual_ann_date": _first_non_empty(node.get("actual_ann_date"), node.get("actual_date")),
        "period": _first_non_empty(node.get("period"), node.get("report_period")),
        "source": _clean_text(node.get("source")),
        "status": _clean_text(node.get("status")) or "pending_source",
        "near_target_window": node.get("near_target_window"),
        "distance_calendar_days": node.get("distance_calendar_days"),
        "note": _clean_text(node.get("note")),
        "raw_fields": list(node.get("raw_fields") or []),
        "raw": _as_dict(node.get("raw")) or None,
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
            "raw_fields": list(src.get("raw_fields") or []),
            "raw": _as_dict(src.get("raw")) or None,
        })
    return {
        "available": bool(events),
        "source_status": "provided" if events else "pending_source",
        "required_event_fields": list(REQUIRED_EVENT_FIELDS),
        "events": events,
        "usage": "context_only_not_scoring",
    }


def _impact_from_pct(*values: Any) -> str:
    nums = []
    for value in values:
        try:
            if value is not None:
                nums.append(float(value))
        except (TypeError, ValueError):
            continue
    if not nums:
        return "unknown"
    if min(nums) > 0:
        return "positive"
    if max(nums) < 0:
        return "negative"
    return "mixed"


def _format_pct_range(min_value: Any, max_value: Any) -> Optional[str]:
    lo = _clean_text(min_value)
    hi = _clean_text(max_value)
    if lo and hi:
        return f"{lo}%~{hi}%"
    if lo:
        return f"{lo}%"
    if hi:
        return f"{hi}%"
    return None


def _raw_fields(node: Dict[str, Any]) -> List[str]:
    fields = node.get("raw_fields")
    if isinstance(fields, list):
        return list(fields)
    return list(node.keys())


def _next_disclosure(schedule: List[Any], target_trade_date: Optional[str]) -> Dict[str, Any]:
    """Select the nearest unreported scheduled disclosure relative to target date."""
    rows = []
    for value in schedule:
        row = _as_dict(value)
        pre_date = _clean_text(row.get("pre_date"))
        if not pre_date or _clean_text(row.get("actual_date")):
            continue
        rows.append((pre_date, row))
    if not rows:
        return {}
    rows.sort(key=lambda pair: pair[0])
    target = _clean_text(target_trade_date)
    selected = next((pair for pair in rows if not target or pair[0] >= target), rows[-1])
    pre_date, row = selected
    status = "scheduled" if not target or pre_date >= target else "planned_date_passed_unconfirmed"
    return {
        "expected_ann_date": pre_date,
        "actual_ann_date": _clean_text(row.get("actual_date")),
        "period": row.get("end_date"),
        "source": "tushare.disclosure_date",
        "status": status,
        "note": "交易所预约披露日期，后续可能修订" if status == "scheduled" else "预约日期已过，实际披露待数据源确认",
        "raw_fields": list(row.get("raw_fields") or sorted(str(k) for k in row.keys())),
        "raw": row,
    }


def _raw_context_from_item(item: Dict[str, Any], target_trade_date: Optional[str] = None) -> Dict[str, Any]:
    """Derive context from existing real Tushare fields assembled in stock_item."""
    fina_history = _as_list(item.get("fina_history"))
    forecast = _as_dict(item.get("forecast"))
    express = _as_dict(item.get("express"))
    events: List[Dict[str, Any]] = []

    latest_report: Dict[str, Any] = {}
    if fina_history:
        latest = _as_dict(fina_history[0])
        latest_report = {
            "period": latest.get("end_date"),
            "report_type": latest.get("period_type"),
            "ann_date": latest.get("ann_date"),
            "source": latest.get("source") or "tushare.fina_indicator",
            "net_profit_yoy": latest.get("np_yoy"),
            "revenue_yoy": latest.get("or_yoy"),
            "roe": latest.get("roe"),
            "gross_margin": latest.get("gross_margin"),
            "raw_fields": _raw_fields(latest),
            "raw": latest,
        }

    if forecast:
        pct_range = _format_pct_range(forecast.get("p_change_min"), forecast.get("p_change_max"))
        summary = _first_non_empty(forecast.get("summary"), pct_range)
        title_parts = ["performance forecast"]
        if forecast.get("end_date"):
            title_parts.append(str(forecast.get("end_date")))
        if forecast.get("type"):
            title_parts.append(str(forecast.get("type")))
        events.append({
            "event_id": f"tushare_forecast_{forecast.get('end_date') or 'unknown'}",
            "event_type": "guidance",
            "event_date": forecast.get("ann_date"),
            "source": forecast.get("source") or "tushare.forecast",
            "title": " ".join(title_parts),
            "summary": summary,
            "impact_hint": _impact_from_pct(forecast.get("p_change_min"), forecast.get("p_change_max")),
            "confidence": None,
            "raw_fields": _raw_fields(forecast),
            "raw": forecast,
        })

    if express:
        yoy = _first_non_empty(express.get("yoy_net_profit"), express.get("net_profit_yoy"))
        summary = _first_non_empty(express.get("perf_summary"), f"net profit yoy {yoy}%" if yoy else None)
        events.append({
            "event_id": f"tushare_express_{express.get('end_date') or 'unknown'}",
            "event_type": "earnings",
            "event_date": express.get("ann_date"),
            "source": express.get("source") or "tushare.express",
            "title": f"performance express {express.get('end_date') or ''}".strip(),
            "summary": summary,
            "impact_hint": _impact_from_pct(yoy),
            "confidence": None,
            "raw_fields": _raw_fields(express),
            "raw": express,
        })

    next_report = _next_disclosure(_as_list(item.get("disclosure_schedule")), target_trade_date)
    raw: Dict[str, Any] = {}
    if latest_report or next_report:
        raw["earnings"] = {
            "source": "tushare.fina_indicator" if latest_report else "tushare.disclosure_date",
            "latest_report": latest_report,
            "next_report": next_report or {
                "status": "pending_source",
                "note": "预约披露日期待数据源返回",
            },
        }
    if events:
        raw["company_events"] = events
    return raw

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
    raw = _deep_merge(
        _raw_context_from_item(item, target_trade_date),
        _as_dict(item.get("company_context") or item.get("event_context")),
    )
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
