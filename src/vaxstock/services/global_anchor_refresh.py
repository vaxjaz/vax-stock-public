# -*- coding: utf-8 -*-
"""Explicit live/replay orchestration for Research v2 global anchors."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from vaxstock import config
from vaxstock.research.global_anchor_dimension import (
    ANCHOR_CONTEXT_ENTITY_ID,
    ANCHORS,
    DIMENSION,
    build_global_anchor_run,
)
from vaxstock.research.point_in_time_store import (
    StorePaths,
    append_run,
    append_runs,
    default_store_paths,
    observations_as_of,
)


logger = logging.getLogger(__name__)
CHINA_TZ = timezone(timedelta(hours=8))


def _aware_china(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=CHINA_TZ)
    return parsed.astimezone(CHINA_TZ)


def run_global_anchor_refresh(
    *,
    as_of_trade_date: str,
    us_market: Mapping[str, Any],
    retrieved_at: Optional[str] = None,
    mode: str = "live",
    paths: Optional[StorePaths] = None,
) -> Dict[str, Any]:
    """Append one F-dimension anchor run from an already collected payload."""

    target_paths = paths or default_store_paths()
    retrieved = (
        _aware_china(retrieved_at, "retrieved_at")
        if retrieved_at
        else datetime.now(CHINA_TZ)
    )
    retrieved_iso = retrieved.isoformat(timespec="seconds")
    entity_ids = [
        ANCHOR_CONTEXT_ENTITY_ID,
        *(definition["symbol"] for definition in ANCHORS.values()),
    ]
    historical = observations_as_of(
        retrieved_iso,
        paths=target_paths,
        entity_ids=entity_ids,
        dimensions=[DIMENSION],
    )
    manifest, observations, factors, summary = build_global_anchor_run(
        as_of_trade_date=str(as_of_trade_date),
        retrieved_at=retrieved_iso,
        us_market=us_market,
        existing_observations=historical,
        mode=mode,
    )
    stored = append_run(
        manifest,
        observations,
        factors,
        paths=target_paths,
    )
    result = {
        "status": stored["status"],
        "run_id": stored["run_id"],
        "summary": summary,
        "stored": stored,
    }
    logger.info("Global anchor refresh: %s", result)
    return result


def _payload_retrieved_at(
    payload: Mapping[str, Any],
    *,
    report_path: Path,
) -> str:
    generated_at = str(payload.get("generated_at") or "").strip()
    if generated_at:
        return _aware_china(
            generated_at,
            f"{report_path} generated_at",
        ).isoformat(timespec="seconds")
    # Old reports without a generation stamp cannot prove an earlier
    # availability time.  Filesystem mtime is a conservative capture time.
    return datetime.fromtimestamp(
        report_path.stat().st_mtime,
        CHINA_TZ,
    ).isoformat(timespec="seconds")


def replay_global_anchors(
    *,
    reports_dir: Optional[Path] = None,
    paths: Optional[StorePaths] = None,
    start_trade_date: Optional[str] = None,
    end_trade_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Replay saved payloads without re-fetching or modifying report files."""

    root = Path(reports_dir or config.REPORTS_DIR)
    target_paths = paths or default_store_paths()
    start = str(start_trade_date or "").strip()
    end = str(end_trade_date or "").strip()
    bundles = []
    blocked = []
    pending_observations = []
    for payload_path in sorted(root.glob("*/payload.json")):
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            blocked.append({
                "path": str(payload_path),
                "reason": f"invalid_payload:{type(exc).__name__}",
            })
            continue
        if not isinstance(payload, dict):
            blocked.append({
                "path": str(payload_path),
                "reason": "payload_root_not_object",
            })
            continue
        trade_date = str(
            ((payload.get("market_overview") or {}).get("trade_date"))
            or ""
        ).strip()
        if start and trade_date < start:
            continue
        if end and trade_date > end:
            continue
        us_market = payload.get("us_market")
        if not trade_date or not isinstance(us_market, Mapping):
            blocked.append({
                "path": str(payload_path),
                "reason": "trade_date_or_us_market_missing",
            })
            continue
        retrieved_at = _payload_retrieved_at(
            payload,
            report_path=payload_path,
        )
        historical = observations_as_of(
            retrieved_at,
            paths=target_paths,
            entity_ids=[
                ANCHOR_CONTEXT_ENTITY_ID,
                *(definition["symbol"] for definition in ANCHORS.values()),
            ],
            dimensions=[DIMENSION],
        )
        decision_time = _aware_china(retrieved_at, "retrieved_at")
        historical.extend(
            row
            for row in pending_observations
            if _aware_china(
                row.get("available_at"), "observation available_at"
            )
            <= decision_time
        )
        try:
            manifest, observations, factors, _ = build_global_anchor_run(
                as_of_trade_date=trade_date,
                retrieved_at=retrieved_at,
                us_market=us_market,
                existing_observations=historical,
                mode="replay",
            )
        except Exception as exc:
            blocked.append({
                "path": str(payload_path),
                "reason": f"{type(exc).__name__}:{str(exc)[:120]}",
            })
            continue
        bundles.append((manifest, observations, factors))
        pending_observations.extend(observations)

    stored = (
        append_runs(bundles, paths=target_paths)
        if bundles
        else {
            "observations_written": 0,
            "factors_written": 0,
            "manifests_written": 0,
        }
    )
    return {
        "status": (
            "blocked"
            if not bundles
            else ("partial" if blocked else "complete")
        ),
        "trade_dates": len(bundles),
        "blocked": blocked,
        **stored,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay saved global-anchor payloads into Research v2"
    )
    parser.add_argument("--reports-dir", type=Path)
    parser.add_argument("--research-dir", type=Path)
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    args = parser.parse_args(argv)
    result = replay_global_anchors(
        reports_dir=args.reports_dir,
        paths=(
            default_store_paths(args.research_dir)
            if args.research_dir
            else None
        ),
        start_trade_date=args.from_date,
        end_trade_date=args.to_date,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in {"complete", "partial"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
