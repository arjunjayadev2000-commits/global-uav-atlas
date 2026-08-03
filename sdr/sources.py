"""IQ sources for the tracker: simulated, recorded, and live hardware.

The tracker only ever needs a ``(4, N)`` complex array per frame, so the
source behind it is interchangeable. Three are provided:

* :class:`SimulatedSource` synthesises drones with known bearings, so the
  application is runnable and testable with no radio attached and there is
  a ground truth to check the display against.
* :class:`FileSource` replays a recorded capture.
* :class:`FMComms5Source` drives real hardware -- an FMCOMMS5 is two
  phase-synchronised AD9361s presenting exactly the four coherent receive
  channels this tracker assumes.

Channel order is fixed everywhere: 0 = North, 1 = East, 2 = South, 3 = West.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from sdr.multi_drone_tracker import SPEED_OF_LIGHT_M_S

#: A Hann-windowed on-bin tone puts half-amplitude leakage in each adjacent
#: bin, so the tracker's per-hop cluster carries 1 + 2*(1/2)**2 times the
#: peak bin's power. Inverting the range model without this leaves simulated
#: ranges about 17% short.
_HANN_CLUSTER_POWER_FACTOR = 1.5


class IQSource(ABC):
    """A source of coherent 4-channel IQ frames."""

    sample_rate: float
    center_freq_hz: float
    buffer_size: int

    @abstractmethod
    def read(self) -> np.ndarray:
        """Return the next ``(4, buffer_size)`` complex frame."""

    def close(self) -> None:  # pragma: no cover - trivial default
        """Release any hardware or file handles."""

    @property
    def description(self) -> str:
        return type(self).__name__

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


# ----------------------------------------------------------------------
# Simulation
# ----------------------------------------------------------------------


@dataclass
class SimulatedDrone:
    """A synthetic frequency-hopping emitter at a known bearing.

    ``hop_channels`` lists the carriers it may hop between, in Hz. Leaving
    it empty means "hop anywhere in the passband", which is the case the
    tracker handles best; setting it to a single channel reproduces the
    degenerate no-frequency-diversity case, where the tracker should
    correctly refuse to confirm a bearing.
    """

    bearing_deg: float
    range_m: float = 100.0
    #: Leave as None to derive the transmit amplitude from ``range_m`` through
    #: the same log-distance model the tracker inverts, so the range it
    #: reports round-trips back to this value. Set it explicitly to drive the
    #: signal level directly and ignore range.
    amplitude: float | None = None
    hop_channels: list[float] = field(default_factory=list)
    #: Angular velocity, so tracks can be seen to move rather than sit still.
    bearing_rate_deg_s: float = 0.0
    #: Frames the emitter stays on one carrier before hopping.
    dwell_frames: int = 1
    label: str = ""


class SimulatedSource(IQSource):
    """Synthesise coherent 4-channel frames from a list of drones.

    Phases are generated from the same geometry the tracker inverts, so a
    correct tracker recovers ``bearing_deg`` exactly. Note that means this
    validates the signal processing, not the hardware assumptions -- it
    models a clean plane wave with perfectly matched channels, no mutual
    coupling and no multipath.
    """

    def __init__(
        self,
        drones: list[SimulatedDrone] | None = None,
        sample_rate: float = 40e6,
        center_freq_hz: float = 2.44e9,
        buffer_size: int = 1024,
        antenna_spacing_m: float = 0.245,
        snr_db: float = 25.0,
        seed: int | None = None,
        rssi_at_1m_dbm: float = -25.0,
        path_loss_exponent: float = 2.2,
        adc_full_scale_dbm: float = 10.0,
    ):
        self.sample_rate = sample_rate
        self.center_freq_hz = center_freq_hz
        self.buffer_size = buffer_size
        self.antenna_spacing_m = antenna_spacing_m
        self.snr_db = snr_db
        self.rssi_at_1m_dbm = rssi_at_1m_dbm
        self.path_loss_exponent = path_loss_exponent
        self.adc_full_scale_dbm = adc_full_scale_dbm
        # `drones=[]` means "no emitters, noise only" and must not collapse
        # to the default the way a falsy check would make it.
        self.drones = [SimulatedDrone(bearing_deg=60.0)] if drones is None else list(drones)
        self._rng = np.random.default_rng(seed)
        self._frame = 0
        self._current_bins: dict[int, int] = {}

    def amplitude_for(self, drone: SimulatedDrone) -> float:
        """Tone amplitude that makes the tracker report ``drone.range_m``.

        An on-bin complex tone of amplitude A gives ``|X| = A*sum(window)``
        per channel, so the tracker's coherent-gain-corrected power over
        four channels is ``4*A**2``, times the window leakage the hop's bin
        cluster picks up. Its RSSI is therefore
        ``20*log10(A) + 10*log10(4 * leakage) + adc_full_scale``. Inverting
        the log-distance model for the desired range gives the amplitude
        below, so the range the tracker reports round-trips to ``range_m``.
        """
        if drone.amplitude is not None:
            return drone.amplitude
        rssi = self.rssi_at_1m_dbm - 10 * self.path_loss_exponent * np.log10(
            max(drone.range_m, 0.1)
        )
        gain_db = 10 * np.log10(4 * _HANN_CLUSTER_POWER_FACTOR) + self.adc_full_scale_dbm
        return float(10 ** ((rssi - gain_db) / 20))

    @property
    def description(self) -> str:
        return f"Simulated ({len(self.drones)} drone{'s' if len(self.drones) != 1 else ''})"

    def _hop_bin(self, index: int, drone: SimulatedDrone) -> int:
        """Pick this frame's FFT bin for a drone, honouring its dwell time."""
        if self._frame % max(drone.dwell_frames, 1) == 0 or index not in self._current_bins:
            if drone.hop_channels:
                channel = float(self._rng.choice(drone.hop_channels))
                offset = channel - self.center_freq_hz
                self._current_bins[index] = round(offset / self.sample_rate * self.buffer_size)
            else:
                limit = int(self.buffer_size * 0.46)  # stay clear of the band edges
                self._current_bins[index] = int(self._rng.integers(-limit, limit))
        return self._current_bins[index]

    def read(self) -> np.ndarray:
        n = self.buffer_size
        amplitudes = [self.amplitude_for(d) for d in self.drones]
        # SNR is quoted against the strongest emitter, so more distant ones
        # are correspondingly weaker rather than all being equally loud.
        peak = max(amplitudes, default=0.6)
        sigma = peak / np.sqrt(2 * 10 ** (self.snr_db / 10))
        frame = (
            sigma * (self._rng.standard_normal((4, n)) + 1j * self._rng.standard_normal((4, n)))
        ).astype(complex)

        seconds = self._frame * n / self.sample_rate
        t = np.arange(n)

        for index, drone in enumerate(self.drones):
            hop_bin = self._hop_bin(index, drone)
            hop_hz = self.center_freq_hz + (hop_bin / n) * self.sample_rate
            wavelength = SPEED_OF_LIGHT_M_S / hop_hz

            bearing = drone.bearing_deg + drone.bearing_rate_deg_s * seconds
            k = 2 * np.pi * self.antenna_spacing_m / wavelength
            phi_ns = k * np.cos(np.radians(bearing))
            phi_ew = k * np.sin(np.radians(bearing))

            tone = amplitudes[index] * np.exp(1j * (2 * np.pi * hop_bin / n * t))
            frame[0] += tone
            frame[2] += tone * np.exp(-1j * phi_ns)
            frame[1] += tone
            frame[3] += tone * np.exp(-1j * phi_ew)

        self._frame += 1
        return frame

    def truth_bearings(self) -> list[float]:
        """Current true bearings, for validating a display against."""
        seconds = self._frame * self.buffer_size / self.sample_rate
        return [
            (d.bearing_deg + d.bearing_rate_deg_s * seconds) % 360 for d in self.drones
        ]


# ----------------------------------------------------------------------
# Recorded capture
# ----------------------------------------------------------------------


class FileSource(IQSource):
    """Replay a recorded capture stored as a ``(4, total_samples)`` .npy file."""

    def __init__(
        self,
        path: str,
        sample_rate: float = 40e6,
        center_freq_hz: float = 2.44e9,
        buffer_size: int = 1024,
        loop: bool = True,
    ):
        self._data = np.load(path)
        if self._data.ndim != 2 or self._data.shape[0] != 4:
            raise ValueError(
                f"expected an array shaped (4, total_samples), got {self._data.shape}"
            )
        if not np.iscomplexobj(self._data):
            raise ValueError("recorded capture must be complex IQ, not real samples")
        self.path = path
        self.sample_rate = sample_rate
        self.center_freq_hz = center_freq_hz
        self.buffer_size = buffer_size
        self.loop = loop
        self._offset = 0

    @property
    def description(self) -> str:
        return f"File ({self.path})"

    def read(self) -> np.ndarray:
        total = self._data.shape[1]
        if self._offset + self.buffer_size > total:
            if not self.loop:
                raise EOFError("end of recorded capture")
            self._offset = 0
        frame = self._data[:, self._offset : self._offset + self.buffer_size]
        self._offset += self.buffer_size
        return frame


# ----------------------------------------------------------------------
# Live hardware
# ----------------------------------------------------------------------


class FMComms5Source(IQSource):
    """Live capture from an FMCOMMS5 (two phase-synchronised AD9361s).

    The FMCOMMS5 exposes four coherent receive channels off a shared LO,
    which is what makes the inter-channel phase comparison meaningful. Map
    the antennas to channels in the documented order (0 = North, 1 = East,
    2 = South, 3 = West) or every bearing will be rotated or mirrored.

    Two things to do before trusting bearings from real hardware:

    * Run a phase calibration. Inject one common reference into all four
      inputs and record the per-channel phase offsets, then pass them as
      ``phase_correction_rad``. Cable and filter mismatch otherwise adds a
      fixed bias to every bearing.
    * Disable AGC (this class sets manual gain by default) and use equal
      gain on all channels, since the range estimate compares amplitudes
      across channels.

    This path cannot be exercised without the radio attached, so it is not
    covered by the test suite.
    """

    def __init__(
        self,
        uri: str = "ip:192.168.2.1",
        sample_rate: float = 40e6,
        center_freq_hz: float = 2.44e9,
        buffer_size: int = 1024,
        gain_db: float = 40.0,
        bandwidth_hz: float | None = None,
        phase_correction_rad: np.ndarray | None = None,
    ):
        try:
            import adi
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise ImportError(
                "live capture needs pyadi-iio: pip install 'global-uav-atlas[sdr-hardware]'"
            ) from exc

        self.uri = uri
        self.sample_rate = sample_rate
        self.center_freq_hz = center_freq_hz
        self.buffer_size = buffer_size
        self.phase_correction = phase_correction_rad

        self._dev = adi.FMComms5(uri=uri)
        self._dev.rx_enabled_channels = [0, 1, 2, 3]
        self._dev.rx_lo = int(center_freq_hz)
        self._dev.rx_lo_chip_b = int(center_freq_hz)  # keep both AD9361s on one frequency
        self._dev.sample_rate = int(sample_rate)
        self._dev.rx_rf_bandwidth = int(bandwidth_hz or sample_rate)
        self._dev.rx_buffer_size = buffer_size

        # Manual, equal gain on every channel: AGC would move the channels
        # independently and corrupt both the amplitude and phase comparisons.
        for attr in ("gain_control_mode_chan0", "gain_control_mode_chan1"):
            if hasattr(self._dev, attr):
                setattr(self._dev, attr, "manual")
        for attr in ("rx_hardwaregain_chan0", "rx_hardwaregain_chan1"):
            if hasattr(self._dev, attr):
                setattr(self._dev, attr, gain_db)

    @property
    def description(self) -> str:
        return f"FMCOMMS5 ({self.uri})"

    def read(self) -> np.ndarray:
        frame = np.asarray(self._dev.rx(), dtype=complex)
        if frame.shape[0] != 4:
            raise RuntimeError(
                f"expected 4 coherent channels from the FMCOMMS5, got {frame.shape[0]}"
            )
        if self.phase_correction is not None:
            frame = frame * np.exp(-1j * np.asarray(self.phase_correction))[:, None]
        return frame

    def close(self) -> None:  # pragma: no cover - hardware only
        dev = getattr(self, "_dev", None)
        if dev is not None and hasattr(dev, "rx_destroy_buffer"):
            dev.rx_destroy_buffer()
