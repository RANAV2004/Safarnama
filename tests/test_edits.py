# edits tests
from app.agents.places import places_agent
from app.agents.stay import stay_agent
from app.agents.transport import transport_agent
from app.graph import plan_trip
from app.state import TripState
from app.tools.budget import split_budget


def state(req):
    return TripState(request=req, budget_plan=split_budget(req))


def test_unknown_journey_falls_back_with_note(make_req):
    out = transport_agent(state(make_req(outbound_id="no-such-train")))
    assert out["selected_outbound"] and "chosen journey does not work" in out["notes"][0]


def test_pinned_journey_kept_even_over_budget(make_req):
    req = make_req(budget_inr=12000, outbound_id="ind-goa-0", return_id="goa-ind-0")
    out = transport_agent(state(req))
    assert out["selected_outbound"].id == "ind-goa-0" and out["trace"][0].note == "kept your chosen journeys"
    assert out["floors"]["transport"] == out["selected_outbound"].price_inr + out["selected_return"].price_inr


def test_unknown_hotel_falls_back_with_note(make_req):
    out = stay_agent(state(make_req(stay_id="no-such-hotel")))
    assert out["selected_stay"] and "chosen hotel is not available" in out["notes"][0]


def test_pinned_hotel_survives_critic(make_req):
    s = plan_trip(
        make_req(origin="Mumbai", start_date=make_req().start_date, stay_id="goa-h2", budget_inr=30000, travellers=1)
    )
    assert s.selected_stay.id == "goa-h2"


def test_added_place_closed_all_trip(make_req):
    req = make_req(include_places=["goa-p6"])
    out = places_agent(state(req))
    assert "goa-p6" not in [p.id for p in out["selected_places"]]
    assert out["notes"] == ["Anjuna Flea Market is closed on every day of your trip"]


def test_added_place_counts_towards_floor(make_req):
    req = make_req(include_places=["goa-p4"], travellers=2)
    out = places_agent(state(req))
    assert "goa-p4" in [p.id for p in out["selected_places"]] and out["floors"]["activities"] == 1200


def test_note_without_ai_is_flagged(make_req):
    s = plan_trip(make_req(note="more beaches please"))
    assert "your note is only read when an AI model is connected" in s.notes


def test_far_added_place_becomes_early_day_trip(make_req):
    from datetime import date

    s = plan_trip(
        make_req(
            start_date=date(2026, 11, 17), end_date=date(2026, 11, 20), budget_inr=15000, include_places=["goa-p4"]
        )
    )
    trip_day = next(d for d in s.days if any(i.place_id == "goa-p4" for i in d.items))
    assert trip_day.date not in (s.request.start_date, s.request.end_date)
    others = [p for p in s.selected_places if p.id != "goa-p4"]
    assert others, "free places still fit next to the paid one the user added"
    notes = s.all_notes()
    assert any("long day out" in n and f"{trip_day.date:%a %d %b}" in n for n in notes)
    assert sum("long day out" in n for n in notes) == 1
    assert not s.critic_issues


def test_writer_notes_are_replaced_not_stacked(make_req):
    s = plan_trip(make_req(budget_inr=20000))
    assert len(s.all_notes()) == len(set(s.all_notes()))
