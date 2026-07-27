# -*- coding: utf-8 -*-
"""Point-in-time E dimension: seller consensus, guidance, and valuation gap.

This module is deliberately strategy-neutral.  It records source observations
and deterministic candidate factors, but it does not label them effective or
change any production action.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from numbers import Integral, Real
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from vaxstock.research.contracts import (
    FACTOR_VALUE_SCHEMA_VERSION,
    OBSERVATION_SCHEMA_VERSION,
    RUN_MANIFEST_SCHEMA_VERSION,
    ContractError,
    canonical_digest,
    make_factor_value_id,
    make_observation_id,
    make_run_id,
)


DIMENSION = "E"
FEATURE_SET_VERSION = "expectation_dimension_v1"
CONSENSUS_FACTOR_VERSION = "E_consensus_90d_v1"
GUIDANCE_FACTOR_VERSION = "E_company_guidance_v1"
VALUATION_GAP_FACTOR_VERSION = "E_price_relative_to_seller_estimates_v1"
NOT_EXECUTED = "not_executed"
CONSENSUS_WINDOW_DAYS = 90
CHINA_TZ = timezone(timedelta(hours=8))

REPORT_SOURCE = "tushare.report_rc"
GUIDANCE_SOURCE = "tushare.forecast"
DAILY_BASIC_SOURCE = "tushare.daily_basic"
REPORT_DOC = "https://tushare.pro/document/2?doc_id=292"
GUIDANCE_DOC = "https://tushare.pro/document/2?doc_id=45"
DAILY_BASIC_DOC = "https://tushare.pro/document/2?doc_id=32"


def _trade_date(value: Any, field: str = "trade_date") -> str:
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
        raise ContractError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include timezone")
    return parsed


def _json_value(value: Any) -> Any:
    """Normalize dataframe/numpy scalars into strict JSON without guessing."""

    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, Mapping):
        return {str(key): _json_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(child) for child in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_value(item())
        except Exception:
            pass
    return str(value)


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _source_identity(record: Mapping[str, Any]) -> Tuple[str, str, str]:
    return (
        str(record.get("source") or ""),
        str(record.get("source_ref") or ""),
        str(record.get("revision_id") or ""),
    )


def _existing_index(
    observations: Iterable[Mapping[str, Any]],
) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    return {
        _source_identity(row): dict(row)
        for row in observations
        if row.get("source") and row.get("source_ref") and row.get("revision_id")
    }


def _observation(
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    value: Any,
    effective_date: str,
    available_at: str,
    retrieved_at: str,
    source: str,
    source_ref: str,
    revision_id: str,
    existing: Mapping[Tuple[str, str, str], Mapping[str, Any]],
    quality: str = "observed",
) -> Dict[str, Any]:
    identity = (source, source_ref, revision_id)
    if identity in existing:
        return dict(existing[identity])
    row = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "observation_id": "",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "dimension": DIMENSION,
        "field": field,
        "value": _json_value(value),
        "effective_date": str(effective_date),
        "available_at": str(available_at),
        "retrieved_at": str(retrieved_at),
        "source": source,
        "source_ref": source_ref,
        "revision_id": revision_id,
        "quality": quality,
    }
    row["observation_id"] = make_observation_id(row)
    return row


def _factor(
    *,
    entity_id: str,
    factor_id: str,
    factor_version: str,
    value: Any,
    as_of_trade_date: str,
    effective_date: str,
    inputs: Iterable[Mapping[str, Any]],
    calculated_at: str,
) -> Dict[str, Any]:
    input_rows = list(inputs)
    input_ids = sorted({str(row["observation_id"]) for row in input_rows})
    if not input_ids:
        raise ContractError(f"{factor_id} requires source observations")
    available = max(
        (str(row["available_at"]) for row in input_rows),
        key=lambda value: _aware(value, "available_at"),
    )
    row = {
        "schema_version": FACTOR_VALUE_SCHEMA_VERSION,
        "factor_value_id": "",
        "entity_type": "stock",
        "entity_id": entity_id,
        "dimension": DIMENSION,
        "factor_id": factor_id,
        "factor_version": factor_version,
        "value": _json_value(value),
        "as_of_trade_date": as_of_trade_date,
        "effective_date": effective_date,
        "available_at": available,
        "calculated_at": calculated_at,
        "input_observation_ids": input_ids,
        "input_digest": canonical_digest(input_ids),
        "quality": "calculated",
    }
    row["factor_value_id"] = make_factor_value_id(row)
    return row


def _report_available_at(row: Mapping[str, Any]) -> str:
    create_time = str(row.get("create_time") or "").strip()
    if create_time:
        try:
            parsed = datetime.fromisoformat(create_time.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                parsed = parsed.replace(tzinfo=CHINA_TZ)
            return parsed.isoformat(timespec="seconds")
        except ValueError:
            pass
    report_date = _trade_date(row.get("report_date"), "report_date")
    parsed_date = datetime.strptime(report_date, "%Y%m%d").date()
    return datetime.combine(parsed_date, time(23, 59, 59), CHINA_TZ).isoformat()


def _quarter_end(quarter: Any) -> Optional[str]:
    text = str(quarter or "").strip().upper()
    if len(text) != 6 or text[4] != "Q" or text[5] not in "1234":
        return None
    year = text[:4]
    if not year.isdigit():
        return None
    suffix = {"1": "0331", "2": "0630", "3": "0930", "4": "1231"}[text[5]]
    return year + suffix


def _available_before_announcement(
    observation: Mapping[str, Any],
    ann_date: str,
) -> bool:
    boundary = datetime.combine(
        datetime.strptime(ann_date, "%Y%m%d").date(),
        time(0, 0),
        CHINA_TZ,
    )
    return _aware(
        observation.get("available_at"), "seller estimate available_at"
    ).astimezone(CHINA_TZ) < boundary


def _code(value: Any) -> str:
    return str(value or "").strip().split(".", 1)[0]


def _latest_per_org(
    rows: Iterable[Mapping[str, Any]],
    value_field: str,
    *,
    positive_only: bool = False,
) -> Tuple[List[float], List[Mapping[str, Any]], int]:
    by_org: Dict[str, List[Mapping[str, Any]]] = {}
    report_count = 0
    for observation in rows:
        value = observation.get("value") or {}
        org = str(value.get("org_name") or "").strip()
        number = _number(value.get(value_field))
        if not org or number is None or (positive_only and number <= 0):
            continue
        by_org.setdefault(org, []).append(observation)
        report_count += 1

    org_values: List[float] = []
    selected_inputs: List[Mapping[str, Any]] = []
    for org_rows in by_org.values():
        latest_date = max(
            str((row.get("value") or {}).get("report_date") or "")
            for row in org_rows
        )
        latest = [
            row for row in org_rows
            if str((row.get("value") or {}).get("report_date") or "") == latest_date
        ]
        values = [
            _number((row.get("value") or {}).get(value_field))
            for row in latest
        ]
        usable = [
            number for number in values
            if number is not None and (not positive_only or number > 0)
        ]
        if not usable:
            continue
        org_values.append(float(median(usable)))
        selected_inputs.extend(latest)
    return org_values, selected_inputs, report_count


def _query_status_value(result: Mapping[str, Any]) -> Dict[str, Any]:
    rows = list(result.get("rows") or [])
    return {
        "available": bool(result.get("available")),
        "complete": bool(result.get("complete")),
        "reason": result.get("reason"),
        "row_count": len(rows),
        "rows_digest": canonical_digest(_json_value(rows)),
        "query": _json_value(result.get("query") or {}),
        "fields": list(result.get("fields") or []),
        "actual_fields": list(result.get("actual_fields") or []),
        "missing_fields": list(result.get("missing_fields") or []),
    }


def _complete_report_window(
    result: Mapping[str, Any],
    *,
    required_start: str,
    required_end: str,
) -> bool:
    """Prove that the global seller-report query covers the full factor window."""

    query = result.get("query") or {}
    start = str(query.get("start_date") or "")
    end = str(query.get("end_date") or "")
    query_code = str(query.get("ts_code") or "").strip()
    try:
        _trade_date(start, "report query start_date")
        _trade_date(end, "report query end_date")
    except ContractError:
        return False
    return bool(
        result.get("available")
        and result.get("complete")
        and not query_code
        and start <= required_start
        and end >= required_end
    )


def build_expectation_run(
    *,
    as_of_trade_date: str,
    previous_trade_date: str,
    retrieved_at: str,
    universe_codes: Iterable[str],
    report_result: Mapping[str, Any],
    forecasts_by_code: Mapping[str, Mapping[str, Any]],
    daily_basic_by_code: Mapping[str, Mapping[str, Any]],
    existing_observations: Iterable[Mapping[str, Any]] = (),
    mode: str = "live",
) -> Tuple[
    Dict[str, Any],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    Dict[str, Any],
]:
    """Build one pre-open E-dimension run without making a strategy decision."""

    as_of = _trade_date(as_of_trade_date, "as_of_trade_date")
    previous = _trade_date(previous_trade_date, "previous_trade_date")
    retrieved_dt = _aware(retrieved_at, "retrieved_at")
    retrieved_iso = retrieved_dt.isoformat(timespec="seconds")
    if mode not in {"live", "replay", "backtest"}:
        raise ContractError("mode must be live/replay/backtest")
    codes = sorted({_code(code) for code in universe_codes if _code(code)})
    if not codes:
        raise ContractError("expectation run requires a non-empty universe")

    historical = [dict(row) for row in existing_observations]
    existing = _existing_index(historical)
    observations: List[Dict[str, Any]] = []
    notes: List[str] = [
        "candidate E factors only; no production action or effective label",
        "group/select/forecast were not executed",
        "report_rc.np and forecast.net_profit_* are unit-aligned in wan per "
        "Tushare docs; accounting-scope equivalence is source-defined and "
        "not independently audited",
    ]

    report_status = _query_status_value(report_result)
    report_query = report_result.get("query") or {}
    report_status_ref = (
        f"tushare.report_rc:query:{report_query.get('start_date')}:{report_query.get('end_date')}"
    )
    report_status_revision = canonical_digest(report_status)
    report_status_observation = _observation(
        entity_type="market",
        entity_id="CN-A",
        field="seller_consensus_query",
        value=report_status,
        effective_date=as_of,
        available_at=retrieved_iso,
        retrieved_at=retrieved_iso,
        source=REPORT_SOURCE,
        source_ref=report_status_ref,
        revision_id=report_status_revision,
        existing=existing,
    )
    observations.append(report_status_observation)

    report_observations: List[Dict[str, Any]] = []
    skipped_future_source_time = 0
    for raw in report_result.get("rows") or []:
        row = _json_value(raw)
        code = _code(row.get("ts_code"))
        if code not in codes:
            continue
        try:
            available_at = _report_available_at(row)
        except ContractError:
            continue
        if _aware(available_at, "report available_at") > retrieved_dt:
            skipped_future_source_time += 1
            continue
        source_key = {
            key: row.get(key)
            for key in (
                "ts_code", "report_date", "report_title", "org_name",
                "author_name", "quarter",
            )
        }
        source_ref = (
            f"tushare.report_rc:{code}:"
            f"{canonical_digest(source_key)[:24]}"
        )
        observation = _observation(
            entity_type="stock",
            entity_id=code,
            field="seller_estimate",
            value=row,
            effective_date=_quarter_end(row.get("quarter"))
            or _trade_date(row.get("report_date"), "report_date"),
            available_at=available_at,
            retrieved_at=retrieved_iso,
            source=REPORT_SOURCE,
            source_ref=source_ref,
            revision_id=canonical_digest(row),
            existing=existing,
        )
        observations.append(observation)
        report_observations.append(observation)
    if skipped_future_source_time:
        notes.append(
            f"report_rc rows skipped because create_time exceeded retrieval: "
            f"{skipped_future_source_time}"
        )

    guidance_observations: Dict[str, List[Dict[str, Any]]] = {code: [] for code in codes}
    guidance_status_by_code: Dict[str, Dict[str, Any]] = {}
    for code in codes:
        result = dict(forecasts_by_code.get(code) or {})
        status = _query_status_value(result)
        query = result.get("query") or {}
        status_ref = (
            f"tushare.forecast:query:{code}:"
            f"{query.get('start_date')}:{query.get('end_date')}"
        )
        status_observation = _observation(
            entity_type="stock",
            entity_id=code,
            field="company_guidance_query",
            value=status,
            effective_date=as_of,
            available_at=retrieved_iso,
            retrieved_at=retrieved_iso,
            source=GUIDANCE_SOURCE,
            source_ref=status_ref,
            revision_id=canonical_digest(status),
            existing=existing,
        )
        observations.append(status_observation)
        guidance_status_by_code[code] = status_observation
        if not (result.get("available") and result.get("complete")):
            continue
        for raw in result.get("rows") or []:
            row = _json_value(raw)
            if _code(row.get("ts_code")) != code:
                notes.append(f"{code} forecast row identity mismatch; row skipped")
                continue
            try:
                end_date = _trade_date(row.get("end_date"), "forecast.end_date")
                ann_date = _trade_date(row.get("ann_date"), "forecast.ann_date")
            except ContractError:
                notes.append(f"{code} forecast row has invalid dates; row skipped")
                continue
            row["end_date"] = end_date
            row["ann_date"] = ann_date
            source_key = {
                key: row.get(key)
                for key in (
                    "ts_code", "end_date", "first_ann_date", "ann_date", "type",
                )
            }
            source_ref = (
                f"tushare.forecast:{code}:"
                f"{canonical_digest(source_key)[:24]}"
            )
            revision_id = canonical_digest(row)
            identity = (GUIDANCE_SOURCE, source_ref, revision_id)
            available_at = (
                str(existing[identity]["available_at"])
                if identity in existing
                else retrieved_iso
            )
            observation = _observation(
                entity_type="stock",
                entity_id=code,
                field="company_guidance",
                value=row,
                effective_date=end_date,
                available_at=available_at,
                retrieved_at=retrieved_iso,
                source=GUIDANCE_SOURCE,
                source_ref=source_ref,
                revision_id=revision_id,
                existing=existing,
            )
            observations.append(observation)
            guidance_observations[code].append(observation)

    daily_observations: Dict[str, Dict[str, Any]] = {}
    daily_status_by_code: Dict[str, Dict[str, Any]] = {}
    for code in codes:
        result = dict(daily_basic_by_code.get(code) or {})
        rows = list(result.get("rows") or [])
        row = _json_value(rows[0]) if len(rows) == 1 else None
        valid = bool(
            result.get("available")
            and result.get("complete")
            and len(rows) == 1
            and isinstance(row, dict)
            and _code(row.get("ts_code")) == code
            and str(row.get("trade_date") or "") == previous
            and (_number(row.get("close")) or 0.0) > 0
        )
        status = _query_status_value(result)
        status.update({
            "anchor_valid": valid,
            "anchor_reason": None if valid else "missing_invalid_or_stale_daily_basic",
            "required_trade_date": previous,
            "actual_trade_date": row.get("trade_date") if isinstance(row, dict) else None,
            "raw_fields": sorted(row) if isinstance(row, dict) else [],
        })
        status_observation = _observation(
            entity_type="stock",
            entity_id=code,
            field="daily_basic_query",
            value=status,
            effective_date=previous,
            available_at=retrieved_iso,
            retrieved_at=retrieved_iso,
            source=DAILY_BASIC_SOURCE,
            source_ref=f"tushare.daily_basic:query:{code}:{previous}",
            revision_id=canonical_digest(status),
            existing=existing,
        )
        observations.append(status_observation)
        daily_status_by_code[code] = status_observation
        if not valid:
            continue
        anchor_value = {
            key: row.get(key)
            for key in ("ts_code", "trade_date", "close", "total_share", "pe_ttm", "total_mv")
        }
        available_at = datetime.combine(
            datetime.strptime(previous, "%Y%m%d").date(),
            time(17, 0),
            CHINA_TZ,
        ).isoformat()
        if _aware(available_at, "daily_basic available_at") > retrieved_dt:
            continue
        observation = _observation(
            entity_type="stock",
            entity_id=code,
            field="daily_basic_anchor",
            value=anchor_value,
            effective_date=previous,
            available_at=available_at,
            retrieved_at=retrieved_iso,
            source=DAILY_BASIC_SOURCE,
            source_ref=f"tushare.daily_basic:{code}:{previous}",
            revision_id=canonical_digest(anchor_value),
            existing=existing,
        )
        observations.append(observation)
        daily_observations[code] = observation

    all_available = {
        str(row["observation_id"]): row
        for row in [*historical, *observations]
        if _aware(row["available_at"], "available_at") <= retrieved_dt
    }
    as_of_date = datetime.strptime(as_of, "%Y%m%d").date()
    cutoff = (as_of_date - timedelta(days=CONSENSUS_WINDOW_DAYS)).strftime("%Y%m%d")
    required_report_end = (as_of_date - timedelta(days=1)).strftime("%Y%m%d")
    report_window_complete = _complete_report_window(
        report_result,
        required_start=cutoff,
        required_end=required_report_end,
    )
    if not report_window_complete:
        notes.append(
            "seller consensus factors skipped: complete global 90-calendar-day "
            "report_rc window was not proven"
        )

    usable_report_observations = []
    for observation in report_observations:
        report_date = str((observation.get("value") or {}).get("report_date") or "")
        if cutoff <= report_date <= required_report_end:
            usable_report_observations.append(observation)

    factors: List[Dict[str, Any]] = []
    factor_inputs: Dict[str, Mapping[str, Any]] = {}
    consensus_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if report_window_complete:
        grouped: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
        for observation in usable_report_observations:
            quarter = str((observation.get("value") or {}).get("quarter") or "").upper()
            if _quarter_end(quarter):
                grouped.setdefault((str(observation["entity_id"]), quarter), []).append(
                    observation
                )
        for (code, quarter), rows in sorted(grouped.items()):
            effective_date = _quarter_end(quarter)
            eps_values, eps_inputs, _ = _latest_per_org(rows, "eps")
            np_values, np_inputs, _ = _latest_per_org(rows, "np")
            pe_values, pe_inputs, _ = _latest_per_org(
                rows, "pe", positive_only=True
            )
            if not eps_values and not np_values:
                continue
            eps_median = float(median(eps_values)) if eps_values else None
            np_median = float(median(np_values)) if np_values else None
            consensus = {
                "eps": eps_median,
                "eps_inputs": eps_inputs,
                "eps_org_count": len(eps_values),
                "np": np_median,
                "np_inputs": np_inputs,
                "np_org_count": len(np_values),
                "report_count": len(rows),
                "pe": float(median(pe_values)) if pe_values else None,
                "pe_inputs": pe_inputs,
                "effective_date": effective_date,
            }
            consensus_by_key[(code, quarter)] = consensus
            if eps_values:
                for factor_id, value in (
                    (f"seller_consensus_eps_median_90d.{quarter}", eps_median),
                    (f"seller_consensus_eps_org_count_90d.{quarter}", len(eps_values)),
                ):
                    factors.append(_factor(
                        entity_id=code,
                        factor_id=factor_id,
                        factor_version=CONSENSUS_FACTOR_VERSION,
                        value=value,
                        as_of_trade_date=as_of,
                        effective_date=effective_date,
                        inputs=[report_status_observation, *eps_inputs],
                        calculated_at=retrieved_iso,
                    ))
            if np_values:
                for factor_id, value in (
                    (
                        f"seller_consensus_net_profit_median_wan_90d.{quarter}",
                        np_median,
                    ),
                    (
                        f"seller_consensus_net_profit_org_count_90d.{quarter}",
                        len(np_values),
                    ),
                ):
                    factors.append(_factor(
                        entity_id=code,
                        factor_id=factor_id,
                        factor_version=CONSENSUS_FACTOR_VERSION,
                        value=value,
                        as_of_trade_date=as_of,
                        effective_date=effective_date,
                        inputs=[report_status_observation, *np_inputs],
                        calculated_at=retrieved_iso,
                    ))
            factors.append(
                _factor(
                    entity_id=code,
                    factor_id=f"seller_report_row_count_90d.{quarter}",
                    factor_version=CONSENSUS_FACTOR_VERSION,
                    value=len(rows),
                    as_of_trade_date=as_of,
                    effective_date=effective_date,
                    inputs=[report_status_observation, *rows],
                    calculated_at=retrieved_iso,
                )
            )
            if pe_values:
                factors.append(
                    _factor(
                        entity_id=code,
                        factor_id=f"seller_reported_forward_pe_median_90d.{quarter}",
                        factor_version=CONSENSUS_FACTOR_VERSION,
                        value=consensus["pe"],
                        as_of_trade_date=as_of,
                        effective_date=effective_date,
                        inputs=[report_status_observation, *pe_inputs],
                        calculated_at=retrieved_iso,
                    )
                )

    for (code, quarter), consensus in sorted(consensus_by_key.items()):
        anchor = daily_observations.get(code)
        eps_value = consensus["eps"]
        pe_value = consensus["pe"]
        if anchor and pe_value and pe_value > 0 and eps_value and eps_value > 0:
            close = _number((anchor.get("value") or {}).get("close"))
            if close and close > 0:
                valuation_inputs = [
                    report_status_observation,
                    *consensus["eps_inputs"],
                    *consensus["pe_inputs"],
                    anchor,
                    daily_status_by_code[code],
                ]
                implied_eps = close / pe_value
                current_forward_pe = close / eps_value
                for factor_id, value in (
                    (
                        f"eps_required_at_seller_reported_pe_median.{quarter}",
                        implied_eps,
                    ),
                    (
                        f"current_forward_pe_from_seller_consensus_eps.{quarter}",
                        current_forward_pe,
                    ),
                    (
                        f"current_forward_pe_vs_seller_reported_pe_gap_pct.{quarter}",
                        (current_forward_pe / pe_value - 1.0) * 100.0,
                    ),
                ):
                    factors.append(
                        _factor(
                            entity_id=code,
                            factor_id=factor_id,
                            factor_version=VALUATION_GAP_FACTOR_VERSION,
                            value=value,
                            as_of_trade_date=as_of,
                            effective_date=consensus["effective_date"],
                            inputs=valuation_inputs,
                            calculated_at=retrieved_iso,
                        )
                    )

    for code, guidance_rows in sorted(guidance_observations.items()):
        by_period: Dict[str, List[Mapping[str, Any]]] = {}
        for observation in guidance_rows:
            by_period.setdefault(str(observation["effective_date"]), []).append(observation)
        for period, period_rows in sorted(by_period.items()):
            latest_ann = max(
                str((row.get("value") or {}).get("ann_date") or "")
                for row in period_rows
            )
            latest = [
                row for row in period_rows
                if str((row.get("value") or {}).get("ann_date") or "") == latest_ann
            ]
            revisions = {str(row.get("revision_id")) for row in latest}
            if len(revisions) != 1:
                notes.append(
                    f"{code}/{period} guidance has conflicting latest revisions; factor skipped"
                )
                continue
            guidance = latest[0]
            value = guidance.get("value") or {}
            low = _number(value.get("net_profit_min"))
            high = _number(value.get("net_profit_max"))
            if low is None or high is None:
                continue
            profit_mid = (low + high) / 2.0
            guidance_status = guidance_status_by_code.get(code)
            if guidance_status is None:
                notes.append(f"{code}/{period} guidance query status unavailable; factor skipped")
                continue
            factors.append(
                _factor(
                    entity_id=code,
                    factor_id=f"guidance_net_profit_mid_wan.{period}",
                    factor_version=GUIDANCE_FACTOR_VERSION,
                    value=profit_mid,
                    as_of_trade_date=as_of,
                    effective_date=period,
                    inputs=[guidance_status, guidance],
                    calculated_at=retrieved_iso,
                )
            )
            preannouncement_rows = []
            if report_window_complete:
                preannouncement_rows = [
                    observation
                    for observation in usable_report_observations
                    if observation.get("entity_id") == code
                    and _quarter_end((observation.get("value") or {}).get("quarter")) == period
                    and str((observation.get("value") or {}).get("report_date") or "")
                    < latest_ann
                    and _available_before_announcement(observation, latest_ann)
                ]
            pre_values, pre_inputs, _ = _latest_per_org(
                preannouncement_rows, "np"
            )
            if pre_values:
                pre_profit = float(median(pre_values))
                factors.append(
                    _factor(
                        entity_id=code,
                        factor_id=(
                            f"preannouncement_seller_net_profit_median_wan."
                            f"{period}.{latest_ann}"
                        ),
                        factor_version=GUIDANCE_FACTOR_VERSION,
                        value=pre_profit,
                        as_of_trade_date=as_of,
                        effective_date=period,
                        inputs=[report_status_observation, *pre_inputs],
                        calculated_at=retrieved_iso,
                    )
                )
            else:
                pre_profit = None
            if pre_profit and pre_profit > 0:
                factors.append(
                    _factor(
                        entity_id=code,
                        factor_id=(
                            f"guidance_vs_preannouncement_seller_net_profit_gap_pct."
                            f"{period}.{latest_ann}"
                        ),
                        factor_version=GUIDANCE_FACTOR_VERSION,
                        value=(profit_mid / pre_profit - 1.0) * 100.0,
                        as_of_trade_date=as_of,
                        effective_date=period,
                        inputs=[
                            guidance_status,
                            guidance,
                            report_status_observation,
                            *pre_inputs,
                        ],
                        calculated_at=retrieved_iso,
                    )
                )

    unique_observations: Dict[str, Dict[str, Any]] = {}
    for observation in observations:
        unique_observations[str(observation["observation_id"])] = observation
    observations = list(unique_observations.values())

    for factor in factors:
        for observation_id in factor["input_observation_ids"]:
            factor_inputs[observation_id] = all_available[observation_id]
    current_ids = sorted({str(row["observation_id"]) for row in observations})
    factor_input_ids = sorted(factor_inputs)
    input_digest = canonical_digest(
        {
            "current_observation_ids": current_ids,
            "factor_input_observation_ids": factor_input_ids,
        }
    )
    manifest = {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": "",
        "mode": mode,
        "as_of_trade_date": as_of,
        "universe_id": f"user_universe_{canonical_digest(codes)[:16]}",
        "feature_set_version": FEATURE_SET_VERSION,
        "group_version": NOT_EXECUTED,
        "select_version": NOT_EXECUTED,
        "forecast_version": NOT_EXECUTED,
        "input_digest": input_digest,
        "generated_at": retrieved_iso,
        "notes": notes,
        "stage": "expectation_refresh",
        "source_refs": [REPORT_DOC, GUIDANCE_DOC, DAILY_BASIC_DOC],
        "observation_count": len(observations),
        "factor_value_count": len(factors),
        "observation_digest": canonical_digest(current_ids),
        "factor_value_digest": canonical_digest(
            sorted(row["factor_value_id"] for row in factors)
        ),
        "factor_input_observation_count": len(factor_input_ids),
        "factor_input_observation_digest": canonical_digest(factor_input_ids),
    }
    manifest["run_id"] = make_run_id(manifest)
    summary = {
        "as_of_trade_date": as_of,
        "previous_trade_date": previous,
        "universe_count": len(codes),
        "report_source_available": bool(report_result.get("available")),
        "report_source_complete": bool(report_result.get("complete")),
        "report_window_complete": report_window_complete,
        "report_required_start": cutoff,
        "report_required_end": required_report_end,
        "report_rows_in_universe": len(report_observations),
        "consensus_stock_quarters": len(consensus_by_key),
        "guidance_rows": sum(len(rows) for rows in guidance_observations.values()),
        "daily_basic_anchors": len(daily_observations),
        "observations": len(observations),
        "factors": len(factors),
    }
    return manifest, observations, factors, summary
