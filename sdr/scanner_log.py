"""Scanner CSV logs: parsing, integrity checking and amplitude direction finding.

This reads the per-detection logs a channelised scanner produces -- one row
per detection with a frequency, a bandwidth, a classification and a received
power for each of four directional antennas (N, E, S, W) -- and turns them
into emitters with a bearing and a range.

Direction finding here is *amplitude comparison*, not the phase
interferometry in :mod:`sdr.multi_drone_tracker`. A scanner log carries no
phase, only power, so the bearing comes from how the four antenna patterns
weight the same signal. The estimator is the standard quadrature form:

    bearing = atan2(P_E - P_W, P_N - P_S)      with powers in dB

Opposite pairs are differenced because a Gaussian-ish beam is quadratic in
angle in dB, which makes the difference of two opposing beams close to
linear in the off-boresight angle. It is coarse -- expect tens of degrees,
not the sub-degree of a phase array -- but it needs no coherence.

The catch, and the reason :class:`LogIntegrity` exists: that formula is only
meaningful if all four powers were measured *at the same instant*. Real
scanner logs frequently violate this. They sample antennas in pairs, hold
the last value between updates, or emit a decayed ramp instead of a fresh
measurement. Subtracting a held S value from a live N value yields a number
that looks like a bearing and means nothing. Every log is therefore screened
before any bearing is reported, and a log that fails the screen produces
emitters with ``bearing_deg = None`` rather than a plausible-looking guess.
"""

from __future__ import annotations

import csv
import math
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

#: Antenna boresights, in the channel order the logs use.
BORESIGHTS = (0.0, 90.0, 180.0, 270.0)
ANTENNA_NAMES = ("N", "E", "S", "W")

#: Free-space path loss at 1 m for 2.44 GHz is ~40.2 dB, so a 20 dBm EIRP
#: emitter presents about -20 dBm at one metre. Both are assumptions: a real
#: deployment should re-derive them from a reference emitter at a known range.
DEFAULT_REFERENCE_DBM = -20.2
DEFAULT_PATH_LOSS_EXPONENT = 2.2


@dataclass
class Detection:
    """One scanner detection."""

    timestamp: datetime
    cycle: int
    freq_mhz: float
    bandwidth_mhz: float
    signal_type: str
    #: Received power per antenna in dBm; None where that antenna did not report.
    powers: list[float | None]

    @property
    def peak_dbm(self) -> float:
        return max(v for v in self.powers if v is not None)

    @property
    def antennas_reporting(self) -> int:
        return sum(v is not None for v in self.powers)


@dataclass
class LogIntegrity:
    """Whether a log's per-antenna powers can support direction finding."""

    rows: int
    simultaneous_fraction: float
    single_channel_change_fraction: float
    quantised_step_db: float | None
    antenna_detections: list[int]
    problems: list[str] = field(default_factory=list)

    @property
    def bearings_trustworthy(self) -> bool:
        return not self.problems

    def report(self) -> str:
        lines = [
            f"rows                     {self.rows}",
            f"all four antennas at once {self.simultaneous_fraction * 100:.1f}%",
            f"only one channel moved    {self.single_channel_change_fraction * 100:.1f}%",
            "detections per antenna    "
            + "  ".join(
                f"{n}={c}"
                for n, c in zip(ANTENNA_NAMES, self.antenna_detections, strict=True)
            ),
        ]
        if self.quantised_step_db:
            lines.append(f"dominant step size        {self.quantised_step_db:.1f} dB")
        if self.problems:
            lines.append("BEARINGS SUPPRESSED:")
            lines.extend(f"  - {p}" for p in self.problems)
        else:
            lines.append("integrity OK - bearings computed")
        return "\n".join(lines)


@dataclass
class Emitter:
    """A signal source grouped from many detections."""

    freq_min_mhz: float
    freq_max_mhz: float
    bandwidth_mhz: float
    detections: int
    peak_dbm: float
    signal_types: list[str]
    hop_channels: list[int]
    antenna_medians: list[float | None]
    first_seen: datetime
    last_seen: datetime
    #: None when the log failed its integrity screen, or when the antennas
    #: needed for the quadrature difference never reported.
    bearing_deg: float | None = None
    bearing_note: str = ""

    @property
    def is_wideband(self) -> bool:
        return self.bandwidth_mhz > 5.0

    @property
    def is_hopping(self) -> bool:
        return len(self.hop_channels) >= 4

    def range_m(
        self,
        path_loss_exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
        reference_dbm: float = DEFAULT_REFERENCE_DBM,
    ) -> float:
        return 10 ** ((reference_dbm - self.peak_dbm) / (10 * path_loss_exponent))

    def range_bracket_m(self) -> tuple[float, float]:
        """Range under open-ground and urban-clutter propagation.

        Reported as a bracket because the exponent is the dominant
        uncertainty and a single number would overstate the precision.
        """
        return self.range_m(2.7), self.range_m(2.0)


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------


def load_detections(path: str | Path) -> list[Detection]:
    """Read a scanner CSV into detections."""
    out: list[Detection] = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            powers = [
                float(row[f"ch{i}_pwr_dbm"]) if row.get(f"ch{i}_pwr_dbm") else None
                for i in range(4)
            ]
            if all(p is None for p in powers):
                continue
            out.append(
                Detection(
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    cycle=int(row.get("cycle", 0) or 0),
                    freq_mhz=float(row["freq_mhz"]),
                    bandwidth_mhz=float(row["bw_mhz"]),
                    signal_type=row.get("type", "UNKNOWN"),
                    powers=powers,
                )
            )
    return out


# ----------------------------------------------------------------------
# Integrity screening
# ----------------------------------------------------------------------


def check_integrity(
    detections: list[Detection],
    min_simultaneous: float = 0.30,
    max_single_change: float = 0.45,
    min_antenna_share: float = 0.05,
) -> LogIntegrity:
    """Decide whether a log's powers are real simultaneous measurements.

    Three independent failure modes are screened, because each one alone is
    enough to make a quadrature bearing meaningless:

    * too few rows carrying all four antennas, so opposite pairs are never
      differenced against a value measured at the same moment;
    * consecutive samples in which only one channel moves, the signature of
      a sample-and-hold rather than four live measurements;
    * an antenna that almost never reports, which is a broken or
      intermittent receive chain rather than a directional null.
    """
    problems: list[str] = []
    rows = len(detections)
    if rows == 0:
        return LogIntegrity(0, 0.0, 0.0, None, [0, 0, 0, 0], ["log is empty"])

    simultaneous = sum(1 for d in detections if d.antennas_reporting == 4) / rows
    counts = [sum(1 for d in detections if d.powers[i] is not None) for i in range(4)]

    # Walk consecutive detections of the same emitter and watch how the
    # channel values move relative to each other.
    both = single = frozen = 0
    steps: Counter[float] = Counter()
    previous: tuple[float, float, float] | None = None
    for det in sorted(detections, key=lambda d: (round(d.freq_mhz, 1), d.timestamp)):
        a, b = det.powers[0], det.powers[1]
        if a is None or b is None:
            previous = None
            continue
        if previous is not None and abs(det.freq_mhz - previous[0]) < 0.05:
            moved_a = round(abs(a - previous[1]), 2)
            moved_b = round(abs(b - previous[2]), 2)
            if moved_a > 0 and moved_b > 0:
                both += 1
            elif moved_a > 0 or moved_b > 0:
                single += 1
                steps[max(moved_a, moved_b)] += 1
            else:
                frozen += 1
        previous = (det.freq_mhz, a, b)

    comparisons = both + single + frozen
    single_fraction = single / comparisons if comparisons else 0.0
    dominant_step = steps.most_common(1)[0][0] if steps else None

    if simultaneous < min_simultaneous:
        problems.append(
            f"only {simultaneous * 100:.1f}% of rows sample all four antennas together "
            f"(need {min_simultaneous * 100:.0f}%); opposite pairs are not simultaneous"
        )
    if single_fraction > max_single_change:
        problems.append(
            f"{single_fraction * 100:.0f}% of consecutive samples move only one channel"
            + (f", mostly by {dominant_step:.1f} dB" if dominant_step else "")
            + " - values are held and ramped, not independently measured"
        )
    for name, count in zip(ANTENNA_NAMES, counts, strict=True):
        if count < rows * min_antenna_share:
            problems.append(
                f"antenna {name} reported on only {count} of {rows} detections "
                f"({count * 100 / rows:.1f}%) - receive chain looks dead or intermittent"
            )

    return LogIntegrity(rows, simultaneous, single_fraction, dominant_step, counts, problems)


# ----------------------------------------------------------------------
# Direction finding
# ----------------------------------------------------------------------


def quadrature_bearing(powers_db: list[float | None]) -> float | None:
    """Bearing from four antenna powers by quadrature amplitude comparison.

    ``atan2(E - W, N - S)`` with powers in dB. Returns None when either
    opposite pair is incomplete -- half a difference carries no direction.
    """
    north, east, south, west = powers_db
    if north is None or south is None or east is None or west is None:
        return None
    delta_ns = north - south
    delta_ew = east - west
    if delta_ns == 0 and delta_ew == 0:
        return None
    return (math.degrees(math.atan2(delta_ew, delta_ns)) + 360) % 360


def _circular_mean(bearings: list[float]) -> tuple[float, float]:
    x = sum(math.sin(math.radians(b)) for b in bearings)
    y = sum(math.cos(math.radians(b)) for b in bearings)
    return (math.degrees(math.atan2(x, y)) + 360) % 360, math.hypot(x, y) / len(bearings)


# ----------------------------------------------------------------------
# Emitter grouping
# ----------------------------------------------------------------------


def group_emitters(
    detections: list[Detection],
    integrity: LogIntegrity | None = None,
    freq_tolerance_mhz: float = 2.0,
    min_detections: int = 3,
) -> list[Emitter]:
    """Cluster detections into emitters by frequency proximity.

    Wideband and narrowband signals are clustered separately: a hopping
    control link and a video downlink can overlap in frequency while being
    entirely different emitters, and merging them by frequency alone
    produces one meaningless blob.
    """
    if integrity is None:
        integrity = check_integrity(detections)

    emitters: list[Emitter] = []
    for wideband in (True, False):
        subset = [d for d in detections if (d.bandwidth_mhz > 5.0) is wideband]
        if not subset:
            continue
        clusters: list[list[Detection]] = []
        for det in sorted(subset, key=lambda d: d.freq_mhz):
            if clusters and det.freq_mhz - clusters[-1][-1].freq_mhz <= freq_tolerance_mhz:
                clusters[-1].append(det)
            else:
                clusters.append([det])
        for cluster in clusters:
            if len(cluster) < min_detections:
                continue
            emitters.append(_build_emitter(cluster, integrity))
    emitters.sort(key=lambda e: -e.peak_dbm)
    return emitters


def _build_emitter(cluster: list[Detection], integrity: LogIntegrity) -> Emitter:
    medians: list[float | None] = []
    for i in range(4):
        values = [d.powers[i] for d in cluster if d.powers[i] is not None]
        medians.append(statistics.median(values) if values else None)

    bearing: float | None = None
    note = ""
    if not integrity.bearings_trustworthy:
        note = "suppressed: log failed integrity screen"
    else:
        # Only rows carrying all four antennas can be differenced honestly.
        per_row = [
            b
            for b in (quadrature_bearing(d.powers) for d in cluster if d.antennas_reporting == 4)
            if b is not None
        ]
        if per_row:
            bearing, concentration = _circular_mean(per_row)
            note = f"{len(per_row)} four-antenna samples, concentration {concentration:.2f}"
            if concentration < 0.5:
                bearing, note = None, (
                    f"suppressed: bearings inconsistent across {len(per_row)} samples "
                    f"(concentration {concentration:.2f})"
                )
        else:
            note = "suppressed: no detection sampled all four antennas"

    return Emitter(
        freq_min_mhz=min(d.freq_mhz for d in cluster),
        freq_max_mhz=max(d.freq_mhz for d in cluster),
        bandwidth_mhz=statistics.median([d.bandwidth_mhz for d in cluster]),
        detections=len(cluster),
        peak_dbm=max(d.peak_dbm for d in cluster),
        signal_types=sorted({d.signal_type for d in cluster}),
        hop_channels=sorted({round(d.freq_mhz) for d in cluster}),
        antenna_medians=medians,
        first_seen=min(d.timestamp for d in cluster),
        last_seen=max(d.timestamp for d in cluster),
        bearing_deg=bearing,
        bearing_note=note,
    )


def analyse(path: str | Path) -> tuple[LogIntegrity, list[Emitter]]:
    """Load a scanner log, screen it, and return its emitters."""
    detections = load_detections(path)
    integrity = check_integrity(detections)
    return integrity, group_emitters(detections, integrity)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def _format(integrity: LogIntegrity, emitters: list[Emitter], drones_only: bool) -> str:
    lines = ["INTEGRITY", integrity.report(), "", "EMITTERS"]
    shown = [e for e in emitters if e.is_wideband or e.is_hopping] if drones_only else emitters
    if not shown:
        lines.append("  none")
    header = (
        f"  {'freq MHz':>17} {'bw':>6} {'n':>5} {'peak dBm':>9} "
        f"{'range m':>13} {'bearing':>9}  note"
    )
    lines.append(header)
    for e in shown:
        lo, hi = e.range_bracket_m()
        bearing = f"{e.bearing_deg:8.0f}°" if e.bearing_deg is not None else "       --"
        lines.append(
            f"  {e.freq_min_mhz:7.1f}-{e.freq_max_mhz:<9.1f} {e.bandwidth_mhz:6.2f} "
            f"{e.detections:5d} {e.peak_dbm:9.1f} {lo:6.0f}-{hi:<6.0f} {bearing}  {e.bearing_note}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Analyse a scanner signal log")
    parser.add_argument("path", help="scanner CSV")
    parser.add_argument(
        "--all", action="store_true", help="show every emitter, not just drone-like ones"
    )
    args = parser.parse_args(argv)

    integrity, emitters = analyse(args.path)
    print(_format(integrity, emitters, drones_only=not args.all))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
