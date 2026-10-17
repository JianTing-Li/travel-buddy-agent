"""Simple in-memory rate limits, so a shared demo link can't run up the Anthropic bill. Owner: Jian.

Sliding windows per key (an IP address or a session id). Like the sessions, the counts live in memory: run one
worker, and a restart resets them. Real protection still needs a spending limit on the API key itself.
"""
import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    sessions_per_ip_per_hour: int = 20
    chat_per_ip_per_minute: int = 20
    chat_turns_per_session: int = 80


class RateLimiter:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, kind: str, key: str, limit: int, window_seconds: float) -> bool:
        """Count one hit for (kind, key) unless `limit` hits already happened in the last `window_seconds`."""
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault((kind, key), deque())
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            if len(self._hits) > 10_000:  # forget idle keys so memory stays small
                self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > now - 3600}
            return True
