"""Main window: assembles the scope, spectrum, table and controls."""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from sdr.gui.controls import ControlPanel
from sdr.gui.engine import TrackerWorker
from sdr.gui.ppi import PPIWidget
from sdr.gui.spectrum import SpectrumWidget
from sdr.gui.tracks import TrackTable
from sdr.multi_drone_tracker import MultiDroneSDRTracker
from sdr.sources import FileSource, IQSource, SimulatedDrone, SimulatedSource

DARK_STYLESHEET = """
QWidget { background-color: #10161a; color: #c8d8dd; font-size: 12px; }
QGroupBox { border: 1px solid #24343c; border-radius: 4px; margin-top: 10px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; color: #7fb3c0; }
QPushButton { background-color: #1c2b33; border: 1px solid #2e4650; border-radius: 3px; padding: 5px 12px; }
QPushButton:hover:enabled { background-color: #243944; }
QPushButton:disabled { color: #4a5a61; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #16222a; border: 1px solid #2a3e48; border-radius: 3px; padding: 3px;
}
QHeaderView::section { background-color: #1a272e; border: 0; padding: 4px; color: #7fb3c0; }
QTableWidget { gridline-color: #24343c; }
QStatusBar { color: #7fb3c0; }
"""


class MainWindow(QtWidgets.QMainWindow):
    """Top-level window wiring the worker thread to the four views."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Multi-Drone SDR Tracker")
        self.resize(1440, 880)

        self._worker: TrackerWorker | None = None
        self._tracker: MultiDroneSDRTracker | None = None

        self.controls = ControlPanel()
        self.ppi = PPIWidget()
        self.spectrum = SpectrumWidget()
        self.tracks = TrackTable()

        right = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        right.addWidget(self.spectrum)
        right.addWidget(self.tracks)
        right.setSizes([520, 300])

        centre = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        centre.addWidget(self.ppi)
        centre.addWidget(right)
        centre.setSizes([620, 800])

        outer = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(self.controls)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(272)
        scroll.setMaximumWidth(330)
        outer.addWidget(scroll)
        outer.addWidget(centre)
        outer.setStretchFactor(1, 1)
        self.setCentralWidget(outer)

        self._build_menu()
        self.statusBar().showMessage("Idle")
        self._status_source = QtWidgets.QLabel("no source")
        self._status_rate = QtWidgets.QLabel("- fps")
        for label in (self._status_source, self._status_rate):
            self.statusBar().addPermanentWidget(label)

        self.controls.startRequested.connect(self.start)
        self.controls.stopRequested.connect(self.stop)
        self.controls.trackerParameterChanged.connect(self._on_tracker_parameter)
        self.controls.displayOptionChanged.connect(self._on_display_option)

    # -- menu ----------------------------------------------------------

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        export = QtGui.QAction("&Export detections to CSV...", self)
        export.setShortcut("Ctrl+E")
        export.triggered.connect(self._export_csv)
        file_menu.addAction(export)

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
            "<b>Multi-Drone SDR Tracker</b><br><br>"
            "Direction finding for frequency-hopping drones using four coherent "
            "receive channels (2x AD9361 / FMCOMMS5).<br><br>"
            "The antenna pairs are about two wavelengths apart at 2.44 GHz, so a "
            "single hop's phase is consistent with roughly a dozen bearings. The "
            "tracker resolves the true one by accumulating hops at different "
            "carriers, and reports a bearing as resolved only once one direction "
            "clearly out-fits every alternative. Unresolved tracks are drawn with "
            "all their candidates rather than a single misleading marker.",
        )

    def _export_csv(self) -> None:
        if not self.tracks.logged_rows:
            QtWidgets.QMessageBox.information(self, "Export", "No detections recorded yet.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export detections", "detections.csv", "CSV (*.csv)"
        )
        if path:
            count = self.tracks.export_csv(path)
            self.statusBar().showMessage(f"Exported {count} detections to {path}", 5000)

    # -- source construction -------------------------------------------

    def _build_source(self) -> IQSource:
        kind = self.controls.source_kind
        common = {
            "sample_rate": self.controls.sample_rate,
            "center_freq_hz": self.controls.center_freq_hz,
            "buffer_size": self.controls.buffer_size,
        }

        if kind == "file":
            path = self.controls.file_edit.text().strip()
            if not path:
                raise ValueError("choose a recorded .npy capture first")
            return FileSource(path, **common)

        if kind == "fmcomms5":
            from sdr.sources import FMComms5Source

            return FMComms5Source(uri=self.controls.uri_edit.text().strip(), **common)

        count = self.controls.drones_spin.value()
        drones = [
            SimulatedDrone(
                bearing_deg=(35 + 360 * i / max(count, 1)) % 360,
                range_m=60 + 45 * i,
                bearing_rate_deg_s=(6.0 if i % 2 == 0 else -4.0),
            )
            for i in range(count)
        ]
        return SimulatedSource(
            drones=drones,
            antenna_spacing_m=self.controls.spacing_spin.value(),
            snr_db=self.controls.snr_spin.value(),
            **common,
        )

    # -- lifecycle -----------------------------------------------------

    def start(self) -> None:
        if self._worker is not None:
            return
        try:
            source = self._build_source()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Cannot start", str(exc))
            return

        self._tracker = MultiDroneSDRTracker(
            sampling_rate=self.controls.sample_rate,
            center_freq_hz=self.controls.center_freq_hz,
            threshold_db=self.controls.threshold_spin.value(),
            antenna_spacing_m=self.controls.spacing_spin.value(),
            confirm_margin=self.controls.margin_spin.value(),
        )

        self.ppi.clear()
        self.spectrum.clear()
        self.tracks.clear_tracks()

        self._worker = TrackerWorker(source, self._tracker)
        self._worker.frameReady.connect(self._on_frame)
        self._worker.statsReady.connect(self._on_stats)
        self._worker.failed.connect(self._on_failure)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

        self.controls.set_running(True)
        self._status_source.setText(source.description)
        self.statusBar().showMessage("Acquiring")

    def stop(self) -> None:
        if self._worker is None:
            return
        self._worker.stop()
        self._worker.wait(2000)

    def _on_finished(self) -> None:
        self._worker = None
        self.controls.set_running(False)
        self.statusBar().showMessage("Stopped")
        self._status_rate.setText("- fps")

    def _on_failure(self, message: str) -> None:
        self.statusBar().showMessage(f"Source error: {message}", 10000)
        QtWidgets.QMessageBox.critical(self, "Acquisition failed", message)

    # -- updates -------------------------------------------------------

    def _on_frame(self, detections, spectrum_db, frequencies_hz, threshold_db) -> None:
        if spectrum_db is not None:
            self.spectrum.update_spectrum(spectrum_db, frequencies_hz, threshold_db)
        if detections:
            self.ppi.set_detections(detections)
            self.tracks.update_detections(detections)
        if self._tracker is not None:
            live = set(self._tracker._tracks)
            self.ppi.prune(live)
            self.tracks.prune(live)

    def _on_stats(self, fps: float, frames: int, track_count: int) -> None:
        self._status_rate.setText(f"{fps:,.0f} fps")
        self.statusBar().showMessage(
            f"Acquiring - {frames:,} frames processed, {track_count} active track"
            f"{'s' if track_count != 1 else ''}"
        )

    def _on_tracker_parameter(self, name: str, value: float) -> None:
        if self._worker is not None:
            self._worker.update_parameter(name, value)

    def _on_display_option(self, name: str, value) -> None:
        if name == "auto_range":
            self.ppi.set_auto_range(bool(value))
        elif name == "max_range":
            self.ppi.set_max_range(float(value))
            self.controls.autorange_check.setChecked(False)
        elif name == "show_ghosts":
            self.ppi.set_show_ghosts(bool(value))

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.stop()
        event.accept()
