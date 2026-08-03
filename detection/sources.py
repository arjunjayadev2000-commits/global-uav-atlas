"""Frame sources for the detection console.

The console needs frames and detections from somewhere. Two implementations:

``LiveSource``
    The real thing — an OpenCV capture feeding a :class:`DroneDetector`.
    Requires a camera (or video file) and trained model weights.

``SimulatedSource``
    A synthetic sky with scripted contacts moving across it, producing
    detections directly without a model. This exists so the console can be
    launched, demonstrated and tested on a machine with no camera, no GPU and
    no weights file — which is also how it is verified in CI.

Both satisfy the same tiny protocol (``read()`` -> frame + detections), so the
server never needs to know which one it has.
"""

from __future__ import annotations

import math
import time
from typing import Protocol

import cv2
import numpy as np

from detection.config import DetectorConfig
from detection.detector import Detection, DroneDetector


class FrameSource(Protocol):
    """Anything the console can drive: yields a frame plus its detections."""

    label: str

    def read(self) -> tuple[np.ndarray, list[Detection]] | None:
        """Return the next (frame, detections), or None when the feed ends."""
        ...

    def release(self) -> None:
        ...


class LiveSource:
    """Real camera/video feed run through the YOLO detector."""

    def __init__(self, source: str = "0", config: DetectorConfig | None = None) -> None:
        self.config = config or DetectorConfig()
        self.detector = DroneDetector(self.config)
        resolved: int | str = int(source) if source.isdigit() else source
        self.capture = cv2.VideoCapture(resolved)
        if not self.capture.isOpened():
            raise RuntimeError(
                f"Could not open video source {source!r}. Check the camera is connected "
                "and not in use by another application (try --source 1, --source 2, ...)."
            )
        self.label = f"CAM{source}" if source.isdigit() else "FILE"

    def read(self) -> tuple[np.ndarray, list[Detection]] | None:
        ok, frame = self.capture.read()
        if not ok:
            return None
        return frame, self.detector.detect(frame)

    def release(self) -> None:
        self.capture.release()


class _SimContact:
    """One scripted contact tracing a path across the synthetic frame."""

    def __init__(self, label: str, *, speed: float, y_base: float, amplitude: float,
                 size: int, phase: float, confidence: float) -> None:
        self.label = label
        self.speed = speed
        self.y_base = y_base
        self.amplitude = amplitude
        self.size = size
        self.phase = phase
        self.confidence = confidence

    def at(self, t: float, width: int, height: int) -> tuple[tuple[int, int, int, int], float]:
        # Wrap horizontally; bob vertically on a sine so tracks look airborne.
        progress = (t * self.speed + self.phase) % 1.0
        cx = progress * (width + self.size * 2) - self.size
        cy = self.y_base * height + math.sin(t * 1.7 + self.phase * 6.28) * self.amplitude

        # Contacts shrink slightly near the middle of the pass (further away).
        scale = 0.85 + 0.3 * abs(progress - 0.5) * 2
        w = h = max(14, int(self.size * scale))

        # Confidence wobbles a little, as a real detector's would.
        conf = min(0.99, max(0.35, self.confidence + 0.06 * math.sin(t * 3.1 + self.phase * 4)))
        return (int(cx - w / 2), int(cy - h / 2), w, h), conf


class SimulatedSource:
    """Synthetic feed: gradient sky, drifting cloud banding, scripted contacts.

    Nothing here touches a camera or a model. It produces the same
    ``(frame, detections)`` shape as :class:`LiveSource` so every downstream
    component — tracker, HUD, state engine, web console — runs identically.
    """

    label = "SIM"

    def __init__(self, width: int = 960, height: int = 540, fps: float = 20.0) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.started = time.monotonic()
        self._last_frame_at = 0.0
        self._background = self._build_background()
        self._contacts = [
            _SimContact("drone", speed=0.055, y_base=0.30, amplitude=18, size=54,
                        phase=0.0, confidence=0.91),
            _SimContact("bird", speed=0.11, y_base=0.22, amplitude=30, size=30,
                        phase=0.45, confidence=0.68),
            _SimContact("drone", speed=0.032, y_base=0.46, amplitude=10, size=38,
                        phase=0.7, confidence=0.79),
        ]

    def _build_background(self) -> np.ndarray:
        """A vertical sky gradient with a horizon and a treeline silhouette."""
        h, w = self.height, self.width
        frame = np.zeros((h, w, 3), np.uint8)

        horizon = int(h * 0.72)
        # Sky: brighter near the horizon, deeper blue-grey up top. BGR.
        top = np.array([104, 78, 56], np.float32)
        bottom = np.array([176, 156, 132], np.float32)
        for y in range(horizon):
            frame[y] = top + (bottom - top) * (y / max(1, horizon - 1))

        # Ground: dark, low contrast.
        frame[horizon:] = (34, 40, 30)

        # Treeline: a jagged silhouette so the horizon isn't a ruler-straight line.
        rng = np.random.default_rng(7)
        xs = np.arange(0, w + 20, 20)
        heights = rng.integers(8, 34, size=len(xs))
        pts = [(0, h)]
        for x, height in zip(xs, heights, strict=False):
            pts.append((int(x), horizon - int(height)))
        pts.append((w, h))
        cv2.fillPoly(frame, [np.array(pts, np.int32)], (24, 30, 22))

        return frame

    def _compose(self, t: float) -> np.ndarray:
        frame = self._background.copy()
        # Slow horizontal cloud banding, so the sky isn't perfectly static.
        shift = int((t * 12) % self.width)
        band = np.zeros((self.height, self.width), np.float32)
        for i in range(3):
            cy = int(self.height * (0.12 + 0.09 * i))
            cv2.ellipse(
                band, ((shift + i * 300) % (self.width + 400) - 200, cy),
                (170, 22), 0, 0, 360, 1.0, -1,
            )
        blurred = cv2.GaussianBlur(band, (0, 0), 28)[..., None]
        return np.clip(frame.astype(np.float32) + blurred * 26, 0, 255).astype(np.uint8)

    def read(self) -> tuple[np.ndarray, list[Detection]] | None:
        # Pace the simulator to its nominal frame rate so FPS readouts and
        # the tracker's hit counting behave like a real feed.
        now = time.monotonic()
        min_interval = 1.0 / self.fps
        wait = self._last_frame_at + min_interval - now
        if wait > 0:
            time.sleep(wait)
        self._last_frame_at = time.monotonic()

        t = time.monotonic() - self.started
        frame = self._compose(t)

        detections: list[Detection] = []
        for contact in self._contacts:
            box, conf = contact.at(t, self.width, self.height)
            x, _, w, _ = box
            if x + w < 0 or x > self.width:
                continue

            # Paint a plausible-looking object so the video and the boxes agree.
            self._paint_contact(frame, contact.label, box)
            detections.append(
                Detection(
                    class_id=0 if contact.label == "drone" else 1,
                    label=contact.label,
                    confidence=conf,
                    box=box,
                    is_target=contact.label == "drone",
                )
            )
        return frame, detections

    @staticmethod
    def _paint_contact(frame: np.ndarray, label: str, box: tuple[int, int, int, int]) -> None:
        x, y, w, h = box
        cx, cy = x + w // 2, y + h // 2
        color = (38, 38, 42) if label == "drone" else (30, 30, 34)
        if label == "drone":
            # Quadcopter: body plus four rotor discs.
            cv2.rectangle(frame, (cx - w // 6, cy - h // 8), (cx + w // 6, cy + h // 8), color, -1)
            r = max(3, w // 6)
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                ox, oy = cx + dx * w // 3, cy + dy * h // 4
                cv2.line(frame, (cx, cy), (ox, oy), color, 2)
                cv2.ellipse(frame, (ox, oy), (r, max(1, r // 3)), 0, 0, 360, color, 1)
        else:
            # Bird: a simple gull-wing stroke.
            cv2.ellipse(frame, (cx - w // 4, cy), (w // 4, h // 3), 0, 200, 340, color, 2)
            cv2.ellipse(frame, (cx + w // 4, cy), (w // 4, h // 3), 0, 200, 340, color, 2)

    def release(self) -> None:  # nothing to release
        return None


def build_source(source: str, *, simulate: bool, config: DetectorConfig | None = None) -> FrameSource:
    """Pick a source: simulator when requested, otherwise the real camera."""
    if simulate:
        return SimulatedSource()
    return LiveSource(source, config)
