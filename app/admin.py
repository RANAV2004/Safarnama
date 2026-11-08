# admin tools
from app.auth import PUBLIC, public
from app.db import connect, rows
from app.trips import SUMMARY

USER_COLS = ", ".join(f"u.{c}" for c in PUBLIC.split(", "))


def like(q: str) -> str:
    return q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_users(q: str = "", limit: int = 100) -> list[dict]:
    q = q.strip().lstrip("#")
    sql = f"select {USER_COLS}, count(i.id) as trips from users u left join itineraries i on i.user_id = u.id"
    args: tuple = ()
    if q.isdigit():
        sql += " where cast(u.id as text) like ?"
        args = (f"{q}%",)
    elif q:
        sql += " where lower(u.name) like ? escape '\\' or u.email like ? escape '\\'"
        args = (f"%{like(q)}%",) * 2
    sql += " group by u.id order by u.created desc limit ?"
    with connect() as con:
        return [public(r) | {"trips": r["trips"]} for r in rows(con.execute(sql, (*args, limit)))]


def user_detail(uid: int) -> dict | None:
    with connect() as con:
        found = rows(con.execute(f"select {PUBLIC} from users where id = ?", (uid,)))
        if not found:
            return None
        trips = rows(con.execute(f"select {SUMMARY} from itineraries where user_id = ? order by updated desc", (uid,)))
    return public(found[0]) | {"trips": len(trips), "itineraries": trips}


def set_banned(uid: int, banned: bool) -> bool:
    with connect() as con:
        return (
            con.execute(
                "update users set banned = ?, token_version = token_version + 1 where id = ?", (int(banned), uid)
            ).rowcount
            > 0
        )


def delete_user(uid: int) -> bool:
    with connect() as con:
        found = con.execute("select email from users where id = ?", (uid,)).fetchone()
        if not found:
            return False
        email = found[0]
        owned = "select id from itineraries where user_id = ?"
        con.execute(f"delete from trip_members where trip_id in ({owned}) or user_id = ?", (uid, uid))
        con.execute(f"delete from trip_invites where trip_id in ({owned}) or created_by = ?", (uid, uid))
        con.execute("delete from itineraries where user_id = ?", (uid,))
        for table in ("feedback", "profiles", "turns"):
            con.execute(f"delete from {table} where user = ?", (email,))
        con.execute("delete from users where id = ?", (uid,))
        return True


def all_trips(q: str = "", limit: int = 200) -> list[dict]:
    q = q.strip().lstrip("#")
    cols = ", ".join(f"i.{c}" for c in SUMMARY.split(", "))
    sql = (
        f"select {cols}, u.name as user_name, u.email as user_email from itineraries i join users u on u.id = i.user_id"
    )
    args: tuple = ()
    if q.isdigit():
        sql += " where cast(i.user_id as text) like ? or cast(i.id as text) = ?"
        args = (f"{q}%", q)
    elif q:
        sql += (
            " where lower(i.destination) like ? escape '\\' or lower(i.origin) like ? escape '\\'"
            " or lower(u.name) like ? escape '\\'"
        )
        args = (f"%{like(q)}%",) * 3
    sql += " order by i.updated desc limit ?"
    with connect() as con:
        return rows(con.execute(sql, (*args, limit)))


def stats() -> dict:
    with connect() as con:
        users, banned = con.execute("select count(*), coalesce(sum(banned), 0) from users").fetchone()
        trips = con.execute("select count(*) from itineraries").fetchone()[0]
    return {"users": users, "banned": banned, "itineraries": trips}
