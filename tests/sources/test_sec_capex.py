import json
import time

import pytest

from vaxstock.sources.sec_capex import fetch_company_facts


def test_verified_identity_and_nonprivate_default_agent(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, _):
            return json.dumps({"cik": 789019, "entityName": "MICROSOFT CORPORATION", "facts": {}}).encode()
    def open_request(request, timeout):
        assert request.full_url in ("https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json",
                                    "https://data.sec.gov/api/xbrl/companyfacts/CIK0001018724.json")
        assert request.get_header("User-agent") == "vaxstock-capex/1.0 public-financial-data-monitor"
        return Response()
    monkeypatch.setattr("urllib.request.urlopen", open_request)
    assert fetch_company_facts("0000789019")["cik"] == 789019
    with pytest.raises(ValueError, match="identity mismatch"):
        fetch_company_facts("0001018724")


def test_blocking_network_call_has_wall_clock_timeout(monkeypatch):
    def stuck(*args, **kwargs):
        time.sleep(.2)
        raise OSError()
    monkeypatch.setattr("urllib.request.urlopen", stuck)
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        fetch_company_facts("0000789019", timeout=.01)
    assert time.monotonic()-start < .15
