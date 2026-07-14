# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path

from vaxstock.services.daily_action import _enrich_market_context_from_a


def _snapshot():
    return {
        "target_trade_dates": ["20260714"],
        "tasks": [{
            "code": "601138",
            "baseline_trade_date": "20260713",
            "target_trade_date": "20260714",
            "evidence_pack": {
                "baseline_trade_date": "20260713",
                "A_eod": {
                    "market": {
                        "market_regime": "panic",
                        "macro_regime": "🟡 中性",
                        "ai_track": {"position_ceiling": "进攻档"},
                    },
                },
            },
        }],
    }


def _payload(trade_date="20260713"):
    return {
        "market_overview": {
            "trade_date": trade_date,
            "up_count": 801,
            "down_count": 4683,
            "limit_up_count": 36,
            "limit_down_count": 211,
        },
        "market_regime": "panic",
        "macro": {
            "macro_regime": "🟡 中性",
            "bullish_count": 5,
            "bearish_count": 8,
            "indicators": {
                "m1_yoy": {
                    "value_pct": 5.5,
                    "mom_delta_pp": 0.5,
                    "percentile_10y": 55.0,
                    "signal": "✅",
                    "latest_month": "202605",
                },
            },
            "errors": [],
        },
        "tracks": [{
            "track_name": "AI算力",
            "available": True,
            "position_ceiling": "进攻档 (赛道上限~高位, 可加)",
            "summary_lines": ["NVDA已证实", "SOX开放"],
            "vetoes": [],
            "pending": [],
        }],
    }


def _write_payload(root: Path, payload):
    path = root / "2026-07-13" / "payload.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_backfills_old_task_only_from_exact_baseline_a_payload():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_payload(root, _payload())
        snapshot = _enrich_market_context_from_a(_snapshot(), reports_dir=root)

    market = snapshot["tasks"][0]["evidence_pack"]["A_eod"]["market"]
    assert market["breadth"]["down_count"] == 4683
    assert market["macro"]["bullish_count"] == 5
    assert market["macro"]["indicators"]["m1_yoy"]["value_pct"] == 5.5
    assert market["ai_track"]["position_ceiling"] == "进攻档"
    assert market["ai_track"]["summary_lines"] == ["NVDA已证实", "SOX开放"]
    assert market["ai_track"]["vetoes"] == []


def test_rejects_a_payload_with_mismatched_trade_date():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_payload(root, _payload(trade_date="20260712"))
        snapshot = _enrich_market_context_from_a(_snapshot(), reports_dir=root)

    market = snapshot["tasks"][0]["evidence_pack"]["A_eod"]["market"]
    assert "macro" not in market
    assert "breadth" not in market
    assert "summary_lines" not in market["ai_track"]
