# -*- coding: utf-8 -*-
"""Pure validation, projection, and reconciliation for user-confirmed trades."""

import datetime as dt
import math
import re
from typing import Any, Dict, Mapping, Optional


SCHEMA_VERSION = 1
CONFIRMED_SOURCE = "broker_screenshot_user_confirmed"
_CODE_RE = re.compile(r"^\d{6}$")
_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{8,160}$")
_SIDES = {"buy", "sell"}
_EXECUTION_STATUSES = {"filled", "partial"}


def _number(value: Any, *, allow_zero: bool = False) -> Optional[float]:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result < 0 or (result == 0 and not allow_zero):
        return None
    return result


def _trade_date(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    for pattern in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, pattern).strftime("%Y%m%d")
        except ValueError:
            continue
    return None


def _aware_timestamp(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return text if parsed.tzinfo is not None else None


def _shares(value: Any, *, allow_zero: bool = False) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or (value == 0 and not allow_zero):
        return None
    return value


def validate_execution_confirmation(data: Mapping[str, Any],
                                    prior_holdings: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    errors = []
    warnings = []
    normalized: Dict[str, Any] = {"schema_version": SCHEMA_VERSION}

    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version.must_equal_1")
    confirmation_id = str(data.get("confirmation_id") or "").strip()
    if not _ID_RE.fullmatch(confirmation_id):
        errors.append("confirmation_id.invalid")
    normalized["confirmation_id"] = confirmation_id or None

    trade_date = _trade_date(data.get("trade_date"))
    if not trade_date:
        errors.append("trade_date.invalid")
    normalized["trade_date"] = trade_date
    confirmed_at = _aware_timestamp(data.get("confirmed_at"))
    if not confirmed_at:
        errors.append("confirmed_at.must_be_timezone_aware_iso")
    normalized["confirmed_at"] = confirmed_at
    if data.get("source") != CONFIRMED_SOURCE:
        errors.append("source.must_be_broker_screenshot_user_confirmed")
    normalized["source"] = data.get("source")
    if data.get("user_confirmed") is not True:
        errors.append("user_confirmed.must_be_true")
    normalized["user_confirmed"] = data.get("user_confirmed") is True
    normalized["supersedes_confirmation_id"] = (
        str(data.get("supersedes_confirmation_id") or "").strip() or None
    )
    replace_prior = data.get("replace_prior_state_confirmed") is True
    normalized["replace_prior_state_confirmed"] = replace_prior

    raw_trades = data.get("trades")
    if not isinstance(raw_trades, list):
        errors.append("trades.must_be_list")
        raw_trades = []
    no_trade = data.get("no_trade_confirmed") is True
    if raw_trades and no_trade:
        errors.append("no_trade_confirmed.conflicts_with_trades")
    if not raw_trades and not no_trade:
        errors.append("trades.empty_requires_no_trade_confirmed_true")
    normalized["no_trade_confirmed"] = no_trade

    seen_execution_ids = set()
    trades = []
    for index, raw in enumerate(raw_trades):
        if not isinstance(raw, Mapping):
            errors.append(f"trades.{index}.must_be_object")
            continue
        execution_id = str(raw.get("execution_id") or "").strip()
        if not _ID_RE.fullmatch(execution_id):
            errors.append(f"trades.{index}.execution_id.invalid")
        elif execution_id in seen_execution_ids:
            errors.append(f"trades.{index}.execution_id.duplicate")
        seen_execution_ids.add(execution_id)
        code = str(raw.get("code") or "").strip()
        if not _CODE_RE.fullmatch(code):
            errors.append(f"trades.{index}.code.invalid")
        side = str(raw.get("side") or "").strip().lower()
        if side not in _SIDES:
            errors.append(f"trades.{index}.side.invalid")
        shares = _shares(raw.get("shares"))
        if shares is None:
            errors.append(f"trades.{index}.shares.invalid")
        price = _number(raw.get("executed_price"))
        if price is None:
            errors.append(f"trades.{index}.executed_price.invalid")
        executed_at = _aware_timestamp(raw.get("executed_at"))
        if not executed_at:
            errors.append(f"trades.{index}.executed_at.must_be_timezone_aware_iso")
        elif trade_date and _trade_date(executed_at[:10]) != trade_date:
            errors.append(f"trades.{index}.executed_at.trade_date_mismatch")
        status = str(raw.get("status") or "").strip().lower()
        if status not in _EXECUTION_STATUSES:
            errors.append(f"trades.{index}.status.invalid")
        trades.append({
            "execution_id": execution_id or None,
            "code": code,
            "name": str(raw.get("name") or "").strip() or None,
            "side": side,
            "shares": shares,
            "executed_price": price,
            "executed_at": executed_at,
            "status": status,
        })
    normalized["trades"] = trades

    raw_snapshot = data.get("post_trade_snapshot")
    if raw_trades and not isinstance(raw_snapshot, Mapping):
        errors.append("post_trade_snapshot.required_when_trades_exist")
    snapshot = None
    share_checks = []
    if isinstance(raw_snapshot, Mapping):
        snapshot = _normalize_snapshot(raw_snapshot, trade_date, errors)
        if snapshot is not None:
            share_checks = _share_consistency(prior_holdings, trades, snapshot)
            mismatches = [row for row in share_checks if row["status"] != "consistent"]
            if mismatches and not replace_prior:
                errors.append("post_trade_snapshot.share_mismatch_requires_replace_prior_state_confirmed")
            elif mismatches:
                warnings.append("prior_holdings_replaced_by_user_confirmed_complete_snapshot")
    normalized["post_trade_snapshot"] = snapshot
    normalized["share_consistency"] = share_checks
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "confirmation": normalized,
    }


def _normalize_snapshot(raw: Mapping[str, Any], trade_date: Optional[str],
                        errors: list) -> Optional[Dict[str, Any]]:
    if raw.get("holdings_snapshot_complete") is not True:
        errors.append("post_trade_snapshot.holdings_snapshot_complete.must_be_true")
    captured_at = _aware_timestamp(raw.get("captured_at"))
    if not captured_at:
        errors.append("post_trade_snapshot.captured_at.must_be_timezone_aware_iso")
    elif trade_date and _trade_date(captured_at[:10]) != trade_date:
        errors.append("post_trade_snapshot.captured_at.trade_date_mismatch")
    total_assets = _number(raw.get("total_assets"), allow_zero=True)
    market_value = _number(raw.get("market_value"), allow_zero=True)
    available_cash = _number(raw.get("available_cash"), allow_zero=True)
    position_pct = _number(raw.get("position_pct"), allow_zero=True)
    for key, value in (
        ("total_assets", total_assets), ("market_value", market_value),
        ("available_cash", available_cash), ("position_pct", position_pct),
    ):
        if value is None:
            errors.append(f"post_trade_snapshot.{key}.invalid")
    if position_pct is not None and position_pct > 100:
        errors.append("post_trade_snapshot.position_pct.above_100")

    raw_holdings = raw.get("holdings")
    raw_prices = raw.get("reference_prices")
    if not isinstance(raw_holdings, Mapping):
        errors.append("post_trade_snapshot.holdings.must_be_object")
        raw_holdings = {}
    if not isinstance(raw_prices, Mapping):
        errors.append("post_trade_snapshot.reference_prices.must_be_object")
        raw_prices = {}
    holdings = {}
    prices = {}
    for code, row in raw_holdings.items():
        code = str(code).strip()
        if not _CODE_RE.fullmatch(code) or not isinstance(row, Mapping):
            errors.append(f"post_trade_snapshot.holdings.{code}.invalid")
            continue
        shares = _shares(row.get("shares"))
        cost = _number(row.get("cost"))
        available_shares = row.get("available_shares")
        if shares is None:
            errors.append(f"post_trade_snapshot.holdings.{code}.shares.invalid")
        if cost is None:
            errors.append(f"post_trade_snapshot.holdings.{code}.cost.invalid")
        if available_shares is not None:
            available_shares = _shares(available_shares, allow_zero=True)
            if available_shares is None or (shares is not None and available_shares > shares):
                errors.append(f"post_trade_snapshot.holdings.{code}.available_shares.invalid")
        name = str(row.get("name") or "").strip()
        if not name:
            errors.append(f"post_trade_snapshot.holdings.{code}.name.missing")
        holdings[code] = {
            "name": name or None,
            "shares": shares,
            "available_shares": available_shares,
            "cost": cost,
        }
        price = _number(raw_prices.get(code))
        if price is None:
            errors.append(f"post_trade_snapshot.reference_prices.{code}.invalid")
        else:
            prices[code] = price

    if None not in (total_assets, market_value, available_cash):
        if abs(total_assets - market_value - available_cash) > 0.05:
            errors.append("post_trade_snapshot.total_assets_not_cash_plus_market_value")
    if None not in (total_assets, market_value, position_pct) and total_assets > 0:
        calculated_pct = market_value / total_assets * 100.0
        if abs(calculated_pct - position_pct) > 0.05:
            errors.append("post_trade_snapshot.position_pct_inconsistent")
    if market_value is not None and all(
        row.get("shares") is not None and code in prices for code, row in holdings.items()
    ):
        calculated_market_value = sum(row["shares"] * prices[code] for code, row in holdings.items())
        tolerance = max(1.0, market_value * 0.00001)
        if abs(calculated_market_value - market_value) > tolerance:
            errors.append("post_trade_snapshot.holdings_market_value_inconsistent")

    return {
        "captured_at": captured_at,
        "as_of_trade_date": trade_date,
        "source": CONFIRMED_SOURCE,
        "holdings_snapshot_complete": raw.get("holdings_snapshot_complete") is True,
        "total_assets": total_assets,
        "market_value": market_value,
        "available_cash": available_cash,
        "position_pct": position_pct,
        "reference_prices": prices,
        "holdings": holdings,
    }


def _share_consistency(prior_holdings: Mapping[str, Mapping[str, Any]], trades: list,
                       snapshot: Mapping[str, Any]) -> list:
    deltas: Dict[str, int] = {}
    for trade in trades:
        if trade.get("shares") is None or trade.get("side") not in _SIDES:
            continue
        sign = 1 if trade["side"] == "buy" else -1
        deltas[trade["code"]] = deltas.get(trade["code"], 0) + sign * trade["shares"]
    actual_holdings = snapshot.get("holdings") or {}
    codes = sorted(set(prior_holdings) | set(actual_holdings) | set(deltas))
    out = []
    for code in codes:
        prior_raw = (prior_holdings.get(code) or {}).get("shares")
        prior = prior_raw if isinstance(prior_raw, int) and not isinstance(prior_raw, bool) else None
        if code not in prior_holdings and deltas.get(code, 0) > 0:
            prior = 0
        actual = (actual_holdings.get(code) or {}).get("shares", 0)
        expected = None if prior is None else prior + deltas.get(code, 0)
        status = "consistent" if expected is not None and expected == actual else "mismatch"
        out.append({
            "code": code, "prior_shares": prior, "trade_delta": deltas.get(code, 0),
            "expected_shares": expected, "snapshot_shares": actual, "status": status,
        })
    return out


def build_holdings_projection(prior_document: Mapping[str, Any],
                              confirmation: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    snapshot = confirmation.get("post_trade_snapshot")
    if not snapshot:
        return None
    prior_rows = prior_document.get("holdings") or {}
    rows = {}
    for code, confirmed in (snapshot.get("holdings") or {}).items():
        prior = dict(prior_rows.get(code) or {})
        prior.update({
            "name": confirmed.get("name"),
            "cost": confirmed.get("cost"),
            "shares": confirmed.get("shares"),
        })
        if confirmed.get("available_shares") is not None:
            prior["available_shares"] = confirmed.get("available_shares")
        rows[code] = prior
    out = dict(prior_document or {})
    out.update({
        "schema_version": 2,
        "as_of_trade_date": confirmation.get("trade_date"),
        "source": CONFIRMED_SOURCE,
        "last_execution_confirmation_id": confirmation.get("confirmation_id"),
        "holdings": rows,
    })
    return out


def build_portfolio_projection(prior_document: Mapping[str, Any],
                               confirmation: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    snapshot = confirmation.get("post_trade_snapshot")
    if not snapshot:
        return None
    out = dict(prior_document or {})
    for stale_key in ("revaluation_pending", "base_snapshot_captured_at"):
        out.pop(stale_key, None)
    out.update({
        "schema_version": 2,
        "as_of_trade_date": confirmation.get("trade_date"),
        "captured_at": snapshot.get("captured_at"),
        "source": CONFIRMED_SOURCE,
        "total_assets": snapshot.get("total_assets"),
        "market_value": snapshot.get("market_value"),
        "available_cash": snapshot.get("available_cash"),
        "position_pct": snapshot.get("position_pct"),
        "reference_prices": dict(snapshot.get("reference_prices") or {}),
        "last_execution_confirmation_id": confirmation.get("confirmation_id"),
    })
    return out


def reconcile_execution(plan: Mapping[str, Any], confirmation: Mapping[str, Any]) -> Dict[str, Any]:
    plan_rows = {str(row.get("code")): row for row in (plan.get("holdings") or []) if row.get("code")}
    actual_by_code: Dict[str, Dict[str, Any]] = {}
    for trade in confirmation.get("trades") or []:
        row = actual_by_code.setdefault(trade["code"], {
            "sides": set(), "shares": 0, "amount": 0.0, "trades": [],
        })
        row["sides"].add(trade["side"])
        row["shares"] += trade["shares"]
        row["amount"] += trade["shares"] * trade["executed_price"]
        row["trades"].append(trade)

    rows = []
    codes = sorted(set(plan_rows) | set(actual_by_code))
    for code in codes:
        plan_row = plan_rows.get(code) or {}
        expected_side, expected_plan = _expected_execution(plan_row)
        expected_shares = (expected_plan or {}).get("estimated_shares")
        actual = actual_by_code.get(code)
        actual_side = None
        actual_shares = 0
        actual_price = None
        if actual:
            actual_shares = actual["shares"]
            actual_price = actual["amount"] / actual_shares if actual_shares else None
            actual_side = next(iter(actual["sides"])) if len(actual["sides"]) == 1 else "mixed"
        status = _execution_status(expected_side, expected_shares, actual_side, actual_shares)
        trigger_price = _number(((expected_plan or {}).get("trigger_fact") or {}).get("price"))
        deviation = None
        adverse = None
        if expected_side == actual_side and trigger_price and actual_price is not None:
            deviation = (actual_price / trigger_price - 1.0) * 100.0
            adverse = deviation if expected_side == "buy" else -deviation
        rows.append({
            "code": code,
            "name": plan_row.get("name") or ((actual or {}).get("trades") or [{}])[0].get("name"),
            "expected_side": expected_side,
            "expected_shares": expected_shares,
            "trigger_price": trigger_price,
            "actual_side": actual_side,
            "actual_shares": actual_shares,
            "actual_average_price": round(actual_price, 4) if actual_price is not None else None,
            "price_deviation_pct": round(deviation, 4) if deviation is not None else None,
            "adverse_slippage_pct": round(adverse, 4) if adverse is not None else None,
            "status": status,
            "policy_violation": (
                "forbidden_board_execution" if actual and (code.startswith("688") or code.startswith("300")) else None
            ),
            "trades": (actual or {}).get("trades") or [],
        })
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "schema_version": 1,
        "confirmation_id": confirmation.get("confirmation_id"),
        "trade_date": confirmation.get("trade_date"),
        "plan_trade_date": (plan.get("background") or {}).get("target_trade_date"),
        "plan_available": bool(plan),
        "summary": counts,
        "rows": rows,
        "boundary": "confirmed_execution_reconciliation_not_broker_order_source",
    }


def _expected_execution(plan_row: Mapping[str, Any]):
    risk = plan_row.get("risk_reduce") or {}
    add = plan_row.get("conditional_add") or {}
    risk_recorded = risk.get("trigger_record_status") == "recorded" or risk.get("triggered") is True
    add_recorded = add.get("trigger_record_status") == "recorded" or add.get("triggered") is True
    if risk_recorded:
        return "sell", risk
    if add_recorded:
        return "buy", add
    return None, None


def _execution_status(expected_side, expected_shares, actual_side, actual_shares):
    if actual_side == "mixed":
        return "mixed_execution"
    if expected_side is None and actual_side is None:
        return "no_action"
    if expected_side is None:
        return "unplanned_execution"
    if actual_side is None:
        return "not_executed"
    if expected_side != actual_side:
        return "opposite_execution"
    if not isinstance(expected_shares, int) or expected_shares <= 0:
        return "executed_without_quantity_plan"
    if actual_shares < expected_shares:
        return "partial_execution"
    if actual_shares > expected_shares:
        return "over_executed"
    return "executed"
