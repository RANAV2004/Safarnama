# photos and short summaries from Wikipedia, cached in the database
import json
import os
import time
from urllib.parse import quote

import httpx

from app.db import connect

URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
USER_AGENT = "Safarnama/0.1 (https://github.com/RANAV2004/Itinerary-Bot; trip planner)"
TIMEOUT = 4
KEEP_FOUND = 30 * 86400
KEEP_MISSING = 3600


COMMONS = "https://commons.wikimedia.org/wiki/"


def commons(file: str, name: str, width: int = 800) -> dict:
    path = quote(file.replace(" ", "_"))
    return {
        "title": name,
        "extract": "",
        "image": f"{COMMONS}Special:FilePath/{path}?width={width}",
        "page": f"{COMMONS}File:{path}",
    }


def enabled() -> bool:
    return os.getenv("WIKI_MODE", "live") == "live"


def cached(con, title: str, now: float) -> tuple[bool, dict | None]:
    row = con.execute("select data, fetched from wiki_cache where title = ?", (title,)).fetchone()
    if not row:
        return False, None
    found = row[0] is not None
    if now - row[1] > (KEEP_FOUND if found else KEEP_MISSING):
        return False, None
    return True, json.loads(row[0]) if found else None


def fetch(title: str) -> dict | None:
    try:
        r = httpx.get(
            URL + quote(title.replace(" ", "_"), safe=""),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        if r.status_code != 200:
            return None
        d = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    image = (d.get("thumbnail") or {}).get("source")
    if image and not image.startswith("https://upload.wikimedia.org/"):
        image = None
    return {
        "title": d.get("title", title),
        "extract": (d.get("extract") or "")[:600],
        "image": image,
        "page": ((d.get("content_urls") or {}).get("desktop") or {}).get("page", ""),
    }


def summary(title: str, now: float | None = None) -> dict | None:
    now = now or time.time()
    with connect() as con:
        hit, value = cached(con, title, now)
    if hit:
        return value
    if not enabled():
        return None
    value = fetch(title)
    with connect() as con:
        con.execute(
            "insert into wiki_cache (title, data, fetched) values (?, ?, ?)"
            " on conflict(title) do update set data = excluded.data, fetched = excluded.fetched",
            (title, json.dumps(value) if value else None, now),
        )
    return value
