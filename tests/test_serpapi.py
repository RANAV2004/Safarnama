# serpapi tests
from datetime import date, time

import httpx
import pytest

from app.providers import ProviderError, get_providers, serpapi
from app.providers.serpapi import SerpApiFlights, SerpApiHotels, parse_clock


class FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status = data, status

    def raise_for_status(self):
        if self.status >= 400:
            raise httpx.HTTPStatusError(
                "bad", request=httpx.Request("GET", "https://x"), response=httpx.Response(self.status)
            )

    def json(self):
        return self.data


@pytest.fixture
def serp(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "k")

    def set_reply(data, status=200):
        monkeypatch.setattr(serpapi.httpx, "get", lambda *a, **k: FakeResponse(data, status))

    return set_reply


FLIGHT = {
    "price": 4200,
    "flights": [
        {
            "airline": "IndiGo",
            "departure_airport": {"time": "2026-11-20 06:10"},
            "arrival_airport": {"time": "2026-11-20 08:05"},
        }
    ],
}
HOTEL = {
    "name": "Sea View",
    "rate_per_night": {"extracted_lowest": 2500},
    "overall_rating": 4.2,
    "check_in_time": "2:00 PM",
    "gps_coordinates": {"latitude": 15.5, "longitude": 73.8},
}


@pytest.mark.parametrize(
    "raw,expected", [("3:00 PM", time(15, 0)), ("12:30 am", time(0, 30)), (None, time(12, 0)), ("noon", time(12, 0))]
)
def test_parse_clock(raw, expected):
    assert parse_clock(raw, time(12, 0)) == expected


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    with pytest.raises(ProviderError):
        SerpApiHotels().search("Goa", date(2026, 11, 20), date(2026, 11, 22), 2)


def test_flights_parsed(serp):
    serp({"best_flights": [FLIGHT], "other_flights": [{"price": 1}]})
    res = SerpApiFlights().search("Indore", "Goa", date(2026, 11, 20), 1, "arrive_on")
    assert len(res) == 1 and res[0].price_inr == 4200 and res[0].provider == "IndiGo" and res[0].source == "serpapi"


def test_unknown_airport_raises(serp):
    with pytest.raises(ProviderError):
        SerpApiFlights().search("Ujjain", "Goa", date(2026, 11, 20), 1, "arrive_on")


def test_hotels_parsed_and_zero_nights_handled(serp):
    serp({"properties": [HOTEL, {"name": "No price"}]})
    res = SerpApiHotels().search("Goa", date(2026, 11, 20), date(2026, 11, 20), 2)
    assert [h.name for h in res] == ["Sea View"] and res[0].checkin_from == time(14, 0)


@pytest.mark.parametrize("data,status", [({"error": "quota"}, 200), ({}, 500), ({"best_flights": []}, 200)])
def test_api_problems_raise(serp, data, status):
    serp(data, status)
    with pytest.raises(ProviderError):
        SerpApiFlights().search("Indore", "Goa", date(2026, 11, 20), 1, "arrive_on")


def test_live_mode_falls_back_to_fixtures(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "live")
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    p = get_providers()
    res = p.stays.search("Goa", date(2026, 11, 20), date(2026, 11, 22), 2)
    assert res[0].source == "fixture" and "SERPAPI_KEY" in p.stays.last_error


def test_live_failure_is_reported_in_plan(monkeypatch, make_req):
    from app.graph import plan_trip

    monkeypatch.setenv("PROVIDER_MODE", "live")
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    s = plan_trip(make_req(budget_inr=20000))
    assert any("used fixtures" in e for e in s.errors)
    assert "live transport data failed, showing sample data" in s.notes


def test_errors_never_show_the_key(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "secret-key-123")

    def fail(*a, **k):
        req = httpx.Request("GET", "https://serpapi.com/search.json?api_key=secret-key-123")
        raise httpx.HTTPStatusError(f"bad for url {req.url}", request=req, response=httpx.Response(401))

    monkeypatch.setattr(serpapi.httpx, "get", fail)
    with pytest.raises(ProviderError) as e:
        serpapi.call({})
    assert "secret-key-123" not in str(e.value) and "401" in str(e.value) and e.value.__cause__ is None
    monkeypatch.setattr(serpapi.httpx, "get", lambda *a, **k: FakeResponse({"error": "bad key secret-key-123"}))
    with pytest.raises(ProviderError) as e:
        serpapi.call({})
    assert "secret-key-123" not in str(e.value)


def test_hotel_ids_come_from_names(serp):
    serp({"properties": [HOTEL, {**HOTEL, "rate_per_night": {"extracted_lowest": 3000}}]})
    res = SerpApiHotels().search("Goa", date(2026, 11, 20), date(2026, 11, 22), 2)
    assert [h.id for h in res] == ["serp-h-sea-view", "serp-h-sea-view-2"]
