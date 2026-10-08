"""Explicit SEC Company Facts requests; no initialization or I/O on import.

Schema verified on the production VPS, 2026-10-08. Official API documentation:
https://www.sec.gov/search-filings/edgar-application-programming-interfaces
USD facts are dollars, not millions. Amazon's current tag includes productive
assets/software; its PPE-only tag stopped in 2017. No interchangeable fallback.
"""
import json
import os
import queue
import threading
import urllib.request

COMPANIES = {
    "MSFT": ("Microsoft", "0000789019", "PaymentsToAcquirePropertyPlantAndEquipment"),
    "GOOGL": ("Alphabet", "0001652044", "PaymentsToAcquirePropertyPlantAndEquipment"),
    "AMZN": ("Amazon", "0001018724", "PaymentsToAcquireProductiveAssets"),
    "META": ("Meta", "0001326801", "PaymentsToAcquirePropertyPlantAndEquipment"),
}
OCF_TAG = "NetCashProvidedByUsedInOperatingActivities"


def fetch_company_facts(cik, timeout=20):
    """Enforce wall-clock timeout even if DNS/TLS/read blocks; no private header."""
    result = queue.Queue(maxsize=1)

    def request():
        try:
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            headers = {"User-Agent": os.getenv("SEC_USER_AGENT") or
                       "vaxstock-capex/1.0 public-financial-data-monitor",
                       "Accept": "application/json"}
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                        timeout=timeout) as response:
                raw = response.read(20_000_001)
            if len(raw) > 20_000_000:
                raise ValueError("SEC response exceeds size limit")
            data = json.loads(raw)
            if int(data["cik"]) != int(cik) or not data.get("entityName"):
                raise ValueError("SEC entity identity mismatch")
            result.put((data, None))
        except Exception as exc:
            result.put((None, exc))

    thread = threading.Thread(target=request, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError("SEC Company Facts wall-clock timeout")
    data, error = result.get_nowait()
    if error:
        raise error
    return data
