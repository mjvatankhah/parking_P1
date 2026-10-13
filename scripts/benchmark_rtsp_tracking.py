"""Measure 200 processed live frames using the configured capture/tracker path."""
import json
import os
from pathlib import Path
import statistics
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from computer_vision_v2.streaming.Streming_Cameras import StreamManager


def main():
    config = json.loads((ROOT / 'src/computer_vision_v2/reno/data/cameras.json').read_text())
    camera = next(c for c in config['cameras'] if c['id'] == 'cam2')
    output = ROOT / 'reports/rtsp_benchmark/current_200_frames.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    stream = StreamManager(camera['id'], camera['source'], 'rtsp', config['model_path'], config.get('detection_interval', 3))
    original = stream.tracker.process
    done = threading.Event()
    rows = []
    state = {'warmup': 0, 'start': None, 'capture_start': 0}
    report = {'model': config['model_path'], 'detection_interval': config.get('detection_interval', 3),
              'warmup_frames': 10, 'requested_frames': 200, 'scope': 'live RTSP capture and vehicle/person tracking; no plate OCR', 'frames': rows}

    def save():
        elapsed = time.monotonic() - state['start'] if state['start'] else 0
        report.update(processed_frames=len(rows), seconds=elapsed, complete=len(rows) == 200,
                      processing_fps=len(rows) / elapsed if elapsed else 0,
                      captured_frames=stream._capture_index - state['capture_start'])
        for key in ('yolo', 'flow', 'fallback'):
            report[key] = sum(r[key] for r in rows)
        if rows:
            durations = [r['processing_seconds'] for r in rows]
            report['mean_processing_ms'] = statistics.mean(durations) * 1000
            report['median_processing_ms'] = statistics.median(durations) * 1000
        temp = output.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2))
        temp.replace(output)

    def process(index, ts, image):
        before = (stream.tracker.yolo_calls, stream.tracker.flow_frames, stream.tracker.flow_fallbacks)
        start = time.monotonic()
        try:
            result = original(index, ts, image)
        except Exception as exc:
            report['error_type'] = type(exc).__name__
            stream._stop.set()
            done.set()
            raise
        duration = time.monotonic() - start
        if state['warmup'] < 10:
            state['warmup'] += 1
            if state['warmup'] == 10:
                state['start'] = time.monotonic()
                state['capture_start'] = stream._capture_index
                print('Warmup complete', flush=True)
            return result
        after = (stream.tracker.yolo_calls, stream.tracker.flow_frames, stream.tracker.flow_fallbacks)
        rows.append(dict(index=index, processing_seconds=duration, yolo=after[0]-before[0], flow=after[1]-before[1], fallback=after[2]-before[2]))
        report['input_wh'] = [image.shape[1], image.shape[0]]
        if len(rows) % 25 == 0:
            save()
            print(f"Processed {len(rows)}/200; {report['processing_fps']:.3f} FPS", flush=True)
        if len(rows) == 200:
            stream._stop.set()
            done.set()
        return result

    stream.tracker.process = process
    # Native decoder diagnostics can expose camera credentials.
    stderr = os.dup(2)
    with open(os.devnull, 'w') as quiet:
        os.dup2(quiet.fileno(), 2)
        try:
            stream.start()
            finished = done.wait(900)
            stream.stop()
            if not finished or len(rows) != 200:
                save()
                print('Incomplete benchmark; see checkpoint', flush=True)
                return 1
        finally:
            os.dup2(stderr, 2)
            os.close(stderr)
    print(json.dumps({k: v for k, v in report.items() if k != 'frames'}, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
