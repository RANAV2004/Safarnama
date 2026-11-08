# entity tagging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.rag.vectors import SAME, STOP, stem

CATEGORY = {
    "beach": "beach",
    "history": "history",
    "fort": "history",
    "palace": "history",
    "museum": "history",
    "monument": "history",
    "shopping": "shopping",
    "market": "shopping",
    "nature": "nature",
    "waterfall": "nature",
    "lake": "nature",
    "garden": "nature",
    "zoo": "nature",
    "hill": "nature",
    "culture": "culture",
    "temple": "culture",
    "church": "culture",
    "dance": "culture",
    "science": "science",
}
GENERIC = set(CATEGORY) | {
    "city",
    "state",
    "ride",
    "boat",
    "show",
    "jeep",
    "safari",
    "art",
    "gallery",
    "bari",
    "ki",
    "st",
    "inn",
    "hotel",
    "hostel",
    "residency",
    "resort",
    "lodge",
    "stay",
    "room",
    "homestay",
}
MODES = {
    "flight": "flight",
    "fly": "flight",
    "plane": "flight",
    "air": "flight",
    "train": "train",
    "rail": "train",
    "bus": "bus",
    "coach": "bus",
}
UNITS = {"k": 1000, "thousand": 1000, "lakh": 100000, "lakhs": 100000}
WORD = re.compile(r"[a-z]+|\d[\d,]*(?:\.\d+)?")


@dataclass
class Tagged:
    text: str
    masked: str
    places: list[str] = field(default_factory=list)
    stays: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    modes: list[str] = field(default_factory=list)
    numbers: list[int] = field(default_factory=list)


def norm(w: str) -> str:
    w = SAME.get(w, w)
    s = stem(w)
    return SAME.get(s, s)


def close(a: str, b: str) -> bool:
    return a == b or (len(a) >= 5 and len(b) >= 5 and SequenceMatcher(None, a, b).ratio() >= 0.8)


def city_words(city: str) -> set[str]:
    return {norm(w) for w in WORD.findall(city.lower())} | ({"mysore"} if city == "Mysuru" else set())


def candidates(normed: list[str], items: list, kind: str, cw: set[str]) -> list[tuple]:
    out = []
    for it in items:
        name = [n for n in (norm(w) for w in WORD.findall(it.name.lower()) if w not in STOP) if n not in cw]
        key = [w for w in name if w not in GENERIC]
        if key:
            hit = {i for i, w in enumerate(normed) if any(close(w, k) for k in key)}
        else:
            hit = {i for i, w in enumerate(normed) if w in name} if name and all(n in normed for n in name) else set()
        if not hit:
            continue
        span = hit | {i for i, w in enumerate(normed) if w in name and any(abs(i - j) <= 2 for j in hit)}
        matched = len({normed[i] for i in hit})
        out.append((matched / max(len(key) or len(name), 1), len(span), kind, it.id, span))
    return out


def tag(text: str, places: list, stays: list, city: str) -> Tagged:
    words = WORD.findall(text.lower())
    normed = [norm(w) for w in words]
    cw = city_words(city)
    cands = candidates(normed, places, "place", cw) + candidates(normed, stays, "hotel", cw)
    t, taken = Tagged(text=text, masked=""), {}
    for _, _, kind, item_id, span in sorted(cands, key=lambda c: (-c[0], -c[1])):
        if span & set(taken):
            continue
        for i in span:
            taken[i] = kind
        (t.places if kind == "place" else t.stays).append(item_id)
    out = []
    for i, (w, n) in enumerate(zip(words, normed, strict=True)):
        if i in taken:
            tok = f"_{taken[i]}_"
        elif w[0].isdigit():
            unit = words[i + 1] if i + 1 < len(words) else ""
            t.numbers.append(int(float(w.replace(",", "")) * UNITS.get(unit, 1)))
            tok = "_num_"
        elif w in UNITS and i > 0 and words[i - 1][0].isdigit():
            continue
        elif n in MODES:
            t.modes.append(MODES[n])
            tok = "_mode_"
        elif n in CATEGORY:
            t.kinds.append(n)
            tok = "_kind_"
        else:
            tok = w
        if out and out[-1] == tok and tok.startswith("_"):
            continue
        out.append(tok)
    t.masked = " ".join(out)
    return t
