"""Rate limiter à fenêtres glissantes (clé perso Riot : 20 req/1 s et 100 req/2 min)."""

from __future__ import annotations

import time
from collections import deque


class SlidingWindowRateLimiter:
    def __init__(self, limits: list[tuple[int, float]] | None = None) -> None:
        # (max_requêtes, fenêtre_secondes)
        self.limits = limits or [(20, 1.0), (100, 120.0)]
        self._history: list[deque[float]] = [deque() for _ in self.limits]

    def acquire(self) -> None:
        """Bloque jusqu'à ce qu'une requête soit autorisée par toutes les fenêtres."""
        while True:
            now = time.monotonic()
            wait = 0.0
            for (max_req, window), hist in zip(self.limits, self._history):
                while hist and now - hist[0] >= window:
                    hist.popleft()
                if len(hist) >= max_req:
                    wait = max(wait, window - (now - hist[0]))
            if wait <= 0:
                break
            time.sleep(wait + 0.05)
        stamp = time.monotonic()
        for hist in self._history:
            hist.append(stamp)
