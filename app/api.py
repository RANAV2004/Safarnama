# api
import json
import logging
import math
import os
from datetime import date
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from app import admin, explore, google_places, llm, media
from app.agents.intake import IntakeError, parse_text
from app.agents.reviser import AlreadyRated, CurrentPlan, TooMuchTeaching, learn, revise
from app.auth import (
    ChangeBody,
    EmailIn,
    ForgotBody,
    LoginBody,
    SignupBody,
    admin_account,
    change_password,
    clear_cookie,
    current_account,
    current_user,
    forgot_password,
    public,
    set_cookie,
    sign_in,
    sign_up,
    start_reset,
)
from app.flights import FlightParseError
from app.flights import parse as parse_booking
from app.graph import PLAN_ERRORS, plan_trip, stream_trip
from app.limits import LIMITS
from app.ml import intent
from app.pdf import PlanDoc, build_pdf, filename
from app.profile import get_profile, options, save_profile
from app.providers.fixture import supported_routes
from app.rag import memory
from app.state import TripRequest, TripState
from app.trips import (
    accept_invite,
    can_view,
    create_invite,
    delete_trip,
    get_trip,
    preview_invite,
    remove_member,
    save_trip,
    stop_invites,
    trips_for,
)

MAX_BODY_BYTES = 1_000_000
AUTH_PER_IP = 30
AUTH_WINDOW = 900
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
}
log = logging.getLogger("safarnama")
app = FastAPI(title="Safarnama", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["authorization", "content-type", "x-requested-with"],
)


@app.middleware("http")
async def guard_requests(request: Request, call_next):
    size = request.headers.get("content-length")
    if size and (not size.isdigit() or int(size) > MAX_BODY_BYTES):
        return JSONResponse({"detail": "request is too large"}, status_code=413)
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if request.url.path.startswith(("/auth", "/trips", "/admin", "/memory", "/profile", "/invites")):
        response.headers["Cache-Control"] = "no-store"
    return response


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class ReviseBody(BaseModel):
    plan: CurrentPlan
    message: str = Field(min_length=1, max_length=500)
    trip_id: int | None = None


class BanBody(BaseModel):
    banned: bool


class LearnBody(BaseModel):
    turn_id: int
    good: bool
    fixes: dict[int, str] = Field(default_factory=dict, max_length=20)


class BookingText(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    mode: Literal["flight", "train", "bus"] | None = None


class ProfileBody(BaseModel):
    interests: list[str] = Field(default_factory=list, max_length=15)


def today() -> date:
    return date.today()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded and os.getenv("TRUST_PROXY") == "1":
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def auth_limit(request: Request):
    key = ("ip", client_ip(request))
    wait = LIMITS.wait(key, AUTH_PER_IP, AUTH_WINDOW)
    if wait:
        raise HTTPException(429, f"too many requests, try again in {math.ceil(wait / 60)} minutes")
    LIMITS.add(key)


def check_dates(req: TripRequest):
    if req.start_date < today():
        raise HTTPException(422, "the trip cannot start in the past, pick today or a later date")


def to_response(s: TripState) -> dict:
    return {
        "request": s.request.model_dump(mode="json"),
        "summary": s.summary,
        "budget_plan": s.budget_plan.model_dump() if s.budget_plan else None,
        "outbound": s.selected_outbound.model_dump(mode="json") if s.selected_outbound else None,
        "return": s.selected_return.model_dump(mode="json") if s.selected_return else None,
        "stay": s.selected_stay.model_dump(mode="json") if s.selected_stay else None,
        "places": [p.model_dump(mode="json") for p in s.selected_places],
        "days": [d.model_dump(mode="json") for d in s.days],
        "breakdown": s.breakdown,
        "total_cost": s.total_cost,
        "over_budget_by": s.over_budget_by,
        "negotiation_rounds": s.round,
        "open_issues": [i.model_dump() for i in s.critic_issues],
        "notes": s.all_notes(),
        "errors": s.errors,
        "trace": [t.model_dump(mode="json") for t in s.trace],
        "options": {
            "outbound": [t.model_dump(mode="json") for t in sorted(s.outbound_options, key=lambda t: t.price_inr)],
            "return": [t.model_dump(mode="json") for t in sorted(s.return_options, key=lambda t: t.price_inr)],
            "stays": [h.model_dump(mode="json") for h in sorted(s.stay_options, key=lambda h: h.price_per_night_inr)],
            "places": [p.model_dump(mode="json") for p in s.place_options],
        },
        **extras(s),
    }


def extras(s: TripState) -> dict:
    cards = explore.all_cards()
    ids = {p.id for p in s.selected_places} | {p.id for p in s.place_options}
    days = [d.model_dump(mode="json") for d in s.days]
    base = (s.selected_stay.lat, s.selected_stay.lng) if s.selected_stay else None
    return {
        "details": {i: cards[i] for i in ids if i in cards},
        "meals": explore.meals(s.request.destination, days, base),
        "stops": explore.stops(s.request.origin, s.request.destination),
    }


def saved(acc: dict, plan: dict, trip_id: int | None) -> dict:
    return plan | {"trip_id": save_trip(acc["id"], plan, trip_id)}


def run(req: TripRequest, acc: dict, trip_id: int | None = None) -> dict:
    try:
        return saved(acc, to_response(plan_trip(req, memory.profile(acc["email"]))), trip_id)
    except PLAN_ERRORS as e:
        raise HTTPException(422, str(e)) from e


def with_cookie(response: Response, s: dict) -> dict:
    set_cookie(response, s["token"])
    return s


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    return {"ok": True, "llm": llm.enabled()}


@app.get("/routes")
def routes():
    return [{"from": a, "to": b} for a, b in supported_routes()]


@app.post("/auth/signup", tags=["auth"], status_code=201, dependencies=[Depends(auth_limit)])
def signup(body: SignupBody, response: Response):
    return with_cookie(response, sign_up(body))


@app.post("/auth/login", tags=["auth"], dependencies=[Depends(auth_limit)])
def login(body: LoginBody, request: Request, response: Response):
    return with_cookie(response, sign_in(body, client_ip(request)))


@app.post("/auth/logout", tags=["auth"])
def logout(response: Response):
    clear_cookie(response)
    return {"ok": True}


@app.post("/auth/forgot/start", tags=["auth"], dependencies=[Depends(auth_limit)])
def forgot_start(body: EmailIn):
    return start_reset(body)


@app.post("/auth/forgot", tags=["auth"], dependencies=[Depends(auth_limit)])
def forgot(body: ForgotBody, response: Response):
    return with_cookie(response, forgot_password(body))


@app.post("/auth/change-password", tags=["auth"])
def change_my_password(body: ChangeBody, response: Response, acc: dict = Depends(current_account)):
    return with_cookie(response, change_password(acc["id"], body))


@app.get("/auth/me", tags=["auth"])
def me(acc: dict = Depends(current_account)):
    return public(acc)


@app.post("/plan")
def plan(req: TripRequest, trip_id: int | None = Query(default=None), acc: dict = Depends(current_account)):
    check_dates(req)
    return run(req, acc, trip_id)


@app.post("/plan/pdf")
def plan_pdf(doc: PlanDoc, user: str = Depends(current_user)):
    headers = {"Content-Disposition": f'attachment; filename="{filename(doc)}"'}
    return Response(build_pdf(doc), media_type="application/pdf", headers=headers)


@app.post("/plan/text")
def plan_from_text(body: TextRequest, acc: dict = Depends(current_account)):
    try:
        req = parse_text(body.text)
    except IntakeError as e:
        raise HTTPException(422, str(e)) from e
    check_dates(req)
    return run(req, acc)


@app.post("/plan/stream")
def plan_stream(req: TripRequest, trip_id: int | None = Query(default=None), acc: dict = Depends(current_account)):
    check_dates(req)

    def event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    def events():
        try:
            final = None
            for mode, chunk in stream_trip(req, memory.profile(acc["email"])):
                if mode == "values":
                    final = chunk
                    continue
                for node, upd in chunk.items():
                    trace = (upd or {}).get("trace") or []
                    yield event({"agent": node, "note": trace[0].note if trace else ""})
            plan = saved(acc, to_response(TripState.model_validate(final)), trip_id)
            yield event({"agent": "done", "plan": plan})
        except PLAN_ERRORS as e:
            yield event({"agent": "error", "note": str(e)})
        except Exception:
            log.exception("planning failed")
            yield event({"agent": "error", "note": "planning failed, please try again"})

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/plan/revise")
def plan_revise(body: ReviseBody, acc: dict = Depends(current_account)):
    try:
        r = revise(body.plan, body.message.strip(), acc["email"])
    except PLAN_ERRORS as e:
        raise HTTPException(422, str(e)) from e
    return {
        "reply": r.reply,
        "changes": r.changes,
        "answer": r.answer,
        "sources": r.sources,
        "plan": saved(acc, to_response(r.state), body.trip_id) if r.state else None,
        "learned": r.learned.model_dump(),
        "understood": [{**p.model_dump(), "label": intent.LABELS[p.intent]} for p in r.parts],
        "turn_id": r.turn_id,
    }


@app.post("/learn", tags=["model"])
def learn_from_feedback(body: LearnBody, tasks: BackgroundTasks, user: str = Depends(current_user)):
    try:
        out = learn(user, body.turn_id, body.good, body.fixes)
    except AlreadyRated as e:
        raise HTTPException(409, "you already rated this reply") from e
    except TooMuchTeaching as e:
        raise HTTPException(429, "thanks, that is enough teaching for today, try again tomorrow") from e
    if out is None:
        raise HTTPException(404, "that message was not found")
    tasks.add_task(intent.train)
    return out


@app.get("/model", tags=["model"])
def model_info(user: str = Depends(current_user)):
    return intent.stats()


@app.get("/profile", tags=["profile"])
def my_profile(user: str = Depends(current_user)):
    return {**get_profile(user), "email": user, "options": options()}


@app.put("/profile", tags=["profile"])
def update_profile(body: ProfileBody, user: str = Depends(current_user)):
    return {**save_profile(user, body.interests), "email": user, "options": options()}


@app.get("/memory", tags=["memory"])
def my_memory(user: str = Depends(current_user)):
    p = memory.profile(user)
    return {
        "likes": p.likes,
        "avoids": p.avoids,
        "interests": p.interests,
        "items": [{"city": i["city"], "text": i["text"], "created": i["created"]} for i in memory.items(user)],
    }


@app.delete("/memory", tags=["memory"])
def forget_me(user: str = Depends(current_user)):
    return {"forgot": memory.forget(user)}


@app.get("/trips", tags=["trips"])
def my_trips(acc: dict = Depends(current_account)):
    return trips_for(acc["id"])


@app.get("/trips/{trip_id}", tags=["trips"])
def one_trip(trip_id: int, acc: dict = Depends(current_account)):
    t = get_trip(trip_id)
    if not t or not can_view(t, acc):
        raise HTTPException(404, "itinerary not found")
    return t


@app.delete("/trips/{trip_id}", tags=["trips"])
def remove_trip(trip_id: int, acc: dict = Depends(current_account)):
    if not delete_trip(trip_id, acc["id"]):
        raise HTTPException(404, "itinerary not found")
    return {"deleted": trip_id}


@app.post("/trips/{trip_id}/invite", tags=["friends"])
def invite_friends(trip_id: int, acc: dict = Depends(current_account)):
    try:
        out = create_invite(trip_id, acc["id"])
    except PermissionError as e:
        raise HTTPException(429, str(e)) from e
    if not out:
        raise HTTPException(404, "itinerary not found")
    return out


@app.delete("/trips/{trip_id}/invite", tags=["friends"])
def stop_inviting(trip_id: int, acc: dict = Depends(current_account)):
    if not stop_invites(trip_id, acc["id"]):
        raise HTTPException(404, "only the person who made this itinerary can do that")
    return {"ok": True}


@app.delete("/trips/{trip_id}/members/{user_id}", tags=["friends"])
def remove_friend(trip_id: int, user_id: int, acc: dict = Depends(current_account)):
    if not remove_member(trip_id, acc["id"], user_id):
        raise HTTPException(404, "that traveller is not on this itinerary")
    return {"removed": user_id}


@app.get("/invites/{token}", tags=["friends"])
def see_invite(token: str = Path(max_length=64), acc: dict = Depends(current_account)):
    out = preview_invite(token, acc["id"])
    if not out:
        raise HTTPException(404, "this invite link has expired or is not valid, ask your friend for a new one")
    return out


@app.post("/invites/{token}/accept", tags=["friends"])
def join_trip(token: str = Path(max_length=64), acc: dict = Depends(current_account)):
    try:
        trip_id = accept_invite(token, acc["id"])
    except PermissionError as e:
        raise HTTPException(409, str(e)) from e
    if not trip_id:
        raise HTTPException(404, "this invite link has expired or is not valid, ask your friend for a new one")
    return {"trip_id": trip_id}


@app.get("/explore", tags=["explore"])
def explore_cities():
    return explore.cities()


@app.get("/explore/{city}", tags=["explore"])
def explore_city(city: str = Path(max_length=60)):
    out = explore.city(city)
    if not out:
        raise HTTPException(404, f"no explore guide for {city} yet")
    return out


@app.get("/stops", tags=["explore"])
def route_stops(origin: str = Query(max_length=60), destination: str = Query(max_length=60)):
    out = explore.stops(origin, destination)
    if not out:
        raise HTTPException(404, "no stops known for this route yet")
    return out


@app.get("/media/{item_id}", tags=["explore"])
def item_media(item_id: str = Path(max_length=80)):
    if item_id.startswith("g-"):
        url = google_places.photo_url(item_id) if google_places.enabled() else None
        return {"title": "", "extract": "", "image": url, "page": "", "credit": "Google Maps"}
    item = explore.card(item_id)
    banner = explore.city_banner(item_id)
    if not item and banner is None:
        raise HTTPException(404, "no such place")
    if banner is not None and not item:
        if banner.startswith("https://"):
            return {"title": item_id, "extract": "", "image": banner, "page": explore.city(item_id)["source"]}
        if banner:
            return media.commons(banner, item_id)
        return {"title": item_id, "extract": "", "image": None, "page": ""}
    if item.get("photo"):
        return media.commons(item["photo"], item["name"])
    if item.get("image"):
        return media.commons(item["image"], item["name"])
    found = media.summary(item["wiki"]) if item.get("wiki") else None
    return found or {"title": "", "extract": "", "image": None, "page": ""}


@app.post("/bookings/parse", tags=["plan"])
def read_booking(body: BookingText, user: str = Depends(current_user)):
    try:
        return parse_booking(body.text, today(), body.mode)
    except FlightParseError as e:
        raise HTTPException(422, str(e)) from e


@app.get("/admin/stats", tags=["admin"])
def admin_stats(acc: dict = Depends(admin_account)):
    return admin.stats()


@app.get("/admin/users", tags=["admin"])
def admin_users(q: str = Query(default="", max_length=100), acc: dict = Depends(admin_account)):
    return admin.search_users(q)


@app.get("/admin/users/{uid}", tags=["admin"])
def admin_user(uid: int, acc: dict = Depends(admin_account)):
    u = admin.user_detail(uid)
    if not u:
        raise HTTPException(404, "no user with that ID")
    return u


@app.post("/admin/users/{uid}/ban", tags=["admin"])
def admin_ban(uid: int, body: BanBody, acc: dict = Depends(admin_account)):
    if uid == acc["id"]:
        raise HTTPException(400, "you cannot ban your own account")
    if not admin.set_banned(uid, body.banned):
        raise HTTPException(404, "no user with that ID")
    return admin.user_detail(uid)


@app.delete("/admin/users/{uid}", tags=["admin"])
def admin_delete(uid: int, acc: dict = Depends(admin_account)):
    if uid == acc["id"]:
        raise HTTPException(400, "you cannot delete your own account here")
    if not admin.delete_user(uid):
        raise HTTPException(404, "no user with that ID")
    return {"deleted": uid}


@app.get("/admin/trips", tags=["admin"])
def admin_trips(q: str = Query(default="", max_length=100), acc: dict = Depends(admin_account)):
    return admin.all_trips(q)
