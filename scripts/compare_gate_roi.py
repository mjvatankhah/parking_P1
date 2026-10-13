"""Offline gate ROI comparison; decode the whole requested interval, no DB writes.

Inference is sampled at --stride. Sizes are (height, width); boxes are mapped
back into original recording coordinates before ByteTrack and line crossing.
"""
import argparse
import gc
import hashlib
import json
import math
from pathlib import Path
import time
from types import SimpleNamespace

import cv2
import numpy as np
import openvino as ov
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker

from computer_vision_v2.Line_Manager.line_detector import LineDetectorManager
from computer_vision_v2.tracking.frame_info import Detection, TrackedFrame

VARIANTS = {
    'full_416': ([0, 0, 920, 530], [256, 416]),
    'full_320': ([0, 0, 920, 530], [192, 320]),
    'gate_320': ([0, 0, 600, 530], [320, 320]),
    'gate_288': ([0, 0, 600, 530], [256, 288]),
    'gate_416': ([0, 0, 600, 530], [384, 416]),
    'door_320': ([0, 0, 500, 380], [256, 320]),
}


def infer(compiled, image, roi, size):
    x0, y0, x2, y2 = roi
    crop = image[y0:y2, x0:x2]
    h, w = crop.shape[:2]
    oh, ow = size
    scale = min(oh / h, ow / w)
    rw, rh = round(w * scale), round(h * scale)
    dx, dy = (ow - rw) // 2, (oh - rh) // 2
    padded = np.full((oh, ow, 3), 114, dtype=np.uint8)
    padded[dy:dy + rh, dx:dx + rw] = cv2.resize(crop, (rw, rh))
    blob = np.ascontiguousarray(padded[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255
    output = compiled(blob)[0][0].T
    cls = output[:, 4:].argmax(1)
    scores = output[np.arange(len(output)), cls + 4]
    # As in model.track: low threshold for ByteTrack, class-aware NMS.
    mask = (scores > .1) & np.isin(cls, [0, 2])
    xywh, scores, cls = output[mask, :4].copy(), scores[mask], cls[mask]
    xywh[:, :2] -= xywh[:, 2:] / 2
    kept = []
    for category in (0, 2):
        ids = np.flatnonzero(cls == category)
        if len(ids):
            indices = cv2.dnn.NMSBoxes(xywh[ids].tolist(), scores[ids].tolist(), .1, .7)
            kept.extend(ids[np.asarray(indices).reshape(-1)].tolist())
    rows = []
    for i in kept:
        x, y, bw, bh = xywh[i]
        box = [(x - dx) / scale, (y - dy) / scale,
               (x + bw - dx) / scale, (y + bh - dy) / scale]
        box = np.clip(box, [0, 0, 0, 0], [w, h, w, h]) + [x0, y0, x0, y0]
        rows.append([*box, float(scores[i]), int(cls[i])])
    return np.asarray(rows, dtype=np.float32).reshape(-1, 6)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video', required=True)
    p.add_argument('--model', default='.uv-model-cache/gate_roi/vehicle_openvino_model/vehicle.xml')
    p.add_argument('--output', type=Path, default=Path('reports/gate_roi_0036'))
    p.add_argument('--start', type=float, default=240)
    p.add_argument('--stride', type=int, default=6)
    p.add_argument('--limit', type=int, default=80, help='New inference samples per variant per invocation; resumes JSON checkpoints')
    p.add_argument('--variants', nargs='+', choices=VARIANTS, default=list(VARIANTS))
    p.add_argument('--registration', type=Path, help='Map screen recording into measured RTSP frame coordinates')
    args = p.parse_args()
    if args.stride < 1:
        p.error('stride must be positive')
    cv2.setNumThreads(1)
    registration = json.loads(args.registration.read_text()) if args.registration else None
    frame_width, frame_height = registration['rtsp_wh'] if registration else (920, 530)
    matrix = np.asarray(registration['homography_recording_to_rtsp']) if registration else None
    args.output.mkdir(parents=True, exist_ok=True)
    config = json.loads(Path('src/computer_vision_v2/reno/data/cameras.json').read_text())
    camera = next(c for c in config['cameras'] if c['id'] == 'cam2')
    safe_camera = {k: camera[k] for k in ('id', 'dir', 'line', 'lines', 'inside_point', 'coordinate_space') if k in camera}
    (args.output / 'lines_used.json').write_text(json.dumps(safe_camera, indent=2))
    core = ov.Core()
    for variant in args.variants:
        roi, size = VARIANTS[variant]
        if registration:
            if variant.startswith('full'):
                roi = [0, 0, frame_width, frame_height]
            else:
                roi = [24, 0, 480, 480]
                side = 288 if variant == 'gate_288' else 320
                size = [side, side]
        report_path = args.output / f'{variant}.json'
        previous = json.loads(report_path.read_text()) if report_path.exists() else {}
        if previous.get('complete'):
            print('ALREADY COMPLETE', variant, flush=True)
            continue
        rows = previous.get('samples', [])
        done_indices = {row['index'] for row in rows}
        model_path = 'yolov8n_openvino_model/yolov8n.xml' if variant == 'full_416' else args.model
        model = core.read_model(model_path)
        model.reshape([1, 3, *size])
        compiled = core.compile_model(model, 'CPU', {'INFERENCE_NUM_THREADS': 2, 'NUM_STREAMS': 1,
                                                    'INFERENCE_PRECISION_HINT': 'f32'})
        for _ in range(3):
            infer(compiled, np.zeros((frame_height, frame_width, 3), np.uint8), roi, size)
        cap = cv2.VideoCapture(args.video)
        fps = cap.get(cv2.CAP_PROP_FPS)
        start = math.ceil(args.start * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        tracker = BYTETracker(SimpleNamespace(track_high_thresh=.25, track_low_thresh=.1,
                            new_track_thresh=.25, track_buffer=30, match_thresh=.8, fuse_score=True))
        lines = LineDetectorManager({'cameras': [camera]})
        # Expiry must be based on video time, not offline execution duration.
        from unittest.mock import patch
        events, elapsed, decoded, new_samples = [], [row['ms'] for row in rows], 0, 0
        complete = False
        loop_start = time.perf_counter()
        while True:
            ok, frame = cap.read()
            if not ok:
                complete = True
                break
            index = start + decoded
            decoded += 1
            if (index - start) % args.stride:
                continue
            if index in done_indices:
                continue
            source_seconds = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if registration:
                frame = cv2.warpPerspective(frame, matrix, (frame_width, frame_height), borderValue=(114, 114, 114))
            t0 = time.perf_counter()
            boxes = infer(compiled, frame, roi, size)
            elapsed.append((time.perf_counter() - t0) * 1000)
            rows.append({'index': index, 'seconds': source_seconds, 'detections': boxes.tolist(), 'ms': elapsed[-1]})
            new_samples += 1
            if new_samples >= args.limit:
                break
        cap.release()
        # Replay inexpensive state from all saved detections after each chunk.
        frame_shape = np.empty((frame_height, frame_width, 3), dtype=np.uint8)
        for row in rows:
            boxes = np.asarray(row['detections'], dtype=np.float32).reshape(-1, 6)
            tracked = tracker.update(Boxes(boxes, frame_shape.shape[:2]), frame_shape)
            ds = [Detection(int(b[4]), tuple(map(float, b[:4])), int(b[6]), float(b[5])) for b in tracked]
            tf = TrackedFrame(camera['id'], row['index'], row['seconds'], frame_shape, ds)
            with patch('computer_vision_v2.Line_Manager.line_detector.time.monotonic', return_value=row['seconds']):
                events.extend(lines.update(tf))
            row['tracks'] = tracked.tolist()
        report = {'variant': variant, 'roi_xyxy': roi, 'input_hw': size, 'video': args.video,
                  'video_fps': fps, 'start_frame': start, 'decoded_frames': decoded,
                  'end_frame_exclusive': start + decoded, 'stride': args.stride,
                  'complete': complete,
                  'registration': registration,
                  'model_xml': model_path, 'model_bin_sha256': hashlib.sha256(Path(model_path).with_suffix('.bin').read_bytes()).hexdigest(),
                  'ov_threads': 2, 'median_ms': float(np.median(elapsed)),
                  'p95_ms': float(np.percentile(elapsed, 95)),
                  'compute_fps': 1000 / float(np.mean(elapsed)),
                  'last_chunk_wall_seconds': time.perf_counter() - loop_start,
                  'events': events, 'samples': rows,
                  'limitation': 'Sampled offline inference, not live FPS. Screen recording; existing camera lines projected under full-frame alignment assumption. No OCR or DB.'}
        report_path.write_text(json.dumps(report, indent=2))
        print('CHECKPOINT', variant, 'complete', complete, 'decoded', decoded, 'samples', len(rows), 'compute_fps', round(report['compute_fps'], 2), 'events', len(events), flush=True)
        del compiled, model, tracker
        gc.collect()


if __name__ == '__main__':
    main()
