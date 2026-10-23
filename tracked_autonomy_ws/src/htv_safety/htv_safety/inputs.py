"""Freshness-tracked latest-value cache for supervisor inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Tracked:
    timeout: float
    value: Any = None
    received_at: float | None = None

    def set(self, value: Any, now: float) -> None:
        self.value = value
        self.received_at = now

    def fresh(self, now: float) -> bool:
        if self.received_at is None:
            return False
        age = now - self.received_at
        # Negative age means the clock jumped backwards (e.g. simulation reset):
        # the sample can no longer be trusted.
        return 0.0 <= age <= self.timeout

    def get(self, now: float) -> Any:
        """Value if fresh, else None. Stale data is never trusted."""
        return self.value if self.fresh(now) else None
