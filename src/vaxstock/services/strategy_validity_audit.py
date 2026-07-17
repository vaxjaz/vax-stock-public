# -*- coding: utf-8 -*-
"""Audit whether C/D evidence is truthful, independently counted and actionable."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from vaxstock import config
from vaxstock.services.dline_evaluator import trigger_expectation
from vaxstock.services.prediction_evaluator import (
    absolute_action_expectation,
    absolute_action_hit,
)


EVIDENCE_DIR = config.STATE_DIR / "evidence"
PREDICTIONS_FILE = config.STATE_DIR / "prediction" / "eod_predictions.jsonl"
PREDICTION_RESULTS_FILE = (
    config.STATE_DIR / "prediction" / "eod_prediction_results.jsonl"
)
FORECAST_RESULTS_FILE = config.STATE_DIR / "forecast" / "forecast_results.jsonl"
FORECAST_EVOLUTION_FILE = config.STATE_DIR / "forecast" / "forecast_evolution.jsonl"
FIXED_HORIZONS = ("1", "5", "10", "30")
VALID_MODES = {"live", "replay"}
AUDIT_SCHEMA_VERSION = 1
AUDIT_POLICY_VERSION = "strategy_validity_v1"


def _trade_date(value: Any, *, field: str) -> str:
    text = "".join(char for char in str(value or "") if char.isdigit())
    if len(text) != 8:
        raise ValueError(f"{field} must be YYYYMMDD: {value!r}")
    return text


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _mean(values: Iterable[Optional[float]]) -> Optional[float]:
    finite = [value for value in values if value is not None and math.isfinite(value)]
    return sum(finite) / len(finite) if finite else None


def _rate(numerator: int, denominator: int) -> Optional[float]:
    return numerator / denominator if denominator else None


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not path.exists():
        return [], [{"path": str(path), "line": None, "error": "file_missing"}]
    rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:
            errors.append({
                "path": str(path), "line": line_no,
                "error": f"invalid_json:{type(exc).__name__}",
            })
            continue
        if not isinstance(row, dict):
            errors.append({
                "path": str(path), "line": line_no, "error": "row_not_object",
            })
            continue
        rows.append(row)
    return rows, errors


def _dedupe(rows: Iterable[Mapping[str, Any]], key_fields: Sequence[str]) -> Dict[str, Any]:
    values = list(rows)
    unique: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    duplicate_rows = 0
    conflicting_keys = set()
    missing_key_rows = 0
    for raw in values:
        row = dict(raw)
        key = tuple(str(row.get(field) or "").strip() for field in key_fields)
        if any(not value for value in key):
            missing_key_rows += 1
            continue
        prior = unique.get(key)
        if prior is not None:
            duplicate_rows += 1
            if _canonical(prior) != _canonical(row):
                conflicting_keys.add(key)
        unique[key] = row
    return {
        "rows": list(unique.values()),
        "raw_rows": len(values),
        "unique_rows": len(unique),
        "duplicate_rows": duplicate_rows,
        "conflicting_keys": len(conflicting_keys),
        "missing_key_rows": missing_key_rows,
    }


def _generated_before_open(row: Mapping[str, Any]) -> Optional[bool]:
    target = str(row.get("target_trade_date") or "")
    generated = str(row.get("generated_at") or "")
    if len(target) != 8 or not target.isdigit() or len(generated) < 10:
        return None
    date_text = generated[:10].replace("-", "")
    if len(date_text) != 8 or not date_text.isdigit():
        return None
    if date_text < target:
        return True
    if date_text > target:
        return False
    if len(generated) < 16 or generated[10] != "T":
        return None
    return generated[11:16] < "09:30"


def _prediction_quality(predictions: List[Dict[str, Any]], as_of: str) -> Dict[str, Any]:
    included = [
        row for row in predictions
        if str(row.get("target_trade_date") or "") <= as_of
    ]
    deduped = _dedupe(included, ("prediction_id",))
    modes = Counter(str(row.get("generation_mode") or "missing") for row in deduped["rows"])
    invalid_date_order = 0
    unknown_mode = 0
    live_before_open = live_after_open = live_time_unknown = 0
    for row in deduped["rows"]:
        baseline = str(row.get("baseline_trade_date") or "")
        target = str(row.get("target_trade_date") or "")
        if not (
            len(baseline) == len(target) == 8
            and baseline.isdigit() and target.isdigit() and baseline < target
        ):
            invalid_date_order += 1
        mode = str(row.get("generation_mode") or "")
        if mode not in VALID_MODES:
            unknown_mode += 1
        if mode == "live":
            before_open = _generated_before_open(row)
            if before_open is True:
                live_before_open += 1
            elif before_open is False:
                live_after_open += 1
            else:
                live_time_unknown += 1
    return {
        "included_rows": len(included),
        "unique_predictions": deduped["unique_rows"],
        "duplicate_rows": deduped["duplicate_rows"],
        "conflicting_prediction_ids": deduped["conflicting_keys"],
        "missing_prediction_id_rows": deduped["missing_key_rows"],
        "generation_modes": dict(sorted(modes.items())),
        "invalid_date_order": invalid_date_order,
        "unknown_generation_mode": unknown_mode,
        "live_generated_before_open": live_before_open,
        "live_generated_at_or_after_open": live_after_open,
        "live_generation_time_unverifiable": live_time_unknown,
        "rows": deduped["rows"],
    }


def _aggregate_c_cells(cells: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = list(cells)
    scored = [row for row in rows if row.get("hit") is not None]
    returns = [row.get("ret") for row in rows]
    hits = sum(1 for row in scored if row.get("hit") is True)
    return {
        "result_cells": len(rows),
        "prediction_samples": len({row["prediction_id"] for row in rows}),
        "independent_target_dates": len({row["target_trade_date"] for row in rows}),
        "scored_cells": len(scored),
        "positive_action_hits": hits,
        "absolute_action_hit_rate": _rate(hits, len(scored)),
        "average_stock_return": _mean(returns),
    }


def _build_c_audit(predictions: List[Dict[str, Any]], results: List[Dict[str, Any]],
                   as_of: str) -> Dict[str, Any]:
    quality = _prediction_quality(predictions, as_of)
    prediction_index = {
        str(row.get("prediction_id")): row for row in quality.pop("rows")
    }
    included_results = []
    for row in results:
        actual_date = str((row.get("actual") or {}).get("trade_date") or "")
        if actual_date and actual_date <= as_of:
            included_results.append(row)
    deduped = _dedupe(included_results, ("prediction_id", "horizon"))
    cells: List[Dict[str, Any]] = []
    evaluation_mismatches = 0
    orphan_results = 0
    for row in deduped["rows"]:
        prediction_id = str(row.get("prediction_id") or "")
        prediction = prediction_index.get(prediction_id)
        if not prediction:
            orphan_results += 1
            continue
        ret = _number((row.get("actual") or {}).get("ret"))
        frozen = prediction.get("prediction") or {}
        expectation = absolute_action_expectation(dict(frozen))
        hit = absolute_action_hit(expectation, ret)
        recorded_hit = (row.get("evaluation") or {}).get(
            "path_absolute_action_alignment"
        )
        if recorded_hit is not None and hit is not None and bool(recorded_hit) != hit:
            evaluation_mismatches += 1
        cells.append({
            "prediction_id": prediction_id,
            "generation_mode": str(prediction.get("generation_mode") or ""),
            "predecision_verified": _generated_before_open(prediction) is True,
            "target_trade_date": str(prediction.get("target_trade_date") or ""),
            "code": str(prediction.get("code") or ""),
            "action": str(frozen.get("action") or ""),
            "direction": str(frozen.get("direction") or ""),
            "horizon": str(row.get("horizon") or ""),
            "ret": ret,
            "expectation": expectation,
            "hit": hit,
        })

    by_mode_horizon: Dict[str, Dict[str, Any]] = {}
    for mode in sorted(VALID_MODES):
        mode_rows = [row for row in cells if row["generation_mode"] == mode]
        for horizon in FIXED_HORIZONS:
            key = f"{mode}:T+{horizon}"
            by_mode_horizon[key] = _aggregate_c_cells(
                row for row in mode_rows if row["horizon"] == horizon
            )
            if mode == "live":
                by_mode_horizon[f"live_preopen:T+{horizon}"] = _aggregate_c_cells(
                    row for row in mode_rows
                    if row["horizon"] == horizon and row["predecision_verified"]
                )

    latest_cells = []
    by_prediction: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in cells:
        if row["horizon"].isdigit():
            by_prediction[row["prediction_id"]].append(row)
    for rows_for_prediction in by_prediction.values():
        latest_cells.append(max(rows_for_prediction, key=lambda row: int(row["horizon"])))
    latest_by_mode = {
        mode: _aggregate_c_cells(
            row for row in latest_cells if row["generation_mode"] == mode
        )
        for mode in sorted(VALID_MODES)
    }
    latest_by_mode["live_preopen"] = _aggregate_c_cells(
        row for row in latest_cells
        if row["generation_mode"] == "live" and row["predecision_verified"]
    )

    live_t1_actions = {}
    live_t1 = [
        row for row in cells
        if row["generation_mode"] == "live"
        and row["predecision_verified"]
        and row["horizon"] == "1"
    ]
    for action in sorted({row["action"] for row in live_t1}):
        live_t1_actions[action] = _aggregate_c_cells(
            row for row in live_t1 if row["action"] == action
        )

    quality.update({
        "result_rows_included": len(included_results),
        "unique_prediction_horizon_cells": deduped["unique_rows"],
        "duplicate_result_rows": deduped["duplicate_rows"],
        "conflicting_result_keys": deduped["conflicting_keys"],
        "orphan_result_cells": orphan_results,
        "evaluation_mismatches": evaluation_mismatches,
    })
    return {
        "identity_and_counting": quality,
        "return_contract": {
            "source": "factor_results.ret joined by baseline_trade_date+code+horizon",
            "price_path": "baseline_eod_close_to_horizon_eod_close",
            "operation_price_executable": False,
            "reason": (
                "预测在baseline收盘后生成，现有收益包含目标日开盘前价格变化；"
                "可用于方向复核，不能证明9:30后可执行操作收益。"
            ),
        },
        "by_mode_and_fixed_horizon": by_mode_horizon,
        "t_plus_now_by_mode": latest_by_mode,
        "live_t1_by_action": live_t1_actions,
        "unscored_live_t1_actions": {
            action: int(stats.get("prediction_samples") or 0)
            for action, stats in live_t1_actions.items()
            if int(stats.get("scored_cells") or 0) == 0
        },
        "operation_effectiveness_verdict": "unverified_non_executable_return_anchor",
    }


def _aggregate_d_results(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    values = list(rows)
    scored = [row for row in values if row.get("hit") is not None]
    hits = sum(1 for row in scored if row.get("hit") is True)
    return {
        "result_cells": len(values),
        "decision_samples": len({row["sample_id"] for row in values}),
        "stock_days": len({(row["target_trade_date"], row["code"]) for row in values}),
        "independent_target_dates": len({row["target_trade_date"] for row in values}),
        "scored_cells": len(scored),
        "decision_hits": hits,
        "decision_hit_rate": _rate(hits, len(scored)),
        "average_evaluation_return": _mean(row.get("ret") for row in values),
    }


def _timing_benefit(expectation: str, entry: float, close: float) -> Optional[float]:
    if entry <= 0 or close <= 0:
        return None
    if expectation == "positive":
        return close / entry - 1.0
    if expectation == "non_positive":
        return entry / close - 1.0
    return None


def _aggregate_timing(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    values = list(rows)
    benefits = [row.get("benefit") for row in values]
    scored = [value for value in benefits if value is not None]
    positive = sum(1 for value in scored if value > 0)
    return {
        "samples": len(scored),
        "independent_target_dates": len({row["target_trade_date"] for row in values}),
        "average_gross_benefit_vs_no_action": _mean(scored),
        "positive_gross_benefit_rate": _rate(positive, len(scored)),
        "transaction_cost_included": False,
    }


def _effect_verdict(stats: Mapping[str, Any], policy: Mapping[str, Any]) -> str:
    dates = int(stats.get("independent_target_dates") or 0)
    avg = _number(stats.get("average_gross_benefit_vs_no_action"))
    hit_rate = _number(stats.get("positive_gross_benefit_rate"))
    history = ((policy.get("action_rules") or {}).get("history_evidence") or {})
    preliminary = history.get("minimum_preliminary_samples")
    stable = history.get("minimum_stable_samples")
    support = _number(history.get("support_min_absolute_action_hit_rate"))
    conflict = _number(history.get("conflict_max_absolute_action_hit_rate"))
    if not all(isinstance(value, int) and value > 0 for value in (preliminary, stable)):
        return "threshold_policy_missing"
    if dates < preliminary:
        return "evidence_insufficient"
    if avg is None or hit_rate is None or support is None or conflict is None:
        return "evidence_not_scorable"
    if avg > 0 and hit_rate >= support:
        return "evidence_supported" if dates >= stable else "preliminary_support"
    if avg < 0 or hit_rate <= conflict:
        return "evidence_conflicts"
    return "mixed_evidence"


def _build_d_audit(results: List[Dict[str, Any]], evolution: List[Dict[str, Any]],
                   as_of: str, policy: Mapping[str, Any]) -> Dict[str, Any]:
    included_results = [
        row for row in results
        if str(row.get("target_trade_date") or "") <= as_of
        and str(row.get("horizon_trade_date") or row.get("target_trade_date") or "") <= as_of
    ]
    result_dedupe = _dedupe(included_results, ("sample_id", "horizon"))
    result_cells = []
    for row in result_dedupe["rows"]:
        outcome = row.get("outcome") or {}
        evaluation = row.get("evaluation") or {}
        result_cells.append({
            "sample_id": str(row.get("sample_id") or ""),
            "target_trade_date": str(row.get("target_trade_date") or ""),
            "code": str(row.get("code") or ""),
            "trigger_type": str(row.get("trigger_type") or ""),
            "trigger_status": str((row.get("trigger") or {}).get("status") or ""),
            "horizon": str(row.get("horizon") or ""),
            "ret": _number(outcome.get("evaluation_return")),
            "hit": evaluation.get("decision_hit"),
        })

    by_trigger_horizon = {}
    for trigger_type, horizon in sorted({
        (row["trigger_type"], row["horizon"]) for row in result_cells
    }):
        by_trigger_horizon[f"{trigger_type}:T+{horizon}"] = _aggregate_d_results(
            row for row in result_cells
            if row["trigger_type"] == trigger_type and row["horizon"] == horizon
        )

    included_evolution = [
        row for row in evolution
        if str(row.get("target_trade_date") or "") <= as_of
    ]
    evolution_dedupe = _dedupe(included_evolution, ("task_id", "trigger_type"))
    timing_rows: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    unscored_evolution = 0
    missing_close = 0
    for row in evolution_dedupe["rows"]:
        trigger_type = str(row.get("trigger_type") or "")
        expectation = trigger_expectation(trigger_type)
        if expectation == "unscored":
            unscored_evolution += 1
            continue
        trigger = row.get("trigger") or {}
        checkpoints = row.get("checkpoints") or {}
        close = _number((checkpoints.get("close") or {}).get("price"))
        if close is None:
            missing_close += 1
            continue
        entries = {
            "immediate": _number(trigger.get("price")),
            "wait_15m": _number((checkpoints.get("15m") or {}).get("price")),
            "wait_30m": _number((checkpoints.get("30m") or {}).get("price")),
        }
        for timing, entry in entries.items():
            if entry is None:
                continue
            timing_rows[(trigger_type, timing)].append({
                "target_trade_date": str(row.get("target_trade_date") or ""),
                "code": str(row.get("code") or ""),
                "benefit": _timing_benefit(expectation, entry, close),
            })
    timing = {}
    for key, rows_for_key in sorted(timing_rows.items()):
        trigger_type, timing_name = key
        stats = _aggregate_timing(rows_for_key)
        stats["verdict"] = _effect_verdict(stats, policy)
        timing[f"{trigger_type}:{timing_name}"] = stats

    event_dates = Counter(
        str(row.get("target_trade_date") or "") for row in evolution_dedupe["rows"]
    )
    return {
        "identity_and_counting": {
            "result_rows_included": len(included_results),
            "unique_sample_horizon_cells": result_dedupe["unique_rows"],
            "duplicate_result_rows": result_dedupe["duplicate_rows"],
            "conflicting_result_keys": result_dedupe["conflicting_keys"],
            "evolution_rows_included": len(included_evolution),
            "unique_trigger_events": evolution_dedupe["unique_rows"],
            "duplicate_evolution_rows": evolution_dedupe["duplicate_rows"],
            "conflicting_evolution_keys": evolution_dedupe["conflicting_keys"],
            "triggered_stock_days": len({
                (str(row.get("target_trade_date") or ""), str(row.get("code") or ""))
                for row in evolution_dedupe["rows"]
            }),
            "independent_target_dates": len([date for date in event_dates if date]),
            "trigger_events_by_date": dict(sorted(event_dates.items())),
        },
        "result_evidence_by_trigger_and_horizon": by_trigger_horizon,
        "gross_timing_evidence": timing,
        "timing_contract": {
            "positive_trigger": "close_price / execution_price - 1",
            "risk_trigger": "execution_price / close_price - 1",
            "baseline": "no_action_until_same_day_close",
            "transaction_cost_included": False,
            "user_execution_used": False,
        },
        "unscored_evolution_events": unscored_evolution,
        "evolution_missing_close": missing_close,
    }


def _gate_statuses(c_audit: Mapping[str, Any], d_audit: Mapping[str, Any],
                   source_errors: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    c_quality = c_audit.get("identity_and_counting") or {}
    d_quality = d_audit.get("identity_and_counting") or {}
    lineage_failures = (
        len(source_errors)
        + int(c_quality.get("invalid_date_order") or 0)
        + int(c_quality.get("unknown_generation_mode") or 0)
        + int(c_quality.get("live_generated_at_or_after_open") or 0)
        + int(c_quality.get("live_generation_time_unverifiable") or 0)
    )
    count_conflicts = (
        int(c_quality.get("conflicting_prediction_ids") or 0)
        + int(c_quality.get("conflicting_result_keys") or 0)
        + int(d_quality.get("conflicting_result_keys") or 0)
        + int(d_quality.get("conflicting_evolution_keys") or 0)
    )
    independent_dates = int(d_quality.get("independent_target_dates") or 0)
    return [
        {
            "gate": "source_truth",
            "status": "pass" if lineage_failures == 0 else "fail",
            "detail": f"源文件、日期、模式或事前生成时点不合格共{lineage_failures}项",
        },
        {
            "gate": "honest_counting",
            "status": "pass" if count_conflicts == 0 else "fail",
            "detail": f"相同身份但内容冲突的键共{count_conflicts}个",
        },
        {
            "gate": "consistent_evaluation",
            "status": "partial",
            "detail": "C线收益起点不可执行；D线为触发价毛收益，尚未扣交易成本",
        },
        {
            "gate": "operation_value",
            "status": "insufficient",
            "detail": "C线只能复核方向；D线按真实触发价比较，但独立日期仍有限",
        },
        {
            "gate": "cross_time_stability",
            "status": "insufficient" if independent_dates < 20 else "partial",
            "detail": f"D线当前独立目标交易日{independent_dates}个",
        },
    ]


def build_strategy_validity_audit(
    *,
    as_of_trade_date: str,
    predictions: Iterable[Mapping[str, Any]],
    prediction_results: Iterable[Mapping[str, Any]],
    forecast_results: Iterable[Mapping[str, Any]],
    forecast_evolution: Iterable[Mapping[str, Any]],
    strategy_policy: Mapping[str, Any],
    source_errors: Sequence[Mapping[str, Any]] = (),
    source_digests: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    as_of = _trade_date(as_of_trade_date, field="as_of_trade_date")
    c_audit = _build_c_audit(
        [dict(row) for row in predictions],
        [dict(row) for row in prediction_results],
        as_of,
    )
    d_audit = _build_d_audit(
        [dict(row) for row in forecast_results],
        [dict(row) for row in forecast_evolution],
        as_of,
        strategy_policy,
    )
    gates = _gate_statuses(c_audit, d_audit, source_errors)
    report = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "audit_policy_version": AUDIT_POLICY_VERSION,
        "as_of_trade_date": as_of,
        "overall_verdict": "strategy_effectiveness_unproven",
        "gates": gates,
        "c_line": c_audit,
        "d_line": d_audit,
        "source_errors": list(source_errors),
        "source_digests": dict(source_digests or {}),
        "mail_policy": {
            "allow_c_direction_statistics": True,
            "allow_c_operation_profit_claim": False,
            "allow_d_trigger_facts": True,
            "allow_d_effectiveness_claim": any(
                row.get("verdict") in {"preliminary_support", "evidence_supported"}
                for row in (d_audit.get("gross_timing_evidence") or {}).values()
            ),
            "hide_raw_matured_cell_count": True,
        },
    }
    report["facts_digest"] = _digest(report)
    return report


def _fmt_pct(value: Any) -> str:
    number = _number(value)
    return "待验证" if number is None else f"{number:+.2%}"


def _fmt_rate(value: Any) -> str:
    number = _number(value)
    return "待验证" if number is None else f"{number:.1%}"


def render_strategy_validity_audit(report: Mapping[str, Any]) -> str:
    as_of = report.get("as_of_trade_date") or "待验证"
    c_line = report.get("c_line") or {}
    d_line = report.get("d_line") or {}
    c_quality = c_line.get("identity_and_counting") or {}
    d_quality = d_line.get("identity_and_counting") or {}
    live_t1 = (
        (c_line.get("by_mode_and_fixed_horizon") or {}).get("live_preopen:T+1")
        or {}
    )
    lines = [
        f"# {as_of} 策略有效性审计",
        "",
        "## 审计结论",
        "",
        "- **总判断**: 当前A/B/C/D数据可用于保存事实和继续积累，尚不能证明整套策略能稳定提高实际交易收益。",
        "- **C线**: 可以复核收盘到收盘的方向，但当前收益起点不可执行，禁止作为9:30后操作收益。",
        "- **D线**: 触发价和盘中演变可用于比较操作时机；目前只报告毛效果，且独立交易日不足。",
        "- **邮件处理**: 不再展示“成熟结果总行数”作为策略样本数；未经审计通过的统计不得修改动作。",
        "",
        "## 五道审计关",
        "",
        "| 审计关 | 状态 | 说明 |",
        "|---|---|---|",
    ]
    status_text = {
        "pass": "通过", "partial": "部分通过", "fail": "不通过",
        "insufficient": "证据不足",
    }
    for gate in report.get("gates") or []:
        lines.append(
            f"| {gate.get('gate')} | {status_text.get(gate.get('status'), gate.get('status'))} | {gate.get('detail')} |"
        )
    lines.extend([
        "",
        "## 真实样本口径",
        "",
        (
            f"- C线: 原始预测{c_quality.get('included_rows', 0)}行，去重后"
            f"{c_quality.get('unique_predictions', 0)}次预测；live "
            f"{(c_quality.get('generation_modes') or {}).get('live', 0)}次，replay "
            f"{(c_quality.get('generation_modes') or {}).get('replay', 0)}次。"
        ),
        (
            f"- C线live生成时点: 开盘前{c_quality.get('live_generated_before_open', 0)}次，"
            f"开盘后{c_quality.get('live_generated_at_or_after_open', 0)}次，"
            f"无法核实{c_quality.get('live_generation_time_unverifiable', 0)}次。"
        ),
        (
            f"- C线有效live T+1方向样本（已剔除开盘后生成）: "
            f"{live_t1.get('prediction_samples', 0)}次预测，"
            f"来自{live_t1.get('independent_target_dates', 0)}个目标交易日；"
            f"动作命中率{_fmt_rate(live_t1.get('absolute_action_hit_rate'))}，"
            f"平均股票收益{_fmt_pct(live_t1.get('average_stock_return'))}。"
        ),
        "- T+1、T+5、T+now是同一次预测的不同路径节点，不分别冒充独立样本。",
        (
            f"- D线: {d_quality.get('unique_trigger_events', 0)}条去重触发，"
            f"涉及{d_quality.get('triggered_stock_days', 0)}个股票日，"
            f"但只有{d_quality.get('independent_target_dates', 0)}个独立目标交易日。"
        ),
        "",
        "## C线有效性",
        "",
        "- 当前收益口径: 前一交易日收盘价到后续收盘价。",
        "- 当前预测生成于前一日收盘之后，因此该收益包含无法在预测后成交的价格变化。",
        "- 结论: 仅保留为方向研究证据；买入、卖出收益有效性待建立目标日可执行价格地基。",
        "",
        "### 有效live T+1动作复核",
        "",
        "| C线动作 | 预测数 | 独立日 | 已评分 | 方向命中率 | 平均收益 | 审计判断 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for action, stats in sorted((c_line.get("live_t1_by_action") or {}).items()):
        scored = int(stats.get("scored_cells") or 0)
        independent_dates = int(stats.get("independent_target_dates") or 0)
        if scored == 0:
            c_verdict = "动作含义未映射，不能评分"
        elif independent_dates < 5:
            c_verdict = "独立日不足，仅作方向参考"
        else:
            c_verdict = "仅为方向证据，非可执行收益"
        lines.append(
            f"| {action} | {stats.get('prediction_samples', 0)} | "
            f"{independent_dates} | {scored} | "
            f"{_fmt_rate(stats.get('absolute_action_hit_rate'))} | "
            f"{_fmt_pct(stats.get('average_stock_return'))} | {c_verdict} |"
        )
    lines.extend([
        "",
        "## D线操作时机",
        "",
        "以下为相对“不操作并持有到当日收盘”的毛效果，未扣佣金、印花税和滑点。",
        "",
        "| 触发与时机 | 样本 | 独立日 | 平均毛增益 | 正增益率 | 结论 |",
        "|---|---:|---:|---:|---:|---|",
    ])

    verdict_text = {
        "evidence_insufficient": "证据不足",
        "preliminary_support": "初步支持",
        "evidence_supported": "证据支持",
        "evidence_conflicts": "证据冲突",
        "mixed_evidence": "结果混合",
        "threshold_policy_missing": "阈值缺失",
        "evidence_not_scorable": "不可评分",
    }
    for key, stats in sorted((d_line.get("gross_timing_evidence") or {}).items()):
        lines.append(
            f"| {key} | {stats.get('samples', 0)} | "
            f"{stats.get('independent_target_dates', 0)} | "
            f"{_fmt_pct(stats.get('average_gross_benefit_vs_no_action'))} | "
            f"{_fmt_rate(stats.get('positive_gross_benefit_rate'))} | "
            f"{verdict_text.get(stats.get('verdict'), stats.get('verdict'))} |"
        )
    if not (d_line.get("gross_timing_evidence") or {}):
        lines.append("| 暂无可评分触发 | 0 | 0 | 待验证 | 待验证 | 证据不足 |")
    lines.extend([
        "",
        "## 当前允许进入每日邮件的内容",
        "",
        "- 允许: 真实持仓盈亏、C线冻结动作、D线真实触发及价格、数据缺口。",
        "- 暂不允许: 用C线收盘到收盘收益声称可执行盈利；用记录行数声称独立样本充足。",
        "- D线操作效果只有达到多个独立交易日并通过现有纪律阈值后，才可标记为初步支持。",
        "",
        f"> 事实哈希: `{report.get('facts_digest') or '待验证'}`",
        "",
    ])
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temp, path)


def run_strategy_validity_audit(
    *,
    as_of_trade_date: str,
    predictions_path: Path = PREDICTIONS_FILE,
    prediction_results_path: Path = PREDICTION_RESULTS_FILE,
    forecast_results_path: Path = FORECAST_RESULTS_FILE,
    forecast_evolution_path: Path = FORECAST_EVOLUTION_FILE,
    output_dir: Path = EVIDENCE_DIR,
    strategy_policy: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    sources = {
        "predictions": Path(predictions_path),
        "prediction_results": Path(prediction_results_path),
        "forecast_results": Path(forecast_results_path),
        "forecast_evolution": Path(forecast_evolution_path),
    }
    loaded = {name: _read_jsonl(path) for name, path in sources.items()}
    source_errors = [error for _, errors in loaded.values() for error in errors]
    report = build_strategy_validity_audit(
        as_of_trade_date=as_of_trade_date,
        predictions=loaded["predictions"][0],
        prediction_results=loaded["prediction_results"][0],
        forecast_results=loaded["forecast_results"][0],
        forecast_evolution=loaded["forecast_evolution"][0],
        strategy_policy=strategy_policy or config.load_strategy_policy(),
        source_errors=source_errors,
        source_digests={name: _file_digest(path) for name, path in sources.items()},
    )
    as_of = report["as_of_trade_date"]
    out_dir = Path(output_dir)
    paths = {
        "dated_json": out_dir / f"strategy_validity_audit_{as_of}.json",
        "dated_md": out_dir / f"strategy_validity_audit_{as_of}.md",
        "latest_json": out_dir / "strategy_validity_audit_latest.json",
        "latest_md": out_dir / "strategy_validity_audit_latest.md",
    }
    json_content = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False,
    ) + "\n"
    markdown = render_strategy_validity_audit(report)
    for key, path in paths.items():
        _atomic_write(path, json_content if key.endswith("json") else markdown)
    return {
        "status": "written",
        "as_of_trade_date": as_of,
        "overall_verdict": report["overall_verdict"],
        "facts_digest": report["facts_digest"],
        **{f"{key}_path": str(path) for key, path in paths.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit C/D strategy evidence validity")
    parser.add_argument("--as-of", required=True, help="finalized trade date YYYYMMDD")
    args = parser.parse_args()
    print(json.dumps(
        run_strategy_validity_audit(as_of_trade_date=args.as_of),
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
