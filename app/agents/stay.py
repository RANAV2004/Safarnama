# stay agent
from datetime import timedelta

from pydantic import BaseModel

from app import llm
from app.agents.common import money, traced, user_note
from app.providers import ProviderError, get_providers
from app.state import StayOption, TripState
from app.tools.budget import rooms_needed
from app.tools.checks import TRANSFER_MIN, desk_closed

SHORTLIST = 5


class StayPick(BaseModel):
    stay_id: str
    reason: str


def can_check_in(s: StayOption, state: TripState) -> bool:
    out = state.selected_outbound
    if s.late_checkin or not out:
        return True
    reach = out.arrive_at + timedelta(minutes=TRANSFER_MIN)
    return not desk_closed(reach, s.checkin_until)


@traced("stay")
def stay_agent(state: TripState, usage) -> dict:
    req = state.request
    if req.nights == 0:
        return {"selected_stay": None, "floors": {"stay": 0}, "_note": "day trip, no stay"}
    prov = get_providers().stays
    try:
        options = prov.search(req.destination, req.start_date, req.end_date, req.travellers)
    except ProviderError as e:
        return {"errors": [f"stay: {e}"], "_note": "no stay data"}
    if not options:
        return {"errors": [f"stay: no hotels found in {req.destination}"], "_note": "no stay data"}
    errors = [f"stay: {prov.last_error}"] if getattr(prov, "last_error", None) else []
    units = req.nights * rooms_needed(req.travellers)
    notes = []
    if req.stay_id:
        mine = next((s for s in options if s.id == req.stay_id), None)
        if mine:
            return {
                "stay_options": options,
                "selected_stay": mine,
                "floors": {"stay": mine.price_per_night_inr * units},
                "errors": errors,
                "_note": "kept your chosen hotel",
            }
        notes.append("your chosen hotel is not available, so another one was picked")
    hints = state.instructions.get("stay", [])
    if "late_checkin" in hints:
        ok = [s for s in options if can_check_in(s, state)]
        options = ok or options
    cap = state.budget_plan.stay // units
    floor = min(s.price_per_night_inr for s in options) * units
    fits = [s for s in options if s.price_per_night_inr <= cap]
    if not fits:
        pick = min(options, key=lambda s: s.price_per_night_inr)
        return {
            "stay_options": options,
            "selected_stay": pick,
            "floors": {"stay": floor},
            "errors": errors,
            "notes": notes,
            "_note": f"cheapest stay {money(pick.price_per_night_inr)}/night is over the cap {money(cap)}",
        }
    if "cheaper" in hints:
        ranked = sorted(fits, key=lambda s: (s.price_per_night_inr, -(s.rating or 0)))
    else:
        ranked = sorted(fits, key=lambda s: (-(s.rating or 0), s.price_per_night_inr))
    ranked = ranked[:SHORTLIST]
    pick, note = ranked[0], "rule based pick"
    prompt = (
        f"Stay in {req.destination} for {req.nights} night(s), {req.travellers} traveller(s), preferences {req.preferences or 'none'}. Max {money(cap)} per room per night.{user_note(state)}\n"
        + "\n".join(
            f"{s.id}: {s.name}, {s.area}, {money(s.price_per_night_inr)}/night, rating {s.rating}, desk until {s.checkin_until:%H:%M}"
            for s in ranked
        )
    )
    ans = llm.ask_json(
        "You are the stay agent of a trip planner. Choose one hotel id from the list.", prompt, StayPick, usage
    )
    by_id = {s.id: s for s in ranked}
    if ans and ans.stay_id in by_id:
        pick, note = by_id[ans.stay_id], ans.reason
    return {
        "stay_options": options,
        "selected_stay": pick,
        "floors": {"stay": floor},
        "errors": errors,
        "notes": notes,
        "_note": note,
    }
