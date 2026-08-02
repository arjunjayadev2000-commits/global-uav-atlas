"""Tests for the drone detection module (detection/).

These tests never load real YOLO weights or open a camera — they exercise the
pure-Python logic (dataset splitting, NMS/threshold post-processing, the
multi-frame fusion tracker) with synthetic data, matching how the rest of
this repo's test suite avoids network/hardware dependencies.
"""

from __future__ import annotations

import numpy as np
import pytest

from detection.config import DatasetConfig, DetectorConfig
from detection.dataset import find_labelled_images, split_dataset, write_darknet_manifests
from detection.detector import Detection, DroneDetector
from detection.fusion import FusionTracker

# --- dataset.py -----------------------------------------------------------


def _make_labelled_pair(images_dir, labels_dir, name, label_line="0 0.5 0.5 0.2 0.2\n"):
    (images_dir / f"{name}.jpg").write_bytes(b"fake-jpeg-bytes")
    (labels_dir / f"{name}.txt").write_text(label_line, encoding="utf-8")


def test_find_labelled_images_skips_unlabelled(tmp_path):
    images_dir = tmp_path / "images"
    labels_dir = tmp_path / "labels"
    images_dir.mkdir(exist_ok=True)
    labels_dir.mkdir(exist_ok=True)

    _make_labelled_pair(images_dir, labels_dir, "drone_0001")
    (images_dir / "drone_0002.jpg").write_bytes(b"no matching label")

    config = DatasetConfig(images_dir=images_dir, labels_dir=labels_dir, output_dir=tmp_path)
    found = find_labelled_images(config)

    assert [p.name for p in found] == ["drone_0001.jpg"]


def test_split_dataset_is_80_20_and_deterministic(tmp_path):
    images_dir = tmp_path / "images"
    labels_dir = tmp_path / "labels"
    images_dir.mkdir(exist_ok=True)
    labels_dir.mkdir(exist_ok=True)
    for i in range(100):
        _make_labelled_pair(images_dir, labels_dir, f"img_{i:04d}")

    config = DatasetConfig(images_dir=images_dir, labels_dir=labels_dir, output_dir=tmp_path)
    split_a = split_dataset(config)
    split_b = split_dataset(config)

    assert len(split_a.train_images) == 80
    assert len(split_a.test_images) == 20
    assert split_a.total == 100
    # Same seed -> same split, every time.
    assert [p.name for p in split_a.train_images] == [p.name for p in split_b.train_images]


def test_write_darknet_manifests_contents(tmp_path):
    images_dir = tmp_path / "images"
    labels_dir = tmp_path / "labels"
    images_dir.mkdir(exist_ok=True)
    labels_dir.mkdir(exist_ok=True)
    for i in range(10):
        _make_labelled_pair(images_dir, labels_dir, f"img_{i:04d}")

    config = DatasetConfig(
        images_dir=images_dir,
        labels_dir=labels_dir,
        output_dir=tmp_path,
        class_names=("drone", "bird"),
    )
    split = split_dataset(config)
    manifests = write_darknet_manifests(config, split)

    assert manifests["names"].read_text(encoding="utf-8").splitlines() == ["drone", "bird"]
    train_lines = manifests["train"].read_text(encoding="utf-8").splitlines()
    test_lines = manifests["test"].read_text(encoding="utf-8").splitlines()
    assert len(train_lines) == len(split.train_images)
    assert len(test_lines) == len(split.test_images)
    data_text = manifests["data"].read_text(encoding="utf-8")
    assert "classes = 2" in data_text


# --- detector.py: post-processing (no model file / GPU required) ----------


def _bare_detector(confidence_threshold=0.5, nms_threshold=0.4, target_classes=("drone",)):
    """A DroneDetector-shaped object with only what _postprocess touches set."""
    detector = DroneDetector.__new__(DroneDetector)
    detector.config = DetectorConfig(
        confidence_threshold=confidence_threshold,
        nms_threshold=nms_threshold,
        target_classes=target_classes,
    )
    detector.class_names = ["drone", "bird"]
    return detector


def _raw_detection(cx, cy, w, h, drone_score, bird_score):
    # Darknet output row: [cx, cy, w, h, objectness, class_0_score, class_1_score]
    return [cx, cy, w, h, 1.0, drone_score, bird_score]


def test_postprocess_filters_low_confidence():
    detector = _bare_detector(confidence_threshold=0.6)
    layer_outputs = [np.array([_raw_detection(0.5, 0.5, 0.2, 0.2, 0.3, 0.1)])]

    detections = detector._postprocess(layer_outputs, width=640, height=480)

    assert detections == []


def test_postprocess_returns_labelled_target_detection():
    detector = _bare_detector(confidence_threshold=0.5)
    layer_outputs = [np.array([_raw_detection(0.5, 0.5, 0.2, 0.2, 0.9, 0.05)])]

    detections = detector._postprocess(layer_outputs, width=640, height=480)

    assert len(detections) == 1
    det = detections[0]
    assert isinstance(det, Detection)
    assert det.label == "drone"
    assert det.is_target is True
    assert det.confidence == pytest.approx(0.9)
    x, y, w, h = det.box
    assert w == pytest.approx(640 * 0.2, abs=1)
    assert h == pytest.approx(480 * 0.2, abs=1)


def test_postprocess_non_target_class_is_not_flagged():
    detector = _bare_detector(confidence_threshold=0.5, target_classes=("drone",))
    layer_outputs = [np.array([_raw_detection(0.5, 0.5, 0.2, 0.2, 0.1, 0.95)])]

    detections = detector._postprocess(layer_outputs, width=640, height=480)

    assert len(detections) == 1
    assert detections[0].label == "bird"
    assert detections[0].is_target is False


def test_postprocess_suppresses_duplicate_overlapping_boxes():
    detector = _bare_detector(confidence_threshold=0.5, nms_threshold=0.4)
    # Two near-identical boxes for the same object -> NMS should keep one.
    layer_outputs = [
        np.array(
            [
                _raw_detection(0.50, 0.50, 0.20, 0.20, 0.90, 0.0),
                _raw_detection(0.51, 0.51, 0.20, 0.20, 0.85, 0.0),
            ]
        )
    ]

    detections = detector._postprocess(layer_outputs, width=640, height=480)

    assert len(detections) == 1


# --- fusion.py --------------------------------------------------------------


def _det(label="drone", box=(100, 100, 50, 50), confidence=0.9):
    return Detection(class_id=0, label=label, confidence=confidence, box=box, is_target=True)


def test_track_requires_min_hits_before_confirming():
    tracker = FusionTracker(min_hits=3)

    assert tracker.update([_det()]) == []  # hit 1
    assert tracker.update([_det()]) == []  # hit 2
    confirmed = tracker.update([_det()])  # hit 3 -> confirmed

    assert len(confirmed) == 1
    assert confirmed[0].label == "drone"


def test_single_frame_flicker_is_not_reported():
    tracker = FusionTracker(min_hits=3, max_misses=0)

    assert tracker.update([_det()]) == []
    # Object vanishes for a frame; with max_misses=0 the track is dropped
    # immediately rather than surviving to be (wrongly) confirmed later.
    assert tracker.update([]) == []
    assert tracker.update([_det()]) == []


def test_track_dropped_after_max_misses():
    tracker = FusionTracker(min_hits=1, max_misses=1)
    tracker.update([_det()])  # confirmed immediately (min_hits=1)

    tracker.update([])  # miss 1 (still within max_misses)
    remaining = tracker.update([])  # miss 2 -> dropped

    assert remaining == []


def test_external_confirm_can_veto_a_track():
    tracker = FusionTracker(min_hits=1, external_confirm=lambda track: False)

    confirmed = tracker.update([_det()])

    assert confirmed == []


def test_external_confirm_abstain_falls_back_to_visual():
    tracker = FusionTracker(min_hits=1, external_confirm=lambda track: None)

    confirmed = tracker.update([_det()])

    assert len(confirmed) == 1
