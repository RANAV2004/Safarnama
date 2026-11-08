# graph tests
from datetime import date

from fastapi.testclient import TestClient

from app.api import app
from app.graph import plan_trip
from app.tools.checks import run_all_checks


def test_normal_budget_fits(make_req):
    s = plan_trip(make_req(budget_inr=20000))
    assert s.over_budget_by == 0
    assert s.selected_outbound and s.selected_return and s.selected_stay
    assert len(s.days) == 4
    assert run_all_checks(s) == []


def test_tight_budget_triggers_negotiation():
    from app.state import TripRequest

    req = TripRequest(
        origin="Indore",
        destination="Goa",
        start_date=date(2026, 11, 20),
        end_date=date(2026, 11, 23),
        budget_inr=12000,
        travellers=2,
    )
    s = plan_trip(req)
    assert s.round >= 1
    assert [t.agent for t in s.trace].count("coordinator") >= 2


def test_late_arrival_gets_fixed_by_critic_loop():
    from app.state import TripRequest

    req = TripRequest(
        origin="Mumbai",
        destination="Goa",
        start_date=date(2026, 11, 20),
        end_date=date(2026, 11, 22),
        budget_inr=30000,
        travellers=1,
    )
    s = plan_trip(req)
    assert "late_arrival" not in [i.type for i in s.critic_issues]


def test_day_trip_works():
    from app.state import TripRequest

    s = plan_trip(
        TripRequest(
            origin="Bengaluru",
            destination="Mysuru",
            start_date=date(2026, 11, 24),
            end_date=date(2026, 11, 24),
            budget_inr=3000,
        )
    )
    assert s.selected_stay is None and s.selected_return is not None
    assert s.over_budget_by == 0


def test_api_plan_and_errors(auth):
    c = TestClient(app)
    ok = c.post(
        "/plan",
        headers=auth,
        json={
            "origin": "Delhi",
            "destination": "Jaipur",
            "start_date": "2026-11-27",
            "end_date": "2026-11-29",
            "budget_inr": 15000,
            "travellers": 2,
        },
    )
    assert ok.status_code == 200 and ok.json()["days"]
    low = c.post(
        "/plan",
        headers=auth,
        json={
            "origin": "Delhi",
            "destination": "Jaipur",
            "start_date": "2026-11-27",
            "end_date": "2026-11-29",
            "budget_inr": 500,
            "travellers": 2,
        },
    )
    assert low.status_code == 422
    assert c.post("/plan/text", headers=auth, json={"text": "goa trip"}).status_code == 422
