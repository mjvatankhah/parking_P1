"""Select a camera ROI, reference line and parking side on a still frame."""

import argparse
from dataclasses import dataclass, field
from enum import Enum, auto
import json
import math
from pathlib import Path
import time

import cv2
import numpy as np

from computer_vision_v2.Line_Manager.line_detector import LineDetector
from computer_vision_v2.streaming.Source_Base import RTSPSource, VideoSource


class Stage(Enum):
    ROI = auto()
    LINE = auto()
    SIDE = auto()


@dataclass
class Selection:
    """Geometry and transitions, independent of the OpenCV event loop."""

    width: int
    height: int
    stage: Stage = Stage.ROI
    roi: list = field(default_factory=list)
    line: list = field(default_factory=list)
    inside_point: tuple | None = None
    selected_point: tuple | None = None
    outside: bool = False

    def normalize(self, points):
        return [[x / self.width, y / self.height] for x, y in points]

    def click(self, point):
        if self.stage == Stage.ROI:
            self.roi.append(point)
        elif self.stage == Stage.LINE:
            if self.line and point == self.line[-1]:
                raise ValueError('Choose a different endpoint.')
            if self.roi and cv2.pointPolygonTest(np.asarray(self.roi, np.float32), point, False) < 0:
                raise ValueError('Reference line must be inside ROI.')
            self.line.append(point)
            if len(self.line) == 3:
                self.confirm()
        else:
            self.select_side(point)

    def confirm(self):
        if self.stage == Stage.ROI:
            if self.roi and (len(self.roi) < 3 or
                             cv2.contourArea(np.asarray(self.roi, np.float32)) <= 0):
                raise ValueError('Select an ROI with at least three corners.')
            self.stage = Stage.LINE
        elif self.stage == Stage.LINE:
            if len(self.line) < 2:
                raise ValueError('Select two endpoints first.')
            self.stage = Stage.SIDE

    def select_side(self, point):
        inside = point
        if self.outside:
            # Reflect across the shared corner (or straight-line midpoint).
            # This reverses the side of every segment without changing the schema.
            anchor = (self.line[1] if len(self.line) == 3 else
                      tuple((a + b) / 2 for a, b in zip(*self.line)))
            delta = tuple(a - p for a, p in zip(anchor, point))
            scale = 1.0
            for a, d, limit in zip(anchor, delta, (self.width, self.height)):
                if d:
                    scale = min(scale, ((limit - a) if d > 0 else a) / abs(d) * 0.9)
            if scale <= 0:
                raise ValueError('Choose inside mode (I) and click inside the parking area.')
            inside = tuple(a + scale * d for a, d in zip(anchor, delta))
        LineDetector('selection', self.normalize(self.line), 'entry_exit',
                     inside_point=self.normalize([inside])[0], coordinate_space='normalized')
        self.inside_point = inside
        self.selected_point = point

    def set_side_mode(self, outside):
        self.outside = outside
        self.inside_point = None
        self.selected_point = None

    def geometry(self):
        if self.stage != Stage.SIDE or self.inside_point is None:
            raise ValueError('Select the parking side before saving.')
        return dict(roi=self.normalize(self.roi) if self.roi else None,
                    line=self.normalize(self.line),
                    inside_point=self.normalize([self.inside_point])[0],
                    coordinate_space='normalized')


def save_geometry(path, camera, selection):
    """Preserve unrelated edits and reject changes to the selected source."""
    geometry = selection.geometry()
    latest = json.loads(path.read_text(encoding='utf-8'))
    target = next((item for item in latest.get('cameras', []) if item['id'] == camera['id']), None)
    if target is None or any(target.get(key) != camera.get(key) for key in ('source', 'dir', 'type')):
        raise ValueError('Camera settings changed; reopen the selector.')
    target.update(geometry)
    temporary = path.with_suffix('.geometry.tmp')
    temporary.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def draw_frame(original, selection, cursor, message='', timestamp=None):
    frame = original.copy()
    if len(selection.roi) > 1:
        cv2.polylines(frame, [np.asarray(selection.roi, np.int32)],
                      selection.stage != Stage.ROI, (255, 200, 0), 2)
    for index, point in enumerate(selection.line):
        cv2.circle(frame, point, 6, (0, 255, 255), -1)
        cv2.putText(frame, str(index + 1), (point[0] + 8, point[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 255), 2)
    for start, end in zip(selection.line, selection.line[1:]):
        cv2.line(frame, start, end, (0, 255, 255), 2)
    if selection.stage == Stage.SIDE:
        target = selection.selected_point or cursor
        phase = time.monotonic() if timestamp is None else timestamp
        offset = round(30 + 7 * math.sin(phase * 5))
        # Keep the animated diagonal pointer on screen near image edges.
        dx = offset if target[0] < selection.width / 2 else -offset
        dy = offset if target[1] < selection.height / 2 else -offset
        color = (0, 150, 255) if selection.outside else (0, 255, 0)
        cv2.arrowedLine(frame, (target[0] + dx, target[1] + dy), target,
                        color, 3, cv2.LINE_AA, tipLength=.35)
        cv2.circle(frame, target, 5, color, 1, cv2.LINE_AA)
    instructions = {
        Stage.ROI: 'ROI (optional): click corners; Enter / S: confirm or skip if empty',
        Stage.LINE: 'Line: 2 points + S to confirm, or click a 3rd point for L',
        Stage.SIDE: f'Click {"OUTSIDE" if selection.outside else "INSIDE"} parking; I/O: change side; S: save',
    }
    for index, text in enumerate((instructions[selection.stage], 'R: restart | Q / Esc: cancel', message)):
        cv2.putText(frame, text, (15, 30 + index * 28), cv2.FONT_HERSHEY_SIMPLEX,
                    .55, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def run_selector(original, camera, config_path):
    height, width = original.shape[:2]
    selection = Selection(width, height)
    cursor = (width // 2, height // 2)
    message = ''
    window = 'Line selector'

    def mouse_event(event, x, y, _flags, _param):
        nonlocal cursor, message
        cursor = (x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            try:
                selection.click(cursor)
                message = ''
            except ValueError as error:
                message = str(error)

    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    scale = min(1., 1280 / width, 800 / height)
    cv2.resizeWindow(window, round(width * scale), round(height * scale))
    cv2.setMouseCallback(window, mouse_event)
    try:
        while True:
            cv2.imshow(window, draw_frame(original, selection, cursor, message))
            key = cv2.waitKey(20) & 0xFF
            if key in (ord('q'), 27) or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
            try:
                if key == ord('r'):
                    selection = Selection(width, height)
                    message = ''
                elif key in (ord('i'), ord('o')) and selection.stage == Stage.SIDE:
                    selection.set_side_mode(key == ord('o'))
                    message = ''
                elif key in (ord('s'), 10, 13):
                    if selection.stage == Stage.SIDE:
                        save_geometry(config_path, camera, selection)
                        print('تنظیمات ذخیره شد؛ برنامهٔ پردازش را دوباره اجرا کنید.')
                        break
                    selection.confirm()
                    message = ''
            except (ValueError, OSError) as error:
                message = str(error)
    finally:
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', help='Camera ID; defaults to the first configured camera')
    parser.add_argument('--config', type=Path,
                        default=Path(__file__).resolve().parents[2] / 'reno/data/cameras.json')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    camera = next((c for c in config.get('cameras', [])
                   if args.camera is None or c['id'] == args.camera), None)
    if camera is None:
        parser.error('No matching camera in configuration')
    source = (RTSPSource(camera['source']) if camera['type'] == 'rtsp'
              else VideoSource(camera['source']))
    try:
        source.connect()
        success, original = source.get_frame()
    finally:
        source.disconnect()
    if not success:
        raise RuntimeError('فریم دوربین خوانده نشد')
    run_selector(original, camera, args.config)


if __name__ == '__main__':
    main()
