"""Heartbeat bookkeeping for the watchdog (ROS-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Severity(IntEnum):
    # Values match htv_interfaces/msg/WatchdogStatus constants.
    NONE = 0
    MINOR = 1
    MAJOR = 2
    CRITICAL = 3


SEVERITY_NAMES = {"minor": Severity.MINOR, "major": Severity.MAJOR, "critical": Severity.CRITICAL}


@dataclass
class HeartbeatReport:
    stale: list[str] = field(default_factory=list)
    worst: Severity = Severity.NONE
    # A critical node that was alive and then went silent or reported unhealthy.
    lost_critical: bool = False
    # True when this evaluation was deferred because the monitor itself stalled.
    deferred: bool = False


class HeartbeatMonitor:
    def __init__(self, severities: dict[str, Severity], timeout: float, startup_grace: float) -> None:
        self.severities = dict(severities)
        self.timeout = timeout
        self.startup_grace = startup_grace
        self._start: float | None = None
        self._last_seen: dict[str, float] = {}
        self._unhealthy: set[str] = set()
        self._last_eval: float | None = None
        self._deferred_last = False
        self._last_report = HeartbeatReport()

    def start(self, now: float) -> None:
        if self._start is None:
            self._start = now

    def beat(self, name: str, healthy: bool, now: float) -> None:
        if name not in self.severities:
            return
        self._last_seen[name] = now
        if healthy:
            self._unhealthy.discard(name)
        else:
            self._unhealthy.add(name)

    def evaluate(self, now: float) -> HeartbeatReport:
        """Evaluate heartbeat freshness.

        If the monitor itself stalled for longer than the timeout, heartbeats that
        arrived meanwhile may still be queued unprocessed. The first evaluation
        after such a stall is deferred (previous report returned) so the queue can
        drain; never two in a row, so a persistently starved monitor still trips.
        """
        self.start(now)
        assert self._start is not None
        stalled = self._last_eval is not None and now - self._last_eval > self.timeout
        self._last_eval = now
        if stalled and not self._deferred_last:
            self._deferred_last = True
            return HeartbeatReport(self._last_report.stale, self._last_report.worst,
                                   self._last_report.lost_critical, deferred=True)
        self._deferred_last = False
        in_grace = now - self._start < self.startup_grace
        report = HeartbeatReport()
        for name, severity in self.severities.items():
            seen = self._last_seen.get(name)
            never_started = seen is None and not in_grace
            # Negative age (clock jumped backwards) is as untrustworthy as a timeout.
            lost = seen is not None and not 0.0 <= now - seen <= self.timeout
            unhealthy = name in self._unhealthy
            if never_started or lost or unhealthy:
                report.stale.append(name)
                report.worst = max(report.worst, severity)
                # The direct E-stop is armed only after start-up: until the supervisor
                # reaches READY no motion can be enabled, and start-up CPU bursts
                # would otherwise cause nuisance latches.
                if severity >= Severity.CRITICAL and (lost or unhealthy) and not in_grace:
                    report.lost_critical = True
        self._last_report = report
        return report
