"""Tests for scanner-log parsing, integrity screening and amplitude DF.

The important pair of tests here are the two synthetic logs. One is clean --
four antennas measured together, independent noise -- and proves the
quadrature estimator recovers a known bearing. The other reproduces the
sample-and-hold artifact seen in real scanner output and proves the screen
catches it and suppresses the bearing instead of reporting a plausible
looking number. Together they show the failure is detected, not merely
survived.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta

import pytest

from sdr.scanner_log import (
    BORESIGHTS,
    Detection,
    analyse,
    check_integrity,
    group_emitters,
    load_detections,
    quadrature_bearing,
)

# ----------------------------------------------------------------------
# Synthetic log builders
# ----------------------------------------------------------------------


def _antenna_power(bearing_deg: float, boresight_deg: float, peak_dbm: float,
                   beamwidth_deg: float = 90.0) -> float:
    """Gaussian antenna pattern, in dB relative to the emitter's level."""
    off = (bearing_deg - boresight_deg + 180) % 360 - 180
    return peak_dbm - 12.04 * (off / beamwidth_deg) ** 2


def write_clean_log(path, bearing_deg: float, rows: int = 200, peak_dbm: float = -60.0,
                    noise_db: float = 0.8, seed: int = 0) -> None:
    """A well-formed log: all four antennas per row, independent noise."""
    rng = random.Random(seed)
    start = datetime(2026, 8, 3, 12, 0, 0)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "cycle", "freq_mhz", "bw_mhz", "type",
                         "ch0_pwr_dbm", "ch1_pwr_dbm", "ch2_pwr_dbm", "ch3_pwr_dbm"])
        for i in range(rows):
            freq = 2406.0 + rng.uniform(-0.4, 0.4)
            powers = [
                _antenna_power(bearing_deg, b, peak_dbm) + rng.gauss(0, noise_db)
                for b in BORESIGHTS
            ]
            writer.writerow(
                [(start + timedelta(milliseconds=100 * i)).isoformat(timespec="milliseconds"),
                 100 + i // 10, f"{freq:.3f}", "8.90", "FHSS DRONE"]
                + [f"{p:.2f}" for p in powers]
            )


def write_held_log(path, rows: int = 200, step_db: float = 1.7) -> None:
    """Reproduces the real artifact: paired channels, held values, fixed ramp."""
    start = datetime(2026, 8, 3, 12, 0, 0)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "cycle", "freq_mhz", "bw_mhz", "type",
                         "ch0_pwr_dbm", "ch1_pwr_dbm", "ch2_pwr_dbm", "ch3_pwr_dbm"])
        a, b = -70.0, -74.0
        for i in range(rows):
            # only one of the pair updates per row, always by the same step
            if i % 2 == 0:
                a -= step_db
            else:
                b -= step_db
            writer.writerow(
                [(start + timedelta(milliseconds=100 * i)).isoformat(timespec="milliseconds"),
                 100 + i // 10, "2406.100", "8.90", "FHSS DRONE",
                 f"{a:.2f}", f"{b:.2f}", "", ""]
            )


# ----------------------------------------------------------------------
# Estimator
# ----------------------------------------------------------------------


class TestQuadratureBearing:
    @pytest.mark.parametrize("truth", [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0])
    def test_recovers_a_known_bearing_from_ideal_patterns(self, truth):
        powers = [_antenna_power(truth, b, -60.0) for b in BORESIGHTS]
        got = quadrature_bearing(powers)
        error = abs((got - truth + 180) % 360 - 180)
        assert error < 1.0, f"truth {truth}, got {got}"

    def test_returns_none_when_an_opposite_pair_is_incomplete(self):
        assert quadrature_bearing([-70.0, -80.0, None, -90.0]) is None
        assert quadrature_bearing([-70.0, None, -85.0, None]) is None

    def test_returns_none_when_all_antennas_are_equal(self):
        assert quadrature_bearing([-70.0] * 4) is None


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------


class TestLoading:
    def test_reads_rows_and_blank_channels(self, tmp_path):
        path = tmp_path / "log.csv"
        write_clean_log(path, 30.0, rows=12)
        dets = load_detections(path)
        assert len(dets) == 12
        assert all(d.antennas_reporting == 4 for d in dets)
        assert dets[0].signal_type == "FHSS DRONE"

    def test_skips_rows_with_no_antenna_data(self, tmp_path):
        path = tmp_path / "log.csv"
        with open(path, "w", newline="", encoding="utf-8") as handle:
            w = csv.writer(handle)
            w.writerow(["timestamp", "cycle", "freq_mhz", "bw_mhz", "type",
                        "ch0_pwr_dbm", "ch1_pwr_dbm", "ch2_pwr_dbm", "ch3_pwr_dbm"])
            w.writerow(["2026-08-03T12:00:00.000", 1, "2406.0", "8.9", "UNKNOWN", "", "", "", ""])
            w.writerow(["2026-08-03T12:00:00.100", 1, "2406.0", "8.9", "UNKNOWN", "-70", "", "", ""])
        assert len(load_detections(path)) == 1


# ----------------------------------------------------------------------
# Integrity screening
# ----------------------------------------------------------------------


class TestIntegrity:
    def test_clean_log_passes(self, tmp_path):
        path = tmp_path / "clean.csv"
        write_clean_log(path, 30.0)
        integrity = check_integrity(load_detections(path))
        assert integrity.bearings_trustworthy, integrity.problems
        assert integrity.simultaneous_fraction == 1.0

    def test_held_and_ramped_log_is_rejected(self, tmp_path):
        path = tmp_path / "held.csv"
        write_held_log(path)
        integrity = check_integrity(load_detections(path))
        assert not integrity.bearings_trustworthy
        joined = " ".join(integrity.problems)
        assert "held and ramped" in joined
        assert integrity.quantised_step_db == pytest.approx(1.7, abs=0.05)

    def test_dead_antenna_is_reported(self, tmp_path):
        path = tmp_path / "dead.csv"
        write_clean_log(path, 30.0, rows=100)
        # blank out W on all but two rows
        with open(path, newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        for row in rows[3:]:
            row[8] = ""
        with open(path, "w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(rows)
        integrity = check_integrity(load_detections(path))
        assert not integrity.bearings_trustworthy
        assert any("antenna W" in p and "intermittent" in p for p in integrity.problems)

    def test_empty_log_is_handled(self, tmp_path):
        path = tmp_path / "empty.csv"
        with open(path, "w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(["timestamp", "cycle", "freq_mhz", "bw_mhz", "type",
                                         "ch0_pwr_dbm", "ch1_pwr_dbm", "ch2_pwr_dbm",
                                         "ch3_pwr_dbm"])
        integrity = check_integrity(load_detections(path))
        assert not integrity.bearings_trustworthy
        assert "empty" in integrity.problems[0]


# ----------------------------------------------------------------------
# End to end
# ----------------------------------------------------------------------


class TestEndToEnd:
    @pytest.mark.parametrize("truth", [0.0, 45.0, 90.0, 180.0, 270.0, 315.0])
    def test_clean_log_yields_the_right_bearing(self, tmp_path, truth):
        path = tmp_path / "clean.csv"
        write_clean_log(path, truth, rows=150, seed=int(truth))
        integrity, emitters = analyse(path)
        assert integrity.bearings_trustworthy
        assert len(emitters) == 1
        emitter = emitters[0]
        assert emitter.bearing_deg is not None
        error = abs((emitter.bearing_deg - truth + 180) % 360 - 180)
        assert error < 10.0, f"truth {truth}, got {emitter.bearing_deg}"

    def test_held_log_suppresses_the_bearing(self, tmp_path):
        """The whole point: report nothing rather than something plausible."""
        path = tmp_path / "held.csv"
        write_held_log(path)
        integrity, emitters = analyse(path)
        assert not integrity.bearings_trustworthy
        assert emitters, "emitters should still be found"
        assert all(e.bearing_deg is None for e in emitters)
        assert all("integrity" in e.bearing_note for e in emitters)

    def test_range_is_still_reported_when_bearing_is_suppressed(self, tmp_path):
        path = tmp_path / "held.csv"
        write_held_log(path)
        _, emitters = analyse(path)
        lo, hi = emitters[0].range_bracket_m()
        assert 0 < lo < hi

    def test_range_falls_as_signal_rises(self, tmp_path):
        near, far = tmp_path / "near.csv", tmp_path / "far.csv"
        write_clean_log(near, 0.0, peak_dbm=-50.0)
        write_clean_log(far, 0.0, peak_dbm=-80.0)
        assert analyse(near)[1][0].range_m() < analyse(far)[1][0].range_m()

    def test_wideband_and_narrowband_are_grouped_separately(self):
        start = datetime(2026, 8, 3, 12, 0, 0)
        dets = []
        for i in range(12):
            for bw, kind in ((8.9, "FHSS DRONE"), (1.2, "CW/BEACON")):
                dets.append(
                    Detection(
                        timestamp=start + timedelta(milliseconds=100 * i),
                        cycle=1,
                        freq_mhz=2406.0 + (0.1 if bw > 5 else 0.2),
                        bandwidth_mhz=bw,
                        signal_type=kind,
                        powers=[-70.0, -75.0, -80.0, -85.0],
                    )
                )
        emitters = group_emitters(dets)
        assert len(emitters) == 2
        assert {e.is_wideband for e in emitters} == {True, False}

    def test_inconsistent_bearings_are_suppressed(self, tmp_path):
        """A clean-looking log whose bearings scatter must not be averaged
        into a confident-looking answer."""
        path = tmp_path / "scatter.csv"
        rng = random.Random(7)
        start = datetime(2026, 8, 3, 12, 0, 0)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            w = csv.writer(handle)
            w.writerow(["timestamp", "cycle", "freq_mhz", "bw_mhz", "type",
                        "ch0_pwr_dbm", "ch1_pwr_dbm", "ch2_pwr_dbm", "ch3_pwr_dbm"])
            for i in range(200):
                powers = [rng.uniform(-90, -60) for _ in range(4)]
                w.writerow([(start + timedelta(milliseconds=100 * i)).isoformat(
                    timespec="milliseconds"), 1, "2406.100", "8.90", "FHSS DRONE"]
                    + [f"{p:.2f}" for p in powers])
        _, emitters = analyse(path)
        assert emitters[0].bearing_deg is None
        assert "inconsistent" in emitters[0].bearing_note


def test_boresights_match_antenna_names():
    assert len(BORESIGHTS) == 4
    assert math.isclose(BORESIGHTS[0], 0.0) and math.isclose(BORESIGHTS[2], 180.0)
