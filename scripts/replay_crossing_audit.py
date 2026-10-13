"""Replay a screen-recorded crossing without camera or database writes."""
import argparse
import json
from pathlib import Path

import cv2

from computer_vision_v2.tracking.tracker import CameraTracker
from computer_vision_v2.Line_Manager.line_detector import LineDetectorManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True)
    parser.add_argument('--start', type=float, default=95)
    parser.add_argument('--end', type=float, default=140)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stride', type=int, default=1)
    parser.add_argument('--diagnostic-pt', action='store_true',
                        help='Use local PyTorch weights to accelerate diagnostic replay')
    parser.add_argument('--ov-threads', type=int)
    parser.add_argument('--auto-crop', action='store_true')
    args = parser.parse_args()
    cv2.setNumThreads(2)
    if args.ov_threads:
        import openvino as ov
        from unittest.mock import patch
        original_compile = ov.Core.compile_model

        def bounded_compile(self, *compile_args, **kwargs):
            kwargs['config'] = dict(kwargs.get('config', {}),
                                    INFERENCE_NUM_THREADS=args.ov_threads, NUM_STREAMS=1)
            return original_compile(self, *compile_args, **kwargs)

        patch.object(ov.Core, 'compile_model', bounded_compile).start()
    config = json.loads(Path('src/computer_vision_v2/reno/data/cameras.json').read_text())
    camera = next(c for c in config['cameras'] if c['id'] == 'cam2')
    manager = LineDetectorManager({'cameras': [camera]})
    tracker = CameraTracker(camera['id'], config['model_path'], config.get('detection_interval', 3))
    if args.diagnostic_pt:
        import torch
        import numpy as np
        from ultralytics import YOLO
        tracker.model = YOLO('yolov8n.pt')
        tracker.model.track(np.zeros((315, 475, 3), dtype=np.uint8), persist=True,
                            imgsz=(256, 416), verbose=False, tracker='bytetrack.yaml')
        torch.set_num_threads(2)
    capture = cv2.VideoCapture(args.video)
    fps = capture.get(cv2.CAP_PROP_FPS)
    capture.set(cv2.CAP_PROP_POS_FRAMES, int(args.start * fps))
    trace, events = [], []
    try:
        for index in range(int(args.start * fps), int(args.end * fps)):
            ok, image = capture.read()
            if not ok:
                break
            if (index - int(args.start * fps)) % args.stride:
                continue
            # This recording has side bars during the first vehicle passage.
            if args.auto_crop:
                from scan_recorded_crossings import content
                image, _ = content(image)
            else:
                image = image[:315, 50:525]
            frame = tracker.process(index, index / fps, image)
            crossings = manager.update(frame)
            events.extend(crossings)
            if frame.detections or crossings:
                trace.append({'seconds': index / fps,
                              'detections': [{'track_id': d.track_id, 'class_id': d.class_id,
                                              'bbox': list(map(float, d.bbox))}
                                             for d in frame.detections],
                              'crossings': crossings})
            if index % 300 == 0:
                print('replayed_seconds', round(index/fps, 1), flush=True)
    finally:
        capture.release()
    args.output.write_text(json.dumps({'events': events, 'trace': trace,
        'limitation': 'Screen recording with approximate crop; not original RTSP frames'},
        ensure_ascii=False, indent=2))
    print('tracked_samples', len(trace), 'crossing_events', len(events), flush=True)
    assert any(e['class_id'] == 2 for e in events), 'Visible vehicle produced no car crossing event'


if __name__ == '__main__':
    main()
