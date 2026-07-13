# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path

from vaxstock import config


def test_private_holdings_precedence_and_corruption_do_not_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        baseline = root / "holdings.json"
        private_state = root / "holdings_state.json"
        baseline.write_text(json.dumps({"holdings": {"600001": {"shares": 100}}}), encoding="utf-8")
        private_state.write_text(json.dumps({"holdings": {"600001": {"shares": 90}}}), encoding="utf-8")
        old_base = config.HOLDINGS_BASE_FILE
        old_state = config.HOLDINGS_STATE_FILE
        try:
            config.HOLDINGS_BASE_FILE = baseline
            config.HOLDINGS_STATE_FILE = private_state
            assert config.load_holdings()["600001"]["shares"] == 90
            private_state.write_text("{broken", encoding="utf-8")
            assert config.load_holdings() == {}
            private_state.unlink()
            assert config.load_holdings()["600001"]["shares"] == 100
        finally:
            config.HOLDINGS_BASE_FILE = old_base
            config.HOLDINGS_STATE_FILE = old_state