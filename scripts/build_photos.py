# adds a real photo to every city, place, stop and restaurant in fixtures/explore.json
# photos are Wikimedia Commons files: the main image (P18) of the place's Wikidata item,
# the photo named in its Wikivoyage listing, or for restaurants and cafes a photo of the
# region's food from Wikipedia's cuisine articles
# run: python -m scripts.build_photos [cache folder]
import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "explore.json"
USER_AGENT = "Safarnama/0.1 (https://github.com/RANAV2004/Itinerary-Bot; trip planner)"
ITEM_BY_TITLE = "https://www.wikidata.org/wiki/Special:ItemByTitle/enwiki/{}"
ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
RAW = "https://en.wikipedia.org/w/index.php?title={}&action=raw"
NEAR_KM = 35
HOME_COUNTRIES = {"Q668", "Q837"}
CAPTION = re.compile(r"\[\[(?:File|Image):([^|\]]+\.(?:jpe?g|png))((?:\|[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*)*)\]\]", re.I)
GALLERY = re.compile(r"^\s*(?:File|Image):([^|\n]+\.(?:jpe?g|png))\|?(.*)$", re.I | re.M)
LITTLE = {"the", "and", "of", "in", "at", "a", "an", "to", "for", "on", "by"}
CITY_ARTICLES = {
    "Goa": "Goa",
    "Pondicherry": "Pondicherry",
    "Gokarna": "Gokarna, Karnataka",
    "Varkala": "Varkala",
    "Kochi": "Kochi",
    "Alleppey": "Alappuzha",
    "Andaman Islands": "Andaman Islands",
    "Manali": "Manali, Himachal Pradesh",
    "Mount Abu": "Mount Abu",
    "Lonavala": "Lonavala",
    "Shimla": "Shimla",
    "Dharamshala": "Dharamshala",
    "Rishikesh": "Rishikesh",
    "Mussoorie": "Mussoorie",
    "Nainital": "Nainital",
    "Leh": "Leh",
    "Srinagar": "Srinagar",
    "Darjeeling": "Darjeeling",
    "Gangtok": "Gangtok",
    "Ooty": "Ooty",
    "Munnar": "Munnar",
    "Kodaikanal": "Kodaikanal",
    "Coorg": "Kodagu district",
    "Jaipur": "Jaipur",
    "Udaipur": "Udaipur",
    "Jodhpur": "Jodhpur",
    "Jaisalmer": "Jaisalmer",
    "Agra": "Taj Mahal",
    "Varanasi": "Varanasi",
    "Amritsar": "Golden Temple",
    "Khajuraho": "Khajuraho Group of Monuments",
    "Hampi": "Hampi",
    "Mysuru": "Mysore Palace",
    "Delhi": "India Gate",
    "Mumbai": "Gateway of India",
    "Bengaluru": "Bangalore Palace",
    "Kolkata": "Victoria Memorial, Kolkata",
    "Chennai": "Marina Beach",
    "Hyderabad": "Charminar",
    "Kathmandu": "Kathmandu",
    "Pokhara": "Pokhara",
}
CUISINES = {
    "Goa": "Goan cuisine",
    "Pondicherry": "Tamil cuisine",
    "Gokarna": "Mangalorean cuisine",
    "Varkala": "Cuisine of Kerala",
    "Kochi": "Cuisine of Kerala",
    "Alleppey": "Cuisine of Kerala",
    "Andaman Islands": "Bengali cuisine",
    "Manali": "Himachali cuisine",
    "Mount Abu": "Rajasthani cuisine",
    "Lonavala": "Marathi cuisine",
    "Shimla": "Himachali cuisine",
    "Dharamshala": "Tibetan cuisine",
    "Rishikesh": "Kumauni cuisine",
    "Mussoorie": "Kumauni cuisine",
    "Nainital": "Kumauni cuisine",
    "Leh": "Tibetan cuisine",
    "Srinagar": "Kashmiri cuisine",
    "Darjeeling": "Sikkimese cuisine",
    "Gangtok": "Sikkimese cuisine",
    "Ooty": "Tamil cuisine",
    "Munnar": "Cuisine of Kerala",
    "Kodaikanal": "Tamil cuisine",
    "Coorg": "Kodava cuisine",
    "Jaipur": "Rajasthani cuisine",
    "Udaipur": "Rajasthani cuisine",
    "Jodhpur": "Rajasthani cuisine",
    "Jaisalmer": "Rajasthani cuisine",
    "Agra": "Mughlai cuisine",
    "Varanasi": "Cuisine of Uttar Pradesh",
    "Amritsar": "Punjabi cuisine",
    "Khajuraho": "Cuisine of Uttar Pradesh",
    "Hampi": "Cuisine of Karnataka",
    "Mysuru": "Cuisine of Karnataka",
    "Delhi": "Mughlai cuisine",
    "Mumbai": "Marathi cuisine",
    "Bengaluru": "Cuisine of Karnataka",
    "Kolkata": "Bengali cuisine",
    "Chennai": "Tamil cuisine",
    "Hyderabad": "Hyderabadi cuisine",
    "Kathmandu": "Nepalese cuisine",
    "Pokhara": "Nepalese cuisine",
}
CAFE_ARTICLES = ["Indian filter coffee", "Masala chai", "Coffeehouse", "Café"]
SKIP_FILE = re.compile(r"\.(svg|gif|tif|tiff|webm|ogg|ogv|pdf)$|logo|map|flag|icon|seal|emblem|symbol|locator|coat of arms", re.I)
FILE_LINK = re.compile(r"(?:\[\[(?:File|Image):|\|\s*image\d*\s*=\s*|\n\s*(?:File|Image):)([^|\]\n{}]+\.(?:jpe?g|png))", re.I)


def get(url: str, cache: Path) -> tuple[str, str]:
    key = hashlib.sha1(url.encode()).hexdigest()
    path = cache / f"{key}.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        return saved["url"], saved["body"]
    for wait in (5, 15, 30, 60, 120):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                final, body = r.geturl(), r.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                final, body = "", ""
                break
            print(f"  {e.code} for {url[:80]}, waiting {wait}s", flush=True)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  {type(e).__name__} for {url[:80]}, waiting {wait}s", flush=True)
            time.sleep(wait)
    else:
        return "", ""
    path.write_text(json.dumps({"url": final, "body": body}), encoding="utf-8")
    time.sleep(0.8)
    return final, body


def qid_for_title(title: str, cache: Path) -> str | None:
    final, _ = get(ITEM_BY_TITLE.format(quote(title.replace(" ", "_"), safe="")), cache)
    m = re.search(r"/(Q\d+)$", final or "")
    return m.group(1) if m else None


def entity(qid: str, cache: Path) -> dict:
    _, body = get(ENTITY.format(qid), cache)
    try:
        return next(iter(json.loads(body)["entities"].values()))
    except (ValueError, KeyError, StopIteration):
        return {}


def claim(e: dict, prop: str):
    for c in e.get("claims", {}).get(prop, []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if v:
            return v
    return None


def km(a: tuple, b: tuple) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def photo_of(qid: str | None, near: tuple | None, cache: Path, check: bool) -> str | None:
    if not qid:
        return None
    e = entity(qid, cache)
    if check and near:
        where = claim(e, "P625")
        if where and km(near, (where["latitude"], where["longitude"])) > NEAR_KM:
            return None
        if not where and (claim(e, "P17") or {}).get("id") not in HOME_COUNTRIES:
            return None
    image = claim(e, "P18")
    return image if isinstance(image, str) and not SKIP_FILE.search(image) else None


def article_photos(title: str, cache: Path) -> list[str]:
    _, body = get(RAW.format(quote(title.replace(" ", "_"), safe="")), cache)
    if m := re.match(r"#REDIRECT\s*\[\[([^\]|#]+)", body, re.I):
        _, body = get(RAW.format(quote(m.group(1).strip().replace(" ", "_"), safe="")), cache)
    files = [f.strip() for f in FILE_LINK.findall(body)]
    return list(dict.fromkeys(f for f in files if not SKIP_FILE.search(f)))


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in LITTLE}


def page_photos(pages: list[str]) -> list[tuple[str, set[str]]]:
    out = []
    for text in pages:
        for m in list(CAPTION.finditer(text)) + list(GALLERY.finditer(text)):
            file = m.group(1).strip()
            if SKIP_FILE.search(file) or re.search(r"banner|default", file, re.I):
                continue
            out.append((file, words(file.rsplit(".", 1)[0].replace("_", " ") + " " + m.group(2))))
    return out


def caption_match(card: dict, photos: list[tuple[str, set[str]]]) -> str | None:
    want = words(card["name"])
    if not want or (len(want) == 1 and len(next(iter(want))) < 5):
        return None
    return next((file for file, have in photos if want <= have), None)


def place_photo(card: dict, city_point: tuple | None, cache: Path) -> str | None:
    if card.get("image") and not re.search(r"banner", card["image"], re.I):
        return card["image"]
    near = (card["lat"], card["lng"]) if card.get("lat") is not None else city_point
    if card.get("wikidata"):
        found = photo_of(card["wikidata"], near, cache, check=False)
        if found:
            return found
    if card.get("wiki"):
        found = photo_of(qid_for_title(card["wiki"], cache), near, cache, check=False)
        if found:
            return found
    if card["kind"] in ("attraction", "photo") and near:
        return photo_of(qid_for_title(card["name"], cache), near, cache, check=True)
    return None


def main(cache_dir: str = "data/photos", wikivoyage_dir: str = "") -> int:
    cache = Path(cache_dir)
    pages_dir = Path(wikivoyage_dir) if wikivoyage_dir else None
    cache.mkdir(parents=True, exist_ok=True)
    data = json.loads(OUT.read_text(encoding="utf-8"))
    cafe_pool = [f for t in CAFE_ARTICLES for f in article_photos(t, cache)][:12]
    for name, city in data["cities"].items():
        point = (city["lat"], city["lng"]) if city.get("lat") is not None else None
        city["photo"] = photo_of(qid_for_title(CITY_ARTICLES.get(name, name), cache), None, cache, check=False)
        food = article_photos(CUISINES.get(name, "Indian cuisine"), cache) or article_photos("Indian cuisine", cache)
        counts = {"own": 0, "food": 0, "none": 0}
        sources = {c.get("source", "") for cards in city["sections"].values() for c in cards}
        texts = []
        if pages_dir:
            for page in sources:
                path = pages_dir / (re.sub(r"[^A-Za-z0-9]+", "_", page) + ".txt")
                if path.exists():
                    texts.append(path.read_text(encoding="utf-8"))
        captions = page_photos(texts)
        used_food = used_cafe = 0
        for kind, cards in city["sections"].items():
            for card in cards:
                card.pop("photo", None)
                card.pop("photo_note", None)
                found = place_photo(card, point, cache) or caption_match(card, captions)
                if found:
                    card["photo"] = found
                    counts["own"] += 1
                elif kind == "restaurant" and food:
                    card["photo"], card["photo_note"] = food[used_food % len(food)], "Typical local dish"
                    used_food += 1
                    counts["food"] += 1
                elif kind == "cafe" and cafe_pool:
                    card["photo"], card["photo_note"] = cafe_pool[used_cafe % len(cafe_pool)], "Typical cafe"
                    used_cafe += 1
                    counts["food"] += 1
                else:
                    counts["none"] += 1
        if not city["photo"]:
            city["photo"] = next((c["photo"] for c in city["sections"]["attraction"] if c.get("photo")), None)
        print(f"{name:16} city photo {'yes' if city['photo'] else 'NO '} {counts}", flush=True)
    for key, route in data["routes"].items():
        found = 0
        for stop in route["stops"]:
            here = (stop["lat"], stop["lng"])
            photo = photo_of(qid_for_title(stop["name"], cache), here, cache, check=True)
            if not photo and stop.get("image") and not re.search(r"banner|default", stop["image"], re.I):
                photo = stop["image"]
            stop.pop("photo", None)
            if photo:
                stop["photo"] = photo
                found += 1
        print(f"{key:18} stops with photos {found}/{len(route['stops'])}", flush=True)
    data["place_photos"] = {}
    for pid, title in data.get("wiki", {}).items():
        photo = photo_of(qid_for_title(title, cache), None, cache, check=False)
        if photo:
            data["place_photos"][pid] = photo
    print(f"planner places with photos {len(data['place_photos'])}/{len(data.get('wiki', {}))}", flush=True)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
