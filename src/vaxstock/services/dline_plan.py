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
    print("DLINE plan done:", stats)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        sys.exit(main())
    except Exception:
        logging.exception("D-line observation worker failed")
        sys.exit(1)
