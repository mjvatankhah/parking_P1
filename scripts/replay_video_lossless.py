"""Sequential offline replay: no queue/latest-slot loss and no database access.

Uses production tracking, crossing, sampling, detector, geometry and OCR.
EOF finalization is explicit and identified separately from natural departures.
"""
import argparse
import contextlib
from dataclasses import asdict
import json
import logging
from pathlib import Path
import time

import cv2
import numpy as np
import torch

from computer_vision_v2.tracking.tracker import CameraTracker
from computer_vision_v2.Line_Manager.line_detector import LineDetectorManager
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates
from computer_vision_v2.inference.plate_ocr import PlateReader


def json_number(value):
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=json_number))
    temporary.replace(path)


class MeasuredReader(PlateReader):
    def __init__(self, output):
        super().__init__()
        self.output = output
        self.calls = {'primary': 0, 'fallback': 0, 'accepted': 0}
        self.seconds = {'primary': 0., 'fallback': 0., 'ocr': 0.}
        self.frame_idx = 0

    def _detect_plate(self, crop, detector, input_name):
        name = 'primary' if detector is self.detector else 'fallback'
        self.calls[name] += 1
        start = time.perf_counter()
        try:
            return super()._detect_plate(crop, detector, input_name)
        finally:
            self.seconds[name] += time.perf_counter()-start

    def detect_plate(self, crop):
        result = super().detect_plate(crop)
        if result is not None:
            self.calls['accepted'] += 1
        return result


def run(config, output, max_frames=None):
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'config.json', config)
    camera = config['cameras'][0]
    if camera['type'] != 'video' or len(config['cameras']) != 1:
        raise ValueError('This diagnostic requires exactly one video camera')
    cv2.setNumThreads(2)
    torch.set_num_threads(2)
    capture = cv2.VideoCapture(camera['source'])
    if not capture.isOpened():
        raise ValueError('Could not open configured video')
    fps = capture.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        raise ValueError('Video FPS is unavailable')
    metadata_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    # Independent decode census catches early EOF in the measured replay.
    expected = 0
    while capture.read()[0]:
        expected += 1
    capture.release()
    capture = cv2.VideoCapture(camera['source'])
    target = min(expected, max_frames) if max_frames else expected
    log = (output/'pipeline.log').open('w')
    logging.basicConfig(stream=log, level=logging.INFO, force=True)
    reader = MeasuredReader(output)
    tracker = CameraTracker(camera['id'], config['model_path'],
                            config.get('detection_interval', 3), roi=camera.get('roi'))
    lines = LineDetectorManager(config)
    pool = PlateCandidates(reader, **config.get('plate_sampling', {}))
    events, crossings = [], []
    seconds = {'decode': 0., 'tracking': 0., 'observation': 0.}
    processed = 0
    start = time.perf_counter()
    trace = (output/'frames.jsonl').open('w')

    def finish(passage, reason):
        before = time.perf_counter()
        result = reader.recognize_candidates(passage.candidates)
        reader.seconds['ocr'] += time.perf_counter()-before
        image = result.pop('image')
        index = len(events)+1
        if image is not None:
            cv2.imwrite(str(output/f'event_{index}_plate.png'), image)
        candidates = []
        for i, c in enumerate(passage.candidates):
            cv2.imwrite(str(output/f'event_{index}_candidate_{i}_raw.png'), c.crop)
            if c.prepared is not None:
                cv2.imwrite(str(output/f'event_{index}_candidate_{i}_prepared.png'), c.prepared.image)
            candidates.append(dict(frame=c.frame_idx, ts=c.ts, confidence=c.confidence,
                                   quality=c.quality, prepared=c.prepared is not None))
        events.append(dict(event=passage.event, finalized_at=processed, reason=reason,
                           candidates=candidates, result=result))
        write_json(output/'events.json', events)
        print('EVENT', index, 'frame', processed, result, flush=True)

    def snapshot(complete=False):
        data = dict(complete=complete, metadata_frames=metadata_frames, decodable_frames=expected,
                    target_frames=target, processed_frames=processed, dropped_frames=0,
                    database_writes=False, elapsed_seconds=time.perf_counter()-start,
                    video_seconds=processed/fps, fps=fps, stage_seconds=seconds,
                    detector_calls=reader.calls, reader_seconds=reader.seconds,
                    crossings=crossings, vehicle_events=events,
                    active_tracks=len(pool.tracks), vehicle_yolo_calls=tracker.yolo_calls,
                    flow_frames=tracker.flow_frames, flow_fallbacks=tracker.flow_fallbacks,
                    scope='full_video' if target==expected else 'prefix_only',
                    mode='sequential; timestamps from video; no new image filters')
        write_json(output/'summary.json', data)
        return data

    try:
        while processed < target:
            before = time.perf_counter()
            ok, image = capture.read()
            seconds['decode'] += time.perf_counter()-before
            if not ok:
                raise RuntimeError(f'Early EOF at {processed}, expected {target}')
            processed += 1
            reader.frame_idx = processed
            before = time.perf_counter()
            with contextlib.redirect_stdout(log):
                frame = tracker.process(processed, processed/fps, image)
            seconds['tracking'] += time.perf_counter()-before
            before = time.perf_counter()
            current = lines.update(frame)
            crossings.extend(current)
            complete = pool.observe(frame, current)
            seconds['observation'] += time.perf_counter()-before
            trace.write(json.dumps(dict(frame=processed, ts=frame.ts,
                             detections=[asdict(d) for d in frame.detections],
                             crossings=current, tracks=[dict(key=list(k), aliases=[list(a) for a in s.aliases],
                             candidates=[c.frame_idx for c in s.candidates], pending=s.event is not None)
                             for k,s in pool.tracks.items()]), default=json_number)+'\n')
            for passage in complete:
                finish(passage, 'left_roi')
            if processed%30==0:
                snapshot(); trace.flush();log.flush()
                print('PROGRESS',processed,'/',target,'elapsed',round(time.perf_counter()-start),flush=True)
        for key in list(pool.tracks):
            passage = pool._retire(key, processed/fps)
            if passage is not None:
                finish(passage, 'eof' if target==expected else 'prefix_end')
        assert processed == target
        vehicle_crossings = [c for c in crossings if c['class_id']==2]
        data=snapshot(True)
        data['vehicle_crossing_count']=len(vehicle_crossings)
        data['finalized_vehicle_events']=len(events)
        data['remaining_pending_events']=sum(s.event is not None for s in pool.tracks.values())
        write_json(output/'summary.json',data)
        print('DONE',processed,'frames;',len(events),'vehicle events;',round(data['elapsed_seconds']),'seconds',flush=True)
    except BaseException:
        snapshot(False)
        raise
    finally:
        capture.release();trace.close();log.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('src/reno/data/cameras.json'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-frames',type=int)
    args=parser.parse_args()
    run(json.loads(args.config.read_text()),args.output,args.max_frames)
