"""Track table.

One row per live track. The margin column is the important one and is
shown rather than hidden behind the confirmed/unresolved flag: it is the
ratio by which the winning direction out-fits the best distinct
alternative, so an operator can see a track firming up hop by hop instead
of only seeing the moment it crosses the threshold.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime

from PyQt6 import QtCore, QtGui, QtWidgets

from sdr.multi_drone_tracker import Detection

COLUMNS = [
    ("Track", 58),
    ("Freq (GHz)", 92),
    ("Bearing", 78),
    ("State", 96),
    ("Margin", 72),
    ("Range (m)", 86),
    ("RSSI (dBm)", 88),
    ("Hops", 54),
]

CONFIRMED_BG = QtGui.QColor(20, 60, 48)
AMBIGUOUS_BG = QtGui.QColor(66, 50, 16)


class TrackTable(QtWidgets.QTableWidget):
    """Live view of every track, newest state per track."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(0, len(COLUMNS), parent)
        self.setHorizontalHeaderLabels([name for name, _ in COLUMNS])
        for index, (_, width) in enumerate(COLUMNS):
            self.setColumnWidth(index, width)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(False)

        self._rows: dict[int, int] = {}
        self._latest: dict[int, Detection] = {}
        self._log: list[tuple[str, Detection]] = []

    # -- updates -------------------------------------------------------

    def update_detections(self, detections: list[Detection]) -> None:
        stamp = datetime.now(UTC).isoformat(timespec="milliseconds")
        for det in detections:
            self._latest[det.track_id] = det
            self._log.append((stamp, det))
        self._rebuild()

    def prune(self, live_track_ids: set[int]) -> None:
        for tid in list(self._latest):
            if tid not in live_track_ids:
                del self._latest[tid]
        self._rebuild()

    def clear_tracks(self) -> None:
        self._latest.clear()
        self._rows.clear()
        self.setRowCount(0)

    def _rebuild(self) -> None:
        ordered = sorted(self._latest.values(), key=lambda d: d.track_id)
        self.setRowCount(len(ordered))
        for row, det in enumerate(ordered):
            confirmed = not det.bearing_ambiguous
            margin = "inf" if det.ambiguity_margin == float("inf") else f"{det.ambiguity_margin:.1f}"
            values = [
                f"T{det.track_id}",
                f"{det.frequency_ghz:.4f}",
                f"{det.bearing_degrees:.2f}°",
                "resolved" if confirmed else "unresolved",
                margin,
                f"{det.distance_meters:.1f}",
                f"{det.signal_strength_dbm:.1f}",
                str(det.hops_observed),
            ]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setBackground(CONFIRMED_BG if confirmed else AMBIGUOUS_BG)
                if column in (1, 2, 4, 5, 6, 7):
                    item.setTextAlignment(
                        QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
                    )
                self.setItem(row, column, item)

    # -- export --------------------------------------------------------

    @property
    def logged_rows(self) -> int:
        return len(self._log)

    def export_csv(self, path: str) -> int:
        """Write every detection seen so far. Returns the row count."""
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "timestamp_utc",
                    "track_id",
                    "frequency_ghz",
                    "bearing_deg",
                    "bearing_resolved",
                    "ambiguity_margin",
                    "range_m",
                    "rssi_dbm",
                    "hops_observed",
                    "candidate_bearings_deg",
                ]
            )
            for stamp, det in self._log:
                writer.writerow(
                    [
                        stamp,
                        det.track_id,
                        f"{det.frequency_ghz:.6f}",
                        f"{det.bearing_degrees:.3f}",
                        int(not det.bearing_ambiguous),
                        det.ambiguity_margin,
                        f"{det.distance_meters:.3f}",
                        f"{det.signal_strength_dbm:.2f}",
                        det.hops_observed,
                        " ".join(f"{b:.2f}" for b in det.candidate_bearings),
                    ]
                )
        return len(self._log)
