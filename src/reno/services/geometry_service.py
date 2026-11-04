"""Bounded frame capture and atomic geometry persistence using the selector module."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

import cv2
from computer_vision_v2.Line_Manager.select_line_points import annotated_frame, save_geometry


def capture_frame(camera):
    with tempfile.TemporaryDirectory(prefix='plakino-geometry-') as folder:
        snapshot = Path(folder) / 'frame.png'
        environment = os.environ.copy()
        environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[2]) + os.pathsep + environment.get('PYTHONPATH', '')
        try:
            result = subprocess.run([sys.executable, '-m', 'reno.services.source_probe'],
                input=json.dumps({'source': camera['source'], 'type': camera['type'], 'snapshot_path': str(snapshot)}),
                text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12, env=environment)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError('دریافت تصویر ممکن نشد؛ اتصال دوربین را بررسی کنید') from error
        frame = cv2.imread(str(snapshot)) if result.returncode == 0 else None
        if frame is None:
            raise ValueError('تصویری از منبع دریافت نشد؛ دوباره تلاش کنید')
        return frame


def persist_selection(config_path, camera, selection, frame):
    config_path = Path(config_path)
    folder = config_path.parent / 'geometry_previews'
    folder.mkdir(parents=True, exist_ok=True)
    preview = folder / f'{uuid4().hex}.png'
    try:
        thumbnail = annotated_frame(frame, selection)
        if thumbnail.shape[1] > 640:
            thumbnail = cv2.resize(thumbnail, (640, round(thumbnail.shape[0] * 640 / thumbnail.shape[1])), interpolation=cv2.INTER_AREA)
        if not cv2.imwrite(str(preview), thumbnail):
            raise OSError('ذخیره تصویر پیش‌نمایش ممکن نشد')
        save_geometry(config_path, camera, selection, preview_path=preview)
    except Exception:
        preview.unlink(missing_ok=True)
        raise
    return str(preview)
