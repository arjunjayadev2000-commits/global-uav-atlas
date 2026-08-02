# Drone Detection (YOLOv3/YOLOv4)

Real-time drone detection from a webcam or video feed, drawing bounding boxes
and confidence scores. This is a standalone computer-vision module — it does
not depend on, or feed into, the UAV Atlas database in the rest of this repo.

## Quick start (no coding experience needed)

You need **three files** before this will run. They are not included in this
repository because they are large binary model files, not source code:

| File | What it is | Where to put it |
| --- | --- | --- |
| `yolov4.cfg` | The network architecture definition | `detection/models/yolov4.cfg` |
| `yolov4.weights` | The trained weights (~245 MB) | `detection/models/yolov4.weights` |
| `obj.names` | One class name per line (e.g. `drone`, `bird`) | `detection/models/obj.names` |

If you don't have a drone-specific trained model yet, you can start with the
stock YOLOv4 files trained on the general-purpose COCO dataset (from the
official [AlexeyAB/darknet](https://github.com/AlexeyAB/darknet) releases) —
it won't have a "drone" class, but it's the fastest way to confirm the camera
pipeline itself works before swapping in a drone-trained model produced with
`detection/dataset.py` (see below).

Once the three files are in `detection/models/`:

1. Install dependencies once: `pip install -r requirements.txt`
   (this installs `opencv-python<5` deliberately — OpenCV 5.0 removed Darknet
   `.cfg`/`.weights` loading, which this detector needs. Don't
   `pip install --upgrade opencv-python` past 5.0 or loading the model will
   fail with an `AttributeError` on `readNetFromDarknet`.)
2. Plug in your webcam (or have a video file ready).
3. Run:
   ```bash
   python detection/live_detect.py
   ```
4. A window opens showing the live feed. Anything detected gets a colored box
   and a confidence percentage. **Red boxes** are drones (or whatever classes
   you listed in `DetectorConfig.target_classes`); **green boxes** are
   everything else the model recognizes (e.g. birds).
5. Press **`q`** or **`Esc`** in that window to stop.

To use a video file instead of a webcam: `python detection/live_detect.py --source path/to/video.mp4`

## What's in this folder

- `config.py` — all the tunables (model paths, input resolution, thresholds,
  which classes count as "drone" alerts, CPU/GPU backend selection).
- `detector.py` — loads the YOLO model via OpenCV and runs inference on a
  single frame, returning boxes + confidence scores.
- `fusion.py` — stabilizes detections across frames (a single noisy frame
  won't trigger an alert) and has a hook for corroborating with a second
  sensor (RF/acoustic/radar) if one is available.
- `dataset.py` — given a folder of labelled training images, does the 80/20
  train/test split and writes the manifest files a YOLO training run expects.
- `optimize.py` — optional quantization/pruning helpers for shrinking a
  trained model down for edge hardware (a Jetson-class board, a handheld
  unit) rather than the workstation this was developed against.
- `live_detect.py` — the script you actually run; wires the camera, detector
  and fusion tracker together.

## Training your own drone/bird model

This module doesn't train a model — training YOLOv3/v4 from scratch is done
with the [Darknet](https://github.com/AlexeyAB/darknet) framework (or an
equivalent PyTorch reimplementation), not pure OpenCV. What `dataset.py`
gives you is the repeatable data-prep step:

```bash
# Expects detection/dataset/images/*.jpg and detection/dataset/labels/*.txt
# (YOLO-format labels: "<class_id> <cx> <cy> <w> <h>", normalized 0-1)
python detection/dataset.py
```

This splits your labelled images 80/20 (matching the ~2,395-image drone/bird
dataset size this detector was designed around) and writes `train.txt`,
`test.txt`, `obj.names` and `obj.data` into `detection/dataset/`, ready to
hand to `darknet detector train`. Once training finishes, point
`detection/models/` at the resulting `.cfg`/`.weights` files.

## Hardware notes

Developed and tuned against an Intel i7-9750H CPU / 16 GB RAM / NVIDIA GTX
1660 Ti laptop. At 416×416 input, that GPU comfortably clears real-time
(20+ FPS) via OpenCV's CUDA backend (`--backend cuda`); the CPU-only path
(`--backend cpu`) still holds a usable frame rate if no GPU is present, just
slower. Use `--input-size 608` only if small/distant drones are being missed
— it costs meaningful FPS for better recall on small objects.

For deployment on smaller edge hardware, see `optimize.py` for quantization
and pruning of an ONNX export of the trained model.
