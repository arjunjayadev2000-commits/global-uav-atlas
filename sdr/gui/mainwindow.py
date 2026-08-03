"""Detector console: header, control column and map overview."""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from sdr.gui import theme
from sdr.gui.engine import TrackerWorker
from sdr.gui.map_view import MapView
from sdr.gui.settings_dialog import SettingsDialog
from sdr.gui.spectrum import SpectrumWidget
from sdr.gui.tracks import ThreatLogTable
from sdr.gui.widgets import (
    GlyphButton,
    GlyphLabel,
    MapPill,
    NeonButton,
    OutlinedBox,
    RadioPill,
    ToggleSwitch,
)
from sdr.multi_drone_tracker import MultiDroneSDRTracker
from sdr.sources import FileSource, IQSource, SimulatedDrone, SimulatedSource

TITLE = "KHARGA KALATEER DRONE DETECTOR"

#: Band centre frequencies. One AD9361 pair has a single LO, so DUAL is
#: time-multiplexed -- the receiver retunes between dwells rather than
#: watching both bands at once.
BANDS = {
    "2.4G": 2.44e9,
    "5.8G": 5.80e9,
}

#: Path-loss exponents for the range model. Urban clutter attenuates much
#: faster than open ground, and range is exponential in this number.
PATH_LOSS_OPEN = 2.2
PATH_LOSS_URBAN = 3.0

SCAN_MODES = ["OMNI", "SECTOR", "TRACK"]


class MainWindow(QtWidgets.QMainWindow):
    """Top-level console."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(TITLE.title())
        self.resize(1500, 900)

        self._worker: TrackerWorker | None = None
        self._tracker: MultiDroneSDRTracker | None = None
        self._mode_index = 0
        self._dwell_band = "2.4G"

        self.settings = {
            "source": "simulated",
            "uri": "ip:192.168.2.1",
            "file": "",
            "drones": 3,
            "snr_db": 26.0,
            "sample_rate": 40e6,
            "buffer_size": 1024,
            "threshold_db": 12.0,
            "antenna_spacing_m": 0.245,
            "confirm_margin": 6.0,
            "latitude": 30.7333,
            "longitude": 76.7794,
            "inner_ring_m": 1500.0,
            "outer_ring_m": 3000.0,
        }

        central = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(10)
        outer.addWidget(self._build_header())

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(self._build_left_column(), stretch=4)
        body.addWidget(self._build_map_panel(), stretch=6)
        outer.addLayout(body, stretch=1)
        self.setCentralWidget(central)

        self._build_menu()
        self.statusBar().showMessage("Idle")
        self._status_source = QtWidgets.QLabel("no source")
        self._status_rate = QtWidgets.QLabel("— fps")
        for label in (self._status_source, self._status_rate):
            label.setStyleSheet(f"color: {theme.TEXT_MUTED.name()};")
            self.statusBar().addPermanentWidget(label)

        self._apply_band()
        self._sync_jam_angle()

    # -- header --------------------------------------------------------

    def _build_header(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        mark = GlyphButton(theme.draw_drone_mark, theme.SENSOR, size=40, tooltip=TITLE)
        mark.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        row.addWidget(mark)

        title = QtWidgets.QLabel(TITLE)
        title.setObjectName("titleText")
        row.addWidget(title)
        row.addStretch(1)

        self.jam_angle_label = QtWidgets.QLabel("JAM ANGLE")
        self.jam_angle_label.setStyleSheet(
            f"color: {theme.GOLD.name()}; font-weight: bold; letter-spacing: 1px;"
        )
        self.jam_angle_label.setToolTip(
            "Bearing of the strongest resolved contact.\n"
            "A passive readout for aiming a directional effector — this\n"
            "application never transmits."
        )
        row.addWidget(self.jam_angle_label)
        row.addSpacing(18)

        self.urban_label = QtWidgets.QLabel("URBAN")
        self.urban_label.setStyleSheet(f"color: {theme.RED.name()}; font-weight: bold;")
        row.addWidget(self.urban_label)

        self.urban_toggle = ToggleSwitch(on_colour=theme.RED)
        self.urban_toggle.setToolTip(
            f"Propagation model for the range estimate.\n"
            f"Open ground n={PATH_LOSS_OPEN}, urban clutter n={PATH_LOSS_URBAN}."
        )
        self.urban_toggle.toggled.connect(self._on_urban_toggled)
        row.addWidget(self.urban_toggle)
        row.addSpacing(14)

        gear = GlyphButton(theme.draw_gear, theme.GOLD, size=30, tooltip="Settings")
        gear.clicked.connect(self._open_settings)
        row.addWidget(gear)

        spiral = GlyphButton(theme.draw_spiral, theme.PURPLE, size=30, tooltip="About")
        spiral.clicked.connect(self._about)
        row.addWidget(spiral)
        return bar

    # -- left column ---------------------------------------------------

    def _build_left_column(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)

        self.reset_button = NeonButton("RESET SYSTEM CACHE", theme.RED_DEEP.lighter(140), theme.RED)
        self.reset_button.setToolTip("Drop all tracks, history and the logged detections.")
        self.reset_button.clicked.connect(self._reset_cache)
        column.addWidget(self.reset_button)

        self.mode_button = NeonButton("MODE: OMNI", theme.BLUE, theme.GREEN)
        self.mode_button.setToolTip(
            "OMNI   — report every bearing\n"
            "SECTOR — report only contacts inside the watch sector\n"
            "TRACK  — report only resolved contacts"
        )
        self.mode_button.clicked.connect(self._cycle_mode)
        column.addWidget(self.mode_button)

        heading_row = QtWidgets.QHBoxLayout()
        heading = QtWidgets.QLabel("THREAT LOG")
        heading.setObjectName("sectionHeading")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        self.bt_glyph = GlyphLabel(
            theme.draw_bluetooth, theme.SENSOR, tooltip="2.4 GHz band armed"
        )
        self.wifi_glyph = GlyphLabel(theme.draw_wifi, theme.SENSOR, tooltip="5.8 GHz band armed")
        heading_row.addWidget(self.bt_glyph)
        heading_row.addWidget(self.wifi_glyph)
        column.addLayout(heading_row)

        column.addWidget(self._build_band_box())
        self.threat_log = ThreatLogTable()
        column.addWidget(self.threat_log, stretch=3)

        spectrum_heading = QtWidgets.QLabel("Spectrum Analyzer")
        spectrum_heading.setObjectName("goldHeading")
        column.addWidget(spectrum_heading)

        self.spectrum_stack = QtWidgets.QStackedWidget()
        self.spectrum_placeholder = QtWidgets.QLabel("No chart data available.")
        self.spectrum_placeholder.setObjectName("placeholder")
        self.spectrum_placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.spectrum = SpectrumWidget()
        self.spectrum_stack.addWidget(self.spectrum_placeholder)
        self.spectrum_stack.addWidget(self.spectrum)
        column.addWidget(self.spectrum_stack, stretch=4)
        return panel

    def _build_band_box(self) -> QtWidgets.QWidget:
        box = OutlinedBox()
        box.setFixedHeight(44)
        row = QtWidgets.QHBoxLayout(box)
        row.setContentsMargins(12, 4, 12, 4)
        row.setSpacing(10)

        self.band_group = QtWidgets.QButtonGroup(self)
        self.band_buttons: dict[str, RadioPill] = {}
        for name in ("BAND 2.4G", "BAND 5.8G", "DUAL"):
            pill = RadioPill(name)
            self.band_group.addButton(pill)
            self.band_buttons[name] = pill
            row.addWidget(pill)
        self.band_buttons["DUAL"].setChecked(True)
        self.band_group.buttonClicked.connect(lambda _: self._apply_band())

        row.addStretch(1)
        self.start_stop = NeonButton("ARM", theme.GREEN, theme.GREEN)
        self.start_stop.setFixedWidth(78)
        self.start_stop.setFixedHeight(28)
        self.start_stop.clicked.connect(self._toggle_acquisition)
        row.addWidget(self.start_stop)
        return box

    # -- map panel -----------------------------------------------------

    def _build_map_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)

        heading = QtWidgets.QLabel("MAP OVERVIEW")
        heading.setObjectName("mapHeading")
        column.addWidget(heading)

        container = QtWidgets.QWidget()
        container.setStyleSheet(f"border: 1px solid {theme.BORDER.name()};")
        holder = QtWidgets.QVBoxLayout(container)
        holder.setContentsMargins(1, 1, 1, 1)

        self.map_view = MapView(
            latitude=self.settings["latitude"],
            longitude=self.settings["longitude"],
        )
        self.map_view.set_rings(self.settings["inner_ring_m"], self.settings["outer_ring_m"])
        holder.addWidget(self.map_view)
        column.addWidget(container, stretch=1)

        # floating overlay controls
        self.nl_pill = MapPill("NL Sources", self.map_view)
        self.nl_pill.setToolTip(
            "Show every candidate bearing for unresolved contacts.\n"
            "At this array's spacing they are real alternatives, not noise."
        )
        self.nl_pill.setChecked(True)
        self.nl_pill.toggled.connect(self.map_view.set_show_candidates)

        self.fit_button = GlyphButton(
            theme.draw_crosshair, theme.GOLD, size=38, tooltip="Fit rings", framed=True,
            parent=self.map_view,
        )
        self.fit_button.clicked.connect(self.map_view.fit_rings)
        self.locate_button = GlyphButton(
            theme.draw_locate, theme.GOLD, size=38, tooltip="Recentre on sensor", framed=True,
            parent=self.map_view,
        )
        self.locate_button.clicked.connect(self.map_view.recenter)

        self.map_view.installEventFilter(self)
        return panel

    def eventFilter(self, watched, event) -> bool:
        if watched is self.map_view and event.type() == QtCore.QEvent.Type.Resize:
            self._place_map_overlays()
        return super().eventFilter(watched, event)

    def _place_map_overlays(self) -> None:
        width, height = self.map_view.width(), self.map_view.height()
        self.nl_pill.move(14, height - self.nl_pill.height() - 14)
        self.fit_button.move(width - 52, height - 96)
        self.locate_button.move(width - 52, height - 52)

    # -- menu ----------------------------------------------------------

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        export = QtGui.QAction("&Export threat log to CSV…", self)
        export.setShortcut("Ctrl+E")
        export.triggered.connect(self._export_csv)
        file_menu.addAction(export)
        settings = QtGui.QAction("&Settings…", self)
        settings.setShortcut("Ctrl+,")
        settings.triggered.connect(self._open_settings)
        file_menu.addAction(settings)
        file_menu.addSeparator()
        quit_action = QtGui.QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("&Help")
        about = QtGui.QAction("&About", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    def _about(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "About",
            f"<b>{TITLE.title()}</b><br><br>"
            "Passive direction finding for frequency-hopping drones using four "
            "coherent receive channels (2× AD9361 / FMCOMMS5). Receive only — "
            "this application never transmits.<br><br>"
            "The antenna pairs are roughly two wavelengths apart at 2.44 GHz, so "
            "a single hop's phase is consistent with about a dozen bearings. The "
            "true one is recovered by accumulating hops at different carriers, "
            "and a bearing is reported as resolved only once one direction "
            "clearly out-fits every alternative. Unresolved contacts are drawn "
            "with all their candidate wedges rather than one misleading mark."
            "<br><br>Contacts are shown as bearing wedges, not points: bearing is "
            "measured precisely, range is inferred from signal strength and is "
            "far rougher.",
        )

    def _export_csv(self) -> None:
        if not self.threat_log.logged_rows:
            QtWidgets.QMessageBox.information(self, "Export", "No detections recorded yet.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export threat log", "threat_log.csv", "CSV (*.csv)"
        )
        if path:
            count = self.threat_log.export_csv(path)
            self.statusBar().showMessage(f"Exported {count} detections to {path}", 5000)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.settings.update(dialog.values())
            self.map_view.set_sensor_position(
                self.settings["latitude"], self.settings["longitude"]
            )
            self.map_view.set_rings(
                self.settings["inner_ring_m"], self.settings["outer_ring_m"]
            )
            if self._worker is not None:
                self._worker.update_parameter("threshold_db", self.settings["threshold_db"])
                self._worker.update_parameter(
                    "antenna_spacing_m", self.settings["antenna_spacing_m"]
                )
                self._worker.update_parameter("confirm_margin", self.settings["confirm_margin"])

    # -- controls ------------------------------------------------------

    @property
    def band_mode(self) -> str:
        for name, pill in self.band_buttons.items():
            if pill.isChecked():
                return name.replace("BAND ", "")
        return "DUAL"

    def _apply_band(self) -> None:
        mode = self.band_mode
        self.bt_glyph.set_active(mode in ("2.4G", "DUAL"))
        self.wifi_glyph.set_active(mode in ("5.8G", "DUAL"))
        if mode != "DUAL":
            self._dwell_band = mode
        if self._worker is not None:
            self.statusBar().showMessage(
                "Band change applies on the next arm — the receiver retunes at start", 4000
            )

    def _current_center_freq(self) -> float:
        return BANDS.get(self._dwell_band if self.band_mode == "DUAL" else self.band_mode, 2.44e9)

    def _cycle_mode(self) -> None:
        self._mode_index = (self._mode_index + 1) % len(SCAN_MODES)
        self.mode_button.setText(f"MODE: {SCAN_MODES[self._mode_index]}")
        self.mode_button.update()

    @property
    def scan_mode(self) -> str:
        return SCAN_MODES[self._mode_index]

    def _on_urban_toggled(self, urban: bool) -> None:
        exponent = PATH_LOSS_URBAN if urban else PATH_LOSS_OPEN
        self.urban_label.setStyleSheet(
            f"color: {(theme.RED if urban else theme.TEXT_MUTED).name()}; font-weight: bold;"
        )
        if self._worker is not None:
            self._worker.update_parameter("path_loss_exponent", exponent)

    def _reset_cache(self) -> None:
        self.threat_log.reset()
        self.map_view.clear()
        self.spectrum.clear()
        self.spectrum_stack.setCurrentWidget(self.spectrum_placeholder)
        if self._tracker is not None:
            self._tracker._tracks.clear()
        self.statusBar().showMessage("System cache cleared", 3000)
        self._sync_jam_angle()

    def _sync_jam_angle(self) -> None:
        contact = self.threat_log.priority_contact()
        if contact is None:
            self.jam_angle_label.setText("JAM ANGLE  —")
            self.jam_angle_label.setStyleSheet(
                f"color: {theme.GOLD_DIM.name()}; font-weight: bold; letter-spacing: 1px;"
            )
            return
        suffix = "" if not contact.bearing_ambiguous else " ?"
        self.jam_angle_label.setText(f"JAM ANGLE  {contact.bearing_degrees:.0f}°{suffix}")
        colour = theme.GOLD if not contact.bearing_ambiguous else theme.GOLD_DIM
        self.jam_angle_label.setStyleSheet(
            f"color: {colour.name()}; font-weight: bold; letter-spacing: 1px;"
        )

    # -- acquisition ---------------------------------------------------

    def _build_source(self) -> IQSource:
        common = {
            "sample_rate": self.settings["sample_rate"],
            "center_freq_hz": self._current_center_freq(),
            "buffer_size": int(self.settings["buffer_size"]),
        }
        kind = self.settings["source"]

        if kind == "file":
            if not self.settings["file"]:
                raise ValueError("choose a recorded .npy capture in Settings first")
            return FileSource(self.settings["file"], **common)

        if kind == "fmcomms5":
            from sdr.sources import FMComms5Source

            return FMComms5Source(uri=self.settings["uri"], **common)

        count = int(self.settings["drones"])
        drones = [
            SimulatedDrone(
                bearing_deg=(35 + 360 * i / max(count, 1)) % 360,
                range_m=600 + 700 * i,
                bearing_rate_deg_s=(3.0 if i % 2 == 0 else -2.0),
            )
            for i in range(count)
        ]
        return SimulatedSource(
            drones=drones,
            antenna_spacing_m=self.settings["antenna_spacing_m"],
            snr_db=self.settings["snr_db"],
            path_loss_exponent=(
                PATH_LOSS_URBAN if self.urban_toggle.isChecked() else PATH_LOSS_OPEN
            ),
            **common,
        )

    def _toggle_acquisition(self) -> None:
        self.stop() if self._worker is not None else self.start()

    def start(self) -> None:
        if self._worker is not None:
            return
        try:
            source = self._build_source()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Cannot arm", str(exc))
            return

        self._tracker = MultiDroneSDRTracker(
            sampling_rate=self.settings["sample_rate"],
            center_freq_hz=self._current_center_freq(),
            threshold_db=self.settings["threshold_db"],
            antenna_spacing_m=self.settings["antenna_spacing_m"],
            confirm_margin=self.settings["confirm_margin"],
        )
        self._tracker.path_loss_exponent = (
            PATH_LOSS_URBAN if self.urban_toggle.isChecked() else PATH_LOSS_OPEN
        )

        self.map_view.clear()
        self.spectrum.clear()
        self.threat_log.clear_tracks()

        self._worker = TrackerWorker(source, self._tracker)
        self._worker.frameReady.connect(self._on_frame)
        self._worker.statsReady.connect(self._on_stats)
        self._worker.failed.connect(self._on_failure)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

        self.start_stop.setText("DISARM")
        self.start_stop.set_text_colour(theme.RED)
        self._status_source.setText(f"{source.description} · {self.band_mode}")
        self.statusBar().showMessage("Acquiring")

    def stop(self) -> None:
        worker = self._worker
        if worker is None:
            return
        worker.stop()
        if not worker.wait(3000):
            worker.terminate()
            worker.wait(500)
        # Tear down here rather than waiting for the queued `finished`
        # signal: until _worker is cleared, start() refuses to run, so a
        # quick DISARM/ARM would silently do nothing.
        self._on_finished()

    def _on_finished(self) -> None:
        if self._worker is None:
            return  # already torn down synchronously by stop()
        self._worker = None
        self.start_stop.setText("ARM")
        self.start_stop.set_text_colour(theme.GREEN)
        self.statusBar().showMessage("Stopped")
        self._status_rate.setText("— fps")

    def _on_failure(self, message: str) -> None:
        self.statusBar().showMessage(f"Source error: {message}", 10000)
        QtWidgets.QMessageBox.critical(self, "Acquisition failed", message)

    # -- updates -------------------------------------------------------

    def _filter_for_mode(self, detections):
        if self.scan_mode == "TRACK":
            return [d for d in detections if not d.bearing_ambiguous]
        return detections

    def _on_frame(self, detections, spectrum_db, frequencies_hz, threshold_db) -> None:
        if spectrum_db is not None:
            self.spectrum.update_spectrum(spectrum_db, frequencies_hz, threshold_db)
            self.spectrum_stack.setCurrentWidget(self.spectrum)

        shown = self._filter_for_mode(detections)
        if shown:
            self.map_view.set_detections(shown)
            self.threat_log.update_detections(shown)
        if self._tracker is not None:
            live = set(self._tracker._tracks)
            self.map_view.prune(live)
            self.threat_log.prune(live)
        self._sync_jam_angle()

    def _on_stats(self, fps: float, frames: int, track_count: int) -> None:
        self._status_rate.setText(f"{fps:,.0f} fps")
        self.statusBar().showMessage(
            f"Acquiring — {frames:,} frames, {track_count} contact"
            f"{'s' if track_count != 1 else ''}"
        )

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.stop()
        event.accept()
