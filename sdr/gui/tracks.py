"""Threat log: one row per live contact.

Columns mirror the operator console -- frequency, power, bearing, device --
with the ambiguity margin appended, because the margin is what says whether
the bearing can be acted on. It is the ratio by which the winning direction
out-fits the best distinct alternative, so a contact can be watched firming
up hop by hop rather than only at the moment it crosses the threshold.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime

from PyQt6 import QtCore, QtGui, QtWidgets

from sdr.gui import theme
from sdr.multi_drone_tracker import Detection

COLUMNS = [
    ("Freq MHz", 82),
    ("Power dbm", 84),
    ("Bearing", 78),
    ("Margin", 64),
    ("Device", 90),
]

RESOLVED_BG = QtGui.QColor(16, 46, 34)
UNRESOLVED_BG = QtGui.QColor(52, 40, 12)


def classify_band(frequency_ghz: float) -> str:
    """Coarse band label.

    This is a band label, not a device identification: nothing in the
    tracker fingerprints airframes or protocols, so claiming a model here
    would be invention. Anything outside the common control bands is
    reported as unknown rather than guessed at.
    """
    if 2.35 <= frequency_ghz <= 2.55:
        return "2.4G"
    if 5.10 <= frequency_ghz <= 5.95:
        return "5.8G"
    if 0.90 <= frequency_ghz <= 0.94:
        return "900M"
    return "unknown"


class ThreatLogTable(QtWidgets.QTableWidget):
    """Live contact list, newest state per track."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(0, len(COLUMNS), parent)
        self.setHorizontalHeaderLabels([name for name, _ in COLUMNS])
        for index, (_, width) in enumerate(COLUMNS):
            self.setColumnWidth(index, width)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setHighlightSections(False)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(True)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)

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
        removed = [tid for tid in self._latest if tid not in live_track_ids]
        for tid in removed:
            del self._latest[tid]
        if removed:
            self._rebuild()

    def clear_tracks(self) -> None:
        self._latest.clear()
        self.setRowCount(0)

    def reset(self) -> None:
        self.clear_tracks()
        self._log.clear()

    @property
    def contacts(self) -> list[Detection]:
        return sorted(self._latest.values(), key=lambda d: d.track_id)

    def priority_contact(self) -> Detection | None:
        """Strongest resolved contact, else the strongest of any state."""
        if not self._latest:
            return None
        resolved = [d for d in self._latest.values() if not d.bearing_ambiguous]
        pool = resolved or list(self._latest.values())
        return max(pool, key=lambda d: d.signal_strength_dbm)

    def _rebuild(self) -> None:
        ordered = self.contacts
        self.setRowCount(len(ordered))
        for row, det in enumerate(ordered):
            resolved = not det.bearing_ambiguous
            margin = (
                "inf" if det.ambiguity_margin == float("inf") else f"{det.ambiguity_margin:.1f}"
            )
            values = [
                f"{det.frequency_ghz * 1000:.1f}",
                f"{det.signal_strength_dbm:.1f}",
                f"{det.bearing_degrees:.1f}°" + ("" if resolved else " ?"),
                margin,
                classify_band(det.frequency_ghz),
            ]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setBackground(RESOLVED_BG if resolved else UNRESOLVED_BG)
                item.setForeground(theme.TEXT if resolved else theme.GOLD)
                if column != 4:
                    item.setTextAlignment(
                        int(
                            QtCore.Qt.AlignmentFlag.AlignRight
                            | QtCore.Qt.AlignmentFlag.AlignVCenter
                        )
                    )
                if column == 0:
                    item.setToolTip(
                        f"Track T{det.track_id}\n"
                        f"{'resolved' if resolved else 'bearing unresolved'}\n"
                        f"hops observed: {det.hops_observed}\n"
                        f"candidate bearings: "
                        f"{', '.join(f'{b:.0f}°' for b in det.candidate_bearings) or 'n/a'}"
                    )
                self.setItem(row, column, item)

    # -- export --------------------------------------------------------

    @property
    def logged_rows(self) -> int:
        return len(self._log)

    def export_csv(self, path: str) -> int:
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "timestamp_utc",
                    "track_id",
                    "frequency_mhz",
                    "power_dbm",
                    "bearing_deg",
                    "bearing_resolved",
                    "ambiguity_margin",
                    "band",
                    "range_m",
                    "hops_observed",
                    "candidate_bearings_deg",
                ]
            )
            for stamp, det in self._log:
                writer.writerow(
                    [
                        stamp,
                        det.track_id,
                        f"{det.frequency_ghz * 1000:.3f}",
                        f"{det.signal_strength_dbm:.2f}",
                        f"{det.bearing_degrees:.3f}",
                        int(not det.bearing_ambiguous),
                        det.ambiguity_margin,
                        classify_band(det.frequency_ghz),
                        f"{det.distance_meters:.3f}",
                        det.hops_observed,
                        " ".join(f"{b:.2f}" for b in det.candidate_bearings),
                    ]
                )
        return len(self._log)
