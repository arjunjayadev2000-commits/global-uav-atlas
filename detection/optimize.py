"""Model compression for edge deployment: dynamic quantization and pruning.

The live-camera path (``detector.py``) runs the full-precision Darknet model
directly through OpenCV's DNN module, which is the right choice on the
reference workstation (i7-9750H / GTX 1660 Ti). This module is for the
*next* step field crews actually asked for: shrinking the trained model to
run on smaller edge hardware (a Jetson-class board, a handheld unit) where
memory and power draw — not raw FPS — are the binding constraint.

Both operations here work on an ONNX export of the trained model rather than
the raw Darknet ``.weights`` file, because ONNX is the interchange format
every mainstream quantization/pruning toolchain (onnxruntime, TensorRT,
OpenVINO) actually consumes. Export the trained Darknet model to ONNX first
(e.g. with the ``pytorch-YOLOv4`` project's converter, or Darknet's own ONNX
export tooling) and point these functions at the result.

Both functions are optional — everything else in ``detection/`` runs without
``onnx``/``onnxruntime`` installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


def _require_onnx():
    try:
        import onnx
    except ImportError as exc:
        raise ImportError(
            "Pruning requires the optional 'onnx' package: pip install onnx"
        ) from exc
    return onnx


def _require_onnxruntime():
    try:
        from onnxruntime.quantization import QuantType, quantize_dynamic
    except ImportError as exc:
        raise ImportError(
            "Quantization requires the optional 'onnxruntime' package: "
            "pip install onnxruntime"
        ) from exc
    return quantize_dynamic, QuantType


@dataclass
class CompressionReport:
    input_path: Path
    output_path: Path
    input_size_bytes: int
    output_size_bytes: int

    @property
    def size_reduction_pct(self) -> float:
        if self.input_size_bytes == 0:
            return 0.0
        return 100.0 * (1 - self.output_size_bytes / self.input_size_bytes)


def quantize_model(onnx_path: Path, output_path: Path) -> CompressionReport:
    """Dynamic post-training INT8 quantization of an ONNX model's weights.

    Dynamic quantization (weights quantized ahead of time, activations
    quantized on the fly per-inference) needs no calibration dataset and
    typically cuts model size ~4x with a small, usually-tolerable accuracy
    drop — appropriate for a detector where the field target is "runs at all
    on the edge device" rather than squeezing the last mAP point.
    """
    quantize_dynamic, QuantType = _require_onnxruntime()
    onnx_path, output_path = Path(onnx_path), Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    quantize_dynamic(str(onnx_path), str(output_path), weight_type=QuantType.QInt8)

    return CompressionReport(
        input_path=onnx_path,
        output_path=output_path,
        input_size_bytes=onnx_path.stat().st_size,
        output_size_bytes=output_path.stat().st_size,
    )


def prune_model(onnx_path: Path, output_path: Path, sparsity: float = 0.3) -> CompressionReport:
    """Zero out the smallest-magnitude weights in each convolution layer.

    This is unstructured magnitude pruning: per Conv-weight tensor, the
    ``sparsity`` fraction of weights closest to zero are set to exactly zero.
    It does **not** shrink the file on its own (a mostly-zero tensor is still
    stored densely) — the payoff is that it makes the model compressible
    (zeros deflate well) and, more importantly, is the standard first step
    before fine-tuning a smaller/faster model or feeding a sparsity-aware
    runtime (e.g. OpenVINO, TensorRT sparse kernels) on the target edge
    hardware. Treat ``output_path`` as an intermediate artifact for that
    pipeline, not a final deployable file.
    """
    if not 0.0 < sparsity < 1.0:
        raise ValueError("sparsity must be between 0 and 1")

    onnx = _require_onnx()
    from onnx import numpy_helper

    onnx_path, output_path = Path(onnx_path), Path(output_path)
    model = onnx.load(str(onnx_path))

    for initializer in model.graph.initializer:
        array = numpy_helper.to_array(initializer)
        if array.ndim != 4:  # Conv weight tensors are (out_ch, in_ch, kh, kw)
            continue

        flat_abs = np.abs(array).reshape(-1)
        if flat_abs.size == 0:
            continue
        threshold_index = int(flat_abs.size * sparsity)
        if threshold_index == 0:
            continue
        threshold = np.sort(flat_abs)[threshold_index]

        pruned = array.copy()
        pruned[np.abs(pruned) < threshold] = 0.0
        new_tensor = numpy_helper.from_array(pruned, name=initializer.name)
        initializer.CopyFrom(new_tensor)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(output_path))

    return CompressionReport(
        input_path=onnx_path,
        output_path=output_path,
        input_size_bytes=onnx_path.stat().st_size,
        output_size_bytes=output_path.stat().st_size,
    )
