"""Tiny in-memory rate limiter. The backend runs as one process, so memory is enough."""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


def client_ip(request: Request) -> str:
    # nginx overwrites X-Real-IP with the address it sees, and the backend is only reachable through nginx.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


class Limiter:
    """At most `limit` hits per `window` seconds for each key."""

    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str):
        """Count one hit for `key`; raise 429 when it's over the limit."""
        now = time.monotonic()
        if len(self.hits) > 10_000:  # forget keys with no recent hits
            for k in [k for k, q in self.hits.items() if not q or now - q[-1] > self.window]:
                del self.hits[k]
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            minutes = int(self.window - (now - q[0])) // 60 + 1
            raise HTTPException(429, f"Too many attempts. Try again in {minutes} min.")
        q.append(now)
