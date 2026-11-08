# critic agent
from pydantic import BaseModel

from app import llm
from app.agents.common import traced
from app.agents.coordinator import add_hint
from app.state import TripState
from app.tools.checks import run_all_checks

MAX_CRITIC_ROUNDS = 2


class Review(BaseModel):
    warnings: list[str]


def user_trips(state: TripState, issues: list) -> tuple[list, list[str]]:
    added = set(state.request.include_places)
    days = {d.date: d for d in state.days}
    keep, notes = [], []
    for i in issues:
        day = days.get(i.day) if i.type == "too_much_travel" else None
        mine = [it.title for it in day.items if it.place_id in added] if day else []
        if mine:
            notes.append(
                f"{day.date:%a %d %b} is a long day out, about {day.km:.0f} km in total, for {', '.join(mine)}"
            )
        else:
            keep.append(i)
    return keep, notes


@traced("critic")
def critic_agent(state: TripState, usage) -> dict:
    issues = run_all_checks(state)
    issues, chosen_far = user_trips(state, issues)
    hints = state.instructions
    for i in issues:
        if i.type == "late_arrival":
            hints = add_hint(hints, "stay", "late_checkin")
        if i.type == "too_much_travel":
            hints = add_hint(hints, "places", "nearby")
    notes = chosen_far
    if not issues:
        plan_text = "\n".join(
            f"{d.date} {d.weekday}: " + ", ".join(f"{i.start} {i.title}" for i in d.items) for d in state.days
        )
        ans = llm.ask_json(
            "You review trip plans. Only flag real practical problems, max 3, one short line each.",
            f"Trip to {state.request.destination}, preferences {state.request.preferences or 'none'}.\n{plan_text}",
            Review,
            usage,
        )
        if ans:
            notes = [f"tip: {w}" for w in ans.warnings[:3]]
    rnd = state.critic_round + 1
    if issues and rnd >= MAX_CRITIC_ROUNDS:
        notes += [f"unresolved: {i.description}" for i in issues]
    return {
        "critic_issues": issues,
        "critic_round": rnd,
        "instructions": hints,
        "critic_notes": notes,
        "_note": f"{len(issues)} issue(s)",
    }
