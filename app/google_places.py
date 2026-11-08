# live places from Google Maps (Places API, new version) when GOOGLE_MAPS_API_KEY is set
# Google's terms allow keeping place ids, but other place details only briefly, so results
# are kept in memory for an hour and never written to the database
import math
import os
import time

import httpx

SEARCH = "https://places.googleapis.com/v1/places:searchText"
PHOTO = "https://places.googleapis.com/v1/{}/media?maxWidthPx={}&skipHttpRedirect=true"
OSRM = "https://router.project-osrm.org/route/v1/driving/{},{};{},{}?overview=full&geometries=polyline"
FIELDS = ",".join(
    "places." + f
    for f in (
        "id",
        "displayName",
        "shortFormattedAddress",
        "location",
        "rating",
        "userRatingCount",
        "priceLevel",
        "editorialSummary",
        "primaryTypeDisplayName",
        "googleMapsUri",
        "photos",
        "regularOpeningHours.weekdayDescriptions",
    )
)
QUERIES = {
    "attraction": "top tourist attractions in {}",
    "restaurant": "best restaurants in {}",
    "cafe": "best cafes in {}",
    "photo": "best viewpoints and photo spots in {}",
}
ROUTE_QUERIES = {
    "nature": "scenic places, waterfalls and viewpoints",
    "history": "forts and heritage sites",
    "food": "popular restaurants",
}
PRICES = {
    "PRICE_LEVEL_FREE": "Free",
    "PRICE_LEVEL_INEXPENSIVE": "₹",
    "PRICE_LEVEL_MODERATE": "₹₹",
    "PRICE_LEVEL_EXPENSIVE": "₹₹₹",
    "PRICE_LEVEL_VERY_EXPENSIVE": "₹₹₹₹",
}
KEEP_SECONDS = 3600
TIMEOUT = 8
_memory: dict[str, tuple[float, object]] = {}
photos: dict[str, str] = {}


class GoogleError(Exception):
    pass


def key() -> str:
    return os.getenv("GOOGLE_MAPS_API_KEY", "")


def enabled() -> bool:
    return bool(key()) and os.getenv("PLACES_MODE", "auto") != "off"


def remembered(name: str, make, now: float | None = None):
    now = now or time.time()
    hit = _memory.get(name)
    if hit and now - hit[0] < KEEP_SECONDS:
        return hit[1]
    value = make()
    _memory[name] = (now, value)
    if len(_memory) > 500:
        for k, _ in sorted(_memory.items(), key=lambda kv: kv[1][0])[:100]:
            _memory.pop(k, None)
    return value


def search(body: dict) -> list[dict]:
    try:
        r = httpx.post(
            SEARCH,
            json={"languageCode": "en", "regionCode": "IN", **body},
            headers={"X-Goog-Api-Key": key(), "X-Goog-FieldMask": FIELDS, "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as e:
        raise GoogleError(f"Google Places request failed ({type(e).__name__})") from None
    if r.status_code != 200:
        raise GoogleError(f"Google Places answered {r.status_code}")
    return r.json().get("places", [])


def score(p: dict) -> float:
    return (p.get("rating") or 0) * math.log10(10 + (p.get("userRatingCount") or 0))


def to_card(p: dict, kind: str) -> dict:
    name = (p.get("displayName") or {}).get("text", "")
    loc = p.get("location") or {}
    summary = (p.get("editorialSummary") or {}).get("text", "")
    label = (p.get("primaryTypeDisplayName") or {}).get("text", "")
    rating = p.get("rating")
    count = p.get("userRatingCount") or 0
    rated = f"rated {rating} by {count:,} people on Google." if rating else ""
    text = summary or (
        f"{label}, {rated}" if label and rated else ((rated[:1].upper() + rated[1:]) if rated else label)
    )
    card = {
        "id": "g-" + p["id"],
        "name": name,
        "kind": kind,
        "category": kind,
        "area": p.get("shortFormattedAddress", ""),
        "text": text,
        "tip": "",
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
        "rating": rating,
        "reviews": count,
        "maps_url": p.get("googleMapsUri", ""),
        "source": "Google Maps",
    }
    if p.get("priceLevel") in PRICES:
        card["price"] = PRICES[p["priceLevel"]]
    hours = (p.get("regularOpeningHours") or {}).get("weekdayDescriptions")
    if hours:
        card["hours"] = "; ".join(hours)
    shot = (p.get("photos") or [None])[0]
    if shot:
        photos[card["id"]] = shot["name"]
        who = [a.get("displayName") for a in shot.get("authorAttributions", []) if a.get("displayName")]
        if who:
            card["photo_by"] = ", ".join(who)
    return card


def city_sections(city: str, lat: float | None, lng: float | None, limit: int = 12) -> dict[str, list[dict]]:
    def make():
        out = {}
        for kind, q in QUERIES.items():
            body: dict = {"textQuery": q.format(city), "pageSize": limit}
            if lat is not None and lng is not None:
                body["locationBias"] = {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 20000.0}}
            found = sorted(search(body), key=score, reverse=True)
            out[kind] = [to_card(p, kind) for p in found if p.get("id")]
        return out

    return remembered(f"city:{city}", make)


def photo_url(card_id: str, width: int = 800) -> str | None:
    name = photos.get(card_id)
    if not name:
        return None

    def make():
        try:
            r = httpx.get(PHOTO.format(name, width), headers={"X-Goog-Api-Key": key()}, timeout=TIMEOUT)
        except httpx.HTTPError:
            return None
        return r.json().get("photoUri") if r.status_code == 200 else None

    return remembered(f"photo:{name}", make)


def route_line(a: tuple[float, float], b: tuple[float, float]) -> str | None:
    def make():
        try:
            r = httpx.get(OSRM.format(a[1], a[0], b[1], b[0]), timeout=TIMEOUT)
            return r.json()["routes"][0]["geometry"] if r.status_code == 200 else None
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            return None

    return remembered(f"route:{a}:{b}", make)


def along_route(a: tuple[float, float], b: tuple[float, float], limit: int = 6) -> list[dict]:
    line = route_line(a, b)
    if not line:
        return []

    def make():
        out, seen = [], set()
        for kind, q in ROUTE_QUERIES.items():
            found = search(
                {
                    "textQuery": q,
                    "pageSize": limit,
                    "searchAlongRouteParameters": {"polyline": {"encodedPolyline": line}},
                }
            )
            for p in sorted(found, key=score, reverse=True):
                if p.get("id") and p["id"] not in seen:
                    seen.add(p["id"])
                    out.append(to_card(p, kind))
        return out

    return remembered(f"along:{a}:{b}", make)
