# -*- coding: utf-8 -*-
"""Evaluate whether D-line triggers add value over qualified no-trigger samples."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from vaxstock import config
from vaxstock.services.dline_evaluator import RESULTS_FILE, _read_jsonl

REPORT_DIR = config.STATE_DIR / "forecast" / "dline_reviews"
STATE_FILE = REPORT_DIR / "dline_rule_review_latest.json"
MIN_GROUP_SAMPLES = 5
STABLE_GROUP_SAMPLES = 20
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


def build_dline_review(rows: Iterable[Dict[str, Any]], *,
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
        })
    return {
        "schema_version": 1,
        "as_of_trade_date": str(as_of_trade_date or ""),
        "basis": {
            "primary_return": "stock_absolute_return",
            "triggered_vs_not_triggered": "same_plan_version_trigger_type_horizon",
            "minimum_samples_per_side": MIN_GROUP_SAMPLES,
            "stable_samples_per_side": STABLE_GROUP_SAMPLES,
            "user_execution_used": False,
            "automatic_parameter_change": False,
        },
        "cells": cells,
    }


def _pct(value: Optional[float]) -> str:
    return "???" if value is None else f"{value:+.2%}"


def _rate(value: Optional[float]) -> str:
    return "???" if value is None else f"{value:.0%}"


def render_dline_review(report: Mapping[str, Any]) -> str:
    lines = [
        f"# D????? {report.get('as_of_trade_date') or '???'}",
        "",
        "- ????????????????????????????",
        "- ?????????D??????????????",
        "- ?????????????????????????",
        "",
        "| ???? | ???? | ?? | ??/??? | ????? | ??????? | ??????? | D??? | ?? |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for cell in report.get("cells") or []:
        lines.append(
            f"| {cell.get('plan_version')} | {cell.get('trigger_type')} | "
            f"T+{cell.get('horizon')} | {cell.get('triggered')}/"
            f"{cell.get('qualified_not_triggered')} | "
            f"{_rate(cell.get('decision_hit_rate'))} | "
            f"{_pct(cell.get('avg_triggered_ret_from_target_close'))} | "
            f"{_pct(cell.get('avg_not_triggered_ret_from_target_close'))} | "
            f"{_pct(cell.get('incremental_separation'))} | "
            f"{cell.get('verdict')} |"
        )
    if not report.get("cells"):
        lines.append("| - | - | - | - | - | - | - | - | ??? |")
    lines += [
        "",
        "> ????????????????????D??????",
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
    old = {
        str(cell.get("cell_key")): str(cell.get("verdict"))
        for cell in previous.get("cells") or []
    }
    changes = []
    for cell in current.get("cells") or []:
        key = str(cell.get("cell_key") or "")
        before = old.get(key)
        after = str(cell.get("verdict") or "")
        material = after.endswith("_support") or after.endswith("_conflict")
        if before is None and not material:
            continue
        if before != after:
            changes.append({
                "cell_key": key,
                "before": before or "new_evidence",
                "after": after,
                "suggestion": cell.get("suggestion"),
            })
    return changes


def run_dline_review(*, write: bool = True, results_path=None,
                     output_dir=None, state_path=None,
                     as_of_trade_date: Optional[str] = None) -> Dict[str, Any]:
    report = build_dline_review(
        _read_jsonl(results_path or RESULTS_FILE),
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
