# revise agent
import json
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.common import money
from app.db import connect, now_iso
from app.graph import plan_trip
from app.ml import intent
from app.ml.entities import CATEGORY, Tagged, tag
from app.rag import guide, memory
from app.rag.vectors import tokens
from app.state import MAX_BUDGET, Learned, PlaceOption, StayOption, TransportOption, TripRequest, TripState

PEOPLE = re.compile(r"\b(\d{1,2})\s*(people|persons|travellers|travelers|adults|of us)\b")
CHEAPER = re.compile(r"\b(cheap\w*|budget|less|lower|affordable|save|reduce|cut)\b")


class AlreadyRated(Exception):
    pass


class TooMuchTeaching(Exception):
    pass


HELP = "I could not work out what to change. Try something like: remove the flea market, add another beach, a cheaper hotel, go by train, or set the budget to 25k. If I got you wrong, press Not right and show me what you meant, so I learn."


class PlanOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    outbound: list[TransportOption] = Field(default_factory=list, max_length=200)
    return_: list[TransportOption] = Field(default_factory=list, alias="return", max_length=200)
    stays: list[StayOption] = Field(default_factory=list, max_length=200)
    places: list[PlaceOption] = Field(default_factory=list, max_length=200)


class CurrentPlan(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    request: TripRequest
    outbound: TransportOption | None = None
    return_: TransportOption | None = Field(default=None, alias="return")
    stay: StayOption | None = None
    places: list[PlaceOption] = Field(default_factory=list, max_length=100)
    total_cost: int = 0
    options: PlanOptions = Field(default_factory=PlanOptions)


class Part(BaseModel):
    text: str
    masked: str
    intent: str
    confidence: float
    done: bool = False


class Edits(BaseModel):
    add_places: list[str] = Field(default_factory=list)
    remove_places: list[str] = Field(default_factory=list)
    stay_id: str | None = None
    outbound_id: str | None = None
    return_id: str | None = None
    budget_inr: int | None = None
    travellers: int | None = None
    signals: dict[str, int] = Field(default_factory=dict)
    answers: list[str] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    found: list[dict] = Field(default_factory=list)

    def changes_plan(self) -> bool:
        return bool(
            self.add_places
            or self.remove_places
            or self.stay_id
            or self.outbound_id
            or self.return_id
            or self.budget_inr
            or self.travellers
        )

    def bump(self, cat: str, n: int):
        self.signals[cat] = max(-3, min(3, self.signals.get(cat, 0) + n))


class Revision(BaseModel):
    reply: str
    changes: list[str] = Field(default_factory=list)
    answer: str = ""
    sources: list[dict] = Field(default_factory=list)
    state: TripState | None = None
    learned: Learned = Field(default_factory=Learned)
    parts: list[Part] = Field(default_factory=list)
    turn_id: int | None = None


def clauses(text: str) -> list[str]:
    low = text.lower().replace("’", "'").replace("'", "")
    low = re.sub(r"\b(?:replace|swap)\s+(.+?)\s+(?:with|for)\s+([^.,;!?]+)", r"remove \1, add \2", low)
    low = re.sub(r"([^.,;!?]+?)\s+instead of\s+([^.,;!?]+)", r"\1, remove \2", low)
    return [
        c.strip()
        for c in re.split(r"(?<!\d)[.,](?!\d)|[.,](?=\D|$)|[;!?\n]| and | but | then | also ", f" {low} ")
        if c.strip()
    ]


def understand(plan: CurrentPlan, text: str) -> list[tuple[Part, Tagged]]:
    out = []
    for c in clauses(text):
        t = tag(c, plan.options.places, plan.options.stays, plan.request.destination)
        name, conf = intent.predict(t.masked)
        out.append((Part(text=c, masked=t.masked, intent=name, confidence=conf), t))
    return out


def of_kind(p: PlaceOption, kind: str) -> bool:
    if CATEGORY[kind] == kind:
        return p.category == kind
    doc = guide.get(p.id) or {}
    return kind in set(tokens(p.name + " " + " ".join(doc.get("tags", []))))


def plural(kind: str) -> str:
    return {
        "history": "history places",
        "shopping": "shopping places",
        "nature": "nature places",
        "culture": "culture places",
        "science": "science places",
        "beach": "beaches",
        "church": "churches",
        "hill": "hills",
    }.get(kind, kind + "s")


def pick_mode(plan: CurrentPlan, mode: str | None) -> tuple[TransportOption | None, TransportOption | None]:
    outs = [t for t in plan.options.outbound if mode is None or t.mode == mode]
    backs = [t for t in plan.options.return_ if mode is None or t.mode == mode]
    cheapest_out = min(outs, key=lambda t: t.price_inr) if outs else None
    cheapest_back = min(backs, key=lambda t: t.price_inr) if backs else None
    return cheapest_out, cheapest_back


def hotel(plan: CurrentPlan, e: Edits, which: str) -> str:
    cur, stays = plan.stay, plan.options.stays
    if not cur:
        return "this trip has no hotel to change"
    if which == "cheaper_hotel":
        lower = [s for s in stays if s.price_per_night_inr < cur.price_per_night_inr]
        if not lower:
            return f"{cur.name} is already the cheapest hotel I have"
        e.stay_id = max(lower, key=lambda s: (s.price_per_night_inr, s.rating or 0)).id
        return ""
    higher = [s for s in stays if (s.rating or 0) > (cur.rating or 0)]
    if not higher:
        return f"{cur.name} is already the best rated hotel I have"
    e.stay_id = min(higher, key=lambda s: (-(s.rating or 0), s.price_per_night_inr)).id
    return ""


def add_place(plan: CurrentPlan, e: Edits, part: Part, t: Tagged) -> str:
    in_plan = {p.id for p in plan.places}
    by_id = {p.id: p for p in plan.options.places}
    if t.places:
        issues = []
        for i in t.places:
            if i in in_plan:
                issues.append(f"{by_id[i].name} is already in your plan")
            else:
                e.add_places.append(i)
                e.bump(by_id[i].category, 1)
        return "; ".join(issues)
    pool = [
        p
        for p in plan.options.places
        if p.id not in in_plan
        and p.id not in e.add_places
        and p.id not in e.remove_places
        and (not t.kinds or any(of_kind(p, k) for k in t.kinds))
    ]
    hits = guide.search(part.text, plan.request.destination, k=1, only={p.id for p in pool})
    hit = next((by_id[h["id"]] for h in hits if h["id"] in by_id and h["score"] >= 0.08), None)
    if not hit and t.kinds and pool:
        hit = max(pool, key=lambda p: p.rating)
    if hit:
        e.add_places.append(hit.id)
        e.bump(hit.category, 2 if any(CATEGORY[k] == k for k in t.kinds) else 1)
        if not t.kinds:
            e.found.append({"place_id": hit.id, "text": part.text})
        return ""
    if t.kinds:
        return f"I have no more {plural(t.kinds[0])} to add in {plan.request.destination}"
    near = guide.search(part.text, plan.request.destination, k=1, only=in_plan)
    if near and near[0]["id"] in in_plan and near[0]["score"] >= 0.08:
        return f"the best match, {near[0]['title']}, is already in your plan"
    return "I could not find a place like that"


def remove_place(plan: CurrentPlan, e: Edits, t: Tagged) -> str:
    in_plan = {p.id for p in plan.places}
    by_id = {p.id: p for p in plan.options.places}
    if t.places:
        issues = []
        for i in t.places:
            if i in in_plan:
                e.remove_places.append(i)
                e.bump(by_id[i].category, -1)
            else:
                issues.append(f"{by_id[i].name} is not in your plan")
        return "; ".join(issues)
    if t.kinds:
        gone = [p for p in plan.places if any(of_kind(p, k) for k in t.kinds)]
        for p in gone:
            e.remove_places.append(p.id)
            e.bump(p.category, -1)
        for k in {k for k in t.kinds if CATEGORY[k] == k}:
            e.bump(k, -1)
        return "" if gone else f"there are no {plural(t.kinds[0])} in your plan"
    return "tell me which place to remove"


def answer(plan: CurrentPlan, e: Edits, part: Part, t: Tagged) -> str:
    named = [d for d in (guide.get(i) for i in t.places) if d][:1]
    top = (
        named
        or [
            h
            for h in guide.search(part.text, plan.request.destination, k=3, only={p.id for p in plan.options.places})
            if h["score"] >= 0.1
        ][:1]
    )
    if not top:
        e.answers.append(f"I don't have notes on that for {plan.request.destination} yet.")
        return "no notes"
    e.answers.append(guide.snippet(top[0]))
    e.sources += [{"title": d["title"], "text": d["text"]} for d in top]
    return ""


def act(plan: CurrentPlan, part: Part, t: Tagged, e: Edits) -> str:
    i, low = part.intent, part.text
    if i == "add_place":
        return add_place(plan, e, part, t)
    if i == "remove_place":
        return remove_place(plan, e, t)
    if i in ("cheaper_hotel", "better_hotel"):
        return hotel(plan, e, i)
    if i == "change_hotel":
        mine = [s for s in t.stays if not plan.stay or s != plan.stay.id]
        if mine:
            e.stay_id = mine[0]
            return ""
        return "you are already staying there" if t.stays else "tell me the name of the hotel"
    if i == "change_travel":
        mode = t.modes[0] if t.modes else None
        if mode is None and not CHEAPER.search(low):
            return "tell me if you want a flight, train or bus"
        if mode and plan.outbound and plan.outbound.mode == mode and (not plan.return_ or plan.return_.mode == mode):
            return f"you are already going by {mode}"
        out, back = pick_mode(plan, mode)
        if not (out or back):
            return f"there is no {mode} on this route for your dates"
        e.outbound_id, e.return_id = (out.id if out else None), (back.id if back else None)
        return ""
    if i == "set_budget":
        if not t.numbers:
            return "tell me the new budget, for example 25k"
        if m := PEOPLE.search(low):
            people = int(m.group(1))
            if not 1 <= people <= 10:
                return "I can plan for 1 to 10 travellers"
            e.travellers = people
        money_like = [n for n in t.numbers if n >= 500]
        if not money_like:
            return "tell me the new budget, for example 25k"
        if max(money_like) > MAX_BUDGET:
            return f"the budget can be at most {money(MAX_BUDGET)}"
        e.budget_inr = max(money_like)
        return ""
    if i == "set_travellers":
        n = (
            t.numbers[0]
            if t.numbers
            else (
                1
                if re.search(r"\bjust me\b|\bonly me\b|\balone\b", low)
                else plan.request.travellers + 1
                if "more" in low
                else 0
            )
        )
        if not 1 <= n <= 10:
            return "tell me how many people are travelling, from 1 to 10"
        e.travellers = n
        return ""
    if i in ("like", "dislike"):
        if not t.kinds:
            return "tell me what kind of place you mean, like beaches or forts"
        sign = 1 if i == "like" else -1
        for k in t.kinds:
            e.bump(CATEGORY[k], sign * (2 if CATEGORY[k] == k else 1))
        if i == "dislike":
            remove_place(plan, e, t)
        else:
            add_place(plan, e, part, t)
        return ""
    if i == "question":
        return answer(plan, e, part, t)
    return "?"


def apply(plan: CurrentPlan, e: Edits) -> TripRequest:
    r = plan.request
    inc = [i for i in r.include_places if i not in e.remove_places] + [
        i for i in e.add_places if i not in r.include_places
    ]
    exc = [i for i in r.exclude_places if i not in e.add_places] + [
        i for i in e.remove_places if i not in r.exclude_places
    ]
    data = r.model_dump() | {"include_places": inc, "exclude_places": exc}
    data["stay_id"] = e.stay_id or (plan.stay.id if plan.stay else r.stay_id)
    data["outbound_id"] = e.outbound_id or (plan.outbound.id if plan.outbound else r.outbound_id)
    data["return_id"] = e.return_id or (plan.return_.id if plan.return_ else r.return_id)
    if e.outbound_id:
        data["my_outbound"] = None
    if e.return_id:
        data["my_return"] = None
    if e.budget_inr:
        data["budget_inr"] = e.budget_inr
    if e.travellers:
        data["travellers"] = e.travellers
    return TripRequest(**data)


def trip_line(t: TransportOption) -> str:
    return f"{t.mode} by {t.provider}, {t.depart_at:%a %d %b %H:%M}"


def diff(plan: CurrentPlan, e: Edits, s: TripState) -> list[str]:
    old, new = {p.id: p.name for p in plan.places}, {p.id: p.name for p in s.selected_places}
    out = [f"Added {n}" for i, n in new.items() if i not in old] + [
        f"Removed {n}" for i, n in old.items() if i not in new
    ]
    missed = [p.name for p in plan.options.places if p.id in e.add_places and p.id not in new]
    out += [f"Could not fit {n}, it is closed on your dates or there is no time left" for n in missed]
    if s.selected_stay and (not plan.stay or s.selected_stay.id != plan.stay.id):
        out.append(f"Hotel changed to {s.selected_stay.name}, {money(s.selected_stay.price_per_night_inr)} a night")
    if s.selected_outbound and (not plan.outbound or s.selected_outbound.id != plan.outbound.id):
        out.append(f"Going: {trip_line(s.selected_outbound)}")
    if s.selected_return and (not plan.return_ or s.selected_return.id != plan.return_.id):
        out.append(f"Coming back: {trip_line(s.selected_return)}")
    if s.request.budget_inr != plan.request.budget_inr:
        out.append(f"Budget set to {money(s.request.budget_inr)}")
    if s.request.travellers != plan.request.travellers:
        out.append(f"Travellers set to {s.request.travellers}")
    if s.total_cost != plan.total_cost:
        out.append(f"Total cost {money(plan.total_cost)} to {money(s.total_cost)}")
    return out


def save_turn(user: str, text: str, parts: list[Part], found: list[dict]) -> int:
    with connect() as con:
        cur = con.execute(
            "insert into turns (user, message, parts, adds, created) values (?, ?, ?, ?, ?)",
            (
                user,
                text,
                json.dumps([p.model_dump() for p in parts]),
                json.dumps(found),
                now_iso(),
            ),
        )
        return cur.lastrowid


def revise(plan: CurrentPlan, text: str, user: str) -> Revision:
    e, issues, parts = Edits(), [], []
    for part, t in understand(plan, text):
        why = act(plan, part, t, e)
        part.done = not why
        parts.append(part)
        if why and why not in ("?", "no notes"):
            issues.append(why)
    e.add_places = list(dict.fromkeys(e.add_places))
    e.remove_places = [i for i in dict.fromkeys(e.remove_places) if i not in e.add_places]
    sure = [
        (p.masked, p.intent)
        for p in parts
        if p.done and p.intent not in ("other", "question") and p.confidence >= intent.AUTO_SAVE
    ]
    if intent.room_left(user) >= len(sure):
        intent.add_examples(sure, "auto", retrain=False, user=user)
    sig = {c: n for c, n in e.signals.items() if n}
    if sig:
        memory.remember(user, plan.request.destination, text, sig)
    learned = memory.profile(user, text)
    turn = save_turn(user, text, parts, e.found)
    said = "; ".join(issues)
    note = said[:1].upper() + said[1:] + "." if said else ""
    reply_answer = " ".join(e.answers)
    if not e.changes_plan():
        reply = reply_answer or note or ("Noted, I will remember that for your next trips." if sig else HELP)
        if reply_answer and note:
            reply += f" {note}"
        return Revision(reply=reply, answer=reply_answer, sources=e.sources, learned=learned, parts=parts, turn_id=turn)
    try:
        req = apply(plan, e)
    except ValidationError as err:
        why = err.errors()[0]["msg"].removeprefix("Value error, ")
        return Revision(reply=f"I could not make that change: {why}.", learned=learned, parts=parts, turn_id=turn)
    state = plan_trip(req, learned)
    changes = diff(plan, e, state)
    lead = "Done, here is your updated plan." if changes else "I replanned, but nothing in your plan changed."
    reply = " ".join(x for x in (reply_answer, lead, f"Note: {note}" if note else "") if x)
    return Revision(
        reply=reply,
        changes=changes,
        answer=reply_answer,
        sources=e.sources,
        state=state,
        learned=learned,
        parts=parts,
        turn_id=turn,
    )


def turn(user: str, turn_id: int) -> dict | None:
    with connect() as con:
        row = con.execute(
            "select message, parts, adds from turns where id = ? and user = ?", (turn_id, user)
        ).fetchone()
    return (
        {"message": row[0], "parts": [Part(**p) for p in json.loads(row[1])], "adds": json.loads(row[2])}
        if row
        else None
    )


def mark_rated(turn_id: int):
    with connect() as con:
        if con.execute("select 1 from rated_turns where turn_id = ?", (turn_id,)).fetchone():
            raise AlreadyRated()
        con.execute("insert into rated_turns (turn_id, created) values (?, ?)", (turn_id, now_iso()))


def learn(user: str, turn_id: int, good: bool, fixes: dict[int, str]) -> dict | None:
    t = turn(user, turn_id)
    if t is None:
        return None
    parts = t["parts"]
    if good:
        rows = [(p.masked, p.intent) for p in parts if p.intent != "other"]
    else:
        rows = [(parts[i].masked, name) for i, name in fixes.items() if 0 <= i < len(parts) and name in intent.LABELS]
    if intent.room_left(user) < len(rows):
        raise TooMuchTeaching()
    mark_rated(turn_id)
    if good:
        n = intent.add_examples(rows, "confirmed", retrain=False, user=user)
        if t["adds"]:
            with connect() as con:
                con.executemany(
                    "insert into place_words (place_id, text, created) values (?, ?, ?)",
                    [(a["place_id"], a["text"][:200], now_iso()) for a in t["adds"][:5]],
                )
    else:
        with connect() as con:
            for masked, _ in rows:
                con.execute("delete from examples where text = ? and source = 'auto'", (masked,))
        n = intent.add_examples(rows, "corrected", retrain=False, user=user)
    return {"learned": n, "model": intent.stats()}
