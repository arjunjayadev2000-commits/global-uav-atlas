"""Tests for the IQ sources and the PyQt application.

GUI tests run against Qt's offscreen platform so they need no display. They
are skipped entirely when PyQt6 is not installed, since the processing core
is usable without the GUI stack.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sdr.multi_drone_tracker import MultiDroneSDRTracker
from sdr.sources import FileSource, SimulatedDrone, SimulatedSource

pyqt = pytest.importorskip("PyQt6", reason="GUI extras not installed")


# ----------------------------------------------------------------------
# Sources
# ----------------------------------------------------------------------


class TestSimulatedSource:
    def test_frame_shape_and_dtype(self):
        source = SimulatedSource(buffer_size=512, seed=1)
        frame = source.read()
        assert frame.shape == (4, 512)
        assert np.iscomplexobj(frame)

    def test_bearing_and_range_round_trip_through_the_tracker(self):
        """Truth in, truth out: the simulator derives amplitude from range
        using the same model the tracker inverts, so a correct pipeline
        recovers both the bearing and the range it was given."""
        drones = [
            SimulatedDrone(bearing_deg=35.0, range_m=60.0),
            SimulatedDrone(bearing_deg=200.0, range_m=140.0),
        ]
        source = SimulatedSource(
            drones=drones, center_freq_hz=2.44e9, buffer_size=1024, snr_db=30, seed=2
        )
        tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.44e9)

        detections = []
        for _ in range(6):
            detections = tracker.process_sdr_buffer(source.read())

        assert len(detections) == 2
        for drone in drones:
            match = min(
                detections, key=lambda d: abs(d.bearing_degrees - drone.bearing_deg)
            )
            assert not match.bearing_ambiguous
            assert abs(match.bearing_degrees - drone.bearing_deg) < 2.0
            assert match.distance_meters == pytest.approx(drone.range_m, rel=0.10)

    def test_single_hop_channel_never_confirms_a_bearing(self):
        """A drone pinned to one carrier gives no frequency diversity, so
        the tracker must decline to resolve rather than guess."""
        source = SimulatedSource(
            drones=[SimulatedDrone(bearing_deg=75.0, hop_channels=[2.442e9])],
            center_freq_hz=2.44e9,
            snr_db=30,
            seed=3,
        )
        tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.44e9)
        detections = []
        for _ in range(8):
            detections = tracker.process_sdr_buffer(source.read())

        assert detections and detections[0].hops_observed >= 5
        assert detections[0].bearing_ambiguous

    def test_no_drones_produces_only_noise(self):
        source = SimulatedSource(drones=[], seed=4)
        tracker = MultiDroneSDRTracker()
        assert tracker.process_sdr_buffer(source.read()) == []

    def test_moving_drone_reports_changing_truth(self):
        source = SimulatedSource(
            drones=[SimulatedDrone(bearing_deg=10.0, bearing_rate_deg_s=1e5)], seed=5
        )
        first = source.truth_bearings()[0]
        for _ in range(20):
            source.read()
        assert source.truth_bearings()[0] != first


class TestFileSource:
    def test_replays_and_loops(self, tmp_path):
        data = (np.random.default_rng(0).standard_normal((4, 2048))
                + 1j * np.random.default_rng(1).standard_normal((4, 2048)))
        path = tmp_path / "capture.npy"
        np.save(path, data)

        source = FileSource(str(path), buffer_size=1024)
        assert source.read().shape == (4, 1024)
        assert source.read().shape == (4, 1024)
        np.testing.assert_allclose(source.read(), data[:, :1024])  # wrapped around

    def test_rejects_wrong_shape(self, tmp_path):
        path = tmp_path / "bad.npy"
        np.save(path, np.zeros((2, 100), dtype=complex))
        with pytest.raises(ValueError, match="4, total_samples"):
            FileSource(str(path))

    def test_rejects_real_valued_capture(self, tmp_path):
        path = tmp_path / "real.npy"
        np.save(path, np.zeros((4, 100)))
        with pytest.raises(ValueError, match="complex"):
            FileSource(str(path))

    def test_raises_at_end_when_not_looping(self, tmp_path):
        path = tmp_path / "short.npy"
        np.save(path, np.zeros((4, 1024), dtype=complex))
        source = FileSource(str(path), buffer_size=1024, loop=False)
        source.read()
        with pytest.raises(EOFError):
            source.read()


# ----------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    app.processEvents()


class TestPPIWidget:
    def test_renders_with_no_tracks(self, qapp):
        from sdr.gui.ppi import PPIWidget

        widget = PPIWidget()
        widget.resize(400, 400)
        assert not widget.grab().isNull()

    def test_renders_resolved_and_unresolved_tracks(self, qapp):
        from sdr.gui.ppi import PPIWidget
        from sdr.multi_drone_tracker import Detection

        widget = PPIWidget()
        widget.resize(400, 400)
        widget.set_detections(
            [
                Detection(1, 2.44, 60.0, False, 30.0, 80.0, -60.0, 5, [60.0]),
                Detection(2, 2.43, 90.0, True, 1.0, 0.0, -70.0, 1, [30.0, 90.0, 150.0]),
            ]
        )
        assert not widget.grab().isNull()
        assert len(widget._tracks) == 2

    def test_prune_drops_dead_tracks(self, qapp):
        from sdr.gui.ppi import PPIWidget
        from sdr.multi_drone_tracker import Detection

        widget = PPIWidget()
        widget.set_detections([Detection(1, 2.44, 60.0, False, 30.0, 80.0, -60.0, 5, [60.0])])
        widget.prune(set())
        assert widget._tracks == {}


class TestTrackTable:
    def test_shows_one_row_per_track_and_exports(self, qapp, tmp_path):
        from sdr.gui.tracks import TrackTable
        from sdr.multi_drone_tracker import Detection

        table = TrackTable()
        table.update_detections(
            [
                Detection(1, 2.44, 60.0, False, 30.0, 80.0, -60.0, 5, [60.0]),
                Detection(2, 2.43, 90.0, True, 1.0, 0.0, -70.0, 1, [30.0, 90.0]),
            ]
        )
        # a second hop on track 1 replaces its row rather than adding one
        table.update_detections([Detection(1, 2.45, 61.0, False, 33.0, 81.0, -60.0, 6, [61.0])])
        assert table.rowCount() == 2

        out = tmp_path / "detections.csv"
        assert table.export_csv(str(out)) == 3  # every detection logged, not just live rows
        text = out.read_text(encoding="utf-8")
        assert "track_id" in text and "candidate_bearings_deg" in text


class TestSpectrumWidget:
    def test_accepts_frames_and_builds_history(self, qapp):
        from sdr.gui.spectrum import SpectrumWidget

        widget = SpectrumWidget()
        freqs = np.linspace(2.42e9, 2.46e9, 256)
        for _ in range(3):
            widget.update_spectrum(np.random.default_rng(0).normal(-90, 3, 256), freqs, -70.0)
        assert widget._history is not None
        assert widget._history.shape[1] == 256


class TestMainWindow:
    def test_starts_tracks_and_stops_cleanly(self, qapp):
        from sdr.gui.mainwindow import MainWindow

        window = MainWindow()
        window.controls.drones_spin.setValue(2)
        window.controls.snr_spin.setValue(30.0)
        window.start()
        assert window._worker is not None

        deadline = __import__("time").time() + 6
        while __import__("time").time() < deadline:
            qapp.processEvents()
            if len(window.ppi._tracks) >= 2 and all(
                not d.bearing_ambiguous for d in window.ppi._tracks.values()
            ):
                break

        assert len(window.ppi._tracks) == 2
        assert window.tracks.rowCount() == 2
        assert not window.grab().isNull()

        window.stop()
        qapp.processEvents()
        assert window._worker is None

    def test_file_source_without_a_path_is_reported_not_raised(self, qapp):
        from sdr.gui.mainwindow import MainWindow

        window = MainWindow()
        window.controls.source_combo.setCurrentIndex(2)  # recorded file
        window.controls.file_edit.setText("")
        with pytest.raises(ValueError, match="recorded"):
            window._build_source()
