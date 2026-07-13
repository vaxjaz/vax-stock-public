# -*- coding: utf-8 -*-
"""把持仓容量、C线动作和D线条件压缩为每日操作计划。"""

from math import floor
from typing import Any, Dict, Iterable, Mapping, Optional

_TRIGGER_LABELS = {
    "reclaim_confirm": "收复确认",
    "breakout_confirm": "突破确认",
    "panic_rebound_probe": "恐慌修复确认",
    "breakdown_confirm": "破位确认",
    "failed_breakout": "突破失败",
    "risk_off_confirm": "风险关闭",
}
_PRICE_FIELDS = {
    "price_vs_ma5_pct": ("ma5", "5日均线"),
    "price_vs_ma10_pct": ("ma10", "10日均线"),
    "price_vs_ma20_pct": ("ma20", "20日均线"),
    "price_vs_ma60_pct": ("ma60", "60日均线"),
}
_REGIME_LABELS = {
    "momentum": "趋势偏强",
    "value": "价值/防守分化",
    "panic": "恐慌防守",
}


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_trigger(blueprints: Iterable[Mapping[str, Any]], allowed) -> Optional[Mapping[str, Any]]:
    allowed_set = set(allowed or [])
    for blueprint in blueprints or []:
        if blueprint.get("trigger_type") in allowed_set:
            return blueprint
    return None


def _trigger_condition_text(blueprint: Optional[Mapping[str, Any]], metrics: Mapping[str, Any]) -> Optional[str]:
    if not blueprint:
        return None
    trigger_type = blueprint.get("trigger_type")
    parts = []
    has_non_price = False
    condition = blueprint.get("condition") or {}
    for group in ("all", "any"):
        for atom in condition.get(group) or []:
            field = atom.get("field")
            ma_spec = _PRICE_FIELDS.get(field)
            if not ma_spec:
                has_non_price = True
                continue
            ma_key, ma_label = ma_spec
            ma = _number(metrics.get(ma_key))
            offset = _number(atom.get("value"))
            if ma is None or offset is None:
                continue
            level = ma * (1.0 + offset / 100.0)
            op = atom.get("op")
            verb = "站上" if op in (">", ">=") else "跌破"
            if abs(offset) < 1e-9:
                text = f"{verb}{ma_label}{level:.2f}"
            else:
                side = "上方" if offset > 0 else "下方"
                text = f"{verb}{ma_label}{side}{abs(offset):g}%阈值{level:.2f}"
            if text not in parts:
                parts.append(text)
    base = _TRIGGER_LABELS.get(trigger_type, str(trigger_type or "触发条件"))
    if parts:
        base += "（" + "、".join(parts[:2]) + "）"
    if has_non_price:
        base += "，并同时满足成交活跃度和当天波动条件"
    return base


def _sell_estimate(unit_amount: Optional[float], price: Optional[float],
                   current_shares: Optional[int], lot_size: Optional[int]) -> Dict[str, Any]:
    if not unit_amount or not price or not current_shares or not lot_size:
        return {"amount": unit_amount, "estimated_shares": None, "estimated_amount": None}
    lots = floor(unit_amount / price / lot_size)
    estimated = min(current_shares, lots * lot_size)
    if estimated <= 0:
        return {"amount": round(unit_amount, 2), "estimated_shares": None, "estimated_amount": None}
    return {
        "amount": round(unit_amount, 2),
        "estimated_shares": int(estimated),
        "estimated_amount": round(estimated * price, 2),
    }


def build_daily_action_plan(task_snapshot: Mapping[str, Any], holdings: Mapping[str, Mapping[str, Any]],
                            capacity: Mapping[str, Any], policy: Mapping[str, Any], *,
                            degraded: bool = False) -> Dict[str, Any]:
    """生成只面向真实持仓的每日操作计划；不读取网络，不自动开新仓。"""
    tasks = task_snapshot.get("tasks") or []
    task_by_code = {str(t.get("code")): t for t in tasks if isinstance(t, dict) and t.get("code")}
    target_dates = [str(x) for x in (task_snapshot.get("target_trade_dates") or []) if x]
    target = target_dates[0] if len(set(target_dates)) == 1 else None
    pending = []
    if not target:
        pending.append("dline.target_trade_date")

    rules = policy.get("action_rules") or {}
    positive_types = rules.get("positive_trigger_types") or []
    risk_types = rules.get("risk_trigger_types") or []
    eligible_actions = set(rules.get("c_actions_eligible_for_conditional_add") or [])
    add_unit = rules.get("conditional_add_unit")
    reduce_unit = rules.get("risk_reduce_unit")
    lot_size = ((policy.get("trade_rules") or {}).get("buy_lot_size"))
    account = capacity.get("account") or {}
    unit_amounts = account.get("unit_amounts") or {}

    first_task = tasks[0] if tasks else {}
    first_evidence = (first_task.get("evidence_pack") or {}) if isinstance(first_task, dict) else {}
    market = ((first_evidence.get("A_eod") or {}).get("market") or {})
    ai_track = market.get("ai_track") or {}
    background = {
        "baseline_trade_date": first_evidence.get("baseline_trade_date") or first_task.get("baseline_trade_date"),
        "target_trade_date": target,
        "market_regime": market.get("market_regime"),
        "market_regime_text": _REGIME_LABELS.get(market.get("market_regime"), market.get("market_regime") or "待验证"),
        "macro_regime": market.get("macro_regime"),
        "ai_position_ceiling": ai_track.get("position_ceiling"),
    }

    rows = []
    capacity_rows = capacity.get("holdings") or {}
    for code, holding in holdings.items():
        task = task_by_code.get(code)
        cap = capacity_rows.get(code) or {}
        row_pending = []
        if not task:
            row_pending.append("dline.task")
        if not cap.get("available"):
            row_pending.extend(cap.get("pending") or ["position.capacity"])

        evidence = (task or {}).get("evidence_pack") or {}
        history_summary = evidence.get("B_prediction_history_summary") or {}
        earnings = ((evidence.get("E_context") or {}).get("earnings") or {})
        c_prediction = (evidence.get("C_prediction") or {}).get("prediction") or {}
        c_action = c_prediction.get("action")
        c_direction = c_prediction.get("direction")
        blueprints = ((task or {}).get("observation") or {}).get("trigger_blueprints") or []
        positive = _first_trigger(blueprints, positive_types)
        risk = _first_trigger(blueprints, risk_types)
        metrics = (evidence.get("A_eod") or {}).get("metrics") or {}

        add_capacity = ((cap.get("unit_capacity") or {}).get(add_unit) or {}) if add_unit else {}
        add_eligible = (
            not degraded
            and not row_pending
            and c_action in eligible_actions
            and c_direction == "up"
            and positive is not None
            and (add_capacity.get("estimated_shares") or 0) > 0
        )
        if row_pending:
            action = "数据待确认，不操作"
            reason = "账户、价格或D线条件不完整"
        elif degraded:
            action = "持有，不加仓"
            reason = "D线未完整生成，今日禁止所有条件加仓"
        elif c_action == "avoid" or c_direction != "up":
            action = "持有观察，不加仓"
            reason = "C线为回避/低优先级；盘中转强只重新评估，不直接买入"
        elif add_eligible:
            action = "持有，等待加仓确认"
            reason = "C线偏上，但必须等D线确认后才允许增加仓位"
        elif cap.get("over_cap"):
            action = "持有，不加仓"
            reason = "当前仓位已经超过本档上限"
        elif cap.get("at_or_above_cap"):
            action = "持有，不加仓"
            reason = "当前仓位已经达到本档上限"
        elif add_capacity.get("status") == "below_one_buy_lot":
            action = "持有，不加仓"
            reason = f"剩余新增容量仅{float(cap.get('max_add_amount') or 0):,.2f}元，不足买入100股"
        elif add_capacity and not add_capacity.get("estimated_shares"):
            action = "持有，不加仓"
            reason = "可用现金或仓位容量不足"
        else:
            action = "持有，不加仓"
            reason = "当前没有同时满足C线方向、D线确认和仓位容量的条件"

        add_plan = None
        if add_eligible:
            add_plan = {
                "unit": add_unit,
                "amount": add_capacity.get("estimated_amount"),
                "estimated_shares": add_capacity.get("estimated_shares"),
                "trigger_type": positive.get("trigger_type"),
                "condition": _trigger_condition_text(positive, metrics),
            }

        risk_plan = None
        if risk is not None and cap.get("available"):
            risk_plan = {
                "unit": reduce_unit,
                "trigger_type": risk.get("trigger_type"),
                "condition": _trigger_condition_text(risk, metrics),
                **_sell_estimate(
                    unit_amounts.get(reduce_unit),
                    _number(cap.get("reference_price")),
                    cap.get("shares"),
                    lot_size,
                ),
            }

        rows.append({
            "code": code,
            "name": holding.get("name") or (task or {}).get("name"),
            "tier": cap.get("tier"),
            "current_weight_pct": cap.get("current_weight_pct"),
            "cap_pct": cap.get("cap_pct"),
            "c_action": c_action,
            "c_direction": c_direction,
            "c_confidence": c_prediction.get("confidence"),
            "history_summary": history_summary,
            "earnings": earnings,
            "action": action,
            "reason": reason,
            "conditional_add": add_plan,
            "risk_reduce": risk_plan,
            "pending": row_pending,
        })

    return {
        "schema_version": 1,
        "policy_version": policy.get("policy_version"),
        "degraded": degraded,
        "available": not pending and bool(rows) and all(not row.get("pending") for row in rows),
        "pending": pending,
        "background": background,
        "account": account,
        "holdings": rows,
        "new_positions": {
            "action": "今日不开新仓",
            "reason": "第一版只处理真实持仓；新标的必须先完成显式分类和D线确认",
        },
        "boundary": "conditional_discipline_plan_not_order",
    }
