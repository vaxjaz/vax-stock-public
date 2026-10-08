"""Overwrite a single latest snapshot; no historical files or LLM calls."""
import json
import logging
import os
import time
from datetime import datetime, timezone, date

from vaxstock import config
from vaxstock.indicators.capex import analyze_company
from vaxstock.sources.sec_capex import COMPANIES, fetch_company_facts

logger = logging.getLogger(__name__)


def refresh_capex(*, fetcher=fetch_company_facts, now=None, path=None):
    now = now or datetime.now(timezone.utc)
    path = path or config.STATE_DIR / "eod" / "current_capex.json"
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        age = (now-datetime.fromisoformat(cached["generated_at"])).total_seconds()
        if 0 <= age < 12*3600 and cached.get("complete"):
            return cached
    except (OSError, ValueError, KeyError, TypeError):
        pass
    snapshot = {"generated_at": now.isoformat(), "as_of": now.date().isoformat(), "companies": [], "complete": True}
    for symbol, (name, cik, tag) in COMPANIES.items():
        try:
            result = analyze_company(fetcher(cik), tag, snapshot["as_of"])
            if result.get("available"):
                result["period_age_days"] = (now.date()-date.fromisoformat(result["period_end"])).days
        except Exception as exc:
            logger.warning("SEC CAPEX %s unavailable: %s", symbol, type(exc).__name__)
            result = {"available": False, "reason": f"官方取数/解析失败（{type(exc).__name__}）"}
        snapshot["companies"].append(dict(result, symbol=symbol, name=name))
        snapshot["complete"] = snapshot["complete"] and result.get("available", False)
        time.sleep(0.2)  # Far below SEC's 10 requests/second limit.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+f".{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return snapshot
