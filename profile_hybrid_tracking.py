"""Compare detector-every-frame with two optical-flow frames between detections.

PYTHONPATH=src .venv/bin/python profile_hybrid_tracking.py
Measures decode + CameraTracker, excluding warmup, UI, OCR, DB and network.
All video frames are processed in order, without playback pacing or frame drops.
"""
import argparse
import gc
import json
import platform
from pathlib import Path
import statistics
import time

import cv2

from computer_vision_v2.tracking.tracker import CameraTracker
from computer_vision_v2.Line_Manager.line_detector import LineDetector
from computer_vision_v2.best_crop_selector import BestCropSelector


def run(video, interval, warmup, max_frames):
    tracker = CameraTracker('benchmark', 'yolov8n_openvino_model', interval)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open {video}')
    source_fps = cap.get(cv2.CAP_PROP_FPS) or 25
    # c5 line from config/cameras.json; counts are diagnostic, not ground truth.
    camera = json.loads(Path('src/computer_vision_v2/config/cameras.json').read_text())['cameras'][0]
    line = LineDetector('benchmark', line=camera['line'], direction=camera['dir'],
                        coordinate_space=camera.get('coordinate_space', 'pixels'))
    selector = BestCropSelector()
    samples, detected_samples, flow_samples, downstream_samples = [], [], [], []
    yolo_calls = flow_frames = fallbacks = 0
    events = []
    ids = set()
    frames_with_tracks = 0
    frame_idx = 0
    try:
        while frame_idx < max_frames:
            start = time.perf_counter()
            ok, image = cap.read()
            if not ok:
                break
            frame_idx += 1
            old_calls = tracker.yolo_calls
            old_fallbacks = tracker.flow_fallbacks
            # Use the same monotonic capture timestamp convention as StreamManager.
            frame = tracker.process(frame_idx, time.monotonic(), image)
            end = time.perf_counter()
            used_yolo = tracker.yolo_calls != old_calls
            events.extend(line.update(frame))
            selector.update('benchmark', frame)
            downstream_end = time.perf_counter()
            ids.update(det.track_id for det in frame.detections)
            frames_with_tracks += bool(frame.detections)
            if frame_idx > warmup:
                elapsed = end - start
                samples.append(elapsed)
                (detected_samples if used_yolo else flow_samples).append(elapsed)
                downstream_samples.append(downstream_end - end)
                yolo_calls += int(used_yolo)
                flow_frames += int(not used_yolo)
                fallbacks += tracker.flow_fallbacks - old_fallbacks
            if frame_idx % 60 == 0:
                print(f'  {frame_idx} frames processed', flush=True)
    finally:
        cap.release()
    if not samples:
        raise RuntimeError('No frames measured after warmup')
    result = dict(
        interval=interval, source_fps=source_fps, total_frames=frame_idx,
        measured_frames=len(samples), warmup_frames=warmup,
        fps=len(samples) / sum(samples), mean_frame_ms=1000 * statistics.mean(samples),
        p95_frame_ms=1000 * sorted(samples)[min(len(samples) - 1, int(len(samples) * .95))],
        detector_frame_ms=1000 * statistics.mean(detected_samples) if detected_samples else None,
        flow_frame_ms=1000 * statistics.mean(flow_samples) if flow_samples else None,
        line_crop_mean_ms=1000 * statistics.mean(downstream_samples),
        yolo_calls=yolo_calls, flow_frames=flow_frames, flow_fallbacks=fallbacks,
        unique_ids=len(ids), frames_with_tracks=frames_with_tracks,
        crossing_events=events,
    )
    print(json.dumps(result), flush=True)
    del tracker
    gc.collect()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', default='src/computer_vision_v2/video/c5.mp4')
    parser.add_argument('--warmup', type=int, default=15)
    parser.add_argument('--max-frames', type=int, default=180)
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--output', default='reports/hybrid-tracking.json')
    args = parser.parse_args()
    if args.repeats < 1 or args.warmup < 0 or args.max_frames <= args.warmup:
        parser.error('repeats must be positive and max-frames must exceed nonnegative warmup')
    runs = []
    for repeat in range(args.repeats):
        # Reverse order on alternate repeats to reduce warm-cache/order bias.
        for interval in ((1, 3) if repeat % 2 == 0 else (3, 1)):
            print(f'Run {repeat + 1}, detection interval {interval}', flush=True)
            runs.append(run(args.video, interval, args.warmup, args.max_frames))
    baseline = statistics.median(r['fps'] for r in runs if r['interval'] == 1)
    hybrid = statistics.median(r['fps'] for r in runs if r['interval'] == 3)
    report = dict(
        scope='decode + CameraTracker; no network, pacing, UI, OCR or database; no frame drops',
        platform=platform.platform(), opencv=cv2.__version__, video=args.video,
        model='yolov8n_openvino_model', imgsz=[256, 416],
        baseline_median_fps=baseline, hybrid_median_fps=hybrid,
        speedup=hybrid / baseline, throughput_gain_percent=(hybrid / baseline - 1) * 100,
        runs=runs,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Baseline {baseline:.2f} FPS -> hybrid {hybrid:.2f} FPS ({hybrid / baseline:.2f}x); {output}', flush=True)


if __name__ == '__main__':
    main()
