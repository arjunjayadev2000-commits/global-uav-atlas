"""Live spectrum and waterfall.

Shows what the detector is actually working from: the combined 4-channel
power spectrum, the adaptive threshold the tracker derived from it, and a
rolling waterfall in which a hopping emitter is immediately recognisable as
scattered dashes rather than a continuous line.

The frequency axis covers the whole complex passband, LO +/- fs/2 -- the
half below the LO is real signal, not a mirror, and hops land there just as
often.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtWidgets

WATERFALL_ROWS = 160


class SpectrumWidget(QtWidgets.QWidget):
    """Spectrum plot above a rolling waterfall, sharing a frequency axis."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True, background=(10, 16, 20), foreground=(150, 180, 190))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._plot = pg.PlotWidget()
        self._plot.setLabel("left", "Power", units="dBm")
        self._plot.setLabel("bottom", "Frequency", units="Hz")
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._curve = self._plot.plot(pen=pg.mkPen((80, 200, 240), width=1))
        self._threshold = pg.InfiniteLine(
            angle=0, pen=pg.mkPen((240, 120, 100), width=1, style=pg.QtCore.Qt.PenStyle.DashLine)
        )
        self._plot.addItem(self._threshold)
        layout.addWidget(self._plot, stretch=3)

        self._waterfall_plot = pg.PlotWidget()
        self._waterfall_plot.setLabel("left", "History")
        self._waterfall_plot.setLabel("bottom", "Frequency", units="Hz")
        self._waterfall_plot.setXLink(self._plot)
        self._image = pg.ImageItem()
        self._waterfall_plot.addItem(self._image)
        self._image.setColorMap(pg.colormap.get("inferno"))
        view = self._waterfall_plot.getViewBox()
        view.invertY(True)
        # Pin the history axis: left to autorange it tracks the image's raw
        # pixel extent instead of the row count and the waterfall collapses
        # into a sliver at the top.
        view.setYRange(0, WATERFALL_ROWS, padding=0)
        view.setMouseEnabled(x=True, y=False)
        layout.addWidget(self._waterfall_plot, stretch=2)

        self._history: np.ndarray | None = None
        self._frequencies: np.ndarray | None = None

    def update_spectrum(
        self, spectrum_db: np.ndarray, frequencies_hz: np.ndarray, threshold_db: float
    ) -> None:
        self._curve.setData(frequencies_hz, spectrum_db)
        self._threshold.setValue(threshold_db)

        if self._history is None or self._history.shape[1] != spectrum_db.size:
            self._history = np.full((WATERFALL_ROWS, spectrum_db.size), float(spectrum_db.min()))
            self._frequencies = frequencies_hz

        self._history = np.roll(self._history, 1, axis=0)
        self._history[0] = spectrum_db
        # Clip the floor so the colour map spends its range on signal
        # rather than on the noise it sits in.
        floor = float(np.percentile(self._history, 40))
        self._image.setImage(
            self._history.T, autoLevels=False, levels=(floor, float(self._history.max()))
        )
        # setImage resets the item transform, so the frequency mapping has
        # to be reapplied after it rather than once at construction.
        span = float(frequencies_hz[-1] - frequencies_hz[0])
        self._image.setRect(
            pg.QtCore.QRectF(float(frequencies_hz[0]), 0.0, span, float(WATERFALL_ROWS))
        )

    def clear(self) -> None:
        self._history = None
        self._curve.setData([], [])
