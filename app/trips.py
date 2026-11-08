# saved itineraries and the friends they are shared with
import hashlib
import json
import secrets
import time

from app.db import connect, now_iso, rows

SUMMARY = "id, user_id, origin, destination, start_date, end_date, travellers, budget_inr, total_cost, created, updated"
INVITE_DAYS = 7
INVITES_PER_DAY = 20
MAX_MEMBERS = 10


def can_edit(con, trip_id: int, user_id: int) -> bool:
    return bool(
        con.execute(
            "select 1 from itineraries where id = ? and user_id = ?"
            " union select 1 from trip_members where trip_id = ? and user_id = ?",
            (trip_id, user_id, trip_id, user_id),
        ).fetchone()
    )


def save_trip(user_id: int, plan: dict, trip_id: int | None = None) -> int:
    r = plan["request"]
    values = (
        r["origin"],
        r["destination"],
        r["start_date"],
        r["end_date"],
        r["travellers"],
        r["budget_inr"],
        plan["total_cost"],
        json.dumps(plan),
    )
    with connect() as con:
        if trip_id and can_edit(con, trip_id, user_id):
            con.execute(
                "update itineraries set origin = ?, destination = ?, start_date = ?, end_date = ?, travellers = ?,"
                " budget_inr = ?, total_cost = ?, plan = ?, updated = ? where id = ?",
                (*values, now_iso(), trip_id),
            )
            return trip_id
        cur = con.execute(
            "insert into itineraries (user_id, origin, destination, start_date, end_date, travellers, budget_inr,"
            " total_cost, plan, created, updated) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, *values, now_iso(), now_iso()),
        )
        return cur.lastrowid


def trips_for(user_id: int) -> list[dict]:
    cols = ", ".join(f"i.{c}" for c in SUMMARY.split(", "))
    with connect() as con:
        found = rows(
            con.execute(
                f"select {cols}, u.name as owner_name, (i.user_id != ?) as shared from itineraries i"
                " join users u on u.id = i.user_id"
                " where i.user_id = ? or i.id in (select trip_id from trip_members where user_id = ?)"
                " order by i.updated desc, i.id desc",
                (user_id, user_id, user_id),
            )
        )
    return [t | {"shared": bool(t["shared"])} for t in found]


def members(con, trip_id: int) -> list[dict]:
    return rows(
        con.execute(
            "select u.id, u.name, 'owner' as role from itineraries i join users u on u.id = i.user_id where i.id = ?"
            " union all select u.id, u.name, m.role from trip_members m join users u on u.id = m.user_id"
            " where m.trip_id = ?",
            (trip_id, trip_id),
        )
    )


def get_trip(trip_id: int) -> dict | None:
    with connect() as con:
        found = rows(con.execute(f"select {SUMMARY}, plan from itineraries where id = ?", (trip_id,)))
        if not found:
            return None
        people = members(con, trip_id)
    t = found[0]
    return t | {"plan": json.loads(t["plan"]) | {"trip_id": t["id"]}, "members": people}


def can_view(trip: dict, acc: dict) -> bool:
    return acc["role"] == "admin" or any(m["id"] == acc["id"] for m in trip["members"])


def delete_trip(trip_id: int, user_id: int) -> bool:
    with connect() as con:
        gone = con.execute("delete from itineraries where id = ? and user_id = ?", (trip_id, user_id)).rowcount > 0
        if gone:
            con.execute("delete from trip_members where trip_id = ?", (trip_id,))
            con.execute("delete from trip_invites where trip_id = ?", (trip_id,))
        return gone


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_invite(trip_id: int, user_id: int, now: float | None = None) -> dict | None:
    now = now or time.time()
    with connect() as con:
        if not can_edit(con, trip_id, user_id):
            return None
        recent = con.execute(
            "select count(*) from trip_invites where trip_id = ? and expires > ?",
            (trip_id, now + (INVITE_DAYS - 1) * 86400),
        ).fetchone()[0]
        if recent >= INVITES_PER_DAY:
            raise PermissionError("too many invite links today, use one you already made")
        token = secrets.token_urlsafe(18)
        expires = now + INVITE_DAYS * 86400
        con.execute(
            "insert into trip_invites (token, trip_id, created_by, expires, created) values (?, ?, ?, ?, ?)",
            (token_hash(token), trip_id, user_id, expires, now_iso()),
        )
    return {"token": token, "expires": expires, "days": INVITE_DAYS}


def find_invite(con, token: str, now: float) -> dict | None:
    found = rows(
        con.execute(
            "select t.trip_id, t.created_by, t.expires, i.origin, i.destination, i.start_date, i.end_date,"
            " u.name as invited_by from trip_invites t join itineraries i on i.id = t.trip_id"
            " join users u on u.id = t.created_by where t.token = ?",
            (token_hash(token),),
        )
    )
    if not found or found[0]["expires"] < now:
        return None
    return found[0]


def preview_invite(token: str, user_id: int, now: float | None = None) -> dict | None:
    now = now or time.time()
    with connect() as con:
        inv = find_invite(con, token, now)
        if not inv:
            return None
        people = members(con, inv["trip_id"])
    return {
        "trip_id": inv["trip_id"],
        "origin": inv["origin"],
        "destination": inv["destination"],
        "start_date": inv["start_date"],
        "end_date": inv["end_date"],
        "invited_by": inv["invited_by"],
        "members": [m["name"] for m in people],
        "joined": any(m["id"] == user_id for m in people),
    }


def accept_invite(token: str, user_id: int, now: float | None = None) -> int | None:
    now = now or time.time()
    with connect() as con:
        inv = find_invite(con, token, now)
        if not inv:
            return None
        people = members(con, inv["trip_id"])
        if any(m["id"] == user_id for m in people):
            return inv["trip_id"]
        if len(people) >= MAX_MEMBERS:
            raise PermissionError(f"this itinerary already has {MAX_MEMBERS} travellers")
        con.execute(
            "insert into trip_members (trip_id, user_id, role, joined) values (?, ?, 'member', ?)",
            (inv["trip_id"], user_id, now_iso()),
        )
        return inv["trip_id"]


def remove_member(trip_id: int, acting_id: int, member_id: int) -> bool:
    with connect() as con:
        owner = con.execute("select user_id from itineraries where id = ?", (trip_id,)).fetchone()
        if not owner or (acting_id != member_id and acting_id != owner[0]):
            return False
        return (
            con.execute("delete from trip_members where trip_id = ? and user_id = ?", (trip_id, member_id)).rowcount > 0
        )


def stop_invites(trip_id: int, user_id: int) -> bool:
    with connect() as con:
        owner = con.execute("select 1 from itineraries where id = ? and user_id = ?", (trip_id, user_id)).fetchone()
        if not owner:
            return False
        con.execute("delete from trip_invites where trip_id = ?", (trip_id,))
        return True
