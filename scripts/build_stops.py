# finds real stops on the way for each route: the road comes from OSRM, the towns and
# places come from Wikivoyage region pages, and each stop gets its Wikivoyage intro and a place to eat
# run: python -m scripts.build_stops [cache folder]
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

import mwparserfromhell

from scripts.build_explore import (
    USER_AGENT,
    banner,
    city_point,
    clip,
    fetch,
    page_items,
    paragraphs,
    sections,
)

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "explore.json"
OSRM = "https://router.project-osrm.org/route/v1/driving/{},{};{},{}?overview=full&geometries=geojson"
STATES = {
    "Mumbai|Goa": ["Maharashtra", "Goa"],
    "Indore|Goa": ["Madhya Pradesh", "Maharashtra", "Karnataka", "Goa"],
    "Bengaluru|Goa": ["Karnataka", "Goa"],
    "Delhi|Jaipur": ["Haryana", "Rajasthan"],
    "Delhi|Udaipur": ["Haryana", "Rajasthan"],
    "Mumbai|Udaipur": ["Maharashtra", "Gujarat", "Rajasthan"],
    "Indore|Udaipur": ["Madhya Pradesh", "Rajasthan"],
    "Bengaluru|Mysuru": ["Karnataka"],
}
ENDS = {
    "Indore": (22.72, 75.86),
    "Mumbai": (19.08, 72.88),
    "Bengaluru": (12.97, 77.59),
    "Delhi": (28.61, 77.21),
    "Goa": (15.49, 73.83),
    "Jaipur": (26.91, 75.79),
    "Udaipur": (24.58, 73.71),
    "Mysuru": (12.30, 76.64),
}
SKIP = {"Mumbai", "Goa", "Delhi", "Bengaluru", "Bangalore", "Jaipur", "Udaipur", "Indore", "Mysore", "Mysuru", "Pune"}
ON_WAY_KM = 15
DETOUR_KM = 45
END_KM = 50
MAX_STOPS = 10
KINDS = [
    ("beach", r"\bbeach"),
    ("nature", r"hill station|waterfall|\bfalls\b|national park|sanctuary|wildlife|lake|valley|ghat|forest|bird"),
    ("history", r"\bfort|palace|ruin|caves?\b|heritage|unesco|histor"),
    ("culture", r"temple|pilgrim|shrine|church|mosque|dargah|holy"),
]


def regions(text: str) -> list[str]:
    out = []
    for t in mwparserfromhell.parse(text).filter_templates():
        if str(t.name).strip().lower() != "regionlist":
            continue
        for p in t.params:
            if re.fullmatch(r"region\d+name", str(p.name).strip()):
                m = re.search(r"\[\[([^\]|#]+)", str(p.value))
                if m:
                    out.append(m.group(1).strip())
    return out


def markers(text: str) -> list[dict]:
    out = []
    secs = sections(text)
    for head in ("Cities", "Other destinations"):
        for t in mwparserfromhell.parse(secs.get(head, "")).filter_templates():
            if str(t.name).strip().lower() != "marker":
                continue
            p = {str(x.name).strip().lower(): str(x.value).strip() for x in t.params}
            m = re.search(r"\[\[([^\]|#]+)", p.get("name", ""))
            if not m:
                continue
            lat, lng = p.get("lat"), p.get("long")
            out.append(
                {
                    "title": m.group(1).strip(),
                    "lat": float(lat) if lat else None,
                    "lng": float(lng) if lng else None,
                    "image": p.get("image") or None,
                    "type": p.get("type", "city"),
                }
            )
    return out


def km(a: tuple, b: tuple) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def road(a: str, b: str, cache: Path) -> list[tuple[float, float]]:
    path = cache / f"osrm_{a}_{b}.json"
    if not path.exists():
        (la1, lo1), (la2, lo2) = ENDS[a], ENDS[b]
        req = urllib.request.Request(OSRM.format(lo1, la1, lo2, la2), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as r:
            path.write_text(r.read().decode(), encoding="utf-8")
    coords = json.loads(path.read_text(encoding="utf-8"))["routes"][0]["geometry"]["coordinates"]
    return [(lat, lng) for lng, lat in coords]


def along(points: list[tuple], here: tuple) -> tuple[float, float]:
    total, best, best_at, run = 0.0, 1e9, 0.0, 0.0
    for i in range(1, len(points)):
        total += km(points[i - 1], points[i])
    for i, p in enumerate(points):
        if i:
            run += km(points[i - 1], p)
        d = km(p, here)
        if d < best:
            best, best_at = d, run
    return best, best_at / total if total else 0.0


def kind_of(text: str, marker_type: str) -> str:
    low = text.lower()
    for kind, pattern in KINDS:
        if re.search(pattern, low):
            return kind
    return "nature" if marker_type == "other" else "town"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def candidates(states: list[str], cache: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for state in states:
        text = fetch(state, cache)
        pages = [state] + regions(text)
        for page in pages:
            body = text if page == state else fetch(page, cache)
            for m in markers(body):
                if m["title"] not in SKIP:
                    found.setdefault(m["title"], m)
            for sub in regions(body) if page != state else []:
                for m in markers(fetch(sub, cache)):
                    if m["title"] not in SKIP:
                        found.setdefault(m["title"], m)
    return found


def stop_for(m: dict, cache: Path) -> dict | None:
    text = fetch(m["title"], cache)
    if not text:
        return None
    point = (m["lat"], m["lng"]) if m["lat"] is not None else city_point(text)
    if not point:
        return None
    intro = paragraphs(sections(text)["_lead"], 360)
    if len(intro) < 40:
        return None
    eats = [x for x in page_items(text, m["title"]) if x["kind"] == "eat"]
    image = m["image"] or banner(text)
    stop = {
        "id": f"rt-{slug(m['title'])}"[:60],
        "name": m["title"],
        "kind": kind_of(intro, m["type"]),
        "text": intro,
        "lat": round(point[0], 4),
        "lng": round(point[1], 4),
        "source": f"https://en.wikivoyage.org/wiki/{m['title'].replace(' ', '_')}",
    }
    if image:
        stop["image"] = image
    if eats:
        stop["eat"] = {"name": eats[0]["name"], "text": clip(eats[0]["text"], 160)}
    return stop


def build_route(key: str, cache: Path) -> dict:
    a, b = key.split("|")
    points = road(a, b, cache)
    start, end = ENDS[a], ENDS[b]
    total = sum(km(points[i - 1], points[i]) for i in range(1, len(points)))
    end_km = min(END_KM, total * 0.15)
    picked = []
    for m in candidates(STATES[key], cache).values():
        if m["lat"] is not None:
            near, _ = along(points, (m["lat"], m["lng"]))
            if near > DETOUR_KM:
                continue
        stop = stop_for(m, cache)
        if not stop:
            continue
        here = (stop["lat"], stop["lng"])
        near, at = along(points, here)
        if near > DETOUR_KM or km(here, start) < end_km or km(here, end) < end_km:
            continue
        stop["on_way"] = near <= ON_WAY_KM
        stop["detour_km"] = round(near)
        stop["time"] = "1 to 2 hours" if stop["on_way"] else "Half a day"
        picked.append((at, stop))
    picked.sort(key=lambda x: x[0])
    chosen = []
    for at, stop in sorted(picked, key=lambda x: (not x[1]["on_way"], -len(x[1]["text"]))):
        if len(chosen) >= MAX_STOPS:
            break
        if all(abs(at - c[0]) > 0.04 for c in chosen):
            chosen.append((at, stop))
    chosen.sort(key=lambda x: x[0])
    print(f"{key:18} road {round(total)} km, {len(picked)} candidates, kept {len(chosen)}", flush=True)
    return {
        "road": f"road, about {round(total)} km",
        "km": round(total),
        "stops": [s for _, s in chosen],
        "source": "Road from OpenStreetMap via OSRM, stops from Wikivoyage",
    }


def main(cache_dir: str = "data/wikivoyage") -> int:
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    data = json.loads(OUT.read_text(encoding="utf-8"))
    data["routes"] = {key: build_route(key, cache) for key in STATES}
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
