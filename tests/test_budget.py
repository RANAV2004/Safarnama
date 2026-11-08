# budget tests
from datetime import date

import pytest
from pydantic import ValidationError

from app.providers.fixture import FixturePlaces, FixtureStays, FixtureTransport
from app.state import TripRequest, TripState
from app.tools.budget import BudgetTooLowError, compute_totals, food_floor, split_budget


@pytest.mark.parametrize("budget", [20000, 10001, 9999, 33333, 150001])
def test_envelopes_sum_exactly(make_req, budget):
    plan = split_budget(make_req(budget_inr=budget))
    assert plan.total == budget


def test_day_trip_has_no_stay(make_req):
    plan = split_budget(make_req(end_date=date(2026, 11, 20), budget_inr=8000))
    assert plan.stay == 0
    assert plan.total == 8000


def test_food_floor_takes_from_activities(make_req):
    req = make_req(budget_inr=6000)
    plan = split_budget(req)
    assert plan.food == food_floor(req) == 4000
    assert plan.activities == 0
    assert plan.total == 6000


def test_budget_below_food_floor_raises(make_req):
    with pytest.raises(BudgetTooLowError):
        split_budget(make_req(budget_inr=3999))


def test_end_before_start_is_rejected():
    with pytest.raises(ValidationError):
        TripRequest(
            origin="Delhi",
            destination="Jaipur",
            start_date=date(2026, 11, 5),
            end_date=date(2026, 11, 4),
            budget_inr=5000,
        )


def test_same_city_is_rejected():
    with pytest.raises(ValidationError):
        TripRequest(
            origin="goa ", destination="Goa", start_date=date(2026, 11, 5), end_date=date(2026, 11, 6), budget_inr=5000
        )


def selected_state(req):
    t = FixtureTransport()
    s = TripState(request=req, budget_plan=split_budget(req))
    s.selected_outbound = t.search(req.origin, req.destination, req.start_date, req.travellers, "arrive_on")[0]
    s.selected_return = t.search(req.destination, req.origin, req.end_date, req.travellers, "depart_on")[0]
    s.selected_stay = FixtureStays().search(req.destination, req.start_date, req.end_date, req.travellers)[4]
    s.selected_places = FixturePlaces().search(req.destination)[:3]
    return s


def test_totals_over_budget(make_req):
    req = make_req(budget_inr=20000)
    res = compute_totals(selected_state(req))
    assert res["total_cost"] == sum(res["breakdown"].values())
    assert res["over_budget_by"] == res["total_cost"] - 20000 > 0


def test_totals_under_budget_is_zero_not_negative(make_req):
    req = make_req(budget_inr=500000)
    assert compute_totals(selected_state(req))["over_budget_by"] == 0
