"""Offline diagnostics; never writes database records or changes camera settings.

Run from repo root: PYTHONPATH=src .venv/bin/python reports/uncertain_20261014/replay.py
Use --late to replay the historical last-car clip with current tracker/ROI.
"""
import contextlib
import io
import json
import sys
from collections import Counter
from pathlib import Path

import cv2

from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.ocr_worker.plate_candidates import Candidate, PlateCandidates
from computer_vision_v2.inference.plate_geometry import PreparedPlate
from computer_vision_v2.tracking.frame_info import Detection, TrackedFrame

OUT = Path(__file__).resolve().parent


def summarize(reader, samples):
    ranked = sorted((c for c in samples if c.prepared is not None),
                    key=lambda c: c.confidence * c.prepared.quality, reverse=True)
    readings = []
    for c in ranked:
        row = reader.recognize_candidates([c])['readings'][0]
        row.update(shape=list(c.crop.shape[:2]), quality=c.quality,
                   geometry_quality=c.prepared.quality)
        readings.append(row)
    decisions = {}
    for limit in (3, 5, 12):
        votes = Counter(r['text'] for r in readings[:limit]
                        if r['valid'] and r['confidence'] >= .8)
        decisions[str(limit)] = dict(votes)
    actual = reader.recognize_candidates(samples)
    actual.pop('image')
    return dict(actual=actual, ranked_readings=readings, votes_by_limit=decisions)


def main():
    reader = PlateReader()
    if '--single' in sys.argv:
        image = cv2.imread('src/captured_plates/eca1ac67c5e44cc5988a2d4119b8be9e.jpg')
        result = reader.recognize_candidates([
            Candidate(image, 0, 2095, 1, 1, prepared=PreparedPlate(image, 1))])
        result.pop('image')
        assert result['recognition_status'] == 'uncertain'
        assert len(result['readings']) == 1
        assert result['readings'][0]['text'] == '81ط79545'
        assert result['readings'][0]['confidence'] >= .8
        (OUT / 'single.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
        return
    pools = {str(near): PlateCandidates(reader, near=near) for near in (.25, .09)}
    results = {key: [] for key in pools}
    late = '--late' in sys.argv
    if late:
        from computer_vision_v2.tracking.tracker import CameraTracker
        from computer_vision_v2.Line_Manager.line_detector import LineDetectorManager
        config = json.loads(Path('src/reno/data/cameras.json').read_text())
        camera = config['cameras'][0]
        tracker = CameraTracker(camera['id'], config['model_path'],
                                config.get('detection_interval', 3), roi=camera.get('roi'))
        lines = LineDetectorManager({'cameras': [camera]})
        cap = cv2.VideoCapture('src/computer_vision_v2/video/InShot_20261012_210725035.mp4')
        fps = cap.get(cv2.CAP_PROP_FPS)
        def frames():
            for n in range(1, 2221):
                ok, image = cap.read()
                if not ok:
                    break
                if n < 2031:
                    continue
                with contextlib.redirect_stdout(io.StringIO()):
                    frame = tracker.process(n, n/fps, image)
                if n % 30 == 0:
                    print('processed', n, flush=True)
                yield frame, lines.update(frame)
        stream = frames()
    else:
        baseline = json.loads(Path('reports/exit_plate_trial/baseline.json').read_text())
        def frames():
            for row in baseline:
                n = row['frame']
                image = cv2.imread(f'reports/exit_plate_trial/vehicle_{n}.png')
                if image is None:
                    continue
                h, w = image.shape[:2]
                if '--cached-boxes' in sys.argv:
                    def cached_detect(vehicle, detections=row['detections']):
                        choices = sorted(detections, key=lambda d: d['score'], reverse=True)
                        plausible = [d for d in choices if 1.15 <=
                                     (d['bbox'][2]-d['bbox'][0])/max(d['bbox'][3]-d['bbox'][1], 1) <= 8]
                        if not choices:
                            return None
                        best = (plausible or choices)[0]
                        x1, y1, x2, y2 = best['bbox']
                        vh, vw = vehicle.shape[:2]
                        if x1 <= 0 or y1 <= 0 or x2 >= vw or y2 >= vh:
                            return None
                        pad = max(12, round((x2-x1)*.15))
                        return (vehicle[y1:y2, x1:x2].copy(), best['score'],
                                vehicle[max(0,y1-pad):min(vh,y2+pad),
                                        max(0,x1-pad):min(vw,x2+pad)].copy())
                    reader.detect_plate = cached_detect
                event = dict(camera_id='cached', track_id=1, class_id=2,
                             direction='exit', frame_idx=n, ts=n/30.01544071471942)
                yield TrackedFrame('cached', n, event['ts'], image,
                                   [Detection(1, (0, 0, w, h), 2, 1)]), [event]
        stream = frames()
    trace = []
    for frame, crossings in stream:
        for key, pool in pools.items():
            completed = pool.observe(frame, crossings)
            for passage in completed:
                results[key].append(dict(event=passage.event,
                                         **summarize(reader, passage.candidates)))
            trace.append(dict(near=key, frame=frame.frame_idx,
                              tracks=[dict(track=k[1], count=len(s.candidates),
                                           frames=[c.frame_idx for c in s.candidates],
                                           event=s.event is not None)
                                      for k, s in pool.tracks.items()]))
    for key, pool in pools.items():
        for state in pool.tracks.values():
            samples = state.candidates + ([state.fallback] if state.fallback else [])
            results[key].append(dict(event=state.event, unfinished=True,
                                     **summarize(reader, samples)))
    name = 'late' if late else 'cached_boxes' if '--cached-boxes' in sys.argv else 'cached_exit'
    (OUT / f'{name}.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    (OUT / f'{name}_trace.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
