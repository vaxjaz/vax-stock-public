# -*- coding: utf-8 -*-
"""Collect historical AI market data and materialize probability research.

The service is an explicit offline/replay entry point.  It does not read or
write the legacy A/B/C/D evidence lines and is not wired to EOD or intraday
actions in v1.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from vaxstock import config
from vaxstock.research.ai_historical_probability import (
    ANCHOR_SYMBOLS,
    DEFAULT_HORIZONS,
    MODEL_VERSION,
    build_ai_probability_forecast,
    build_ai_stock_panels,
    build_ai_stock_probability_forecasts,
    build_ai_track_panel,
)
from vaxstock.research.contracts import canonical_digest
from vaxstock.sources.tushare_src import TushareSource
from vaxstock.sources.us_market import fetch_us_market_history
from vaxstock.tracks.ai import AIDC_BASKET


CHINA_TZ = timezone(timedelta(hours=8))
DEFAULT_BENCHMARK = "000300.SH"
DEFAULT_OUTPUT_DIR = (
    config.STATE_DIR / "research" / "ai_historical_probability"
)


def _trade_date(value: Any, field: str) -> str:
    text = str(value or "").strip()
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYYMMDD") from exc
    return text


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y%m%d")
    if isinstance(value, Mapping):
        return {str(key): _json_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(child) for child in value]
    return value


def _records(frame: pd.DataFrame, sort_fields: Sequence[str]) -> list[Dict[str, Any]]:
    output = []
    sorted_frame = frame.sort_values(list(sort_fields)).reset_index(drop=True)
    for raw in sorted_frame.to_dict("records"):
        output.append({str(key): _json_value(value) for key, value in raw.items()})
    return output


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = (
        json.dumps(
            _json_value(dict(payload)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, target)


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> str:
    target = Path(path)
    expected = (
        json.dumps(
            _json_value(dict(payload)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )
    if target.exists():
        if target.read_text(encoding="utf-8") != expected:
            raise RuntimeError(f"immutable probability output changed: {target}")
        return "already_complete"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(expected)
        handle.flush()
        os.fsync(handle.fileno())
    return "written"


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    target = Path(path)
    content = "".join(
        json.dumps(
            _json_value(dict(row)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
        for row in rows
    )
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, target)


def _read_jsonl(path: Path) -> list[Dict[str, Any]]:
    rows = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            if not isinstance(row, dict):
                raise RuntimeError(
                    f"JSONL row is not an object: {path}:{line_number}"
                )
            rows.append(row)
    return rows


def _ai_universe() -> list[Dict[str, str]]:
    rows = []
    for raw in AIDC_BASKET:
        ts_code = str(raw.get("code") or "").strip()
        if not ts_code:
            continue
        rows.append({
            "code": ts_code.split(".")[0].zfill(6),
            "ts_code": ts_code,
            "name": str(raw.get("name") or ""),
            "segment": str(raw.get("seg") or ""),
            "trade_board": str(raw.get("trade") or ""),
        })
    unique = {row["code"]: row for row in rows}
    return [unique[code] for code in sorted(unique)]


def _collect_cn_stock_history(
    source: Any,
    *,
    universe: Sequence[Mapping[str, str]],
    start_date: str,
    end_date: str,
    force_refresh: bool,
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    output: list[Dict[str, Any]] = []
    audit = {
        "requested_codes": len(universe),
        "complete_codes": [],
        "excluded_codes": [],
        "daily_basic_missing_codes": [],
        "source_refs": {
            "daily": "https://tushare.pro/document/2?doc_id=27",
            "daily_basic": "https://tushare.pro/document/2?doc_id=32",
            "adj_factor": "https://tushare.pro/document/2?doc_id=28",
        },
    }
    for member in universe:
        code = member["code"]
        daily = source.get_daily_history_range(
            code,
            start_date=start_date,
            end_date=end_date,
            force_refresh=force_refresh,
        )
        adjustment = source.get_adj_factor_history_range(
            code,
            start_date=start_date,
            end_date=end_date,
            force_refresh=force_refresh,
        )
        if not daily or not adjustment:
            audit["excluded_codes"].append({
                "code": code,
                "reason": (
                    "daily_missing" if not daily else "adj_factor_missing"
                ),
            })
            continue
        basic = source.get_daily_basic_history_range(
            code,
            start_date=start_date,
            end_date=end_date,
            force_refresh=force_refresh,
        )
        if not basic:
            audit["daily_basic_missing_codes"].append(code)
            basic = []
        daily_frame = pd.DataFrame(daily)
        factor_frame = pd.DataFrame(adjustment)
        required_daily = {"ts_code", "trade_date", "close"}
        required_factor = {"ts_code", "trade_date", "adj_factor"}
        if not required_daily.issubset(daily_frame.columns):
            audit["excluded_codes"].append({
                "code": code,
                "reason": "daily_contract_invalid",
            })
            continue
        if not required_factor.issubset(factor_frame.columns):
            audit["excluded_codes"].append({
                "code": code,
                "reason": "adj_factor_contract_invalid",
            })
            continue
        merged = daily_frame.merge(
            factor_frame[["ts_code", "trade_date", "adj_factor"]],
            on=["ts_code", "trade_date"],
            how="inner",
            validate="one_to_one",
        )
        if basic:
            basic_frame = pd.DataFrame(basic)
            basic_fields = [
                field for field in (
                    "ts_code",
                    "trade_date",
                    "turnover_rate",
                    "volume_ratio",
                    "pe",
                    "pe_ttm",
                    "pb",
                    "ps",
                    "ps_ttm",
                    "total_mv",
                    "circ_mv",
                )
                if field in basic_frame
            ]
            if {"ts_code", "trade_date"}.issubset(basic_fields):
                merged = merged.merge(
                    basic_frame[basic_fields],
                    on=["ts_code", "trade_date"],
                    how="left",
                    validate="one_to_one",
                )
        merged["code"] = code
        merged["adj_close"] = (
            pd.to_numeric(merged["close"], errors="coerce")
            * pd.to_numeric(merged["adj_factor"], errors="coerce")
        )
        merged = merged[
            merged["adj_close"].notna() & (merged["adj_close"] > 0)
        ]
        if merged.empty:
            audit["excluded_codes"].append({
                "code": code,
                "reason": "no_valid_adjusted_close",
            })
            continue
        output.extend(_records(merged, ("trade_date", "code")))
        audit["complete_codes"].append(code)
    audit["complete_codes"] = sorted(audit["complete_codes"])
    audit["daily_basic_missing_codes"] = sorted(
        audit["daily_basic_missing_codes"]
    )
    audit["rows"] = len(output)
    return output, audit


def _collect_benchmark_history(
    source: Any,
    *,
    benchmark: str,
    start_date: str,
    end_date: str,
    force_refresh: bool,
) -> list[Dict[str, Any]]:
    rows = source.get_index_daily_history_range(
        benchmark,
        start_date=start_date,
        end_date=end_date,
        force_refresh=force_refresh,
    )
    if not rows:
        raise RuntimeError(f"benchmark history unavailable: {benchmark}")
    frame = pd.DataFrame(rows)
    if not {"trade_date", "close"}.issubset(frame.columns):
        raise RuntimeError("benchmark history contract invalid")
    frame["adj_close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame[frame["adj_close"].notna() & (frame["adj_close"] > 0)]
    if frame.empty:
        raise RuntimeError("benchmark has no valid closes")
    return _records(frame, ("trade_date",))


def _dataset_digest(
    stock_rows: Sequence[Mapping[str, Any]],
    benchmark_rows: Sequence[Mapping[str, Any]],
    anchor_rows: Sequence[Mapping[str, Any]],
    universe: Sequence[Mapping[str, Any]],
) -> str:
    return canonical_digest({
        "stock_rows": list(stock_rows),
        "benchmark_rows": list(benchmark_rows),
        "anchor_rows": list(anchor_rows),
        "universe": list(universe),
    })


def _write_dataset(
    *,
    output_dir: Path,
    digest: str,
    stock_rows: Sequence[Mapping[str, Any]],
    benchmark_rows: Sequence[Mapping[str, Any]],
    anchor_rows: Sequence[Mapping[str, Any]],
    universe: Sequence[Mapping[str, Any]],
    source_audit: Mapping[str, Any],
    start_date: str,
    end_date: str,
) -> Path:
    dataset_dir = Path(output_dir) / "datasets" / digest
    manifest_path = dataset_dir / "manifest.json"
    manifest = {
        "schema_version": 1,
        "dataset_digest": digest,
        "start_date": start_date,
        "end_date": end_date,
        "stock_rows": len(stock_rows),
        "benchmark_rows": len(benchmark_rows),
        "anchor_rows": len(anchor_rows),
        "universe": list(universe),
        "source_audit": dict(source_audit),
    }
    if manifest_path.exists():
        stored = json.loads(manifest_path.read_text(encoding="utf-8"))
        if stored != _json_value(manifest):
            raise RuntimeError(f"dataset manifest conflict: {manifest_path}")
        return dataset_dir
    dataset_dir.parent.mkdir(parents=True, exist_ok=True)
    if dataset_dir.exists():
        raise RuntimeError(
            f"incomplete dataset directory already exists: {dataset_dir}"
        )
    temporary = Path(tempfile.mkdtemp(
        prefix=f".{digest}.",
        dir=dataset_dir.parent,
    ))
    _write_jsonl(temporary / "cn_stocks.jsonl", stock_rows)
    _write_jsonl(temporary / "benchmark.jsonl", benchmark_rows)
    _write_jsonl(temporary / "anchors.jsonl", anchor_rows)
    _atomic_json(temporary / "manifest.json", manifest)
    os.replace(temporary, dataset_dir)
    return dataset_dir


def load_dataset(dataset_dir: Path) -> tuple[
    list[Dict[str, Any]],
    list[Dict[str, Any]],
    list[Dict[str, Any]],
    Dict[str, Any],
]:
    root = Path(dataset_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    stock_rows = _read_jsonl(root / "cn_stocks.jsonl")
    benchmark_rows = _read_jsonl(root / "benchmark.jsonl")
    anchor_rows = _read_jsonl(root / "anchors.jsonl")
    digest = _dataset_digest(
        stock_rows,
        benchmark_rows,
        anchor_rows,
        manifest["universe"],
    )
    if digest != manifest["dataset_digest"]:
        raise RuntimeError(f"dataset digest mismatch: {root}")
    return stock_rows, benchmark_rows, anchor_rows, manifest


def run_ai_probability_refresh(
    *,
    start_date: str,
    end_date: str,
    output_dir: Optional[Path] = None,
    source: Optional[Any] = None,
    anchor_fetcher: Callable[..., Optional[list[Dict[str, Any]]]] = (
        fetch_us_market_history
    ),
    force_refresh: bool = False,
    run_validation: bool = True,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    dataset_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Collect or load immutable history, then write a deterministic forecast."""

    start = _trade_date(start_date, "start_date")
    end = _trade_date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date cannot be after end_date")
    root = Path(output_dir or DEFAULT_OUTPUT_DIR)
    universe = _ai_universe()
    if dataset_dir:
        stocks, benchmark, anchors, dataset_manifest = load_dataset(dataset_dir)
        dataset_digest = dataset_manifest["dataset_digest"]
        source_audit = dataset_manifest.get("source_audit") or {}
        stored_dataset_dir = Path(dataset_dir)
    else:
        market_source = source or TushareSource(
            token=config.SECRETS.get("tushare_token")
        )
        if not getattr(market_source, "enabled", True):
            return {
                "status": "blocked",
                "reason": "tushare_source_unavailable",
            }
        stocks, cn_audit = _collect_cn_stock_history(
            market_source,
            universe=universe,
            start_date=start,
            end_date=end,
            force_refresh=force_refresh,
        )
        if len(cn_audit["complete_codes"]) < 5:
            return {
                "status": "blocked",
                "reason": "insufficient_ai_stock_histories",
                "source_audit": cn_audit,
            }
        benchmark = _collect_benchmark_history(
            market_source,
            benchmark=DEFAULT_BENCHMARK,
            start_date=start,
            end_date=end,
            force_refresh=force_refresh,
        )
        anchors = anchor_fetcher(
            symbols=ANCHOR_SYMBOLS,
            start_date=start,
            end_date=end,
        )
        if not anchors:
            return {
                "status": "blocked",
                "reason": "overseas_anchor_history_unavailable",
                "source_audit": cn_audit,
            }
        source_audit = {
            "cn_stocks": cn_audit,
            "benchmark": {
                "code": DEFAULT_BENCHMARK,
                "rows": len(benchmark),
                "source_ref": (
                    "https://tushare.pro/document/2?doc_id=95"
                ),
            },
            "anchors": {
                "symbols": list(ANCHOR_SYMBOLS),
                "rows": len(anchors),
                "source": "yfinance.download(auto_adjust=True)",
            },
        }
        dataset_digest = _dataset_digest(
            stocks, benchmark, anchors, universe
        )
        stored_dataset_dir = _write_dataset(
            output_dir=root,
            digest=dataset_digest,
            stock_rows=stocks,
            benchmark_rows=benchmark,
            anchor_rows=anchors,
            universe=universe,
            source_audit=source_audit,
            start_date=start,
            end_date=end,
        )

    configured_codes = [row["code"] for row in universe]
    run_spec = {
        "model_version": MODEL_VERSION,
        "dataset_digest": dataset_digest,
        "horizons": [int(value) for value in horizons],
        "run_validation": bool(run_validation),
    }
    run_spec_digest = canonical_digest(run_spec)
    actual_as_of = max(str(row["trade_date"]) for row in benchmark)
    forecast_path = root / "forecasts" / (
        f"ai_probability_{actual_as_of}"
        f"__{MODEL_VERSION}__{dataset_digest[:12]}"
        f"__{run_spec_digest[:10]}.json"
    )
    if forecast_path.exists():
        stored_forecast = json.loads(
            forecast_path.read_text(encoding="utf-8")
        )
        if stored_forecast.get("run_spec") != run_spec:
            raise RuntimeError(
                f"stored forecast run spec mismatch: {forecast_path}"
            )
        latest = {
            "schema_version": 1,
            "model_version": MODEL_VERSION,
            "as_of_trade_date": stored_forecast["as_of_trade_date"],
            "dataset_digest": dataset_digest,
            "forecast_digest": stored_forecast["forecast_digest"],
            "dataset_dir": str(stored_dataset_dir),
            "forecast_path": str(forecast_path),
            "updated_at": datetime.now(CHINA_TZ).isoformat(
                timespec="seconds"
            ),
        }
        _atomic_json(root / "latest.json", latest)
        return {
            "status": "complete",
            "write_status": "already_complete",
            "as_of_trade_date": stored_forecast["as_of_trade_date"],
            "dataset_digest": dataset_digest,
            "dataset_dir": str(stored_dataset_dir),
            "forecast_path": str(forecast_path),
            "member_count": stored_forecast["current_member_count"],
            "horizons": stored_forecast["horizons"],
            "production_eligible": False,
        }

    panel, panel_audit = build_ai_track_panel(
        stock_rows=stocks,
        benchmark_rows=benchmark,
        anchor_rows=anchors,
        universe_codes=configured_codes,
        horizons=horizons,
    )
    forecast = build_ai_probability_forecast(
        panel=panel,
        panel_audit=panel_audit,
        horizons=horizons,
        run_validation=run_validation,
    )
    stock_panels = build_ai_stock_panels(
        stock_rows=stocks,
        track_panel=panel,
        universe_codes=configured_codes,
        horizons=horizons,
    )
    stock_forecasts = build_ai_stock_probability_forecasts(
        stock_panels=stock_panels,
        as_of_trade_date=forecast["as_of_trade_date"],
        horizons=horizons,
    )
    universe_by_code = {row["code"]: row for row in universe}
    for code, row in stock_forecasts.items():
        definition = universe_by_code.get(code) or {}
        row["name"] = definition.get("name")
        row["segment"] = definition.get("segment")
        row["trade_board"] = definition.get("trade_board")
    forecast["stock_probabilities"] = stock_forecasts
    forecast["stock_probability_count"] = len(stock_forecasts)
    forecast["input_dataset_digest"] = dataset_digest
    forecast["run_spec"] = run_spec
    forecast["source_audit"] = source_audit
    forecast["data_boundary"] = {
        "requested_start_date": start,
        "requested_end_date": end,
        "actual_as_of_trade_date": forecast["as_of_trade_date"],
    }
    forecast_digest = canonical_digest(forecast)
    forecast["forecast_digest"] = forecast_digest
    write_status = _write_immutable_json(forecast_path, forecast)
    latest = {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "as_of_trade_date": forecast["as_of_trade_date"],
        "dataset_digest": dataset_digest,
        "forecast_digest": forecast_digest,
        "dataset_dir": str(stored_dataset_dir),
        "forecast_path": str(forecast_path),
        "updated_at": datetime.now(CHINA_TZ).isoformat(timespec="seconds"),
    }
    _atomic_json(root / "latest.json", latest)
    return {
        "status": "complete",
        "write_status": write_status,
        "as_of_trade_date": forecast["as_of_trade_date"],
        "dataset_digest": dataset_digest,
        "dataset_dir": str(stored_dataset_dir),
        "forecast_path": str(forecast_path),
        "member_count": forecast["current_member_count"],
        "horizons": forecast["horizons"],
        "production_eligible": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build AI probability research from historical raw data"
    )
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--end", required=True, help="YYYYMMDD")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dataset-dir", type=Path)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args(argv)
    result = run_ai_probability_refresh(
        start_date=args.start,
        end_date=args.end,
        output_dir=args.output_dir,
        dataset_dir=args.dataset_dir,
        force_refresh=args.force_refresh,
        run_validation=not args.skip_validation,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
