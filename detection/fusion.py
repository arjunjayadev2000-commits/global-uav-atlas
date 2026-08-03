"""Detection stabilization via multi-frame (and optionally multi-sensor) fusion.

A single YOLO frame is noisy: a bird glinting in the sun, a lens flare or one
unlucky frame of motion blur can register as a momentary "drone" box that
disappears next frame. Rather than alert on every raw detection, this module
fuses detections *across frames* into tracks, and only reports a track once it
has been seen consistently — which is what most of the false-positive
reduction in a fielded system like this actually comes from.

``FusionTracker`` also accepts an optional ``external_confirm`` callback so a
second, independent sensor (an RF/acoustic detector, a radar return, a second
camera) can corroborate or veto a visual track — true sensor fusion, for
deployments that have that hardware. Without one, it degrades gracefully to
pure temporal fusion.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import count

from detection.detector import Detection

BoxF = tuple[float, float, float, float]


def _iou(box_a: BoxF, box_b: BoxF) -> float:
    """Intersection-over-union of two (x, y, w, h) boxes."""
    ax1, ay1, aw, ah = box_a
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx1, by1, bw, bh = box_b
    bx2, by2 = bx1 + bw, by1 + bh

    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    inter_w, inter_h = max(0.0, inter_x2 - inter_x1), max(0.0, inter_y2 - inter_y1)
    intersection = inter_w * inter_h
    if intersection <= 0:
        return 0.0

    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def _as_box_f(box: tuple[int, int, int, int]) -> BoxF:
    x, y, w, h = box
    return (float(x), float(y), float(w), float(h))


@dataclass
class Track:
    track_id: int
    label: str
    box: BoxF
    confidence: float
    hits: int = 1
    misses: int = 0
    confirmed: bool = False
    externally_confirmed: bool | None = None  # None = no external sensor consulted
    velocity: tuple[float, float] = (0.0, 0.0)  # px/frame, estimated from matches

    def predicted_box(self) -> BoxF:
        """Where this track is expected to be on the next frame.

        Matching against the prediction rather than the last observed box is
        what keeps fast, small contacts attached to their track: a smoothed
        box always trails a moving target by roughly one frame of motion, and
        for a distant drone only a few tens of pixels wide that lag alone is
        enough to push IoU under the match threshold and split one real
        object into a stream of one-frame tracks.
        """
        x, y, w, h = self.box
        vx, vy = self.velocity
        return (x + vx, y + vy, w, h)


@dataclass
class FusionTracker:
    """Greedy IoU tracker with exponential smoothing and a hit-count gate.

    Parameters
    ----------
    iou_threshold:
        Minimum overlap between a track's last box and a new detection to
        count as the same object.
    min_hits:
        Consecutive matched frames required before a track is reported as
        "confirmed" (i.e. worth alerting on). Raising this trades alert
        latency for fewer single-frame false positives.
    max_misses:
        Frames a track may go unmatched before it is dropped.
    smoothing:
        Exponential-smoothing factor (0-1) applied to box position and
        confidence on each match; higher values track new detections more
        closely, lower values are steadier under jitter.
    external_confirm:
        Optional callback consulted once a track first reaches ``min_hits``,
        given the :class:`Track`. Return ``True``/``False`` to corroborate or
        veto with a second sensor; return ``None`` to abstain (falls back to
        visual-only confirmation). Left unset, confirmation is visual-only.
    """

    iou_threshold: float = 0.3
    min_hits: int = 3
    max_misses: int = 5
    smoothing: float = 0.5
    velocity_smoothing: float = 0.5
    external_confirm: Callable[[Track], bool | None] | None = None

    _tracks: list[Track] = field(default_factory=list)
    _id_counter: count = field(default_factory=count)

    def update(self, detections: list[Detection]) -> list[Track]:
        """Advance the tracker by one frame and return currently confirmed tracks."""
        unmatched_detections = list(range(len(detections)))

        for track in self._tracks:
            predicted = track.predicted_box()
            best_index, best_iou = None, 0.0
            for i in unmatched_detections:
                det = detections[i]
                if det.label != track.label:
                    continue
                overlap = _iou(predicted, _as_box_f(det.box))
                if overlap > best_iou:
                    best_index, best_iou = i, overlap

            if best_index is not None and best_iou >= self.iou_threshold:
                self._apply_match(track, detections[best_index])
                unmatched_detections.remove(best_index)
            else:
                track.misses += 1
                track.hits = 0
                # Coast along the last known velocity so a briefly occluded
                # contact is re-acquired at the right place rather than
                # dropped and renumbered.
                track.box = predicted

        for i in unmatched_detections:
            det = detections[i]
            self._tracks.append(
                Track(
                    track_id=next(self._id_counter),
                    label=det.label,
                    box=_as_box_f(det.box),
                    confidence=det.confidence,
                )
            )

        self._tracks = [t for t in self._tracks if t.misses <= self.max_misses]

        for track in self._tracks:
            if not track.confirmed and track.hits >= self.min_hits:
                track.confirmed = self._confirm(track)

        return [t for t in self._tracks if t.confirmed]

    def _apply_match(self, track: Track, det: Detection) -> None:
        alpha = self.smoothing
        tx, ty, tw, th = track.box
        dx, dy, dw, dh = det.box
        new_box = (
            tx + alpha * (dx - tx),
            ty + alpha * (dy - ty),
            tw + alpha * (dw - tw),
            th + alpha * (dh - th),
        )

        # Velocity is the smoothed frame-to-frame displacement of the track's
        # own (smoothed) position, so it stays stable under detector jitter.
        beta = self.velocity_smoothing
        vx, vy = track.velocity
        track.velocity = (
            vx + beta * ((new_box[0] - tx) - vx),
            vy + beta * ((new_box[1] - ty) - vy),
        )

        track.box = new_box
        track.confidence = track.confidence + alpha * (det.confidence - track.confidence)
        track.hits += 1
        track.misses = 0

    def _confirm(self, track: Track) -> bool:
        if self.external_confirm is None:
            return True
        verdict = self.external_confirm(track)
        track.externally_confirmed = verdict
        # Abstaining (None) falls back to visual-only confirmation rather than
        # blocking an alert on a sensor that has nothing to say.
        return verdict is not False
