# -*- coding: utf-8 -*-
"""Pure EOD market/anchor recalculation for the human-facing report.

The module consumes only already-collected report payloads.  It never fetches
data and it never substitutes a neutral value for a missing observation.
Every derived field carries its comparison date or source date so the report
can distinguish a current fact from a historical change.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


CALCULATION_VERSION = "eod_market_anchor_v1"
PRICE_ANCHORS = (
    ("NVDA", "英伟达", "stocks"),
    ("SOXX", "美国半导体ETF", "etfs"),
    ("QQQ", "纳斯达克100ETF", "etfs"),
    ("^VIX", "VIX", "indices"),
    ("^TNX", "美国10年期国债收益率", "macro"),
    ("DX-Y.NYB", "美元指数", "macro"),
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> str:
    text = str(value or "").strip().replace("-", "")
    return text if len(text) == 8 and text.isdigit() else ""


def _trade_date(payload: Mapping[str, Any]) -> str:
    return _date(_mapping(payload.get("market_overview")).get("trade_date"))


def _path(payload: Mapping[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        value = _mapping(value).get(key)
    return value


def _snapshot_rows(
    current_payload: Mapping[str, Any],
    historical_payloads: Iterable[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Return one payload per trade date, with current payload winning."""

    by_date: Dict[str, Mapping[str, Any]] = {}
    for payload in historical_payloads:
        if isinstance(payload, Mapping):
            trade_date = _trade_date(payload)
            if trade_date:
                by_date[trade_date] = payload
    current_date = _trade_date(current_payload)
    if current_date:
        by_date[current_date] = current_payload
    return [by_date[key] for key in sorted(by_date)]


def _change_metric(
    rows: Sequence[Mapping[str, Any]],
    getter,
    *,
    lookback: int = 5,
) -> Dict[str, Any]:
    observations = []
    for payload in rows:
        value = _number(getter(payload))
        if value is not None:
            observations.append((_trade_date(payload), value))

    current_date, current = observations[-1] if observations else ("", None)
    reference_date = None
    reference = None
    change = None
    if len(observations) > lookback:
        reference_date, reference = observations[-lookback - 1]
        change = current - reference

    first_date, first = observations[0] if observations else ("", None)
    return {
        "current": current,
        "current_trade_date": current_date or None,
        "reference_5_sessions": reference,
        "reference_5_sessions_trade_date": reference_date,
        "change_5_sessions": change,
        "first_available": first,
        "first_available_trade_date": first_date or None,
        "change_available_window": (
            current - first
            if current is not None and first is not None and len(observations) > 1
            else None
        ),
        "observation_count": len(observations),
    }


def _find_symbol(payload: Mapping[str, Any], section: str, symbol: str) -> Mapping[str, Any]:
    rows = _mapping(payload.get("us_market")).get(section)
    if not isinstance(rows, list):
        return {}
    for raw in rows:
        row = _mapping(raw)
        if str(row.get("symbol") or "") == symbol:
            return row
    return {}


def _price_anchor(
    rows: Sequence[Mapping[str, Any]],
    *,
    symbol: str,
    name: str,
    section: str,
) -> Dict[str, Any]:
    # A-share report dates and US source dates are different clocks.  Dedupe by
    # the source session date so a holiday/retry cannot be counted twice.
    by_source_date: Dict[str, Mapping[str, Any]] = {}
    for payload in rows:
        row = _find_symbol(payload, section, symbol)
        source_date = _date(row.get("date"))
        price = _number(row.get("price"))
        if source_date and price is not None:
            by_source_date[source_date] = row
    ordered = [(key, by_source_date[key]) for key in sorted(by_source_date)]
    if not ordered:
        return {
            "symbol": symbol,
            "name": name,
            "status": "missing",
            "source": "payload.us_market",
        }

    source_date, latest = ordered[-1]
    price = _number(latest.get("price"))
    daily_change = _number(latest.get("change_pct"))
    ref_date = None
    ref_price = None
    return_5 = None
    if len(ordered) > 5:
        ref_date, ref_row = ordered[-6]
        ref_price = _number(ref_row.get("price"))
        if price is not None and ref_price not in (None, 0.0):
            return_5 = (price / ref_price - 1.0) * 100.0
    return {
        "symbol": symbol,
        "name": name,
        "status": "available",
        "price": price,
        "daily_change_pct": daily_change,
        "source_date": source_date,
        "reference_5_sessions_price": ref_price,
        "reference_5_sessions_source_date": ref_date,
        "return_5_sessions_pct": return_5,
        "source_session_count": len(ordered),
        "source": "payload.us_market",
    }


def _track(payload: Mapping[str, Any], track_results: Optional[Sequence[Mapping[str, Any]]]) -> Mapping[str, Any]:
    rows: Any = track_results if track_results is not None else payload.get("tracks")
    if isinstance(rows, Mapping):
        rows = [rows]
    if not isinstance(rows, (list, tuple)):
        return {}
    for raw in rows:
        row = _mapping(raw)
        if str(row.get("track_name") or "") == "AI算力":
            return row
    return _mapping(rows[0]) if rows else {}


def _track_signal_value(payload: Mapping[str, Any], signal: str, field: str) -> Any:
    return _path(_track(payload, None), "signals", signal, field)


def _indices(current_payload: Mapping[str, Any]) -> list[Dict[str, Any]]:
    rows = current_payload.get("indices")
    if not isinstance(rows, list):
        return []
    result = []
    for raw in rows:
        row = _mapping(raw)
        result.append({
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "price": _number(row.get("price")),
            "change_pct": _number(row.get("change_pct")),
            "source_trade_date": _date(row.get("trade_date")) or None,
            "source": row.get("source"),
        })
    return result


def _style(current_payload: Mapping[str, Any]) -> Dict[str, Any]:
    inputs = _mapping(_mapping(current_payload.get("regime_audit")).get("inputs"))
    return {
        "sh_change_pct": _number(inputs.get("sh_change_pct")),
        "growth_average_change_pct": _number(inputs.get("growth_avg_change_pct")),
        "sh_minus_growth_pp": _number(inputs.get("sh_minus_growth_pct")),
        "source_trade_date": _trade_date(current_payload) or None,
        "source": "payload.regime_audit.inputs",
    }


def _participation(current_payload: Mapping[str, Any]) -> Dict[str, Any]:
    overview = _mapping(current_payload.get("market_overview"))
    up = _number(overview.get("up_count"))
    down = _number(overview.get("down_count"))
    flat = _number(overview.get("flat_count"))
    total = _number(overview.get("total"))
    if total is None and None not in (up, down, flat):
        total = up + down + flat
    up_ratio = None
    if up is not None and total not in (None, 0.0):
        up_ratio = up / total * 100.0
    return {
        "up_count": int(up) if up is not None else None,
        "down_count": int(down) if down is not None else None,
        "flat_count": int(flat) if flat is not None else None,
        "limit_up_count": overview.get("limit_up_count"),
        "limit_down_count": overview.get("limit_down_count"),
        "total": int(total) if total is not None else None,
        "up_ratio_pct": up_ratio,
        "source_trade_date": _trade_date(current_payload) or None,
        "source": "payload.market_overview",
    }


def _state_from_data(
    *,
    breadth: Mapping[str, Any],
    funding: Mapping[str, Any],
    margin: Mapping[str, Any],
    demand: Mapping[str, Any],
    price_gate: Mapping[str, Any],
) -> Dict[str, str]:
    ma60_delta = _number(_mapping(breadth.get("above_ma60_pct")).get("change_5_sessions"))
    ma200_delta = _number(_mapping(breadth.get("above_ma200_pct")).get("change_5_sessions"))
    ma200 = _number(_mapping(breadth.get("above_ma200_pct")).get("current"))
    if None in (ma60_delta, ma200_delta, ma200):
        breadth_state = "insufficient_history"
    elif ma60_delta > 0 and ma200_delta > 0 and ma200 < 50:
        breadth_state = "repairing_but_long_term_majority_below_ma200"
    elif ma60_delta > 0 and ma200_delta > 0:
        breadth_state = "broad_repair"
    elif ma60_delta < 0 and ma200_delta < 0:
        breadth_state = "deteriorating"
    else:
        breadth_state = "mixed"

    etf5 = _number(funding.get("etf_net_sub_5d_yi"))
    etf20 = _number(funding.get("etf_net_sub_20d_yi"))
    if etf5 is None or etf20 is None:
        funding_state = "insufficient_data"
    elif etf5 < 0 < etf20:
        funding_state = "short_outflow_medium_inflow_divergence"
    elif etf5 < 0 and etf20 < 0:
        funding_state = "broad_outflow"
    elif etf5 > 0 and etf20 > 0:
        funding_state = "broad_inflow"
    else:
        funding_state = "mixed"

    margin_delta = _number(_mapping(margin.get("ratio_pct")).get("change_5_sessions"))
    margin_pctile = _number(margin.get("percentile_3y"))
    if margin_delta is None or margin_pctile is None:
        deleveraging_state = "insufficient_history"
    elif margin_delta < 0 and etf5 is not None and etf5 < 0 and ma60_delta is not None and ma60_delta < 0:
        deleveraging_state = "active_deleveraging"
    elif margin_pctile >= 90 and margin_delta >= 0:
        deleveraging_state = "not_deleveraging_high_leverage_fragility"
    elif margin_delta < 0:
        deleveraging_state = "leverage_contracting_not_systemic"
    else:
        deleveraging_state = "not_deleveraging"

    demand_expanding = demand.get("expanding")
    gate_open = price_gate.get("gate_open")
    if not isinstance(demand_expanding, bool) or not isinstance(gate_open, bool):
        ai_state = "insufficient_data"
    elif demand_expanding and not gate_open:
        ai_state = "demand_proxy_intact_price_reversal_not_confirmed"
    elif demand_expanding and gate_open:
        ai_state = "demand_and_price_gate_aligned"
    elif not demand_expanding and not gate_open:
        ai_state = "demand_and_price_both_weak"
    else:
        ai_state = "price_repair_without_demand_confirmation"

    return {
        "breadth_state": breadth_state,
        "funding_state": funding_state,
        "deleveraging_state": deleveraging_state,
        "ai_state": ai_state,
    }


def build_eod_market_analysis(
    current_payload: Mapping[str, Any],
    historical_payloads: Iterable[Mapping[str, Any]] = (),
    *,
    track_results: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Recalculate macro/market/AI anchors from immutable EOD payload facts."""

    rows = _snapshot_rows(current_payload, historical_payloads)
    as_of = _trade_date(current_payload)
    indicators = _mapping(_mapping(current_payload.get("macro")).get("indicators"))
    breadth_now = _mapping(indicators.get("breadth"))
    etf = _mapping(indicators.get("etf_net_sub"))
    margin_now = _mapping(indicators.get("margin_ratio"))
    turnover = _mapping(indicators.get("turnover"))
    erp = _mapping(indicators.get("hs300_erp"))
    m1 = _mapping(indicators.get("m1_yoy"))
    sf = _mapping(indicators.get("sf_pulse"))

    breadth = {
        "above_ma60_pct": _change_metric(
            rows,
            lambda p: _path(p, "macro", "indicators", "breadth", "above_ma60_pct"),
        ),
        "above_ma200_pct": _change_metric(
            rows,
            lambda p: _path(p, "macro", "indicators", "breadth", "above_ma200_pct"),
        ),
        "ma250_bias_pct": _change_metric(
            rows,
            lambda p: _path(p, "macro", "indicators", "breadth", "ma250_bias_pct"),
        ),
        "latest_date": _date(breadth_now.get("latest_date")) or None,
        "valid_count_ma60": breadth_now.get("valid_count_ma60"),
        "valid_count_ma200": breadth_now.get("valid_count_ma200"),
        "source": "payload.macro.indicators.breadth",
    }
    funding = {
        "etf_net_sub_5d_yi": _number(etf.get("value_5d_yi")),
        "etf_net_sub_20d_yi": _number(etf.get("value_20d_yi")),
        "latest_date": _date(etf.get("latest_date")) or None,
        "etf_net_sub_5d_history": _change_metric(
            rows,
            lambda p: _path(p, "macro", "indicators", "etf_net_sub", "value_5d_yi"),
        ),
        "etf_net_sub_20d_history": _change_metric(
            rows,
            lambda p: _path(p, "macro", "indicators", "etf_net_sub", "value_20d_yi"),
        ),
        "source": "payload.macro.indicators.etf_net_sub",
    }
    margin = {
        "ratio_pct": _change_metric(
            rows,
            lambda p: _path(p, "macro", "indicators", "margin_ratio", "ratio_pct"),
        ),
        "percentile_3y": _number(margin_now.get("percentile_3y")),
        "latest_date": _date(margin_now.get("latest_date")) or None,
        "stale": margin_now.get("stale") if isinstance(margin_now.get("stale"), bool) else None,
        "source": "payload.macro.indicators.margin_ratio",
    }
    valuation_credit = {
        "turnover_percentile_3y": _number(turnover.get("percentile_3y")),
        "turnover_latest_date": _date(turnover.get("latest_date")) or None,
        "hs300_pe_ttm": _number(erp.get("pe_ttm")),
        "cn_10y_yield_pct": _number(erp.get("yield_10y_pct")),
        "erp_pct": _number(erp.get("erp_pct")),
        "erp_percentile_5y": _number(erp.get("percentile_5y")),
        "erp_latest_date": _date(erp.get("latest_date")) or None,
        "m1_yoy_pct": _number(m1.get("value_pct")),
        "m1_mom_delta_pp": _number(m1.get("mom_delta_pp")),
        "m1_latest_month": str(m1.get("latest_month") or "") or None,
        "social_financing_pulse_yoy_pct": _number(sf.get("pulse_yoy_pct")),
        "social_financing_acceleration_pp": _number(sf.get("accel_pp")),
        "social_financing_latest_month": str(sf.get("latest_month") or "") or None,
        "source": "payload.macro.indicators",
    }

    track = _track(current_payload, track_results)
    signals = _mapping(track.get("signals"))
    prosperity = _mapping(signals.get("prosperity"))
    gate = _mapping(signals.get("sox_gate"))
    qvix = _mapping(signals.get("qvix"))
    crowding = _mapping(signals.get("crowding"))
    yoy = _number(prosperity.get("yoy_pct"))
    qoq = _number(prosperity.get("qoq_pct"))
    demand = {
        "status": prosperity.get("status") or "missing",
        "meaning": "NVDA季度营收增速，仅作AI需求景气代理，不是Capex或债务数据",
        "revenue_yoy_pct": yoy,
        "revenue_qoq_pct": qoq,
        "revenue_acceleration_pp": _number(prosperity.get("accel_pp")),
        "latest_revenue_busd": _number(prosperity.get("latest_rev_busd")),
        "expanding": (yoy > 0 and qoq > 0) if yoy is not None and qoq is not None else None,
        "source": "payload.tracks[AI算力].signals.prosperity",
    }
    sox_close = _number(gate.get("sox_close"))
    sox_ma50 = _number(gate.get("sox_ma50"))
    price_gate = {
        "status": gate.get("status") or "missing",
        "gate_open": gate.get("gate_open") if isinstance(gate.get("gate_open"), bool) else None,
        "sox_close": sox_close,
        "sox_ma50": sox_ma50,
        "sox_vs_ma50_pct": (
            (sox_close / sox_ma50 - 1.0) * 100.0
            if sox_close is not None and sox_ma50 not in (None, 0.0)
            else None
        ),
        "sox_momentum_1m_pct": _number(gate.get("mom_1m_pct")),
        "source": "payload.tracks[AI算力].signals.sox_gate",
    }
    local_risk = {
        "qvix_300": _change_metric(
            rows,
            lambda p: _track_signal_value(p, "qvix", "qvix_300"),
        ),
        "qvix_cyb": _change_metric(
            rows,
            lambda p: _track_signal_value(p, "qvix", "qvix_cyb"),
        ),
        "mood": qvix.get("mood"),
        "basket_turnover_percentile_pct": _change_metric(
            rows,
            lambda p: (
                _number(_track_signal_value(p, "crowding", "turnover_pctile")) * 100.0
                if _number(_track_signal_value(p, "crowding", "turnover_pctile")) is not None
                else None
            ),
        ),
        "basket_52w_position_pct": _change_metric(
            rows,
            lambda p: (
                _number(_track_signal_value(p, "crowding", "basket_52w_pos")) * 100.0
                if _number(_track_signal_value(p, "crowding", "basket_52w_pos")) is not None
                else None
            ),
        ),
        "source": "payload.tracks[AI算力].signals.qvix/crowding",
    }
    price_anchors = [
        _price_anchor(rows, symbol=symbol, name=name, section=section)
        for symbol, name, section in PRICE_ANCHORS
    ]
    capital_cycle = {
        "status": "not_available",
        "available": False,
        "missing": [
            "头部云厂point-in-time资本开支",
            "头部云厂自由现金流",
            "头部云厂净负债/EBITDA或等价杠杆指标",
        ],
        "conclusion_limit": "现有数据不能验证AI资本开支是否已进入债务驱动阶段，也不能据此判断周期顶部",
    }

    states = _state_from_data(
        breadth=breadth,
        funding=funding,
        margin=margin,
        demand=demand,
        price_gate=price_gate,
    )
    return {
        "schema_version": 1,
        "calculation_version": CALCULATION_VERSION,
        "as_of_trade_date": as_of or None,
        "history": {
            "report_session_count": len(rows),
            "first_trade_date": _trade_date(rows[0]) if rows else None,
            "last_trade_date": _trade_date(rows[-1]) if rows else None,
            "five_session_reference_trade_date": (
                _trade_date(rows[-6]) if len(rows) > 5 else None
            ),
        },
        "market": {
            "regime": current_payload.get("market_regime"),
            "indices": _indices(current_payload),
            "participation": _participation(current_payload),
            "style": _style(current_payload),
            "breadth": breadth,
            "funding": funding,
            "margin": margin,
            "valuation_credit": valuation_credit,
        },
        "ai_anchors": {
            "price_anchors": price_anchors,
            "demand_proxy": demand,
            "price_gate": price_gate,
            "local_risk": local_risk,
            "position_ceiling": track.get("position_ceiling"),
            "capital_cycle": capital_cycle,
        },
        "states": states,
        "audit": {
            "input_current_payload_trade_date": as_of or None,
            "historical_payload_count": max(len(rows) - 1, 0),
            "missing_values_are_none": True,
            "no_network_fetch": True,
        },
    }
