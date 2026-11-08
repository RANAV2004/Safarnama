# writer agent
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel

from app import llm
from app.agents.common import money, traced, user_note
from app.state import DayPlan, PlaceOption, PlanItem, TripState
from app.tools.budget import compute_totals
from app.tools.checks import RETURN_GAP_MIN, TRANSFER_MIN
from app.tools.geo import km_between, travel_minutes

DAY_START = time(9, 0)
DAY_END = time(20, 30)
CHECKIN_MIN = 30
FULL_DAY_HOURS = 7
EDGE_DAY_HOURS = 3
EARLY_START = time(6, 30)
FAR_MIN = 120


class Summary(BaseModel):
    summary: str


def fmt(t: datetime) -> str:
    return t.strftime("%H:%M")


def round_up(t: datetime, step: int = 15) -> datetime:
    extra = (-t.minute) % step
    return (t + timedelta(minutes=extra)).replace(second=0, microsecond=0)


def day_window(state: TripState, d: date, items: list) -> tuple[datetime, datetime]:
    start, end = datetime.combine(d, DAY_START), datetime.combine(d, DAY_END)
    out, back, stay = state.selected_outbound, state.selected_return, state.selected_stay
    if out and out.arrive_at.date() == d:
        left = out.depart_at.strftime("%d %b %H:%M") if out.overnight else fmt(out.depart_at)
        items.append(
            PlanItem(
                start=fmt(out.arrive_at) if out.overnight else fmt(out.depart_at),
                end=fmt(out.arrive_at),
                title=f"Arrive by {out.mode} ({out.provider}, left {left})",
                kind="travel",
                cost_inr=out.price_inr,
            )
        )
        start = max(start, out.arrive_at + timedelta(minutes=TRANSFER_MIN))
        if stay:
            items.append(
                PlanItem(
                    start=fmt(start),
                    end=fmt(start + timedelta(minutes=CHECKIN_MIN)),
                    title=f"Check in at {stay.name}",
                    kind="checkin",
                )
            )
            start += timedelta(minutes=CHECKIN_MIN)
        start = round_up(start)
    if back and back.depart_at.date() == d:
        end = min(end, back.depart_at - timedelta(minutes=RETURN_GAP_MIN))
    return start, end


def try_fit(p: PlaceOption, here: tuple[float, float], now: datetime, end: datetime, d: date):
    dist = km_between(*here, p.lat, p.lng)
    begin = round_up(max(now + timedelta(minutes=travel_minutes(dist)), datetime.combine(d, p.opens)))
    finish = begin + timedelta(hours=p.est_hours)
    ok = d.strftime("%A") not in p.closed_days and finish.date() == d and finish.time() <= p.closes and finish <= end
    return (p, dist, begin, finish) if ok else None


def schedule_day(
    state: TripState,
    d: date,
    todo: list[PlaceOption],
    base: tuple[float, float],
    target: float,
    trip: PlaceOption | None = None,
) -> DayPlan:
    items: list[PlanItem] = []
    now, end = day_window(state, d, items)
    weekday, here, km, busy = d.strftime("%A"), base, 0.0, 0.0
    edge = d in (state.request.start_date, state.request.end_date)
    limit = EDGE_DAY_HOURS if edge and state.request.days > 1 else min(FULL_DAY_HOURS, target)
    first = try_fit(trip, here, datetime.combine(d, EARLY_START), end, d) if trip in todo else None
    while True:
        best = first
        first = None
        if not best:
            for p in todo:
                cand = try_fit(p, here, now, end, d)
                if cand and busy + p.est_hours <= limit and (best is None or cand[1] < best[1]):
                    best = cand
        if not best:
            break
        p, dist, begin, finish = best
        items.append(
            PlanItem(
                start=fmt(begin),
                end=fmt(finish),
                title=p.name,
                kind="place",
                place_id=p.id,
                cost_inr=p.entry_fee_inr * state.request.travellers,
            )
        )
        km += dist
        busy += p.est_hours
        here, now = (p.lat, p.lng), finish
        todo.remove(p)
    if here != base:
        km += km_between(*here, *base)
    if busy == 0 and not edge:
        items.append(
            PlanItem(start=fmt(now), end=fmt(end), title=f"Free day in {state.request.destination}", kind="free")
        )
    back = state.selected_return
    if back and back.depart_at.date() == d:
        reach = back.arrive_at.strftime("%d %b %H:%M") if back.overnight else fmt(back.arrive_at)
        items.append(
            PlanItem(
                start=fmt(back.depart_at),
                end=fmt(back.arrive_at),
                title=f"Leave by {back.mode} ({back.provider}, reach {state.request.origin} {reach})",
                kind="travel",
                cost_inr=back.price_inr,
            )
        )
    return DayPlan(date=d, weekday=weekday, items=items, km=round(km, 1))


def hotel_base(state: TripState) -> tuple[float, float]:
    if state.selected_stay:
        return state.selected_stay.lat, state.selected_stay.lng
    ps = state.selected_places or state.place_options
    return (sum(p.lat for p in ps) / len(ps), sum(p.lng for p in ps) / len(ps)) if ps else (0.0, 0.0)


def plan_day_trips(state: TripState, todo: list[PlaceOption], base: tuple[float, float]) -> dict[date, PlaceOption]:
    req, out = state.request, {}
    full = [d for d in req.trip_dates() if req.days == 1 or d not in (req.start_date, req.end_date)]
    for p in todo:
        if travel_minutes(km_between(*base, p.lat, p.lng)) <= FAR_MIN:
            continue
        day = next((d for d in full if d not in out and d.strftime("%A") not in p.closed_days), None)
        if day:
            out[day] = p
    return out


@traced("writer")
def writer_agent(state: TripState, usage) -> dict:
    req = state.request
    todo = sorted(state.selected_places, key=lambda p: (len(p.closed_days) == 0, -p.rating))
    base = hotel_base(state)
    full_days = max(1, req.days - 2)
    target = max(3.0, sum(p.est_hours for p in todo) / full_days + 1)
    trips = plan_day_trips(state, todo, base)
    days = [schedule_day(state, d, todo, base, target, trips.get(d)) for d in req.trip_dates()]
    notes = [f"dropped {p.name}, it did not fit any day's timings" for p in todo]
    kept = [p for p in state.selected_places if p not in todo]
    new_state = state.model_copy(update={"selected_places": kept, "days": days})
    totals = compute_totals(new_state)
    summary = f"{req.days} day trip from {req.origin} to {req.destination} for {req.travellers}, total {money(totals['total_cost'])} of {money(req.budget_inr)}."
    plan_text = "\n".join(f"{dp.date} {dp.weekday}: " + ", ".join(i.title for i in dp.items) for dp in days)
    ans = llm.ask_json(
        "You write short friendly trip summaries. No invented facts, no prices.",
        f"Write a 2 to 3 sentence summary of this plan:\n{plan_text}{user_note(state)}",
        Summary,
        usage,
    )
    if ans:
        summary = ans.summary
    return {
        "days": days,
        "selected_places": kept,
        "summary": summary,
        "writer_notes": notes,
        **totals,
        "_note": f"{len(days)} days, {len(kept)} places",
    }
