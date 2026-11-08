# agent helpers
import time
from datetime import datetime
from functools import wraps

from app.llm import Usage
from app.state import TraceEvent, TripState


def traced(name: str):
    def wrap(fn):
        @wraps(fn)
        def inner(state: TripState) -> dict:
            usage = Usage()
            started = datetime.now()
            t0 = time.perf_counter()
            updates = fn(state, usage) or {}
            ms = round((time.perf_counter() - t0) * 1000)
            note = updates.pop("_note", "")
            updates["trace"] = [
                TraceEvent(
                    agent=name,
                    started_at=started,
                    duration_ms=ms,
                    tokens=usage.tokens,
                    cost_usd=round(usage.cost_usd, 6),
                    note=note,
                )
            ]
            return updates

        return inner

    return wrap


def money(n: int) -> str:
    return f"Rs {n:,}"


def user_note(state: TripState) -> str:
    out = f"\nTraveller's note: {state.request.note}" if state.request.note else ""
    if state.learned.memories:
        out += "\nThis traveller told us on earlier trips: " + "; ".join(state.learned.memories)
    return out
