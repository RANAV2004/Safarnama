# vectors
import math
import re
from collections import Counter

STOP = set(
    "a an the and or but of to in on at for with from by is are was were be been it its this that these those i me my we our you your he she they them some any can could would should will just very really also too please want like into out up down over about there here than then so do does did not no yes get got go going".split()
)
SAME = {
    "sea": "beach",
    "seaside": "beach",
    "shore": "beach",
    "calm": "quiet",
    "peaceful": "quiet",
    "relax": "relaxing",
    "children": "kids",
    "shop": "shopping",
    "bazaar": "market",
    "dusk": "sunset",
    "sundown": "sunset",
    "fall": "waterfall",
    "boating": "boat",
    "eat": "food",
    "eating": "food",
    "cuisine": "food",
    "dish": "food",
    "historic": "history",
    "historical": "history",
    "heritage": "history",
    "hike": "hiking",
    "trek": "hiking",
    "view": "views",
    "night": "evening",
    "mountain": "hill",
    "mountains": "hill",
    "hills": "hill",
}


def stem(w: str) -> str:
    if len(w) > 5 and w.endswith(("ches", "shes", "xes")):
        return w[:-2]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us")):
        return w[:-1]
    return w


def tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in STOP:
            continue
        w = SAME.get(w, w)
        w = SAME.get(stem(w), stem(w))
        out.append(w)
    return out


class VectorIndex:
    def __init__(self, docs: list[tuple[str, str]]):
        counts = {i: Counter(tokens(t)) for i, t in docs}
        df = Counter(w for c in counts.values() for w in c)
        n = len(docs)
        self.idf = {w: math.log((n + 1) / (d + 1)) + 1 for w, d in df.items()}
        self.vecs = {i: self.weigh(c) for i, c in counts.items()}

    def weigh(self, c: Counter) -> dict[str, float]:
        v = {w: (1 + math.log(f)) * self.idf.get(w, 0.0) for w, f in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items() if x}

    def embed(self, text: str) -> dict[str, float]:
        return self.weigh(Counter(tokens(text)))

    def search(self, query: str, k: int = 4, allow: set[str] | None = None) -> list[tuple[str, float]]:
        q = self.embed(query)
        scores = []
        for i, v in self.vecs.items():
            if allow is not None and i not in allow:
                continue
            s = sum(x * v.get(w, 0.0) for w, x in q.items())
            if s > 0:
                scores.append((i, round(s, 4)))
        return sorted(scores, key=lambda t: -t[1])[:k]
