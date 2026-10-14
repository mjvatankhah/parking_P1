# Plate Detector Trial

Candidate: [shalchianmh/Iran_license_plate_detection_YOLOv8m](https://huggingface.co/shalchianmh/Iran_license_plate_detection_YOLOv8m), revision `056e81d`.
The publisher lists the model license as AGPL-3.0.

The downloaded checkpoint is kept in `source/YOLOv8m_Iran_license_plate_detection.pt`.
It contains one class (`L`). Export used Ultralytics 8.4.135, ONNX opset 17,
FP32, batch 1, `imgsz=640`, `dynamic=False`, `nms=False`, and `simplify=False`.
The resulting input is `images: float32[1,3,640,640]`; output is
`output0: float32[1,5,8400]`. ONNX validation passed.

`dill==0.4.1` was installed only to load/export the checkpoint. Its official
source archive is retained in `source/dill-0.4.1.tar.gz`; inference uses the
project's existing ONNX Runtime and does not require dill.

Model files live in `src/computer_vision_v2/ocr_worker/models/`:

- `plate_yolo.platrix-backup.onnx`: verified copy of the original detector.
- `plate_yolo_yolov8m.onnx`: exported candidate.
- `plate_yolo.onnx`: the filename loaded by the application.

The original detector has been restored as `plate_yolo.onnx`; the candidate
remains available as `plate_yolo_yolov8m.onnx` for future trials. The candidate SHA-256 is
`2840415ec21286d94d2b715a29a1658716ddc30cbf31b5cff43d662013f22e18`.
The original backup SHA-256 is
`a54e475c402e6036bb5c70f1a6ff75179e76098a5c8039bb5d148c0b6421f5c6`.

Run the reproducible offline comparison from the project root:

```bash
PYTHONPATH=src .venv/bin/python scripts/compare_plate_detectors.py \
  --config src/reno/data/cameras.json \
  --video src/computer_vision_v2/video/MyRecord_20261010091951.mp4 \
  --baseline src/computer_vision_v2/ocr_worker/models/plate_yolo.platrix-backup.onnx \
  --candidate src/computer_vision_v2/ocr_worker/models/plate_yolo_yolov8m.onnx \
  --output reports/plate_model_trial/video_091951
```

The configuration file is unchanged. This command overrides only the source
in memory for offline replay. Camera registration and database writes are
disabled. The real tracking, line-crossing, and crop-selection workers collect
recognition inputs; both detectors then process identical saved PNG crops
using the existing plate reader and OCR. Comparison runs after replay so CPU
inference time does not interfere with capture or worker shutdown.

`video_091951/comparison.json` records model hashes, outputs, timings, and
frame counts. `vehicle_*.png` are the actual recognition inputs and
`pipeline.log` contains the replay log. Text output is not a correctness score;
there is no labelled ground truth in this trial, and a single video cannot
establish which model is more accurate overall.

## Observed Result

The previous test video had 484 decodable frames (its metadata reports 485).
The pipeline produced one car crossing and one selected recognition crop,
144 x 126 pixels. Neither detector found a plate at the existing confidence
threshold of 0.35; neither reached OCR character decoding. Single-crop latency
was 0.915 seconds for the original detector and 7.320 seconds for YOLOv8m on
this CPU. These are single cold-call observations, not average latency or
accuracy measurements. This video does not demonstrate an improvement.

The application currently allows five seconds per worker during shutdown.
An initial trial that compared both models inside the OCR worker exceeded
that timeout. Stop-time draining for slow inference remains a limitation;
the offline comparison above completes inference synchronously after replay.

To restore the original detector:

```bash
cp src/computer_vision_v2/ocr_worker/models/plate_yolo.platrix-backup.onnx \
   src/computer_vision_v2/ocr_worker/models/plate_yolo.onnx
```

Restart the backend after switching model files; running sessions keep their
loaded weights in memory.
