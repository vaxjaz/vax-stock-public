# -*- coding: utf-8 -*-
"""services.regime_auditor tests (zero network)."""

import json
import pathlib
import shutil
import tempfile

from vaxstock.services import regime_auditor as ra


def _payload():
    return {
        "generated_at": "2026-07-03 05:00:00",
        "market_regime": "panic",
        "indices": [
            {"name": "上证指数", "change_pct": -1.0, "source": "tushare"},
            {"name": "创业板指", "change_pct": -3.0, "source": "tushare"},
            {"name": "科创50", "change_pct": -2.0, "source": "tushare"},
        ],
        "market_overview": {
            "trade_date": "20260702",
            "limit_down_count": 60,
            "source": "tushare",
        },
    }


def test_build_regime_audit_from_payload():
    audit = ra.build_regime_audit(_payload())
    assert audit["schema_version"] == 1
    assert audit["trade_date"] == "20260702"
    assert audit["raw_regime"] == "panic"
    assert audit["smoothed_regime"] == "panic"
    assert audit["inputs"]["limit_down_count"] == 60
    assert audit["sources"] == {"indices": ["tushare"], "market_overview": "tushare"}
    assert "limit_down_count=60" in audit["reason"]


def test_record_regime_audit_writes_jsonl_and_markdown_idempotent():
    d = pathlib.Path(tempfile.mkdtemp(prefix="vaxregaudit_"))
    try:
        jsonl = d / "regime_audit.jsonl"
        first = ra.record_regime_audit(_payload(), jsonl_path=jsonl, output_dir=d)
        second = ra.record_regime_audit(_payload(), jsonl_path=jsonl, output_dir=d)
        assert first["written"] == 1 and first["skipped"] == 0
        assert second["written"] == 0 and second["skipped"] == 1

        rows = [json.loads(x) for x in jsonl.read_text(encoding="utf-8").splitlines() if x.strip()]
        assert len(rows) == 1
        assert rows[0]["trade_date"] == "20260702"

        md = d / "regime_audit_20260702.md"
        assert md.is_file()
        text = md.read_text(encoding="utf-8")
        assert "# Regime Audit 20260702" in text
        assert "raw_regime: panic" in text
        assert "limit_down_count=60" in text
        assert "market_overview_source: tushare" in text
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    import sys
    fns = sorted((n, f) for n, f in globals().items()
                 if n.startswith("test_") and callable(f))
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  [PASS] {name}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)