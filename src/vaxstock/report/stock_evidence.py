# -*- coding: utf-8 -*-
"""Chinese rendering for audited stock history and earnings context."""

from typing import Any, Mapping


def _pct(value: Any, signed: bool = True) -> str:
    try:
        number = float(value) * 100
    except (TypeError, ValueError):
        return "待验证"
    return f"{number:+.2f}%" if signed else f"{number:.2f}%"


def _metric_pct(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "待验证"
    return f"{number:+.2f}%"


def _period(value: Any) -> str:
    text = str(value or "")
    if len(text) != 8:
        return text or "报告期待验证"
    labels = {"0331": "Q1", "0630": "H1", "0930": "Q1-Q3", "1231": "年报"}
    return f"{text[:4]}{labels.get(text[4:], text[4:])}"


def _date(value: Any) -> str:
    text = str(value or "")
    if len(text) == 8:
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text or "待公布"


def format_live_history(summary: Mapping[str, Any]) -> str:
    if not summary or not summary.get("available") or not summary.get("evaluated"):
        return "全部C线历史结果待积累"
    horizons = summary.get("horizons") or {}
    keys = [str(value) for value in (summary.get("key_horizons") or ("1", "5", "10", "30"))]
    latest = str(summary.get("latest_horizon") or summary.get("max_horizon") or "")
    display = [
        (
            horizon,
            f"T+now（当前T+{horizon}）" if latest and horizon == latest else f"T+{horizon}",
        )
        for horizon in keys
    ]
    if latest and latest not in keys and horizons.get(latest):
        display.append((latest, f"T+now（当前T+{latest}）"))

    parts = []
    for horizon, label in display:
        cell = horizons.get(horizon) or {}
        if not cell.get("evaluated"):
            continue
        cell_count = int(cell["evaluated"])
        detail = f"{label} {cell_count}次，平均收益{_pct(cell.get('avg_ret'))}"
        if cell.get("positive_ret_count") is not None:
            detail += f"，{int(cell['positive_ret_count'])}/{cell_count}次收益为正"
        parts.append(detail)
    if parts:
        return "全部C线历史：" + "；".join(parts)
    count = int(summary["evaluated"])
    text = f"live已核验{count}次，平均收益{_pct(summary.get('avg_ret'))}"
    if summary.get("positive_ret_count") is not None:
        text += f"，{int(summary['positive_ret_count'])}/{count}次收益为正"
    return "全部C线历史：" + text


def format_history_verdict(verdict: Mapping[str, Any]) -> str:
    verdict = verdict or {}
    cells = verdict.get("horizon_verdicts") or {}
    latest = str(verdict.get("latest_horizon") or "")
    display_horizons = ["1", "5", "10", "30"]
    if latest and latest not in display_horizons and cells.get(latest):
        display_horizons.append(latest)

    parts = []
    for horizon in display_horizons:
        cell = cells.get(horizon) or {}
        path_evaluated = int(cell.get("path_evaluated") or 0)
        evaluated = int(cell.get("evaluated") or 0)
        if not path_evaluated and not evaluated:
            continue
        label = f"T+now（当前T+{horizon}）" if latest and horizon == latest else f"T+{horizon}"
        all_evaluated = int(cell.get("all_evaluated") or 0)
        if evaluated:
            sample_scope = f"同动作{evaluated}/{all_evaluated}次" if all_evaluated else f"同动作{evaluated}次"
            detail = f"{label} {sample_scope}"
            if cell.get("avg_ret") is not None:
                detail += f"/平均收益{_pct(cell.get('avg_ret'))}"
            hit_count = int(cell.get("absolute_action_hit_count") or 0)
            hit_rate = cell.get("absolute_action_hit_rate")
            detail += f"/动作命中{hit_count}/{evaluated}"
            if hit_rate is not None:
                detail += f"（{_pct(hit_rate, signed=False)}）"
            dates = [str(value) for value in (cell.get("sample_dates") or []) if value]
            if dates:
                shown = dates if len(dates) <= 5 else [*dates[:4], f"等{len(dates)}日"]
                detail += "/样本日" + "、".join(shown)
        else:
            sample_scope = f"同动作路径{path_evaluated}/{all_evaluated}次" if all_evaluated else f"同动作路径{path_evaluated}次"
            detail = f"{label} {sample_scope}"
            if cell.get("avg_ret") is not None:
                detail += f"/平均收益{_pct(cell.get('avg_ret'))}"
            detail += "/当前C线动作不定义涨跌命中"
            dates = [str(value) for value in (cell.get("path_sample_dates") or []) if value]
            if dates:
                shown = dates if len(dates) <= 5 else [*dates[:4], f"等{len(dates)}日"]
                detail += "/样本日" + "、".join(shown)
        parts.append(detail)

    state = str(verdict.get("verdict") or "insufficient")
    labels = {
        "insufficient": "样本不足，不改变今天动作",
        "unscored": "当前C线动作只观察，等待D线，不做正确率评分",
        "preliminary_support": "初步支持今天动作，不提高操作力度",
        "stable_support": "较强支持今天动作，不提高操作力度",
        "preliminary_conflict": "初步反对今天动作；若原计划允许加仓，则禁止加仓",
        "stable_conflict": "较强反对今天动作；若原计划允许加仓，则禁止加仓",
        "mixed": "结果混合，不提高操作力度",
    }
    prefix = "与今天相同动作的C线历史：" + ("；".join(parts) if parts else "暂无成熟样本")
    text = f"{prefix}；{labels.get(state, '结论待验证')}"
    if verdict.get("position_review_required"):
        review = "/".join(f"T+{value}" for value in verdict.get("review_horizons") or [])
        text += f"；{review}达到稳定证据，仓位规则待人工复盘"
    return text

def format_earnings(earnings: Mapping[str, Any]) -> str:
    earnings = earnings or {}
    latest = earnings.get("latest_report") or {}
    parts = []
    if latest.get("period"):
        parts.append(_period(latest.get("period")))
    for label, key in (
        ("净利同比", "net_profit_yoy"),
        ("营收同比", "revenue_yoy"),
        ("ROE", "roe"),
        ("毛利率", "gross_margin"),
    ):
        if latest.get(key) is not None:
            parts.append(f"{label}{_metric_pct(latest.get(key))}")
    report_text = "财报待验证" if not parts else "财报 " + "，".join(parts)

    next_report = earnings.get("next_report") or {}
    expected = next_report.get("expected_ann_date")
    if expected:
        next_text = f"预计披露 {_date(expected)}（{_period(next_report.get('period'))}，交易所预约，可能修订）"
    else:
        next_text = "预计披露待公布"
    return f"{report_text}；{next_text}"

def format_today_strategy(row: Mapping[str, Any]) -> str:
    if not row:
        return "今日策略待生成"
    text = str(row.get("action") or "今日策略待确认")
    add = row.get("conditional_add") or {}
    risk = row.get("risk_reduce") or {}
    if add:
        shares = add.get("estimated_shares")
        amount = add.get("amount")
        detail = []
        if shares is not None:
            detail.append(f"约{int(shares)}股")
        if amount is not None:
            detail.append(f"{float(amount):,.2f}元")
        text += "；条件满足后加仓" + ("/".join(detail) if detail else "，金额盘中重算")
    if risk:
        shares = risk.get("estimated_shares")
        text += f"；风险触发后减仓约{int(shares)}股" if shares is not None else "；风险触发后减仓股数盘中重算"
    return text