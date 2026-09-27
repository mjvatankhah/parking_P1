# Periodic YOLO with visual tracking

`reno/data/cameras.json` sets `detection_interval: 3`: run YOLO/ByteTrack on
frames 1, 4, 7, … and sparse Lucas–Kanade optical flow on the two intervening
frames. Set the interval to `1` to restore detector-every-frame behavior.
The camera settings service preserves this setting when saving cameras.
Restart the pipeline after changing it.

The existing OpenVINO backend and `(256, 416)` input size are retained.
As before, `CameraTracker` uses `yolov8n_openvino_model`; the `model_path`
argument does not select another backend in this version.

`TrackedFrame` is unchanged. `Detection` adds backward-compatible defaults:

- `is_predicted=False`: true for boxes updated by optical flow.
- `tracking_quality=None`: for optical flow, the surviving inlier fraction,
  accumulated since the latest detector update. This is not a calibrated probability.
- `confidence` remains the most recent YOLO detection confidence.

ByteTrack assigns IDs on detection frames. Flow propagates those IDs and
classes between detections; it does not discover new objects. New objects
normally wait until the next scheduled detection. Flow tracks up to 40 points
per box on a grayscale image at most 640 pixels wide, validates forward/backward
motion, fits a robust similarity transform, and updates box center/size.
If any box has too few reliable points, inconsistent motion, excessive
scale/rotation, or the image dimensions change, detection runs immediately.
Nonconsecutive frame indices, nonincreasing timestamps and gaps over one
second also force detection. Thus the YOLO call count may exceed one in three.

Line/crop/OCR/database workers and their queue policies are unchanged. Both
YOLO and valid flow outputs can trigger crossing events and supply crops.
Tests cover a crossing on either source continuing through the real workers
to the database input queue, using a fake plate reader and no database writes.
Flow can still drift or lose identities in real scenes; a matching event count
on one clip does not establish recognition accuracy for all cameras.

The source reader still processes frames sequentially in its existing thread.
This change does not add an asynchronous capture buffer, guarantee live-stream
latency, or increase the dashboard's approximately 10 Hz refresh rate.

## Reproduce the speed comparison

From the repository root:

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python profile_hybrid_tracking.py
```

The benchmark compares intervals 1 and 3 on the same local `c5.mp4`, model and
hardware, twice each with reversed order. It excludes the first 15 frames
(including model startup) of each 180-frame pass. FPS includes decoding and
`CameraTracker.process`, including optical-flow setup/fallbacks and output
construction. Every frame is processed: no pacing or intentional frame drops.
Line/crop time is reported separately; network, preview, queues, OCR and database
are not measured. The clip's configured line is used to report crossing events
as a diagnostic, not as labeled accuracy ground truth.

Results are saved to `reports/hybrid-tracking.json`, including per-pass FPS,
YOLO calls, flow frames, fallback counts, tracked-frame coverage and crossings.
The reported median FPS is processing capacity on this clip, not the actual
FPS of the configured HLS stream. Optional arguments include `--video`,
`--warmup`, `--max-frames`, `--repeats`, and `--output`; the diagnostic crossing
line always comes from `config/cameras.json` and is only meaningful for c5.

## Measured result (2026-09-27)

On the AMD A8 PRO-7150B CPU in this workspace, two passes per mode gave median
decode/tracking throughput of **3.92 FPS** at interval 1 and **8.52 FPS** at
interval 3 (**2.17x**, about **117%** more throughput). Each measured pass used
165 frames after 15 warmup frames. Hybrid passes used 67 YOLO calls and 98 flow
frames, with 21 early detector refreshes due to unreliable flow.

Both modes recorded two crossings. The first crossing moved from frame 44 to
46, while the second remained at frame 143. Frames containing tracked objects
were 174/180 in baseline versus 165/180 in hybrid; this is not a labeled accuracy
score, but shows the outputs are not identical. Verify tracking and crop quality
on the target camera before treating this speed gain as an accuracy-neutral change.
