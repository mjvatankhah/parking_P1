"""Select a straight or L-shaped reference line on a configured camera frame."""

import argparse
import json
from pathlib import Path

import cv2

from computer_vision_v2.Line_Manager.line_detector import LineDetector
from computer_vision_v2.streaming.Source_Base import RTSPSource, VideoSource


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shape', choices=('l', 'straight'), default='l')
    parser.add_argument('--camera', help='Camera ID; defaults to the first configured camera')
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
    line_point_count = 3 if args.shape == 'l' else 2
    points = []
    window_name = 'Line selector'

    def redraw():
        frame = original.copy()
        vertices = points[:line_point_count]
        for i, point in enumerate(vertices):
            cv2.circle(frame, point, 6, (0, 255, 255), -1)
            cv2.putText(frame, str(i + 1), (point[0] + 8, point[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 255), 2)
        for a, b in zip(vertices, vertices[1:]):
            cv2.line(frame, a, b, (0, 255, 255), 2)
        if len(points) > line_point_count:
            cv2.circle(frame, points[-1], 7, (0, 255, 0), -1)
        cv2.imshow(window_name, frame)

    def mouse_click(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN or len(points) >= line_point_count + 1:
            return
        points.append((x, y))
        if len(points) == line_point_count + 1:
            normalized = [[round(px / width, 6), round(py / height, 6)]
                          for px, py in points]
            result = {'coordinate_space': 'normalized',
                      'line': normalized[:line_point_count],
                      'inside_point': normalized[-1]}
            try:
                LineDetector(camera['id'], result['line'], 'entry_exit',
                             inside_point=result['inside_point'], coordinate_space='normalized')
            except ValueError:
                print('نقاط نامعتبر: ضلع‌ها نباید صفرطول باشند و نقطه داخل نباید روی امتداد ضلع‌ها باشد. R برای شروع مجدد')
            else:
                print('\nPixel points:', points)
                print('\nNormalized config:')
                print(json.dumps(result, indent=2))
        redraw()

    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(window_name, mouse_click)
    redraw()
    print('سه نقطه برای خط L و نقطه چهارم برای داخل پارکینگ' if args.shape == 'l'
          else 'دو نقطه برای خط مستقیم و نقطه سوم برای داخل پارکینگ')
    print('R: شروع مجدد؛ Q یا Escape: خروج. خروجی را در تنظیمات وارد کنید؛ فایل خودکار تغییر نمی‌کند.')
    try:
        while True:
            key = cv2.waitKey(20) & 0xFF
            if key in (ord('q'), 27):
                break
            if key == ord('r'):
                points.clear()
                redraw()
            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
