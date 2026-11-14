# builds fixtures/explore.json from Wikivoyage city guides
# run: python -m scripts.build_explore [cache folder]
# text and listings come from Wikivoyage (CC BY-SA 4.0), photos from Wikimedia Commons
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

import mwparserfromhell

RAW = "https://en.wikivoyage.org/w/index.php?title={}&action=raw"
USER_AGENT = "Safarnama/0.1 (https://github.com/RANAV2004/Itinerary-Bot; trip planner)"
OUT = Path(__file__).resolve().parents[1] / "fixtures" / "explore.json"
FILE_URL = "https://commons.wikimedia.org/wiki/Special:FilePath/{}?width={}"

# name shown in the app, Wikivoyage pages (first one gives the travel information), kinds of trip
CITIES = [
    ("Goa", ["Goa", "Panaji", "Calangute", "Anjuna", "Old Goa", "Palolem"], ["beach"]),
    ("Pondicherry", ["Puducherry"], ["beach", "heritage"]),
    ("Gokarna", ["Gokarna"], ["beach", "spiritual"]),
    ("Varkala", ["Varkala"], ["beach"]),
    ("Kochi", ["Kochi", "Fort Kochi"], ["beach", "heritage"]),
    ("Alleppey", ["Alappuzha"], ["nature"]),
    ("Andaman Islands", ["Port Blair", "Havelock Island"], ["beach", "nature"]),
    ("Manali", ["Manali"], ["mountains", "trekking"]),
    ("Mount Abu", ["Mount Abu"], ["mountains", "nature"]),
    ("Lonavala", ["Lonavala"], ["mountains", "trekking"]),
    ("Shimla", ["Shimla"], ["mountains"]),
    ("Dharamshala", ["McLeod Ganj", "Dharamsala"], ["mountains", "trekking", "spiritual"]),
    ("Rishikesh", ["Rishikesh"], ["mountains", "trekking", "spiritual"]),
    ("Mussoorie", ["Mussoorie"], ["mountains"]),
    ("Nainital", ["Nainital"], ["mountains", "nature"]),
    ("Leh", ["Leh"], ["mountains", "trekking"]),
    ("Srinagar", ["Srinagar"], ["mountains", "nature"]),
    ("Darjeeling", ["Darjeeling"], ["mountains", "trekking"]),
    ("Gangtok", ["Gangtok"], ["mountains", "trekking"]),
    ("Ooty", ["Ooty"], ["mountains", "nature"]),
    ("Munnar", ["Munnar"], ["mountains", "nature", "trekking"]),
    ("Kodaikanal", ["Kodaikanal"], ["mountains", "nature", "trekking"]),
    ("Coorg", ["Kodagu", "Madikeri"], ["mountains", "nature", "trekking"]),
    ("Jaipur", ["Jaipur"], ["heritage"]),
    ("Udaipur", ["Udaipur"], ["heritage"]),
    ("Jodhpur", ["Jodhpur"], ["heritage"]),
    ("Jaisalmer", ["Jaisalmer"], ["heritage"]),
    ("Agra", ["Agra"], ["heritage"]),
    ("Varanasi", ["Varanasi"], ["heritage", "spiritual"]),
    ("Amritsar", ["Amritsar"], ["heritage", "spiritual"]),
    ("Khajuraho", ["Khajuraho"], ["heritage"]),
    ("Hampi", ["Hampi"], ["heritage"]),
    ("Mysuru", ["Mysore"], ["heritage"]),
    ("Delhi", ["Delhi"], ["city", "heritage"]),
    ("Mumbai", ["Mumbai"], ["city"]),
    ("Bengaluru", ["Bengaluru"], ["city"]),
    ("Kolkata", ["Kolkata"], ["city", "heritage"]),
    ("Chennai", ["Chennai"], ["city", "beach"]),
    ("Hyderabad", ["Hyderabad"], ["city", "heritage"]),
    ("Kathmandu", ["Kathmandu"], ["nepal", "heritage", "trekking"]),
    ("Pokhara", ["Pokhara"], ["nepal", "mountains", "trekking"]),
]
INFO_SECTIONS = {
    "understand": ["Understand"],
    "get_in": ["Get in"],
    "get_around": ["Get around"],
    "stay_safe": ["Stay safe", "Stay healthy"],
}
CAFE_WORDS = re.compile(r"\b(caf[eé]|coffee|tea\b|bakery|bakehouse|patisserie|juice|chai|dessert|ice cream)", re.I)
PHOTO_WORDS = re.compile(
    r"\b(view ?point|viewpoint|sunset|sunrise|panoram\w*|lake|ghat|falls?|waterfall|beach|peak|valley|meadow|lookout|point|promenade|garden|backwater)\b",
    re.I,
)
LISTING_KINDS = {"see", "do", "eat", "drink", "listing", "marker"}
MAX_PER_KIND = 12
MAX_DISTRICTS = 5
BULLET = re.compile(r"^\*+\s*(?:the\s+)?'''(.+?)'''(.*)$", re.I)
SECTION_KIND = {"see": "see", "do": "do", "eat": "eat", "drink": "drink"}


def get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, ""


def fetch(title: str, cache: Path, client=None) -> str:
    path = cache / (re.sub(r"[^A-Za-z0-9]+", "_", title) + ".txt")
    if path.exists():
        return path.read_text(encoding="utf-8")
    for wait in (5, 15, 30, 60, 120):
        status, text = get(RAW.format(quote(title.replace(" ", "_"), safe="/")))
        if status == 200:
            if m := re.match(r"#REDIRECT\s*\[\[([^\]|#]+)", text, re.I):
                return fetch(m.group(1).strip(), cache)
            path.write_text(text, encoding="utf-8")
            time.sleep(1.5)
            return text
        if status == 404:
            return ""
        print(f"  {title}: status {status}, waiting {wait}s", flush=True)
        time.sleep(wait)
    raise RuntimeError(f"could not fetch {title}")


def plain(code) -> str:
    text = mwparserfromhell.parse(str(code)).strip_code(normalize=True, collapse=True)
    text = re.sub(r"\[\S+ ([^\]]+)\]", r"\1", text)
    text = re.sub(r"\s+", " ", text.replace(" ", " ")).strip()
    return text


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > limit * 0.5 else cut.rsplit(" ", 1)[0] + "..."


def paragraphs(code: str, limit: int) -> str:
    wiki = mwparserfromhell.parse(code)
    for t in wiki.filter_templates(recursive=False):
        try:
            wiki.remove(t)
        except ValueError:
            pass
    for link in wiki.filter_wikilinks(recursive=False):
        if str(link.title).strip().lower().startswith(("file:", "image:")):
            try:
                wiki.remove(link)
            except ValueError:
                pass
    parts = [english(plain(p)) for p in re.split(r"\n\s*\n", str(wiki))]
    parts = [p for p in parts if len(p) > 40 and not p.startswith(("*", "|", "{", "File:", "Image:"))]
    return clip(" ".join(parts), limit)


LANGUAGES = "Hindi|Marathi|Konkani|Kannada|Tamil|Malayalam|Bengali|Bangla|Nepali|Urdu|Punjabi|Telugu|Gujarati|Sanskrit|Tibetan|Ladakhi|Kashmiri|Odia|Rajasthani|Sikkimese|Newar|IAST|ISO|pronounced"


def english(text: str) -> str:
    text = re.sub(r"\s*\((?=[^()]*(?:[^\x00-\x7F]|\b(?:" + LANGUAGES + r")\b))[^()]*\)", "", text)
    text = re.sub(r"[^\x00-\x7F\u00C0-\u017F\u2013\u2014\u2018\u2019\u201C\u201D\u20B9]+", " ", text)
    text = re.sub(r"\(\s*[,;/]*\s*\)", "", text)
    return re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\s{2,}", " ", text)).strip()


def sections(text: str) -> dict[str, str]:
    out, current, buf = {"_lead": ""}, "_lead", []
    for line in text.splitlines():
        if m := re.match(r"^==\s*([^=].*?)\s*==\s*$", line):
            out[current] = "\n".join(buf)
            current, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    out[current] = "\n".join(buf)
    return out


def number(v: str) -> float | None:
    try:
        return round(float(v.strip()), 5)
    except ValueError:
        return None


def city_point(text: str) -> tuple[float, float] | None:
    m = re.search(r"\{\{geo\|\s*(-?[\d.]+)\s*\|\s*(-?[\d.]+)", text, re.I)
    return (round(float(m.group(1)), 4), round(float(m.group(2)), 4)) if m else None


def banner(text: str) -> str | None:
    m = re.search(r"\{\{pagebanner\s*\|\s*([^|}]+\.(?:jpe?g|png))", text, re.I)
    name = m.group(1).strip() if m else None
    return None if not name or "default" in name.lower() else name


def file_url(name: str, width: int) -> str:
    return FILE_URL.format(quote(name.replace(" ", "_")), width)


def listings(text: str, page: str) -> list[dict]:
    out = []
    for section, body in sections(text).items():
        sec = section.lower()
        for t in mwparserfromhell.parse(body).filter_templates():
            kind = str(t.name).strip().lower()
            if kind not in LISTING_KINDS:
                continue
            p = {str(x.name).strip().lower(): str(x.value).strip() for x in t.params}
            if kind in ("listing", "marker"):
                kind = (p.get("type") or "").lower() or {"see": "see", "do": "do", "eat": "eat", "drink": "drink"}.get(
                    sec, ""
                )
            if kind not in ("see", "do", "eat", "drink"):
                continue
            name = plain(p.get("name", "")).rstrip(" :")
            content = english(plain(p.get("content", "")))
            if not name or len(name) > 80 or len(content) < 25:
                continue
            out.append(
                {
                    "kind": kind,
                    "name": name,
                    "area": clip(plain(p.get("address", "")) or plain(p.get("directions", "")), 70),
                    "text": clip(content, 320),
                    "hours": clip(plain(p.get("hours", "")), 80),
                    "price": clip(plain(p.get("price", "")), 80),
                    "lat": number(p.get("lat", "")),
                    "lng": number(p.get("long", "")),
                    "image": (p.get("image") or "").strip() or None,
                    "wiki": (p.get("wikipedia") or "").strip() or None,
                    "wikidata": (p.get("wikidata") or "").strip() or None,
                    "page": page,
                }
            )
    return out


def bullets(text: str, page: str) -> list[dict]:
    out = []
    for section, body in sections(text).items():
        kind = SECTION_KIND.get(section.lower())
        if not kind:
            continue
        for line in body.splitlines():
            m = BULLET.match(line.strip())
            if not m or "{{" in m.group(1):
                continue
            name = plain(m.group(1))
            rest = english(plain(m.group(2))).lstrip(" ,.:;-–—")
            content = rest if len(rest) >= 25 else ""
            if line.strip().lower().startswith(("* the ", "*the ")):
                content = english(plain(line.strip().lstrip("* ")))
            if not name or len(name) > 80 or len(content) < 25:
                continue
            out.append(
                {
                    "kind": kind,
                    "name": name,
                    "area": "",
                    "text": clip(content, 320),
                    "hours": "",
                    "price": "",
                    "lat": None,
                    "lng": None,
                    "image": None,
                    "wiki": None,
                    "wikidata": None,
                    "page": page,
                }
            )
    return out


def page_items(text: str, page: str) -> list[dict]:
    items = listings(text, page)
    names = {x["name"].lower() for x in items}
    return items + [x for x in bullets(text, page) if x["name"].lower() not in names]


def districts(text: str, title: str) -> list[str]:
    found = re.findall(r"\[\[(" + re.escape(title) + r"/[^\]|#]+)", text)
    return list(dict.fromkeys(found))[:MAX_DISTRICTS]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def card(item: dict, city: str, kind: str) -> dict:
    d = {
        "id": f"x-{slug(city)}-{slug(item['name'])}"[:70],
        "name": item["name"].rstrip(" :"),
        "kind": kind,
        "category": kind,
        "area": item["area"],
        "text": item["text"],
        "lat": item["lat"],
        "lng": item["lng"],
        "source": item["page"],
    }
    for k in ("hours", "price"):
        if item[k]:
            d[k] = item[k]
    if item["image"]:
        d["image"] = item["image"]
    if item["wiki"]:
        d["wiki"] = item["wiki"]
    if item["wikidata"]:
        d["wikidata"] = item["wikidata"]
    return d


def pick(items: list[dict], limit: int) -> list[dict]:
    ranked = sorted(items, key=lambda x: (not (x["image"] or x["wiki"] or x["wikidata"]), x["lat"] is None))
    seen, out = set(), []
    for x in ranked:
        if x["name"].lower() in seen:
            continue
        seen.add(x["name"].lower())
        out.append(x)
    return out[:limit]


def tagline(lead: str) -> str:
    if not lead:
        return ""
    first = re.sub(r"\s*\([^()]*\)", "", lead.split(". ")[0]).strip(" .,")
    return clip(first + ".", 120)


def build_city(name: str, pages: list[str], tags: list[str], cache: Path, client=None) -> dict:
    found = [(p, fetch(p, cache, client)) for p in pages]
    found = [(p, text) for p, text in found if text]
    if not found:
        raise RuntimeError(f"no Wikivoyage page for {name}")
    first, main = found[0]
    secs = sections(main)
    info = {"intro": paragraphs(secs["_lead"], 700)}
    for key, heads in INFO_SECTIONS.items():
        body = next((secs[h] for h in heads if h in secs), "")
        if body:
            info[key] = paragraphs(body, 900)
    all_items = page_items(main, first)
    for page, text in found[1:]:
        all_items += page_items(text, page)
    see_n = len([x for x in all_items if x["kind"] == "see"])
    eat_n = len([x for x in all_items if x["kind"] == "eat"])
    if "seedistricts" in main.lower() or see_n < 5 or eat_n < 3:
        for page in districts(main, first):
            all_items += page_items(fetch(page, cache, client), page)
    see = [x for x in all_items if x["kind"] == "see"]
    eat = [x for x in all_items if x["kind"] == "eat"]
    drink = [x for x in all_items if x["kind"] == "drink"]
    cafes = [x for x in eat + drink if CAFE_WORDS.search(x["name"] + " " + x["text"][:120])]
    cafe_names = {x["name"] for x in cafes}
    restaurants = [x for x in eat if x["name"] not in cafe_names]
    photo = [x for x in see if PHOTO_WORDS.search(x["name"] + " " + x["text"][:160])]
    photo += [x for x in all_items if x["kind"] == "do" and PHOTO_WORDS.search(x["name"])]
    do = [x for x in all_items if x["kind"] == "do"]
    attractions = pick(see, MAX_PER_KIND)
    if len(attractions) < MAX_PER_KIND:
        taken = {x["name"].lower() for x in attractions}
        attractions += pick([x for x in do if x["name"].lower() not in taken], MAX_PER_KIND - len(attractions))
    sections_out = {
        "attraction": [card(x, name, "attraction") for x in attractions],
        "restaurant": [card(x, name, "restaurant") for x in pick(restaurants, MAX_PER_KIND)],
        "cafe": [card(x, name, "cafe") for x in pick(cafes, MAX_PER_KIND)],
        "photo": [card(x, name, "photo") for x in pick(photo, MAX_PER_KIND)],
    }
    lead = info["intro"]
    point = city_point(main)
    return {
        "name": name,
        "tags": tags,
        "tagline": tagline(lead),
        "lat": point[0] if point else None,
        "lng": point[1] if point else None,
        "banner": file_url(b, 1400) if (b := banner(main)) else None,
        "info": info,
        "top": [c["id"] for c in sections_out["attraction"][:8]],
        "sections": sections_out,
        "source": f"https://en.wikivoyage.org/wiki/{quote(first.replace(' ', '_'))}",
    }


def main(cache_dir: str = "data/wikivoyage") -> int:
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    cities = {}
    for name, pages, tags in CITIES:
        city = build_city(name, pages, tags, cache, None)
        counts = {k: len(v) for k, v in city["sections"].items()}
        print(f"{name:16} {counts} info={sorted(city['info'])}", flush=True)
        cities[name] = city
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    data = {
        "licence": "Text and listings from Wikivoyage, CC BY-SA 4.0. Photos from Wikimedia Commons under their own licences.",
        "cities": cities,
        "wiki": old.get("wiki", {}),
        "routes": old.get("routes", {}),
    }
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
