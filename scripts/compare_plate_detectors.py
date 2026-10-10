"""Replay a video through the real pipeline, comparing identical OCR inputs.

No camera registration or database writes occur during this offline trial.
"""
import argparse
import contextlib
import hashlib
import json
import logging
from pathlib import Path
import time
from unittest.mock import patch

import cv2

from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.main_v2 import Pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    video = cv2.VideoCapture(str(args.video.resolve()))
    try:
        if not video.isOpened():
            raise ValueError('Test video could not be opened')
        metadata_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        expected_frames = 0
        while video.read()[0]:
            expected_frames += 1
    finally:
        video.release()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    camera = dict(config['cameras'][0], type='video', source=str(args.video.resolve()))
    config['cameras'] = [camera]
    comparisons, events = [], []

    class ComparisonReader:
        def read(self, crop):
            index = len(comparisons) + 1
            input_path = args.output / f'vehicle_{index}.png'
            if not cv2.imwrite(str(input_path), crop):
                raise OSError(f'Could not save {input_path}')
            result = {'input': str(input_path.resolve()), 'shape': list(crop.shape)}
            comparisons.append(result)
            return None, 0.0, None

    def collect_events(items, _alive):
        while True:
            item = items.get()
            try:
                if item is None:
                    return
                events.append(item)
            finally:
                items.task_done()

    with (args.output / 'pipeline.log').open('w', encoding='utf-8') as log:
        logging.basicConfig(stream=log, level=logging.INFO)
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log), \
             patch('computer_vision_v2.main_v2.PlateReader', ComparisonReader), \
             patch('computer_vision_v2.main_v2.database_worker', collect_events), \
             patch('computer_vision_v2.streaming.Cameras_Manager.prepare_camera'):
            pipeline = Pipeline(config)
            try:
                pipeline.start()
                streams = list(pipeline.camera_manager.streams.values())
                deadline = time.monotonic() + 600
                while any(stream._capture_thread.is_alive() for stream in streams):
                    if time.monotonic() > deadline:
                        raise TimeoutError('Video replay exceeded ten minutes')
                    time.sleep(.5)
                time.sleep(2)
            finally:
                pipeline.stop()
            if pipeline._worker_stages:
                raise RuntimeError('Pipeline workers did not drain')
            decoded_frames = streams[0]._capture_index
            if decoded_frames != expected_frames:
                raise RuntimeError(f'Incomplete replay: {decoded_frames}/{expected_frames} frames')
            if not comparisons:
                raise RuntimeError('No vehicle crop reached the plate reader')

    # Compare after capture so slow CPU inference cannot exhaust worker shutdown timeouts.
    readers = {
        'baseline': PlateReader(detector_path=args.baseline),
        'candidate': PlateReader(detector_path=args.candidate),
    }
    for result in comparisons:
        crop = cv2.imread(result['input'])
        for name, reader in readers.items():
            started = time.perf_counter()
            text, confidence, image_path = reader.read(crop)
            result[name] = {
                'plate_text': text, 'confidence': confidence,
                'image_path': image_path,
                'elapsed_seconds': time.perf_counter() - started,
            }

    report = {
        'video': str(args.video.resolve()),
        'decoded_frames': decoded_frames,
        'expected_frames': expected_frames,
        'metadata_frames': metadata_frames,
        'models': {name: {'path': str(path.resolve()),
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                   for name, path in [('baseline', args.baseline), ('candidate', args.candidate)]},
        'comparisons': comparisons,
        'crossing_events_before_recognition': events,
        'database_writes': False,
    }
    report_path = args.output / 'comparison.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f'Report: {report_path}')


if __name__ == '__main__':
    main()
