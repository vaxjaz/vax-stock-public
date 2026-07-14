# -*- coding: utf-8 -*-
"""Append-only A/B/C/D strategy evidence ledger.

The immutable root records the decision-time identity and source references. Mature
T+N outcomes and D-line observations are joined when a view is built, so later
backfills never rewrite historical evidence roots. LLM reviews are a separate,
append-only interpretation layer and cannot modify facts or production rules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from vaxstock import config
from vaxstock.services.prediction_evaluator import (
    absolute_action_expectation, absolute_action_hit,
)


EVIDENCE_DIR = config.STATE_DIR / "evidence"
EVIDENCE_OBJECTS_FILE = EVIDENCE_DIR / "evidence_objects.jsonl"
EVIDENCE_REVIEWS_FILE = EVIDENCE_DIR / "evidence_reviews.jsonl"
PREDICTIONS_FILE = config.STATE_DIR / "prediction" / "eod_predictions.jsonl"
PREDICTION_RESULTS_FILE = config.STATE_DIR / "prediction" / "eod_prediction_results.jsonl"
FACTOR_SNAPSHOTS_FILE = config.STATE_DIR / "eval" / "factor_snapshots.jsonl"
FACTOR_RESULTS_FILE = config.STATE_DIR / "eval" / "factor_results.jsonl"
OBSERVATION_TASKS_FILE = config.STATE_DIR / "forecast" / "observation_tasks.jsonl"
FORECASTS_FILE = config.STATE_DIR / "forecast" / "forecasts.jsonl"
OBSERVATION_COVERAGE_FILE = config.STATE_DIR / "forecast" / "observation_coverage.jsonl"
FORECAST_EVOLUTION_FILE = config.STATE_DIR / "forecast" / "forecast_evolution.jsonl"
FORECAST_RESULTS_FILE = config.STATE_DIR / "forecast" / "forecast_results.jsonl"

EVIDENCE_POLICY_VERSION = "strategy_evidence_v1"
DLINE_PLAN_VERSION = "d_observe_llm_v2"
KEY_HORIZONS = ("1", "5", "10", "30")


def _trade_date(value: Any, *, field: str) -> str:
    text = re.sub(r"[^0-9]", "", str(value or ""))
    if len(text) != 8:
        raise ValueError(f"{field} must be YYYYMMDD: {value!r}")
    return text


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def _read_jsonl(path: Path, *, required: bool = False) -> List[Dict[str, Any]]:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return []
    rows: List[Dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:
            raise ValueError(f"invalid JSONL: {path}:{lineno}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row must be object: {path}:{lineno}")
        rows.append(row)
    return rows


def _source_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(config.PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _report_path(reports_dir: Path, trade_date: str) -> Path:
    return reports_dir / f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}" / "payload.json"


def _stock_index(payload: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = payload.get("stocks") or payload.get("stock_items") or []
    return {
        str(row.get("code") or "").strip(): row
        for row in rows
        if isinstance(row, dict) and str(row.get("code") or "").strip()
    }


def _prices_match(values: Iterable[float], *, tolerance: float = 1e-8) -> bool:
    items = list(values)
    return bool(items) and max(items) - min(items) <= tolerance * max(1.0, max(map(abs, items)))


class _FileLock:
    def __init__(self, path: Path, *, stale_seconds: int = 21600):
        self.path = path
        self.stale_seconds = stale_seconds
        self.acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"pid={os.getpid()} time={time.time()}".encode("ascii"))
                os.close(fd)
                self.acquired = True
                return self
            except FileExistsError:
                try:
                    stale = time.time() - self.path.stat().st_mtime > self.stale_seconds
                except FileNotFoundError:
                    continue
                if stale:
                    self.path.unlink(missing_ok=True)
                    continue
                raise RuntimeError(f"evidence ledger is already running: {self.path}")
        raise RuntimeError(f"cannot acquire evidence ledger lock: {self.path}")

    def __exit__(self, exc_type, exc, tb):
        if self.acquired:
            self.path.unlink(missing_ok=True)


def _snapshot_index(rows: Iterable[Mapping[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("trade_date") or ""), str(row.get("code") or ""))
        if all(key):
            out[key] = dict(row)
    return out


def build_evidence_objects(
    predictions: Iterable[Mapping[str, Any]],
    snapshots: Iterable[Mapping[str, Any]],
    *,
    as_of_trade_date: str,
    reports_dir: Path = config.REPORTS_DIR,
    snapshots_source_path: Path = FACTOR_SNAPSHOTS_FILE,
    predictions_source_path: Path = PREDICTIONS_FILE,
    prediction_results_source_path: Path = PREDICTION_RESULTS_FILE,
    observation_tasks_source_path: Path = OBSERVATION_TASKS_FILE,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Build immutable roots only when A/B/C identities agree.

    A report, B snapshot and C frozen prediction are all required. Missing or
    conflicting data is counted and omitted instead of receiving a default value.
    """
    as_of = _trade_date(as_of_trade_date, field="as_of_trade_date")
    snapshot_by_key = _snapshot_index(snapshots)
    report_cache: Dict[str, Tuple[Path, Dict[str, Dict[str, Any]]]] = {}
    roots: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {
        "as_of_trade_date": as_of,
        "candidates": 0,
        "ready": 0,
        "future_skipped": 0,
        "missing_a": 0,
        "missing_b": 0,
        "missing_identity": 0,
        "exact_a_identity": 0,
        "a_realtime_drift": 0,
        "a_realtime_missing": 0,
        "identity_conflict": 0,
        "issues": [],
    }

    for source_prediction in predictions:
        prediction = dict(source_prediction)
        pid = str(prediction.get("prediction_id") or "").strip()
        baseline = str(prediction.get("baseline_trade_date") or "").strip()
        target = str(prediction.get("target_trade_date") or "").strip()
        code = str(prediction.get("code") or "").strip()
        if target and target > as_of:
            stats["future_skipped"] += 1
            continue
        stats["candidates"] += 1
        if not pid or not code or not re.fullmatch(r"\d{8}", baseline) or not re.fullmatch(r"\d{8}", target):
            stats["missing_identity"] += 1
            stats["issues"].append({"prediction_id": pid or None, "code": "missing_c_identity"})
            continue

        snapshot = snapshot_by_key.get((baseline, code))
        if snapshot is None:
            stats["missing_b"] += 1
            stats["issues"].append({"prediction_id": pid, "code": "missing_b_snapshot"})
            continue

        if baseline not in report_cache:
            path = _report_path(Path(reports_dir), baseline)
            if not path.exists():
                report_cache[baseline] = (path, {})
            else:
                payload = _read_json(path)
                payload_date = _trade_date(
                    ((payload.get("market_overview") or {}).get("trade_date")),
                    field=f"{path}.market_overview.trade_date",
                )
                if payload_date != baseline:
                    raise ValueError(f"A report trade date conflict: {path}: {payload_date} != {baseline}")
                report_cache[baseline] = (path, _stock_index(payload))
        report_path, stocks = report_cache[baseline]
        stock = stocks.get(code)
        if stock is None:
            stats["missing_a"] += 1
            stats["issues"].append({"prediction_id": pid, "code": "missing_a_stock"})
            continue

        a_price = _finite((stock.get("realtime") or {}).get("price"))
        b_price = _finite(snapshot.get("price_at_snapshot"))
        c_price = _finite((prediction.get("features_ref") or {}).get("price_at_baseline"))
        a_stock_date = re.sub(
            r"[^0-9]", "", str((stock.get("realtime") or {}).get("trade_date") or "")
        )
        if None in (b_price, c_price):
            stats["missing_identity"] += 1
            stats["issues"].append({"prediction_id": pid, "code": "missing_frozen_b_c_price"})
            continue
        assert b_price is not None and c_price is not None
        if not _prices_match((b_price, c_price)):
            stats["identity_conflict"] += 1
            stats["issues"].append({
                "prediction_id": pid,
                "code": "frozen_b_c_price_conflict",
                "b_price": b_price,
                "c_price": c_price,
            })
            continue

        if a_stock_date == baseline and a_price is not None:
            if not _prices_match((a_price, b_price, c_price)):
                stats["identity_conflict"] += 1
                stats["issues"].append({
                    "prediction_id": pid,
                    "code": "aligned_a_b_c_price_conflict",
                    "a_price": a_price,
                    "b_price": b_price,
                    "c_price": c_price,
                })
                continue
            a_realtime_status = "aligned"
            stats["exact_a_identity"] += 1
        elif a_stock_date and a_stock_date != baseline:
            a_realtime_status = "drifted_late_or_overwritten"
            stats["a_realtime_drift"] += 1
            stats["issues"].append({
                "prediction_id": pid,
                "code": "a_realtime_drift_not_used_for_decision",
                "expected": baseline,
                "actual": a_stock_date,
            })
        else:
            a_realtime_status = "missing_not_used_for_decision"
            stats["a_realtime_missing"] += 1
            stats["issues"].append({
                "prediction_id": pid,
                "code": "a_realtime_missing_not_used_for_decision",
            })

        frozen = prediction.get("prediction") or {}
        identity = {
            "prediction_id": pid,
            "baseline_trade_date": baseline,
            "target_trade_date": target,
            "code": code,
            "generation_mode": str(prediction.get("generation_mode") or ""),
            "rule_version": str(prediction.get("rule_version") or ""),
        }
        root = {
            "schema_version": 1,
            "evidence_id": f"ev_{_digest({'policy': EVIDENCE_POLICY_VERSION, **identity})[:24]}",
            "evidence_policy_version": EVIDENCE_POLICY_VERSION,
            "evidence_role": (
                "decision_evidence" if identity["generation_mode"] == "live"
                else "historical_reconstruction"
            ),
            "identity": identity,
            "stock": {
                "code": code,
                "name": str(prediction.get("name") or stock.get("configured_name") or ""),
                "group": str(prediction.get("group") or snapshot.get("group") or ""),
            },
            "frozen_c_prediction": {
                "action": str(frozen.get("action") or ""),
                "direction": str(frozen.get("direction") or ""),
                "confidence": _finite(frozen.get("confidence")),
                "horizon": str(frozen.get("horizon") or ""),
                "expected_excess_bucket": str(frozen.get("expected_excess_bucket") or ""),
                "reason_codes": list(frozen.get("reason_codes") or []),
                "reason": str(frozen.get("reason") or ""),
                "model_version": str(prediction.get("model_version") or ""),
                "rule_version": str(prediction.get("rule_version") or ""),
                "features_ref": dict(prediction.get("features_ref") or {}),
            },
            "evidence_quality": (
                "exact_a_b_c_identity" if a_realtime_status == "aligned"
                else "frozen_b_c_verified_with_a_realtime_drift"
                if a_realtime_status == "drifted_late_or_overwritten"
                else "frozen_b_c_verified_with_a_realtime_missing"
            ),
            "identity_checks": {
                "a_report_trade_date": baseline,
                "a_stock_trade_date": a_stock_date or None,
                "a_realtime_price": a_price,
                "a_realtime_status": a_realtime_status,
                "a_realtime_used_for_decision": False,
                "b_snapshot_price": b_price,
                "c_frozen_price": c_price,
                "b_c_prices_match": True,
                "a_b_c_prices_match": (
                    True if a_realtime_status == "aligned" else None
                ),
                "decision_price_source": "B_factor_snapshot.price_at_snapshot",
            },
            "source_refs": {
                "a_payload": {
                    "path": _source_ref(report_path),
                    "key": {"trade_date": baseline, "code": code},
                },
                "b_snapshot": {
                    "path": _source_ref(Path(snapshots_source_path)),
                    "key": {"trade_date": baseline, "code": code},
                },
                "c_prediction": {
                    "path": _source_ref(Path(predictions_source_path)),
                    "key": {"prediction_id": pid},
                },
                "c_results": {
                    "path": _source_ref(Path(prediction_results_source_path)),
                    "key_prefix": {"prediction_id": pid},
                },
                "d_observation": {
                    "task_path": _source_ref(Path(observation_tasks_source_path)),
                    "join_key": {
                        "target_trade_date": target,
                        "code": code,
                        "plan_version": DLINE_PLAN_VERSION,
                    },
                },
            },
            "outcome_contract": {
                "primary_metric": "actual_stock_return",
                "audit_metric": "market_excess_return",
                "key_horizons": list(KEY_HORIZONS),
                "latest_horizon": "dynamic_T_plus_now",
                "source": "eod_prediction_results.jsonl joined by prediction_id+horizon",
            },
            "review_contract": {
                "facts_are_immutable": True,
                "llm_review_is_separate": True,
                "automatic_rule_change": False,
            },
        }
        root["decision_facts_digest"] = _digest({
            "identity": root["identity"],
            "frozen_c_prediction": root["frozen_c_prediction"],
            "b_snapshot_price": b_price,
            "c_frozen_price": c_price,
        })
        root["source_audit_digest"] = _digest({
            "a_report": root["source_refs"]["a_payload"],
            "a_realtime_status": a_realtime_status,
            "a_stock_trade_date": a_stock_date or None,
            "a_realtime_price": a_price,
        })
        root["facts_digest"] = _digest({
            "decision_facts_digest": root["decision_facts_digest"],
            "source_audit_digest": root["source_audit_digest"],
        })
        roots.append(root)
        stats["ready"] += 1
    return roots, stats


def record_evidence_objects(rows: Iterable[Mapping[str, Any]], *, path: Path = EVIDENCE_OBJECTS_FILE) -> Dict[str, int]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _FileLock(path.with_suffix(path.suffix + ".lock")):
        existing = {
            str(row.get("evidence_id") or ""): row for row in _read_jsonl(path)
            if str(row.get("evidence_id") or "")
        }
        pending = []
        seen = set(existing)
        known = dict(existing)
        skipped = 0
        for source in rows:
            row = dict(source)
            evidence_id = str(row.get("evidence_id") or "").strip()
            if not evidence_id:
                raise ValueError("evidence_id missing")
            if evidence_id in seen:
                previous = known.get(evidence_id)
                if previous is not None:
                    old_digest = previous.get("decision_facts_digest") or previous.get("facts_digest")
                    new_digest = row.get("decision_facts_digest") or row.get("facts_digest")
                    if old_digest != new_digest:
                        raise ValueError(f"immutable evidence conflict: {evidence_id}")
                skipped += 1
                continue
            pending.append(row)
            seen.add(evidence_id)
            known[evidence_id] = row
        if pending:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                for row in pending:
                    handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
    return {"written": len(pending), "skipped": skipped}


def _result_index(rows: Iterable[Mapping[str, Any]], *, as_of: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for source in rows:
        row = dict(source)
        pid = str(row.get("prediction_id") or "")
        horizon = str(row.get("horizon") or "")
        actual_date = re.sub(r"[^0-9]", "", str((row.get("actual") or {}).get("trade_date") or ""))
        if not pid or not horizon.isdigit() or int(horizon) < 1:
            continue
        if actual_date and actual_date > as_of:
            continue
        out[(pid, horizon)] = row
    return out


def _factor_result_dates(rows: Iterable[Mapping[str, Any]]) -> Dict[Tuple[str, str, str], str]:
    out: Dict[Tuple[str, str, str], str] = {}
    for row in rows:
        baseline = str(row.get("trade_date") or "")
        code = str(row.get("code") or "")
        for horizon, date in (row.get("horizon_trade_dates") or {}).items():
            text = re.sub(r"[^0-9]", "", str(date or ""))
            if baseline and code and str(horizon).isdigit() and len(text) == 8:
                out[(baseline, code, str(horizon))] = text
    return out


def _outcome_view(root: Mapping[str, Any], results: Mapping[Tuple[str, str], Mapping[str, Any]],
                  result_dates: Mapping[Tuple[str, str, str], str], *, as_of: str) -> Dict[str, Any]:
    identity = root.get("identity") or {}
    pid = str(identity.get("prediction_id") or "")
    baseline = str(identity.get("baseline_trade_date") or "")
    code = str(identity.get("code") or "")
    expectation = absolute_action_expectation(dict(root.get("frozen_c_prediction") or {}))
    cells: Dict[str, Dict[str, Any]] = {}
    for (result_pid, horizon), row in results.items():
        if result_pid != pid:
            continue
        actual = row.get("actual") or {}
        trade_date = re.sub(r"[^0-9]", "", str(actual.get("trade_date") or ""))
        if not trade_date:
            trade_date = result_dates.get((baseline, code, horizon), "")
        if not trade_date or trade_date > as_of:
            continue
        ret = _finite(actual.get("ret"))
        if ret is None:
            continue
        evaluation = row.get("evaluation") or {}
        action_hit = evaluation.get("absolute_action_hit")
        if action_hit is None:
            action_hit = absolute_action_hit(expectation, ret)
        cells[horizon] = {
            "status": "mature",
            "horizon": horizon,
            "actual_trade_date": trade_date or None,
            "ret": ret,
            "positive": ret > 0,
            "absolute_action_expectation": (
                evaluation.get("absolute_action_expectation") or expectation
            ),
            "absolute_action_hit": action_hit,
            "audit_excess": _finite(actual.get("excess")),
        }
    fixed = {
        horizon: cells.get(horizon) or {"status": "pending", "horizon": horizon}
        for horizon in KEY_HORIZONS
    }
    max_horizon = max((int(horizon) for horizon in cells), default=None)
    latest = cells.get(str(max_horizon)) if max_horizon is not None else {
        "status": "pending",
        "horizon": None,
        "as_of_trade_date": as_of,
        "reason": "no_mature_c_result",
    }
    return {
        "primary_metric": "actual_stock_return",
        "fixed_horizons": fixed,
        "t_plus_now": latest,
        "available_horizons": sorted(cells, key=int),
    }


def _latest_by(rows: Iterable[Mapping[str, Any]], key_name: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = str(row.get(key_name) or "").strip()
        if key:
            out[key] = dict(row)
    return out


def _d_task_id(row: Mapping[str, Any]) -> str:
    return str(
        row.get("task_id")
        or (row.get("structured") or {}).get("task_id")
        or (row.get("inputs_ref") or {}).get("dline_task_id")
        or ""
    ).strip()


def _d_trigger_type(row: Mapping[str, Any]) -> str:
    return str(
        row.get("trigger_type")
        or (row.get("structured") or {}).get("trigger_type")
        or ((row.get("inputs_ref") or {}).get("trigger_blueprint") or {}).get("trigger_type")
        or ""
    ).strip()


def _dline_view(root: Mapping[str, Any], *, tasks: List[Dict[str, Any]], forecasts: List[Dict[str, Any]],
                coverage: List[Dict[str, Any]], evolution: List[Dict[str, Any]],
                forecast_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    identity = root.get("identity") or {}
    target = str(identity.get("target_trade_date") or "")
    code = str(identity.get("code") or "")
    target_tasks = [
        row for row in tasks
        if str(row.get("target_trade_date") or "") == target
        and str(row.get("plan_version") or "") == DLINE_PLAN_VERSION
    ]
    matching = [row for row in target_tasks if str(row.get("code") or "") == code]
    if not matching:
        return {
            "status": "not_selected" if target_tasks else "d_data_missing",
            "task_count_for_target": len(target_tasks),
            "user_execution_used": False,
        }

    task = matching[-1]
    task_id = str(task.get("task_id") or "")
    trigger_by_type: Dict[str, Dict[str, Any]] = {}
    for row in forecasts:
        trigger_type = _d_trigger_type(row)
        if _d_task_id(row) == task_id and trigger_type:
            trigger_by_type.setdefault(trigger_type, row)
    trigger_types = set(trigger_by_type)
    coverage_row = _latest_by(coverage, "task_id").get(task_id)
    evolution_by_type: Dict[str, Dict[str, Any]] = {}
    for row in evolution:
        trigger_type = _d_trigger_type(row)
        if _d_task_id(row) == task_id and trigger_type:
            evolution_by_type[trigger_type] = row
    result_rows = [row for row in forecast_results if _d_task_id(row) == task_id]
    qualified = bool(((coverage_row or {}).get("quality") or {}).get("qualified"))
    complete_types = {
        trigger_type for trigger_type, row in evolution_by_type.items()
        if bool(((row.get("quality") or {}).get("complete")))
    }
    if trigger_types:
        status = "triggered_complete" if trigger_types.issubset(complete_types) else "partial_data"
    else:
        status = "no_trigger_observed" if qualified else "partial_data"
    return {
        "status": status,
        "task_id": task_id,
        "trigger_count": len(trigger_types),
        "trigger_types": sorted(trigger_types),
        "coverage_present": coverage_row is not None,
        "coverage_qualified": qualified,
        "evolution_count": len(evolution_by_type),
        "complete_evolution_count": len(complete_types),
        "result_count": len(result_rows),
        "user_execution_used": False,
    }


def hydrate_evidence_objects(
    roots: Iterable[Mapping[str, Any]],
    *,
    as_of_trade_date: str,
    prediction_results: Iterable[Mapping[str, Any]],
    factor_results: Iterable[Mapping[str, Any]] = (),
    observation_tasks: Iterable[Mapping[str, Any]] = (),
    forecasts: Iterable[Mapping[str, Any]] = (),
    observation_coverage: Iterable[Mapping[str, Any]] = (),
    forecast_evolution: Iterable[Mapping[str, Any]] = (),
    forecast_results: Iterable[Mapping[str, Any]] = (),
) -> List[Dict[str, Any]]:
    as_of = _trade_date(as_of_trade_date, field="as_of_trade_date")
    result_index = _result_index(prediction_results, as_of=as_of)
    date_index = _factor_result_dates(factor_results)
    d_inputs = {
        "tasks": [dict(row) for row in observation_tasks],
        "forecasts": [dict(row) for row in forecasts],
        "coverage": [dict(row) for row in observation_coverage],
        "evolution": [dict(row) for row in forecast_evolution],
        "forecast_results": [dict(row) for row in forecast_results],
    }
    hydrated = []
    for source in roots:
        root = dict(source)
        target = str((root.get("identity") or {}).get("target_trade_date") or "")
        if target and target > as_of:
            continue
        root["as_of_trade_date"] = as_of
        root["c_outcomes"] = _outcome_view(root, result_index, date_index, as_of=as_of)
        root["d_evidence"] = _dline_view(root, **d_inputs)
        root["hydrated_facts_digest"] = _digest({
            "root_facts_digest": root.get("facts_digest"),
            "as_of_trade_date": as_of,
            "c_outcomes": root["c_outcomes"],
            "d_evidence": root["d_evidence"],
        })
        hydrated.append(root)
    return hydrated


def load_hydrated_evidence(
    *,
    as_of_trade_date: str,
    evidence_objects_path: Path = EVIDENCE_OBJECTS_FILE,
    prediction_results_path: Path = PREDICTION_RESULTS_FILE,
    factor_results_path: Path = FACTOR_RESULTS_FILE,
    observation_tasks_path: Path = OBSERVATION_TASKS_FILE,
    forecasts_path: Path = FORECASTS_FILE,
    observation_coverage_path: Path = OBSERVATION_COVERAGE_FILE,
    forecast_evolution_path: Path = FORECAST_EVOLUTION_FILE,
    forecast_results_path: Path = FORECAST_RESULTS_FILE,
) -> List[Dict[str, Any]]:
    """Materialize one auditable as-of view from immutable roots and append-only results."""
    return hydrate_evidence_objects(
        _read_jsonl(Path(evidence_objects_path), required=True),
        as_of_trade_date=as_of_trade_date,
        prediction_results=_read_jsonl(Path(prediction_results_path)),
        factor_results=_read_jsonl(Path(factor_results_path)),
        observation_tasks=_read_jsonl(Path(observation_tasks_path)),
        forecasts=_read_jsonl(Path(forecasts_path)),
        observation_coverage=_read_jsonl(Path(observation_coverage_path)),
        forecast_evolution=_read_jsonl(Path(forecast_evolution_path)),
        forecast_results=_read_jsonl(Path(forecast_results_path)),
    )


def build_evidence_review(
    hydrated: Mapping[str, Any],
    *,
    review_version: str,
    reviewer: str,
    analysis: str,
    hypotheses: Iterable[str] = (),
    data_limitations: Iterable[str] = (),
    verdict: str = "open",
    confidence: Optional[float] = None,
) -> Dict[str, Any]:
    """Build an interpretation record bound to one exact hydrated fact view."""
    evidence_id = str(hydrated.get("evidence_id") or "").strip()
    as_of = _trade_date(hydrated.get("as_of_trade_date"), field="as_of_trade_date")
    facts_digest = str(hydrated.get("hydrated_facts_digest") or "").strip()
    if not evidence_id or not facts_digest or not review_version or not reviewer or not analysis.strip():
        raise ValueError("review requires evidence_id, facts_digest, version, reviewer and analysis")
    identity = {
        "evidence_id": evidence_id,
        "as_of_trade_date": as_of,
        "facts_digest": facts_digest,
        "review_version": review_version,
        "reviewer": reviewer,
    }
    review = {
        "schema_version": 1,
        "review_id": f"review_{_digest(identity)[:24]}",
        **identity,
        "role": "interpretation_not_fact",
        "analysis": analysis.strip(),
        "hypotheses": [str(value) for value in hypotheses],
        "data_limitations": [str(value) for value in data_limitations],
        "verdict": str(verdict),
        "confidence": _finite(confidence),
        "automatic_rule_change": False,
    }
    review["review_digest"] = _digest({
        key: value for key, value in review.items() if key != "review_digest"
    })
    return review


def record_evidence_reviews(rows: Iterable[Mapping[str, Any]], *, path: Path = EVIDENCE_REVIEWS_FILE) -> Dict[str, int]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _FileLock(path.with_suffix(path.suffix + ".lock")):
        existing = {
            str(row.get("review_id") or ""): row for row in _read_jsonl(path)
            if str(row.get("review_id") or "")
        }
        pending = []
        seen = set(existing)
        known = dict(existing)
        skipped = 0
        for source in rows:
            row = dict(source)
            review_id = str(row.get("review_id") or "").strip()
            if not review_id:
                raise ValueError("review_id missing")
            if row.get("automatic_rule_change") is not False:
                raise ValueError("evidence review cannot change production rules automatically")
            if review_id in seen:
                previous = known.get(review_id)
                old_digest = (previous or {}).get("review_digest")
                new_digest = row.get("review_digest")
                if old_digest != new_digest:
                    raise ValueError(f"immutable evidence review conflict: {review_id}")
                skipped += 1
                continue
            pending.append(row)
            seen.add(review_id)
            known[review_id] = row
        if pending:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                for row in pending:
                    handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
    return {"written": len(pending), "skipped": skipped}


def _fmt_ret(value: Any) -> str:
    number = _finite(value)
    return "待回填" if number is None else f"{number * 100:+.2f}%"


def _fmt_action_review(latest: Mapping[str, Any]) -> str:
    if latest.get("status") != "mature":
        return "待回填"
    expectation = str(latest.get("absolute_action_expectation") or "unscored")
    hit = latest.get("absolute_action_hit")
    if expectation == "unscored" or hit is None:
        return "当前动作没有明确正负收益预期，不评分"
    return "命中" if hit is True else "未命中"


def render_evidence_summary(rows: Iterable[Mapping[str, Any]], *, as_of_trade_date: str) -> str:
    as_of = _trade_date(as_of_trade_date, field="as_of_trade_date")
    all_rows = [dict(row) for row in rows]
    live = [row for row in all_rows if row.get("evidence_role") == "decision_evidence"]
    target = max((str((row.get("identity") or {}).get("target_trade_date") or "") for row in live), default="")
    current = [row for row in live if str((row.get("identity") or {}).get("target_trade_date") or "") == target]
    lines = [
        f"# {as_of} 策略证据账本",
        "",
        "- 口径: 收益只看股票自身实际收益；指数超额仅保留在机器审计字段。",
        "- T+now: 截至本次交易日已成熟的最远 C 线结果；不足或超过 T+30 都如实展示。",
        "- D线: 只记录任务、触发、全天覆盖、演变和市场结果，不读取用户实际成交。",
        f"- 账本: 有效根对象 {len(all_rows)} 条，其中 live {len(live)} 条；本页展示目标日 {target or '待验证'}。",
        "",
    ]
    if not current:
        lines.append("- 当前没有可展示的 live 证据对象。")
        return "\n".join(lines) + "\n"
    for index, row in enumerate(sorted(current, key=lambda x: str((x.get("stock") or {}).get("code") or "")), 1):
        stock = row.get("stock") or {}
        prediction = row.get("frozen_c_prediction") or {}
        outcomes = row.get("c_outcomes") or {}
        latest = outcomes.get("t_plus_now") or {}
        dline = row.get("d_evidence") or {}
        latest_text = (
            f"T+{latest.get('horizon')} {_fmt_ret(latest.get('ret'))}"
            if latest.get("status") == "mature" else "待回填"
        )
        fixed = outcomes.get("fixed_horizons") or {}
        fixed_text = "；".join(
            f"T+{h} {_fmt_ret((fixed.get(h) or {}).get('ret'))}"
            for h in KEY_HORIZONS
        )
        lines.extend([
            f"## {index}. {stock.get('name') or stock.get('code')} ({stock.get('code')})",
            "",
            f"- C线原始动作: {prediction.get('action') or '待验证'} / {prediction.get('direction') or '待验证'} / 置信度 {prediction.get('confidence') if prediction.get('confidence') is not None else '待验证'}",
            f"- 实际结果: T+now {latest_text}；{fixed_text}",
            f"- 原始动作复核: {_fmt_action_review(latest)}",
            f"- D线证据: {dline.get('status') or '待验证'}；触发 {dline.get('trigger_count', 0)} 次；完整演变 {dline.get('complete_evolution_count', 0)} 条",
            f"- 事实哈希: `{row.get('hydrated_facts_digest')}`",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temp, path)


def run_evidence_ledger(
    *,
    as_of_trade_date: str,
    reports_dir: Path = config.REPORTS_DIR,
    predictions_path: Path = PREDICTIONS_FILE,
    snapshots_path: Path = FACTOR_SNAPSHOTS_FILE,
    prediction_results_path: Path = PREDICTION_RESULTS_FILE,
    factor_results_path: Path = FACTOR_RESULTS_FILE,
    observation_tasks_path: Path = OBSERVATION_TASKS_FILE,
    forecasts_path: Path = FORECASTS_FILE,
    observation_coverage_path: Path = OBSERVATION_COVERAGE_FILE,
    forecast_evolution_path: Path = FORECAST_EVOLUTION_FILE,
    forecast_results_path: Path = FORECAST_RESULTS_FILE,
    evidence_objects_path: Path = EVIDENCE_OBJECTS_FILE,
    summary_dir: Path = EVIDENCE_DIR,
) -> Dict[str, Any]:
    """Record immutable roots and rebuild the as-of human-readable evidence view."""
    as_of = _trade_date(as_of_trade_date, field="as_of_trade_date")
    predictions = _read_jsonl(Path(predictions_path), required=True)
    snapshots = _read_jsonl(Path(snapshots_path), required=True)
    roots, build_stats = build_evidence_objects(
        predictions, snapshots, as_of_trade_date=as_of, reports_dir=Path(reports_dir),
        snapshots_source_path=Path(snapshots_path),
        predictions_source_path=Path(predictions_path),
        prediction_results_source_path=Path(prediction_results_path),
        observation_tasks_source_path=Path(observation_tasks_path),
    )
    write_stats = record_evidence_objects(roots, path=Path(evidence_objects_path))
    hydrated = load_hydrated_evidence(
        as_of_trade_date=as_of,
        evidence_objects_path=Path(evidence_objects_path),
        prediction_results_path=Path(prediction_results_path),
        factor_results_path=Path(factor_results_path),
        observation_tasks_path=Path(observation_tasks_path),
        forecasts_path=Path(forecasts_path),
        observation_coverage_path=Path(observation_coverage_path),
        forecast_evolution_path=Path(forecast_evolution_path),
        forecast_results_path=Path(forecast_results_path),
    )
    markdown = render_evidence_summary(hydrated, as_of_trade_date=as_of)
    dated = Path(summary_dir) / f"evidence_summary_{as_of}.md"
    latest = Path(summary_dir) / "evidence_summary_latest.md"
    _atomic_write(dated, markdown)
    _atomic_write(latest, markdown)
    return {
        "status": "written",
        "as_of_trade_date": as_of,
        "build": build_stats,
        "ledger": write_stats,
        "hydrated": len(hydrated),
        "dated_path": str(dated),
        "latest_path": str(latest),
        "llm_reviews_generated": 0,
        "automatic_rule_change": False,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the append-only strategy evidence ledger")
    parser.add_argument("--as-of", required=True, help="Confirmed EOD trade date (YYYYMMDD)")
    args = parser.parse_args(argv)
    result = run_evidence_ledger(as_of_trade_date=args.as_of)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
