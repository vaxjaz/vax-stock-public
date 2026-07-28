# -*- coding: utf-8 -*-
"""Strict adapter from legacy incremental returns to frozen group outcomes.

The legacy result file is append-only and may repeat an already known horizon
on every later EOD run.  This module merges by field and horizon, rejects
conflicts, and records the first row at which a horizon became complete.  It
then joins that mature label to the earliest EOD-aligned MR5 group assignment.

No selection statistic is calculated here.  The output is the auditable fact
base that a later walk-forward ``select`` stage may consume.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from numbers import Real
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from vaxstock.research.contextual_group import (
    GROUP_DIMENSION,
    GROUP_VERSION,
    STOCK_GROUP_FACTOR_ID,
    STOCK_GROUP_FACTOR_VERSION,
)
from vaxstock.research.contracts import (
    GROUP_OUTCOME_SCHEMA_VERSION,
    ContractError,
    canonical_digest,
    make_group_outcome_id,
    validate_factor_value,
    validate_group_outcome_sample,
)


CHINA_TZ = timezone(timedelta(hours=8))
LEGACY_RESULT_SOURCE = "legacy.factor_results"
LEGACY_RESULT_SOURCE_REF = "var/eval/factor_results.jsonl"
LEGACY_BENCHMARK_CODE = "000001.SH"
LEGACY_BENCHMARK_KIND = "legacy_market_index"
GROUP_SELECTION_POLICY = "earliest_eod_aligned_group_v1"


def _trade_date(value: Any, field: str) -> str:
    text = str(value or "").strip()
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ContractError(f"{field} must be YYYYMMDD") from exc
    return text


def _aware(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include a timezone offset")
    return parsed


def _legacy_available_at(value: Any) -> Tuple[str, bool]:
    """Normalize legacy naive ``filled_ts`` as Asia/Shanghai capture time."""

    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("factor_results filled_ts must be ISO-8601") from exc
    inferred = parsed.tzinfo is None or parsed.utcoffset() is None
    if inferred:
        parsed = parsed.replace(tzinfo=CHINA_TZ)
    return parsed.isoformat(timespec="seconds"), inferred


def _horizon(value: Any, field: str) -> int:
    try:
        horizon = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field} horizon must be a positive integer") from exc
    if horizon <= 0:
        raise ContractError(f"{field} horizon must be a positive integer")
    return horizon


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ContractError(f"{field} must be a finite number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ContractError(f"{field} must be a finite number")
    return numeric


def _horizon_map(
    row: Mapping[str, Any],
    field: str,
) -> Dict[int, Any]:
    raw = row.get(field) or {}
    if not isinstance(raw, Mapping):
        raise ContractError(f"factor_results {field} must be an object")
    normalized = {}
    for raw_horizon, raw_value in raw.items():
        horizon = _horizon(raw_horizon, field)
        value = (
            _trade_date(raw_value, f"{field}[{horizon}]")
            if field == "horizon_trade_dates"
            else _number(raw_value, f"{field}[{horizon}]")
        )
        normalized[horizon] = value
    return normalized


def _same_value(field: str, left: Any, right: Any) -> bool:
    if field == "horizon_trade_dates":
        return left == right
    return math.isclose(
        float(left), float(right), rel_tol=0.0, abs_tol=1e-12
    )


def merge_legacy_factor_results(
    rows: Iterable[Mapping[str, Any]],
) -> Tuple[Dict[Tuple[str, str, int], Dict[str, Any]], Dict[str, Any]]:
    """Merge incremental legacy outcomes without last-write ambiguity."""

    materialized = [dict(row) for row in rows]
    state: Dict[Tuple[str, str], Dict[str, Dict[int, Any]]] = {}
    outcomes: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
    inferred_timezone_rows = 0
    duplicate_entries = 0
    total_entries = 0
    for row_number, row in enumerate(materialized, start=1):
        trade_date = _trade_date(
            row.get("trade_date"), "factor_results trade_date"
        )
        code = str(row.get("code") or "").strip()
        if not code:
            raise ContractError("factor_results code is required")
        available_at, inferred = _legacy_available_at(row.get("filled_ts"))
        inferred_timezone_rows += int(inferred)
        maps = {
            field: _horizon_map(row, field)
            for field in (
                "ret",
                "mkt_ret",
                "excess",
                "horizon_trade_dates",
            )
        }
        box = state.setdefault(
            (trade_date, code),
            {
                "ret": {},
                "mkt_ret": {},
                "excess": {},
                "horizon_trade_dates": {},
            },
        )
        affected = set()
        for field, values in maps.items():
            for horizon, value in values.items():
                total_entries += 1
                affected.add(horizon)
                if horizon in box[field]:
                    duplicate_entries += 1
                    if not _same_value(field, box[field][horizon], value):
                        raise ContractError(
                            "conflicting factor_results value at "
                            f"{trade_date}/{code}/T+{horizon}/{field}"
                        )
                    continue
                box[field][horizon] = value

        for horizon in sorted(affected):
            key = (trade_date, code, horizon)
            if key in outcomes:
                continue
            if not all(
                horizon in box[field]
                for field in (
                    "ret",
                    "mkt_ret",
                    "excess",
                    "horizon_trade_dates",
                )
            ):
                continue
            outcome_trade_date = str(
                box["horizon_trade_dates"][horizon]
            )
            if outcome_trade_date <= trade_date:
                raise ContractError(
                    "factor_results outcome trade date must follow baseline at "
                    f"{trade_date}/{code}/T+{horizon}"
                )
            ret = float(box["ret"][horizon])
            benchmark_ret = float(box["mkt_ret"][horizon])
            excess_ret = float(box["excess"][horizon])
            if not math.isclose(
                excess_ret,
                ret - benchmark_ret,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ContractError(
                    "factor_results excess mismatch at "
                    f"{trade_date}/{code}/T+{horizon}"
                )
            outcomes[key] = {
                "as_of_trade_date": trade_date,
                "code": code,
                "horizon_sessions": horizon,
                "outcome_trade_date": outcome_trade_date,
                "outcome_available_at": available_at,
                "ret": ret,
                "benchmark_ret": benchmark_ret,
                "excess_ret": excess_ret,
                "availability_timezone_inferred": inferred,
                "first_complete_row_number": row_number,
            }
    incomplete = 0
    for (trade_date, code), box in state.items():
        horizons = set().union(*(set(values) for values in box.values()))
        incomplete += sum(
            (trade_date, code, horizon) not in outcomes
            for horizon in horizons
        )
    horizon_counts = Counter(
        outcome["horizon_sessions"] for outcome in outcomes.values()
    )
    audit = {
        "raw_rows": len(materialized),
        "raw_field_entries": total_entries,
        "duplicate_field_entries": duplicate_entries,
        "merged_keys": len(state),
        "mature_outcomes": len(outcomes),
        "incomplete_horizons": incomplete,
        "inferred_timezone_rows": inferred_timezone_rows,
        "horizon_counts": {
            str(horizon): count
            for horizon, count in sorted(horizon_counts.items())
        },
        "merge_policy": "field_horizon_strict_first_complete_v1",
    }
    return outcomes, audit


def _has_legacy_eod_features(row: Mapping[str, Any]) -> bool:
    value = row.get("value")
    factor_groups = (
        value.get("factor_groups")
        if isinstance(value, Mapping)
        else None
    )
    if not isinstance(factor_groups, Mapping):
        return False
    return any(
        str(series_id).startswith("legacy_snapshot::legacy.")
        for series_id in factor_groups
    )


def select_eod_group_assignments(
    rows: Iterable[Mapping[str, Any]],
) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], Dict[str, Any]]:
    """Select the earliest group run that directly contains EOD legacy factors."""

    candidates: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    scanned = 0
    rejected_non_group = 0
    rejected_non_eod = 0
    for raw in rows:
        row = dict(raw)
        scanned += 1
        validate_factor_value(row)
        if not (
            row.get("entity_type") == "stock"
            and row.get("dimension") == GROUP_DIMENSION
            and row.get("factor_id") == STOCK_GROUP_FACTOR_ID
            and row.get("factor_version") == STOCK_GROUP_FACTOR_VERSION
        ):
            rejected_non_group += 1
            continue
        value = row.get("value")
        if not isinstance(value, Mapping):
            raise ContractError("stock group value must be an object")
        if (
            value.get("group_version") != GROUP_VERSION
            or value.get("label_usage") != "none"
        ):
            raise ContractError("stock group version/label boundary mismatch")
        if not _has_legacy_eod_features(row):
            rejected_non_eod += 1
            continue
        key = (
            _trade_date(row.get("as_of_trade_date"), "group as_of_trade_date"),
            str(row.get("entity_id") or "").strip(),
        )
        if not key[1]:
            raise ContractError("group entity_id is required")
        candidates.setdefault(key, []).append(row)

    selected = {}
    multiple_candidates = 0
    for key, values in candidates.items():
        if len(values) > 1:
            multiple_candidates += 1
        selected[key] = min(
            values,
            key=lambda row: (
                _aware(row.get("calculated_at"), "group calculated_at"),
                str(row.get("factor_value_id") or ""),
            ),
        )
    return selected, {
        "factor_rows_scanned": scanned,
        "eod_groups_selected": len(selected),
        "multiple_eod_candidates": multiple_candidates,
        "rejected_non_group": rejected_non_group,
        "rejected_non_eod": rejected_non_eod,
        "selection_policy": GROUP_SELECTION_POLICY,
    }


def _sample(
    group: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> Dict[str, Any]:
    group_available_at = _aware(
        group.get("available_at"), "group available_at"
    ).isoformat(timespec="seconds")
    group_calculated_at = _aware(
        group.get("calculated_at"), "group calculated_at"
    ).isoformat(timespec="seconds")
    outcome_available_at = _aware(
        outcome.get("outcome_available_at"), "outcome available_at"
    ).isoformat(timespec="seconds")
    if _aware(group_calculated_at, "group calculated_at") > _aware(
        outcome_available_at, "outcome available_at"
    ):
        raise ContractError("outcome became available before its group assignment")
    horizon = int(outcome["horizon_sessions"])
    source_ref = (
        f"{LEGACY_RESULT_SOURCE_REF}#"
        f"{outcome['as_of_trade_date']}:{outcome['code']}:T+{horizon}"
    )
    digest = canonical_digest({
        "group_factor_value_id": group["factor_value_id"],
        "horizon_sessions": horizon,
        "outcome_trade_date": outcome["outcome_trade_date"],
        "outcome_available_at": outcome_available_at,
        "ret": float(outcome["ret"]),
        "benchmark_ret": float(outcome["benchmark_ret"]),
        "excess_ret": float(outcome["excess_ret"]),
        "benchmark_code": LEGACY_BENCHMARK_CODE,
        "source": LEGACY_RESULT_SOURCE,
    })
    value = group.get("value")
    row = {
        "schema_version": GROUP_OUTCOME_SCHEMA_VERSION,
        "outcome_id": "",
        "as_of_trade_date": str(outcome["as_of_trade_date"]),
        "code": str(outcome["code"]),
        "group_factor_value_id": str(group["factor_value_id"]),
        "group_factor_version": str(group["factor_version"]),
        "group_version": str(value["group_version"]),
        "group_available_at": group_available_at,
        "group_calculated_at": group_calculated_at,
        "horizon_sessions": horizon,
        "outcome_trade_date": str(outcome["outcome_trade_date"]),
        "outcome_available_at": outcome_available_at,
        "ret": float(outcome["ret"]),
        "benchmark_ret": float(outcome["benchmark_ret"]),
        "excess_ret": float(outcome["excess_ret"]),
        "benchmark_code": LEGACY_BENCHMARK_CODE,
        "benchmark_kind": LEGACY_BENCHMARK_KIND,
        "source": LEGACY_RESULT_SOURCE,
        "source_ref": source_ref,
        "independent_session_id": str(outcome["as_of_trade_date"]),
        "input_digest": digest,
        "return_unit": "decimal_return",
        "quality": "observed",
        "label_status": "matured",
        "group_selection_policy": GROUP_SELECTION_POLICY,
        "availability_timezone_inferred": bool(
            outcome.get("availability_timezone_inferred")
        ),
        "outcome_first_complete_row_number": int(
            outcome["first_complete_row_number"]
        ),
    }
    row["outcome_id"] = make_group_outcome_id(row)
    validate_group_outcome_sample(row)
    return row


def build_group_outcome_samples(
    *,
    group_factor_rows: Iterable[Mapping[str, Any]],
    factor_result_rows: Iterable[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Join mature legacy labels to EOD-aligned group factors."""

    outcomes, outcome_audit = merge_legacy_factor_results(
        factor_result_rows
    )
    groups, group_audit = select_eod_group_assignments(group_factor_rows)
    samples = []
    missing_group = Counter()
    for key in sorted(outcomes):
        outcome = outcomes[key]
        group_key = (
            str(outcome["as_of_trade_date"]),
            str(outcome["code"]),
        )
        group = groups.get(group_key)
        if group is None:
            missing_group[group_key[0]] += 1
            continue
        samples.append(_sample(group, outcome))
    horizon_counts = Counter(
        sample["horizon_sessions"] for sample in samples
    )
    summary = {
        "status": "complete" if not missing_group else "partial",
        "outcome_audit": outcome_audit,
        "group_audit": group_audit,
        "samples_ready": len(samples),
        "sample_horizon_counts": {
            str(horizon): count
            for horizon, count in sorted(horizon_counts.items())
        },
        "independent_trade_dates": len({
            sample["independent_session_id"] for sample in samples
        }),
        "missing_group_samples": sum(missing_group.values()),
        "missing_group_by_trade_date": dict(sorted(missing_group.items())),
        "selection_status": "not_executed",
        "forecast_status": "not_executed",
        "benchmark_boundary": (
            "000001.SH legacy market-index excess; not a track benchmark"
        ),
    }
    return samples, summary
