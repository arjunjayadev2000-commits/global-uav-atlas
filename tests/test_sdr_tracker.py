"""Tests for the standalone sdr.multi_drone_tracker module."""

from __future__ import annotations

import numpy as np
import pytest

from sdr.multi_drone_tracker import SPEED_OF_LIGHT_M_S, MultiDroneSDRTracker


def _make_buffer(n_samples: int, rng: np.random.Generator) -> np.ndarray:
    noise = 0.02 * (rng.standard_normal((4, n_samples)) + 1j * rng.standard_normal((4, n_samples)))
    return noise.astype(complex)


def test_rejects_non_four_channel_input():
    tracker = MultiDroneSDRTracker()
    with pytest.raises(ValueError):
        tracker.process_sdr_buffer(np.zeros((3, 256), dtype=complex))


def test_clean_spectrum_yields_no_detections():
    tracker = MultiDroneSDRTracker()
    rng = np.random.default_rng(1)
    buffer = _make_buffer(1024, rng)
    assert tracker.process_sdr_buffer(buffer) == []


def test_one_hop_mainlobe_is_a_single_detection_not_several():
    """A hop's Hanning mainlobe spans several bins; it must collapse to one hit."""
    tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)
    n_samples = 1024
    rng = np.random.default_rng(2)
    buffer = _make_buffer(n_samples, rng)
    t = np.arange(n_samples)
    tone = 0.6 * np.exp(1j * (2 * np.pi * 200 / n_samples * t))
    buffer[0, :] += tone
    buffer[1, :] += tone
    buffer[2, :] += tone * np.exp(-1j * 0.4)
    buffer[3, :] += tone * np.exp(-1j * 0.1)

    detections = tracker.process_sdr_buffer(buffer)
    assert len(detections) == 1


def test_two_simultaneous_emitters_stay_separate():
    tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)
    n_samples = 1024
    rng = np.random.default_rng(3)
    buffer = _make_buffer(n_samples, rng)
    t = np.arange(n_samples)
    for bin_idx, phase in ((150, 0.9), (500, -1.4)):
        tone = 0.6 * np.exp(1j * (2 * np.pi * bin_idx / n_samples * t))
        buffer[0, :] += tone
        buffer[1, :] += tone
        buffer[2, :] += tone * np.exp(-1j * phase)
        buffer[3, :] += tone * np.exp(-1j * phase * 0.5)

    detections = tracker.process_sdr_buffer(buffer)
    assert len(detections) == 2
    assert detections[0].track_id != detections[1].track_id


def test_frequency_hop_disambiguation_converges_to_true_bearing():
    """The N-S/E-W baseline is ~2 wavelengths, so a single hop's phase is
    ambiguous (grating lobes). A second hop at a different carrier must
    corroborate the anchor hop and resolve the correct bearing, not just
    repeat whatever the first (possibly wrong) wrap happened to be.
    """
    tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)
    n_samples = 1024
    d = tracker.antenna_spacing_m
    true_bearing_deg = 60.0
    true_u_ns = np.cos(np.radians(true_bearing_deg))
    true_u_ew = np.sin(np.radians(true_bearing_deg))
    rng = np.random.default_rng(4)

    last_detections = []
    for hop_ghz in (2.410, 2.418, 2.426, 2.434):
        f_hz = hop_ghz * 1e9
        wavelength_m = SPEED_OF_LIGHT_M_S / f_hz
        t = np.arange(n_samples)
        phi_ns = ((2 * np.pi * d / wavelength_m) * true_u_ns + np.pi) % (2 * np.pi) - np.pi
        phi_ew = ((2 * np.pi * d / wavelength_m) * true_u_ew + np.pi) % (2 * np.pi) - np.pi

        buffer = _make_buffer(n_samples, rng)
        base = 0.6 * np.exp(1j * (2 * np.pi * 200 / n_samples * t))
        buffer[0, :] += base
        buffer[2, :] += base * np.exp(-1j * phi_ns)
        buffer[1, :] += base
        buffer[3, :] += base * np.exp(-1j * phi_ew)

        last_detections = tracker.process_sdr_buffer(buffer)

    assert len(last_detections) == 1
    detection = last_detections[0]
    assert not detection.bearing_ambiguous
    assert abs(detection.bearing_degrees - true_bearing_deg) < 1.0
