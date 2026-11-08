# eval trips
import json
import random
from datetime import date, timedelta
from pathlib import Path

from app.providers.fixture import load, supported_routes
from app.tools.budget import FOOD_PER_PERSON_DAY, rooms_needed

OUT = Path(__file__).with_name("trips.jsonl")
FACTORS = [0.6, 0.75, 0.9, 1.2, 1.6]
PREFS = [[], ["beach"], ["history"], ["nature"], ["culture", "shopping"]]


def fair_cost(origin, dest, nights, travellers) -> int:
    rows = load("transport").get(f"{origin}|{dest}")
    cheapest = min(r["price_per_person"] for r in rows) * travellers * 2
    hotels = sorted(h["price_per_night_inr"] for h in load("stays")[dest])
    mid = hotels[len(hotels) // 2]
    days = nights + 1
    return (
        cheapest
        + mid * nights * rooms_needed(travellers)
        + FOOD_PER_PERSON_DAY * travellers * days
        + 300 * travellers * days
    )


def main(n: int = 50, seed: int = 7):
    rnd = random.Random(seed)
    routes = supported_routes()
    trips = []
    for i in range(n):
        origin, dest = routes[i % len(routes)]
        nights = 0 if dest == "Mysuru" and rnd.random() < 0.5 else rnd.randint(1, 4)
        travellers = rnd.choice([1, 1, 2, 2, 3, 4])
        start = date(2026, 11, 16) + timedelta(days=rnd.randint(0, 40))
        factor = FACTORS[i % len(FACTORS)]
        budget = int(fair_cost(origin, dest, nights, travellers) * factor) // 100 * 100
        trips.append(
            {
                "id": f"t{i:02d}",
                "origin": origin,
                "destination": dest,
                "start_date": start.isoformat(),
                "end_date": (start + timedelta(days=nights)).isoformat(),
                "budget_inr": budget,
                "travellers": travellers,
                "preferences": rnd.choice(PREFS),
                "factor": factor,
            }
        )
    OUT.write_text("\n".join(json.dumps(t) for t in trips) + "\n")
    print(f"wrote {len(trips)} trips to {OUT}")


if __name__ == "__main__":
    main()
