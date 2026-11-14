# travel guide
import json
from functools import lru_cache
from pathlib import Path

from app.db import connect
from app.rag.vectors import VectorIndex

GUIDE_FILE = Path(__file__).resolve().parents[2] / "fixtures" / "guide.json"


@lru_cache
def docs() -> dict[str, dict]:
    return {d["id"]: d for d in json.loads(GUIDE_FILE.read_text(encoding="utf-8"))}


def doc_text(d: dict) -> str:
    return " ".join(
        [d["title"], d["title"], d.get("category", ""), d["text"], d.get("tips", ""), " ".join(d.get("tags", []))]
    )


def learned_words() -> dict[str, str]:
    with connect() as con:
        return dict(
            con.execute("select place_id, group_concat(text, ' ') from place_words group by place_id").fetchall()
        )


@lru_cache(maxsize=8)
def build_index(extra: tuple[tuple[str, str], ...]) -> VectorIndex:
    more = dict(extra)
    return VectorIndex([(i, doc_text(d) + " " + more.get(i, "")) for i, d in docs().items()])


def index() -> VectorIndex:
    return build_index(tuple(sorted(learned_words().items())))


def get(doc_id: str) -> dict | None:
    return docs().get(doc_id)


def search(query: str, city: str | None = None, k: int = 4, only: set[str] | None = None) -> list[dict]:
    allow = {
        i
        for i, d in docs().items()
        if (city is None or d["city"] == city) and (only is None or i in only or d["kind"] == "city")
    }
    return [{**docs()[i], "score": s} for i, s in index().search(query, k, allow)]


def snippet(d: dict) -> str:
    return f"{d['title']}: {d['text']}" + (f" Tip: {d['tips']}" if d.get("tips") else "")
