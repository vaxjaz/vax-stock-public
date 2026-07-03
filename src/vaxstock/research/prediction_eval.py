# -*- coding: utf-8 -*-
"""EOD Prediction Layer2 analyzer (MR-Eval E4-5).

This module is a read-only interpretation layer above:
  - var/prediction/eod_predictions.jsonl
  - var/prediction/eod_prediction_results.jsonl

It evaluates whether the frozen prediction action/direction/confidence buckets
worked in later verified results. It never mutates prediction/result jsonl.
Pending predictions are counted as pending but are not included in metrics.
"""

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from vaxstock.services import eod_predictor as ep
from vaxstock.services import prediction_evaluator as pe

logger = logging.getLogger(__name__)

DEFAULT_DIMENSIONS = ("action", "direction", "confidence_bucket", "market", "concept")
HIGH_CONFIDENCE = 0.70
MEDIUM_CONFIDENCE = 0.50


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def confidence_bucket(value) -> str:
    """Map prediction confidence to a stable bucket."""
    v = _to_float(value)
    if v is None:
        return "confidence待验证"
    if v >= HIGH_CONFIDENCE:
        return "high(>=0.70)"
    if v >= MEDIUM_CONFIDENCE:
        return "medium(>=0.50)"
    return "low(<0.50)"


def market_bucket(prediction: Dict[str, Any]) -> str:
    """regime|macro_regime bucket, with honest missing markers."""
    features = prediction.get("features_ref") or {}
    regime = features.get("market_regime") or "regime待验证"
    macro = features.get("macro_regime") or "宏观待验证"
    return f"{regime}|{macro}"


def _result_key(row: Dict[str, Any]) -> tuple:
    return (row.get("prediction_id"), str(row.get("horizon") or ""))


def load_joined(*, predictions_path=None, results_path=None) -> List[Dict[str, Any]]:
    """Join predictions to verification rows by prediction_id+horizon.

    Later result rows for the same key overwrite earlier rows in memory only.
    The underlying append-only files are not changed.
    """
    predictions_path = predictions_path or ep.PREDICTIONS_FILE
    results_path = results_path or pe.PREDICTION_RESULTS_FILE
    predictions = pe._read_jsonl(predictions_path)

    results_by_key: Dict[tuple, dict] = {}
    for row in pe._read_jsonl(results_path):
        key = _result_key(row)
        if key[0] and key[1]:
            results_by_key[key] = row

    joined = []
    for pred in predictions:
        horizon = pe.prediction_horizon(pred)
        joined.append({
            "prediction": pred,
            "result": results_by_key.get((pred.get("prediction_id"), str(horizon))),
            "horizon": str(horizon),
        })
    return joined


def _bucket_values(row: Dict[str, Any], dimension: str) -> List[str]:
    pred = row.get("prediction") or {}
    payload = pred.get("prediction") or {}

    if dimension == "action":
        return [str(payload.get("action") or "action待验证")]
    if dimension == "direction":
        return [str(payload.get("direction") or "direction待验证")]
    if dimension == "confidence_bucket":
        return [confidence_bucket(payload.get("confidence"))]
    if dimension == "market":
        return [market_bucket(pred)]
    if dimension == "concept":
        concepts = pred.get("concepts") or []
        values = [str(x) for x in concepts if x]
        return values or ["concept待验证"]
    return ["unsupported_dimension"]


def _metric_cell(total: int, pending: int, evaluated: List[Dict[str, Any]]) -> Dict[str, Any]:
    rets: List[float] = []
    excesses: List[float] = []
    action_hits: List[bool] = []
    direction_hits: List[bool] = []
    deviations: Dict[str, int] = defaultdict(int)

    for row in evaluated:
        result = row.get("result") or {}
        actual = result.get("actual") or {}
        evaluation = result.get("evaluation") or {}

        ret = _to_float(actual.get("ret"))
        excess = _to_float(actual.get("excess"))
        if ret is not None:
            rets.append(ret)
        if excess is not None:
            excesses.append(excess)

        action_hit = evaluation.get("action_hit")
        if action_hit is not None:
            action_hits.append(bool(action_hit))
        direction_hit = evaluation.get("direction_hit")
        if direction_hit is not None:
            direction_hits.append(bool(direction_hit))

        deviations[str(evaluation.get("deviation") or "unknown")] += 1

    return {
        "predictions": total,
        "evaluated": len(evaluated),
        "pending": pending,
        "avg_ret": (sum(rets) / len(rets)) if rets else None,
        "avg_excess": (sum(excesses) / len(excesses)) if excesses else None,
        "positive_excess_rate": (
            sum(1 for v in excesses if v > 0) / len(excesses)
            if excesses else None
        ),
        "action_hit_rate": (
            sum(1 for v in action_hits if v) / len(action_hits)
            if action_hits else None
        ),
        "direction_hit_rate": (
            sum(1 for v in direction_hits if v) / len(direction_hits)
            if direction_hits else None
        ),
        "deviations": dict(deviations),
    }


def analyze(joined: Iterable[Dict[str, Any]], dimensions=DEFAULT_DIMENSIONS) -> Dict[str, Any]:
    """Analyze prediction verification metrics by generation mode and buckets.

    No sample-count gate is applied. N is displayed directly; pending rows are
    counted but not included in return/excess/hit-rate metrics.
    """
    rows = list(joined)
    modes: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: {"all": [], "evaluated": [], "pending": []})
    bucket_rows: Dict[str, Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: {"all": [], "evaluated": [], "pending": []}))
    )

    for row in rows:
        pred = row.get("prediction") or {}
        mode = str(pred.get("generation_mode") or "mode待验证")
        result = row.get("result")

        modes[mode]["all"].append(row)
        if result is None:
            modes[mode]["pending"].append(row)
        else:
            modes[mode]["evaluated"].append(row)

        for dimension in dimensions:
            for value in _bucket_values(row, dimension):
                box = bucket_rows[mode][dimension][value]
                box["all"].append(row)
                if result is None:
                    box["pending"].append(row)
                else:
                    box["evaluated"].append(row)

    mode_stats = {
        mode: _metric_cell(len(parts["all"]), len(parts["pending"]), parts["evaluated"])
        for mode, parts in modes.items()
    }
    bucket_stats: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {}
    for mode, by_dim in bucket_rows.items():
        bucket_stats[mode] = {}
        for dimension, by_value in by_dim.items():
            bucket_stats[mode][dimension] = {
                value: _metric_cell(len(parts["all"]), len(parts["pending"]), parts["evaluated"])
                for value, parts in by_value.items()
            }

    return {
        "total_predictions": len(rows),
        "dimensions": list(dimensions),
        "modes": mode_stats,
        "buckets": bucket_stats,
    }


def summarize_prediction_check(*, target_trade_date: Optional[str] = None,
                               joined: Optional[Iterable[Dict[str, Any]]] = None,
                               predictions_path=None,
                               results_path=None,
                               max_actions: int = 6) -> Dict[str, Any]:
    """Build a compact EOD report summary for one target trade date.

    This is a read-only helper for E4-6. It summarizes the predictions whose
    `target_trade_date` equals the just-finished EOD report trade date. Pending
    rows are counted but excluded from return/excess/hit-rate metrics.
    """
    rows = list(joined) if joined is not None else load_joined(
        predictions_path=predictions_path,
        results_path=results_path,
    )
    target = str(target_trade_date or "").strip()
    if target:
        rows = [
            row for row in rows
            if str((row.get("prediction") or {}).get("target_trade_date") or "").strip() == target
        ]
    else:
        target = _latest_trade_date(rows) or ""

    if not rows:
        return {
            "available": False,
            "target_trade_date": target or None,
            "reason": "no_predictions",
            "message": "暂无可核验 prediction 样本,待积累",
        }

    evaluated = [row for row in rows if row.get("result") is not None]
    pending = len(rows) - len(evaluated)
    summary = _metric_cell(len(rows), pending, evaluated)
    modes = analyze(rows, dimensions=("action",)).get("modes") or {}

    by_action: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(
        lambda: {"all": [], "evaluated": [], "pending": []}
    )
    for row in rows:
        action = _bucket_values(row, "action")[0]
        box = by_action[action]
        box["all"].append(row)
        if row.get("result") is None:
            box["pending"].append(row)
        else:
            box["evaluated"].append(row)

    action_rows = []
    for action, parts in by_action.items():
        cell = _metric_cell(len(parts["all"]), len(parts["pending"]), parts["evaluated"])
        cell["action"] = action
        action_rows.append(cell)
    action_rows.sort(key=lambda x: (-x["predictions"], -x["evaluated"], x["action"]))

    return {
        "available": True,
        "target_trade_date": target or None,
        "predictions": summary["predictions"],
        "evaluated": summary["evaluated"],
        "pending": summary["pending"],
        "avg_ret": summary["avg_ret"],
        "avg_excess": summary["avg_excess"],
        "positive_excess_rate": summary["positive_excess_rate"],
        "action_hit_rate": summary["action_hit_rate"],
        "direction_hit_rate": summary["direction_hit_rate"],
        "generation_modes": modes,
        "actions": action_rows[:max_actions],
    }
def _fmt_pct(value: Optional[float], *, signed: bool = False) -> str:
    if value is None:
        return "-"
    sign = "+" if signed else ""
    return f"{value * 100:{sign}.2f}%"


def _fmt_rate(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.0f}%"


def _render_metric_table(rows: List[tuple]) -> List[str]:
    lines = [
        "| bucket | predictions | evaluated | pending | avg_ret | avg_excess | excess>0 | action_hit | direction_hit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, cell in rows:
        lines.append(
            f"| {label} | {cell['predictions']} | {cell['evaluated']} | {cell['pending']} | "
            f"{_fmt_pct(cell['avg_ret'], signed=True)} | {_fmt_pct(cell['avg_excess'], signed=True)} | "
            f"{_fmt_rate(cell['positive_excess_rate'])} | {_fmt_rate(cell['action_hit_rate'])} | "
            f"{_fmt_rate(cell['direction_hit_rate'])} |"
        )
    return lines


def _dimension_title(dimension: str) -> str:
    return {
        "action": "动作 action",
        "direction": "方向 direction",
        "confidence_bucket": "置信度 confidence",
        "market": "市场环境 regime|macro",
        "concept": "概念 concept",
    }.get(dimension, dimension)


def render_report(stats: Dict[str, Any]) -> str:
    """Render markdown report for prediction Layer2."""
    lines = [
        "# EOD Prediction Layer2 评估报告",
        "",
        "> 本报告验证的是冻结预测里的 action / direction / confidence 是否命中后续真实结果,不是重新计算 score 档收益。",
        "> prediction/result 两条 jsonl 均只读; pending 样本只计数,不进入收益、超额、命中率统计。",
        "> 概念 concept 分桶采用一票多桶: 同一预测带多个概念时会分别计入各概念桶,因此概念桶 N 之和可能大于预测总数。",
        "",
    ]

    modes = stats.get("modes") or {}
    if not modes:
        lines.append("(暂无 prediction 样本)")
        return "\n".join(lines)

    lines.append("## 总览")
    overview_rows = sorted(modes.items())
    lines.extend(_render_metric_table(overview_rows))
    lines.append("")

    buckets = stats.get("buckets") or {}
    for mode in sorted(modes):
        lines.append(f"## generation_mode: {mode}")
        by_dim = buckets.get(mode) or {}
        for dimension in stats.get("dimensions") or DEFAULT_DIMENSIONS:
            values = by_dim.get(dimension) or {}
            if not values:
                continue
            lines.append(f"### {_dimension_title(dimension)}")
            ordered = sorted(values.items(), key=lambda kv: (-kv[1]["evaluated"], -kv[1]["predictions"], kv[0]))
            lines.extend(_render_metric_table(ordered))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _latest_trade_date(joined: Iterable[Dict[str, Any]]) -> Optional[str]:
    dates: List[str] = []
    for row in joined:
        pred = row.get("prediction") or {}
        td = str(pred.get("target_trade_date") or pred.get("baseline_trade_date") or "").strip()
        if td:
            dates.append(td)
    return max(dates) if dates else None


def run_prediction_layer2(*, write: bool = True, predictions_path=None, results_path=None,
                          output_dir=None) -> str:
    """load -> analyze -> render; optionally write prediction_layer2_report_<date>.md."""
    joined = load_joined(predictions_path=predictions_path, results_path=results_path)
    stats = analyze(joined)
    report = render_report(stats)
    if write:
        base_dir = Path(output_dir) if output_dir is not None else Path(predictions_path or ep.PREDICTIONS_FILE).parent
        td = _latest_trade_date(joined) or "nodate"
        out = base_dir / f"prediction_layer2_report_{td}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        logger.info(f"Prediction Layer2 报告落盘: {out}")
    return report
