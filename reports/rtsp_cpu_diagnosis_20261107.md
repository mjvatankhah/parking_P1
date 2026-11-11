# RTSP CPU and frame-skip diagnosis — 2026-11-07

## Scope

Measured the configured camera and actual CameraTracker/StreamManager paths. No application settings or processing behavior were changed. The desktop application's reported 79% CPU reading and the other computer were not directly measured. Tests ran in this workspace's execution environment, with access to the configured local camera.

## Configuration and hardware

- Camera frame: width 1440, height 1616; configured ROI enabled.
- Vehicle model: `src/models/vehicle/yolo26n_openvino_model`, fixed input 384 × 640, batch 1.
- OpenVINO runtime: CPU, float32, LATENCY, NUM_STREAMS=1, INFERENCE_NUM_THREADS=4, optimal infer requests=1.
- Visible CPU: AMD A8 PRO-7150B, four cores, all four allowed by CPU affinity. AVX present; AVX2 absent. Microsoft hypervisor visible.
- No cgroup CPU bandwidth quota (`cpu.max`: `max 100000`). CUDA unavailable. These observations do not measure host power management, throttling, or other host processes.

## Experiments

### Actual RTSP capture and tracking

A 35-second StreamManager probe wrapped the actual `tracker.process` call with wall-clock and CPU timing. Capture continued independently. It recorded:

- Wall time: 35.62 s; process CPU time: 66.22 s.
- Captured frames: 341; completed tracked frames: 2.
- Processed indices: 1, 310 (index jump 309, including model initialization).
- First processing call: 28.77 s; next: 3.08 s.

This reproduces capture outrunning processing and skipped indices. The large startup jump must not be presented as a steady-state 309-frame jump. The user's exact approximately 40-frame steady-state jump was not independently established by this short startup-inclusive probe.

### Warmed tracking on one captured frame

Ran the real tracker six times on the same camera frame, with monotonically increasing timestamps one second apart, to force detector updates and isolate processing from continuous decoding. The first call was excluded below.

| Stage | Observed range |
| --- | --- |
| Total tracking call | 919–1972 ms |
| Model inference | 819–1857 ms |
| Preprocessing | 9–46 ms |
| Postprocessing | 1.4–2.1 ms |

Inference accounts for roughly 86–94% of measured tracking wall time in these samples. Model speed excludes other tracking and ROI costs, which are included in the total.

### Thread-count comparison

Compiled the same OpenVINO model separately with 1, 2, and 4 threads in LATENCY mode. Used a zero tensor at the actual compiled input shape, one warmup, then three synchronous calls each. This isolates inference and is not an end-to-end camera throughput test.

| Threads | Individual inference times (s) | Mean (s) |
| --- | --- | --- |
| 1 | 1.968, 2.232, 2.087 | 2.095 |
| 2 | 1.978, 1.521, 1.278 | 1.592 |
| 4 | 1.125, 1.075, 1.166 | 1.122 |

Four threads were fastest among tested settings and are already the active setting. Timing variability prevents claiming these small samples are a precise capacity estimate. Four-thread inference consumed 9.04 CPU seconds in 3.37 wall seconds: about 67% of four-core aggregate capacity during this isolated test, despite all four inference threads being configured.

## Causal findings

1. **The dominant measured bottleneck is CPU vehicle inference.** This slowdown reproduces without OCR, database writes, or the desktop UI, so those components are not required for it to occur. They can still add contention in the full application.
2. **RTSP deliberately replaces pending frames.** `streaming/Streming_Cameras.py:109` overwrites `_latest_capture`; one tracking thread consumes it at line 148. Frames arriving during a slow inference are replaced before processing. The frame number therefore jumps when processing resumes. An unbounded FIFO would exchange this symptom for increasing live latency.
3. **The detector scheduling reinforces the slow path.** `tracking/tracker.py:79` schedules detection every 0.2 seconds of source time; a gap over 0.5 seconds also forces detection. When processing takes around a second or more, the next consumed frame is generally already due for another full detector pass. `detection_interval=3` does not mean strictly one detector pass per three captured frames in this implementation.
4. **79% aggregate utilization does not establish an artificial CPU cap.** Four inference threads are enabled, affinity allows all four cores, and tested reductions made inference slower. Work inside each call includes stages with different parallelism; measured CPU time is below four-core saturation. The exact reason for the desktop's specific percentage cannot be isolated from this environment.
5. **Preview has a separate display limit.** `preview.py:21` publishes at most three updates per second, and preview publication receives already tracked frames (`main_v2.py:83`). Display can skip additional frames even if tracking is improved.

## Recommended next work

- Optimize or replace the measured vehicle-inference path first. Benchmark candidate backends/models on this CPU and verify detection quality before switching. AVX2 absence is a relevant hardware constraint, not independently proven to be the sole cause.
- Separate raw live preview from processed overlays if smooth monitoring is required; raising preview frequency alone cannot fix slow detection.
- Instrument steady-state captured/processed/displayed rates and per-stage latency in the full application before changing scheduling. Preserve bounded latency and crossing-detection accuracy when adjusting detector cadence.
- Compare the other machine with the same model artifact, backend, camera settings and measurement window. CPU percentages alone do not establish which machine processes more frames.

No production fix is claimed. This task establishes the bottleneck and skip mechanism; sustained full-application load and comparative-machine measurements remain outside the captured evidence.
