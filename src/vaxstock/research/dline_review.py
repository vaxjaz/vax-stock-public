# -*- coding: utf-8 -*-
"""Evaluate D-line classification and intraday trigger timing."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from vaxstock import config
from vaxstock.services.dline_evaluator import RESULTS_FILE, _read_jsonl
from vaxstock.services.forecast_evolution import EVOLUTION_HISTORY_FILE

REPORT_DIR = config.STATE_DIR / "forecast" / "dline_reviews"
STATE_FILE = REPORT_DIR / "dline_rule_review_latest.json"
MIN_GROUP_SAMPLES = 5
STABLE_GROUP_SAMPLES = 20
MIN_EVOLUTION_SAMPLES = 5
STABLE_EVOLUTION_SAMPLES = 20
SUPPORT_HIT_RATE = 0.60
CONFLICT_HIT_RATE = 0.40
DISPLAY_HORIZONS = ("1", "5", "10", "30")


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _average(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None]
    return mean(clean) if clean else None


def _latest_by_key(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest = {}
    for row in rows:
        key = (str(row.get("sample_id") or ""), str(row.get("horizon") or ""))
        if all(key):
            latest[key] = row
    return list(latest.values())


def _latest_evolution_index(rows: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    latest = {}
    for row in rows:
        key = (
            str(row.get("task_id") or ""),
            str(row.get("trigger_type") or ""),
        )
        if all(key):
            latest[key] = row
    return latest


def _cell_key(row: Mapping[str, Any]) -> Tuple[str, str, str]:
    return (
        str(row.get("plan_version") or ""),
        str(row.get("trigger_type") or ""),
        str(row.get("horizon") or ""),
    )


def _verdict(*, triggered_n: int, not_triggered_n: int, hit_rate: Optional[float],
             separation: Optional[float]) -> str:
    if triggered_n < MIN_GROUP_SAMPLES or not_triggered_n < MIN_GROUP_SAMPLES:
        return "insufficient_counterfactual"
    stable = (
        triggered_n >= STABLE_GROUP_SAMPLES
        and not_triggered_n >= STABLE_GROUP_SAMPLES
    )
    strength = "stable" if stable else "preliminary"
    if hit_rate is not None and separation is not None:
        if hit_rate >= SUPPORT_HIT_RATE and separation > 0:
            return f"{strength}_support"
        if hit_rate <= CONFLICT_HIT_RATE and separation <= 0:
            return f"{strength}_conflict"
    return "mixed"


def _direction_hit(expectation: str, value: Optional[float]) -> Optional[bool]:
    if value is None or expectation == "unscored":
        return None
    if expectation == "positive":
        return value > 0
    if expectation == "non_positive":
        return value <= 0
    return None


def _timing_diagnosis(n_30m: int, n_close: int,
                      rate_30m: Optional[float], rate_close: Optional[float]) -> str:
    if n_30m < MIN_EVOLUTION_SAMPLES or n_close < MIN_EVOLUTION_SAMPLES:
        return "insufficient_intraday_path"
    stable = n_30m >= STABLE_EVOLUTION_SAMPLES and n_close >= STABLE_EVOLUTION_SAMPLES
    strength = "stable" if stable else "preliminary"
    if rate_30m >= SUPPORT_HIT_RATE and rate_close >= SUPPORT_HIT_RATE:
        return f"{strength}_sustained"
    if rate_30m <= CONFLICT_HIT_RATE and rate_close >= SUPPORT_HIT_RATE:
        return f"{strength}_trigger_early"
    if rate_30m >= SUPPORT_HIT_RATE and rate_close <= CONFLICT_HIT_RATE:
        return f"{strength}_intraday_fade"
    if rate_30m <= CONFLICT_HIT_RATE and rate_close <= CONFLICT_HIT_RATE:
        return f"{strength}_intraday_conflict"
    return "mixed_intraday_path"


def _timing_suggestion(diagnosis: str) -> str:
    if diagnosis.endswith("_trigger_early"):
        return "review_confirmation_delay"
    if diagnosis.endswith("_intraday_fade"):
        return "review_falsification_or_exit_condition"
    if diagnosis.endswith("_intraday_conflict"):
        return "review_trigger_tighten_or_remove"
    if diagnosis.endswith("_sustained"):
        return "keep_trigger_timing"
    return "collect_intraday_path"


def _evolution_metrics(triggered: Iterable[Dict[str, Any]], expectation: str,
                       index: Mapping[Tuple[str, str], Dict[str, Any]]) -> Dict[str, Any]:
    selected = []
    seen = set()
    for result in triggered:
        key = (
            str(result.get("task_id") or ""),
            str(result.get("trigger_type") or ""),
        )
        evolution = index.get(key)
        evolution_id = str((evolution or {}).get("evolution_id") or "")
        if evolution and evolution_id not in seen:
            selected.append(evolution)
            seen.add(evolution_id)

    def checkpoint_returns(label: str) -> List[float]:
        values = []
        for row in selected:
            value = _number(
                (((row.get("checkpoints") or {}).get(label) or {}).get("return_from_trigger"))
            )
            if value is not None:
                values.append(value)
        return values

    ret_15m = checkpoint_returns("15m")
    ret_30m = checkpoint_returns("30m")
    ret_close = checkpoint_returns("close")
    hits_30m = [_direction_hit(expectation, value) for value in ret_30m]
    hits_close = [_direction_hit(expectation, value) for value in ret_close]
    clean_30m = [value for value in hits_30m if value is not None]
    clean_close = [value for value in hits_close if value is not None]
    rate_30m = (
        sum(value is True for value in clean_30m) / len(clean_30m)
        if clean_30m else None
    )
    rate_close = (
        sum(value is True for value in clean_close) / len(clean_close)
        if clean_close else None
    )
    diagnosis = _timing_diagnosis(
        len(clean_30m), len(clean_close), rate_30m, rate_close,
    )
    return {
        "evolution_samples": len(selected),
        "checkpoint_15m_n": len(ret_15m),
        "checkpoint_30m_n": len(clean_30m),
        "checkpoint_close_n": len(clean_close),
        "avg_15m_return_from_trigger": _average(ret_15m),
        "avg_30m_return_from_trigger": _average(ret_30m),
        "avg_close_return_from_trigger": _average(ret_close),
        "direction_hit_rate_30m": rate_30m,
        "direction_hit_rate_close": rate_close,
        "avg_max_return_from_trigger": _average(
            _number((row.get("path") or {}).get("max_return_from_trigger"))
            for row in selected
        ),
        "avg_min_return_from_trigger": _average(
            _number((row.get("path") or {}).get("min_return_from_trigger"))
            for row in selected
        ),
        "timing_diagnosis": diagnosis,
        "timing_suggestion": _timing_suggestion(diagnosis),
    }


def build_dline_review(rows: Iterable[Dict[str, Any]], *,
                       evolution_rows: Iterable[Dict[str, Any]] = (),
                       as_of_trade_date: Optional[str] = None) -> Dict[str, Any]:
    grouped: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for row in _latest_by_key(rows):
        horizon = str(row.get("horizon") or "")
        if horizon not in DISPLAY_HORIZONS:
            continue
        if as_of_trade_date:
            horizon_date = str(row.get("horizon_trade_date") or "")
            if horizon_date and horizon_date > str(as_of_trade_date):
                continue
        grouped.setdefault(_cell_key(row), []).append(row)

    evolution_index = _latest_evolution_index(evolution_rows)
    cells = []
    for (plan_version, trigger_type, horizon), group in sorted(grouped.items()):
        expectation = str(group[0].get("expectation") or "unscored")
        scored = [
            row for row in group
            if (row.get("evaluation") or {}).get("decision_hit") is not None
        ]
        triggered = [
            row for row in scored
            if ((row.get("trigger") or {}).get("status") == "triggered")
        ]
        not_triggered = [
            row for row in scored
            if ((row.get("trigger") or {}).get("status") == "qualified_not_triggered")
        ]
        triggered_close_returns = [
            _number((row.get("outcome") or {}).get("ret_from_target_close"))
            for row in triggered
        ]
        not_triggered_close_returns = [
            _number((row.get("outcome") or {}).get("ret_from_target_close"))
            for row in not_triggered
        ]
        avg_triggered = _average(triggered_close_returns)
        avg_not_triggered = _average(not_triggered_close_returns)
        separation = None
        if avg_triggered is not None and avg_not_triggered is not None:
            separation = (
                avg_triggered - avg_not_triggered
                if expectation == "positive"
                else avg_not_triggered - avg_triggered
                if expectation == "non_positive"
                else None
            )
        hits = sum(
            1 for row in scored
            if (row.get("evaluation") or {}).get("decision_hit") is True
        )
        hit_rate = hits / len(scored) if scored else None
        verdict = _verdict(
            triggered_n=len(triggered),
            not_triggered_n=len(not_triggered),
            hit_rate=hit_rate,
            separation=separation,
        )
        timing = _evolution_metrics(triggered, expectation, evolution_index)
        cells.append({
            "cell_key": "|".join((plan_version, trigger_type, horizon)),
            "plan_version": plan_version,
            "trigger_type": trigger_type,
            "expectation": expectation,
            "horizon": horizon,
            "evaluated": len(scored),
            "triggered": len(triggered),
            "qualified_not_triggered": len(not_triggered),
            "decision_hits": hits,
            "decision_hit_rate": hit_rate,
            "avg_triggered_ret_from_target_close": avg_triggered,
            "avg_not_triggered_ret_from_target_close": avg_not_triggered,
            "incremental_separation": separation,
            "verdict": verdict,
            "suggestion": (
                "review_rule_tighten_or_remove"
                if verdict.endswith("_conflict")
                else "keep_rule"
                if verdict.endswith("_support")
                else "collect_counterfactual"
                if verdict == "insufficient_counterfactual"
                else "hold_current_rule"
            ),
            "intraday_evolution": timing,
        })
    return {
        "schema_version": 2,
        "as_of_trade_date": str(as_of_trade_date or ""),
        "basis": {
            "primary_return": "stock_absolute_return",
            "triggered_vs_not_triggered": "same_plan_version_trigger_type_horizon",
            "intraday_path": "verified_quotes_at_15m_30m_and_last_verified_close_quote",
            "checkpoint_max_delay_seconds": 300,
            "minimum_samples_per_side": MIN_GROUP_SAMPLES,
            "stable_samples_per_side": STABLE_GROUP_SAMPLES,
            "minimum_intraday_paths": MIN_EVOLUTION_SAMPLES,
            "user_execution_used": False,
            "automatic_parameter_change": False,
        },
        "cells": cells,
    }


def _pct(value: Optional[float]) -> str:
    return "\u5f85\u9a8c\u8bc1" if value is None else f"{value:+.2%}"


def _rate(value: Optional[float]) -> str:
    return "\u5f85\u9a8c\u8bc1" if value is None else f"{value:.0%}"


def render_dline_review(report: Mapping[str, Any]) -> str:
    lines = [
        f"# D\u7ebf\u89c4\u5219\u6548\u679c\u590d\u6838 {report.get('as_of_trade_date') or '\u5f85\u9a8c\u8bc1'}",
        "",
        "- \u957f\u671f\u7ed3\u679c: \u5df2\u89e6\u53d1\u4e0e\u5408\u683c\u672a\u89e6\u53d1\u6309\u540c\u4e00\u6536\u76ca\u53e3\u5f84\u5bf9\u7167\u3002",
        "- \u76d8\u4e2d\u6f14\u53d8: \u4ec5\u4f7f\u7528\u89e6\u53d1\u540e\u5df2\u9a8c\u8bc1 quote \u8ba1\u7b97 15/30 \u5206\u949f\u4e0e\u6536\u76d8\u524d\u8def\u5f84\u3002",
        "- \u8fb9\u754c: \u4e0d\u8bfb\u53d6\u7528\u6237\u6210\u4ea4,\u4e0d\u81ea\u52a8\u4fee\u6539\u751f\u4ea7\u53c2\u6570\u3002",
        "",
        "| \u89c4\u5219\u7248\u672c | \u89e6\u53d1\u7c7b\u578b | \u5468\u671f | \u89e6\u53d1/\u672a\u89e6\u53d1 | \u957f\u671f\u547d\u4e2d | \u589e\u91cf\u5206\u79bb | 30\u5206\u949f\u547d\u4e2d | \u6536\u76d8\u547d\u4e2d | \u65f6\u673a\u8bca\u65ad | \u89c4\u5219\u7ed3\u8bba |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for cell in report.get("cells") or []:
        timing = cell.get("intraday_evolution") or {}
        lines.append(
            f"| {cell.get('plan_version')} | {cell.get('trigger_type')} | "
            f"T+{cell.get('horizon')} | {cell.get('triggered')}/"
            f"{cell.get('qualified_not_triggered')} | "
            f"{_rate(cell.get('decision_hit_rate'))} | "
            f"{_pct(cell.get('incremental_separation'))} | "
            f"{_rate(timing.get('direction_hit_rate_30m'))} "
            f"(N={timing.get('checkpoint_30m_n', 0)}) | "
            f"{_rate(timing.get('direction_hit_rate_close'))} "
            f"(N={timing.get('checkpoint_close_n', 0)}) | "
            f"{timing.get('timing_diagnosis')} | {cell.get('verdict')} |"
        )
    if not report.get("cells"):
        lines.append("| - | - | - | - | - | - | - | - | - | \u5f85\u9a8c\u8bc1 |")
    lines += [
        "",
        "> \u7ed3\u8bba\u53ea\u662f\u53ef\u5ba1\u8ba1\u8bc1\u636e;\u751f\u4ea7D\u7ebf\u89c4\u5219\u4e0d\u4f1a\u81ea\u52a8\u8c03\u53c2\u3002",
    ]
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _changed_cells(previous: Mapping[str, Any], current: Mapping[str, Any]) -> List[Dict[str, Any]]:
    old = {str(cell.get("cell_key")): cell for cell in previous.get("cells") or []}
    changes = []
    timing_seen = set()
    for cell in current.get("cells") or []:
        key = str(cell.get("cell_key") or "")
        old_cell = old.get(key) or {}
        before = str(old_cell.get("verdict") or "") or None
        after = str(cell.get("verdict") or "")
        material = after.endswith("_support") or after.endswith("_conflict")
        if before != after and (before is not None or material):
            changes.append({
                "cell_key": key,
                "before": before or "new_evidence",
                "after": after,
                "suggestion": cell.get("suggestion"),
            })

        timing_change_key = "|".join((
            str(cell.get("plan_version") or ""),
            str(cell.get("trigger_type") or ""),
            "intraday",
        ))
        if timing_change_key in timing_seen:
            continue
        timing_seen.add(timing_change_key)
        old_timing = str((old_cell.get("intraday_evolution") or {}).get("timing_diagnosis") or "") or None
        timing = cell.get("intraday_evolution") or {}
        new_timing = str(timing.get("timing_diagnosis") or "")
        timing_material = (
            new_timing not in {
                "", "insufficient_intraday_path", "mixed_intraday_path",
            }
        )
        if old_timing != new_timing and (old_timing is not None or timing_material):
            changes.append({
                "cell_key": timing_change_key,
                "before": old_timing or "new_evidence",
                "after": new_timing,
                "suggestion": timing.get("timing_suggestion"),
            })
    return changes


def run_dline_review(*, write: bool = True, results_path=None,
                     evolution_path=None, output_dir=None, state_path=None,
                     as_of_trade_date: Optional[str] = None) -> Dict[str, Any]:
    report = build_dline_review(
        _read_jsonl(results_path or RESULTS_FILE),
        evolution_rows=_read_jsonl(evolution_path or EVOLUTION_HISTORY_FILE),
        as_of_trade_date=as_of_trade_date,
    )
    state = Path(state_path or STATE_FILE)
    report["changes"] = _changed_cells(_read_json(state), report)
    if write:
        directory = Path(output_dir or REPORT_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        token = str(as_of_trade_date or "latest")
        markdown = render_dline_review(report)
        (directory / f"dline_review_{token}.md").write_text(markdown, encoding="utf-8")
        (directory / "dline_review_latest.md").write_text(markdown, encoding="utf-8")
        state.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report
