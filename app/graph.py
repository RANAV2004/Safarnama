# agent graph
import os

from langgraph.graph import END, START, StateGraph

from app.agents.coordinator import MAX_ROUNDS, budget_check, coordinator_agent
from app.agents.critic import MAX_CRITIC_ROUNDS, critic_agent
from app.agents.places import places_agent
from app.agents.stay import stay_agent
from app.agents.transport import transport_agent
from app.agents.writer import writer_agent
from app.providers.fixture import load
from app.state import Learned, TripRequest, TripState
from app.tools.budget import BudgetTooLowError, split_budget

WORKERS = ["transport", "stay", "places"]


class TripNotSupportedError(ValueError):
    pass


PLAN_ERRORS = (BudgetTooLowError, TripNotSupportedError)


def check_supported(req: TripRequest):
    if req.destination not in load("places"):
        raise TripNotSupportedError(f"Safarnama has no travel data for {req.destination} yet")
    routes = load("transport")
    if os.getenv("PROVIDER_MODE", "fixture") != "live" and not (
        f"{req.origin}|{req.destination}" in routes or f"{req.destination}|{req.origin}" in routes
    ):
        raise TripNotSupportedError(f"Safarnama has no transport data from {req.origin} to {req.destination} yet")


def after_coordinator(state: TripState):
    return state.rerun or "writer"


def after_budget(state: TripState):
    if state.over_budget_by > 0 and state.round < MAX_ROUNDS:
        return "coordinator"
    return "writer"


def after_critic(state: TripState):
    if not state.critic_issues or state.critic_round >= MAX_CRITIC_ROUNDS:
        return END
    owners = sorted({i.responsible_agent for i in state.critic_issues})
    workers = [a for a in owners if a in WORKERS]
    return workers or ["writer"]


def build_graph():
    g = StateGraph(TripState)
    g.add_node("coordinator", coordinator_agent)
    g.add_node("transport", transport_agent)
    g.add_node("stay", stay_agent)
    g.add_node("places", places_agent)
    g.add_node("budget_check", budget_check)
    g.add_node("writer", writer_agent)
    g.add_node("critic", critic_agent)
    g.add_edge(START, "coordinator")
    g.add_conditional_edges("coordinator", after_coordinator, WORKERS + ["writer"])
    for w in WORKERS:
        g.add_edge(w, "budget_check")
    g.add_conditional_edges("budget_check", after_budget, ["coordinator", "writer"])
    g.add_edge("writer", "critic")
    g.add_conditional_edges("critic", after_critic, WORKERS + ["writer", END])
    return g.compile()


GRAPH = build_graph()
CONFIG = {"recursion_limit": 60}


def plan_trip(req: TripRequest, learned: Learned | None = None) -> TripState:
    check_supported(req)
    split_budget(req)
    out = GRAPH.invoke(TripState(request=req, learned=learned or Learned()), CONFIG)
    return TripState.model_validate(out)


def stream_trip(req: TripRequest, learned: Learned | None = None):
    check_supported(req)
    split_budget(req)
    yield from GRAPH.stream(
        TripState(request=req, learned=learned or Learned()), CONFIG, stream_mode=["updates", "values"]
    )
