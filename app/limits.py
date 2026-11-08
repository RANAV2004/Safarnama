# rate limits kept in memory, use Redis instead when running more than one server
import math
import time
from collections import defaultdict, deque


class Limiter:
    def __init__(self):
        self.hits: dict[tuple, deque] = defaultdict(deque)

    def recent(self, key: tuple, window: int, now: float | None = None) -> deque:
        now = now or time.time()
        q = self.hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        return q

    def count(self, key: tuple, window: int, now: float | None = None) -> int:
        return len(self.recent(key, window, now))

    def wait(self, key: tuple, limit: int, window: int, now: float | None = None) -> int:
        q = self.recent(key, window, now)
        if len(q) < limit:
            return 0
        return max(1, math.ceil(q[0] + window - (now or time.time())))

    def add(self, key: tuple, now: float | None = None):
        self.hits[key].append(now or time.time())

    def clear(self, key: tuple | None = None):
        if key is None:
            self.hits.clear()
        else:
            self.hits.pop(key, None)


LIMITS = Limiter()
