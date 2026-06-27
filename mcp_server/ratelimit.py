"""Minimal in-process token-bucket rate limiter for the MCP server.

Defense in depth: the server enforces its own per-tool limits even though the
gateway also rate-limits. In production this is backed by Redis (Phase 8).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    rate_per_sec: float
    burst: int
    _tokens: float = field(default=0.0, init=False)
    _last: float = field(default_factory=time.monotonic, init=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.burst)

    def allow(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        self._tokens = min(self.burst, self._tokens + (now - self._last) * self.rate_per_sec)
        self._last = now
        if self._tokens >= cost:
            self._tokens -= cost
            return True
        return False
