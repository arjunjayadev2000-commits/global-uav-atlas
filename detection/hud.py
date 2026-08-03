"""Military-style heads-up display overlay drawn onto detection frames.

This replaces the plain rectangles from ``detector.draw_detections`` with a
tactical HUD: corner-bracket target reticles, a boresight crosshair, a
reference grid, a status strip and threat-graded colouring. It is pure
OpenCV drawing on a BGR frame — no extra dependencies, and it works
identically whether the frame is going to a desktop window or to the web
console's MJPEG stream.

Colours are BGR (OpenCV's byte order), not RGB.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import cv2
import numpy as np

# Phosphor-CRT inspired palette. BGR.
GREEN = (65, 255, 65)
DIM_GREEN = (40, 120, 40)
AMBER = (0, 176, 255)
RED = (60, 60, 255)
WHITE = (235, 235, 235)
GRID = (30, 60, 30)

FONT = cv2.FONT_HERSHEY_SIMPLEX
MONO = cv2.FONT_HERSHEY_PLAIN


@dataclass
class HudContact:
    """A single contact to paint on the HUD.

    Kept deliberately separate from ``detector.Detection`` and
    ``fusion.Track`` so the HUD can render either one, or a simulated
    contact, without importing the whole detection stack.
    """

    track_id: int
    label: str
    confidence: float
    box: tuple[int, int, int, int]  # x, y, w, h
    threat: bool = False


def _bracket(frame: np.ndarray, box, color, thickness: int = 2, arm_ratio: float = 0.25) -> None:
    """Draw four corner brackets instead of a closed rectangle.

    Corner brackets are the standard targeting-reticle idiom: they mark the
    extent of the contact without boxing in (and obscuring) the object.
    """
    x, y, w, h = (int(v) for v in box)
    arm = max(6, int(min(w, h) * arm_ratio))

    corners = (
        ((x, y), (1, 1)),                    # top-left
        ((x + w, y), (-1, 1)),               # top-right
        ((x, y + h), (1, -1)),               # bottom-left
        ((x + w, y + h), (-1, -1)),          # bottom-right
    )
    for (cx, cy), (dx, dy) in corners:
        cv2.line(frame, (cx, cy), (cx + dx * arm, cy), color, thickness, cv2.LINE_AA)
        cv2.line(frame, (cx, cy), (cx, cy + dy * arm), color, thickness, cv2.LINE_AA)


def _darken_roi(frame: np.ndarray, x0: int, y0: int, x1: int, y1: int, alpha: float) -> None:
    """Blend a black plate into just this rectangle.

    Blending the sub-array rather than copying the whole frame keeps HUD cost
    proportional to the label area, not the frame area — this runs once per
    label per frame, so a full-frame copy here would dominate the draw budget
    as soon as several contacts are on screen.
    """
    h, w = frame.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return
    roi = frame[y0:y1, x0:x1]
    roi[:] = (roi * (1.0 - alpha)).astype(roi.dtype)


def _label_plate(frame: np.ndarray, text: str, origin, color, scale: float = 0.42) -> None:
    """Draw text on a darkened plate so it stays legible over bright sky."""
    x, y = origin
    (tw, th), baseline = cv2.getTextSize(text, FONT, scale, 1)
    pad = 3
    x = max(0, min(x, frame.shape[1] - tw - 2 * pad))
    y = max(th + pad, y)

    x0, y0 = x - pad, y - th - pad
    x1, y1 = x + tw + pad, y + baseline + pad - 1
    _darken_roi(frame, x0, y0, x1, y1, alpha=0.55)
    cv2.rectangle(frame, (x0, y0), (x1, y1), color, 1, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), FONT, scale, color, 1, cv2.LINE_AA)


def draw_grid(frame: np.ndarray, spacing: int = 80) -> None:
    """Faint reference grid, drawn under everything else."""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    for x in range(spacing, w, spacing):
        cv2.line(overlay, (x, 0), (x, h), GRID, 1)
    for y in range(spacing, h, spacing):
        cv2.line(overlay, (0, y), (w, y), GRID, 1)
    cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)


def draw_frame_border(frame: np.ndarray) -> None:
    """Outer bracket frame — the 'inside a targeting system' cue."""
    h, w = frame.shape[:2]
    m, arm = 10, 40
    for (cx, cy), (dx, dy) in (
        ((m, m), (1, 1)),
        ((w - m, m), (-1, 1)),
        ((m, h - m), (1, -1)),
        ((w - m, h - m), (-1, -1)),
    ):
        cv2.line(frame, (cx, cy), (cx + dx * arm, cy), DIM_GREEN, 1, cv2.LINE_AA)
        cv2.line(frame, (cx, cy), (cx, cy + dy * arm), DIM_GREEN, 1, cv2.LINE_AA)


def draw_boresight(frame: np.ndarray) -> None:
    """Centre crosshair with tick marks."""
    h, w = frame.shape[:2]
    cx, cy = w // 2, h // 2
    gap, arm = 10, 22
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        cv2.line(
            frame,
            (cx + dx * gap, cy + dy * gap),
            (cx + dx * (gap + arm), cy + dy * (gap + arm)),
            DIM_GREEN,
            1,
            cv2.LINE_AA,
        )
    cv2.circle(frame, (cx, cy), 2, DIM_GREEN, -1, cv2.LINE_AA)


def draw_scanline(frame: np.ndarray, phase: float) -> None:
    """A slow sweeping scan bar. Cosmetic, but it makes a static feed read as 'live'."""
    h, w = frame.shape[:2]
    y = int((phase % 1.0) * h)
    overlay = frame.copy()
    cv2.line(overlay, (0, y), (w, y), GREEN, 2)
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)


def bearing_for(box, frame_width: int, fov_degrees: float = 62.0) -> float:
    """Approximate horizontal bearing of a contact, in degrees off boresight.

    Uses a pinhole assumption and the camera's horizontal field of view; 62°
    is a typical webcam FOV. Negative is left of centre, positive is right.
    This is an estimate for operator situational awareness, not a survey-grade
    measurement — a single camera cannot resolve true bearing without
    calibration.
    """
    x, _, w, _ = box
    centre_x = x + w / 2
    offset = (centre_x - frame_width / 2) / (frame_width / 2)  # -1 .. 1
    return offset * (fov_degrees / 2)


def draw_contacts(frame: np.ndarray, contacts: list[HudContact], pulse: float = 0.0) -> None:
    """Paint every contact with a reticle, ID, class and confidence."""
    frame_w = frame.shape[1]
    for contact in contacts:
        color = RED if contact.threat else GREEN
        thickness = 2
        if contact.threat:
            # Pulse the bracket weight so hostile contacts draw the eye.
            thickness = 2 + int(1.5 * (1 + math.sin(pulse * 2 * math.pi)))

        _bracket(frame, contact.box, color, thickness)

        x, y, w, h = (int(v) for v in contact.box)
        bearing = bearing_for(contact.box, frame_w)
        tag = "HOSTILE" if contact.threat else "TRACK"
        _label_plate(
            frame,
            f"{tag} {contact.track_id:03d}  {contact.label.upper()}  {contact.confidence * 100:.0f}%",
            (x, y - 8),
            color,
        )
        _label_plate(frame, f"BRG {bearing:+05.1f}", (x, y + h + 16), color, scale=0.38)

        # Leader line from the contact down toward the status strip.
        cv2.line(frame, (x + w // 2, y + h), (x + w // 2, y + h + 6), color, 1, cv2.LINE_AA)


def draw_status_strip(
    frame: np.ndarray,
    *,
    fps: float,
    contact_count: int,
    threat_count: int,
    mode: str,
    source_label: str,
) -> None:
    """Top and bottom status strips: the always-on telemetry read."""
    h, w = frame.shape[:2]
    strip_h = 26

    _darken_roi(frame, 0, 0, w, strip_h, alpha=0.6)
    _darken_roi(frame, 0, h - strip_h, w, h, alpha=0.6)
    cv2.line(frame, (0, strip_h), (w, strip_h), DIM_GREEN, 1)
    cv2.line(frame, (0, h - strip_h), (w, h - strip_h), DIM_GREEN, 1)

    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cv2.putText(frame, f"UAV-DET // {mode}", (12, 18), FONT, 0.45, GREEN, 1, cv2.LINE_AA)
    cv2.putText(frame, stamp, (w - 200, 18), FONT, 0.45, GREEN, 1, cv2.LINE_AA)

    threat_color = RED if threat_count else GREEN
    cv2.putText(
        frame,
        f"CONTACTS {contact_count:02d}   HOSTILE {threat_count:02d}",
        (12, h - 9),
        FONT,
        0.45,
        threat_color,
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame, f"{source_label}   {fps:5.1f} FPS", (w - 250, h - 9), FONT, 0.45, GREEN, 1, cv2.LINE_AA
    )


def render(
    frame: np.ndarray,
    contacts: list[HudContact],
    *,
    fps: float = 0.0,
    mode: str = "LIVE",
    source_label: str = "CAM0",
    show_grid: bool = True,
    show_scanline: bool = True,
    phase: float | None = None,
) -> np.ndarray:
    """Draw the complete HUD onto ``frame`` in place and return it."""
    phase = time.time() * 0.25 if phase is None else phase

    if show_grid:
        draw_grid(frame)
    draw_boresight(frame)
    if show_scanline:
        draw_scanline(frame, phase)
    draw_contacts(frame, contacts, pulse=phase)
    draw_frame_border(frame)
    draw_status_strip(
        frame,
        fps=fps,
        contact_count=len(contacts),
        threat_count=sum(1 for c in contacts if c.threat),
        mode=mode,
        source_label=source_label,
    )
    return frame
