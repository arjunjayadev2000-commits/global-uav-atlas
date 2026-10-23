"""Detect that the *evaluating* node itself stalled.

After a scheduling stall longer than ``threshold`` the node's input queues may
still hold messages that arrived during the stall, so every input looks stale
at the first tick. ``should_defer`` returns True for that first tick only, never
for two consecutive ticks: a node that stays starved still fails safe.
"""

from __future__ import annotations


class StallGuard:
    def __init__(self, threshold: float) -> None:
        self.threshold = threshold
        self._last: float | None = None
        self._deferred_last = False
        self.stall_count = 0

    def should_defer(self, now: float) -> bool:
        stalled = self._last is not None and now - self._last > self.threshold
        self._last = now
        if stalled and not self._deferred_last:
            self._deferred_last = True
            self.stall_count += 1
            return True
        self._deferred_last = False
        return False
