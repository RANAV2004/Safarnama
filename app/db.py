# database
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
create table if not exists feedback (id integer primary key, user text not null, city text, text text not null, signals text not null, created text not null);
create table if not exists profiles (user text primary key, interests text not null, onboarded integer not null default 0, updated text not null);
create table if not exists examples (id integer primary key, text text not null, intent text not null, source text not null, created text not null);
create table if not exists turns (id integer primary key, user text not null, message text not null, parts text not null, adds text not null, created text not null);
create table if not exists users (id integer primary key, name text not null, email text not null unique, birth_date text not null, password text not null, role text not null default 'user', banned integer not null default 0, token_version integer not null default 0, fails integer not null default 0, locked_until real not null default 0, created text not null, last_login text);
create table if not exists itineraries (id integer primary key autoincrement, user_id integer not null, origin text not null, destination text not null, start_date text not null, end_date text not null, travellers integer not null, budget_inr integer not null default 0, total_cost integer not null, plan text not null, created text not null, updated text not null);
create index if not exists itineraries_user on itineraries (user_id);
create table if not exists place_words (id integer primary key, place_id text not null, text text not null, created text not null);
create table if not exists reset_codes (email text primary key, code text not null, expires real not null, tries integer not null default 0);
create table if not exists rated_turns (turn_id integer primary key, created text not null);
create table if not exists wiki_cache (title text primary key, data text, fetched real not null);
create table if not exists trip_members (trip_id integer not null, user_id integer not null, role text not null, joined text not null, primary key (trip_id, user_id));
create index if not exists trip_members_user on trip_members (user_id);
create table if not exists trip_invites (token text primary key, trip_id integer not null, created_by integer not null, expires real not null, created text not null);
"""
NEW_COLUMNS = {"examples": {"user": "text"}}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def add_missing_columns(con):
    for table, cols in NEW_COLUMNS.items():
        have = {r[1] for r in con.execute(f"pragma table_info({table})")}
        for name, kind in cols.items():
            if name not in have:
                con.execute(f"alter table {table} add column {name} {kind}")


def db_path() -> Path:
    return Path(os.getenv("SAFARNAMA_DB", "data/safarnama.db"))


def rows(cur) -> list[dict]:
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


@contextmanager
def connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(SCHEMA)
        add_missing_columns(con)
        yield con
        con.commit()
    finally:
        con.close()
