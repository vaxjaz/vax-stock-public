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
    "risk_off_confirm": "转弱减仓确认",
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


def _history_evidence_verdict(summary: Mapping[str, Any],
                              action_rules: Mapping[str, Any]) -> Dict[str, Any]:
    policy = action_rules.get("history_evidence") or {}
    primary_horizon = str(policy.get("decision_horizon") or "1")
    add_veto_horizons = [
        str(value) for value in (policy.get("add_veto_horizons") or (1, 5))
    ]
    position_review_horizons = [
        str(value) for value in (policy.get("position_review_horizons") or (10, 30))
    ]
    tracked_horizons = list(dict.fromkeys(
        [primary_horizon, *add_veto_horizons, *position_review_horizons]
    ))
    latest_horizon = str(
        (summary or {}).get("latest_horizon")
        or (summary or {}).get("max_horizon")
        or ""
    )
    if latest_horizon.isdigit() and latest_horizon not in tracked_horizons:
        tracked_horizons.append(latest_horizon)
    minimum = int(policy.get("minimum_preliminary_samples") or 5)
    stable_minimum = int(policy.get("minimum_stable_samples") or 20)
    support_rate = _number(
        policy.get("support_min_absolute_action_hit_rate")
        if policy.get("support_min_absolute_action_hit_rate") is not None
        else policy.get("support_min_positive_ret_rate")
    )
    conflict_rate = _number(
        policy.get("conflict_max_absolute_action_hit_rate")
        if policy.get("conflict_max_absolute_action_hit_rate") is not None
        else policy.get("conflict_max_positive_ret_rate")
    )
    support_rate = 0.60 if support_rate is None else support_rate
    conflict_rate = 0.40 if conflict_rate is None else conflict_rate

    horizon_verdicts = {}
    for horizon in tracked_horizons:
        cell = ((summary or {}).get("horizons") or {}).get(horizon) or {}
        path_evaluated = int(cell.get("evaluated") or 0)
        evaluated = int(cell.get("absolute_action_evaluated") or 0)
        avg_ret = _number(cell.get("avg_ret"))
        hit_rate = _number(cell.get("absolute_action_hit_rate"))
        expectation = str(cell.get("absolute_action_expectation") or "")
        verdict = "insufficient"
        if expectation == "unscored" and path_evaluated:
            verdict = "unscored"
        elif evaluated >= minimum and avg_ret is not None and hit_rate is not None:
            strength = "stable" if evaluated >= stable_minimum else "preliminary"
            mean_supports = (
                avg_ret > 0 if expectation == "positive"
                else avg_ret <= 0 if expectation == "non_positive"
                else False
            )
            mean_conflicts = (
                avg_ret <= 0 if expectation == "positive"
                else avg_ret > 0 if expectation == "non_positive"
                else False
            )
            if mean_supports and hit_rate >= support_rate:
                verdict = f"{strength}_support"
            elif mean_conflicts and hit_rate <= conflict_rate:
                verdict = f"{strength}_conflict"
            else:
                verdict = "mixed"
        horizon_verdicts[horizon] = {
            "verdict": verdict,
            "horizon": horizon,
            "path_evaluated": path_evaluated,
            "evaluated": evaluated,
            "avg_ret": avg_ret,
            "absolute_action_expectation": expectation or None,
            "absolute_action_hit_count": int(cell.get("absolute_action_hit_count") or 0),
            "absolute_action_hit_rate": hit_rate,
            "all_evaluated": int(cell.get("all_evaluated") or 0),
            "sample_dates": list(cell.get("absolute_action_sample_dates") or []),
            "path_sample_dates": list(cell.get("sample_baseline_dates") or []),
        }

    priority = (
        "stable_conflict", "preliminary_conflict", "stable_support",
        "preliminary_support", "mixed", "unscored", "insufficient",
    )
    action_states = {
        horizon_verdicts[horizon]["verdict"]
        for horizon in add_veto_horizons if horizon in horizon_verdicts
    }
    verdict = next(
        (state for state in priority if state in action_states), "insufficient"
    )
    blocked_horizons = [
        horizon for horizon in add_veto_horizons
        if horizon_verdicts.get(horizon, {}).get("verdict")
        in {"preliminary_conflict", "stable_conflict"}
    ]
    review_horizons = [
        horizon for horizon in position_review_horizons
        if horizon_verdicts.get(horizon, {}).get("verdict")
        in {"stable_support", "stable_conflict"}
    ]
    primary = horizon_verdicts.get(primary_horizon) or {}
    return {
        "verdict": verdict,
        "horizon": primary_horizon,
        "evaluated": primary.get("evaluated", 0),
        "avg_ret": primary.get("avg_ret"),
        "absolute_action_expectation": primary.get("absolute_action_expectation"),
        "absolute_action_hit_count": primary.get("absolute_action_hit_count", 0),
        "absolute_action_hit_rate": primary.get("absolute_action_hit_rate"),
        "horizon_verdicts": horizon_verdicts,
        "latest_horizon": latest_horizon or None,
        "add_veto_horizons": add_veto_horizons,
        "blocked_horizons": blocked_horizons,
        "position_review_horizons": position_review_horizons,
        "review_horizons": review_horizons,
        "position_review_required": bool(review_horizons),
        "minimum_preliminary_samples": minimum,
        "minimum_stable_samples": stable_minimum,
        "blocks_add": (
            bool(blocked_horizons)
            and policy.get("conflict_effect", "block_conditional_add") == "block_conditional_add"
        ),
        "scope": (summary or {}).get("scope") or "matching_current_action",
        "cohort": (summary or {}).get("cohort"),
    }

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
                            degraded: bool = False,
                            dline_trigger_facts: Optional[Mapping[str, Iterable[Mapping[str, Any]]]] = None,
                            dline_coverage: Optional[Mapping[str, Any]] = None,
                            phase: str = "pre_market") -> Dict[str, Any]:
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
    coverage_status = str((dline_coverage or {}).get("status") or "not_loaded")
    coverage_by_code = (dline_coverage or {}).get("by_code") or {}

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
        "breadth": dict(market.get("breadth") or {}),
        "macro": dict(market.get("macro") or {}),
        "ai_track": dict(ai_track),
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
        matching_history = evidence.get("C_matching_history_summary") or {}
        history_verdict = _history_evidence_verdict(matching_history, rules)
        history_blocks_add = bool(history_verdict.get("blocks_add"))
        earnings = ((evidence.get("E_context") or {}).get("earnings") or {})
        c_prediction = (evidence.get("C_prediction") or {}).get("prediction") or {}
        c_action = c_prediction.get("action")
        c_direction = c_prediction.get("direction")
        blueprints = ((task or {}).get("observation") or {}).get("trigger_blueprints") or []
        positive = _first_trigger(blueprints, positive_types)
        risk = _first_trigger(blueprints, risk_types)
        metrics = (evidence.get("A_eod") or {}).get("metrics") or {}
        task_id = str((task or {}).get("task_id") or "")
        trigger_facts = [
            dict(fact) for fact in ((dline_trigger_facts or {}).get(code) or [])
            if task_id and str((fact or {}).get("task_id") or "") == task_id
        ]
        coverage_fact = next((
            dict(fact) for fact in (coverage_by_code.get(code) or [])
            if task_id and str((fact or {}).get("task_id") or "") == task_id
        ), None)
        risk_trigger = next(
            (fact for fact in trigger_facts if fact.get("trigger_type") in set(risk_types)), None
        ) if phase == "close_review" else None
        positive_trigger = next(
            (fact for fact in trigger_facts if fact.get("trigger_type") in set(positive_types)), None
        ) if phase == "close_review" else None

        add_capacity = ((cap.get("unit_capacity") or {}).get(add_unit) or {}) if add_unit else {}
        add_eligible = (
            not degraded
            and not row_pending
            and c_action in eligible_actions
            and c_direction == "up"
            and positive is not None
            and not history_blocks_add
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
        elif history_blocks_add:
            action = "持有观察，不加仓"
            reason = (
                f"同动作C线T+{'/T+'.join(history_verdict.get('blocked_horizons') or [])}"
                "历史反对当前加仓，D线转强只重新评估"
            )
        elif add_eligible:
            action = "持有，等待加仓确认"
            reason = "C线偏上，历史未否决；必须等D线确认后才允许增加仓位"
        else:
            action = "持有，不加仓"
            reason = "当前没有同时满足C线方向、历史校验、D线确认和仓位容量的条件"

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

        if add_plan is not None:
            add_plan.update({
                "triggered": None,
                "trigger_record_status": (
                    "not_recorded" if phase == "close_review" and coverage_fact
                    else "coverage_missing" if phase == "close_review" else "pending"
                ),
            })
        if risk_plan is not None:
            risk_plan.update({
                "triggered": None,
                "trigger_record_status": (
                    "not_recorded" if phase == "close_review" and coverage_fact
                    else "coverage_missing" if phase == "close_review" else "pending"
                ),
            })

        if risk_trigger is not None:
            add_plan = None
            action = (
                "风险条件已触发，减仓执行待确认"
                if risk_plan is not None else "风险条件已触发，减仓数量待确认"
            )
            reason = "D线风险条件已真实触发；系统没有实际成交记录，不能视为已经减仓"
            if risk_plan is not None:
                trigger_price = _number(risk_trigger.get("price"))
                if trigger_price is not None:
                    risk_plan.update(_sell_estimate(
                        unit_amounts.get(reduce_unit), trigger_price,
                        cap.get("shares"), lot_size,
                    ))
                risk_plan.update({
                    "triggered": True, "trigger_record_status": "recorded",
                    "trigger_fact": risk_trigger,
                })
        elif positive_trigger is not None and add_plan is not None:
            if coverage_fact:
                action = "加仓条件已触发，成交待确认"
                reason = "D线加仓条件已真实触发；系统没有实际成交记录，不能视为已经买入"
            else:
                action = "加仓触发已记录，但D线观察证据不完整，不执行系统加仓"
                reason = "存在加仓触发记录，但没有同任务观察覆盖记录，无法确认后续风险条件"
                row_pending.append("dline.coverage")
            add_plan.update({
                "triggered": True, "trigger_record_status": "recorded",
                "trigger_fact": positive_trigger,
            })
        elif phase == "close_review" and coverage_fact is None:
            action = "D线观察证据不足，不操作"
            reason = f"没有与当前任务匹配的D线有效观察记录（覆盖状态={coverage_status}），不能判断盘中条件是否发生"
            row_pending.append("dline.coverage")
        elif phase == "close_review" and add_plan is not None:
            action = "D线已观察，未记录加仓触发，不执行系统加仓"
            reason = f"D线记录了{int(coverage_fact.get('observation_count') or 0)}次有效观察，未发现与当前任务匹配的加仓触发记录"

        cost_price = _number(holding.get("cost"))
        reference_price = _number(cap.get("reference_price"))
        current_shares = cap.get("shares")
        pnl_pct = None
        pnl_amount_estimate = None
        if cost_price is not None and cost_price > 0 and reference_price is not None and current_shares is not None:
            pnl_pct = (reference_price / cost_price - 1.0) * 100.0
            pnl_amount_estimate = (reference_price - cost_price) * int(current_shares)

        rows.append({
            "code": code,
            "name": holding.get("name") or (task or {}).get("name"),
            "tier": cap.get("tier"),
            "current_weight_pct": cap.get("current_weight_pct"),
            "cost_price": cost_price,
            "reference_price": reference_price,
            "pnl_pct": round(pnl_pct, 4) if pnl_pct is not None else None,
            "pnl_amount_estimate": round(pnl_amount_estimate, 2) if pnl_amount_estimate is not None else None,
            "cap_pct": cap.get("cap_pct"),
            "c_action": c_action,
            "c_direction": c_direction,
            "c_confidence": c_prediction.get("confidence"),
            "history_summary": history_summary,
            "matching_history_summary": matching_history,
            "history_verdict": history_verdict,
            "history_position_review": bool(history_verdict.get("position_review_required")),
            "earnings": earnings,
            "action": action,
            "reason": reason,
            "conditional_add": add_plan,
            "risk_reduce": risk_plan,
            "dline_triggers": trigger_facts,
            "dline_coverage": coverage_fact,
            "pending": row_pending,
        })

    return {
        "schema_version": 3,
        "phase": phase,
        "dline_coverage_status": coverage_status,
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
