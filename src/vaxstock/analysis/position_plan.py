# -*- coding: utf-8 -*-
"""账户仓位单位与单票容量计算。

本模块只把已确认账户快照、持仓、参考价和已审核策略转换为容量数据。
它不读取行情、不生成买卖动作、不自动修改策略；缺字段时明确返回 pending。
"""

from math import floor, isfinite
from typing import Any, Dict, Mapping, Optional

SCHEMA_VERSION = 1
_ALLOWED_TIERS = {"ordinary", "core", "strategic_core"}


def _number(value: Any, *, allow_zero: bool = False) -> Optional[float]:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        return None
    return number


def _percentage(value: Any) -> Optional[float]:
    number = _number(value)
    return number if number is not None and number <= 100 else None


def _money(value: float) -> float:
    return round(float(value) + 1e-9, 2)


def _unit_capacity(requested_amount: float, max_add_amount: float,
                   reference_price: float, lot_size: int) -> Dict[str, Any]:
    budget = min(requested_amount, max_add_amount)
    if budget <= 0:
        return {
            "requested_amount": _money(requested_amount),
            "budget_amount": 0.0,
            "estimated_shares": 0,
            "estimated_amount": 0.0,
            "status": "blocked_by_position_cap_or_cash",
        }

    shares = floor(budget / reference_price / lot_size) * lot_size
    estimated_amount = shares * reference_price
    if shares <= 0:
        status = "below_one_buy_lot"
    elif budget + 1e-9 < requested_amount:
        status = "clipped_by_position_cap_or_cash"
    else:
        status = "ok"
    return {
        "requested_amount": _money(requested_amount),
        "budget_amount": _money(budget),
        "estimated_shares": int(shares),
        "estimated_amount": _money(estimated_amount),
        "status": status,
    }


def revalue_portfolio_state(portfolio_state: Mapping[str, Any],
                            holdings: Mapping[str, Mapping[str, Any]],
                            reference_prices: Mapping[str, Any], *,
                            as_of_trade_date: str,
                            source: str = "eod_revalued_from_confirmed_cash_and_holdings") -> Dict[str, Any]:
    """用已确认现金/股数和新EOD价格机械重估账户；缺任一价格则不产出总资产。"""
    out = dict(portfolio_state or {})
    pending = []
    cash = _number(out.get("available_cash"), allow_zero=True)
    if cash is None:
        pending.append("portfolio.available_cash")
    market_value = 0.0
    for code, holding in holdings.items():
        shares = holding.get("shares")
        price = _number(reference_prices.get(code))
        if not isinstance(shares, int) or isinstance(shares, bool) or shares < 0:
            pending.append(f"holding.{code}.shares")
            continue
        if price is None:
            pending.append(f"reference_price.{code}")
            continue
        market_value += shares * price

    out["as_of_trade_date"] = str(as_of_trade_date or "") or None
    out["source"] = source
    out["base_snapshot_captured_at"] = portfolio_state.get("captured_at")
    out["reference_prices"] = dict(reference_prices or {})
    out["revaluation_pending"] = pending
    if pending:
        out["total_assets"] = None
        out["market_value"] = None
        out["position_pct"] = None
        return out

    total_assets = cash + market_value
    out["market_value"] = _money(market_value)
    out["total_assets"] = _money(total_assets)
    out["position_pct"] = round(market_value / total_assets * 100.0, 2) if total_assets > 0 else None
    return out

def build_position_capacity(portfolio_state: Mapping[str, Any],
                            holdings: Mapping[str, Mapping[str, Any]],
                            policy: Mapping[str, Any], *,
                            reference_prices: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """计算仓位单位、当前占比和单票新增容量。

    `estimated_shares` 仅按传入参考价和交易所买入申报单位估算，不是委托指令。
    新持仓若未在 `stock_tiers` 显式分类，整行保持 pending，不默认归为普通仓。
    """
    pending = []
    total_assets = _number(portfolio_state.get("total_assets"))
    available_cash = _number(portfolio_state.get("available_cash"), allow_zero=True)
    if total_assets is None:
        pending.append("portfolio.total_assets")
    if available_cash is None:
        pending.append("portfolio.available_cash")

    units_cfg = policy.get("position_units_pct") or {}
    caps_cfg = policy.get("position_caps_pct") or {}
    tiers = policy.get("stock_tiers") or {}
    trade_rules = policy.get("trade_rules") or {}
    unit_pcts: Dict[str, float] = {}
    for key in ("half_unit", "unit"):
        value = _percentage(units_cfg.get(key))
        if value is None:
            pending.append(f"policy.position_units_pct.{key}")
        else:
            unit_pcts[key] = value

    cap_pcts: Dict[str, float] = {}
    for tier in sorted(_ALLOWED_TIERS):
        value = _percentage(caps_cfg.get(tier))
        if value is None:
            pending.append(f"policy.position_caps_pct.{tier}")
        else:
            cap_pcts[tier] = value

    if len(unit_pcts) == 2 and unit_pcts["half_unit"] > unit_pcts["unit"]:
        pending.append("policy.position_units_pct.order_invalid")
    if len(cap_pcts) == len(_ALLOWED_TIERS) and not (
        cap_pcts["ordinary"] <= cap_pcts["core"] <= cap_pcts["strategic_core"]
    ):
        pending.append("policy.position_caps_pct.order_invalid")
    if not str(policy.get("policy_version") or "").strip():
        pending.append("policy.policy_version")

    lot_raw = trade_rules.get("buy_lot_size")
    lot_size = int(lot_raw) if isinstance(lot_raw, int) and not isinstance(lot_raw, bool) and lot_raw > 0 else None
    if lot_size is None:
        pending.append("policy.trade_rules.buy_lot_size")

    max_strategic = policy.get("max_strategic_core_count")
    if not isinstance(max_strategic, int) or isinstance(max_strategic, bool) or max_strategic < 1:
        pending.append("policy.max_strategic_core_count")
    elif sum(1 for tier in tiers.values() if tier == "strategic_core") > max_strategic:
        pending.append("policy.stock_tiers.strategic_core_count_exceeded")

    account = {
        "as_of_trade_date": portfolio_state.get("as_of_trade_date"),
        "captured_at": portfolio_state.get("captured_at"),
        "source": portfolio_state.get("source"),
        "total_assets": _money(total_assets) if total_assets is not None else None,
        "available_cash": _money(available_cash) if available_cash is not None else None,
        "reported_market_value": portfolio_state.get("market_value"),
        "reported_position_pct": portfolio_state.get("position_pct"),
        "unit_amounts": {
            key: _money(total_assets * pct / 100.0) if total_assets is not None else None
            for key, pct in unit_pcts.items()
        },
        "price_trade_date": portfolio_state.get("price_trade_date"),
        "price_source": portfolio_state.get("price_source"),
    }

    prices = reference_prices if reference_prices is not None else (portfolio_state.get("reference_prices") or {})
    rows: Dict[str, Dict[str, Any]] = {}
    top_ready = not pending and total_assets is not None and available_cash is not None and lot_size is not None
    for code, holding in holdings.items():
        row_pending = []
        tier = tiers.get(code)
        if tier not in _ALLOWED_TIERS:
            row_pending.append("policy.stock_tier")
        price = _number(prices.get(code))
        if price is None:
            row_pending.append("reference_price")
        shares_raw = holding.get("shares")
        shares = int(shares_raw) if isinstance(shares_raw, int) and not isinstance(shares_raw, bool) and shares_raw >= 0 else None
        if shares is None:
            row_pending.append("holding.shares")

        row: Dict[str, Any] = {
            "code": code,
            "name": holding.get("name"),
            "tier": tier,
            "shares": shares,
            "reference_price": price,
            "cap_pct": cap_pcts.get(tier),
            "available": False,
            "pending": row_pending,
        }
        if not top_ready or row_pending:
            rows[code] = row
            continue

        cap_pct = cap_pcts[tier]
        current_value = shares * price
        current_weight_pct = current_value / total_assets * 100.0
        cap_value = total_assets * cap_pct / 100.0
        headroom = max(0.0, cap_value - current_value)
        max_add = min(headroom, available_cash)
        at_or_above_cap = current_value + 1e-9 >= cap_value
        row.update({
            "available": True,
            "current_value": _money(current_value),
            "current_weight_pct": round(current_weight_pct, 2),
            "cap_value": _money(cap_value),
            "at_or_above_cap": at_or_above_cap,
            "over_cap": current_value > cap_value + 1e-9,
            "max_add_amount": _money(max_add),
            "capacity_reason": "at_or_above_cap_no_add" if at_or_above_cap else "within_cap",
            "unit_capacity": {
                key: _unit_capacity(account["unit_amounts"][key], max_add, price, lot_size)
                for key in ("half_unit", "unit")
            },
        })
        rows[code] = row

    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": policy.get("policy_version"),
        "available": top_ready and all(row.get("available") for row in rows.values()),
        "pending": pending,
        "account": account,
        "holdings": rows,
        "boundary": "capacity_only_not_trade_instruction",
    }
