"""Tiny in-memory rate limiter. The backend runs as one process, so memory is enough."""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


def client_ip(request: Request) -> str:
    """Find the address a request came from.

    Args:
        request: The incoming request.

    Returns:
        The IP address from the `X-Real-IP` header, else the address of the connection, else "unknown".
    """
    # nginx overwrites X-Real-IP with the address it sees, and the backend is only reachable through nginx.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


class Limiter:
    """At most `limit` hits per `window` seconds for each key.

    The window slides: a hit stops counting `window` seconds after it happened. Everything is forgotten when the
    backend restarts.

    Attributes:
        limit: How many hits a key may have inside one window.
        window: Length of the window in seconds.
        hits: The times of each key's recent hits, oldest first.
    """

    def __init__(self, limit: int, window: int):
        """Create a limiter.

        Args:
            limit: How many hits a key may have inside one window.
            window: Length of the window in seconds.
        """
        self.limit, self.window = limit, window
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str):
        """Count one hit for `key`.

        Args:
            key: What is being limited, e.g. an IP address, an email or a user id.

        Raises:
            HTTPException: 429 when the key is already at its limit. That attempt is not counted.
        """
        now = time.monotonic()  # it never jumps when the system time is changed
        if len(self.hits) > 10_000:  # forget keys with no recent hits
            for k in [k for k, q in self.hits.items() if not q or now - q[-1] > self.window]:
                del self.hits[k]
        q = self.hits[key]
        while q and now - q[0] > self.window:  # drop the hits that have left the window
            q.popleft()
        if len(q) >= self.limit:
            # The oldest hit is the next one to leave the window: that's when another attempt fits.
            minutes = int(self.window - (now - q[0])) // 60 + 1
            raise HTTPException(429, f"Too many attempts. Try again in {minutes} min.")
        q.append(now)
