# sample data provider
import json
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from app.providers.base import PlacesProvider, ProviderError, StayProvider, TransportProvider
from app.state import PlaceOption, StayOption, TransportOption

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@lru_cache
def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def at(d: date, hhmm: str) -> datetime:
    return datetime.combine(d, datetime.strptime(hhmm, "%H:%M").time())


class FixtureTransport(TransportProvider):
    def search(self, origin, destination, travel_date, travellers, direction):
        routes = load("transport")
        rows = routes.get(f"{origin}|{destination}") or routes.get(f"{destination}|{origin}")
        if not rows:
            raise ProviderError(f"no transport data for {origin} to {destination}")
        out = []
        for i, r in enumerate(rows):
            if direction == "arrive_on" and r["next_day"]:
                dep_day = travel_date - timedelta(days=1)
            else:
                dep_day = travel_date
            arr_day = dep_day + timedelta(days=1) if r["next_day"] else dep_day
            out.append(
                TransportOption(
                    id=f"{origin[:3]}-{destination[:3]}-{i}".lower(),
                    mode=r["mode"],
                    provider=r["provider"],
                    depart_at=at(dep_day, r["depart"]),
                    arrive_at=at(arr_day, r["arrive"]),
                    price_inr=r["price_per_person"] * travellers,
                    overnight=r["next_day"],
                    source="fixture",
                )
            )
        return out


class FixtureStays(StayProvider):
    def search(self, city, check_in, check_out, travellers):
        rows = load("stays").get(city)
        if not rows:
            raise ProviderError(f"no stay data for {city}")
        return [StayOption(**r, source="fixture") for r in rows]


class FixturePlaces(PlacesProvider):
    def search(self, city):
        rows = load("places").get(city)
        if not rows:
            raise ProviderError(f"no places data for {city}")
        return [PlaceOption(**r, source="fixture") for r in rows]


def supported_routes() -> list[tuple[str, str]]:
    return [tuple(k.split("|")) for k in load("transport")]
