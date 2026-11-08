# budget
from app.state import BudgetPlan, TripRequest, TripState

FOOD_PER_PERSON_DAY = 500
SPLIT = {"transport": 35, "stay": 35, "food": 15, "activities": 10}


class BudgetTooLowError(ValueError):
    pass


def rooms_needed(travellers: int) -> int:
    return (travellers + 1) // 2


def food_floor(req: TripRequest) -> int:
    return FOOD_PER_PERSON_DAY * req.travellers * req.days


def split_budget(req: TripRequest) -> BudgetPlan:
    total = req.budget_inr
    floor = food_floor(req)
    if total < floor:
        raise BudgetTooLowError(f"budget Rs {total} is below the minimum Rs {floor} needed just for food")
    transport = total * SPLIT["transport"] // 100
    stay = total * SPLIT["stay"] // 100
    food = total * SPLIT["food"] // 100
    activities = total * SPLIT["activities"] // 100
    if req.nights == 0:
        activities += stay
        stay = 0
    if food < floor:
        short = floor - food
        food = floor
        take = min(short, activities)
        activities -= take
    buffer = total - (transport + stay + food + activities)
    if buffer < 0:
        deficit = -buffer
        cut_t = deficit if stay == 0 else deficit // 2
        transport -= cut_t
        stay -= deficit - cut_t
        buffer = 0
    return BudgetPlan(transport=transport, stay=stay, food=food, activities=activities, buffer=buffer)


def stay_cost(state: TripState) -> int:
    s = state.selected_stay
    if not s:
        return 0
    req = state.request
    return s.price_per_night_inr * req.nights * rooms_needed(req.travellers)


def places_cost(state: TripState) -> int:
    return sum(p.entry_fee_inr for p in state.selected_places) * state.request.travellers


def transport_cost(state: TripState) -> int:
    out = state.selected_outbound.price_inr if state.selected_outbound else 0
    back = state.selected_return.price_inr if state.selected_return else 0
    return out + back


def compute_totals(state: TripState) -> dict:
    food = state.budget_plan.food if state.budget_plan else food_floor(state.request)
    breakdown = {
        "transport": transport_cost(state),
        "stay": stay_cost(state),
        "activities": places_cost(state),
        "food": food,
    }
    total = sum(breakdown.values())
    over = max(0, total - state.request.budget_inr)
    return {"breakdown": breakdown, "total_cost": total, "over_budget_by": over}
