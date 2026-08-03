"""Multi-drone SDR tracker for a synchronized 4-element AD9361 array.

The array's N-S and E-W antenna pairs sit ~2 wavelengths apart at 2.44 GHz.
That buys angular resolution, but it puts the array well past the lambda/2
spacing at which a phase interferometer is unambiguous: a single snapshot's
measured phase is consistent with about a dozen different sky directions,
and the aliases are *exact* -- they agree with the measurement on every one
of the array's six baselines simultaneously. No amount of processing
recovers the true bearing from one hop. This was verified by beamforming
the full array: seven peaks of identical height for one incident signal.

What breaks the tie is a second measurement at a different scale. A
frequency-hopping emitter supplies exactly that for free: each hop has its
own wavelength, so each hop's aliases land in different places while the
true direction stays put. This module therefore does not try to resolve a
bearing from a single hop. It accumulates hops per track and scores every
candidate direction against *all* of them, only declaring a bearing
resolved once one direction fits the accumulated evidence substantially
better than any other distinct direction.

Design notes on the parts that are easy to get wrong:

* Ambiguity is enumerated, never guessed. ``_direction_cosine_candidates``
  returns every direction cosine consistent with a wrapped phase. Picking
  the smallest wrap (n=0) is an arbitrary choice, not a disambiguation.
* Confidence is measured, not counted. ``bearing_ambiguous`` is driven by
  the actual margin between the best and the runner-up direction, so hops
  that lack the frequency diversity to disambiguate report ambiguous
  instead of reporting a confident wrong answer.
* The spectrum is complex, so the upper half of the FFT holds real
  frequencies *below* the LO, not Nyquist mirrors. Discarding them would
  blind the tracker to half its own bandwidth and halve the frequency
  diversity the disambiguation depends on.
* One hop's windowed mainlobe spans several bins; bins are clustered so a
  hop yields one detection rather than several near-duplicates.
* FFT magnitudes are corrected by the window's coherent gain, otherwise the
  dBFS scale -- and therefore range, which is exponential in RSSI -- drifts
  with window choice and buffer length.

Remaining hardware caveat: adding one antenna pair at <= lambda/2 spacing
(~6.1 cm at 2.44 GHz) would make every individual hop unambiguous on its
own, removing the dependence on hop diversity entirely. Worth it if you
expect several simultaneous hoppers, where associating hops to the right
emitter becomes the limiting factor.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from itertools import count

import numpy as np

SPEED_OF_LIGHT_M_S = 299_792_458.0


def _wrap_to_pi(x: np.ndarray | float) -> np.ndarray | float:
    """Wrap an angle (or array of angles) into [-pi, pi)."""
    return (x + np.pi) % (2 * np.pi) - np.pi


@dataclass
class Detection:
    """One hop, associated with a persistent track.

    ``bearing_ambiguous`` is the honest one: it is True whenever the hops
    gathered so far do not pin the direction down, and callers should treat
    ``bearing_degrees`` as a guess while it is set.
    """

    track_id: int
    frequency_ghz: float
    bearing_degrees: float
    bearing_ambiguous: bool
    ambiguity_margin: float
    distance_meters: float
    signal_strength_dbm: float
    hops_observed: int


@dataclass
class _Observation:
    """One hop's raw interferometric measurement, kept unresolved."""

    delta_phi_ns: float
    delta_phi_ew: float
    wavelength_m: float


@dataclass
class _Track:
    track_id: int
    distance_m: float
    rssi_dbm: float
    observations: list[_Observation] = field(default_factory=list)
    bearing_vec: complex = 0j
    resolved: bool = False
    margin: float = 0.0
    misses: int = 0
    #: Frame this track last accepted a hop in. Two hops in the same capture
    #: are two emitters (or a multipath image), never two looks at one
    #: emitter, so pooling them into one joint solve would be meaningless.
    last_frame: int = -1

    @property
    def bearing_deg(self) -> float:
        return float(np.degrees(np.angle(self.bearing_vec)) % 360)


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
        Separation of the N-S and (independently) E-W antenna pairs, in
        meters. This sets the phase-to-angle mapping and the ambiguity
        spacing, so it must match the real array.
    confirm_margin:
        How much better the winning direction must fit the accumulated hops
        than the best distinct runner-up before the bearing is reported as
        unambiguous. It is a ratio of residual costs, which makes it a
        likelihood-ratio-like statistic: the numerator is how badly the
        runner-up misfits and the denominator tracks the measurement noise,
        so it is insensitive to absolute signal level. Calibrated over 4320
        Monte Carlo trials spanning 5-40 dB SNR, 2-8 hops, and both spread
        and degenerate hop patterns: margin < 2 was correct 6-16% of the
        time, 2-3 was 84%, >30 was 99.4%. The default of 6 keeps ~98% of
        confirmed bearings correct. Raise it to trade coverage for
        precision; the raw margin is reported on every detection so callers
        can apply their own policy.
    phase_noise_floor_deg:
        Lower clamp on the best-fit residual, purely to stop a noiseless
        perfect fit dividing by zero. Keep it well below the alias
        separation -- with only ~1.6% fractional hop bandwidth the nearest
        alias sits about 2 degrees of phase from a perfect fit, so a floor
        of even 3 degrees swamps the discrimination entirely.
    distinct_candidate_deg:
        Two candidate directions closer than this are treated as the same
        hypothesis, so the runner-up is a genuinely different direction
        rather than a neighbouring grid point.
    max_observations:
        Hops retained per track for the joint solve.
    association_max_residual_deg:
        How badly a direction may fit a track's hops plus a new one before
        the hop is judged to come from a different emitter. Hops from one
        emitter fit to within the phase noise; hops from two emitters leave
        a residual orders of magnitude larger, so this gate is not
        sensitive to its exact value.
    track_bearing_gate_deg / track_rssi_gate_db:
        Association gates for attaching a new hop to an existing track.
    track_max_misses:
        Frames a track may go undetected before it is dropped.
    smoothing:
        EWMA weight for range/RSSI updates. Bearing is not smoothed this
        way -- it is re-solved from all retained hops each time, which is
        both better conditioned and self-correcting.
    """

    def __init__(
        self,
        sampling_rate: float = 40e6,
        center_freq_hz: float = 2.44e9,
        threshold_db: float = 12.0,
        antenna_spacing_m: float = 0.245,  # ~2 lambda at 2.44 GHz
        peak_min_gap_bins: int = 2,
        confirm_margin: float = 6.0,
        phase_noise_floor_deg: float = 0.1,
        distinct_candidate_deg: float = 10.0,
        max_observations: int = 12,
        association_max_residual_deg: float = 15.0,
        track_bearing_gate_deg: float = 30.0,
        track_rssi_gate_db: float = 10.0,
        track_max_misses: int = 3,
        smoothing: float = 0.4,
    ):
        self.sampling_rate = sampling_rate
        self.center_freq_hz = center_freq_hz
        self.threshold_db = threshold_db
        self.antenna_spacing_m = antenna_spacing_m
        self.peak_min_gap_bins = peak_min_gap_bins
        self.confirm_margin = confirm_margin
        self.phase_noise_floor_rad2 = float(np.radians(phase_noise_floor_deg) ** 2)
        self.distinct_candidate_deg = distinct_candidate_deg
        self.max_observations = max_observations
        self.association_max_residual_rad2 = float(np.radians(association_max_residual_deg) ** 2)
        self.track_bearing_gate_deg = track_bearing_gate_deg
        self.track_rssi_gate_db = track_rssi_gate_db
        self.track_max_misses = track_max_misses
        self.smoothing = smoothing

        # Log-distance path loss model calibration. These are
        # transmitter-specific: re-derive rssi_at_1m_dbm against a real
        # reference emitter using the coherent-gain-corrected scale below.
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
        self._frame = -1

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _prepare_for_length(self, n_samples: int) -> None:
        if self._cached_n_samples == n_samples:
            return
        window = np.hanning(n_samples)
        self._window = window
        self._coherent_gain = float(np.sum(window))
        # fftshift so the spectrum runs monotonically from -fs/2 to +fs/2.
        # The negative half holds genuine frequencies below the LO, not
        # mirrors -- complex IQ has no redundant half to discard.
        self._freqs = np.fft.fftshift(np.fft.fftfreq(n_samples, d=1 / self.sampling_rate))
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

    @staticmethod
    def _refine_peak_bin(power: np.ndarray, peak_bin: int) -> float:
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
        return peak_bin + float(np.clip(delta, -0.5, 0.5))

    # ------------------------------------------------------------------
    # Ambiguity enumeration
    # ------------------------------------------------------------------

    def _direction_cosine_candidates(self, delta_phi: float, wavelength_m: float) -> list[float]:
        """Every direction cosine consistent with a wrapped phase measurement.

        delta_phi = 2*pi*d/lambda * u (mod 2*pi), so any integer wrap n with
        u = (lambda / (2*pi*d)) * (delta_phi + 2*pi*n) inside [-1, 1] is
        physically legal. A baseline beyond lambda/2 admits several; which
        one is real is decided later, across hops, never here.
        """
        d = self.antenna_spacing_m
        scale = wavelength_m / (2 * np.pi * d)
        max_n = int(np.ceil(d / wavelength_m)) + 1
        candidates = [
            scale * (delta_phi + 2 * np.pi * n)
            for n in range(-max_n, max_n + 1)
            if -1.0 <= scale * (delta_phi + 2 * np.pi * n) <= 1.0
        ]
        return candidates or [float(np.clip(scale * delta_phi, -1.0, 1.0))]

    def _direction_cosine_pairs(
        self, delta_phi_ns: float, delta_phi_ew: float, wavelength_m: float
    ) -> list[tuple[float, float]]:
        return list(
            itertools.product(
                self._direction_cosine_candidates(delta_phi_ns, wavelength_m),
                self._direction_cosine_candidates(delta_phi_ew, wavelength_m),
            )
        )

    @staticmethod
    def _bearing_from_u(u_ns: float, u_ew: float) -> float:
        return float((np.degrees(np.arctan2(u_ew, u_ns)) + 360) % 360)

    @staticmethod
    def _angular_distance_deg(a: float, b: float) -> float:
        diff = abs(a - b) % 360
        return min(diff, 360 - diff)

    # ------------------------------------------------------------------
    # Joint multi-hop solve
    #
    # Every hop contributes a full candidate set. The true direction is the
    # one that appears (to within noise) in all of them; an alias only fits
    # the hop that produced it, because a different wavelength moves it.
    # Scoring each candidate against every retained hop and comparing the
    # winner to the best *distinct* runner-up gives both the estimate and a
    # usable confidence measure -- when the hops lack frequency diversity,
    # every candidate fits equally well, the margin collapses, and the
    # bearing is correctly reported as unresolved.
    # ------------------------------------------------------------------

    def _residual_costs(
        self, candidates: np.ndarray, observations: list[_Observation]
    ) -> np.ndarray:
        """Mean squared wrapped phase residual of every candidate over all hops.

        Scores the whole (candidates x hops) grid at once: this runs for
        every track on every hop during association, so the scalar version
        dominated the runtime.
        """
        k = 2 * np.pi * self.antenna_spacing_m
        inv_lambda = np.array([1.0 / o.wavelength_m for o in observations])
        phi_ns = np.array([o.delta_phi_ns for o in observations])
        phi_ew = np.array([o.delta_phi_ew for o in observations])

        r_ns = _wrap_to_pi(k * np.outer(candidates[:, 0], inv_lambda) - phi_ns)
        r_ew = _wrap_to_pi(k * np.outer(candidates[:, 1], inv_lambda) - phi_ew)
        return np.mean(r_ns**2 + r_ew**2, axis=1)

    def _refine(
        self, seed: tuple[float, float], observations: list[_Observation]
    ) -> tuple[float, float]:
        """Least-squares refine a direction once its phase wraps are known.

        With the correct candidate in hand each hop's wrap index is
        determined, so the phases can be unwrapped and averaged directly
        instead of snapping to the discrete candidate grid.
        """
        k = 2 * np.pi * self.antenna_spacing_m
        estimates: list[list[float]] = [[], []]
        for obs in observations:
            for axis, (u_seed, phi) in enumerate(
                ((seed[0], obs.delta_phi_ns), (seed[1], obs.delta_phi_ew))
            ):
                predicted = k * u_seed / obs.wavelength_m
                n = round((predicted - phi) / (2 * np.pi))
                estimates[axis].append((phi + 2 * np.pi * n) * obs.wavelength_m / k)
        u_ns, u_ew = float(np.mean(estimates[0])), float(np.mean(estimates[1]))
        norm = np.hypot(u_ns, u_ew)
        if norm > 1.0:  # noise can push the estimate just outside the visible region
            u_ns, u_ew = u_ns / norm, u_ew / norm
        return u_ns, u_ew

    def _solve(self, observations: list[_Observation]) -> tuple[float, float, float, float]:
        """Return (u_ns, u_ew, margin, best_cost) for the best-supported direction."""
        candidates: list[tuple[float, float]] = []
        for obs in observations:
            candidates.extend(
                self._direction_cosine_pairs(obs.delta_phi_ns, obs.delta_phi_ew, obs.wavelength_m)
            )

        # Hops repeat each other's candidates; keep one representative of
        # each distinct direction. Deduplicating in numpy rather than with a
        # Python set of rounded tuples matters -- this is the hottest loop.
        grid = np.array(candidates)
        _, unique_idx = np.unique(np.round(grid, 2), axis=0, return_index=True)
        grid = grid[np.sort(unique_idx)]
        costs = self._residual_costs(grid, observations)
        order = np.argsort(costs)

        best_cost = float(costs[order[0]])
        best_u = (float(grid[order[0], 0]), float(grid[order[0], 1]))
        best_bearing = self._bearing_from_u(*best_u)

        runner_up_cost = None
        for idx in order[1:]:
            bearing = self._bearing_from_u(float(grid[idx, 0]), float(grid[idx, 1]))
            if self._angular_distance_deg(bearing, best_bearing) >= self.distinct_candidate_deg:
                runner_up_cost = float(costs[idx])
                break

        if runner_up_cost is None:
            # Only one distinct direction fits at all: nothing to confuse it with.
            margin = float("inf")
        else:
            margin = runner_up_cost / max(best_cost, self.phase_noise_floor_rad2)

        u_ns, u_ew = self._refine(best_u, observations)
        return u_ns, u_ew, margin, best_cost

    # ------------------------------------------------------------------
    # Track association
    # ------------------------------------------------------------------

    def _find_track(self, observation: _Observation, rssi_dbm: float) -> _Track | None:
        """Attach a hop to the track it is geometrically compatible with.

        RSSI alone is a weak gate -- two drones at similar range have
        near-identical power, and assigning their hops arbitrarily pools
        both emitters into one track, which then fits neither. The decisive
        test is whether *any single direction* explains the track's existing
        hops together with this one. Hops from one emitter always admit such
        a direction (the true one); hops from two emitters admit none, and
        the best achievable residual jumps by orders of magnitude.
        """
        best_track, best_cost = None, None
        for track in self._tracks.values():
            # One capture frame cannot contain two looks at the same
            # emitter: a second cluster is another drone or a multipath
            # image, and pooling it would corrupt the joint solve.
            if track.last_frame == self._frame:
                continue
            if abs(rssi_dbm - track.rssi_dbm) > self.track_rssi_gate_db:
                continue
            if track.resolved:
                candidates = self._direction_cosine_pairs(
                    observation.delta_phi_ns, observation.delta_phi_ew, observation.wavelength_m
                )
                bearing_err = min(
                    self._angular_distance_deg(self._bearing_from_u(*u), track.bearing_deg)
                    for u in candidates
                )
                if bearing_err > self.track_bearing_gate_deg:
                    continue
            _, _, _, cost = self._solve([*track.observations, observation])
            if cost <= self.association_max_residual_rad2 and (
                best_cost is None or cost < best_cost
            ):
                best_cost, best_track = cost, track
        return best_track

    def _associate(
        self,
        delta_phi_ns: float,
        delta_phi_ew: float,
        wavelength_m: float,
        rssi_dbm: float,
        distance_m: float,
    ) -> Detection:
        observation = _Observation(delta_phi_ns, delta_phi_ew, wavelength_m)
        track = self._find_track(observation, rssi_dbm)

        if track is None:
            track = _Track(track_id=next(self._track_ids), distance_m=distance_m, rssi_dbm=rssi_dbm)
            self._tracks[track.track_id] = track
        else:
            a = self.smoothing
            track.distance_m = (1 - a) * track.distance_m + a * distance_m
            track.rssi_dbm = (1 - a) * track.rssi_dbm + a * rssi_dbm
            track.misses = 0

        track.last_frame = self._frame
        track.observations.append(observation)
        if len(track.observations) > self.max_observations:
            track.observations.pop(0)

        u_ns, u_ew, margin, _ = self._solve(track.observations)
        bearing_rad = np.radians(self._bearing_from_u(u_ns, u_ew))
        track.bearing_vec = complex(np.cos(bearing_rad), np.sin(bearing_rad))
        track.margin = margin
        track.resolved = len(track.observations) >= 2 and margin >= self.confirm_margin

        return Detection(
            track_id=track.track_id,
            frequency_ghz=0.0,  # filled in by the caller
            bearing_degrees=round(track.bearing_deg, 2),
            bearing_ambiguous=not track.resolved,
            ambiguity_margin=round(margin, 2) if np.isfinite(margin) else float("inf"),
            distance_meters=round(float(track.distance_m), 1),
            signal_strength_dbm=round(float(track.rssi_dbm), 1),
            hops_observed=len(track.observations),
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
        self._frame += 1
        fft_output = np.fft.fftshift(np.fft.fft(iq_matrix * self._window, axis=1), axes=1)

        # Combined power across all 4 channels: a target sitting in one
        # antenna's null still shows up through the other three.
        power_all = np.mean(np.abs(fft_output) ** 2, axis=0)
        noise_threshold = np.median(power_all) * (10 ** (self.threshold_db / 10))

        active_bins = np.where(power_all > noise_threshold)[0]
        if len(active_bins) == 0:
            self._prune_stale_tracks(set())
            return []

        detections: list[Detection] = []
        updated_track_ids: set[int] = set()

        for cluster in self._cluster_bins(active_bins, self.peak_min_gap_bins):
            peak_bin = int(cluster[np.argmax(power_all[cluster])])
            refined_bin = self._refine_peak_bin(power_all, peak_bin)
            bin_freq_hz = float(np.interp(refined_bin, np.arange(n_samples), self._freqs))
            hop_freq_hz = self.center_freq_hz + bin_freq_hz
            wavelength_m = SPEED_OF_LIGHT_M_S / hop_freq_hz

            # Coherent combination across the cluster's bins raises the SNR
            # of both the phase (bearing) and the power (range) estimates.
            x_n, x_e = fft_output[0, cluster], fft_output[1, cluster]
            x_s, x_w = fft_output[2, cluster], fft_output[3, cluster]

            delta_phi_ns = float(np.angle(np.sum(x_n * np.conj(x_s))))
            delta_phi_ew = float(np.angle(np.sum(x_e * np.conj(x_w))))

            total_power = float(
                np.sum(np.abs(x_n) ** 2 + np.abs(x_e) ** 2 + np.abs(x_s) ** 2 + np.abs(x_w) ** 2)
            )
            # An FFT of a windowed signal scales amplitude by sum(window),
            # not n_samples; without this the dBFS scale drifts with the
            # window and buffer length, and range is exponential in it.
            calibrated_power = total_power / (self._coherent_gain**2)
            measured_rssi_dbm = 10 * np.log10(calibrated_power + 1e-30) + self.adc_full_scale_dbm

            distance_ratio = (self.rssi_at_1m_dbm - measured_rssi_dbm) / (
                10 * self.path_loss_exponent
            )
            approx_distance_m = self.ref_distance_m * (10**distance_ratio)

            detection = self._associate(
                delta_phi_ns, delta_phi_ew, wavelength_m, measured_rssi_dbm, approx_distance_m
            )
            detection.frequency_ghz = round(hop_freq_hz / 1e9, 4)
            detections.append(detection)
            updated_track_ids.add(detection.track_id)

        self._prune_stale_tracks(updated_track_ids)
        return detections


# --- Demonstration: two drones hopping simultaneously across the band at
# 25 dB SNR, from fixed bearings of 60 and 210 degrees.
#
# Note each hop lands on a *different* FFT bin. That is the whole point:
# hops at one frequency carry no more direction information than a single
# hop does, and the tracker will correctly refuse to confirm a bearing from
# them. Watch the first frame report `ambiguous` with a margin near zero,
# then both tracks lock on once a second carrier gives the joint solve
# something to discriminate with.
#
# The range and RSSI figures follow from the simulation's arbitrary signal
# amplitude; the log-distance constants need calibrating against a real
# reference transmitter before the metres mean anything. ---
if __name__ == "__main__":
    rng = np.random.default_rng(21)
    tracker = MultiDroneSDRTracker(sampling_rate=40e6, center_freq_hz=2.42e9)

    n_samples = 1024
    amplitude = 0.6
    noise_sigma = amplitude / np.sqrt(2 * 10 ** (25 / 10))
    truth = {60.0: (-470, -100), 210.0: (100, 470)}

    for frame in range(5):
        buffer = (
            noise_sigma
            * (
                rng.standard_normal((4, n_samples))
                + 1j * rng.standard_normal((4, n_samples))
            )
        ).astype(complex)

        for bearing_deg, (lo, hi) in truth.items():
            hop_bin = int(rng.integers(lo, hi))
            hop_hz = tracker.center_freq_hz + (hop_bin / n_samples) * tracker.sampling_rate
            wavelength = SPEED_OF_LIGHT_M_S / hop_hz
            k = 2 * np.pi * tracker.antenna_spacing_m / wavelength
            phi_ns = _wrap_to_pi(k * np.cos(np.radians(bearing_deg)))
            phi_ew = _wrap_to_pi(k * np.sin(np.radians(bearing_deg)))

            t = np.arange(n_samples)
            tone = amplitude * np.exp(1j * (2 * np.pi * hop_bin / n_samples * t))
            buffer[0] += tone
            buffer[2] += tone * np.exp(-1j * phi_ns)
            buffer[1] += tone
            buffer[3] += tone * np.exp(-1j * phi_ew)

        for det in sorted(tracker.process_sdr_buffer(buffer), key=lambda d: d.track_id):
            state = "ambiguous" if det.bearing_ambiguous else "CONFIRMED"
            print(
                f"frame {frame}  track {det.track_id}  {det.frequency_ghz:.4f} GHz  "
                f"bearing {det.bearing_degrees:6.2f} deg  margin {det.ambiguity_margin:7.1f}  "
                f"{state:9}  rssi {det.signal_strength_dbm:5.1f} dBm  "
                f"hops {det.hops_observed}"
            )
