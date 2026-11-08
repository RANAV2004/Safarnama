# checks tests
from datetime import date, datetime

from app.state import DayPlan, PlaceOption, PlanItem, StayOption, TransportOption, TripState
from app.tools.checks import run_all_checks


def place(**kw):
    return PlaceOption(
        **{
            "id": "p1",
            "name": "Museum",
            "lat": 15.5,
            "lng": 73.8,
            "source": "test",
            "opens": "09:00",
            "closes": "17:00",
            **kw,
        }
    )


def test_catches_closed_day(make_req):
    p = place(closed_days=["Monday"])
    s = TripState(
        request=make_req(),
        place_options=[p],
        days=[
            DayPlan(
                date=date(2026, 11, 23),
                weekday="Monday",
                items=[PlanItem(start="10:00", end="11:00", title="Museum", kind="place", place_id="p1")],
            )
        ],
    )
    assert "closed_day" in [i.type for i in run_all_checks(s)]


def test_catches_outside_opening_hours(make_req):
    s = TripState(
        request=make_req(),
        place_options=[place()],
        days=[
            DayPlan(
                date=date(2026, 11, 21),
                weekday="Saturday",
                items=[PlanItem(start="16:30", end="18:00", title="Museum", kind="place", place_id="p1")],
            )
        ],
    )
    assert "opening_hours" in [i.type for i in run_all_checks(s)]


def test_catches_late_arrival_and_blames_stay(make_req):
    out = TransportOption(
        id="t",
        mode="bus",
        provider="x",
        depart_at=datetime(2026, 11, 20, 14),
        arrive_at=datetime(2026, 11, 20, 23, 30),
        price_inr=1000,
        source="test",
    )
    stay = StayOption(
        id="h", name="Hotel", price_per_night_inr=1000, checkin_until="22:00", lat=15.5, lng=73.8, source="test"
    )
    issues = run_all_checks(TripState(request=make_req(), selected_outbound=out, selected_stay=stay))
    assert [(i.type, i.responsible_agent) for i in issues] == [("late_arrival", "stay")]


def test_clean_plan_has_no_issues(make_req):
    s = TripState(
        request=make_req(),
        place_options=[place()],
        days=[
            DayPlan(
                date=date(2026, 11, 21),
                weekday="Saturday",
                items=[PlanItem(start="10:00", end="12:00", title="Museum", kind="place", place_id="p1")],
            )
        ],
    )
    assert run_all_checks(s) == []


def test_arriving_after_midnight_misses_the_desk(make_req):
    out = TransportOption(
        id="o",
        mode="bus",
        provider="x",
        depart_at=datetime(2026, 11, 19, 18),
        arrive_at=datetime(2026, 11, 20, 0, 30),
        price_inr=1,
        overnight=True,
        source="t",
    )
    stay = StayOption(id="s", name="H", price_per_night_inr=1, lat=0, lng=0, source="t")
    issues = run_all_checks(TripState(request=make_req(), selected_outbound=out, selected_stay=stay))
    assert [i.type for i in issues] == ["late_arrival"]


def test_early_morning_return_leaves_no_time_that_day(make_req):
    req = make_req()
    back = TransportOption(
        id="b",
        mode="bus",
        provider="x",
        depart_at=datetime(2026, 11, 23, 1, 0),
        arrive_at=datetime(2026, 11, 23, 9),
        price_inr=1,
        source="t",
    )
    day = DayPlan(
        date=req.end_date,
        weekday="Monday",
        items=[PlanItem(start="10:00", end="12:00", title="Fort", kind="place")],
    )
    issues = run_all_checks(TripState(request=req, selected_return=back, days=[day]))
    assert [i.type for i in issues] == ["misses_return"]
