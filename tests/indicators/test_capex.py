import copy
from datetime import datetime, timezone

from vaxstock.indicators.capex import analyze_company
from vaxstock.sources.sec_capex import OCF_TAG
from vaxstock.report.capex import render_capex_lines
from vaxstock.services.capex_refresh import refresh_capex

TAG = "PaymentsToAcquirePropertyPlantAndEquipment"


def fact(start, end, value, filed="2026-02-01", accn="filing", form="10-K"):
    return dict(start=start, end=end, val=value, filed=filed, accn=accn, form=form)


def company(capex, ocf=()):
    return {"cik": 789019, "entityName": "MICROSOFT CORPORATION", "facts": {"us-gaap": {
        TAG: {"units": {"USD": list(capex)}}, OCF_TAG: {"units": {"USD": list(ocf)}}}}}


def annual_rows(multiplier=1):
    return [fact("2025-01-01", "2025-03-31", 10*multiplier),
            fact("2025-01-01", "2025-06-30", 30*multiplier),
            fact("2025-01-01", "2025-09-30", 60*multiplier),
            fact("2025-01-01", "2025-12-31", 100*multiplier)]


def test_ytd_quarters_q4_ttm_and_cashflow():
    result = analyze_company(company(annual_rows(), annual_rows(2)), TAG, "2026-02-02")
    assert result["capex_usd"] == 40
    assert result["period_start"] == "2025-10-01"
    assert result["ttm_capex_usd"] == 100
    assert result["operating_cashflow_usd"] == 80
    assert result["capex_to_ocf_pct"] == 50
    assert result["cashflow_less_capex_usd"] == 40
    assert len(result["quarter"]["operands"]) == 2


def test_direct_quarter_wins_and_yoy_uses_matching_quarter():
    rows = annual_rows()+[fact("2025-10-01", "2025-12-31", 45),
                          fact("2024-10-01", "2024-12-31", 30)]
    result = analyze_company(company(rows), TAG, "2026-02-02")
    assert result["capex_usd"] == 45
    assert result["yoy_pct"] == 50
    assert result["quarter"]["method"] == "reported"
    assert result["capex_to_ocf_pct"] is None


def test_future_disclosure_excluded_and_latest_restatement_selected():
    rows = [fact("2025-01-01", "2025-03-31", 10, "2025-04-20", "old"),
            fact("2025-01-01", "2025-03-31", 12, "2025-07-20", "restated"),
            fact("2025-04-01", "2025-06-30", 20, "2025-07-20", "new")]
    result = analyze_company(company(rows), TAG, "2025-05-01")
    assert result["capex_usd"] == 10
    assert analyze_company(company(rows[:2]), TAG, "2025-08-01")["capex_usd"] == 12


def test_latest_unrecoverable_is_missing_not_previous_quarter():
    rows = [fact("2025-01-01", "2025-03-31", 10), fact("2025-01-01", "2025-12-31", 100)]
    assert not analyze_company(company(rows), TAG, "2026-02-02")["available"]


def test_missing_usd_wrong_units_and_zero_ocf():
    data = company(annual_rows(), annual_rows(0))
    result = analyze_company(data, TAG, "2026-02-02")
    assert result["capex_to_ocf_pct"] is None
    data["facts"]["us-gaap"][TAG]["units"] = {"EUR": annual_rows()}
    assert not analyze_company(data, TAG, "2026-02-02")["available"]


def test_no_partial_ttm_and_no_mismatched_cashflow():
    rows = [fact("2025-10-01", "2025-12-31", 40)]
    ocf = [fact("2025-09-15", "2025-12-31", 80)]
    result = analyze_company(company(rows, ocf), TAG, "2026-02-02")
    assert result["ttm_capex_usd"] is None
    assert result["operating_cashflow_usd"] is None


def test_snapshot_overwrite_cache_and_failed_company(tmp_path, monkeypatch):
    import vaxstock.services.capex_refresh as module
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr(module, "COMPANIES", {"MSFT": ("Microsoft", "0000789019", TAG)})
    path = tmp_path/"current_capex.json"
    now = datetime(2026, 2, 2, tzinfo=timezone.utc)
    result = refresh_capex(fetcher=lambda _: company(annual_rows(), annual_rows(2)), now=now, path=path)
    assert result["complete"]
    def fail(_):
        raise TimeoutError()
    assert refresh_capex(fetcher=fail, now=now, path=path) == result
    later = datetime(2026, 2, 3, tzinfo=timezone.utc)
    missing = refresh_capex(fetcher=fail, now=later, path=path)
    assert not missing["complete"]
    assert not missing["companies"][0]["available"]
    assert list(tmp_path.iterdir()) == [path]
    assert "待验证" in "\n".join(render_capex_lines(missing))


def test_pure_calculation_does_not_mutate_input():
    data = company(annual_rows())
    original = copy.deepcopy(data)
    analyze_company(data, TAG, "2026-02-02")
    assert data == original
