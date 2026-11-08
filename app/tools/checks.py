# checks
from datetime import datetime, time, timedelta

from app.state import CriticIssue, TripState

MAX_DAY_HOURS = 10
MAX_DAY_KM = 60
TRANSFER_MIN = 45
RETURN_GAP_MIN = 120
NIGHT_ENDS = time(5, 0)


def desk_closed(reach: datetime, until: time) -> bool:
    return reach.time() > until or reach.time() < NIGHT_ENDS


def hm(s: str):
    return datetime.strptime(s, "%H:%M").time()


def check_late_arrival(state: TripState) -> list[CriticIssue]:
    out, stay = state.selected_outbound, state.selected_stay
    if not out or not stay or stay.late_checkin or state.request.nights == 0:
        return []
    reach = out.arrive_at + timedelta(minutes=TRANSFER_MIN)
    if desk_closed(reach, stay.checkin_until):
        return [
            CriticIssue(
                type="late_arrival",
                description=f"reach {stay.name} at {reach:%H:%M} but desk closes at {stay.checkin_until:%H:%M}",
                responsible_agent="stay",
            )
        ]
    return []


def check_days(state: TripState) -> list[CriticIssue]:
    issues = []
    places = {p.id: p for p in state.place_options + state.selected_places}
    for day in state.days:
        busy = 0.0
        for it in day.items:
            if it.kind != "place" or it.place_id not in places:
                continue
            p = places[it.place_id]
            if day.weekday in p.closed_days:
                issues.append(
                    CriticIssue(
                        type="closed_day",
                        description=f"{p.name} is closed on {day.weekday}",
                        responsible_agent="writer",
                    )
                )
            if hm(it.start) < p.opens or hm(it.end) > p.closes:
                issues.append(
                    CriticIssue(
                        type="opening_hours",
                        description=f"{p.name} visit {it.start}-{it.end} is outside {p.opens:%H:%M}-{p.closes:%H:%M}",
                        responsible_agent="writer",
                    )
                )
            busy += p.est_hours
        if busy > MAX_DAY_HOURS:
            issues.append(
                CriticIssue(
                    type="long_day",
                    description=f"{day.date} has {busy:.1f} hours of sightseeing",
                    responsible_agent="writer",
                )
            )
        if day.km > MAX_DAY_KM:
            issues.append(
                CriticIssue(
                    type="too_much_travel",
                    day=day.date,
                    description=f"{day.date} needs {day.km:.0f} km of local travel",
                    responsible_agent="places",
                )
            )
    return issues


def check_arrival_departure(state: TripState) -> list[CriticIssue]:
    issues = []
    if not state.days:
        return issues
    first, last = state.days[0], state.days[-1]
    out, back = state.selected_outbound, state.selected_return
    if out:
        ready = (out.arrive_at + timedelta(minutes=TRANSFER_MIN)).time()
        for it in first.items:
            if it.kind == "place" and out.arrive_at.date() == first.date and hm(it.start) < ready:
                issues.append(
                    CriticIssue(
                        type="before_arrival",
                        description=f"{it.title} at {it.start} is before you arrive",
                        responsible_agent="writer",
                    )
                )
    if back:
        leave_by = back.depart_at - timedelta(minutes=RETURN_GAP_MIN)
        for it in last.items:
            ends = datetime.combine(last.date, hm(it.end))
            if it.kind == "place" and back.depart_at.date() == last.date and ends > leave_by:
                issues.append(
                    CriticIssue(
                        type="misses_return",
                        description=f"{it.title} ends {it.end}, too close to the {back.depart_at:%H:%M} departure",
                        responsible_agent="writer",
                    )
                )
    return issues


def run_all_checks(state: TripState) -> list[CriticIssue]:
    return check_late_arrival(state) + check_days(state) + check_arrival_departure(state)
