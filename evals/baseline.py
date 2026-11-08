# baselines
from pydantic import BaseModel

from app import llm
from app.agents.coordinator import budget_check, coordinator_agent
from app.agents.places import places_agent
from app.agents.stay import stay_agent
from app.agents.transport import transport_agent
from app.agents.writer import writer_agent
from app.llm import Usage
from app.providers import get_providers
from app.state import DayPlan, PlanItem, TripRequest, TripState
from app.tools.budget import compute_totals


def apply(state: TripState, updates: dict) -> TripState:
    merged = {}
    for k, v in updates.items():
        if k in ("trace", "errors", "notes"):
            v = getattr(state, k) + v
        elif k == "floors":
            v = {**state.floors, **v}
        merged[k] = v
    return state.model_copy(update=merged)


def single_pass(req: TripRequest) -> TripState:
    s = TripState(request=req)
    for node in (coordinator_agent, transport_agent, stay_agent, places_agent, budget_check, writer_agent):
        s = apply(s, node(s))
    return s


class OneShot(BaseModel):
    outbound_id: str
    return_id: str
    stay_id: str | None
    days: list[dict]


def by_id(opts, i):
    return next((o for o in opts if o.id == i), None)


def single_llm(req: TripRequest) -> tuple[TripState, Usage]:
    p = get_providers()
    outs = p.transport.search(req.origin, req.destination, req.start_date, req.travellers, "arrive_on")
    backs = p.transport.search(req.destination, req.origin, req.end_date, req.travellers, "depart_on")
    stays = p.stays.search(req.destination, req.start_date, req.end_date, req.travellers) if req.nights else []
    places = p.places.search(req.destination)
    lines = [f"OUT {o.id}: {o.mode} {o.provider} {o.depart_at} -> {o.arrive_at}, Rs {o.price_inr}" for o in outs]
    lines += [f"BACK {b.id}: {b.mode} {b.provider} {b.depart_at} -> {b.arrive_at}, Rs {b.price_inr}" for b in backs]
    lines += [
        f"STAY {h.id}: {h.name} Rs {h.price_per_night_inr}/room/night, rating {h.rating}, desk until {h.checkin_until}"
        for h in stays
    ]
    lines += [
        f"PLACE {x.id}: {x.name}, Rs {x.entry_fee_inr}/person, {x.est_hours}h, open {x.opens}-{x.closes}, closed {x.closed_days or 'never'}"
        for x in places
    ]
    prompt = (
        f"Plan a trip {req.origin} to {req.destination}, {req.start_date} to {req.end_date}, {req.travellers} traveller(s), total budget Rs {req.budget_inr} including Rs 500 food per person per day. Two people per room. Preferences {req.preferences or 'none'}.\n"
        + "\n".join(lines)
    )
    usage = Usage()
    ans = llm.ask_json(
        "You are a trip planner. Pick transport, a hotel and a day by day schedule within budget.",
        prompt,
        OneShot,
        usage,
    )
    s = TripState(request=req, place_options=places)
    if not ans:
        return s.model_copy(update={"errors": ["single llm call failed"]}), usage
    pmap = {x.id: x for x in places}
    days, chosen = [], []
    for d in req.trip_dates():
        raw = next((x for x in ans.days if str(x.get("date")) == d.isoformat()), {"items": []})
        items = []
        for it in raw.get("items", []):
            if it.get("place_id") in pmap:
                items.append(
                    PlanItem(
                        start=it["start"],
                        end=it["end"],
                        title=pmap[it["place_id"]].name,
                        kind="place",
                        place_id=it["place_id"],
                    )
                )
                if pmap[it["place_id"]] not in chosen:
                    chosen.append(pmap[it["place_id"]])
        days.append(DayPlan(date=d, weekday=d.strftime("%A"), items=items))
    s = s.model_copy(
        update={
            "selected_outbound": by_id(outs, ans.outbound_id),
            "selected_return": by_id(backs, ans.return_id),
            "selected_stay": by_id(stays, ans.stay_id),
            "selected_places": chosen,
            "days": days,
        }
    )
    return s.model_copy(update=compute_totals(s)), usage
