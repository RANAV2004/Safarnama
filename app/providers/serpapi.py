# serpapi provider
import os
import re
from datetime import datetime, time, timedelta

import httpx

from app.providers.base import ProviderError, StayProvider, TransportProvider
from app.state import StayOption, TransportOption

URL = "https://serpapi.com/search.json"
TIMEOUT = 15
IATA = {
    "Delhi": "DEL",
    "Mumbai": "BOM",
    "Bengaluru": "BLR",
    "Indore": "IDR",
    "Goa": "GOI",
    "Jaipur": "JAI",
    "Udaipur": "UDR",
    "Mysuru": "MYQ",
    "Hyderabad": "HYD",
    "Chennai": "MAA",
    "Kolkata": "CCU",
    "Pune": "PNQ",
}


def call(params: dict) -> dict:
    key = os.getenv("SERPAPI_KEY")
    if not key:
        raise ProviderError("SERPAPI_KEY not set")
    try:
        r = httpx.get(URL, params={**params, "api_key": key, "currency": "INR", "hl": "en"}, timeout=TIMEOUT)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise ProviderError(f"serpapi request failed with status {e.response.status_code}") from None
    except httpx.HTTPError as e:
        raise ProviderError(f"serpapi request failed ({type(e).__name__})") from None
    try:
        data = r.json()
    except ValueError:
        raise ProviderError("serpapi sent a reply that is not JSON") from None
    if "error" in data:
        raise ProviderError(str(data["error"]).replace(key, "***")[:200])
    return data


def parse_clock(s: str | None, default: time) -> time:
    if not s:
        return default
    m = re.match(r"(\d{1,2}):(\d{2})\s*([AP]M)", s.strip(), re.IGNORECASE)
    if not m:
        return default
    h = int(m[1]) % 12 + (12 if m[3].upper() == "PM" else 0)
    return time(h, int(m[2]))


class SerpApiFlights(TransportProvider):
    def search(self, origin, destination, travel_date, travellers, direction):
        if origin not in IATA or destination not in IATA:
            raise ProviderError(f"no airport code for {origin} or {destination}")
        data = call(
            {
                "engine": "google_flights",
                "departure_id": IATA[origin],
                "arrival_id": IATA[destination],
                "outbound_date": travel_date.isoformat(),
                "type": 2,
                "adults": travellers,
            }
        )
        out = []
        for i, f in enumerate(data.get("best_flights", []) + data.get("other_flights", [])):
            legs = f.get("flights") or []
            if not legs or "price" not in f:
                continue
            dep = datetime.strptime(legs[0]["departure_airport"]["time"], "%Y-%m-%d %H:%M")
            arr = datetime.strptime(legs[-1]["arrival_airport"]["time"], "%Y-%m-%d %H:%M")
            out.append(
                TransportOption(
                    id=f"serp-fl-{i}",
                    mode="flight",
                    provider=legs[0].get("airline", "flight"),
                    depart_at=dep,
                    arrive_at=arr,
                    price_inr=int(f["price"]),
                    overnight=arr.date() > dep.date(),
                    source="serpapi",
                )
            )
        if not out:
            raise ProviderError("serpapi returned no flights")
        return out


def hotel_id(name: str, taken: set[str]) -> str:
    base = "serp-h-" + (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "hotel")
    hid, n = base, 2
    while hid in taken:
        hid, n = f"{base}-{n}", n + 1
    return hid


class SerpApiHotels(StayProvider):
    def search(self, city, check_in, check_out, travellers):
        if check_out <= check_in:
            check_out = check_in + timedelta(days=1)
        data = call(
            {
                "engine": "google_hotels",
                "q": f"hotels in {city}",
                "check_in_date": check_in.isoformat(),
                "check_out_date": check_out.isoformat(),
                "adults": min(travellers, 2),
            }
        )
        out = []
        for h in data.get("properties", [])[:15]:
            price = (h.get("rate_per_night") or {}).get("extracted_lowest")
            gps = h.get("gps_coordinates") or {}
            if not price or "latitude" not in gps:
                continue
            out.append(
                StayOption(
                    id=hotel_id(h["name"], {s.id for s in out}),
                    name=h["name"],
                    price_per_night_inr=int(price),
                    rating=h.get("overall_rating"),
                    checkin_from=parse_clock(h.get("check_in_time"), time(12, 0)),
                    lat=gps["latitude"],
                    lng=gps["longitude"],
                    source="serpapi",
                    link=h.get("link"),
                )
            )
        if not out:
            raise ProviderError("serpapi returned no hotels")
        return out
