# -*- coding: utf-8 -*-
"""Run the immutable v2 nested AI probability backtest offline."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from vaxstock import config
from vaxstock.research.ai_historical_probability import build_ai_track_panel
from vaxstock.research.ai_probability_v2 import (
    BACKTEST_VERSION,
    MODEL_VERSION,
    run_v2_daily_backtest,
)
from vaxstock.research.contracts import canonical_digest
from vaxstock.services.ai_probability_backtest import (
    _immutable_json,
    _json_value,
    _load_frozen_dataset,
)


logger = logging.getLogger(__name__)
DEFAULT_OUTPUT_DIR = (
    config.STATE_DIR / "research" / "ai_historical_probability"
)


def run_ai_probability_backtest_v2(
    *,
    dataset_dir: Path,
    output_dir: Optional[Path] = None,
    horizon: int = 20,
    bootstrap_repetitions: int = 1000,
) -> Dict[str, Any]:
    stocks, benchmark, anchors, manifest = _load_frozen_dataset(dataset_dir)
    codes = [
        str(row["code"]).zfill(6)
        for row in manifest.get("universe") or []
        if row.get("code")
    ]
    if len(codes) < 5:
        raise RuntimeError("dataset universe has fewer than five members")
    dataset_digest = str(manifest["dataset_digest"])
    run_spec = {
        "backtest_version": BACKTEST_VERSION,
        "model_version": MODEL_VERSION,
        "dataset_digest": dataset_digest,
        "horizon": int(horizon),
        "bootstrap_repetitions": int(bootstrap_repetitions),
    }
    run_spec_digest = canonical_digest(run_spec)
    root = Path(output_dir or DEFAULT_OUTPUT_DIR)
    output_path = root / "backtests" / (
        f"ai_daily_T{int(horizon)}_excess"
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
            "publication_gate": stored["publication_gate"],
            "overall_nested_metrics": stored["overall_nested_metrics"],
        }

    panel, panel_audit = build_ai_track_panel(
        stock_rows=stocks,
        benchmark_rows=benchmark,
        anchor_rows=anchors,
        universe_codes=codes,
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
                "v2 nested walk-forward %s/%s (%s)",
                current,
                total,
                trade_date,
            )
            last_logged["value"] = current

    report = run_v2_daily_backtest(
        panel,
        horizon=int(horizon),
        bootstrap_repetitions=int(bootstrap_repetitions),
        progress=progress,
    )
    report["run_spec"] = run_spec
    report["input_dataset_digest"] = dataset_digest
    report["input_dataset_dir"] = str(Path(dataset_dir))
    report["panel_audit"] = panel_audit
    report["production_eligible"] = bool(
        report["publication_gate"]["publish_numeric_probability"]
    )
    report["report_digest"] = canonical_digest(report)
    write_status = _immutable_json(output_path, report)
    return {
        "status": "complete",
        "write_status": write_status,
        "output_path": str(output_path),
        "report_digest": report["report_digest"],
        "publication_gate": report["publication_gate"],
        "overall_nested_metrics": report["overall_nested_metrics"],
    }


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description=(
            "Run v2 nested daily AI benchmark-excess probability backtest"
        )
    )
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--bootstrap-repetitions", type=int, default=1000)
    args = parser.parse_args(argv)
    result = run_ai_probability_backtest_v2(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        horizon=args.horizon,
        bootstrap_repetitions=args.bootstrap_repetitions,
    )
    print(json.dumps(
        _json_value(result),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    ), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

