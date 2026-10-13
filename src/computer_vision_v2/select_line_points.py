"""Select two independent lines, a straight line or an L-shaped boundary."""

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2

from computer_vision_v2.Line_Manager.line_detector import LineDetector
from computer_vision_v2.streaming.Source_Base import RTSPSource, VideoSource


def selection_config(points, width, height, shape, role, reference_side='inside'):
    normalized = [[round(x / width, 6), round(y / height, 6)] for x, y in points]
    if shape == 'independent':
        if len(points) != 5:
            raise ValueError('Two lines and one reference point require five clicks')
        return {'coordinate_space': 'normalized', 'lines': [
            {'line': normalized[i:i+2], 'inside_point': normalized[-1],
             'reference_side': reference_side, 'dir': role} for i in (0, 2)]}
    return {'coordinate_space': 'normalized', 'line': normalized[:-1],
            'inside_point': normalized[-1], 'reference_side': reference_side}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shape', choices=('independent', 'l', 'straight'), default='independent')
    parser.add_argument('--camera', help='Camera ID; defaults to the first configured camera')
    parser.add_argument('--reference-side', choices=('inside', 'outside'), default='inside',
                        help='Whether the final click is inside or outside the parking area')
    parser.add_argument('--config', type=Path,
                        default=Path(__file__).resolve().parent / 'reno/data/cameras.json')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    cameras = config.get('cameras', [])
    camera = next((c for c in cameras if args.camera is None or c['id'] == args.camera), None)
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

    height, width = original.shape[:2]
    independent = args.shape == 'independent'
    line_point_count = 3 if args.shape == 'l' else 2
    total_points = 5 if independent else line_point_count + 1
    points = []
    result = None
    window_name = 'Line selector'

    def redraw():
        frame = original.copy()
        vertices = points[:4] if independent else points[:line_point_count]
        for i, point in enumerate(vertices):
            cv2.circle(frame, point, 6, (0, 255, 255), -1)
            cv2.putText(frame, str(i + 1), (point[0] + 8, point[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 255), 2)
        edges = [(points[i], points[i+1]) for i in (0, 2)
                 if len(points) > i+1] if independent else zip(vertices, vertices[1:])
        for a, b in edges:
            cv2.line(frame, a, b, (0, 255, 255), 2)
        if len(points) == total_points:
            cv2.circle(frame, points[-1], 7, (0, 255, 0), -1)
        cv2.imshow(window_name, frame)

    def mouse_click(event, x, y, flags, param):
        nonlocal result
        if event != cv2.EVENT_LBUTTONDOWN or len(points) >= total_points:
            return
        points.append((x, y))
        if len(points) == total_points:
            candidate = selection_config(points, width, height, args.shape,
                                         camera['dir'], args.reference_side)
            try:
                LineDetector(camera['id'], candidate.get('line'), 'entry_exit',
                             inside_point=candidate.get('inside_point'),
                             coordinate_space='normalized', lines=candidate.get('lines'),
                             reference_side=args.reference_side)
            except ValueError:
                print('نقاط نامعتبر: ضلع‌ها نباید صفرطول باشند و نقطه داخل نباید روی امتداد ضلع‌ها باشد. R برای شروع مجدد')
            else:
                result = candidate
                print('\nPixel points:', points)
                print('\nNormalized config:')
                print(json.dumps(result, indent=2))
        redraw()

    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(window_name, mouse_click)
    redraw()
    print('کلیک ۱ و ۲: خط اول؛ کلیک ۳ و ۴: خط دوم؛ کلیک ۵: نقطه مشترک مرجع' if independent else
          'سه نقطه برای خط L و نقطه چهارم برای داخل پارکینگ' if args.shape == 'l'
          else 'دو نقطه برای خط مستقیم و نقطه سوم برای داخل پارکینگ')
    print('نقطه آخر: داخل پارکینگ' if args.reference_side == 'inside' else 'نقطه آخر: بیرون پارکینگ')
    print('S: ذخیره در تنظیمات دوربین؛ R: شروع مجدد؛ Q یا Escape: خروج بدون ذخیره')
    try:
        while True:
            key = cv2.waitKey(20) & 0xFF
            if key in (ord('q'), 27):
                break
            if key == ord('r'):
                points.clear()
                result = None
                redraw()
            if key == ord('s'):
                if result is None:
                    print('ابتدا همه نقاط معتبر را انتخاب کنید')
                    continue
                # Re-read to preserve changes made by other tools while selecting.
                latest = json.loads(args.config.read_text(encoding='utf-8'))
                target = next(c for c in latest['cameras'] if c['id'] == camera['id'])
                target.update(result)
                if not independent:
                    target.pop('lines', None)
                temporary = args.config.with_suffix(args.config.suffix + '.tmp')
                temporary.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + '\n',
                                     encoding='utf-8')
                temporary.replace(args.config)
                print('ذخیره شد؛ پایپ‌لاین را دوباره اجرا کنید')
            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
