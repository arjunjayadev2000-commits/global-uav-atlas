"""Dataset preparation for training the drone/bird YOLO model.

This module does not ship the ~2,395-image dataset (drones + birds) itself —
image datasets of that size belong in dedicated storage, not in a git repo.
What it does is the repeatable, deterministic part: given a directory of
images with matching YOLO-format label files, split them 80/20 into train and
test sets and emit the Darknet training manifests (``train.txt``,
``test.txt``, ``obj.names``, ``obj.data``) that ``darknet detector train`` or
any YOLOv3/v4 training script expects.

Expected input layout::

    dataset/images/drone_0001.jpg
    dataset/images/bird_0001.jpg
    dataset/labels/drone_0001.txt   # "<class_id> <cx> <cy> <w> <h>" per box, normalized 0-1
    dataset/labels/bird_0001.txt
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from detection.config import DatasetConfig


@dataclass
class SplitResult:
    train_images: list[Path]
    test_images: list[Path]

    @property
    def total(self) -> int:
        return len(self.train_images) + len(self.test_images)


def find_labelled_images(config: DatasetConfig) -> list[Path]:
    """Return every image under ``images_dir`` that has a matching label file.

    Images without a corresponding ``.txt`` label are skipped rather than
    raising, since partially-annotated drops are the normal state of an
    in-progress dataset.
    """
    images_dir = Path(config.images_dir)
    labels_dir = Path(config.labels_dir)
    if not images_dir.is_dir():
        raise FileNotFoundError(f"images_dir does not exist: {images_dir}")

    labelled = [
        image_path
        for image_path in sorted(images_dir.iterdir())
        if image_path.suffix.lower() in config.image_extensions
        and (labels_dir / f"{image_path.stem}.txt").is_file()
    ]
    return labelled


def split_dataset(config: DatasetConfig, images: list[Path] | None = None) -> SplitResult:
    """Deterministically shuffle and split images into train/test sets.

    A fixed seed (``config.seed``) makes the split reproducible across runs —
    important so re-running dataset prep doesn't silently leak test images
    into a later training run.
    """
    candidates = list(images) if images is not None else find_labelled_images(config)
    rng = random.Random(config.seed)
    shuffled = candidates[:]
    rng.shuffle(shuffled)

    split_index = round(len(shuffled) * config.train_fraction)
    return SplitResult(train_images=shuffled[:split_index], test_images=shuffled[split_index:])


def write_darknet_manifests(config: DatasetConfig, split: SplitResult) -> dict[str, Path]:
    """Write ``train.txt``, ``test.txt``, ``obj.names`` and ``obj.data``.

    Returns a mapping of manifest name to the path it was written to, so
    callers (and tests) can inspect the result without re-deriving paths.
    """
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_path = output_dir / "train.txt"
    test_path = output_dir / "test.txt"
    names_path = output_dir / "obj.names"
    data_path = output_dir / "obj.data"
    backup_dir = output_dir / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    train_path.write_text(
        "\n".join(str(p.resolve()) for p in split.train_images) + "\n" if split.train_images else "",
        encoding="utf-8",
    )
    test_path.write_text(
        "\n".join(str(p.resolve()) for p in split.test_images) + "\n" if split.test_images else "",
        encoding="utf-8",
    )
    names_path.write_text("\n".join(config.class_names) + "\n", encoding="utf-8")
    data_path.write_text(
        "\n".join(
            [
                f"classes = {len(config.class_names)}",
                f"train = {train_path.resolve()}",
                f"valid = {test_path.resolve()}",
                f"names = {names_path.resolve()}",
                f"backup = {backup_dir.resolve()}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "train": train_path,
        "test": test_path,
        "names": names_path,
        "data": data_path,
    }


def prepare(config: DatasetConfig | None = None) -> SplitResult:
    """Convenience entry point: find images, split 80/20, write manifests."""
    config = config or DatasetConfig()
    split = split_dataset(config)
    write_darknet_manifests(config, split)
    return split


if __name__ == "__main__":
    result = prepare()
    print(
        f"Found {result.total} labelled images -> "
        f"{len(result.train_images)} train / {len(result.test_images)} test"
    )
