# explore data: city guides, restaurants, cafes, photo spots and stops on the way
# built from Wikivoyage by scripts/build_explore.py, or live from Google Places when a key is set
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, quote_plus

from app import google_places as google
from app.providers.fixture import load as load_fixture
from app.rag import guide
from app.tools.geo import km_between

EXPLORE_FILE = Path(__file__).resolve().parents[1] / "fixtures" / "explore.json"
CITY_COORDS = {
    "Indore": (22.72, 75.86),
    "Mumbai": (19.08, 72.88),
    "Bengaluru": (12.97, 77.59),
    "Delhi": (28.61, 77.21),
    "Goa": (15.49, 73.83),
    "Jaipur": (26.91, 75.79),
    "Udaipur": (24.58, 73.71),
    "Mysuru": (12.30, 76.64),
}
KIND_LABELS = {"restaurant": "Restaurants", "cafe": "Cafes", "photo": "Photo spots", "attraction": "Attractions"}
TAG_LABELS = {
    "beach": "Beaches",
    "mountains": "Mountains",
    "trekking": "Trekking",
    "heritage": "Heritage",
    "spiritual": "Spiritual",
    "nature": "Nature",
    "city": "Big cities",
    "nepal": "Nepal",
}
MEAL_KM = 8


@lru_cache
def data() -> dict:
    return json.loads(EXPLORE_FILE.read_text(encoding="utf-8"))


PHOTO_URL = "https://commons.wikimedia.org/wiki/Special:FilePath/{}?width={}"
CARD_WIDTH = 960
HERO_WIDTH = 1920


def photo_url(file: str | None, width: int = CARD_WIDTH) -> str | None:
    return PHOTO_URL.format(quote(file.replace(" ", "_")), width) if file else None


def maps_url(name: str, area: str, city: str) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(
        ", ".join(x for x in (name, area, city) if x)
    )


def place_card(p: dict, city: str) -> dict:
    doc = guide.get(p["id"]) or {}
    return {
        "id": p["id"],
        "name": p["name"],
        "kind": "attraction",
        "category": p["category"],
        "area": "",
        "text": doc.get("text", ""),
        "tip": doc.get("tips", ""),
        "lat": p["lat"],
        "lng": p["lng"],
        "rating": p.get("rating"),
        "entry_fee_inr": p.get("entry_fee_inr", 0),
        "wiki": data()["wiki"].get(p["id"], ""),
        "maps_url": maps_url(p["name"], "", city),
        "source": "Safarnama travel guide",
        "photo_url": photo_url(data().get("place_photos", {}).get(p["id"])),
    }


def explore_card(c: dict, city: str) -> dict:
    return {
        "tip": "",
        **c,
        "maps_url": maps_url(c["name"], c.get("area", ""), city),
        "photo_url": photo_url(c.get("photo")),
    }


def city_places(city: str) -> list[dict]:
    return [place_card(p, city) for p in load_fixture("places").get(city, [])]


def landmark(c: dict) -> str | None:
    return next((x["id"] for k in ("attraction", "photo") for x in c["sections"].get(k, []) if x.get("photo") or x.get("image")), None)


def cities() -> list[dict]:
    out = []
    for name, c in data()["cities"].items():
        out.append(
            {
                "name": name,
                "tagline": c["tagline"],
                "tags": c["tags"],
                "lat": c["lat"],
                "lng": c["lng"],
                "banner": c["banner"],
                "photo_id": landmark(c),
                "photo_url": photo_url(c.get("photo")),
                "counts": {k: len(v) for k, v in c["sections"].items()},
            }
        )
    return out


def live_sections(name: str, lat: float | None, lng: float | None) -> dict | None:
    if not google.enabled():
        return None
    try:
        return google.city_sections(name, lat, lng)
    except google.GoogleError:
        return None


def city(name: str) -> dict | None:
    c = data()["cities"].get(name)
    live = live_sections(name, c["lat"] if c else None, c["lng"] if c else None)
    if not c and not live:
        return None
    if not c:
        c = {"tagline": "", "tags": [], "lat": None, "lng": None, "banner": None, "info": {}, "top": [], "source": ""}
    if live:
        sections = live
        top = sorted(live["attraction"], key=lambda x: -(x.get("rating") or 0) * (1 + (x.get("reviews") or 0)) ** 0.1)[
            :8
        ]
    else:
        sections = {k: [explore_card(x, name) for x in v] for k, v in c["sections"].items()}
        by_id = {x["id"]: x for v in sections.values() for x in v}
        top = [by_id[i] for i in c["top"] if i in by_id]
    return {
        "name": name,
        "tagline": c["tagline"],
        "tags": c["tags"],
        "lat": c["lat"],
        "lng": c["lng"],
        "banner": c["banner"],
        "photo_url": photo_url(c.get("photo"), HERO_WIDTH),
        "info": c["info"],
        "top": top,
        "sections": sections,
        "labels": KIND_LABELS,
        "source": c["source"],
        "places_from": "Google Maps" if live else "Wikivoyage",
        "licence": data().get("licence", ""),
    }


@lru_cache
def all_cards() -> dict[str, dict]:
    out = {}
    for name in load_fixture("places"):
        for p in city_places(name):
            out[p["id"]] = p
    for name, c in data()["cities"].items():
        for v in c["sections"].values():
            for x in v:
                out.setdefault(x["id"], explore_card(x, name))
    for r in data()["routes"].values():
        for s in r["stops"]:
            out[s["id"]] = {
                "area": "",
                "tip": "",
                "category": s["kind"],
                **s,
                "maps_url": maps_url(s["name"], "", ""),
                "photo_url": photo_url(s.get("photo")),
            }
    return out


def card(item_id: str) -> dict | None:
    return all_cards().get(item_id)


def city_banner(name: str) -> str | None:
    c = data()["cities"].get(name)
    if not c:
        return None
    if c.get("photo"):
        return c["photo"]
    if c["banner"]:
        return c["banner"]
    spot = landmark(c)
    return all_cards()[spot]["image"] if spot else ""


def progress(origin: tuple, dest: tuple, point: tuple) -> float:
    ax, ay, bx, by, px, py = origin[1], origin[0], dest[1], dest[0], point[1], point[0]
    length = (bx - ax) ** 2 + (by - ay) ** 2
    return ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / length if length else 0.0


def live_stops(a: tuple, b: tuple) -> list[dict]:
    if not google.enabled():
        return []
    try:
        return [
            s | {"on_way": True, "time": "1 to 2 hours"} for s in google.along_route(a, b) if s.get("lat") is not None
        ]
    except google.GoogleError:
        return []


def stops(origin: str, destination: str) -> dict | None:
    routes = data()["routes"]
    r = routes.get(f"{origin}|{destination}") or routes.get(f"{destination}|{origin}")
    if origin not in CITY_COORDS or destination not in CITY_COORDS:
        return None
    a, b = CITY_COORDS[origin], CITY_COORDS[destination]
    live = live_stops(a, b)
    if live:
        r = {"road": (r or {}).get("road", "road"), "stops": live, "source": "Google Maps, along the road from OSRM"}
    if not r:
        return None
    out = []
    for s in r["stops"]:
        here = (s["lat"], s["lng"])
        out.append(
            {
                "area": "",
                "tip": "",
                "category": s["kind"],
                **s,
                "maps_url": maps_url(s["name"], "", ""),
                "photo_url": s.get("photo_url") or photo_url(s.get("photo")),
                "from_start_km": round(km_between(*a, *here)),
                "progress": round(min(1.0, max(0.0, progress(a, b, here))), 3),
            }
        )
    out.sort(key=lambda s: s["progress"])
    return {
        "origin": origin,
        "destination": destination,
        "road": r["road"],
        "stops": out,
        "source": r.get("source", ""),
    }


def food_cards(destination: str) -> list[dict]:
    c = data()["cities"].get(destination)
    live = live_sections(destination, c["lat"] if c else None, c["lng"] if c else None)
    if live:
        cards = live["restaurant"] + live["cafe"]
    elif c:
        cards = [explore_card(x, destination) for k in ("restaurant", "cafe") for x in c["sections"].get(k, [])]
    else:
        cards = []
    return [x for x in cards if x.get("lat") is not None and x.get("lng") is not None]


def meals(destination: str, days: list[dict], base: tuple[float, float] | None) -> list[dict]:
    food = food_cards(destination)
    if not food:
        return []
    places = {p["id"]: p for p in city_places(destination)}
    out, used = [], set()
    for d in days:
        pts = [(places[i]["lat"], places[i]["lng"]) for i in (it.get("place_id") for it in d["items"]) if i in places]
        centre = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) if pts else base
        if not centre:
            continue
        picks = []
        for kind in ("restaurant", "cafe"):
            ranked = sorted(
                (f for f in food if f["kind"] == kind),
                key=lambda f: (f["id"] in used, km_between(*centre, f["lat"], f["lng"])),
            )
            if ranked and km_between(*centre, ranked[0]["lat"], ranked[0]["lng"]) <= MEAL_KM:
                picks.append(ranked[0] | {"km": round(km_between(*centre, ranked[0]["lat"], ranked[0]["lng"]), 1)})
                used.add(ranked[0]["id"])
        if picks:
            out.append({"date": d["date"], "picks": picks})
    return out
