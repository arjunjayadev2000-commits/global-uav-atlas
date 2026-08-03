"""Capture/processing worker.

Reading a radio and running the tracker must never happen on the GUI
thread: a 40 Msps source delivers frames far faster than a display can
repaint, and blocking the event loop would freeze the window. This worker
owns the source and the tracker, runs them in their own thread, and
publishes results at a rate a human can actually look at.

Two rates are deliberately decoupled. *Every* frame is processed, because
dropping frames would drop hops and hops are what resolve a bearing. Only
the display is throttled: detections accumulate between repaints and are
emitted as a batch with the most recent spectrum.
"""

from __future__ import annotations

import time

import numpy as np
from PyQt6 import QtCore

from sdr.multi_drone_tracker import Detection, MultiDroneSDRTracker
from sdr.sources import IQSource


class TrackerWorker(QtCore.QThread):
    """Runs a source through a tracker and publishes batched results."""

    #: (detections, spectrum_db, frequencies_hz, threshold_db)
    frameReady = QtCore.pyqtSignal(object, object, object, float)
    #: (frames_per_second, frames_processed, active_tracks)
    statsReady = QtCore.pyqtSignal(float, int, int)
    failed = QtCore.pyqtSignal(str)

    def __init__(
        self,
        source: IQSource,
        tracker: MultiDroneSDRTracker,
        display_hz: float = 25.0,
        parent: QtCore.QObject | None = None,
    ):
        super().__init__(parent)
        self._source = source
        self._tracker = tracker
        self._display_interval = 1.0 / display_hz
        self._running = False
        self._mutex = QtCore.QMutex()
        self._pending: dict[str, float] = {}

    # -- control -------------------------------------------------------

    def stop(self) -> None:
        self._running = False

    def update_parameter(self, name: str, value: float) -> None:
        """Queue a tracker setting change, applied between frames.

        Mutating the tracker straight from the GUI thread would race with
        the frame currently being processed.
        """
        with QtCore.QMutexLocker(self._mutex):
            self._pending[name] = value

    def _apply_pending(self) -> None:
        with QtCore.QMutexLocker(self._mutex):
            if not self._pending:
                return
            pending, self._pending = self._pending, {}
        for name, value in pending.items():
            setattr(self._tracker, name, value)

    # -- main loop -----------------------------------------------------

    def run(self) -> None:
        self._running = True
        pending: list[Detection] = []
        spectrum: np.ndarray | None = None
        frequencies: np.ndarray | None = None
        threshold = 0.0

        frames = 0
        window_frames = 0
        last_emit = time.perf_counter()
        last_rate = last_emit

        try:
            while self._running:
                self._apply_pending()

                try:
                    iq = self._source.read()
                except EOFError:
                    break

                result = self._tracker.process_frame(iq)
                pending.extend(result.detections)
                spectrum = result.spectrum_db
                frequencies = result.frequencies_hz
                threshold = result.threshold_db
                frames += 1
                window_frames += 1

                now = time.perf_counter()
                if now - last_emit >= self._display_interval:
                    self.frameReady.emit(pending, spectrum, frequencies, threshold)
                    pending = []
                    last_emit = now

                if now - last_rate >= 0.5:
                    rate = window_frames / (now - last_rate)
                    self.statsReady.emit(rate, frames, len(self._tracker._tracks))
                    window_frames = 0
                    last_rate = now
        except Exception as exc:  # surfaced in the UI rather than killing the thread
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self._source.close()
