# coordinator agent
from pydantic import BaseModel

from app import llm
from app.agents.common import money, traced
from app.state import BudgetPlan, TripState
from app.tools.budget import compute_totals, split_budget

MAX_ROUNDS = 3
CATEGORY_AGENT = {"transport": "transport", "stay": "stay", "activities": "places"}


class Reallocation(BaseModel):
    transport: int
    stay: int
    activities: int
    reason: str


def add_hint(hints: dict, agent: str, hint: str) -> dict:
    out = {k: list(v) for k, v in hints.items()}
    if hint not in out.setdefault(agent, []):
        out[agent].append(hint)
    return out


def stuck(state: TripState, why: str) -> dict:
    msg = f"could not fit the budget, still over by {money(state.over_budget_by)}"
    notes = [] if msg in state.notes else [msg]
    return {"rerun": [], "notes": notes, "_note": why}


def rule_based_cuts(state: TripState) -> dict[str, int]:
    spent, floors = state.breakdown, state.floors
    room = {c: max(0, spent.get(c, 0) - floors.get(c, 0)) for c in CATEGORY_AGENT}
    left, cuts = state.over_budget_by, {}
    for c in sorted(room, key=room.get, reverse=True):
        if left <= 0 or room[c] == 0:
            continue
        cuts[c] = min(room[c], left)
        left -= cuts[c]
    return cuts


def valid_reallocation(r: Reallocation, state: TripState) -> bool:
    food = state.budget_plan.food
    for c in CATEGORY_AGENT:
        if getattr(r, c) < state.floors.get(c, 0):
            return False
    return r.transport + r.stay + r.activities + food <= state.request.budget_inr


@traced("coordinator")
def coordinator_agent(state: TripState, usage) -> dict:
    if state.budget_plan is None:
        plan = split_budget(state.request)
        notes = (
            ["your note is only read when an AI model is connected"] if state.request.note and not llm.enabled() else []
        )
        return {
            "budget_plan": plan,
            "rerun": ["transport", "stay", "places"],
            "notes": notes,
            "_note": f"split {money(state.request.budget_inr)}",
        }
    plan, spent = state.budget_plan, state.breakdown
    envelopes = {c: getattr(plan, c) for c in CATEGORY_AGENT}
    new_env, reason = None, ""
    prompt = f"Budget {money(state.request.budget_inr)}, over by {money(state.over_budget_by)}. Food fixed at {money(plan.food)}.\nCurrent envelopes {envelopes}\nActual spend {spent}\nCheapest possible spend {state.floors}\nGive new envelopes for transport, stay and activities so the trip fits. Never go below the cheapest possible spend."
    ans = llm.ask_json(
        "You are the coordinator of a multi agent trip planner. You move money between agents.",
        prompt,
        Reallocation,
        usage,
    )
    if ans and valid_reallocation(ans, state):
        new_env, reason = {c: getattr(ans, c) for c in CATEGORY_AGENT}, ans.reason
    else:
        cuts = rule_based_cuts(state)
        if cuts:
            new_env = {
                c: spent.get(c, 0) - cuts.get(c, 0) if c in cuts else max(envelopes[c], spent.get(c, 0))
                for c in CATEGORY_AGENT
            }
            reason = "cut " + ", ".join(f"{c} by {money(v)}" for c, v in cuts.items())
    if not new_env:
        return stuck(state, "no room to cut")
    rerun, hints = [], state.instructions
    for c, agent in CATEGORY_AGENT.items():
        if new_env[c] < spent.get(c, 0):
            rerun.append(agent)
            hints = add_hint(hints, agent, "cheaper")
    if not rerun:
        return stuck(state, "no agent can spend less")
    buffer = max(0, state.request.budget_inr - (sum(new_env.values()) + plan.food))
    new_plan = BudgetPlan(food=plan.food, buffer=buffer, **new_env)
    return {
        "budget_plan": new_plan,
        "round": state.round + 1,
        "rerun": rerun,
        "instructions": hints,
        "_note": f"round {state.round + 1}: {reason}",
    }


@traced("budget_check")
def budget_check(state: TripState, usage) -> dict:
    res = compute_totals(state)
    return {**res, "_note": f"total {money(res['total_cost'])}, over by {money(res['over_budget_by'])}"}
