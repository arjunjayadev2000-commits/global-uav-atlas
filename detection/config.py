"""Configuration for the real-time YOLOv3/YOLOv4 drone detector.

Every tunable is a plain dataclass field with a sensible default rather than an
environment lookup, because this module is meant to be readable end to end by
someone who has never opened the rest of the repository. Override fields with
keyword arguments when constructing :class:`DetectorConfig`, or edit the
defaults below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DETECTION_ROOT = Path(__file__).resolve().parent
MODELS_DIR = DETECTION_ROOT / "models"

#: Darknet input resolutions YOLOv3/v4 support out of the box. 416 is the
#: standard speed/accuracy balance; 608 trades FPS for better small-object
#: (distant drone) recall. Both must be multiples of 32.
SUPPORTED_INPUT_SIZES = (320, 416, 512, 608)


@dataclass
class DetectorConfig:
    """Everything the detector needs to load a model and run inference.

    ``cfg_path`` / ``weights_path`` / ``names_path`` point at the standard
    three Darknet files (see ``detection/README.md`` for exactly where to get
    them). Nothing in this module downloads or ships model weights — they are
    hundreds of megabytes and licensed separately from this code.
    """

    cfg_path: Path = MODELS_DIR / "yolov4.cfg"
    weights_path: Path = MODELS_DIR / "yolov4.weights"
    names_path: Path = MODELS_DIR / "obj.names"

    # Darknet input size. 416x416 for the target hardware (i7-9750H / GTX
    # 1660 Ti) comfortably clears real-time (>20 FPS); step up to 608x608 only
    # if small/distant drones are being missed and the extra latency is
    # affordable.
    input_size: int = 416

    confidence_threshold: float = 0.5
    nms_threshold: float = 0.4

    # Which class names (from names_path) count as "drone" detections worth
    # alerting on. Everything else (e.g. "bird", trained as a hard-negative
    # class in the source dataset) is detected but not surfaced as an alert.
    target_classes: tuple[str, ...] = ("drone",)

    # Backend/target selection. "auto" tries CUDA first (GTX 1660 Ti supports
    # FP16 inference, roughly 2x the throughput of CPU-only) and falls back to
    # CPU transparently if OpenCV wasn't built with CUDA support.
    backend: str = "auto"  # "auto" | "cuda" | "cpu"
    use_fp16: bool = True

    def __post_init__(self) -> None:
        if self.input_size not in SUPPORTED_INPUT_SIZES:
            raise ValueError(
                f"input_size must be one of {SUPPORTED_INPUT_SIZES}, got {self.input_size}"
            )
        if not 0.0 < self.confidence_threshold < 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1")
        if not 0.0 < self.nms_threshold < 1.0:
            raise ValueError("nms_threshold must be between 0 and 1")

    def class_names(self) -> list[str]:
        """Read the class-name file (one label per line, Darknet convention)."""
        text = Path(self.names_path).read_text(encoding="utf-8")
        return [line.strip() for line in text.splitlines() if line.strip()]


@dataclass
class DatasetConfig:
    """Paths and split ratio for the drone/bird training dataset.

    Matches the dataset shape described alongside this detector: ~2,395
    labelled images across two classes (drone, bird — birds are included as a
    hard-negative class so the model learns to tell them apart from drones at
    a distance), split 80/20 train/test.
    """

    images_dir: Path = DETECTION_ROOT / "dataset" / "images"
    labels_dir: Path = DETECTION_ROOT / "dataset" / "labels"
    output_dir: Path = DETECTION_ROOT / "dataset"
    class_names: tuple[str, ...] = ("drone", "bird")
    train_fraction: float = 0.8
    seed: int = 42
    image_extensions: tuple[str, ...] = field(
        default_factory=lambda: (".jpg", ".jpeg", ".png", ".bmp")
    )

    def __post_init__(self) -> None:
        if not 0.0 < self.train_fraction < 1.0:
            raise ValueError("train_fraction must be between 0 and 1")
