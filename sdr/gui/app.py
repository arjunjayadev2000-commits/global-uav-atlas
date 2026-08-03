"""Application entry point.

    python -m sdr.gui.app                       # simulated, starts immediately
    python -m sdr.gui.app --source fmcomms5     # live radio
    python -m sdr.gui.app --file capture.npy    # replay a recording
"""

from __future__ import annotations

import argparse
import sys

from PyQt6 import QtWidgets

from sdr.gui.mainwindow import DARK_STYLESHEET, MainWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi-drone SDR tracker")
    parser.add_argument(
        "--source",
        choices=["simulated", "fmcomms5", "file"],
        default="simulated",
        help="capture source to preselect (default: simulated)",
    )
    parser.add_argument("--uri", default="ip:192.168.2.1", help="FMCOMMS5 device URI")
    parser.add_argument("--file", dest="path", help="recorded .npy capture to replay")
    parser.add_argument("--center", type=float, default=2440.0, help="centre frequency in MHz")
    parser.add_argument("--rate", type=float, default=40.0, help="sample rate in Msps")
    parser.add_argument(
        "--spacing", type=float, default=0.245, help="antenna pair separation in metres"
    )
    parser.add_argument("--drones", type=int, default=2, help="simulated drone count")
    parser.add_argument(
        "--no-autostart", action="store_true", help="open idle instead of acquiring immediately"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    app = QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName("Multi-Drone SDR Tracker")
    app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()
    controls = window.controls
    controls.source_combo.setCurrentIndex(
        {"simulated": 0, "fmcomms5": 1, "file": 2}[args.source]
    )
    controls.uri_edit.setText(args.uri)
    if args.path:
        controls.file_edit.setText(args.path)
        controls.source_combo.setCurrentIndex(2)
    controls.center_spin.setValue(args.center)
    controls.rate_spin.setValue(args.rate)
    controls.spacing_spin.setValue(args.spacing)
    controls.drones_spin.setValue(args.drones)

    window.show()
    if not args.no_autostart:
        window.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
