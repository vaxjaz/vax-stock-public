# -*- coding: utf-8 -*-
"""Per-stock live prediction history summaries for user-facing evidence."""

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from vaxstock import config

PREDICTIONS_FILE = config.STATE_DIR / "prediction" / "eod_predictions.jsonl"
RESULTS_FILE = config.STATE_DIR / "prediction" / "eod_prediction_results.jsonl"


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
                           horizon: str = "1") -> Dict[str, Dict[str, Any]]:
    """Summarize only evaluated live predictions; replay/pending never enter metrics."""
    result_by_id = {
        str(row.get("prediction_id")): row
        for row in results or []
        if row.get("prediction_id")
        and str(row.get("generation_mode") or "") == "live"
        and str(row.get("horizon") or "") == str(horizon)
    }
    grouped: Dict[str, List[Dict[str, float]]] = {}
    cutoff = str(cutoff_trade_date or "")
    for prediction in predictions or []:
        if str(prediction.get("generation_mode") or "") != "live":
            continue
        baseline = str(prediction.get("baseline_trade_date") or "")
        if cutoff and (not baseline or baseline > cutoff):
            continue
        code = str(prediction.get("code") or "")
        result = result_by_id.get(str(prediction.get("prediction_id") or ""))
        actual = (result or {}).get("actual") or {}
        ret = _finite(actual.get("ret"))
        excess = _finite(actual.get("excess"))
        if not code or ret is None or excess is None:
            continue
        grouped.setdefault(code, []).append({"ret": ret, "excess": excess})

    out: Dict[str, Dict[str, Any]] = {}
    for code, rows in grouped.items():
        count = len(rows)
        positive = sum(1 for row in rows if row["excess"] > 0)
        out[code] = {
            "available": True,
            "source": "eod_predictions+eod_prediction_results",
            "generation_mode": "live",
            "horizon": str(horizon),
            "cutoff_trade_date": cutoff or None,
            "evaluated": count,
            "avg_ret": sum(row["ret"] for row in rows) / count,
            "avg_excess": sum(row["excess"] for row in rows) / count,
            "positive_excess_count": positive,
            "positive_excess_rate": positive / count,
        }
    return out


def load_live_history(*, cutoff_trade_date: Optional[str] = None,
                      predictions_path=None, results_path=None) -> Dict[str, Dict[str, Any]]:
    return summarize_live_history(
        _read_jsonl(predictions_path or PREDICTIONS_FILE),
        _read_jsonl(results_path or RESULTS_FILE),
        cutoff_trade_date=cutoff_trade_date,
    )