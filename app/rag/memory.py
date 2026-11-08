# traveller memory
import json

from app.db import connect, now_iso
from app.profile import get_profile
from app.rag.vectors import VectorIndex
from app.state import Learned

LIKE_AT = 2
AVOID_AT = -2
KEEP = 50


def remember(user: str, city: str, text: str, signals: dict[str, int]):
    with connect() as con:
        con.execute(
            "insert into feedback (user, city, text, signals, created) values (?, ?, ?, ?, ?)",
            (user, city, text, json.dumps(signals), now_iso()),
        )
        con.execute(
            "delete from feedback where user = ? and id not in (select id from feedback where user = ? order by id desc limit ?)",
            (user, user, KEEP),
        )


def items(user: str) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "select city, text, signals, created from feedback where user = ? order by id desc", (user,)
        ).fetchall()
    return [{"city": c, "text": t, "signals": json.loads(s), "created": d} for c, t, s, d in rows]


def scores(user: str) -> dict[str, int]:
    total: dict[str, int] = {}
    for it in items(user):
        for cat, n in it["signals"].items():
            total[cat] = total.get(cat, 0) + n
    return total


def recall(user: str, query: str, k: int = 3) -> list[str]:
    past = items(user)
    if not past or not query.strip():
        return []
    idx = VectorIndex([(str(i), it["text"]) for i, it in enumerate(past)])
    return [past[int(i)]["text"] for i, _ in idx.search(query, k)]


def profile(user: str, query: str = "") -> Learned:
    s = scores(user)
    past = items(user)
    memories = list(dict.fromkeys(recall(user, query) + [it["text"] for it in past]))[:3]
    return Learned(
        likes=sorted(c for c, n in s.items() if n >= LIKE_AT),
        avoids=sorted(c for c, n in s.items() if n <= AVOID_AT),
        memories=memories,
        interests=get_profile(user)["interests"],
    )


def forget(user: str) -> int:
    with connect() as con:
        return con.execute("delete from feedback where user = ?", (user,)).rowcount
