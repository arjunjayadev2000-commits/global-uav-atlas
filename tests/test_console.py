"""Tests for the tactical console: HUD, simulator, state engine and server.

Like ``test_detection.py`` these never need a camera, a display or model
weights — the simulated frame source stands in for real hardware, which is
exactly what it exists for.
"""

from __future__ import annotations

import numpy as np
import pytest

from detection.console_state import THREAT_LEVELS, ConsoleState
from detection.detector import Detection
from detection.fusion import FusionTracker, Track
from detection.hud import HudContact, bearing_for, render
from detection.server import DetectionEngine, create_app
from detection.sources import SimulatedSource

# --- hud.py -----------------------------------------------------------------


def test_render_does_not_change_frame_shape():
    frame = np.zeros((240, 320, 3), np.uint8)
    out = render(frame, [HudContact(1, "drone", 0.9, (40, 40, 60, 40), threat=True)], fps=25.0)

    assert out.shape == (240, 320, 3)
    assert out.dtype == np.uint8


def test_render_actually_draws_something():
    blank = np.zeros((240, 320, 3), np.uint8)
    drawn = render(blank.copy(), [HudContact(1, "drone", 0.9, (40, 40, 60, 40))], fps=25.0)

    assert drawn.any(), "HUD render produced an entirely black frame"


def test_render_survives_boxes_outside_the_frame():
    # A contact leaving the frame must not raise or corrupt the image.
    frame = np.zeros((240, 320, 3), np.uint8)
    contacts = [
        HudContact(1, "drone", 0.8, (-80, -40, 60, 40)),
        HudContact(2, "drone", 0.8, (300, 220, 90, 70)),
    ]
    assert render(frame, contacts, fps=10.0).shape == (240, 320, 3)


@pytest.mark.parametrize(
    ("box", "expect_sign"),
    [((0, 0, 20, 20), -1), ((300, 0, 20, 20), 1)],
)
def test_bearing_sign_follows_horizontal_position(box, expect_sign):
    bearing = bearing_for(box, frame_width=320)
    assert (bearing > 0) == (expect_sign > 0)


def test_bearing_is_zero_at_centre():
    assert bearing_for((150, 0, 20, 20), frame_width=320) == pytest.approx(0.0, abs=0.5)


# --- sources.py -------------------------------------------------------------


def test_simulated_source_yields_frames_and_detections():
    src = SimulatedSource(width=320, height=240, fps=1000)  # fps high so it doesn't sleep
    result = src.read()

    assert result is not None
    frame, detections = result
    assert frame.shape == (240, 320, 3)
    assert all(isinstance(d, Detection) for d in detections)
    assert any(d.label == "drone" for d in detections)


def test_simulated_detections_stay_within_expected_labels():
    src = SimulatedSource(width=320, height=240, fps=1000)
    labels = set()
    for _ in range(20):
        _, detections = src.read()
        labels.update(d.label for d in detections)

    assert labels <= {"drone", "bird"}


# --- fusion.py: velocity prediction ----------------------------------------


def test_fast_small_contact_keeps_one_track_id():
    """A small target moving several px/frame must not shed its track.

    This is the regression guard for the lag-induced churn that split one
    moving contact into a stream of one-frame tracks.
    """
    tracker = FusionTracker(min_hits=2)
    ids = set()
    x, y, size = 10, 100, 26
    for step in range(40):
        det = Detection(0, "drone", 0.9, (x + step * 5, y + (step % 3), size, size), True)
        for track in tracker.update([det]):
            ids.add(track.track_id)

    assert len(ids) == 1, f"expected a single stable track, got {sorted(ids)}"


def test_track_coasts_through_a_brief_dropout():
    tracker = FusionTracker(min_hits=2, max_misses=3)
    for step in range(6):
        tracker.update([Detection(0, "drone", 0.9, (10 + step * 6, 50, 30, 30), True)])

    before = {t.track_id for t in tracker.update([])}  # one dropped frame
    after = {t.track_id for t in tracker.update([Detection(0, "drone", 0.9, (52, 50, 30, 30), True)])}

    assert before and before == after, "track should survive and re-attach after a dropout"


def test_velocity_is_estimated_from_motion():
    tracker = FusionTracker(min_hits=1)
    for step in range(8):
        tracker.update([Detection(0, "drone", 0.9, (step * 10, 40, 30, 30), True)])

    (track,) = tracker._tracks
    vx, _ = track.velocity
    assert vx > 3, f"expected a positive rightward velocity estimate, got {vx}"


# --- console_state.py -------------------------------------------------------


def _track(track_id=1, label="drone", confidence=0.9, box=(10.0, 10.0, 40.0, 40.0)):
    return Track(track_id=track_id, label=label, box=box, confidence=confidence, confirmed=True)


@pytest.mark.parametrize(
    ("hostiles", "confidence", "expected"),
    [
        (0, 0.0, "CLEAR"),
        (1, 0.50, "GUARDED"),
        (1, 0.70, "ELEVATED"),
        (1, 0.95, "CRITICAL"),
        (2, 0.40, "CRITICAL"),
    ],
)
def test_threat_level_mapping(hostiles, confidence, expected):
    assert ConsoleState.threat_level_for(hostiles, confidence) == expected
    assert expected in THREAT_LEVELS


def test_state_reports_hostile_drone_and_benign_bird():
    state = ConsoleState(frame_width=320)
    state.ingest([_track(1, "drone", 0.92), _track(2, "bird", 0.71)])
    snap = state.snapshot()

    assert snap["contact_count"] == 2
    assert snap["hostile_count"] == 1
    assert snap["threat_level"] == "CRITICAL"
    labels = {c["label"]: c["hostile"] for c in snap["contacts"]}
    assert labels == {"DRONE": True, "BIRD": False}


def test_state_logs_acquisition_then_loss():
    state = ConsoleState(frame_width=320)
    state.ingest([_track(7, "drone", 0.9)])
    state.ingest([])  # track retired by the fusion layer

    kinds = [e["kind"] for e in state.snapshot()["events"]]
    assert "THREAT" in kinds
    assert "LOST" in kinds


def test_state_snapshot_is_json_safe():
    import json

    state = ConsoleState(frame_width=320)
    state.ingest([_track()])
    json.dumps(state.snapshot())  # must not raise


def test_clear_when_no_contacts():
    snap = ConsoleState(frame_width=320).snapshot()

    assert snap["threat_level"] == "CLEAR"
    assert snap["contacts"] == []


# --- server.py --------------------------------------------------------------


@pytest.fixture
def client():
    source = SimulatedSource(width=320, height=240, fps=1000)
    engine = DetectionEngine(source, mode="SIMULATION")
    app = create_app(engine)
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client, engine
    engine.stop()


def test_index_serves_the_console(client):
    test_client, _ = client
    response = test_client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "UAV-DET" in body
    assert "/stream.mjpg" in body


def test_state_endpoint_shape(client):
    test_client, _ = client
    payload = test_client.get("/api/state").get_json()

    assert set(payload) >= {"threat_level", "contacts", "events", "telemetry"}
    assert payload["telemetry"]["mode"] == "SIMULATION"


def test_healthz(client):
    test_client, _ = client
    assert test_client.get("/healthz").get_json()["ok"] is True
