# UAV-DET — Drone Detection & Tactical Console

Real-time drone detection (YOLOv3/YOLOv4 + OpenCV) with a military-style web
console: live annotated feed, contact table, threat posture, and an event log.

Standalone — it does not read from or write to the UAV Atlas database in the
rest of this repo.

---

## 1. See it working in 2 minutes (no camera, no weights)

Do this first. It proves the install is good before you touch hardware.

```bash
pip install -r requirements.txt
python detection/console.py --simulate
```

Open **http://127.0.0.1:8000** in a browser. You'll see a synthetic sky with
drones and a bird crossing it, fully tracked and classified. `Ctrl+C` to stop.

If that works, the software is fine and anything that goes wrong next is the
camera or the model files.

---

## 2. Set up the camera

### Pick your camera

Any camera OpenCV can open works:

| Camera type | What to pass |
| --- | --- |
| Built-in laptop webcam | `--source 0` |
| Second/USB webcam | `--source 1`, `--source 2`, … |
| IP / CCTV camera | `--source "rtsp://user:pass@192.168.1.50:554/stream1"` |
| Test on a video file | `--source path/to/clip.mp4` |

### Find the right index

If `--source 0` grabs the wrong camera, list what's attached:

```bash
# Linux
ls /dev/video*

# macOS / Windows / anywhere — probe indices 0-5
python -c "import cv2; [print(i, cv2.VideoCapture(i).isOpened()) for i in range(6)]"
```

Whichever index prints `True` is a camera you can use.

### Platform notes

- **Linux** — you may need camera group access: `sudo usermod -aG video $USER`,
  then log out and back in.
- **macOS** — the first run triggers a camera permission prompt. If you never
  saw one, enable it under *System Settings → Privacy & Security → Camera* for
  your terminal app.
- **Windows** — *Settings → Privacy → Camera → Allow desktop apps to access
  your camera*.
- **Any OS** — close Zoom/Teams/OBS first. Most cameras allow only one
  application at a time, and OpenCV will simply fail to open a busy device.

### Verify the camera alone

Before involving the detector, confirm OpenCV can actually read frames:

```bash
python -c "
import cv2
cap = cv2.VideoCapture(0)
ok, frame = cap.read()
print('opened:', cap.isOpened(), '| frame:', None if frame is None else frame.shape)
cap.release()"
```

You want `opened: True` and a shape like `(480, 640, 3)`. If you get
`False`/`None`, it's a permission, index or in-use problem — fix that before
going further.

---

## 3. Get the model files

Detection needs **three** files in `detection/models/`. They are not in this
repo: weights are hundreds of megabytes and licensed separately.

| File | What it is |
| --- | --- |
| `yolov4.cfg` | Network architecture |
| `yolov4.weights` | Trained weights (~245 MB) |
| `obj.names` | One class name per line |

**Starting point:** grab the stock YOLOv4 files from
[AlexeyAB/darknet](https://github.com/AlexeyAB/darknet) (`yolov4.cfg`,
`yolov4.weights`, and `coco.names` renamed to `obj.names`). These are trained
on COCO, so they have **no "drone" class** — every contact will show as a
regular COCO object. That's expected. Use it to confirm the camera → detector
→ console chain runs on your machine, then swap in a drone-trained model.

To make a drone model the alerting class, either name it `drone` in
`obj.names`, or point the config at whatever you called it:

```python
DetectorConfig(target_classes=("drone", "uav"))
```

Anything not in `target_classes` is still detected and tracked — it just
renders green (benign) instead of red (hostile).

---

## 4. Run it for real

```bash
# Tactical web console (recommended)
python detection/console.py --source 0

# Plain OpenCV window, no browser
python detection/live_detect.py --source 0
```

Useful flags for `console.py`:

| Flag | Purpose |
| --- | --- |
| `--simulate` | Synthetic feed; ignores camera and weights entirely |
| `--source 0` | Camera index, file path or RTSP URL |
| `--port 8000` | Change the web port |
| `--host 0.0.0.0` | Serve to other machines on the network (see warning below) |
| `--input-size 608` | Better distant-drone recall, lower FPS (default 416) |
| `--confidence 0.6` | Raise to cut false positives, lower to catch more |
| `--backend cuda` | Force GPU; `cpu` to force CPU; `auto` (default) prefers GPU |

### Watching from a phone or tablet

```bash
python detection/console.py --source 0 --host 0.0.0.0
```

Then browse to `http://<the-machine's-LAN-IP>:8000` from the other device.

> **Security:** `--host 0.0.0.0` exposes the feed to everyone on the network
> with no authentication, and this runs on Flask's development server. Use it
> on a trusted LAN only. For anything beyond that, put it behind a real WSGI
> server and a reverse proxy with auth.

---

## 5. Reading the console

- **Threat banner** — CLEAR → GUARDED → ELEVATED → CRITICAL, driven by how
  many hostile contacts are up and how confident the detector is. Two
  hostiles, or one above 80 %, is CRITICAL.
- **Red brackets / rows** = a class in `target_classes` (a drone).
  **Green** = detected but benign (e.g. a bird).
- **BRG** — approximate bearing in degrees off the camera's centre line.
  Estimated from pixel position and an assumed 62° field of view; it is for
  situational awareness, not targeting. A single uncalibrated camera cannot
  give true bearing.
- **Contacts** are confirmed *tracks*, not raw detections. A contact must
  persist several frames before it appears, which is what keeps a one-frame
  glint off the board.

---

## 6. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `Missing model file(s)` | The three files aren't in `detection/models/`. Or just use `--simulate`. |
| `Could not open video source '0'` | Wrong index, no permission, or another app owns the camera. See §2. |
| `AttributeError: readNetFromDarknet` | OpenCV 5.x removed Darknet loading. `pip install "opencv-python>=4.8,<5"`. |
| Console loads, feed is black | Detector still warming up, or the camera opened but returns no frames. Check `/healthz`. |
| Very low FPS | Use `--input-size 416`, add `--backend cuda`, or lower the camera resolution. |
| Everything is a "hostile" | Your `obj.names` classes don't match `target_classes`. See §3. |
| Log floods with acquire/lose | Raise `FusionTracker(min_hits=…)` or lower `iou_threshold`. |

---

## 7. What's in this folder

| File | Role |
| --- | --- |
| `console.py` | **Main entry point** — serves the web console |
| `live_detect.py` | Alternative plain OpenCV window |
| `server.py` | Flask app, MJPEG stream, `/api/state` |
| `templates/console.html` | The tactical UI (self-contained; no CDN) |
| `hud.py` | On-frame overlay: reticles, crosshair, status strips |
| `sources.py` | `LiveSource` (camera+YOLO) and `SimulatedSource` (demo) |
| `console_state.py` | Threat posture, contact records, event log |
| `detector.py` | YOLO loading, inference, NMS |
| `fusion.py` | Multi-frame tracking with velocity prediction |
| `config.py` | All tunables |
| `dataset.py` | 80/20 train/test split + Darknet manifests |
| `optimize.py` | ONNX quantization / pruning for edge hardware |

### HTTP endpoints

| Endpoint | Returns |
| --- | --- |
| `/` | The console page |
| `/stream.mjpg` | Annotated MJPEG video stream |
| `/api/state` | JSON: contacts, threat level, events, telemetry |
| `/healthz` | Liveness probe |

`/api/state` is plain JSON, so you can drive alarms, logging or a second
display off it without touching this code.

---

## 8. Training your own drone model

This module doesn't train — that's [Darknet](https://github.com/AlexeyAB/darknet)'s
job. What's here is the reproducible data prep:

```bash
# Expects detection/dataset/images/*.jpg
#     and detection/dataset/labels/*.txt   ("<class_id> <cx> <cy> <w> <h>", normalized 0-1)
python detection/dataset.py
```

Splits your labelled images 80/20 with a fixed seed (so re-running never leaks
test images into training) and writes `train.txt`, `test.txt`, `obj.names` and
`obj.data` for `darknet detector train`. Point `detection/models/` at the
resulting `.cfg`/`.weights` when it finishes.

Accuracy is a property of *your trained model and dataset* — not of this code.
Nothing here can produce a given accuracy figure on its own.

---

## 9. Hardware

Tuned against an Intel i7-9750H / 16 GB RAM / NVIDIA GTX 1660 Ti. At 416×416
that GPU clears real-time comfortably via OpenCV's CUDA backend; CPU-only
still runs, just slower. The HUD overlay itself costs ~6 ms/frame at 720p with
8 contacts.

For smaller edge hardware, see `optimize.py` for INT8 quantization and
magnitude pruning of an ONNX export.

> **Note on OpenCV:** `requirements.txt` pins `opencv-python<5` on purpose.
> OpenCV 5.0 removed `cv2.dnn.readNetFromDarknet`, which the `.cfg`/`.weights`
> loader depends on. Don't upgrade past 5.0 unless you switch to ONNX.
