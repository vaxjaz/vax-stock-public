"""Pure cash-CAPEX calculations from disclosed USD cash-flow facts.

Quarter = direct quarter fact, or same fiscal-start YTD minus previous YTD.
Q4 uses full-year minus nine months. Keep all operands for audit. The caller's
as_of date restricts filing availability; later comparative disclosures cannot
enter an earlier snapshot. No investment labels, thresholds or default values.
"""
import math
from datetime import date, timedelta


def _day(value):
    return date.fromisoformat(value)


def _facts(company, tag, as_of):
    rows = company.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", [])
    valid = []
    for row in rows:
        if row.get("form") not in ("10-Q", "10-K", "10-Q/A", "10-K/A"):
            continue
        try:
            start, end, filed = (_day(row[k]) for k in ("start", "end", "filed"))
            value = row["val"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                continue
            if filed > as_of or end > as_of or not 70 <= (end-start).days+1 <= 380:
                continue
            if not row.get("accn"):
                continue
        except (ValueError, KeyError, TypeError):
            continue
        valid.append({k: row[k] for k in ("start", "end", "val", "filed", "accn", "form")} | {"tag": tag, "unit": "USD"})
    return valid


def _latest(rows):
    newest = max(rows, key=lambda r: (r["filed"], r["accn"]))
    peers = [r for r in rows if (r["filed"], r["accn"]) == (newest["filed"], newest["accn"])]
    if len({r["val"] for r in peers}) > 1:
        raise ValueError("conflicting SEC facts in same filing/context")
    return newest


def _quarters(rows):
    quarters = {}
    for end in sorted({r["end"] for r in rows}):
        direct = [r for r in rows if r["end"] == end and 70 <= (_day(end)-_day(r["start"])).days+1 <= 110]
        if direct:
            # All four monitored companies use calendar quarter boundaries.
            starts = {r["start"] for r in direct}
            if len(starts) != 1:
                raise ValueError("ambiguous quarter start")
            r = _latest(direct)
            quarters[end] = {"start": r["start"], "end": end, "value": r["val"], "method": "reported", "operands": [r]}
            continue
        candidates = []
        for total in (r for r in rows if r["end"] == end):
            prefixes = [r for r in rows if r["start"] == total["start"] and r["filed"] <= total["filed"]
                        and 70 <= (_day(end)-_day(r["end"])).days <= 110]
            same_filing = [r for r in prefixes if r["accn"] == total["accn"]]
            if prefixes:
                prefix = _latest(same_filing or prefixes)
                candidates.append((total, prefix))
        if candidates:
            total, prefix = max(candidates, key=lambda pair: (pair[0]["filed"], pair[0]["accn"]))
            quarters[end] = {"start": (_day(prefix["end"])+timedelta(days=1)).isoformat(), "end": end,
                             "value": total["val"]-prefix["val"], "method": "YTD_difference", "operands": [total, prefix]}
    return quarters


def analyze_company(company, capex_tag, as_of):
    as_of = _day(as_of)
    capex_rows = _facts(company, capex_tag, as_of)
    ocf_rows = _facts(company, "NetCashProvidedByUsedInOperatingActivities", as_of)
    if not capex_rows:
        return {"available": False, "reason": "现金 CAPEX 的 USD 披露缺失", "capex_tag": capex_tag}
    capex, ocf = _quarters(capex_rows), _quarters(ocf_rows)
    end = max(r["end"] for r in capex_rows)
    if end not in capex:
        return {"available": False, "reason": "最新披露无法还原单季 CAPEX", "period_end": end}
    quarter = capex[end]
    cashflow = ocf.get(end)
    if cashflow and cashflow["start"] != quarter["start"]:
        cashflow = None
    try:
        prior_end = _day(end).replace(year=_day(end).year-1).isoformat()
        prior_start = _day(quarter["start"]).replace(year=_day(quarter["start"]).year-1).isoformat()
    except ValueError:
        prior_end, prior_start = "", ""
    prior = capex.get(prior_end)
    if prior and prior["start"] != prior_start:
        prior = None
    ttm = [capex[k] for k in sorted(capex) if k <= end][-4:]
    contiguous = len(ttm) == 4 and all(_day(b["start"])-_day(a["end"]) == timedelta(days=1) for a,b in zip(ttm, ttm[1:]))
    cfo = cashflow["value"] if cashflow else None
    if quarter["value"] < 0:
        raise ValueError("negative cash CAPEX; verify source/cumulative contexts")
    return {"available": True, "entity": company["entityName"], "cik": company["cik"],
            "period_start": quarter["start"], "period_end": end, "unit": "USD",
            "filed": max(r["filed"] for r in quarter["operands"]),
            "capex_usd": quarter["value"], "capex_tag": capex_tag,
            "yoy_pct": (quarter["value"]/prior["value"]-1)*100 if prior and prior["value"] > 0 else None,
            "ttm_capex_usd": sum(r["value"] for r in ttm) if contiguous else None,
            "operating_cashflow_usd": cfo,
            "capex_to_ocf_pct": quarter["value"]/cfo*100 if cfo is not None and cfo > 0 else None,
            "cashflow_less_capex_usd": cfo-quarter["value"] if cfo is not None else None,
            "quarter": quarter, "prior_quarter": prior, "ocf_quarter": cashflow,
            "ttm_quarters": ttm if contiguous else [],
            "lease_inclusive_capex": None, "guidance": None,
            "source_url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(company['cik']):010d}.json"}
