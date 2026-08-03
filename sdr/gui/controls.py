"""Source and tracker controls.

Settings split into two kinds, and the difference matters:

* Source settings (radio, centre frequency, sample rate, buffer size)
  define the capture itself and cannot change under a running stream, so
  they are disabled while acquiring.
* Tracker settings (threshold, antenna spacing, confirm margin) are applied
  live between frames via the worker, because they are exactly the things
  an operator wants to tune while watching the effect.
"""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets


class ControlPanel(QtWidgets.QWidget):
    """Left-hand settings column."""

    startRequested = QtCore.pyqtSignal()
    stopRequested = QtCore.pyqtSignal()
    trackerParameterChanged = QtCore.pyqtSignal(str, float)
    displayOptionChanged = QtCore.pyqtSignal(str, object)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        layout.addWidget(self._build_source_group())
        layout.addWidget(self._build_tracker_group())
        layout.addWidget(self._build_display_group())

        self.start_button = QtWidgets.QPushButton("Start")
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.startRequested)
        self.stop_button.clicked.connect(self.stopRequested)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        layout.addLayout(buttons)
        layout.addStretch(1)

    # -- groups --------------------------------------------------------

    def _build_source_group(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Source")
        form = QtWidgets.QFormLayout(box)

        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.addItems(["Simulated", "FMCOMMS5 (live)", "Recorded file"])
        self.source_combo.currentIndexChanged.connect(self._sync_source_fields)
        form.addRow("Type", self.source_combo)

        self.uri_edit = QtWidgets.QLineEdit("ip:192.168.2.1")
        form.addRow("URI", self.uri_edit)

        self.file_edit = QtWidgets.QLineEdit()
        self.file_edit.setPlaceholderText("capture.npy")
        browse = QtWidgets.QPushButton("...")
        browse.setFixedWidth(30)
        browse.clicked.connect(self._browse)
        file_row = QtWidgets.QHBoxLayout()
        file_row.setContentsMargins(0, 0, 0, 0)
        file_row.addWidget(self.file_edit)
        file_row.addWidget(browse)
        wrapper = QtWidgets.QWidget()
        wrapper.setLayout(file_row)
        form.addRow("File", wrapper)

        self.drones_spin = QtWidgets.QSpinBox()
        self.drones_spin.setRange(0, 8)
        self.drones_spin.setValue(2)
        form.addRow("Sim drones", self.drones_spin)

        self.snr_spin = QtWidgets.QDoubleSpinBox()
        self.snr_spin.setRange(-10.0, 60.0)
        self.snr_spin.setValue(25.0)
        self.snr_spin.setSuffix(" dB")
        form.addRow("Sim SNR", self.snr_spin)

        self.center_spin = QtWidgets.QDoubleSpinBox()
        self.center_spin.setRange(70.0, 6000.0)
        self.center_spin.setDecimals(3)
        self.center_spin.setValue(2440.0)
        self.center_spin.setSuffix(" MHz")
        form.addRow("Centre", self.center_spin)

        self.rate_spin = QtWidgets.QDoubleSpinBox()
        self.rate_spin.setRange(0.5, 61.44)
        self.rate_spin.setDecimals(2)
        self.rate_spin.setValue(40.0)
        self.rate_spin.setSuffix(" Msps")
        form.addRow("Sample rate", self.rate_spin)

        self.buffer_combo = QtWidgets.QComboBox()
        self.buffer_combo.addItems(["512", "1024", "2048", "4096"])
        self.buffer_combo.setCurrentText("1024")
        form.addRow("Buffer", self.buffer_combo)

        self._sync_source_fields()
        return box

    def _build_tracker_group(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Tracker")
        form = QtWidgets.QFormLayout(box)

        self.threshold_spin = QtWidgets.QDoubleSpinBox()
        self.threshold_spin.setRange(3.0, 40.0)
        self.threshold_spin.setValue(12.0)
        self.threshold_spin.setSuffix(" dB")
        self.threshold_spin.valueChanged.connect(
            lambda v: self.trackerParameterChanged.emit("threshold_db", float(v))
        )
        form.addRow("Detect SNR", self.threshold_spin)

        self.spacing_spin = QtWidgets.QDoubleSpinBox()
        self.spacing_spin.setRange(0.01, 2.0)
        self.spacing_spin.setDecimals(3)
        self.spacing_spin.setSingleStep(0.005)
        self.spacing_spin.setValue(0.245)
        self.spacing_spin.setSuffix(" m")
        self.spacing_spin.setToolTip(
            "Physical N-S and E-W antenna separation. Must match the real array:\n"
            "this sets the phase-to-angle mapping and the ambiguity spacing."
        )
        self.spacing_spin.valueChanged.connect(
            lambda v: self.trackerParameterChanged.emit("antenna_spacing_m", float(v))
        )
        form.addRow("Antenna spacing", self.spacing_spin)

        self.margin_spin = QtWidgets.QDoubleSpinBox()
        self.margin_spin.setRange(1.0, 100.0)
        self.margin_spin.setValue(6.0)
        self.margin_spin.setToolTip(
            "How decisively the winning bearing must out-fit the runner-up\n"
            "before it is reported as resolved. Higher trades coverage for\n"
            "precision; ~98% of confirmations are correct at the default."
        )
        self.margin_spin.valueChanged.connect(
            lambda v: self.trackerParameterChanged.emit("confirm_margin", float(v))
        )
        form.addRow("Confirm margin", self.margin_spin)
        return box

    def _build_display_group(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Display")
        form = QtWidgets.QFormLayout(box)

        self.autorange_check = QtWidgets.QCheckBox("Auto range")
        self.autorange_check.setChecked(True)
        self.autorange_check.toggled.connect(
            lambda v: self.displayOptionChanged.emit("auto_range", bool(v))
        )
        form.addRow(self.autorange_check)

        self.range_spin = QtWidgets.QDoubleSpinBox()
        self.range_spin.setRange(10.0, 100000.0)
        self.range_spin.setValue(100.0)
        self.range_spin.setSuffix(" m")
        self.range_spin.valueChanged.connect(
            lambda v: self.displayOptionChanged.emit("max_range", float(v))
        )
        form.addRow("Max range", self.range_spin)

        self.ghosts_check = QtWidgets.QCheckBox("Show ambiguity candidates")
        self.ghosts_check.setChecked(True)
        self.ghosts_check.setToolTip(
            "Draw every bearing an unresolved track's phase permits.\n"
            "With a 2-wavelength baseline these are genuine possibilities,\n"
            "not display noise."
        )
        self.ghosts_check.toggled.connect(
            lambda v: self.displayOptionChanged.emit("show_ghosts", bool(v))
        )
        form.addRow(self.ghosts_check)
        return box

    # -- helpers -------------------------------------------------------

    def _browse(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open recorded capture", "", "NumPy capture (*.npy)"
        )
        if path:
            self.file_edit.setText(path)
            self.source_combo.setCurrentIndex(2)

    def _sync_source_fields(self) -> None:
        kind = self.source_combo.currentIndex()
        self.uri_edit.setEnabled(kind == 1)
        self.file_edit.setEnabled(kind == 2)
        self.drones_spin.setEnabled(kind == 0)
        self.snr_spin.setEnabled(kind == 0)

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        for widget in (
            self.source_combo,
            self.uri_edit,
            self.file_edit,
            self.drones_spin,
            self.snr_spin,
            self.center_spin,
            self.rate_spin,
            self.buffer_combo,
        ):
            widget.setEnabled(not running)
        if not running:
            self._sync_source_fields()

    # -- current settings ---------------------------------------------

    @property
    def source_kind(self) -> str:
        return ["simulated", "fmcomms5", "file"][self.source_combo.currentIndex()]

    @property
    def center_freq_hz(self) -> float:
        return self.center_spin.value() * 1e6

    @property
    def sample_rate(self) -> float:
        return self.rate_spin.value() * 1e6

    @property
    def buffer_size(self) -> int:
        return int(self.buffer_combo.currentText())
