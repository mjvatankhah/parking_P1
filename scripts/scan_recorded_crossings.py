"""Scan an entire screen recording with the baseline detector, without DB writes."""
import argparse
import json
from pathlib import Path
import time

import cv2
import numpy as np
import torch
from ultralytics import YOLO


def content(frame):
    # Screen player switches between full width and pillarboxed camera views.
    left = 50 if frame[:300, :20].mean() < 8 else 0
    right = 525 if frame[:300, 550:].mean() < 8 else frame.shape[1]
    return frame[:315, left:right], [left, 0, right, 315]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    torch.set_num_threads(2)
    model = YOLO('yolov8n.pt')
    # Ultralytics CPU setup resets Torch's thread count. Limit threads after
    # initialization to avoid oversubscription in the audit environment.
    model.predict(np.zeros((315, 475, 3), dtype=np.uint8), imgsz=(256, 416), verbose=False)
    torch.set_num_threads(2)
    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    args.output.mkdir(parents=True, exist_ok=True)
    saved = args.output / 'samples.json'
    samples = json.loads(saved.read_text()) if saved.exists() else []
    resume_index = samples[-1]['index'] + 1 if samples else 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, resume_index)
    started = time.monotonic()
    try:
        for index in range(resume_index, count):
            if not cap.grab():
                break
            if index % round(fps):
                continue
            ok, frame = cap.retrieve()
            if not ok:
                continue
            image, crop = content(frame)
            detections = {}
            for label, size in [('deployed_size', (256, 416)), ('larger_size', 640)]:
                result = model.predict(image, imgsz=size, verbose=False)[0]
                detections[label] = [
                    {'class': model.names[int(c)], 'class_id': int(c),
                     'confidence': float(conf), 'bbox': list(map(float, box))}
                    for c, conf, box in zip(result.boxes.cls, result.boxes.conf, result.boxes.xyxy)]
            samples.append({'seconds': index / fps, 'index': index, 'crop': crop,
                            'brightness': float(image.mean()), **detections})
            if any(d['class_id'] in (2, 7, 28) for ds in detections.values() for d in ds):
                cv2.imwrite(str(args.output / f'frame_{index:06d}.jpg'), frame)
            if len(samples) % 60 == 0:
                print('scanned_seconds', round(index/fps), 'elapsed', round(time.monotonic()-started), flush=True)
                (args.output / 'samples.json').write_text(json.dumps(samples))
    finally:
        cap.release()
    (args.output / 'samples.json').write_text(json.dumps(samples, indent=2))
    print('COMPLETE', len(samples), 'samples', 'duration', count/fps, flush=True)


if __name__ == '__main__':
    main()
