"""Application entry point.

    python -m sdr.gui.app                       # simulated, starts immediately
    python -m sdr.gui.app --source fmcomms5     # live radio
    python -m sdr.gui.app --file capture.npy    # replay a recording
"""

from __future__ import annotations

import argparse
import sys

from PyQt6 import QtWidgets

from sdr.gui import theme
from sdr.gui.mainwindow import MainWindow


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
    parser.add_argument("--rate", type=float, default=40.0, help="sample rate in Msps")
    parser.add_argument(
        "--spacing", type=float, default=0.245, help="antenna pair separation in metres"
    )
    parser.add_argument("--drones", type=int, default=3, help="simulated drone count")
    parser.add_argument("--lat", type=float, default=30.7333, help="sensor latitude")
    parser.add_argument("--lon", type=float, default=76.7794, help="sensor longitude")
    parser.add_argument(
        "--no-tiles", action="store_true", help="skip map tile fetching and use the offline grid"
    )
    parser.add_argument(
        "--no-autostart", action="store_true", help="open idle instead of acquiring immediately"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    app = QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName("Kharga Kalateer Drone Detector")
    app.setStyleSheet(theme.STYLESHEET)

    window = MainWindow()
    window.settings.update(
        {
            "source": args.source,
            "uri": args.uri,
            "file": args.path or "",
            "drones": args.drones,
            "sample_rate": args.rate * 1e6,
            "antenna_spacing_m": args.spacing,
            "latitude": args.lat,
            "longitude": args.lon,
        }
    )
    if args.path:
        window.settings["source"] = "file"
    window.map_view.set_sensor_position(args.lat, args.lon)
    if args.no_tiles:
        window.map_view.loader.enabled = False

    window.show()
    if not args.no_autostart:
        window.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
