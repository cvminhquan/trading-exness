"""Simple in-process rate limiter for analyst chat."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class ChatRateLimiter:
    def __init__(self, *, max_requests: int, window_seconds: float) -> None:
        self._max = max(1, max_requests)
        self._window = max(1.0, window_seconds)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self._window:
                q.popleft()
            if len(q) >= self._max:
                return False
            q.append(now)
            return True
