"""Console state: turns raw tracks into the readout the operator actually sees.

The detector produces boxes; the tracker produces stable tracks. This module
produces *situational state*: which contacts are hostile, what the overall
threat posture is, a timestamped event log, and rolling telemetry. It is the
single source of truth the web console renders.

Deliberately free of Flask and OpenCV imports so it can be unit-tested on its
own.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from detection.fusion import Track
from detection.hud import bearing_for

# Threat postures, lowest to highest. Named so the UI can colour-code them.
THREAT_LEVELS = ("CLEAR", "GUARDED", "ELEVATED", "CRITICAL")


@dataclass
class ContactRecord:
    """A confirmed track, enriched for operator display."""

    track_id: int
    label: str
    confidence: float
    box: tuple[float, float, float, float]
    bearing: float
    hostile: bool
    first_seen: float
    last_seen: float

    @property
    def age_seconds(self) -> float:
        return max(0.0, self.last_seen - self.first_seen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.track_id,
            "label": self.label.upper(),
            "confidence": round(self.confidence, 3),
            "bearing": round(self.bearing, 1),
            "hostile": self.hostile,
            "age": round(self.age_seconds, 1),
            "box": [round(v) for v in self.box],
        }


@dataclass
class ConsoleState:
    """Thread-safe aggregate of everything the console displays.

    The capture thread calls :meth:`ingest` on every frame; the HTTP handlers
    call :meth:`snapshot` from request threads. A single lock guards both —
    the critical sections are microseconds, so contention is not a concern at
    video frame rates.
    """

    frame_width: int = 960
    max_events: int = 60
    hostile_labels: tuple[str, ...] = ("drone",)

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _contacts: dict[int, ContactRecord] = field(default_factory=dict, repr=False)
    _events: deque = field(default_factory=lambda: deque(maxlen=60), repr=False)
    _frame_times: deque = field(default_factory=lambda: deque(maxlen=30), repr=False)
    _started: float = field(default_factory=time.time)
    _frames: int = 0
    _seen_ids: set[int] = field(default_factory=set, repr=False)
    _source_label: str = "SIM"
    _mode: str = "SIMULATION"

    def __post_init__(self) -> None:
        self._events = deque(maxlen=self.max_events)
        self.log("SYSTEM", "Detection console initialised")

    # -- ingestion ---------------------------------------------------------

    def ingest(self, tracks: list[Track]) -> None:
        """Fold this frame's confirmed tracks into the running state."""
        now = time.time()
        with self._lock:
            self._frames += 1
            self._frame_times.append(now)

            live_ids = set()
            for track in tracks:
                hostile = track.label in self.hostile_labels
                live_ids.add(track.track_id)

                existing = self._contacts.get(track.track_id)
                if existing is None:
                    record = ContactRecord(
                        track_id=track.track_id,
                        label=track.label,
                        confidence=track.confidence,
                        box=track.box,
                        bearing=bearing_for(track.box, self.frame_width),
                        hostile=hostile,
                        first_seen=now,
                        last_seen=now,
                    )
                    self._contacts[track.track_id] = record
                    if track.track_id not in self._seen_ids:
                        self._seen_ids.add(track.track_id)
                        self._log_locked(
                            "THREAT" if hostile else "CONTACT",
                            f"{'Hostile UAV' if hostile else track.label.capitalize()} "
                            f"acquired — track {track.track_id:03d}",
                        )
                else:
                    existing.confidence = track.confidence
                    existing.box = track.box
                    existing.bearing = bearing_for(track.box, self.frame_width)
                    existing.last_seen = now

            # Drop contacts whose tracks the fusion layer has retired.
            for lost_id in set(self._contacts) - live_ids:
                lost = self._contacts.pop(lost_id)
                self._log_locked(
                    "LOST", f"Track {lost_id:03d} ({lost.label}) lost after {lost.age_seconds:.0f}s"
                )

    def set_source(self, *, source_label: str, mode: str) -> None:
        with self._lock:
            self._source_label = source_label
            self._mode = mode

    def log(self, kind: str, message: str) -> None:
        with self._lock:
            self._log_locked(kind, message)

    def _log_locked(self, kind: str, message: str) -> None:
        """Append an event. Caller must already hold the lock."""
        self._events.appendleft(
            {"t": time.strftime("%H:%M:%S", time.gmtime()), "kind": kind, "message": message}
        )

    # -- derived readouts --------------------------------------------------

    def _fps_locked(self) -> float:
        if len(self._frame_times) < 2:
            return 0.0
        span = self._frame_times[-1] - self._frame_times[0]
        return (len(self._frame_times) - 1) / span if span > 0 else 0.0

    @staticmethod
    def threat_level_for(hostile_count: int, max_confidence: float) -> str:
        """Map hostile contacts and their confidence onto a posture.

        Two hostiles, or one high-confidence hostile, is enough to go
        CRITICAL — a confident single-drone track is the scenario this system
        exists to catch, so it should not sit at a middling posture.
        """
        if hostile_count == 0:
            return "CLEAR"
        if hostile_count >= 2:
            return "CRITICAL"
        if max_confidence >= 0.80:
            return "CRITICAL"
        if max_confidence >= 0.60:
            return "ELEVATED"
        return "GUARDED"

    def snapshot(self) -> dict[str, Any]:
        """A JSON-serialisable view of current state for the web console."""
        with self._lock:
            contacts = sorted(
                self._contacts.values(), key=lambda c: (not c.hostile, -c.confidence)
            )
            hostiles = [c for c in contacts if c.hostile]
            max_conf = max((c.confidence for c in hostiles), default=0.0)
            level = self.threat_level_for(len(hostiles), max_conf)

            return {
                "threat_level": level,
                "threat_index": THREAT_LEVELS.index(level),
                "contacts": [c.to_dict() for c in contacts],
                "contact_count": len(contacts),
                "hostile_count": len(hostiles),
                "events": list(self._events),
                "telemetry": {
                    "fps": round(self._fps_locked(), 1),
                    "frames": self._frames,
                    "uptime": int(time.time() - self._started),
                    "source": self._source_label,
                    "mode": self._mode,
                    "tracks_total": len(self._seen_ids),
                },
            }
