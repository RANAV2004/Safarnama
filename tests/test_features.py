# explore, photos, stops on the way, booked journeys and sharing with friends
from datetime import date, datetime

import httpx
import pytest

from app import explore, media, trips
from app.flights import FlightParseError, parse
from app.graph import plan_trip
from app.state import MyJourney
from tests.conftest import sign_in

TRIP = {
    "origin": "Mumbai",
    "destination": "Goa",
    "start_date": "2026-11-27",
    "end_date": "2026-11-30",
    "budget_inr": 30000,
    "travellers": 2,
}


def test_explore_covers_major_cities(client):
    cities = {c["name"]: c for c in client.get("/explore").json()}
    assert len(cities) >= 40
    for name in ("Goa", "Manali", "Leh", "Rishikesh", "Darjeeling", "Munnar", "Varanasi", "Delhi", "Kathmandu"):
        assert name in cities
    assert {"beach", "mountains", "trekking", "heritage", "city"} <= {t for c in cities.values() for t in c["tags"]}
    assert all(c["counts"]["attraction"] >= 2 for c in cities.values())


def test_explore_city_has_sections_info_and_top_places(client):
    manali = client.get("/explore/Manali").json()
    assert set(manali["sections"]) == {"attraction", "restaurant", "cafe", "photo"}
    assert {"intro", "understand", "get_around"} <= set(manali["info"])
    assert "Manali" in manali["info"]["intro"] and manali["source"].startswith("https://en.wikivoyage.org/wiki/")
    names = [c["name"] for c in manali["sections"]["attraction"]]
    assert "Rohtang Pass" in names and "Hidimba Temple" in names
    assert manali["top"] and manali["top"][0]["id"] == manali["sections"]["attraction"][0]["id"]
    assert all(c["maps_url"].startswith("https://www.google.com/maps/search/") for c in manali["sections"]["cafe"])
    assert "CC BY-SA" in manali["licence"]
    assert client.get("/explore/Atlantis").status_code == 404


def test_every_card_has_a_name_text_and_valid_position():
    for card in explore.all_cards().values():
        assert card["name"] and card["text"]
        if card.get("lat") is not None:
            assert -90 <= card["lat"] <= 90 and -180 <= card["lng"] <= 180


def test_explore_card_ids_are_unique_per_city():
    for c in explore.data()["cities"].values():
        for kind, cards in c["sections"].items():
            ids = [x["id"] for x in cards]
            assert len(ids) == len(set(ids)), kind


@pytest.mark.parametrize("origin,destination", [("Mumbai", "Goa"), ("Goa", "Mumbai")])
def test_stops_come_in_travel_order(client, origin, destination):
    out = client.get("/stops", params={"origin": origin, "destination": destination}).json()
    progress = [s["progress"] for s in out["stops"]]
    assert len(progress) >= 3 and progress == sorted(progress) and out["road"]
    distances = [s["from_start_km"] for s in out["stops"]]
    assert distances[0] < distances[-1]
    assert all(s["text"] and s["source"].startswith("https://en.wikivoyage.org/") for s in out["stops"])


def test_stop_order_flips_with_direction(client):
    there = [s["id"] for s in client.get("/stops", params={"origin": "Mumbai", "destination": "Goa"}).json()["stops"]]
    back = [s["id"] for s in client.get("/stops", params={"origin": "Goa", "destination": "Mumbai"}).json()["stops"]]
    assert there == list(reversed(back))


def test_unknown_route_has_no_stops(client):
    assert client.get("/stops", params={"origin": "Goa", "destination": "Jaipur"}).status_code == 404


class Reply:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data


def test_media_fetches_once_and_caches(client, monkeypatch):
    calls = []
    page = {
        "title": "Fort Aguada",
        "extract": "A fort.",
        "thumbnail": {"source": "https://upload.wikimedia.org/x.jpg"},
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Fort_Aguada"}},
    }

    def fake(url, **kw):
        calls.append(url)
        assert kw["headers"]["User-Agent"].startswith("Safarnama")
        return Reply(page)

    monkeypatch.setenv("WIKI_MODE", "live")
    monkeypatch.setattr(media.httpx, "get", fake)
    first = client.get("/media/goa-p2").json()
    assert first["image"] == "https://upload.wikimedia.org/x.jpg" and first["page"].endswith("Fort_Aguada")
    assert client.get("/media/goa-p2").json() == first and len(calls) == 1
    goa = client.get("/media/Goa").json()
    assert goa["image"].startswith("https://commons.wikimedia.org/wiki/Special:FilePath/")
    with_photo = next(c for c in explore.all_cards().values() if c.get("image"))
    shot = client.get(f"/media/{with_photo['id']}").json()
    assert shot["image"].startswith("https://commons.wikimedia.org/") and "/File:" in shot["page"]
    assert client.get("/media/not-a-place").status_code == 404
    plain = next(c for c in explore.all_cards().values() if not c.get("image") and not c.get("wiki"))
    assert client.get(f"/media/{plain['id']}").json()["image"] is None


def test_media_rejects_odd_images_and_remembers_misses(monkeypatch):
    monkeypatch.setenv("WIKI_MODE", "live")
    monkeypatch.setattr(
        media.httpx, "get", lambda url, **kw: Reply({"thumbnail": {"source": "https://evil.example/x.jpg"}})
    )
    assert media.summary("Somewhere")["image"] is None

    def down(url, **kw):
        raise httpx.ConnectTimeout("slow")

    monkeypatch.setattr(media.httpx, "get", down)
    assert media.summary("Nowhere", now=1000) is None
    monkeypatch.setattr(media.httpx, "get", lambda url, **kw: Reply({}, 404))
    assert media.summary("Nowhere", now=1001) is None
    assert media.summary("Nowhere", now=1000 + media.KEEP_MISSING + 1) is None
    monkeypatch.setenv("WIKI_MODE", "off")
    assert media.summary("Elsewhere") is None


def test_plan_has_details_meals_and_stops(client, auth):
    plan = client.post("/plan", json=TRIP, headers=auth).json()
    assert all(p["id"] in plan["details"] for p in plan["places"])
    assert plan["details"][plan["places"][0]["id"]]["text"]
    assert plan["stops"]["stops"] and plan["stops"]["origin"] == "Mumbai"
    assert plan["meals"] and all(m["picks"] for m in plan["meals"])
    assert all(p["km"] <= explore.MEAL_KM for m in plan["meals"] for p in m["picks"])


def test_meals_need_a_known_city():
    assert explore.meals("Nowhere", [], None) == []
    assert explore.meals("Goa", [{"date": "2026-11-27", "items": []}], None) == []


@pytest.mark.parametrize(
    "text,expected",
    [
        ("6E 5321 BOM 06:10 GOI 07:25 12 Dec 2026", ("IndiGo", "6E 5321", "Mumbai", "Goa", "2026-12-12T07:25")),
        (
            "AI 663 | 12/12/2026 | DEL 23:15 -> GOI 01:50 +1",
            ("Air India", "AI 663", "Delhi", "Goa", "2026-12-13T01:50"),
        ),
        (
            "Akasa QP 1123 Bangalore to Goa Dec 20 9:30 PM - 10:45 PM",
            ("Akasa Air", "QP 1123", "Bengaluru", "Goa", "2026-12-20T22:45"),
        ),
        (
            "Train No: 10103 CSMT 07:10 Madgaon 19:40 15 Dec 2026",
            ("Indian Railways", "10103", "Mumbai", "Goa", "2026-12-15T19:40"),
        ),
        (
            "SG 8123 DEL to JAI on 2026-11-28 departs 18:05 arrives 19:10",
            ("SpiceJet", "SG 8123", "Delhi", "Jaipur", "2026-11-28T19:10"),
        ),
    ],
)
def test_booking_text_is_read(text, expected):
    out = parse(text, date(2026, 11, 7))
    assert (out["provider"], out["number"], out["from_city"], out["to_city"], out["arrive_at"]) == expected


def test_bus_and_dates_without_a_year():
    out = parse("Volvo bus Mumbai 20:00 to Goa 08:30 on 3 Jan", date(2026, 11, 7))
    assert out["mode"] == "bus" and out["depart_at"] == "2027-01-03T20:00" and out["arrive_at"] == "2027-01-04T08:30"


@pytest.mark.parametrize(
    "text",
    ["", "6E 5321 BOM 06:10 12 Dec 2026", "6E 5321 BOM 06:10 GOI 07:25", "6E 1 1 Dec 2026 06:10 and 5 Dec 2026 07:00"],
)
def test_bad_booking_text_explains_why(text):
    with pytest.raises(FlightParseError):
        parse(text, date(2026, 11, 7))


def test_booking_endpoint(client, auth):
    ok = client.post("/bookings/parse", json={"text": "6E 5321 BOM 06:10 GOI 07:25 28 Nov 2026"}, headers=auth)
    assert ok.status_code == 200 and ok.json()["number"] == "6E 5321"
    assert client.post("/bookings/parse", json={"text": "hello"}, headers=auth).status_code == 422
    assert client.post("/bookings/parse", json={"text": "hello"}).status_code == 401


def test_plan_is_built_around_my_flight(make_req):
    flight = MyJourney(
        provider="IndiGo",
        number="6E 5321",
        depart_at=datetime(2026, 11, 21, 6, 10),
        arrive_at=datetime(2026, 11, 21, 7, 25),
        price_inr=9000,
    )
    req = make_req(origin="Mumbai", start_date=date(2026, 11, 20), my_outbound=flight)
    assert req.start_date == date(2026, 11, 21)
    s = plan_trip(req)
    assert s.selected_outbound.id == "mine-out" and s.selected_outbound.provider == "IndiGo 6E 5321"
    first = s.days[0].items[0]
    assert s.days[0].date == date(2026, 11, 21) and first.kind == "travel" and first.end == "07:25"
    assert s.breakdown["transport"] >= 9000


def test_a_later_flight_moves_the_whole_trip(make_req):
    flight = MyJourney(depart_at=datetime(2026, 11, 28, 6, 10), arrive_at=datetime(2026, 11, 28, 7, 25))
    req = make_req(start_date=date(2026, 11, 20), end_date=date(2026, 11, 23), my_outbound=flight)
    assert (req.start_date, req.end_date) == (date(2026, 11, 28), date(2026, 12, 1))


def test_plan_with_both_journeys_booked(make_req):
    out = MyJourney(depart_at=datetime(2026, 11, 20, 6), arrive_at=datetime(2026, 11, 20, 8))
    back = MyJourney(
        mode="train",
        provider="Mandovi Express",
        depart_at=datetime(2026, 11, 23, 9),
        arrive_at=datetime(2026, 11, 23, 21),
    )
    s = plan_trip(make_req(origin="Mumbai", my_outbound=out, my_return=back))
    assert s.selected_outbound.id == "mine-out" and s.selected_return.id == "mine-back"
    assert any("planned around your booked" in t.note for t in s.trace)


@pytest.mark.parametrize(
    "kw",
    [
        {"depart_at": datetime(2026, 11, 20, 8), "arrive_at": datetime(2026, 11, 20, 6)},
        {"depart_at": datetime(2026, 11, 20, 8), "arrive_at": datetime(2026, 11, 25, 6)},
    ],
)
def test_impossible_journeys_are_refused(kw):
    with pytest.raises(ValueError):
        MyJourney(**kw)


def test_return_before_arrival_is_refused(make_req):
    out = MyJourney(depart_at=datetime(2026, 11, 20, 6), arrive_at=datetime(2026, 11, 20, 8))
    back = MyJourney(depart_at=datetime(2026, 11, 20, 7), arrive_at=datetime(2026, 11, 20, 9))
    with pytest.raises(ValueError):
        make_req(my_outbound=out, my_return=back)


def test_chat_travel_change_replaces_a_booked_journey(make_req):
    from app.agents import reviser

    flight = MyJourney(provider="IndiGo", depart_at=datetime(2026, 11, 20, 6), arrive_at=datetime(2026, 11, 20, 8))
    s = plan_trip(make_req(origin="Mumbai", my_outbound=flight))
    plan = reviser.CurrentPlan(
        request=s.request,
        outbound=s.selected_outbound,
        return_=s.selected_return,
        stay=s.selected_stay,
        places=s.selected_places,
        options=reviser.PlanOptions(
            outbound=s.outbound_options, return_=s.return_options, stays=s.stay_options, places=s.place_options
        ),
    )
    r = reviser.revise(plan, "go by train", "me@x.com")
    assert r.state.request.my_outbound is None and r.state.selected_outbound.mode == "train"


def test_friends_join_with_an_invite_link(client):
    owner = sign_in(client, name="Asha")
    friend = sign_in(client, name="Ravi")
    stranger = sign_in(client, name="Sam")
    plan = client.post("/plan", json=TRIP, headers=owner).json()
    tid = plan["trip_id"]
    assert client.get(f"/trips/{tid}", headers=friend).status_code == 404
    link = client.post(f"/trips/{tid}/invite", headers=owner).json()
    assert len(link["token"]) >= 20 and link["days"] == 7
    assert client.post(f"/trips/{tid}/invite", headers=stranger).status_code == 404
    seen = client.get(f"/invites/{link['token']}", headers=friend).json()
    assert seen["invited_by"] == "Asha" and seen["joined"] is False and seen["destination"] == "Goa"
    assert client.post(f"/invites/{link['token']}/accept", headers=friend).json() == {"trip_id": tid}
    assert client.post(f"/invites/{link['token']}/accept", headers=friend).json() == {"trip_id": tid}
    shared = client.get("/trips", headers=friend).json()
    assert shared[0]["id"] == tid and shared[0]["shared"] is True and shared[0]["owner_name"] == "Asha"
    trip = client.get(f"/trips/{tid}", headers=friend).json()
    assert [m["name"] for m in trip["members"]] == ["Asha", "Ravi"]
    again = client.post(f"/plan?trip_id={tid}", json={**TRIP, "budget_inr": 35000}, headers=friend).json()
    assert again["trip_id"] == tid
    assert client.get(f"/trips/{tid}", headers=owner).json()["budget_inr"] == 35000
    assert client.delete(f"/trips/{tid}", headers=friend).status_code == 404
    assert client.get(f"/invites/{link['token']}", headers=stranger).status_code == 200
    assert client.get("/invites/not-a-real-token", headers=friend).status_code == 404


def test_members_can_leave_or_be_removed(client):
    owner, friend, other = sign_in(client), sign_in(client), sign_in(client)
    tid = client.post("/plan", json=TRIP, headers=owner).json()["trip_id"]
    token = client.post(f"/trips/{tid}/invite", headers=owner).json()["token"]
    for head in (friend, other):
        client.post(f"/invites/{token}/accept", headers=head)
    ids = {m["name"]: m["id"] for m in client.get(f"/trips/{tid}", headers=owner).json()["members"]}
    friend_id = client.get("/auth/me", headers=friend).json()["id"]
    other_id = client.get("/auth/me", headers=other).json()["id"]
    assert len(ids) >= 1
    assert client.delete(f"/trips/{tid}/members/{other_id}", headers=friend).status_code == 404
    assert client.delete(f"/trips/{tid}/members/{friend_id}", headers=friend).json() == {"removed": friend_id}
    assert client.delete(f"/trips/{tid}/members/{other_id}", headers=owner).json() == {"removed": other_id}
    assert client.get(f"/trips/{tid}", headers=friend).status_code == 404
    assert client.delete(f"/trips/{tid}/invite", headers=friend).status_code == 404
    assert client.delete(f"/trips/{tid}/invite", headers=owner).json() == {"ok": True}
    assert client.post(f"/invites/{token}/accept", headers=friend).status_code == 404


def test_invites_expire_and_have_limits(client, monkeypatch):
    owner = sign_in(client)
    uid = client.get("/auth/me", headers=owner).json()["id"]
    tid = client.post("/plan", json=TRIP, headers=owner).json()["trip_id"]
    old = trips.create_invite(tid, uid, now=1000)
    assert trips.preview_invite(old["token"], uid, now=1000 + 8 * 86400) is None
    assert trips.accept_invite(old["token"], uid, now=1000 + 8 * 86400) is None
    monkeypatch.setattr(trips, "INVITES_PER_DAY", 2)
    client.post(f"/trips/{tid}/invite", headers=owner)
    client.post(f"/trips/{tid}/invite", headers=owner)
    assert client.post(f"/trips/{tid}/invite", headers=owner).status_code == 429
    monkeypatch.setattr(trips, "INVITES_PER_DAY", 20)
    monkeypatch.setattr(trips, "MAX_MEMBERS", 1)
    token = client.post(f"/trips/{tid}/invite", headers=owner).json()["token"]
    assert client.post(f"/invites/{token}/accept", headers=sign_in(client)).status_code == 409


def test_deleting_a_trip_or_user_cleans_up_sharing(client, monkeypatch):
    from app import admin
    from app.db import connect

    owner, friend = sign_in(client), sign_in(client)
    tid = client.post("/plan", json=TRIP, headers=owner).json()["trip_id"]
    token = client.post(f"/trips/{tid}/invite", headers=owner).json()["token"]
    client.post(f"/invites/{token}/accept", headers=friend)
    assert client.delete(f"/trips/{tid}", headers=owner).json() == {"deleted": tid}
    with connect() as con:
        assert con.execute("select count(*) from trip_members").fetchone()[0] == 0
        assert con.execute("select count(*) from trip_invites").fetchone()[0] == 0
    tid = client.post("/plan", json=TRIP, headers=owner).json()["trip_id"]
    token = client.post(f"/trips/{tid}/invite", headers=owner).json()["token"]
    client.post(f"/invites/{token}/accept", headers=friend)
    friend_id = client.get("/auth/me", headers=friend).json()["id"]
    assert admin.delete_user(friend_id)
    with connect() as con:
        assert con.execute("select count(*) from trip_members").fetchone()[0] == 0


IRCTC = """Electronic Reservation Slip (ERS)
PNR No: 4512345678   Train No./Name: 12051/JANSHATABDI EXP   Class: CHAIR CAR (CC)
Booked From: MUMBAI CSMT (CSMT)   Boarding At: DADAR (DR)   To: MADGAON (MAO)
Date of Journey: 21-Nov-2026
Departure* 05:10 21-Nov-2026   Arrival* 14:05 21-Nov-2026
Transaction ID: 100004567891   Booked on 15-Oct-2026 10:32:05 HRS
Total Fare (all inclusive): Rs. 1,250.00"""
REDBUS = """redBus Ticket
Ticket No: TS7H123456  PNR: 9876543
Travels: Neeta Tours and Travels
Bus Type: A/C Sleeper (2+1)
From: Mumbai   To: Goa
Journey Date: 20 Nov 2026
Reporting Time: 19:30   Departure Time: 20:00
Arrival Time: 21 Nov 2026 08:30
Total Fare: INR 1450"""


def test_irctc_ticket_is_read():
    out = parse(IRCTC, date(2026, 11, 7))
    assert (out["mode"], out["provider"], out["number"]) == ("train", "Jan Shatabdi Express", "12051")
    assert (out["from_city"], out["to_city"]) == ("Mumbai", "Goa")
    assert (out["depart_at"], out["arrive_at"], out["price_inr"]) == ("2026-11-21T05:10", "2026-11-21T14:05", 1250)


def test_overnight_train_is_read():
    text = "Train No./Name: 10103/MANDOVI EXP From: MUMBAI CSMT (CSMT) To: MADGAON (MAO) Departure: 22:00 21-Nov-2026  Arrival: 10:45 22-Nov-2026"
    out = parse(text, date(2026, 11, 7))
    assert (out["provider"], out["depart_at"], out["arrive_at"]) == (
        "Mandovi Express",
        "2026-11-21T22:00",
        "2026-11-22T10:45",
    )


def test_redbus_ticket_is_read():
    out = parse(REDBUS, date(2026, 11, 7))
    assert (out["mode"], out["provider"], out["price_inr"]) == ("bus", "Neeta Tours and Travels", 1450)
    assert (out["depart_at"], out["arrive_at"]) == ("2026-11-20T20:00", "2026-11-21T08:30")


def test_chosen_mode_wins(client, auth):
    out = client.post(
        "/bookings/parse", json={"text": "Mumbai 20:00 to Goa 08:30 on 28 Nov 2026", "mode": "bus"}, headers=auth
    ).json()
    assert out["mode"] == "bus" and out["provider"] == "Bus" and out["arrive_at"] == "2026-11-29T08:30"
    assert (
        parse("Mumbai 20:00 to Goa 08:30 on 28 Nov 2026", date(2026, 11, 7), "train")["provider"] == "Indian Railways"
    )
    assert client.post("/bookings/parse", json={"text": "x", "mode": "boat"}, headers=auth).status_code == 422


def test_placeholder_banners_are_skipped_and_cities_get_a_landmark(client):
    from scripts.build_explore import banner

    assert banner("{{pagebanner|Pagebanner default.jpg}}") is None
    assert banner("{{pagebanner|Manali_banner.jpg|caption=x}}") == "Manali_banner.jpg"
    cities = client.get("/explore").json()
    assert all(c["photo_id"] is None or c["photo_id"].startswith("x-") for c in cities)
    plain = next(c["name"] for c in cities if not c["banner"])
    shot = client.get(f"/media/{plain}").json()
    assert shot["image"] is None or shot["image"].startswith("https://commons.wikimedia.org/")
