"""Tests for the standalone sdr.multi_drone_tracker module.

The disambiguation tests deliberately place each hop on a *different* FFT
bin. An earlier version of these tests reused one bin, which meant the
tracker recomputed the same wavelength every hop and never exercised the
frequency diversity the whole method depends on -- it passed while the
disambiguation was, in fact, 8% accurate.
"""

from __future__ import annotations

import numpy as np
import pytest

from sdr.multi_drone_tracker import SPEED_OF_LIGHT_M_S, MultiDroneSDRTracker

N_SAMPLES = 1024
AMPLITUDE = 0.6


def _noise(n_samples: int, rng: np.random.Generator, snr_db: float | None = None) -> np.ndarray:
    sigma = 0.02 if snr_db is None else AMPLITUDE / np.sqrt(2 * 10 ** (snr_db / 10))
    return (
        sigma * (rng.standard_normal((4, n_samples)) + 1j * rng.standard_normal((4, n_samples)))
    ).astype(complex)


def _inject(buffer: np.ndarray, bin_idx: int, tracker: MultiDroneSDRTracker, bearing_deg: float):
    """Add one hop at `bin_idx` arriving from `bearing_deg`, with correct geometry."""
    n_samples = buffer.shape[1]
    freq_hz = tracker.center_freq_hz + (bin_idx / n_samples) * tracker.sampling_rate
    wavelength_m = SPEED_OF_LIGHT_M_S / freq_hz
    d = tracker.antenna_spacing_m
    u_ns, u_ew = np.cos(np.radians(bearing_deg)), np.sin(np.radians(bearing_deg))
    phi_ns = ((2 * np.pi * d / wavelength_m) * u_ns + np.pi) % (2 * np.pi) - np.pi
    phi_ew = ((2 * np.pi * d / wavelength_m) * u_ew + np.pi) % (2 * np.pi) - np.pi

    t = np.arange(n_samples)
    base = AMPLITUDE * np.exp(1j * (2 * np.pi * bin_idx / n_samples * t))
    buffer[0] += base
    buffer[2] += base * np.exp(-1j * phi_ns)
    buffer[1] += base
    buffer[3] += base * np.exp(-1j * phi_ew)
    return buffer


def test_rejects_non_four_channel_input():
    with pytest.raises(ValueError):
        MultiDroneSDRTracker().process_sdr_buffer(np.zeros((3, 256), dtype=complex))


def test_clean_spectrum_yields_no_detections():
    tracker = MultiDroneSDRTracker()
    assert tracker.process_sdr_buffer(_noise(N_SAMPLES, np.random.default_rng(1))) == []


def test_one_hop_mainlobe_is_a_single_detection_not_several():
    """A hop's Hanning mainlobe spans several bins; it must collapse to one hit."""
    tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)
    buffer = _inject(_noise(N_SAMPLES, np.random.default_rng(2)), 200, tracker, 45.0)
    assert len(tracker.process_sdr_buffer(buffer)) == 1


def test_two_simultaneous_emitters_stay_separate():
    tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)
    buffer = _noise(N_SAMPLES, np.random.default_rng(3))
    _inject(buffer, 150, tracker, 20.0)
    _inject(buffer, 400, tracker, 200.0)
    detections = tracker.process_sdr_buffer(buffer)
    assert len(detections) == 2
    assert detections[0].track_id != detections[1].track_id


def test_hops_below_the_lo_are_not_discarded():
    """Complex IQ has no redundant half: negative bins are real frequencies.

    A hop below the LO must be detected and reported below the centre
    frequency, not folded onto a mirror image above it.
    """
    tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)
    buffer = _inject(_noise(N_SAMPLES, np.random.default_rng(4)), -300, tracker, 45.0)
    detections = tracker.process_sdr_buffer(buffer)
    assert len(detections) == 1
    expected_ghz = (2.42e9 + (-300 / N_SAMPLES) * 40e6) / 1e9
    assert detections[0].frequency_ghz == pytest.approx(expected_ghz, abs=1e-3)


def test_frequency_diverse_hops_resolve_the_true_bearing():
    """The ~2-wavelength baseline aliases, so one hop cannot fix a bearing.

    Hops at different carriers put their aliases in different places while
    the true direction stays put, which is what lets the joint solve pick
    it out. It must both find the right answer and mark it confirmed.
    """
    tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)
    true_bearing = 60.0
    rng = np.random.default_rng(5)

    detections = []
    for bin_idx in (299, -398, -286, 465, 120):
        buffer = _inject(_noise(N_SAMPLES, rng, snr_db=30), bin_idx, tracker, true_bearing)
        detections = tracker.process_sdr_buffer(buffer)

    assert len(detections) == 1
    detection = detections[0]
    assert not detection.bearing_ambiguous
    assert detection.ambiguity_margin >= tracker.confirm_margin
    assert abs(detection.bearing_degrees - true_bearing) < 2.0


def test_first_hop_is_never_reported_as_confirmed():
    """One hop cannot disambiguate a >lambda/2 baseline, whatever it looks like."""
    tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)
    buffer = _inject(_noise(N_SAMPLES, np.random.default_rng(6), snr_db=40), 250, tracker, 137.0)
    detection = tracker.process_sdr_buffer(buffer)[0]
    assert detection.bearing_ambiguous
    assert detection.hops_observed == 1


def test_hops_without_frequency_diversity_refuse_to_confirm():
    """Repeating the same carrier adds no information, and must not be
    mistaken for corroboration. Reporting a confident wrong bearing is far
    worse here than reporting an unresolved one."""
    tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)
    rng = np.random.default_rng(7)
    detections = []
    for _ in range(6):
        buffer = _inject(_noise(N_SAMPLES, rng, snr_db=30), 200, tracker, 60.0)
        detections = tracker.process_sdr_buffer(buffer)

    assert detections[0].hops_observed == 6
    assert detections[0].bearing_ambiguous
    assert detections[0].ambiguity_margin < tracker.confirm_margin


def test_two_hopping_drones_are_tracked_separately_over_time():
    """Two emitters at similar range have near-identical RSSI, so power
    cannot separate them. Association has to fall back on geometry: hops
    from one drone admit a common direction, hops from two do not. Getting
    this wrong pools both emitters into one track that fits neither.
    """
    tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)
    rng = np.random.default_rng(21)

    for _ in range(6):
        buffer = _noise(N_SAMPLES, rng, snr_db=25)
        _inject(buffer, int(rng.integers(-470, -100)), tracker, 60.0)
        _inject(buffer, int(rng.integers(100, 470)), tracker, 210.0)
        detections = tracker.process_sdr_buffer(buffer)
        assert len(detections) == 2
        assert detections[0].track_id != detections[1].track_id

    # after the run each drone should own exactly one confirmed track
    confirmed = [t for t in tracker._tracks.values() if t.resolved]
    assert len(confirmed) == 2
    found = sorted(t.bearing_deg for t in confirmed)
    assert abs(found[0] - 60.0) < 2.0
    assert abs(found[1] - 210.0) < 2.0


def test_confirmed_bearings_are_reliable_across_random_geometry():
    """End-to-end: over many random bearings at 20 dB SNR, a bearing that
    the tracker marks confirmed should almost always be right."""
    rng = np.random.default_rng(8)
    confirmed = 0
    confirmed_correct = 0

    for _ in range(60):
        tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)
        true_bearing = rng.uniform(0, 360)
        detections = []
        for _ in range(5):
            bin_idx = int(rng.integers(-480, 480))
            buffer = _inject(_noise(N_SAMPLES, rng, snr_db=20), bin_idx, tracker, true_bearing)
            detections = tracker.process_sdr_buffer(buffer)
        if detections and not detections[0].bearing_ambiguous:
            confirmed += 1
            error = abs(detections[0].bearing_degrees - true_bearing) % 360
            if min(error, 360 - error) < 5.0:
                confirmed_correct += 1

    assert confirmed >= 30, f"only {confirmed}/60 confirmed; too conservative to be useful"
    assert confirmed_correct / confirmed >= 0.95
