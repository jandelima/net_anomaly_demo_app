from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class InMemoryRateLimiter:
    def __init__(self, rpm: int = 60) -> None:
        self.rpm = max(1, rpm)
        self._timestamps: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._window_seconds = 60.0

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            bucket = self._timestamps[key]
            while bucket and now - bucket[0] > self._window_seconds:
                bucket.popleft()
            if len(bucket) >= self.rpm:
                return False
            bucket.append(now)
            return True

