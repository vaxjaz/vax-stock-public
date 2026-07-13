# -*- coding: utf-8 -*-
"""D-line observation planning worker.

This module consumes the latest queued observation planning job and calls Codex
outside the EOD critical path. It is intended to be launched by systemd after
EOD with --no-block, so slow/failed LLM generation cannot block report delivery.
"""

from __future__ import annotations

import logging
import sys

from vaxstock.services.forecast_planner import run_observation_job

logger = logging.getLogger(__name__)


def main() -> int:
    stats = run_observation_job()
    logger.info("D-line observation worker finished: %s", stats)
    status = stats.get("status")
    if status in {"done", "partial_done", "partial_failed", "missing_payload"}:
        try:
            from vaxstock.services.daily_action import refresh_and_send_daily_action
            result = refresh_and_send_daily_action(
                target_trade_date=stats.get("target_trade_date"),
                degraded=status != "done",
            )
            action_stats = {
                k: v for k, v in result.get("action", {}).items()
                if k not in {"plan", "markdown"}
            }
            logger.info(
                "Daily action completed: action=%s mail=%s",
                action_stats,
                result.get("mail"),
            )
        except Exception as exc:
            logger.warning("Daily action mail failed (D-line tasks remain valid): %s", str(exc)[:160])
    print("DLINE plan done:", stats)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        sys.exit(main())
    except Exception:
        logging.exception("D-line observation worker failed")
        sys.exit(1)
