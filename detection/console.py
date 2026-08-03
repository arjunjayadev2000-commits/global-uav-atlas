#!/usr/bin/env python3
"""Launch the UAV-DET tactical detection console.

Two ways to run it:

    # Demo mode — no camera, no model weights, nothing to install beyond deps.
    python detection/console.py --simulate

    # Live mode — real webcam through the trained YOLO model.
    python detection/console.py --source 0

Then open http://127.0.0.1:8000 in a browser. Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python detection/console.py` to work from a clean checkout without
# requiring `pip install -e .` or PYTHONPATH fiddling — the quick-start
# instructions tell a non-coder to run exactly that command.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from detection.config import DetectorConfig
from detection.server import build


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="detection/console.py",
        description="Serve the UAV-DET tactical detection console.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="run against a synthetic feed: no camera and no model weights required",
    )
    parser.add_argument(
        "--source", default="0",
        help="camera index (0, 1, ...) or a video file / RTSP URL (default: 0)",
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address; use 0.0.0.0 to reach it from another machine")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--input-size", type=int, default=416, choices=(320, 416, 512, 608))
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--backend", default="auto", choices=("auto", "cuda", "cpu"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    config = DetectorConfig(
        input_size=args.input_size,
        confidence_threshold=args.confidence,
        backend=args.backend,
    )

    try:
        app, engine = build(source=args.source, simulate=args.simulate, config=config)
    except FileNotFoundError as exc:
        # Missing weights is the single most common first-run failure, so it
        # gets a pointed message rather than a traceback.
        print(f"\n[!] {exc}\n", file=sys.stderr)
        print("    Run with --simulate to try the console without a model.\n", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"\n[!] {exc}\n", file=sys.stderr)
        print("    Run with --simulate to try the console without a camera.\n", file=sys.stderr)
        return 2

    engine.start()
    mode = "SIMULATION" if args.simulate else "LIVE"
    print(f"\n  UAV-DET console [{mode}]  ->  http://{args.host}:{args.port}\n")
    print("  Ctrl+C to stop.\n")

    try:
        # threaded=True so the MJPEG stream doesn't monopolise the server.
        app.run(host=args.host, port=args.port, threaded=True, debug=False)
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
