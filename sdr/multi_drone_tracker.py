"""Multi-drone SDR tracker for a synchronized 4-element AD9361 array.

Corrects the following issues found in the prototype this replaces:

1. Bearing math used a single ~2*lambda baseline interferometer and fed the
   raw wrapped phase straight into atan2. A baseline > lambda/2 is spatially
   aliased (grating lobes): the same measured phase maps to several distinct
   true angles, so the prototype's bearings are frequently wrong, not just
   noisy. This version treats each hop's phase as a *candidate set* (one
   candidate per integer phase-wrap) and disambiguates candidates across
   successive hops, since each hop's different carrier frequency changes the
   wrap spacing (classic multi-wavelength / CRT-style ambiguity resolution).
   This turns frequency hopping from a nuisance into the resource that makes
   disambiguation possible in the first place.
2. Every bin above the noise threshold was reported as a separate "drone".
   A single hop's mainlobe is several bins wide (worse with a Hanning
   window), so one hop produced several near-duplicate detections at
   slightly different bearings. This version clusters contiguous bins into
   one detection per hop and coherently combines phase/power across the
   cluster for a less noisy estimate.
3. Amplitude/RSSI was read directly off windowed FFT bins with no coherent
   gain correction, so the absolute dBFS/RSSI scale (and therefore the
   distance estimate, which is exponential in RSSI) shifted with window
   choice and buffer size. This version normalizes by the window's coherent
   gain.
4. The noise floor was estimated from a single channel, so a target in that
   channel's antenna null could be missed even with 3 other channels lit up.
   This version floors on the combined power across all four channels.
5. Frequency was reported at raw FFT bin resolution (~39 kHz per bin at
   40 Msps/1024 pt). This version adds parabolic interpolation across the
   peak for sub-bin accuracy.
6. There was no continuity across buffers, so a frequency-hopping emitter
   produced an unordered pile of single-hop detections instead of a track.
   This version keeps lightweight per-track state (EWMA bearing/distance,
   circular mean for the wraparound angle) across calls to
   ``process_sdr_buffer``.

Physical caveat that no amount of software fixes: the N/S and E/W antenna
pairs are ~2 wavelengths apart at 2.44 GHz. That is a deliberate hardware
choice for angular resolution, but it is why disambiguation is needed at
all -- a single-hop, single-baseline system this size cannot report an
unambiguous bearing. If the hardware allows it, adding one extra pair of
antennas at <= lambda/2 spacing (~6.1 cm at 2.44 GHz) removes the ambiguity
outright and lets every single hop resolve on its own, at the cost of the
coarser pair's angular resolution.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from itertools import count

import numpy as np

SPEED_OF_LIGHT_M_S = 299_792_458.0


@dataclass
class Detection:
    """One resolved hop, associated with a persistent track when possible."""

    track_id: int
    frequency_ghz: float
    bearing_degrees: float
    bearing_ambiguous: bool
    distance_meters: float
    signal_strength_dbm: float
    hops_confirmed: int


@dataclass
class _Track:
    track_id: int
    distance_m: float
    rssi_dbm: float
    hops_confirmed: int
    resolved: bool = False
    misses: int = 0
    bearing_vec: complex = 0j  # unit-magnitude complex EWMA accumulator, once resolved
    # Anchor hop, kept raw (not collapsed to one bearing) until a second hop
    # corroborates it in direction-cosine space -- collapsing on a single
    # hop from a >lambda/2 baseline just locks in whichever wrap happened
    # to be closest to zero, which is not more likely to be true than any
    # other wrap.
    anchor_delta_phi_ns: float = 0.0
    anchor_delta_phi_ew: float = 0.0
    anchor_wavelength_m: float = 0.0


class MultiDroneSDRTracker:
    """Tracking processor for a synchronized 2x AD9361 (4-channel) setup.

    Parameters
    ----------
    sampling_rate:
        IQ sample rate in Hz.
    center_freq_hz:
        Tuning center frequency of the AD9361 LO.
    threshold_db:
        SNR threshold above the noise floor to qualify a hop as a detection.
    antenna_spacing_m:
        Physical separation of the N-S and (independently) E-W antenna
        pairs, in meters. This is what actually determines the phase-to-
        angle mapping and the ambiguity spacing -- it must match the real
        array, not be baked into a constant.
    track_bearing_gate_deg / track_rssi_gate_db:
        Association gates: a new hop joins an existing track only if the
        best-matching bearing candidate and RSSI are within these gates of
        the track's current estimate.
    track_max_misses:
        Frames a track can go undetected before it is dropped.
    smoothing:
        EWMA weight (0-1) given to each new hop when updating a track's
        bearing/distance/RSSI estimate. Higher = more responsive, noisier.
    """

    def __init__(
        self,
        sampling_rate: float = 40e6,
        center_freq_hz: float = 2.44e9,
        threshold_db: float = 12.0,
        antenna_spacing_m: float = 0.245,  # ~2 lambda at 2.44 GHz
        peak_min_gap_bins: int = 2,
        track_bearing_gate_deg: float = 30.0,
        track_rssi_gate_db: float = 10.0,
        track_max_misses: int = 3,
        smoothing: float = 0.4,
        ambiguity_resolution_tolerance: float = 0.05,
    ):
        self.sampling_rate = sampling_rate
        self.center_freq_hz = center_freq_hz
        self.threshold_db = threshold_db
        self.antenna_spacing_m = antenna_spacing_m
        self.peak_min_gap_bins = peak_min_gap_bins
        self.track_bearing_gate_deg = track_bearing_gate_deg
        self.track_rssi_gate_db = track_rssi_gate_db
        self.track_max_misses = track_max_misses
        self.smoothing = smoothing
        self.ambiguity_resolution_tolerance = ambiguity_resolution_tolerance

        # Log-distance path loss model calibration (transmitter-specific --
        # re-derive rssi_at_1m_dbm against the *corrected* amplitude scale
        # below with a real reference transmitter, not the prototype's
        # uncalibrated raw FFT magnitude).
        self.ref_distance_m = 1.0
        self.rssi_at_1m_dbm = -25.0
        self.path_loss_exponent = 2.2
        self.adc_full_scale_dbm = 10.0

        self._cached_n_samples: int | None = None
        self._window: np.ndarray | None = None
        self._coherent_gain: float = 1.0
        self._freqs: np.ndarray | None = None

        self._tracks: dict[int, _Track] = {}
        self._track_ids = count(1)

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _prepare_for_length(self, n_samples: int) -> None:
        if self._cached_n_samples == n_samples:
            return
        window = np.hanning(n_samples)
        self._window = window
        self._coherent_gain = float(np.sum(window))
        self._freqs = np.fft.fftfreq(n_samples, d=1 / self.sampling_rate)
        self._cached_n_samples = n_samples

    # ------------------------------------------------------------------
    # Peak finding
    # ------------------------------------------------------------------

    @staticmethod
    def _cluster_bins(active_bins: np.ndarray, min_gap: int) -> list[np.ndarray]:
        """Group active bin indices into contiguous-ish clusters (one per hop)."""
        if len(active_bins) == 0:
            return []
        clusters = []
        current = [int(active_bins[0])]
        for b in active_bins[1:]:
            if int(b) - current[-1] <= min_gap:
                current.append(int(b))
            else:
                clusters.append(np.array(current))
                current = [int(b)]
        clusters.append(np.array(current))
        return clusters

    def _refine_peak_bin(self, power: np.ndarray, peak_bin: int) -> float:
        """Parabolic (quadratic) interpolation for sub-bin frequency accuracy."""
        n = len(power)
        if peak_bin <= 0 or peak_bin >= n - 1:
            return float(peak_bin)
        p_left = np.log(power[peak_bin - 1] + 1e-30)
        p_center = np.log(power[peak_bin] + 1e-30)
        p_right = np.log(power[peak_bin + 1] + 1e-30)
        denom = p_left - 2 * p_center + p_right
        if denom == 0:
            return float(peak_bin)
        delta = 0.5 * (p_left - p_right) / denom
        delta = float(np.clip(delta, -0.5, 0.5))
        return peak_bin + delta

    # ------------------------------------------------------------------
    # Bearing: candidate generation + disambiguation
    # ------------------------------------------------------------------

    def _direction_cosine_candidates(self, delta_phi: float, wavelength_m: float) -> list[float]:
        """All direction cosines consistent with a wrapped phase measurement.

        delta_phi = 2*pi*d/lambda * u  (mod 2*pi), so any n with
        u = (lambda / (2*pi*d)) * (delta_phi + 2*pi*n) in [-1, 1] is a
        physically valid candidate. Baselines > lambda/2 admit more than
        one; the true one is picked by cross-hop consistency, not here.
        """
        d = self.antenna_spacing_m
        scale = wavelength_m / (2 * np.pi * d)
        max_n = int(np.ceil(d / wavelength_m)) + 1
        candidates = []
        for n in range(-max_n, max_n + 1):
            u = scale * (delta_phi + 2 * np.pi * n)
            if -1.0 <= u <= 1.0:
                candidates.append(u)
        # n=0 (smallest |wrap|) first: a reasonable default when there is no
        # track history yet to disambiguate against.
        candidates.sort(key=lambda u: abs(scale * delta_phi - u))
        return candidates or [float(np.clip(scale * delta_phi, -1.0, 1.0))]

    def _direction_cosine_pairs(self, delta_phi_ns: float, delta_phi_ew: float, wavelength_m: float):
        u_ns_candidates = self._direction_cosine_candidates(delta_phi_ns, wavelength_m)
        u_ew_candidates = self._direction_cosine_candidates(delta_phi_ew, wavelength_m)
        return list(itertools.product(u_ns_candidates, u_ew_candidates))

    @staticmethod
    def _bearing_from_u(u_ns: float, u_ew: float) -> float:
        return (np.degrees(np.arctan2(u_ew, u_ns)) + 360) % 360

    @staticmethod
    def _angular_distance_deg(a: float, b: float) -> float:
        diff = abs(a - b) % 360
        return min(diff, 360 - diff)

    # ------------------------------------------------------------------
    # Track association
    #
    # Two different situations need two different strategies:
    #
    # * A track with an already-*resolved* bearing (>=2 corroborated hops):
    #   a new hop's ambiguity is broken by picking whichever of its several
    #   candidate bearings falls closest to the track's running estimate.
    # * A brand-new detection with only one hop so far ("anchor"): its
    #   bearing has NOT been resolved yet -- picking the smallest phase
    #   wrap (n=0) is an arbitrary guess, not a disambiguation, when the
    #   baseline is a couple of wavelengths. It is only resolved once a
    #   second hop (a different carrier -> a different wrap spacing) is
    #   found whose candidate set agrees with the anchor's in direction-
    #   cosine space. Two independently-wrapped measurements agreeing to
    #   within `ambiguity_resolution_tolerance` is what actually pins the
    #   true angle down; this is the frequency-hopping-specific trick.
    # ------------------------------------------------------------------

    def _match_resolved_track(
        self, u_pairs: list[tuple[float, float]], rssi_dbm: float
    ) -> tuple[_Track | None, float, float]:
        best_track, best_u = None, u_pairs[0]
        best_score = None
        for track in self._tracks.values():
            if not track.resolved:
                continue
            track_bearing = np.degrees(np.angle(track.bearing_vec)) % 360
            rssi_err = abs(rssi_dbm - track.rssi_dbm)
            if rssi_err > self.track_rssi_gate_db:
                continue
            for u_ns, u_ew in u_pairs:
                bearing = self._bearing_from_u(u_ns, u_ew)
                bearing_err = self._angular_distance_deg(bearing, track_bearing)
                if bearing_err <= self.track_bearing_gate_deg:
                    score = bearing_err + rssi_err
                    if best_score is None or score < best_score:
                        best_score, best_track, best_u = score, track, (u_ns, u_ew)
        return best_track, best_u[0], best_u[1]

    def _try_resolve_anchor(
        self, delta_phi_ns: float, delta_phi_ew: float, wavelength_m: float, rssi_dbm: float
    ) -> tuple[_Track | None, float, float]:
        """Look for an unresolved track whose anchor hop corroborates this one."""
        best_track, best_u, best_cost = None, None, None
        for track in self._tracks.values():
            if track.resolved:
                continue
            if abs(rssi_dbm - track.rssi_dbm) > self.track_rssi_gate_db:
                continue
            anchor_pairs = self._direction_cosine_pairs(
                track.anchor_delta_phi_ns, track.anchor_delta_phi_ew, track.anchor_wavelength_m
            )
            new_pairs = self._direction_cosine_pairs(delta_phi_ns, delta_phi_ew, wavelength_m)
            for (u1_ns, u1_ew), (u2_ns, u2_ew) in itertools.product(anchor_pairs, new_pairs):
                cost = np.hypot(u1_ns - u2_ns, u1_ew - u2_ew)
                if cost <= self.ambiguity_resolution_tolerance and (best_cost is None or cost < best_cost):
                    best_cost = cost
                    best_track = track
                    best_u = ((u1_ns + u2_ns) / 2, (u1_ew + u2_ew) / 2)
        if best_track is None:
            return None, 0.0, 0.0
        return best_track, best_u[0], best_u[1]

    def _associate(
        self, delta_phi_ns: float, delta_phi_ew: float, wavelength_m: float, rssi_dbm: float, distance_m: float
    ) -> Detection:
        a = self.smoothing
        u_pairs = self._direction_cosine_pairs(delta_phi_ns, delta_phi_ew, wavelength_m)

        track, u_ns, u_ew = self._match_resolved_track(u_pairs, rssi_dbm)
        if track is not None:
            bearing_rad = np.radians(self._bearing_from_u(u_ns, u_ew))
            track.bearing_vec = (1 - a) * track.bearing_vec + a * complex(
                np.cos(bearing_rad), np.sin(bearing_rad)
            )
            track.distance_m = (1 - a) * track.distance_m + a * distance_m
            track.rssi_dbm = (1 - a) * track.rssi_dbm + a * rssi_dbm
            track.hops_confirmed += 1
            track.misses = 0
            return self._detection_from_track(track, ambiguous=False)

        track, u_ns, u_ew = self._try_resolve_anchor(delta_phi_ns, delta_phi_ew, wavelength_m, rssi_dbm)
        if track is not None:
            bearing_rad = np.radians(self._bearing_from_u(u_ns, u_ew))
            track.resolved = True
            track.bearing_vec = complex(np.cos(bearing_rad), np.sin(bearing_rad))
            track.distance_m = (track.distance_m + distance_m) / 2
            track.rssi_dbm = (track.rssi_dbm + rssi_dbm) / 2
            track.hops_confirmed += 1
            track.misses = 0
            return self._detection_from_track(track, ambiguous=False)

        # No corroboration yet: open a new unresolved track anchored on this
        # hop and report its best-effort (unconfirmed) principal-wrap guess.
        u_ns0, u_ew0 = u_pairs[0]
        bearing_rad = np.radians(self._bearing_from_u(u_ns0, u_ew0))
        track = _Track(
            track_id=next(self._track_ids),
            distance_m=distance_m,
            rssi_dbm=rssi_dbm,
            hops_confirmed=1,
            resolved=False,
            bearing_vec=complex(np.cos(bearing_rad), np.sin(bearing_rad)),
            anchor_delta_phi_ns=delta_phi_ns,
            anchor_delta_phi_ew=delta_phi_ew,
            anchor_wavelength_m=wavelength_m,
        )
        self._tracks[track.track_id] = track
        return self._detection_from_track(track, ambiguous=True)

    def _detection_from_track(self, track: _Track, ambiguous: bool) -> Detection:
        return Detection(
            track_id=track.track_id,
            frequency_ghz=0.0,  # filled in by caller
            bearing_degrees=round(float(np.degrees(np.angle(track.bearing_vec)) % 360), 2),
            bearing_ambiguous=ambiguous,
            distance_meters=round(float(track.distance_m), 1),
            signal_strength_dbm=round(float(track.rssi_dbm), 1),
            hops_confirmed=track.hops_confirmed,
        )

    def _prune_stale_tracks(self, updated_ids: set[int]) -> None:
        for tid in list(self._tracks):
            if tid not in updated_ids:
                self._tracks[tid].misses += 1
                if self._tracks[tid].misses > self.track_max_misses:
                    del self._tracks[tid]

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process_sdr_buffer(self, iq_matrix: np.ndarray) -> list[Detection]:
        """Process one coherent capture frame from the four synchronized channels.

        Row 0 = North, 1 = East, 2 = South, 3 = West.
        """
        n_channels, n_samples = iq_matrix.shape
        if n_channels != 4:
            raise ValueError("Input matrix must contain exactly 4 coherent antenna channels.")

        self._prepare_for_length(n_samples)
        window = self._window
        freqs = self._freqs

        fft_output = np.fft.fft(iq_matrix * window, axis=1)

        # Combined power across all 4 channels: a target in one antenna's
        # null still shows up via the other three.
        power_all = np.mean(np.abs(fft_output) ** 2, axis=0)
        median_noise = np.median(power_all)
        noise_threshold = median_noise * (10 ** (self.threshold_db / 10))

        half = n_samples // 2
        active_bins = np.where(power_all[:half] > noise_threshold)[0]
        if len(active_bins) == 0:
            self._prune_stale_tracks(set())
            return []

        clusters = self._cluster_bins(active_bins, self.peak_min_gap_bins)

        detections: list[Detection] = []
        updated_track_ids: set[int] = set()

        for cluster in clusters:
            peak_bin = int(cluster[np.argmax(power_all[cluster])])
            refined_bin = self._refine_peak_bin(power_all, peak_bin)
            bin_freq_hz = np.interp(refined_bin, np.arange(n_samples // 2), freqs[: n_samples // 2])
            exact_frequency_ghz = (self.center_freq_hz + bin_freq_hz) / 1e9
            wavelength_m = SPEED_OF_LIGHT_M_S / (self.center_freq_hz + bin_freq_hz)

            # Coherent combination across the cluster's bins improves the
            # phase (bearing) and power (distance) SNR versus a single bin.
            x_n = fft_output[0, cluster]
            x_e = fft_output[1, cluster]
            x_s = fft_output[2, cluster]
            x_w = fft_output[3, cluster]

            cross_ns = np.sum(x_n * np.conj(x_s))
            cross_ew = np.sum(x_e * np.conj(x_w))
            delta_phi_ns = float(np.angle(cross_ns))
            delta_phi_ew = float(np.angle(cross_ew))

            total_power = np.sum(np.abs(x_n) ** 2 + np.abs(x_e) ** 2 + np.abs(x_s) ** 2 + np.abs(x_w) ** 2)
            # Coherent-gain correction: an FFT of a windowed signal reports
            # amplitude scaled by sum(window), not n_samples.
            calibrated_power = total_power / (self._coherent_gain**2)
            measured_dbfs = 10 * np.log10(calibrated_power + 1e-30)
            measured_rssi_dbm = measured_dbfs + self.adc_full_scale_dbm

            distance_ratio = (self.rssi_at_1m_dbm - measured_rssi_dbm) / (10 * self.path_loss_exponent)
            approx_distance_m = self.ref_distance_m * (10**distance_ratio)

            detection = self._associate(
                delta_phi_ns, delta_phi_ew, wavelength_m, measured_rssi_dbm, approx_distance_m
            )
            detection.frequency_ghz = round(float(exact_frequency_ghz), 4)
            detections.append(detection)
            updated_track_ids.add(detection.track_id)

        self._prune_stale_tracks(updated_track_ids)
        return detections


# --- Verification simulation: a frequency-hopping emitter at a fixed
# bearing, observed over several hops. The N-S/E-W baselines are ~2
# wavelengths, so a single hop's phase is ambiguous; watch
# `bearing_ambiguous` clear and the bearing converge to the true value
# (60 degrees) as more hops confirm the track. Note the distance/RSSI
# numbers here are an artifact of the simulation's arbitrary signal
# amplitude, not a calibrated measurement -- the log-distance constants
# must be re-derived against a real reference transmitter. ---
if __name__ == "__main__":
    rng = np.random.default_rng(0)
    tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)

    n_samples = 1024
    d = tracker.antenna_spacing_m
    true_bearing_deg = 60.0
    true_u_ns = np.cos(np.radians(true_bearing_deg))
    true_u_ew = np.sin(np.radians(true_bearing_deg))

    hop_frequencies_ghz = [2.410, 2.418, 2.426, 2.434, 2.442]
    for hop_ghz in hop_frequencies_ghz:
        f_hz = hop_ghz * 1e9
        wavelength_m = SPEED_OF_LIGHT_M_S / f_hz
        bin_idx = 200
        t = np.arange(n_samples)

        true_phi_ns = ((2 * np.pi * d / wavelength_m) * true_u_ns + np.pi) % (2 * np.pi) - np.pi
        true_phi_ew = ((2 * np.pi * d / wavelength_m) * true_u_ew + np.pi) % (2 * np.pi) - np.pi

        noise = 0.02 * (rng.standard_normal((4, n_samples)) + 1j * rng.standard_normal((4, n_samples)))
        sim_buffer = noise.astype(complex)
        base = 0.6 * np.exp(1j * (2 * np.pi * bin_idx / n_samples * t))
        sim_buffer[0, :] += base
        sim_buffer[2, :] += base * np.exp(-1j * true_phi_ns)
        sim_buffer[1, :] += base
        sim_buffer[3, :] += base * np.exp(-1j * true_phi_ew)

        for det in tracker.process_sdr_buffer(sim_buffer):
            print(
                f"hop {hop_ghz:.3f} GHz -> track {det.track_id} | "
                f"bearing {det.bearing_degrees:6.2f} deg "
                f"({'ambiguous' if det.bearing_ambiguous else 'confirmed'}) | "
                f"dist {det.distance_meters:6.1f} m | "
                f"rssi {det.signal_strength_dbm:6.1f} dBm | "
                f"hops {det.hops_confirmed}"
            )
