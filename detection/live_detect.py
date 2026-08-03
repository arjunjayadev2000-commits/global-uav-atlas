#!/usr/bin/env python3
"""Real-time drone detection from a live camera feed.

Non-coder quick start: see ``detection/README.md``. In short — put
``yolov4.cfg``, ``yolov4.weights`` and ``obj.names`` in ``detection/models/``,
then run::

    python detection/live_detect.py

A window opens showing the camera feed with boxes and confidence scores drawn
around anything detected; press ``q`` or ``Esc`` to quit.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

# Allow `python detection/live_detect.py` to work from a clean checkout
# without `pip install -e .` or PYTHONPATH fiddling.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from detection.config import DetectorConfig
from detection.detector import Detection, DroneDetector, draw_detections
from detection.fusion import FusionTracker, Track


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="0",
        help="camera index (e.g. 0) or a video file / RTSP URL (default: 0, the first webcam)",
    )
    parser.add_argument(
        "--input-size", type=int, default=416, choices=(320, 416, 512, 608),
        help="Darknet input resolution; 608 improves distant-drone recall at lower FPS (default: 416)",
    )
    parser.add_argument("--confidence", type=float, default=0.5, help="minimum detection confidence")
    parser.add_argument("--backend", default="auto", choices=("auto", "cuda", "cpu"))
    parser.add_argument(
        "--no-fusion", action="store_true",
        help="show raw per-frame detections instead of the stabilized multi-frame tracks",
    )
    parser.add_argument("--display-fps", action="store_true", default=True)
    return parser.parse_args(argv)


def _open_capture(source: str) -> cv2.VideoCapture:
    # A plain integer string means "camera index"; anything else (file path,
    # rtsp:// URL) is passed straight through to OpenCV.
    resolved = int(source) if source.isdigit() else source
    capture = cv2.VideoCapture(resolved)
    if not capture.isOpened():
        raise RuntimeError(
            f"Could not open video source {source!r}. If this is a webcam index, "
            "check no other application is using the camera and that the index is correct "
            "(try --source 1, --source 2, ...)."
        )
    return capture


def _tracks_to_drawable(tracks: list[Track]) -> list[Detection]:
    drawable = []
    for track in tracks:
        x, y, w, h = track.box
        drawable.append(
            Detection(
                class_id=-1,
                label=track.label,
                confidence=track.confidence,
                box=(int(x), int(y), int(w), int(h)),
                is_target=True,
            )
        )
    return drawable


def run(args: argparse.Namespace) -> None:
    config = DetectorConfig(
        input_size=args.input_size, confidence_threshold=args.confidence, backend=args.backend
    )
    detector = DroneDetector(config)
    tracker = FusionTracker()
    capture = _open_capture(args.source)

    print("Drone detector running. Press 'q' or Esc in the video window to quit.")
    prev_time = time.time()
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                print("Camera feed ended or frame could not be read.")
                break

            detections = detector.detect(frame)

            if args.no_fusion:
                to_draw = detections
            else:
                confirmed_tracks = tracker.update(detections)
                to_draw = _tracks_to_drawable(confirmed_tracks)

            draw_detections(frame, to_draw)

            if args.display_fps:
                now = time.time()
                fps = 1.0 / max(now - prev_time, 1e-6)
                prev_time = now
                cv2.putText(
                    frame, f"FPS: {fps:.1f}", (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2, cv2.LINE_AA,
                )

            cv2.imshow("Drone Detection", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):  # 'q' or Esc
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()


def main(argv: list[str] | None = None) -> None:
    run(parse_args(argv))


if __name__ == "__main__":
    main()
