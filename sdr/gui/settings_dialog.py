"""Settings dialog behind the gear icon.

Everything the console does not surface on the main face: which radio to
use, the capture parameters, the array geometry, and where the sensor is.
"""

from __future__ import annotations

from PyQt6 import QtWidgets

SOURCE_LABELS = [("Simulated", "simulated"), ("FMCOMMS5 (live)", "fmcomms5"), ("Recorded file", "file")]


class SettingsDialog(QtWidgets.QDialog):
    """Edits a copy of the console's settings dict."""

    def __init__(self, settings: dict, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._build_source_group(settings))
        layout.addWidget(self._build_receiver_group(settings))
        layout.addWidget(self._build_site_group(settings))

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- groups --------------------------------------------------------

    def _build_source_group(self, settings: dict) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Source")
        form = QtWidgets.QFormLayout(box)

        self.source = QtWidgets.QComboBox()
        for label, _ in SOURCE_LABELS:
            self.source.addItem(label)
        current = [key for _, key in SOURCE_LABELS].index(settings["source"])
        self.source.setCurrentIndex(current)
        form.addRow("Type", self.source)

        self.uri = QtWidgets.QLineEdit(settings["uri"])
        form.addRow("Device URI", self.uri)

        self.file = QtWidgets.QLineEdit(settings["file"])
        browse = QtWidgets.QPushButton("…")
        browse.setFixedWidth(32)
        browse.clicked.connect(self._browse)
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.file)
        row.addWidget(browse)
        wrapper = QtWidgets.QWidget()
        wrapper.setLayout(row)
        form.addRow("Capture file", wrapper)

        self.drones = QtWidgets.QSpinBox()
        self.drones.setRange(0, 8)
        self.drones.setValue(int(settings["drones"]))
        form.addRow("Simulated drones", self.drones)

        self.snr = QtWidgets.QDoubleSpinBox()
        self.snr.setRange(-10.0, 60.0)
        self.snr.setSuffix(" dB")
        self.snr.setValue(settings["snr_db"])
        form.addRow("Simulated SNR", self.snr)
        return box

    def _build_receiver_group(self, settings: dict) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Receiver and array")
        form = QtWidgets.QFormLayout(box)

        self.rate = QtWidgets.QDoubleSpinBox()
        self.rate.setRange(0.5, 61.44)
        self.rate.setDecimals(2)
        self.rate.setSuffix(" Msps")
        self.rate.setValue(settings["sample_rate"] / 1e6)
        form.addRow("Sample rate", self.rate)

        self.buffer = QtWidgets.QComboBox()
        self.buffer.addItems(["512", "1024", "2048", "4096"])
        self.buffer.setCurrentText(str(int(settings["buffer_size"])))
        form.addRow("Buffer", self.buffer)

        self.threshold = QtWidgets.QDoubleSpinBox()
        self.threshold.setRange(3.0, 40.0)
        self.threshold.setSuffix(" dB")
        self.threshold.setValue(settings["threshold_db"])
        form.addRow("Detection SNR", self.threshold)

        self.spacing = QtWidgets.QDoubleSpinBox()
        self.spacing.setRange(0.01, 2.0)
        self.spacing.setDecimals(3)
        self.spacing.setSingleStep(0.005)
        self.spacing.setSuffix(" m")
        self.spacing.setValue(settings["antenna_spacing_m"])
        self.spacing.setToolTip(
            "Physical N–S and E–W antenna separation. Must match the real\n"
            "array: it sets the phase-to-angle mapping and the spacing of\n"
            "the ambiguities."
        )
        form.addRow("Antenna spacing", self.spacing)

        self.margin = QtWidgets.QDoubleSpinBox()
        self.margin.setRange(1.0, 100.0)
        self.margin.setValue(settings["confirm_margin"])
        self.margin.setToolTip(
            "How decisively the winning bearing must out-fit the runner-up\n"
            "before it counts as resolved. About 98% of confirmations are\n"
            "correct at the default of 6."
        )
        form.addRow("Confirm margin", self.margin)
        return box

    def _build_site_group(self, settings: dict) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Site")
        form = QtWidgets.QFormLayout(box)

        self.latitude = QtWidgets.QDoubleSpinBox()
        self.latitude.setRange(-85.0, 85.0)
        self.latitude.setDecimals(6)
        self.latitude.setValue(settings["latitude"])
        form.addRow("Latitude", self.latitude)

        self.longitude = QtWidgets.QDoubleSpinBox()
        self.longitude.setRange(-180.0, 180.0)
        self.longitude.setDecimals(6)
        self.longitude.setValue(settings["longitude"])
        form.addRow("Longitude", self.longitude)

        self.inner_ring = QtWidgets.QDoubleSpinBox()
        self.inner_ring.setRange(50.0, 50000.0)
        self.inner_ring.setSuffix(" m")
        self.inner_ring.setValue(settings["inner_ring_m"])
        form.addRow("Inner ring", self.inner_ring)

        self.outer_ring = QtWidgets.QDoubleSpinBox()
        self.outer_ring.setRange(100.0, 100000.0)
        self.outer_ring.setSuffix(" m")
        self.outer_ring.setValue(settings["outer_ring_m"])
        form.addRow("Outer ring", self.outer_ring)
        return box

    def _browse(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open recorded capture", "", "NumPy capture (*.npy)"
        )
        if path:
            self.file.setText(path)
            self.source.setCurrentIndex(2)

    # -- result --------------------------------------------------------

    def values(self) -> dict:
        return {
            "source": SOURCE_LABELS[self.source.currentIndex()][1],
            "uri": self.uri.text().strip(),
            "file": self.file.text().strip(),
            "drones": self.drones.value(),
            "snr_db": self.snr.value(),
            "sample_rate": self.rate.value() * 1e6,
            "buffer_size": int(self.buffer.currentText()),
            "threshold_db": self.threshold.value(),
            "antenna_spacing_m": self.spacing.value(),
            "confirm_margin": self.margin.value(),
            "latitude": self.latitude.value(),
            "longitude": self.longitude.value(),
            "inner_ring_m": self.inner_ring.value(),
            "outer_ring_m": self.outer_ring.value(),
        }
