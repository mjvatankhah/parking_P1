"""Inspect the deployed tracking → crossing → plate-candidate → OCR flow.

Run ``python -m computer_vision_v2.debug_plate --camera cam2``. The camera,
ROI, reference line, model and sampling limits come from Reno's camera config.
"""

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import time

import arabic_reshaper
from bidi.algorithm import get_display
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from computer_vision_v2.Line_Manager.line_detector import LineDetectorManager
from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates
from computer_vision_v2.streaming.Source_Base import VideoSource
from computer_vision_v2.tracking.frame_info import TrackedFrame
from computer_vision_v2.tracking.tracker import CameraTracker

# Change this value to choose the default starting point in the video.
START_SECONDS = 63
CONFIG_PATH = Path(__file__).resolve().parents[1] / 'reno/data/cameras.json'
FONT_PATH = Path(__file__).resolve().parents[1] / 'reno/assets/fonts/Vazirmatn-Regular.ttf'
WINDOW = 'Plate debug | Space: pause | N: next | S: save | Q/Esc: quit'


@lru_cache(maxsize=4)
def display_font(size):
    return ImageFont.truetype(str(FONT_PATH), size, layout_engine=ImageFont.Layout.BASIC)


def result_panel(row, width=1280):
    """Render the final passage result without reordering plate characters."""
    canvas = Image.new('RGB', (width, 190), (25, 25, 25))
    draw = ImageDraw.Draw(canvas)
    font = display_font(22)

    def persian(text, y):
        draw.text((width - 16, y), get_display(arabic_reshaper.reshape(text)),
                  font=font, fill=(230, 230, 230), anchor='rt')

    statuses = {
        'collecting': 'در حال جمع‌آوری نمونه‌های پلاک',
        'no_car': 'خودرویی شناسایی نشده است',
        'read': 'پلاک با توافق نمونه‌ها خوانده شد',
        'uncertain': 'نمونه‌ها به نتیجهٔ مطمئن نرسیدند',
        'unread': 'پلاک خوانده نشد',
        'ocr_error': 'خطا در خواندن پلاک؛ جزئیات در گزارش',
    }
    persian(f"وضعیت: {statuses.get(row['status'], row['status'])}", 8)
    draw.text((16, 8), f"Frame: {row.get('frame', '-')}   Track: {row.get('track', '-')}",
              font=font, fill=(230, 230, 230))
    plate = row.get('plate_text')
    if plate:
        glyphs = [arabic_reshaper.reshape(char) for char in plate]
        text_font = display_font(44)
        width_sum = sum(draw.textlength(char, font=text_font) for char in glyphs)
        if width_sum > width - 32:
            text_font = display_font(max(12, int(44 * (width - 32) / width_sum)))
            width_sum = sum(draw.textlength(char, font=text_font) for char in glyphs)
        x = (width - width_sum) / 2
        for char in glyphs:
            draw.text((x, 40), char, font=text_font, fill=(255, 220, 100))
            x += draw.textlength(char, font=text_font)
    else:
        draw.text((width // 2, 45), '—', font=display_font(44),
                  fill=(180, 180, 180), anchor='mt')
    persian(f"نمونه‌ها: {row.get('candidate_count', 0)}  |  جهت: {row.get('direction', '-')}", 98)
    persian(f"وضعیت خواندن: {row.get('status', '-')}  |  توافق نمونه‌ها معیار ثبت پلاک است", 130)
    persian('تصویر پایین: بهترین نمونهٔ آماده‌شده برای OCR', 158)
    return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)


def panel(image, title, width=640, height=360):
    canvas = np.full((height, width, 3), 25, dtype=np.uint8)
    if image is not None and image.size:
        h, w = image.shape[:2]
        scale = min(width / w, (height - 38) / h)
        resized = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))))
        rh, rw = resized.shape[:2]
        x, y = (width - rw) // 2, 38 + (height - 38 - rh) // 2
        canvas[y:y + rh, x:x + rw] = resized
    cv2.putText(canvas, title, (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                .55, (230, 230, 230), 1)
    return canvas


def choose_camera(config, camera_id):
    cameras = config.get('cameras', [])
    camera = next((c for c in cameras if camera_id is None or c['id'] == camera_id), None)
    if camera is None:
        raise ValueError(f'Camera {camera_id!r} was not found in the config')
    return camera


def inspect_passage(passage, reader):
    """Call the same OCR interface used by the worker, once per completed car."""
    event, candidates = passage.event, passage.candidates
    row = dict(frame=event['frame_idx'], track=event['track_id'],
               camera_id=event['camera_id'], direction=event['direction'],
               candidate_count=len(candidates))
    try:
        result = reader.recognize_candidates(candidates)
        row.update(plate_text=result['plate_text'], status=result['recognition_status'],
                   confidence=result['confidence'], readings=result['readings'])
    except Exception as exc:
        row.update(plate_text=None, status='ocr_error',
                   error=f'{type(exc).__name__}: {exc}', readings=[])
        result = {'image': None}
    return row, result['image']


def current_candidate(candidates, camera_id, track_id):
    key = candidates.aliases.get((camera_id, track_id))
    state = candidates.tracks.get(key)
    if state is None:
        return None, 0
    samples = state.candidates + ([state.fallback] if state.fallback else [])
    best = max(samples, key=lambda sample: sample.quality, default=None)
    return best, len(samples)


def dashboard_image(frame, tracked, candidates, rows, result_image):
    annotated = frame.copy()
    for det in tracked.detections:
        x1, y1, x2, y2 = map(int, det.bbox)
        color = (0, 220, 0) if det.class_id == 2 else (255, 180, 40)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        cv2.putText(annotated, f'id={det.track_id} class={det.class_id}',
                    (x1, max(20, y1)), cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2)
    cars = [det for det in tracked.detections if det.class_id == 2]
    vehicle = sample_image = None
    row = rows[-1] if rows else {'frame': tracked.frame_idx,
                                 'track': cars[0].track_id if cars else '-',
                                 'status': 'collecting' if cars else 'no_car'}
    if cars:
        det = cars[0]
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = map(int, det.bbox)
        vehicle = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        sample, count = current_candidate(candidates, tracked.camera_id, det.track_id)
        if not rows:
            row['candidate_count'] = count
        if sample is not None:
            sample_image = sample.prepared.image if sample.prepared is not None else sample.crop
    return np.vstack((
        np.hstack((panel(annotated, f'Frame {tracked.frame_idx} | tracked'),
                   panel(vehicle, 'Vehicle crop'))),
        np.hstack((panel(sample_image, 'Best buffered plate candidate'),
                   panel(result_image, 'Final OCR image after vehicle leaves'))),
        result_panel(row),
    ))


def create_debug_flow(config, camera, reader):
    tracker = CameraTracker(camera['id'], config['model_path'],
                            config.get('detection_interval', 3), roi=camera.get('roi'))
    lines = LineDetectorManager({'cameras': [camera]})
    candidates = PlateCandidates(reader, **config.get('plate_sampling', {}))
    return tracker, lines, candidates


def process_frame(tracked, lines, candidates, reader):
    crossings = lines.update(tracked)
    completed = candidates.observe(tracked, crossings)
    return [inspect_passage(passage, reader) for passage in completed]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG_PATH)
    parser.add_argument('--camera', help='Configured camera ID; defaults to the first camera')
    parser.add_argument('--video', help='Override the configured video source')
    parser.add_argument('--start-seconds', type=float, default=START_SECONDS,
                        help='Start from this second of the video (default: %(default)s)')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--max-frames', type=int, default=0)
    parser.add_argument('--output', type=Path, default=Path('reports/plate_debug'))
    args = parser.parse_args(argv)
    if not math.isfinite(args.start_seconds) or args.start_seconds < 0:
        parser.error('--start-seconds must be a finite, non-negative number')
    if args.max_frames < 0:
        parser.error('--max-frames must be non-negative')
    config = json.loads(args.config.read_text(encoding='utf-8'))
    try:
        camera = choose_camera(config, args.camera)
    except ValueError as exc:
        parser.error(str(exc))
    source = args.video or camera['source']
    if camera['type'] != 'video' and not args.video:
        parser.error('RTSP debugging requires a video recording via --video')
    video = VideoSource(source)
    reader = PlateReader()
    tracker, lines, candidates = create_debug_flow(config, camera, reader)
    output = args.output / time.strftime('%Y%m%d-%H%M%S')
    output.mkdir(parents=True, exist_ok=True)
    video.connect()
    capture = video.capture
    fps = video.fps
    index = 0
    if args.start_seconds:
        frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if frame_count > 0 and args.start_seconds >= frame_count / fps:
            video.disconnect()
            raise ValueError('Start time must be before the end of the video')
        if not capture.set(cv2.CAP_PROP_POS_MSEC, args.start_seconds * 1000):
            video.disconnect()
            raise RuntimeError('Video source does not support seeking')
        index = int(capture.get(cv2.CAP_PROP_POS_FRAMES))
        print(f'Starting at {args.start_seconds:g} seconds (next frame: {index + 1}).')
    processed = 0
    paused = stop = False
    last_frame = None
    last_result = None
    if not args.headless:
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    try:
        with (output / 'results.jsonl').open('w', encoding='utf-8') as log:
            while not stop and (not args.max_frames or processed < args.max_frames):
                ok, image = video.get_frame()
                if not ok:
                    break
                index += 1
                processed += 1
                tracked = tracker.process(index, index / fps, image)
                last_frame = tracked
                completed = process_frame(tracked, lines, candidates, reader)
                rows = []
                for row, result_image in completed:
                    rows.append(row)
                    last_result = result_image
                    record = json.dumps(row, ensure_ascii=False)
                    print(record, flush=True)
                    log.write(record + '\n')
                dashboard = dashboard_image(image, tracked, candidates, rows, last_result)
                snapshot = output / f'frame_{index}.jpg'
                if args.headless:
                    if not cv2.imwrite(str(snapshot), dashboard):
                        raise OSError(f'Could not save {snapshot}')
                    continue
                cv2.imshow(WINDOW, dashboard)
                while True:
                    key = cv2.waitKey(50 if paused else 1) & 0xFF
                    if key in (27, ord('q')) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                        stop = True
                        break
                    if key == ord('s'):
                        if not cv2.imwrite(str(snapshot), dashboard):
                            raise OSError(f'Could not save {snapshot}')
                        print(f'Saved: {snapshot}')
                    if key == ord(' '):
                        paused = not paused
                    if key == ord('n'):
                        paused = True
                        break
                    if not paused:
                        break
            if last_frame is not None:
                # A recording may end before the disappearance timeout expires.
                # Flush already observed crossings with an empty frame.
                timeout = max(candidates.exit_delay, candidates.stale) + .01
                empty = TrackedFrame(camera['id'], index + 1,
                                     last_frame.ts + timeout, last_frame.image, [])
                for row, _image in process_frame(empty, lines, candidates, reader):
                    record = json.dumps(row, ensure_ascii=False)
                    print(record, flush=True)
                    log.write(record + '\n')
    finally:
        video.disconnect()
        if not args.headless:
            cv2.destroyAllWindows()
        print(f'Debug output: {output}')


if __name__ == '__main__':
    main()
