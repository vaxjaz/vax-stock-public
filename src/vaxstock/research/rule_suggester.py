# -*- coding: utf-8 -*-
"""Rule suggestion report for EOD Prediction (MR-Eval E4-7).

This module is intentionally read-only. It reads frozen predictions plus
verification results and writes a markdown suggestion report. It never mutates
prediction records, result records, rule_version, or production parameters.
"""

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from vaxstock.research import prediction_eval as peval
from vaxstock.services import eod_predictor as ep

logger = logging.getLogger(__name__)

DEFAULT_MIN_EVALUATED = 20
GOOD_EXCESS = 0.015
BAD_EXCESS = -0.010
GOOD_POSITIVE_RATE = 0.60
BAD_POSITIVE_RATE = 0.40
BAD_HIT_RATE = 0.45


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bucket_value(row: Dict[str, Any], dimension: str) -> List[str]:
    pred = row.get("prediction") or {}
    payload = pred.get("prediction") or {}
    if dimension == "action":
        return [str(payload.get("action") or "action待验证")]
    if dimension == "market":
        return [peval.market_bucket(pred)]
    if dimension == "concept":
        concepts = pred.get("concepts") or []
        vals = [str(x) for x in concepts if x]
        return vals or ["concept待验证"]
    return ["unsupported_dimension"]


def _metric(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    rets: List[float] = []
    excesses: List[float] = []
    action_hits: List[bool] = []
    direction_hits: List[bool] = []
    deviations: Dict[str, int] = defaultdict(int)
    for row in rows:
        result = row.get("result") or {}
        actual = result.get("actual") or {}
        evaluation = result.get("evaluation") or {}
        ret = _to_float(actual.get("ret"))
        excess = _to_float(actual.get("excess"))
        if ret is not None:
            rets.append(ret)
        if excess is not None:
            excesses.append(excess)
        if evaluation.get("action_hit") is not None:
            action_hits.append(bool(evaluation.get("action_hit")))
        if evaluation.get("direction_hit") is not None:
            direction_hits.append(bool(evaluation.get("direction_hit")))
        deviations[str(evaluation.get("deviation") or "unknown")] += 1
    return {
        "n": len(rows),
        "avg_ret": (sum(rets) / len(rets)) if rets else None,
        "avg_excess": (sum(excesses) / len(excesses)) if excesses else None,
        "positive_excess_rate": (
            sum(1 for x in excesses if x > 0) / len(excesses)
            if excesses else None
        ),
        "action_hit_rate": (
            sum(1 for x in action_hits if x) / len(action_hits)
            if action_hits else None
        ),
        "direction_hit_rate": (
            sum(1 for x in direction_hits if x) / len(direction_hits)
            if direction_hits else None
        ),
        "deviations": dict(deviations),
    }


def _group_metrics(rows: Iterable[Dict[str, Any]], dimension: str) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for value in _bucket_value(row, dimension):
            grouped[value].append(row)
    return {key: _metric(vals) for key, vals in grouped.items()}


def _latest_evaluated_target_date(rows: Iterable[Dict[str, Any]]) -> Optional[str]:
    dates: List[str] = []
    for row in rows:
        result = row.get("result") or {}
        pred = row.get("prediction") or {}
        td = str(result.get("target_trade_date") or pred.get("target_trade_date") or "").strip()
        if td:
            dates.append(td)
    return max(dates) if dates else None


def _strength(n: int, min_evaluated: int) -> str:
    if n >= max(min_evaluated * 2, 50):
        return "strong"
    if n >= min_evaluated:
        return "medium"
    return "thin"


def _pct(value: Optional[float], *, signed: bool = False, digits: int = 2) -> str:
    if value is None:
        return "-"
    sign = "+" if signed and value >= 0 else ""
    return f"{sign}{value * 100:.{digits}f}%"


def _md_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def _evidence(cell: Dict[str, Any]) -> str:
    return (
        f"N={cell.get('n', 0)}, 平均超额={_pct(cell.get('avg_excess'), signed=True)}, "
        f"正超额率={_pct(cell.get('positive_excess_rate'), digits=0)}, "
        f"action命中={_pct(cell.get('action_hit_rate'), digits=0)}"
    )


def _suggest(priority: str, scope: str, suggestion: str, evidence: str,
             next_step: str, strength: str) -> Dict[str, Any]:
    return {
        "priority": priority,
        "scope": scope,
        "suggestion": suggestion,
        "evidence": evidence,
        "next_step": next_step,
        "evidence_strength": strength,
    }


def _good(cell: Dict[str, Any], min_evaluated: int) -> bool:
    return (
        cell.get("n", 0) >= min_evaluated
        and (cell.get("avg_excess") is not None and cell["avg_excess"] >= GOOD_EXCESS)
        and (cell.get("positive_excess_rate") is not None and cell["positive_excess_rate"] >= GOOD_POSITIVE_RATE)
    )


def _bad(cell: Dict[str, Any], min_evaluated: int) -> bool:
    action_hit = cell.get("action_hit_rate")
    hit_bad = action_hit is not None and action_hit <= BAD_HIT_RATE
    return (
        cell.get("n", 0) >= min_evaluated
        and (cell.get("avg_excess") is not None and cell["avg_excess"] <= BAD_EXCESS)
        and (
            (cell.get("positive_excess_rate") is not None and cell["positive_excess_rate"] <= BAD_POSITIVE_RATE)
            or hit_bad
        )
    )


def build_rule_suggestions(*, joined: Optional[Iterable[Dict[str, Any]]] = None,
                           predictions_path=None,
                           results_path=None,
                           min_evaluated: int = DEFAULT_MIN_EVALUATED) -> Dict[str, Any]:
    """Build deterministic rule suggestions from evaluated prediction rows."""
    rows = list(joined) if joined is not None else peval.load_joined(
        predictions_path=predictions_path,
        results_path=results_path,
    )
    evaluated = [row for row in rows if row.get("result") is not None]
    pending = len(rows) - len(evaluated)
    report_date = _latest_evaluated_target_date(evaluated)

    action_stats = _group_metrics(evaluated, "action")
    market_stats = _group_metrics(evaluated, "market")
    concept_stats = _group_metrics(evaluated, "concept")
    suggestions: List[Dict[str, Any]] = []

    for action, cell in sorted(action_stats.items()):
        strength = _strength(cell["n"], min_evaluated)
        if action.startswith("panic_rebound") and _good(cell, min_evaluated):
            suggestions.append(_suggest(
                "P1", f"action:{action}",
                "保留 panic 修复分支; 可作为左侧修复规则候选继续单独验证。",
                _evidence(cell),
                "人工审核后再决定是否拆成 left/panic_repair 独立 rule_version。",
                strength,
            ))
        elif action == "watch" and _bad(cell, min_evaluated):
            suggestions.append(_suggest(
                "P1", "action:watch",
                "收紧 watch 动作的触发条件,尤其避免在弱环境里把普通观察误判为正超额。",
                _evidence(cell),
                "优先排查 watch 的 market/concept 子桶,只出建议,不直接调参。",
                strength,
            ))
        elif action == "avoid" and cell["n"] >= min_evaluated and (
            cell.get("action_hit_rate") is not None and cell["action_hit_rate"] >= 0.60
        ):
            suggestions.append(_suggest(
                "P2", "action:avoid",
                "avoid 下限过滤目前有一定保护作用,建议保留为防守规则。",
                _evidence(cell),
                "继续观察是否在强主线概念里过度回避。",
                strength,
            ))
        elif cell["n"] < min_evaluated:
            suggestions.append(_suggest(
                "P3", f"action:{action}",
                "样本薄,只记录观察,不建议升级规则。",
                _evidence(cell),
                "继续积累样本; 人工复盘单票,不改 rule_version。",
                strength,
            ))

    for market, cell in sorted(market_stats.items()):
        strength = _strength(cell["n"], min_evaluated)
        if market.startswith("panic|") and _good(cell, min_evaluated):
            suggestions.append(_suggest(
                "P1", f"market:{market}",
                "panic 环境后的修复交易有正向证据,建议把 panic 修复和普通右侧追随分开评估。",
                _evidence(cell),
                "候选方向: 单独建立 left_repair/panic_repair 规则,人工确认后 bump rule_version。",
                strength,
            ))
        elif market.startswith("value|") and _bad(cell, min_evaluated):
            suggestions.append(_suggest(
                "P1", f"market:{market}",
                "value/中性环境下当前动作预测偏弱,建议降低普通 watch 的正超额预期。",
                _evidence(cell),
                "候选方向: value|中性 桶要求额外资金/业绩确认,暂不自动改参数。",
                strength,
            ))

    concept_rows = []
    for concept, cell in concept_stats.items():
        if concept == "concept待验证":
            continue
        if _good(cell, min_evaluated) or _bad(cell, min_evaluated):
            concept_rows.append((concept, cell))
    concept_rows.sort(key=lambda x: abs(x[1].get("avg_excess") or 0), reverse=True)
    for concept, cell in concept_rows[:4]:
        strength = _strength(cell["n"], min_evaluated)
        if _good(cell, min_evaluated):
            suggestions.append(_suggest(
                "P2", f"concept:{concept}",
                "该概念桶有正超额证据,可作为动作规则的加分候选,但概念桶是一票多桶。",
                _evidence(cell),
                "只纳入人工候选; 需要与个股基本面/资金确认交叉验证。",
                strength,
            ))
        elif _bad(cell, min_evaluated):
            suggestions.append(_suggest(
                "P2", f"concept:{concept}",
                "该概念桶阶段性拖累预测表现,不宜只因概念标签提高动作置信度。",
                _evidence(cell),
                "人工复盘成分股差异; 暂不自动降权。",
                strength,
            ))

    priority_order = {"P1": 0, "P2": 1, "P3": 2}
    suggestions.sort(key=lambda x: (priority_order.get(x["priority"], 9), x["scope"]))
    return {
        "report_date": report_date,
        "source_predictions": len(rows),
        "evaluated": len(evaluated),
        "pending": pending,
        "min_evaluated": min_evaluated,
        "actions": action_stats,
        "markets": market_stats,
        "concepts": concept_stats,
        "suggestions": suggestions,
    }


def _render_metric_rows(stats: Dict[str, Dict[str, Any]], *, limit: int = 12) -> List[str]:
    lines = [
        "| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    rows = sorted(
        stats.items(),
        key=lambda kv: (-(kv[1].get("n") or 0), kv[0]),
    )[:limit]
    for bucket, cell in rows:
        lines.append(
            f"| {_md_cell(bucket)} | {cell.get('n', 0)} | {_pct(cell.get('avg_excess'), signed=True)} | "
            f"{_pct(cell.get('positive_excess_rate'), digits=0)} | "
            f"{_pct(cell.get('action_hit_rate'), digits=0)} | "
            f"{_pct(cell.get('direction_hit_rate'), digits=0)} |"
        )
    return lines


def render_rule_suggestions(report: Dict[str, Any]) -> str:
    """Render markdown rule suggestion report."""
    td = report.get("report_date") or "nodate"
    lines = [
        f"# Rule Suggestions {td}",
        "",
        "> 本报告只给规则升级建议和证据,不自动改参数、不修改历史 prediction、不 bump rule_version。",
        "> N 直接展示; 样本薄会标注为 thin,但不会被隐藏。pending 样本不进入收益/命中率统计。",
        "> concept 桶是一票多桶,只能作为候选证据,不能单独决定交易动作。",
        "",
        f"- source_predictions: {report.get('source_predictions', 0)}",
        f"- evaluated: {report.get('evaluated', 0)}",
        f"- pending: {report.get('pending', 0)}",
        f"- min_evaluated_reference: {report.get('min_evaluated', DEFAULT_MIN_EVALUATED)}",
        "",
    ]

    suggestions = report.get("suggestions") or []
    lines.append("## 建议清单")
    if not suggestions:
        lines.append("- 暂无可行动建议; 继续积累样本。")
    else:
        lines.append("| priority | scope | evidence_strength | suggestion | evidence | next_step |")
        lines.append("|---|---|---|---|---|---|")
        for s in suggestions:
            lines.append(
                f"| {_md_cell(s['priority'])} | {_md_cell(s['scope'])} | {_md_cell(s['evidence_strength'])} | "
                f"{_md_cell(s['suggestion'])} | {_md_cell(s['evidence'])} | {_md_cell(s['next_step'])} |"
            )
    lines.append("")

    lines.append("## Action 证据")
    lines.extend(_render_metric_rows(report.get("actions") or {}))
    lines.append("")

    lines.append("## Market 证据")
    lines.extend(_render_metric_rows(report.get("markets") or {}))
    lines.append("")

    lines.append("## Concept 证据(Top by N)")
    lines.extend(_render_metric_rows(report.get("concepts") or {}, limit=15))
    lines.append("")

    lines.append("## 人工审核提醒")
    lines.append("- 任何采纳都必须另开 PR,并显式 bump `rule_version`。")
    lines.append("- 不回写 `eod_predictions.jsonl`; 历史预测原文保持可审计。")
    lines.append("- 左侧/panic 修复若要落地,应独立命名规则,不要污染 `right_side_score`。")
    return "\n".join(lines).rstrip() + "\n"


def run_rule_suggestions(*, write: bool = True, predictions_path=None, results_path=None,
                         output_dir=None, min_evaluated: int = DEFAULT_MIN_EVALUATED) -> str:
    """Build and optionally write rule_suggestions_<trade_date>.md."""
    report = build_rule_suggestions(
        predictions_path=predictions_path,
        results_path=results_path,
        min_evaluated=min_evaluated,
    )
    text = render_rule_suggestions(report)
    if write:
        base_dir = Path(output_dir) if output_dir is not None else Path(predictions_path or ep.PREDICTIONS_FILE).parent
        td = report.get("report_date") or "nodate"
        out = base_dir / f"rule_suggestions_{td}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        logger.info(f"Rule suggestions 报告落盘: {out}")
    return text
