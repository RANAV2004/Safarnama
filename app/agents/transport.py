# transport agent
from datetime import timedelta

from pydantic import BaseModel

from app import llm
from app.agents.common import money, traced, user_note
from app.providers import ProviderError, get_providers
from app.state import TransportOption, TripState

MIN_GAP_HOURS = 4
SHORTLIST = 6


class TransportPick(BaseModel):
    choice: int
    reason: str


def score(out: TransportOption, back: TransportOption, envelope: int) -> float:
    price = (out.price_inr + back.price_inr) / max(envelope, 1)
    wasted = sum(0 if t.overnight else t.hours for t in (out, back))
    return price + 0.05 * wasted


def describe(i: int, o: TransportOption, b: TransportOption) -> str:
    return f"{i}: out {o.mode} {o.provider} {o.depart_at:%d %b %H:%M} to {o.arrive_at:%d %b %H:%M}, back {b.mode} {b.provider} {b.depart_at:%d %b %H:%M} to {b.arrive_at:%d %b %H:%M}, total {money(o.price_inr + b.price_inr)}"


@traced("transport")
def transport_agent(state: TripState, usage) -> dict:
    req, prov = state.request, get_providers().transport
    errors = []
    mine_out = req.my_outbound.option("out") if req.my_outbound else None
    mine_back = req.my_return.option("back") if req.my_return else None
    outs, backs = [], []
    try:
        if not (mine_out and mine_back):
            outs = prov.search(req.origin, req.destination, req.start_date, req.travellers, "arrive_on")
            if getattr(prov, "last_error", None):
                errors.append(f"transport: {prov.last_error}")
            backs = prov.search(req.destination, req.origin, req.end_date, req.travellers, "depart_on")
            if getattr(prov, "last_error", None):
                errors.append(f"transport: {prov.last_error}")
    except ProviderError as e:
        if not (mine_out or mine_back):
            return {"errors": [f"transport: {e}"], "_note": "no transport data"}
        errors.append(f"transport: {e}")
    if mine_out:
        outs = [mine_out] + outs
    if mine_back:
        backs = [mine_back] + backs
    use_outs = [mine_out] if mine_out else outs
    use_backs = [mine_back] if mine_back else backs
    if mine_out and mine_back:
        pairs = [(mine_out, mine_back)]
    else:
        pairs = [
            (o, b) for o in use_outs for b in use_backs if b.depart_at >= o.arrive_at + timedelta(hours=MIN_GAP_HOURS)
        ]
    if not pairs:
        return {"errors": errors + ["transport: no valid outbound and return combination"], "_note": "no pairs"}
    notes = []
    want_out = None if mine_out else req.outbound_id
    want_back = None if mine_back else req.return_id
    pinned_by_user = bool(want_out or want_back or mine_out or mine_back)
    if want_out or want_back:
        mine = [p for p in pairs if (not want_out or p[0].id == want_out) and (not want_back or p[1].id == want_back)]
        if mine:
            pairs = mine
        else:
            notes.append("your chosen journey does not work with these dates, so another one was picked")
            pinned_by_user = bool(mine_out or mine_back)
    envelope = state.budget_plan.transport
    cheapest = min(pairs, key=lambda p: p[0].price_inr + p[1].price_inr)
    floor = cheapest[0].price_inr + cheapest[1].price_inr
    hints = state.instructions.get("transport", [])
    fits = [p for p in pairs if p[0].price_inr + p[1].price_inr <= envelope] or (pairs if pinned_by_user else [])
    if not fits:
        pick, note = cheapest, f"cheapest option {money(floor)} is over the transport budget {money(envelope)}"
    else:
        key = (
            (lambda p: p[0].price_inr + p[1].price_inr)
            if "cheaper" in hints
            else (lambda p: score(p[0], p[1], envelope))
        )
        ranked = sorted(fits, key=key)[:SHORTLIST]
        pick, note = ranked[0], "rule based pick"
        prompt = (
            f"Trip {req.origin} to {req.destination}, {req.start_date} to {req.end_date}, {req.travellers} traveller(s), preferences {req.preferences or 'none'}. Transport budget {money(envelope)}. Pick the best option. Overnight journeys save daytime.{user_note(state)}\n"
            + "\n".join(describe(i, o, b) for i, (o, b) in enumerate(ranked))
        )
        ans = llm.ask_json(
            "You are the transport agent of a trip planner. Choose one option from the list.",
            prompt,
            TransportPick,
            usage,
        )
        if ans and 0 <= ans.choice < len(ranked):
            pick, note = ranked[ans.choice], ans.reason
        if pinned_by_user and len(pairs) == 1:
            note = "kept your chosen journeys"
        if mine_out or mine_back:
            note = "planned around your booked " + " and ".join(t.provider for t in (mine_out, mine_back) if t)
    if errors:
        notes.append("live transport data failed, showing sample data")
    return {
        "outbound_options": outs,
        "return_options": backs,
        "selected_outbound": pick[0],
        "selected_return": pick[1],
        "floors": {"transport": floor},
        "errors": errors,
        "notes": notes,
        "_note": note,
    }
