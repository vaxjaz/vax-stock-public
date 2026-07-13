# -*- coding: utf-8 -*-
"""Per-stock live prediction history summaries for user-facing evidence."""

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from vaxstock import config

PREDICTIONS_FILE = config.STATE_DIR / "prediction" / "eod_predictions.jsonl"
RESULTS_FILE = config.STATE_DIR / "prediction" / "eod_prediction_results.jsonl"
KEY_HORIZONS = ("1", "5", "10", "30")
MAX_HISTORY_HORIZON = 30


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


def summarize_live_history(predictions: Iterable[Dict[str, Any]],
                           results: Iterable[Dict[str, Any]], *,
                           cutoff_trade_date: Optional[str] = None,
                           horizon: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Reduce every mature live C-line path through T+30 from all prior predictions."""
    cutoff = str(cutoff_trade_date or "")
    prediction_ids: Dict[str, str] = {}
    prediction_ids_by_code: Dict[str, set] = {}
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
        prediction_ids[pid] = code
        prediction_ids_by_code.setdefault(code, set()).add(pid)

    selected_horizon = str(horizon) if horizon is not None else None
    result_by_key: Dict[tuple, Dict[str, Any]] = {}
    for row in results or []:
        if str(row.get("generation_mode") or "") != "live":
            continue
        pid = str(row.get("prediction_id") or "")
        code = prediction_ids.get(pid)
        path_horizon = str(row.get("horizon") or "")
        if not code or not path_horizon.isdigit():
            continue
        if not 1 <= int(path_horizon) <= MAX_HISTORY_HORIZON:
            continue
        if selected_horizon is not None and path_horizon != selected_horizon:
            continue
        result_by_key[(pid, path_horizon)] = row

    grouped: Dict[str, Dict[str, List[Dict[str, float]]]] = {}
    for (pid, path_horizon), result in result_by_key.items():
        code = prediction_ids[pid]
        actual = (result or {}).get("actual") or {}
        ret = _finite(actual.get("ret"))
        excess = _finite(actual.get("excess"))
        if ret is None or excess is None:
            continue
        grouped.setdefault(code, {}).setdefault(path_horizon, []).append({
            "ret": ret,
            "excess": excess,
        })

    out: Dict[str, Dict[str, Any]] = {}
    for code, rows_by_horizon in grouped.items():
        horizon_summaries: Dict[str, Dict[str, Any]] = {}
        for path_horizon in sorted(rows_by_horizon, key=int):
            rows = rows_by_horizon[path_horizon]
            count = len(rows)
            positive = sum(1 for row in rows if row["excess"] > 0)
            horizon_summaries[path_horizon] = {
                "horizon": path_horizon,
                "evaluated": count,
                "avg_ret": sum(row["ret"] for row in rows) / count,
                "avg_excess": sum(row["excess"] for row in rows) / count,
                "positive_excess_count": positive,
                "positive_excess_rate": positive / count,
            }
        primary_horizon = selected_horizon or "1"
        primary = horizon_summaries.get(primary_horizon)
        if primary is None:
            primary = horizon_summaries[min(horizon_summaries, key=int)]
        out[code] = {
            "available": True,
            "source": "eod_predictions+eod_prediction_results",
            "generation_mode": "live",
            "cutoff_trade_date": cutoff or None,
            "prediction_count": len(prediction_ids_by_code.get(code) or ()),
            "max_horizon": max((int(value) for value in horizon_summaries), default=None),
            "key_horizons": list(KEY_HORIZONS),
            "horizons": horizon_summaries,
            **primary,
        }
    return out


def load_live_history(*, cutoff_trade_date: Optional[str] = None,
                      predictions_path=None, results_path=None) -> Dict[str, Dict[str, Any]]:
    return summarize_live_history(
        _read_jsonl(predictions_path or PREDICTIONS_FILE),
        _read_jsonl(results_path or RESULTS_FILE),
        cutoff_trade_date=cutoff_trade_date,
    )