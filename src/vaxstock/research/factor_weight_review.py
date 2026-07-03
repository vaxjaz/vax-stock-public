# -*- coding: utf-8 -*-
"""Factor weight review report for MR-Eval E3.

This module is intentionally read-only. It joins frozen factor snapshots with
future result rows, then renders a human review report for possible factor
weight changes. It never mutates scoring weights, snapshots, or results.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from vaxstock.services import eval_recorder as er

logger = logging.getLogger(__name__)

DEFAULT_HORIZON = 1
DEFAULT_MIN_REFERENCE = 20
DEFAULT_SPREAD_THRESHOLD = 0.01

DEFAULT_FACTORS = (
    {"metric": "right_side_score", "label": "right_side_score"},
    {"metric": "main_inflow_5d", "label": "main_inflow_5d"},
    {"metric": "inflow_slope", "label": "inflow_slope"},
    {"metric": "pe_percentile_1y", "label": "pe_percentile_1y"},
    {"metric": "pb_percentile_1y", "label": "pb_percentile_1y"},
    {"metric": "position_20d_pct", "label": "position_20d_pct"},
    {"metric": "position_52w_pct", "label": "position_52w_pct"},
    {"metric": "rsi_14", "label": "rsi_14"},
    {"metric": "volume_ratio_5d", "label": "volume_ratio_5d"},
    {"metric": "turnover_zscore", "label": "turnover_zscore"},
    {"metric": "np_yoy", "label": "np_yoy"},
    {"metric": "roe_avg", "label": "roe_avg"},
)


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_jsonl(path) -> List[Dict[str, Any]]:
    return er._read_jsonl(path)


def load_joined(*, snapshots_path=None, results_path=None) -> List[Dict[str, Any]]:
    """Join frozen factor snapshots with latest result rows by (trade_date, code)."""
    snapshots_path = snapshots_path or er.SNAPSHOTS_FILE
    results_path = results_path or er.RESULTS_FILE
    results_by_key: Dict[tuple, dict] = {}
    for row in _read_jsonl(results_path):
        key = (str(row.get("trade_date") or ""), str(row.get("code") or ""))
        if key[0] and key[1]:
            results_by_key[key] = row

    joined = []
    for snap in _read_jsonl(snapshots_path):
        key = (str(snap.get("trade_date") or ""), str(snap.get("code") or ""))
        joined.append({"snapshot": snap, "result": results_by_key.get(key)})
    return joined


def _result_excess(row: Dict[str, Any], horizon: int) -> Optional[float]:
    result = row.get("result") or {}
    excess = result.get("excess") or {}
    return _to_float(excess.get(str(horizon)))


def _metric_value(snapshot: Dict[str, Any], metric: str) -> Optional[float]:
    return _to_float((snapshot.get("metrics") or {}).get(metric))


def _avg(values: Iterable[float]) -> Optional[float]:
    vals = list(values)
    return (sum(vals) / len(vals)) if vals else None


def _positive_rate(values: Iterable[float]) -> Optional[float]:
    vals = list(values)
    return (sum(1 for v in vals if v > 0) / len(vals)) if vals else None


def _bucket_cell(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    values = [r["value"] for r in rows]
    excesses = [r["excess"] for r in rows]
    return {
        "n": len(rows),
        "value_min": min(values) if values else None,
        "value_max": max(values) if values else None,
        "avg_excess": _avg(excesses),
        "positive_excess_rate": _positive_rate(excesses),
    }


def _strength(n: int, min_reference: int) -> str:
    if n >= max(min_reference * 2, 50):
        return "strong"
    if n >= min_reference:
        return "medium"
    return "thin"


def _review_action(spread: Optional[float], threshold: float) -> str:
    if spread is None:
        return "collect_more"
    if spread >= threshold:
        return "consider_up_weight_for_high_value"
    if spread <= -threshold:
        return "consider_penalty_for_high_value_or_inverse_weight"
    return "watch_no_change"


def analyze(joined: Iterable[Dict[str, Any]], *, horizon: int = DEFAULT_HORIZON,
            factors=DEFAULT_FACTORS, min_reference: int = DEFAULT_MIN_REFERENCE,
            spread_threshold: float = DEFAULT_SPREAD_THRESHOLD) -> Dict[str, Any]:
    """Analyze factor high/low buckets for human weight review.

    No sample-count gate is applied. N is shown directly; low/high buckets are
    bottom/top thirds by the frozen metric value. Rows without a verified excess
    for the requested horizon are counted as pending_or_unfilled and do not enter
    metric statistics.
    """
    rows = list(joined)
    evaluated = [r for r in rows if _result_excess(r, horizon) is not None]
    pending_or_unfilled = len(rows) - len(evaluated)

    factor_rows = []
    for spec in factors:
        metric = spec["metric"]
        usable: List[Dict[str, Any]] = []
        missing_metric = 0
        for row in evaluated:
            snap = row.get("snapshot") or {}
            value = _metric_value(snap, metric)
            excess = _result_excess(row, horizon)
            if value is None:
                missing_metric += 1
                continue
            usable.append({"value": value, "excess": excess, "row": row})

        usable.sort(key=lambda x: x["value"])
        if len(usable) >= 2:
            cut = max(1, len(usable) // 3)
            low_rows = usable[:cut]
            high_rows = usable[-cut:]
        else:
            low_rows = []
            high_rows = usable[:]

        low = _bucket_cell(low_rows)
        high = _bucket_cell(high_rows)
        spread = None
        if high["avg_excess"] is not None and low["avg_excess"] is not None:
            spread = high["avg_excess"] - low["avg_excess"]

        factor_rows.append({
            "metric": metric,
            "label": spec.get("label") or metric,
            "evaluated": len(usable),
            "missing_metric": missing_metric,
            "low": low,
            "high": high,
            "high_minus_low_excess": spread,
            "evidence_strength": _strength(len(usable), min_reference),
            "review_action": _review_action(spread, spread_threshold),
        })

    factor_rows.sort(key=lambda r: (
        r["high_minus_low_excess"] is None,
        -abs(r["high_minus_low_excess"] or 0),
        -r["evaluated"],
        r["metric"],
    ))

    return {
        "schema_version": 1,
        "horizon": horizon,
        "total_snapshots": len(rows),
        "evaluated_rows": len(evaluated),
        "pending_or_unfilled": pending_or_unfilled,
        "min_reference": min_reference,
        "spread_threshold": spread_threshold,
        "factors": factor_rows,
        "latest_trade_date": _latest_trade_date(rows),
    }


def _latest_trade_date(rows: Iterable[Dict[str, Any]]) -> Optional[str]:
    dates: List[str] = []
    for row in rows:
        snap = row.get("snapshot") or {}
        td = str(snap.get("trade_date") or "").strip()
        if td:
            dates.append(td)
    return max(dates) if dates else None


def _pct(value: Optional[float], *, signed: bool = False) -> str:
    if value is None:
        return "-"
    sign = "+" if signed and value >= 0 else ""
    return f"{sign}{value * 100:.2f}%"


def _num(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{value:.4g}"


def _md_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def _term_glossary_lines() -> List[str]:
    return [
        "## 术语说明",
        "- `low bucket` / `high bucket`: 按冻结因子值排序后的底部/顶部三分位样本。",
        "- `low_avg_excess` / `high_avg_excess`: 低值桶/高值桶在目标 horizon 的平均超额收益。",
        "- `high-low`: 高值桶平均超额减低值桶平均超额; 正数表示高值桶阶段性更占优,负数表示高值桶更弱。",
        "- `evidence_strength`: `thin`/`medium`/`strong` 只提示样本证据厚薄,不隐藏任何桶,也不自动形成结论。",
        "- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子的正向权重。",
        "- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶弱于低值桶,可人工复核是否降权或改成反向惩罚。",
        "- `watch_no_change`: 暂无足够方向性证据,继续观察。",
        "- `collect_more`: 缺少可比较样本或字段缺失,继续积累,不做调权动作。",
    ]

def render_report(stats: Dict[str, Any]) -> str:
    """Render a markdown report for manual factor weight review."""
    td = stats.get("latest_trade_date") or "nodate"
    lines = [
        f"# Factor Weight Review {td}",
        "",
        "> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。",
        "> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。",
        "> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。",
        "",
        f"- horizon: T+{stats.get('horizon')}",
        f"- total_snapshots: {stats.get('total_snapshots', 0)}",
        f"- evaluated_rows: {stats.get('evaluated_rows', 0)}",
        f"- pending_or_unfilled: {stats.get('pending_or_unfilled', 0)}",
        f"- min_reference_for_strength: {stats.get('min_reference')}",
        f"- spread_threshold_reference: {_pct(stats.get('spread_threshold'), signed=True)}",
        "",
        *_term_glossary_lines(),
        "",
        "## 因子证据总表",
        "| factor | N | missing_metric | low_range | low_avg_excess | low_excess>0 | high_range | high_avg_excess | high_excess>0 | high-low | strength | review_action |",
        "|---|---:|---:|---|---:|---:|---|---:|---:|---:|---|---|",
    ]

    factors = stats.get("factors") or []
    if not factors:
        lines.append("| - | 0 | 0 | - | - | - | - | - | - | - | thin | collect_more |")
    for row in factors:
        low = row.get("low") or {}
        high = row.get("high") or {}
        lines.append(
            f"| {_md_cell(row.get('label'))} | {row.get('evaluated', 0)} | {row.get('missing_metric', 0)} | "
            f"{_num(low.get('value_min'))}~{_num(low.get('value_max'))} | {_pct(low.get('avg_excess'), signed=True)} | "
            f"{_pct(low.get('positive_excess_rate'))} | {_num(high.get('value_min'))}~{_num(high.get('value_max'))} | "
            f"{_pct(high.get('avg_excess'), signed=True)} | {_pct(high.get('positive_excess_rate'))} | "
            f"{_pct(row.get('high_minus_low_excess'), signed=True)} | {_md_cell(row.get('evidence_strength'))} | "
            f"{_md_cell(row.get('review_action'))} |"
        )

    lines.extend([
        "",
        "## 人工处理规则",
        "- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。",
        "- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。",
        "- `watch_no_change`: 暂无足够方向性证据,保留观察。",
        "- `collect_more`: 缺少可比较样本或字段缺失,继续积累。",
        "- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def run_factor_weight_review(*, write: bool = True, snapshots_path=None, results_path=None,
                             output_dir=None, horizon: int = DEFAULT_HORIZON,
                             min_reference: int = DEFAULT_MIN_REFERENCE) -> str:
    """load -> analyze -> render; optionally write factor_weight_review_<date>.md."""
    joined = load_joined(snapshots_path=snapshots_path, results_path=results_path)
    stats = analyze(joined, horizon=horizon, min_reference=min_reference)
    report = render_report(stats)
    if write:
        base_dir = Path(output_dir) if output_dir is not None else Path(snapshots_path or er.SNAPSHOTS_FILE).parent
        td = stats.get("latest_trade_date") or "nodate"
        out = base_dir / f"factor_weight_review_{td}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        logger.info(f"Factor weight review report written: {out}")
    return report