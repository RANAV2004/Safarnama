# traveller profile
import json

from app.db import connect, now_iso
from app.rag import guide
from app.rag.vectors import tokens

INTERESTS = {
    "beaches": ("Beaches", "Sand, sea and swimming", "beach swimming kayaking"),
    "mountains": ("Mountains and hills", "Hill tops and high ground", "hill hilltop aravalli"),
    "trekking": ("Trekking and hikes", "Climbs, trails and steps", "hiking climb steps"),
    "views": ("Scenic views and sunsets", "Lookouts and golden hours", "views sunset photography"),
    "history": ("History and forts", "Forts, palaces and heritage", "history fort palace unesco heritage"),
    "nature": ("Nature and wildlife", "Lakes, falls, gardens and animals", "nature waterfall lake garden animals zoo"),
    "shopping": ("Shopping and markets", "Bazaars and souvenirs", "shopping market souvenirs jewellery"),
    "food": ("Food and local flavours", "Street food and thalis", "food"),
    "spiritual": ("Temples and spiritual places", "Temples, churches and calm", "temple spiritual church"),
    "culture": ("Art and culture", "Museums, dance and art", "culture art dance music museum"),
    "adventure": ("Adventure", "Jeeps, water sports and thrills", "adventure water sports jeep"),
    "clubs": ("Beaches and clubs", "Beach shacks, clubs and parties", "beach nightlife club party shack"),
    "nightlife": ("Nightlife", "Evenings out", "nightlife evening"),
    "quiet": ("Quiet and relaxing", "Calm spots away from crowds", "quiet relaxing"),
    "family": ("Family and kids", "Fun for all ages", "family kids"),
}
TO_CATEGORY = {
    "beaches": "beach",
    "clubs": "beach",
    "history": "history",
    "nature": "nature",
    "shopping": "shopping",
    "culture": "culture",
    "spiritual": "culture",
}


def options() -> list[dict]:
    return [{"id": k, "label": v[0], "hint": v[1]} for k, v in INTERESTS.items()]


def get_profile(user: str) -> dict:
    with connect() as con:
        row = con.execute("select interests, onboarded from profiles where user = ?", (user,)).fetchone()
    return {"interests": json.loads(row[0]) if row else [], "onboarded": bool(row and row[1])}


def save_profile(user: str, interests: list[str]) -> dict:
    clean = [i for i in dict.fromkeys(interests) if i in INTERESTS]
    with connect() as con:
        con.execute(
            "insert into profiles (user, interests, onboarded, updated) values (?, ?, 1, ?) on conflict(user) do update set interests = excluded.interests, onboarded = 1, updated = excluded.updated",
            (user, json.dumps(clean), now_iso()),
        )
    return get_profile(user)


def place_words(place_id: str, category: str) -> set[str]:
    doc = guide.get(place_id) or {}
    return set(tokens(" ".join([category, doc.get("title", ""), " ".join(doc.get("tags", []))])))


def matches(interests: list[str], place_id: str, category: str) -> list[str]:
    words = place_words(place_id, category)
    return [i for i in interests if i in INTERESTS and set(tokens(INTERESTS[i][2])) & words]
