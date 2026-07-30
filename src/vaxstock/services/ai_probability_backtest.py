# -*- coding: utf-8 -*-
"""Run a full daily walk-forward backtest on one frozen AI dataset.

This is an offline research entry point.  It performs no network access and
never mutates the content-addressed raw dataset.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import numpy as np
import pandas as pd

from vaxstock import config
from vaxstock.research.ai_historical_probability import (
    DAILY_BACKTEST_VERSION,
    MODEL_VERSION,
    build_ai_track_panel,
    run_daily_walk_forward_backtest,
)
from vaxstock.research.contracts import canonical_digest


logger = logging.getLogger(__name__)
DEFAULT_OUTPUT_DIR = (
    config.STATE_DIR / "research" / "ai_historical_probability"
)


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


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y%m%d")
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(child) for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(child) for child in value]
    return value


def _immutable_json(path: Path, payload: Mapping[str, Any]) -> str:
    target = Path(path)
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
    if target.exists():
        if target.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"immutable backtest output changed: {target}")
        return "already_complete"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return "written"


def _load_frozen_dataset(dataset_dir: Path) -> tuple[
    list[Dict[str, Any]],
    list[Dict[str, Any]],
    list[Dict[str, Any]],
    Dict[str, Any],
]:
    root = Path(dataset_dir)
    manifest = json.loads((root / "manifest.json").read_text(
        encoding="utf-8"
    ))
    stocks = _read_jsonl(root / "cn_stocks.jsonl")
    benchmark = _read_jsonl(root / "benchmark.jsonl")
    anchors = _read_jsonl(root / "anchors.jsonl")
    expected_digest = str(manifest.get("dataset_digest") or "")
    actual_digest = canonical_digest({
        "stock_rows": stocks,
        "benchmark_rows": benchmark,
        "anchor_rows": anchors,
        "universe": manifest.get("universe") or [],
    })
    if not expected_digest or actual_digest != expected_digest:
        raise RuntimeError(f"dataset digest mismatch: {root}")
    return stocks, benchmark, anchors, manifest


def run_ai_probability_backtest(
    *,
    dataset_dir: Path,
    output_dir: Optional[Path] = None,
    horizon: int = 20,
    target_kind: str = "excess",
    start_trade_date: Optional[str] = None,
    end_trade_date: Optional[str] = None,
    bootstrap_repetitions: int = 1000,
) -> Dict[str, Any]:
    """Build and persist an immutable day-by-day walk-forward report."""

    dataset_root = Path(dataset_dir)
    stocks, benchmark, anchors, manifest = _load_frozen_dataset(
        dataset_root
    )
    configured_codes = [
        str(row["code"]).zfill(6)
        for row in manifest.get("universe") or []
        if row.get("code")
    ]
    if len(configured_codes) < 5:
        raise RuntimeError("dataset universe has fewer than five members")
    dataset_digest = str(manifest["dataset_digest"])
    run_spec = {
        "backtest_version": DAILY_BACKTEST_VERSION,
        "model_version": MODEL_VERSION,
        "dataset_digest": dataset_digest,
        "horizon": int(horizon),
        "target_kind": str(target_kind),
        "start_trade_date": start_trade_date,
        "end_trade_date": end_trade_date,
        "bootstrap_repetitions": int(bootstrap_repetitions),
    }
    run_spec_digest = canonical_digest(run_spec)
    root = Path(output_dir or DEFAULT_OUTPUT_DIR)
    output_path = root / "backtests" / (
        f"ai_daily_T{int(horizon)}_{target_kind}"
        f"__{MODEL_VERSION}__{dataset_digest[:12]}"
        f"__{run_spec_digest[:10]}.json"
    )
    if output_path.exists():
        stored = json.loads(output_path.read_text(encoding="utf-8"))
        if stored.get("run_spec") != run_spec:
            raise RuntimeError(
                f"stored backtest run spec mismatch: {output_path}"
            )
        return {
            "status": "complete",
            "write_status": "already_complete",
            "output_path": str(output_path),
            "report_digest": stored["report_digest"],
            "summary": {
                key: stored.get(key)
                for key in (
                    "attempted_daily_dates",
                    "estimated_daily_predictions",
                    "settled_daily_predictions",
                    "pending_daily_predictions",
                    "cohort_stability",
                    "overall_daily_dependent_metrics",
                    "moving_block_bootstrap",
                )
            },
        }

    logger.info("building T+%s AI historical panel", int(horizon))
    panel, panel_audit = build_ai_track_panel(
        stock_rows=stocks,
        benchmark_rows=benchmark,
        anchor_rows=anchors,
        universe_codes=configured_codes,
        horizons=[int(horizon)],
    )

    last_logged = {"value": 0}

    def progress(current: int, total: int, trade_date: str) -> None:
        if (
            current == 1
            or current == total
            or current - last_logged["value"] >= 25
        ):
            logger.info(
                "daily walk-forward %s/%s (%s)",
                current,
                total,
                trade_date,
            )
            last_logged["value"] = current

    report = run_daily_walk_forward_backtest(
        panel,
        horizon=int(horizon),
        target_kind=str(target_kind),
        start_trade_date=start_trade_date,
        end_trade_date=end_trade_date,
        bootstrap_repetitions=int(bootstrap_repetitions),
        progress=progress,
    )
    report["run_spec"] = run_spec
    report["input_dataset_digest"] = dataset_digest
    report["input_dataset_dir"] = str(dataset_root)
    report["panel_audit"] = panel_audit
    report["production_eligible"] = False
    report["report_digest"] = canonical_digest(report)
    write_status = _immutable_json(output_path, report)
    return {
        "status": "complete",
        "write_status": write_status,
        "output_path": str(output_path),
        "report_digest": report["report_digest"],
        "summary": {
            key: report.get(key)
            for key in (
                "attempted_daily_dates",
                "estimated_daily_predictions",
                "settled_daily_predictions",
                "pending_daily_predictions",
                "cohort_stability",
                "overall_daily_dependent_metrics",
                "moving_block_bootstrap",
            )
        },
    }


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description=(
            "Run a full day-by-day AI probability walk-forward backtest "
            "from an immutable historical dataset"
        )
    )
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument(
        "--target-kind",
        choices=("absolute", "excess"),
        default="excess",
    )
    parser.add_argument("--start-trade-date")
    parser.add_argument("--end-trade-date")
    parser.add_argument("--bootstrap-repetitions", type=int, default=1000)
    args = parser.parse_args(argv)
    result = run_ai_probability_backtest(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        horizon=args.horizon,
        target_kind=args.target_kind,
        start_trade_date=args.start_trade_date,
        end_trade_date=args.end_trade_date,
        bootstrap_repetitions=args.bootstrap_repetitions,
    )
    print(json.dumps(
        _json_value(result),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    ), flush=True)
    return 0 if result.get("status") == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
