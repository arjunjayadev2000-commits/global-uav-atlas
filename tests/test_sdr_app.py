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


class TestMapView:
    def test_renders_without_tiles(self, qapp):
        from sdr.gui.map_view import MapView

        view = MapView()
        view.loader.enabled = False
        view.resize(500, 400)
        assert not view.grab().isNull()

    def test_renders_resolved_and_unresolved_contacts(self, qapp):
        from sdr.gui.map_view import MapView
        from sdr.multi_drone_tracker import Detection

        view = MapView()
        view.loader.enabled = False
        view.resize(500, 400)
        view.set_detections(
            [
                Detection(1, 2.44, 60.0, False, 30.0, 800.0, -60.0, 5, [60.0]),
                Detection(2, 2.43, 90.0, True, 1.0, 0.0, -70.0, 1, [30.0, 90.0, 150.0]),
            ]
        )
        assert not view.grab().isNull()
        assert len(view._tracks) == 2

    def test_prune_drops_dead_contacts(self, qapp):
        from sdr.gui.map_view import MapView
        from sdr.multi_drone_tracker import Detection

        view = MapView()
        view.loader.enabled = False
        view.set_detections([Detection(1, 2.44, 60.0, False, 30.0, 800.0, -60.0, 5, [60.0])])
        view.prune(set())
        assert view._tracks == {}

    def test_projection_round_trips(self, qapp):
        from sdr.gui.tiles import lonlat_to_world, world_to_lonlat

        for lon, lat, zoom in ((76.7794, 30.7333, 13), (-0.1276, 51.5072, 10), (139.69, 35.69, 16)):
            x, y = lonlat_to_world(lon, lat, zoom)
            back_lon, back_lat = world_to_lonlat(x, y, zoom)
            assert abs(back_lon - lon) < 1e-6
            assert abs(back_lat - lat) < 1e-6

    def test_offset_lonlat_moves_the_expected_distance(self, qapp):
        import math

        from sdr.gui.tiles import offset_lonlat

        lon, lat = 76.7794, 30.7333
        north_lon, north_lat = offset_lonlat(lon, lat, 0.0, 1000.0)
        assert north_lat > lat
        assert abs(north_lon - lon) < 1e-6
        east_lon, east_lat = offset_lonlat(lon, lat, 90.0, 1000.0)
        assert east_lon > lon
        assert math.isclose(east_lat, lat, abs_tol=1e-3)


class TestThreatLog:
    def test_shows_one_row_per_contact_and_exports(self, qapp, tmp_path):
        from sdr.gui.tracks import ThreatLogTable
        from sdr.multi_drone_tracker import Detection

        table = ThreatLogTable()
        table.update_detections(
            [
                Detection(1, 2.44, 60.0, False, 30.0, 800.0, -60.0, 5, [60.0]),
                Detection(2, 5.80, 90.0, True, 1.0, 0.0, -70.0, 1, [30.0, 90.0]),
            ]
        )
        table.update_detections([Detection(1, 2.45, 61.0, False, 33.0, 810.0, -60.0, 6, [61.0])])
        assert table.rowCount() == 2

        out = tmp_path / "threat_log.csv"
        assert table.export_csv(str(out)) == 3
        text = out.read_text(encoding="utf-8")
        assert "track_id" in text and "candidate_bearings_deg" in text

    def test_band_classification_does_not_invent_a_device(self):
        from sdr.gui.tracks import classify_band

        assert classify_band(2.44) == "2.4G"
        assert classify_band(5.80) == "5.8G"
        assert classify_band(0.915) == "900M"
        assert classify_band(1.575) == "unknown"

    def test_priority_contact_prefers_resolved_then_strongest(self, qapp):
        from sdr.gui.tracks import ThreatLogTable
        from sdr.multi_drone_tracker import Detection

        table = ThreatLogTable()
        table.update_detections(
            [
                Detection(1, 2.44, 10.0, True, 1.0, 0.0, -40.0, 1, []),   # loudest, unresolved
                Detection(2, 2.44, 20.0, False, 30.0, 500.0, -80.0, 6, []),
                Detection(3, 2.44, 30.0, False, 30.0, 500.0, -60.0, 6, []),
            ]
        )
        # a resolved contact wins over a louder unresolved one
        assert table.priority_contact().track_id == 3


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
    def test_arms_tracks_and_disarms_cleanly(self, qapp):
        import time

        from sdr.gui.mainwindow import MainWindow

        window = MainWindow()
        window.map_view.loader.enabled = False
        window.settings["drones"] = 2
        window.settings["snr_db"] = 30.0
        window.start()
        assert window._worker is not None

        deadline = time.time() + 8
        while time.time() < deadline:
            qapp.processEvents()
            if len(window.map_view._tracks) >= 2:
                break

        assert len(window.map_view._tracks) == 2
        assert window.threat_log.rowCount() == 2
        assert not window.grab().isNull()

        window.stop()
        qapp.processEvents()
        assert window._worker is None

    def test_file_source_without_a_path_is_reported_not_raised(self, qapp):
        from sdr.gui.mainwindow import MainWindow

        window = MainWindow()
        window.settings["source"] = "file"
        window.settings["file"] = ""
        with pytest.raises(ValueError, match="recorded"):
            window._build_source()

    def test_band_selection_drives_the_centre_frequency(self, qapp):
        from sdr.gui.mainwindow import BANDS, MainWindow

        window = MainWindow()
        window.band_buttons["BAND 5.8G"].setChecked(True)
        window._apply_band()
        assert window._current_center_freq() == BANDS["5.8G"]
        assert window.wifi_glyph._active and not window.bt_glyph._active

        window.band_buttons["BAND 2.4G"].setChecked(True)
        window._apply_band()
        assert window._current_center_freq() == BANDS["2.4G"]

    def test_mode_button_cycles(self, qapp):
        from sdr.gui.mainwindow import SCAN_MODES, MainWindow

        window = MainWindow()
        assert window.scan_mode == SCAN_MODES[0]
        window._cycle_mode()
        assert window.scan_mode == SCAN_MODES[1]
        assert SCAN_MODES[1] in window.mode_button.text()

    def test_track_mode_hides_unresolved_contacts(self, qapp):
        from sdr.gui.mainwindow import MainWindow
        from sdr.multi_drone_tracker import Detection

        window = MainWindow()
        contacts = [
            Detection(1, 2.44, 60.0, False, 30.0, 800.0, -60.0, 5, [60.0]),
            Detection(2, 2.43, 90.0, True, 1.0, 0.0, -70.0, 1, [90.0]),
        ]
        while window.scan_mode != "TRACK":
            window._cycle_mode()
        assert [d.track_id for d in window._filter_for_mode(contacts)] == [1]

    def test_urban_toggle_switches_the_path_loss_model(self, qapp):
        from sdr.gui.mainwindow import PATH_LOSS_OPEN, PATH_LOSS_URBAN, MainWindow

        window = MainWindow()
        window.map_view.loader.enabled = False
        window.urban_toggle.setChecked(True)
        window.start()
        try:
            assert window._tracker.path_loss_exponent == PATH_LOSS_URBAN
        finally:
            window.stop()
            qapp.processEvents()

        window.urban_toggle.setChecked(False)
        window.start()
        try:
            assert window._tracker.path_loss_exponent == PATH_LOSS_OPEN
        finally:
            window.stop()
            qapp.processEvents()

    def test_reset_cache_clears_everything(self, qapp):
        from sdr.gui.mainwindow import MainWindow
        from sdr.multi_drone_tracker import Detection

        window = MainWindow()
        window.map_view.loader.enabled = False
        window.threat_log.update_detections(
            [Detection(1, 2.44, 60.0, False, 30.0, 800.0, -60.0, 5, [60.0])]
        )
        window.map_view.set_detections(
            [Detection(1, 2.44, 60.0, False, 30.0, 800.0, -60.0, 5, [60.0])]
        )
        window._reset_cache()
        assert window.threat_log.rowCount() == 0
        assert window.threat_log.logged_rows == 0
        assert window.map_view._tracks == {}
        assert "—" in window.jam_angle_label.text()

    def test_jam_angle_tracks_the_priority_contact(self, qapp):
        from sdr.gui.mainwindow import MainWindow
        from sdr.multi_drone_tracker import Detection

        window = MainWindow()
        window.threat_log.update_detections(
            [Detection(1, 2.44, 137.0, False, 30.0, 800.0, -60.0, 5, [137.0])]
        )
        window._sync_jam_angle()
        assert "137" in window.jam_angle_label.text()


class TestTileLoader:
    def test_offline_loader_returns_nothing_and_does_not_raise(self, qapp, tmp_path):
        from sdr.gui.tiles import TileLoader

        loader = TileLoader(cache_dir=tmp_path)
        loader.enabled = False
        assert loader.tile(13, 100, 200) is None

    def test_reads_a_tile_back_from_the_disk_cache(self, qapp, tmp_path):
        from PyQt6 import QtGui

        from sdr.gui.tiles import TileLoader

        loader = TileLoader(cache_dir=tmp_path)
        loader.enabled = False
        path = loader._cache_path(13, 100, 200)
        path.parent.mkdir(parents=True, exist_ok=True)
        image = QtGui.QImage(256, 256, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor("#123456"))
        image.save(str(path))

        tile = loader.tile(13, 100, 200)
        assert tile is not None and tile.width() == 256
