# -*- coding: utf-8 -*-
"""Per-stock live prediction history summaries for user-facing evidence."""

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from vaxstock import config
from vaxstock.services.prediction_evaluator import (
    absolute_action_expectation, absolute_action_hit,
)

PREDICTIONS_FILE = config.STATE_DIR / "prediction" / "eod_predictions.jsonl"
RESULTS_FILE = config.STATE_DIR / "prediction" / "eod_prediction_results.jsonl"
FACTOR_RESULTS_FILE = config.STATE_DIR / "eval" / "factor_results.jsonl"
KEY_HORIZONS = ("1", "5", "10", "30")
COHORT_FIELDS = ("rule_version", "action", "direction")


def _read_jsonl(path) -> List[dict]:
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _prediction_horizon(prediction: Mapping[str, Any]) -> str:
    raw = str(((prediction.get("prediction") or {}).get("horizon") or ""))
    match = re.search(r"(\d+)", raw)
    return match.group(1) if match else "1"


def cohort_signature(prediction: Mapping[str, Any]) -> tuple:
    payload = prediction.get("prediction") or {}
    return (
        str(prediction.get("rule_version") or ""),
        str(payload.get("action") or ""),
        str(payload.get("direction") or ""),
    )


def cohort_descriptor(prediction: Mapping[str, Any]) -> Dict[str, str]:
    return dict(zip(COHORT_FIELDS, cohort_signature(prediction)))


def _result_trade_date(result: Mapping[str, Any], prediction: Mapping[str, Any],
                       path_horizon: str) -> Optional[str]:
    actual_date = str(((result.get("actual") or {}).get("trade_date") or ""))
    if len(actual_date) == 8 and actual_date.isdigit():
        return actual_date
    if path_horizon == _prediction_horizon(prediction):
        target = str(prediction.get("target_trade_date") or "")
        if len(target) == 8 and target.isdigit():
            return target
    return None


def summarize_live_history(predictions: Iterable[Dict[str, Any]],
                           results: Iterable[Dict[str, Any]], *,
                           cutoff_trade_date: Optional[str] = None,
                           horizon: Optional[str] = None,
                           current_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
                           require_result_trade_date: bool = False) -> Dict[str, Dict[str, Any]]:
    """Reduce every mature live C-line path without a horizon ceiling."""
    cutoff = str(cutoff_trade_date or "")
    prediction_by_id: Dict[str, Dict[str, Any]] = {}
    prediction_ids_by_code: Dict[str, set] = {}
    cohort_by_code: Dict[str, Dict[str, str]] = {}
    for prediction in predictions or []:
        if str(prediction.get("generation_mode") or "") != "live":
            continue
        baseline = str(prediction.get("baseline_trade_date") or "")
        if cutoff and (not baseline or baseline > cutoff):
            continue
        pid = str(prediction.get("prediction_id") or "")
        code = str(prediction.get("code") or "")
        if not pid or not code:
            continue
        if current_signals is not None:
            current = current_signals.get(code)
            if not current or cohort_signature(prediction) != cohort_signature(current):
                continue
            cohort_by_code[code] = cohort_descriptor(current)
        prediction_by_id[pid] = prediction
        prediction_ids_by_code.setdefault(code, set()).add(pid)

    selected_horizon = str(horizon) if horizon is not None else None
    result_by_key: Dict[tuple, Dict[str, Any]] = {}
    for row in results or []:
        if str(row.get("generation_mode") or "") != "live":
            continue
        pid = str(row.get("prediction_id") or "")
        prediction = prediction_by_id.get(pid)
        code = str((prediction or {}).get("code") or "")
        path_horizon = str(row.get("horizon") or "")
        if not code or not path_horizon.isdigit() or int(path_horizon) < 1:
            continue
        if selected_horizon is not None and path_horizon != selected_horizon:
            continue
        actual_trade_date = _result_trade_date(row, prediction, path_horizon)
        if cutoff and actual_trade_date and actual_trade_date > cutoff:
            continue
        if require_result_trade_date and not actual_trade_date:
            continue
        result_by_key[(pid, path_horizon)] = row

    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for (pid, path_horizon), result in result_by_key.items():
        prediction = prediction_by_id[pid]
        code = str(prediction.get("code") or "")
        actual = (result or {}).get("actual") or {}
        ret = _finite(actual.get("ret"))
        excess = _finite(actual.get("excess"))
        if ret is None:
            continue
        expectation = absolute_action_expectation(prediction.get("prediction") or {})
        grouped.setdefault(code, {}).setdefault(path_horizon, []).append({
            "ret": ret,
            "excess": excess,
            "absolute_action_expectation": expectation,
            "absolute_action_hit": absolute_action_hit(expectation, ret),
            "baseline_trade_date": str(prediction.get("baseline_trade_date") or ""),
        })

    out: Dict[str, Dict[str, Any]] = {}
    for code, rows_by_horizon in grouped.items():
        horizon_summaries: Dict[str, Dict[str, Any]] = {}
        for path_horizon in sorted(rows_by_horizon, key=int):
            rows = rows_by_horizon[path_horizon]
            count = len(rows)
            positive_ret = sum(1 for row in rows if row["ret"] > 0)
            excess_rows = [row for row in rows if row["excess"] is not None]
            scored_rows = [row for row in rows if row["absolute_action_hit"] is not None]
            expectations = {
                row["absolute_action_expectation"] for row in rows
                if row["absolute_action_expectation"] != "unscored"
            }
            expectation = next(iter(expectations)) if len(expectations) == 1 else (
                "mixed" if expectations else "unscored"
            )
            hit_count = sum(1 for row in scored_rows if row["absolute_action_hit"] is True)
            horizon_summaries[path_horizon] = {
                "horizon": path_horizon,
                "evaluated": count,
                "avg_ret": sum(row["ret"] for row in rows) / count,
                "avg_excess": (
                    sum(row["excess"] for row in excess_rows) / len(excess_rows)
                    if excess_rows else None
                ),
                "positive_ret_count": positive_ret,
                "positive_ret_rate": positive_ret / count,
                "positive_excess_count": (
                    sum(1 for row in excess_rows if row["excess"] > 0)
                    if excess_rows else None
                ),
                "positive_excess_rate": (
                    sum(1 for row in excess_rows if row["excess"] > 0) / len(excess_rows)
                    if excess_rows else None
                ),
                "absolute_action_expectation": expectation,
                "absolute_action_evaluated": len(scored_rows),
                "absolute_action_hit_count": hit_count,
                "absolute_action_hit_rate": (
                    hit_count / len(scored_rows) if scored_rows else None
                ),
                "sample_baseline_dates": sorted({
                    row["baseline_trade_date"] for row in rows
                    if row["baseline_trade_date"]
                }),
                "absolute_action_sample_dates": sorted({
                    row["baseline_trade_date"] for row in scored_rows
                    if row["baseline_trade_date"]
                }),
            }
        primary_horizon = selected_horizon or "1"
        primary = horizon_summaries.get(primary_horizon)
        if primary is None:
            primary = horizon_summaries[min(horizon_summaries, key=int)]
        max_horizon = max((int(value) for value in horizon_summaries), default=None)
        out[code] = {
            "available": True,
            "source": "eod_predictions+eod_prediction_results",
            "generation_mode": "live",
            "scope": "matching_current_action" if current_signals is not None else "all_stock_history",
            "cohort": cohort_by_code.get(code),
            "cutoff_trade_date": cutoff or None,
            "prediction_count": len(prediction_ids_by_code.get(code) or ()),
            "max_horizon": max_horizon,
            "latest_horizon": str(max_horizon) if max_horizon is not None else None,
            "key_horizons": list(KEY_HORIZONS),
            "horizons": horizon_summaries,
            **primary,
        }
    return out


def _enrich_result_trade_dates(predictions: Iterable[Dict[str, Any]],
                               results: Iterable[Dict[str, Any]],
                               factor_results: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    date_index: Dict[tuple, str] = {}
    for row in factor_results or []:
        baseline = str((row or {}).get("trade_date") or "")
        code = str((row or {}).get("code") or "")
        for horizon, trade_date in ((row or {}).get("horizon_trade_dates") or {}).items():
            text = str(trade_date or "")
            if baseline and code and str(horizon).isdigit() and len(text) == 8:
                date_index[(baseline, code, str(horizon))] = text

    prediction_by_id = {
        str(row.get("prediction_id")): row
        for row in predictions or [] if row.get("prediction_id")
    }
    enriched = []
    for row in results or []:
        actual = (row or {}).get("actual") or {}
        if actual.get("trade_date"):
            enriched.append(row)
            continue
        prediction = prediction_by_id.get(str((row or {}).get("prediction_id") or "")) or {}
        key = (
            str(prediction.get("baseline_trade_date") or ""),
            str(prediction.get("code") or ""),
            str((row or {}).get("horizon") or ""),
        )
        trade_date = date_index.get(key)
        if not trade_date:
            enriched.append(row)
            continue
        copied = dict(row)
        copied["actual"] = dict(actual)
        copied["actual"]["trade_date"] = trade_date
        enriched.append(copied)
    return enriched


def load_history_views(*, current_signals: Mapping[str, Mapping[str, Any]],
                       cutoff_trade_date: Optional[str] = None,
                       predictions_path=None, results_path=None,
                       factor_results_path=None) -> Dict[str, Dict[str, Dict[str, Any]]]:
    predictions = _read_jsonl(predictions_path or PREDICTIONS_FILE)
    results = _enrich_result_trade_dates(
        predictions,
        _read_jsonl(results_path or RESULTS_FILE),
        _read_jsonl(factor_results_path or FACTOR_RESULTS_FILE),
    )
    overall = summarize_live_history(
        predictions, results, cutoff_trade_date=cutoff_trade_date,
    )
    matching = summarize_live_history(
        predictions,
        results,
        cutoff_trade_date=cutoff_trade_date,
        current_signals=current_signals,
        require_result_trade_date=True,
    )
    for code, summary in matching.items():
        all_summary = overall.get(code) or {}
        summary["all_prediction_count"] = all_summary.get("prediction_count")
        for horizon, cell in (summary.get("horizons") or {}).items():
            all_cell = (all_summary.get("horizons") or {}).get(horizon) or {}
            cell["all_evaluated"] = int(all_cell.get("evaluated") or 0)
    return {"overall": overall, "matching": matching}


def load_live_history(*, cutoff_trade_date: Optional[str] = None,
                      predictions_path=None, results_path=None) -> Dict[str, Dict[str, Any]]:
    return summarize_live_history(
        _read_jsonl(predictions_path or PREDICTIONS_FILE),
        _read_jsonl(results_path or RESULTS_FILE),
        cutoff_trade_date=cutoff_trade_date,
    )