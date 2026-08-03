"""Flask server hosting the tactical detection console.

Architecture: one background capture thread owns the frame source, the
detector and the tracker, and writes two things — the latest JPEG-encoded
frame, and the latest :class:`ConsoleState`. HTTP handlers only read. That
keeps inference off the request path entirely, so a slow browser (or three
browsers) can never stall the detector.

Endpoints
---------
``/``              the console page
``/stream.mjpg``   multipart JPEG stream of the HUD-annotated feed
``/api/state``     JSON snapshot: contacts, threat level, events, telemetry
``/healthz``       liveness probe
"""

from __future__ import annotations

import threading
import time
from typing import Any

import cv2
from flask import Flask, Response, jsonify, render_template

from detection.config import DetectorConfig
from detection.console_state import ConsoleState
from detection.fusion import FusionTracker
from detection.hud import HudContact, render
from detection.sources import FrameSource, build_source


class DetectionEngine:
    """Owns the capture/detect/track/annotate loop on a background thread."""

    def __init__(
        self,
        source: FrameSource,
        *,
        state: ConsoleState | None = None,
        tracker: FusionTracker | None = None,
        jpeg_quality: int = 80,
        mode: str = "LIVE",
    ) -> None:
        self.source = source
        self.tracker = tracker or FusionTracker()
        self.state = state or ConsoleState()
        self.jpeg_quality = jpeg_quality
        self.mode = mode

        self._frame_lock = threading.Lock()
        self._latest_jpeg: bytes | None = None
        self._frame_event = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fps = 0.0

        self.state.set_source(source_label=source.label, mode=mode)

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="detection-engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self.source.release()

    # -- capture loop ------------------------------------------------------

    def _run(self) -> None:
        last = time.monotonic()
        self.state.log("SYSTEM", f"Feed opened on {self.source.label}")
        while not self._stop.is_set():
            try:
                result = self.source.read()
            except Exception as exc:  # a camera unplugged mid-run should not kill the server
                self.state.log("FAULT", f"Frame source error: {exc}")
                break

            if result is None:
                self.state.log("SYSTEM", "Feed ended")
                break

            frame, detections = result
            tracks = self.tracker.update(detections)
            self.state.ingest(tracks)

            now = time.monotonic()
            dt = now - last
            last = now
            # Exponentially smoothed FPS; a single slow frame shouldn't make
            # the readout jump.
            instant = 1.0 / dt if dt > 0 else 0.0
            self._fps = instant if self._fps == 0 else self._fps * 0.85 + instant * 0.15

            contacts = [
                HudContact(
                    track_id=t.track_id,
                    label=t.label,
                    confidence=t.confidence,
                    box=tuple(int(v) for v in t.box),  # type: ignore[arg-type]
                    threat=t.label in self.state.hostile_labels,
                )
                for t in tracks
            ]
            render(
                frame,
                contacts,
                fps=self._fps,
                mode=self.mode,
                source_label=self.source.label,
            )

            ok, buffer = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            )
            if ok:
                with self._frame_lock:
                    self._latest_jpeg = buffer.tobytes()
                # Wake every client waiting for a new frame, then re-arm.
                self._frame_event.set()
                self._frame_event.clear()

    # -- readers -----------------------------------------------------------

    def latest_jpeg(self) -> bytes | None:
        with self._frame_lock:
            return self._latest_jpeg

    def wait_for_frame(self, timeout: float = 1.0) -> None:
        self._frame_event.wait(timeout)

    def mjpeg_frames(self):
        """Yield multipart JPEG chunks for as long as the client stays connected."""
        boundary = b"--frame\r\n"
        while not self._stop.is_set():
            self.wait_for_frame(timeout=1.0)
            jpeg = self.latest_jpeg()
            if jpeg is None:
                continue
            yield boundary + b"Content-Type: image/jpeg\r\nContent-Length: " + str(
                len(jpeg)
            ).encode() + b"\r\n\r\n" + jpeg + b"\r\n"


def create_app(engine: DetectionEngine) -> Flask:
    app = Flask(__name__)
    app.config["ENGINE"] = engine

    @app.route("/")
    def index() -> str:
        return render_template("console.html")

    @app.route("/stream.mjpg")
    def stream() -> Response:
        return Response(
            engine.mjpeg_frames(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
        )

    @app.route("/api/state")
    def api_state() -> Any:
        response = jsonify(engine.state.snapshot())
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/healthz")
    def healthz() -> Any:
        return jsonify({"ok": True, "frame_ready": engine.latest_jpeg() is not None})

    return app


def build(
    *,
    source: str = "0",
    simulate: bool = False,
    config: DetectorConfig | None = None,
) -> tuple[Flask, DetectionEngine]:
    """Assemble source, engine and app without starting anything."""
    frame_source = build_source(source, simulate=simulate, config=config)
    engine = DetectionEngine(frame_source, mode="SIMULATION" if simulate else "LIVE")
    return create_app(engine), engine
