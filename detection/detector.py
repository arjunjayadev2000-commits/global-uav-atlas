"""YOLOv3/YOLOv4 drone detector built on OpenCV's DNN module.

OpenCV's ``cv2.dnn`` was chosen over a full deep-learning framework
(PyTorch/TensorFlow) for the inference path because it has no Python-side
autograd overhead, ships a native CUDA backend that runs well on a GTX 1660
Ti, and has no dependency beyond ``opencv-python`` / ``opencv-contrib-python``
— important for a field-deployable script that a non-coder needs to keep
running.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from detection.config import DetectorConfig


@dataclass
class Detection:
    """One detected object in a single frame, in pixel coordinates."""

    class_id: int
    label: str
    confidence: float
    box: tuple[int, int, int, int]  # x, y, w, h — top-left origin
    is_target: bool = False  # True if label is in DetectorConfig.target_classes


class DroneDetector:
    """Loads a Darknet YOLOv3/v4 model once and runs repeated inference on frames."""

    def __init__(self, config: DetectorConfig | None = None) -> None:
        self.config = config or DetectorConfig()
        self._validate_model_files()
        self.class_names = self.config.class_names()
        self.net = self._load_network()
        self.output_layers = self._resolve_output_layers()

    def _validate_model_files(self) -> None:
        missing = [
            str(path)
            for path in (self.config.cfg_path, self.config.weights_path, self.config.names_path)
            if not Path(path).is_file()
        ]
        if missing:
            raise FileNotFoundError(
                "Missing model file(s): "
                + ", ".join(missing)
                + ". See detection/README.md for where to download the YOLOv4 "
                "cfg/weights/names files, or point DetectorConfig at your own."
            )

    def _load_network(self) -> cv2.dnn.Net:
        net = cv2.dnn.readNetFromDarknet(str(self.config.cfg_path), str(self.config.weights_path))
        backend, target = self._resolve_backend_target(net)
        net.setPreferableBackend(backend)
        net.setPreferableTarget(target)
        return net

    def _resolve_backend_target(self, net: cv2.dnn.Net) -> tuple[int, int]:
        """Pick CUDA if available and requested, otherwise fall back to CPU.

        Tuned for the reference deployment hardware (Intel i7-9750H CPU +
        NVIDIA GTX 1660 Ti GPU): CUDA + FP16 roughly doubles throughput over
        CPU on that card, but the CPU path alone still holds real-time (>15
        FPS) at 416x416, so this never hard-fails when CUDA isn't present.
        """
        want_cuda = self.config.backend in ("auto", "cuda")
        cuda_available = cv2.cuda.getCudaEnabledDeviceCount() > 0 if want_cuda else False

        if want_cuda and cuda_available:
            target = (
                cv2.dnn.DNN_TARGET_CUDA_FP16 if self.config.use_fp16 else cv2.dnn.DNN_TARGET_CUDA
            )
            return cv2.dnn.DNN_BACKEND_CUDA, target

        if self.config.backend == "cuda" and not cuda_available:
            raise RuntimeError(
                "backend='cuda' requested but no CUDA-enabled OpenCV device was found; "
                "install opencv built with CUDA support or set backend='cpu'/'auto'."
            )

        return cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU

    def _resolve_output_layers(self) -> list[str]:
        layer_names = self.net.getLayerNames()
        unconnected = self.net.getUnconnectedOutLayers()
        # OpenCV versions differ on whether this comes back as a flat array
        # or a column vector of arrays.
        indices = unconnected.flatten() if hasattr(unconnected, "flatten") else unconnected
        return [layer_names[i - 1] for i in indices]

    def preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Resize to the configured square input and scale pixels to [0, 1].

        ``cv2.dnn.blobFromImage`` handles the BGR->RGB swap, resize and the
        1/255 normalization Darknet models were trained with in one call.
        """
        size = self.config.input_size
        return cv2.dnn.blobFromImage(
            frame, scalefactor=1 / 255.0, size=(size, size), swapRB=True, crop=False
        )

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Run one forward pass and return post-NMS detections in pixel coordinates."""
        height, width = frame.shape[:2]
        blob = self.preprocess(frame)
        self.net.setInput(blob)
        layer_outputs = self.net.forward(self.output_layers)
        return self._postprocess(layer_outputs, width, height)

    def _postprocess(
        self, layer_outputs: Sequence[np.ndarray], width: int, height: int
    ) -> list[Detection]:
        boxes: list[list[int]] = []
        confidences: list[float] = []
        class_ids: list[int] = []

        for output in layer_outputs:
            for detection in output:
                scores = detection[5:]
                class_id = int(np.argmax(scores))
                confidence = float(scores[class_id])
                if confidence < self.config.confidence_threshold:
                    continue

                cx, cy, w, h = detection[0:4]
                box_w, box_h = int(w * width), int(h * height)
                x = int(cx * width - box_w / 2)
                y = int(cy * height - box_h / 2)

                boxes.append([x, y, box_w, box_h])
                confidences.append(confidence)
                class_ids.append(class_id)

        if not boxes:
            return []

        keep = cv2.dnn.NMSBoxes(
            boxes, confidences, self.config.confidence_threshold, self.config.nms_threshold
        )
        keep_indices = keep.flatten() if hasattr(keep, "flatten") else keep

        detections = []
        for i in keep_indices:
            class_id = class_ids[i]
            label = self.class_names[class_id] if class_id < len(self.class_names) else str(class_id)
            detections.append(
                Detection(
                    class_id=class_id,
                    label=label,
                    confidence=confidences[i],
                    box=tuple(boxes[i]),  # type: ignore[arg-type]
                    is_target=label in self.config.target_classes,
                )
            )
        return detections


def draw_detections(frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
    """Draw bounding boxes and confidence scores in place, returning the frame."""
    for det in detections:
        x, y, w, h = det.box
        color = (0, 0, 255) if det.is_target else (0, 200, 0)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        text = f"{det.label} {det.confidence * 100:.1f}%"
        text_y = max(y - 8, 12)
        cv2.putText(
            frame, text, (x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA
        )
    return frame
