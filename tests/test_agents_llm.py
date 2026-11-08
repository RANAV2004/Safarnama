# agents llm tests
from datetime import date, datetime

import pytest

from app.agents.coordinator import Reallocation, coordinator_agent
from app.agents.critic import Review, critic_agent
from app.agents.intake import IntakeError, ParsedTrip, parse_text
from app.agents.places import PlacesPick, places_agent
from app.agents.stay import StayPick, stay_agent
from app.agents.transport import TransportPick, transport_agent
from app.agents.writer import Summary
from app.graph import plan_trip
from app.providers.fixture import FixtureStays
from app.state import TripState
from app.tools.budget import compute_totals, split_budget
from tests.fakes import answer


def base_state(req):
    return TripState(request=req, budget_plan=split_budget(req))


def test_transport_uses_valid_llm_choice(monkeypatch, make_req):
    answer(monkeypatch, lambda schema, p: TransportPick(choice=1, reason="llm pick"))
    out = transport_agent(base_state(make_req(budget_inr=40000)))
    assert out["trace"][0].note == "llm pick"


def test_transport_ignores_out_of_range_index(monkeypatch, make_req):
    answer(monkeypatch, lambda schema, p: TransportPick(choice=99, reason="bad"))
    out = transport_agent(base_state(make_req(budget_inr=40000)))
    assert out["trace"][0].note == "rule based pick"


def test_stay_rejects_unknown_hotel_id(monkeypatch, make_req):
    answer(monkeypatch, lambda schema, p: StayPick(stay_id="made-up-hotel", reason="bad"))
    out = stay_agent(base_state(make_req()))
    assert out["selected_stay"].id.startswith("goa-") and out["trace"][0].note == "rule based pick"


def test_stay_accepts_offered_id(monkeypatch, make_req):
    answer(monkeypatch, lambda schema, p: StayPick(stay_id="goa-h1", reason="hostel near beach"))
    assert stay_agent(base_state(make_req()))["selected_stay"].id == "goa-h1"


def test_places_rejects_set_that_breaks_budget(monkeypatch, make_req):
    req = make_req(budget_inr=8000)
    answer(monkeypatch, lambda schema, p: PlacesPick(place_ids=["goa-p4", "goa-p8"], reason="safari"))
    out = places_agent(base_state(req))
    assert "goa-p4" not in [p.id for p in out["selected_places"]]


def test_places_drops_unknown_and_duplicate_ids(monkeypatch, make_req):
    answer(monkeypatch, lambda schema, p: PlacesPick(place_ids=["goa-p1", "goa-p1", "nope"], reason="church"))
    out = places_agent(base_state(make_req(budget_inr=40000)))
    assert [p.id for p in out["selected_places"]] == ["goa-p1"]


def over_budget_state(make_req):
    from evals.baseline import single_pass

    s = single_pass(make_req(budget_inr=12100))
    assert s.over_budget_by == 400
    return s


def test_coordinator_rejects_reallocation_below_floor(monkeypatch, make_req):
    s = over_budget_state(make_req)
    answer(monkeypatch, lambda schema, p: Reallocation(transport=10, stay=10, activities=0, reason="impossible"))
    out = coordinator_agent(s)
    assert out["trace"][0].note.startswith("round 1: cut")


def test_coordinator_accepts_valid_reallocation(monkeypatch, make_req):
    s = over_budget_state(make_req)
    t, st = s.floors["transport"], s.floors["stay"]
    answer(
        monkeypatch,
        lambda schema, p: Reallocation(transport=t, stay=st, activities=0, reason="move money to transport"),
    )
    out = coordinator_agent(s)
    assert out["budget_plan"].transport == t and "move money" in out["trace"][0].note


def test_critic_adds_soft_tips_when_plan_is_clean(monkeypatch, make_req):
    s = plan_trip(make_req(budget_inr=20000))
    answer(monkeypatch, lambda schema, p: Review(warnings=["carry sunscreen", "book ahead", "x", "y"]))
    out = critic_agent(s)
    assert out["critic_notes"] == ["tip: carry sunscreen", "tip: book ahead", "tip: x"]


def test_writer_uses_llm_summary(monkeypatch, make_req):
    answer(monkeypatch, lambda schema, p: Summary(summary="Four sunny days in Goa.") if schema is Summary else None)
    assert plan_trip(make_req(budget_inr=20000)).summary == "Four sunny days in Goa."


def test_intake_parses_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("LLM_MODE", "auto")
    answer(
        monkeypatch,
        lambda schema, p: ParsedTrip(
            origin="indore",
            destination="goa",
            start_date=date(2026, 11, 20),
            end_date=date(2026, 11, 23),
            budget_inr=15000,
            travellers=2,
        ),
    )
    req = parse_text("goa from indore 20 to 23 nov, 15k, 2 people", today=date(2026, 11, 3))
    assert (req.origin, req.destination, req.budget_inr) == ("Indore", "Goa", 15000)


@pytest.mark.parametrize(
    "reply",
    [
        None,
        ParsedTrip(
            origin="Goa", destination="Goa", start_date=date(2026, 11, 20), end_date=date(2026, 11, 21), budget_inr=5000
        ),
    ],
)
def test_intake_errors(monkeypatch, reply):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("LLM_MODE", "auto")
    answer(monkeypatch, lambda schema, p: reply)
    with pytest.raises(IntakeError):
        parse_text("goa trip")


def test_totals_with_llm_choices_still_add_up(monkeypatch, make_req):
    answer(monkeypatch, lambda schema, p: None)
    s = plan_trip(make_req(budget_inr=20000))
    assert compute_totals(s)["total_cost"] == s.total_cost


def test_stay_late_checkin_hint_filters_hotels(make_req):
    from app.state import TransportOption

    req = make_req()
    late = TransportOption(
        id="t",
        mode="bus",
        provider="x",
        depart_at=datetime(2026, 11, 19, 20),
        arrive_at=datetime(2026, 11, 20, 21, 50),
        price_inr=1,
        source="test",
    )
    s = base_state(req).model_copy(update={"selected_outbound": late, "instructions": {"stay": ["late_checkin"]}})
    pick = stay_agent(s)["selected_stay"]
    assert pick.late_checkin or pick.checkin_until.hour == 23


def test_stay_takes_cheapest_when_nothing_fits(make_req):
    req = make_req()
    s = TripState(request=req, budget_plan=split_budget(req).model_copy(update={"stay": 100}))
    out = stay_agent(s)
    cheapest = min(FixtureStays().search("Goa", req.start_date, req.end_date, 2), key=lambda h: h.price_per_night_inr)
    assert out["selected_stay"].id == cheapest.id and "over the cap" in out["trace"][0].note


def test_stay_with_no_data_reports_error(make_req):
    req = make_req().model_copy(update={"destination": "Shimla"})
    out = stay_agent(base_state(req))
    assert out["errors"] == ["stay: no stay data for Shimla"]


def test_stay_records_live_fallback(monkeypatch, make_req):
    monkeypatch.setenv("PROVIDER_MODE", "live")
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    out = stay_agent(base_state(make_req()))
    assert out["errors"] and "used fixtures" in out["errors"][0]


def test_agents_handle_empty_results(monkeypatch, make_req):
    from app.agents import places, stay
    from app.providers import Providers

    class Empty:
        last_error = None

        def search(self, *a, **k):
            return []

    empty = Providers(Empty(), Empty(), Empty())
    monkeypatch.setattr(stay, "get_providers", lambda: empty)
    monkeypatch.setattr(places, "get_providers", lambda: empty)
    s = base_state(make_req()).model_copy(update={"instructions": {"places": ["nearby"]}})
    assert stay.stay_agent(s)["errors"] == ["stay: no hotels found in Goa"]
    assert places.places_agent(s)["errors"] == ["places: no places found in Goa"]
