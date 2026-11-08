# providers tests
from datetime import date

import pytest

from app.providers import ProviderError, WithFallback
from app.providers.fixture import FixtureStays, FixtureTransport


def test_overnight_outbound_leaves_day_before():
    opts = FixtureTransport().search("Indore", "Goa", date(2026, 11, 20), 1, "arrive_on")
    for o in opts:
        assert o.arrive_at.date() == date(2026, 11, 20)


def test_price_is_for_all_travellers():
    one = FixtureTransport().search("Delhi", "Jaipur", date(2026, 11, 20), 1, "depart_on")[0]
    three = FixtureTransport().search("Delhi", "Jaipur", date(2026, 11, 20), 3, "depart_on")[0]
    assert three.price_inr == one.price_inr * 3


def test_unknown_route_raises():
    with pytest.raises(ProviderError):
        FixtureTransport().search("Delhi", "Shillong", date(2026, 11, 20), 1, "arrive_on")


class Broken:
    def search(self, *a, **k):
        raise ProviderError("timeout")


def test_fallback_uses_fixtures_and_records_error():
    prov = WithFallback(Broken(), FixtureStays())
    res = prov.search("Goa", date(2026, 11, 20), date(2026, 11, 22), 2)
    assert res and res[0].source == "fixture"
    assert "timeout" in prov.last_error
