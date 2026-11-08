# places agent
from pydantic import BaseModel

from app import llm
from app.agents.common import money, traced, user_note
from app.profile import INTERESTS, matches
from app.providers import ProviderError, get_providers
from app.state import PlaceOption, TripState
from app.tools.geo import km_between

HOURS_PER_DAY = 7
EDGE_DAY_HOURS = 3
NEARBY_KM = 30


class PlacesPick(BaseModel):
    place_ids: list[str]
    reason: str


def hours_available(state: TripState) -> float:
    d = state.request.days
    return EDGE_DAY_HOURS if d == 1 else 2 * EDGE_DAY_HOURS + (d - 2) * HOURS_PER_DAY


def open_on_trip(p: PlaceOption, weekdays: set[str]) -> bool:
    return bool(weekdays - set(p.closed_days))


def fits(chosen: list[PlaceOption], travellers: int, envelope: int, hours: float) -> bool:
    return sum(p.entry_fee_inr for p in chosen) * travellers <= envelope and sum(p.est_hours for p in chosen) <= hours


@traced("places")
def places_agent(state: TripState, usage) -> dict:
    req = state.request
    try:
        options = get_providers().places.search(req.destination)
    except ProviderError as e:
        return {"errors": [f"places: {e}"], "_note": "no places data"}
    if not options:
        return {"errors": [f"places: no places found in {req.destination}"], "_note": "no places data"}
    weekdays = {d.strftime("%A") for d in req.trip_dates()}
    hints = state.instructions.get("places", [])
    envelope, hours = state.budget_plan.activities, hours_available(state)
    allowed = [p for p in options if p.id not in req.exclude_places]
    forced = [p for p in allowed if p.id in req.include_places]
    notes = [f"{p.name} is closed on every day of your trip" for p in forced if not open_on_trip(p, weekdays)]
    forced = [p for p in forced if open_on_trip(p, weekdays)]
    pool = [
        p
        for p in allowed
        if p not in forced and open_on_trip(p, weekdays) and (p.entry_fee_inr == 0 or "cheaper" not in hints)
    ]
    if "nearby" in hints:
        base = (
            (state.selected_stay.lat, state.selected_stay.lng)
            if state.selected_stay
            else (sum(p.lat for p in options) / len(options), sum(p.lng for p in options) / len(options))
        )
        pool = [p for p in pool if km_between(*base, p.lat, p.lng) <= NEARBY_KM]
    prefs = {x.lower() for x in req.preferences}
    likes, avoids = set(state.learned.likes), set(state.learned.avoids) - prefs
    kept = [p for p in pool if p.category not in avoids]
    if len(kept) < len(pool) and len(kept) >= 2:
        skipped = sorted({p.category for p in pool} & avoids)
        notes.append(f"left out {' and '.join(skipped)} places, you removed them on earlier trips")
        pool = kept
    interests = state.learned.interests
    fit = {p.id: matches(interests, p.id, p.category) for p in pool}
    pool.sort(
        key=lambda p: (
            -(
                p.rating
                + (0.4 if p.category in prefs else 0)
                + (0.3 if p.category in likes else 0)
                + 0.35 * min(3, len(fit[p.id]))
            )
        )
    )
    chosen = list(forced)
    allowance = max(envelope, sum(p.entry_fee_inr for p in forced) * req.travellers)
    for p in pool:
        if fits(chosen + [p], req.travellers, allowance, hours):
            chosen.append(p)
    hits = sorted({i for p in chosen for i in fit.get(p.id, [])}, key=interests.index)
    note = (
        f"picked first for your interests: {', '.join(INTERESTS[i][0].lower() for i in hits)}"
        if hits
        else "rule based pick"
    )
    prompt = (
        f"Plan sightseeing in {req.destination} for {req.days} day(s), {req.travellers} traveller(s), preferences {req.preferences or 'none'}, interests {interests or 'none'}. Activities budget {money(envelope)} total, about {hours:.0f} hours available. Always keep: {[p.id for p in forced] or 'none'}.{user_note(state)}\n"
        + "\n".join(
            f"{p.id}: {p.name} ({p.category}), fee {money(p.entry_fee_inr)} per person, {p.est_hours}h, rating {p.rating}"
            for p in pool
        )
    )
    ans = llm.ask_json(
        "You are the places agent of a trip planner. Choose place ids that fit the budget and time.",
        prompt,
        PlacesPick,
        usage,
    )
    by_id = {p.id: p for p in pool}
    if ans:
        picked = forced + [by_id[i] for i in dict.fromkeys(ans.place_ids) if i in by_id]
        if len(picked) > len(forced) and fits(picked, req.travellers, allowance, hours):
            chosen, note = picked, ans.reason
    floor = sum(p.entry_fee_inr for p in forced) * req.travellers
    return {
        "place_options": options,
        "selected_places": chosen,
        "floors": {"activities": floor},
        "notes": notes,
        "_note": note,
    }
