# -*- coding: utf-8 -*-
"""Pre-open E-dimension refresh for the full holdings + watchlist universe."""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Mapping, Optional

from vaxstock import config
from vaxstock.research.expectation_dimension import (
    DIMENSION,
    build_expectation_run,
)
from vaxstock.research.point_in_time_store import (
    StorePaths,
    append_run,
    default_store_paths,
    observations_as_of,
)
from vaxstock.services.curve_refresh import run_curve_refresh
from vaxstock.services.group_refresh import run_group_refresh
from vaxstock.sources.tushare_src import TushareSource


logger = logging.getLogger(__name__)
CHINA_TZ = timezone(timedelta(hours=8))
PREOPEN_CUTOFF = time(9, 25)
REPORT_LOOKBACK_DAYS = max(
    1, int(os.environ.get("EXPECTATION_REPORT_LOOKBACK_DAYS", "90"))
)
REPORT_MAX_PAGES = max(
    1, int(os.environ.get("EXPECTATION_REPORT_MAX_PAGES", "10"))
)


def _market_trade_context(source: Any, calendar_date: str) -> Dict[str, Any]:
    """Classify the calendar day and anchor open dates from Tushare trade_cal."""

    try:
        end = datetime.strptime(calendar_date, "%Y%m%d")
    except ValueError:
        return {"status": "unavailable", "reason": "invalid_calendar_date"}
    start = (end - timedelta(days=20)).strftime("%Y%m%d")
    safe_call = getattr(source, "_safe_call", None)
    if safe_call is None:
        return {"status": "unavailable", "reason": "trade_cal_adapter_missing"}
    df = safe_call("trade_cal", exchange="", start_date=start, end_date=calendar_date)
    if df is None:
        return {"status": "unavailable", "reason": "trade_cal_source_failed"}
    columns = {str(column) for column in getattr(df, "columns", [])}
    if not {"cal_date", "is_open"}.issubset(columns):
        return {"status": "unavailable", "reason": "trade_cal_fields_missing"}
    rows = df.sort_values("cal_date", ascending=True).to_dict("records")
    open_dates = []
    for row in rows:
        try:
            is_open = int(float(row.get("is_open")))
        except (TypeError, ValueError):
            is_open = 0
        cal_date = str(row.get("cal_date") or "").strip()
        if is_open == 1 and len(cal_date) == 8:
            open_dates.append(cal_date)
    if calendar_date not in open_dates:
        return {"status": "closed", "reason": "market_closed"}
    previous = [value for value in open_dates if value < calendar_date]
    if not previous:
        return {"status": "unavailable", "reason": "previous_open_day_missing"}
    return {
        "status": "open",
        "target_trade_date": calendar_date,
        "previous_trade_date": previous[-1],
    }


def _universe() -> Dict[str, str]:
    watchlist, _ = config.load_watchlist()
    holdings = config.load_holdings()
    names = {str(code): str(name or "") for code, name in watchlist.items()}
    for code, info in holdings.items():
        names[str(code)] = str((info or {}).get("name") or names.get(str(code)) or "")
    return names


def run_expectation_refresh(
    *,
    source: Optional[Any] = None,
    now: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    force_after_open: bool = False,
    paths: Optional[StorePaths] = None,
) -> Dict[str, Any]:
    """Collect and append one pre-open E run; never changes strategy actions."""

    current = now or datetime.now(CHINA_TZ)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must include timezone")
    current = current.astimezone(CHINA_TZ)
    if not force_after_open and current.time() >= PREOPEN_CUTOFF:
        return {
            "status": "blocked",
            "reason": "after_preopen_cutoff",
            "retrieved_at": current.isoformat(timespec="seconds"),
        }

    source = source or TushareSource(config.SECRETS.get("tushare_token"))
    calendar_date = current.strftime("%Y%m%d")
    trade_context = _market_trade_context(source, calendar_date)
    if trade_context["status"] != "open":
        return {
            "status": "blocked",
            "reason": trade_context["reason"],
            "calendar_date": calendar_date,
        }
    target_trade_date = str(trade_context["target_trade_date"])
    previous_trade_date = str(trade_context["previous_trade_date"])
    universe = _universe()
    if not universe:
        return {
            "status": "blocked",
            "reason": "empty_universe",
            "target_trade_date": target_trade_date,
        }

    target_date = datetime.strptime(target_trade_date, "%Y%m%d")
    report_start = (
        target_date - timedelta(days=REPORT_LOOKBACK_DAYS)
    ).strftime("%Y%m%d")
    report_end = (target_date - timedelta(days=1)).strftime("%Y%m%d")
    report_result = source.get_report_rc_window(
        start_date=report_start,
        end_date=report_end,
        page_limit=3000,
        max_pages=REPORT_MAX_PAGES,
        refresh_bucket=target_trade_date,
    )

    forecast_start = (
        datetime.strptime(target_trade_date, "%Y%m%d") - timedelta(days=400)
    ).strftime("%Y%m%d")
    forecasts_by_code: Dict[str, Mapping[str, Any]] = {}
    daily_basic_by_code: Dict[str, Mapping[str, Any]] = {}
    for code in sorted(universe):
        try:
            forecasts_by_code[code] = source.get_forecast_contract(
                code,
                start_date=forecast_start,
                end_date=target_trade_date,
                refresh_bucket=target_trade_date,
            )
        except Exception as exc:
            forecasts_by_code[code] = {
                "available": False,
                "complete": False,
                "reason": f"adapter_error:{type(exc).__name__}",
                "rows": [],
                "query": {
                    "ts_code": source.code_to_ts(code),
                    "start_date": forecast_start,
                    "end_date": target_trade_date,
                },
            }
        try:
            daily_basic_by_code[code] = source.get_daily_basic_contract(
                code,
                trade_date=previous_trade_date,
                refresh_bucket=target_trade_date,
            )
        except Exception as exc:
            daily_basic_by_code[code] = {
                "available": False,
                "complete": False,
                "reason": f"adapter_error:{type(exc).__name__}",
                "rows": [],
                "query": {
                    "ts_code": source.code_to_ts(code),
                    "trade_date": previous_trade_date,
                },
            }

    target_paths = paths or default_store_paths()
    completed = completed_at or datetime.now(CHINA_TZ)
    if completed.tzinfo is None or completed.utcoffset() is None:
        raise ValueError("completed_at must include timezone")
    completed = completed.astimezone(CHINA_TZ)
    if not force_after_open and completed.time() >= PREOPEN_CUTOFF:
        return {
            "status": "blocked",
            "reason": "collection_completed_after_preopen_cutoff",
            "started_at": current.isoformat(timespec="seconds"),
            "completed_at": completed.isoformat(timespec="seconds"),
        }
    retrieved_at = completed.isoformat(timespec="seconds")
    historical = observations_as_of(
        retrieved_at,
        paths=target_paths,
        entity_ids=[*universe, "CN-A"],
        dimensions=[DIMENSION],
    )
    manifest, observations, factors, summary = build_expectation_run(
        as_of_trade_date=target_trade_date,
        previous_trade_date=previous_trade_date,
        retrieved_at=retrieved_at,
        universe_codes=universe,
        report_result=report_result,
        forecasts_by_code=forecasts_by_code,
        daily_basic_by_code=daily_basic_by_code,
        existing_observations=historical,
        mode="live",
    )
    stored = append_run(
        manifest,
        observations,
        factors,
        paths=target_paths,
    )
    try:
        curve_result = run_curve_refresh(
            as_of_trade_date=target_trade_date,
            decision_at=(completed + timedelta(seconds=1)).isoformat(timespec="seconds"),
            mode="live",
            paths=target_paths,
        )
    except Exception as exc:
        logger.warning(
            "Expectation facts committed but causal curve refresh failed: %s",
            str(exc)[:160],
        )
        curve_result = {
            "status": "failed",
            "as_of_trade_date": target_trade_date,
            "reason": f"{type(exc).__name__}: {str(exc)[:160]}",
        }
    try:
        group_result = run_group_refresh(
            as_of_trade_date=target_trade_date,
            decision_at=(completed + timedelta(seconds=2)).isoformat(
                timespec="seconds"
            ),
            mode="live",
            paths=target_paths,
        )
    except Exception as exc:
        logger.warning(
            "Expectation facts committed but contextual group refresh failed: %s",
            str(exc)[:160],
        )
        group_result = {
            "status": "failed",
            "as_of_trade_date": target_trade_date,
            "reason": f"{type(exc).__name__}: {str(exc)[:160]}",
        }
    result = {
        "status": stored["status"],
        "run_id": stored["run_id"],
        "summary": summary,
        "stored": stored,
        "curve_refresh": curve_result,
        "group_refresh": group_result,
    }
    logger.info("Expectation refresh: %s", result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Refresh point-in-time E dimension")
    parser.add_argument(
        "--force-after-open",
        action="store_true",
        help="diagnostic/manual override; production timer must not use it",
    )
    args = parser.parse_args(argv)
    result = run_expectation_refresh(force_after_open=args.force_after_open)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result.get("status") in {"written", "already_complete"}:
        return 0
    if result.get("reason") in {
        "market_closed",
        "after_preopen_cutoff",
        "collection_completed_after_preopen_cutoff",
    }:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
