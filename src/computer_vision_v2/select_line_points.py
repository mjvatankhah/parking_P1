import json
from pathlib import Path

import cv2


# مسیر و شماره فریم دلخواهت را اینجا تغییر بده.
VIDEO_PATH = Path(__file__).resolve().parent / "video" / "4_5840467138086702154.mp4"

# یک فریم از ویدیو می‌خوانیم.
video = cv2.VideoCapture(str(VIDEO_PATH))

success, frame = video.read()
video.release()

if not success:
    raise RuntimeError("فریم ویدیو خوانده نشد")

height, width = frame.shape[:2]
points = []
window_name = "Line selector"


def mouse_click(event, x, y, flags, param):
    if event != cv2.EVENT_LBUTTONDOWN or len(points) == 3:
        return

    points.append((x, y))
    cv2.circle(frame, (x, y), 6, (0, 255, 255), -1)

    # دو نقطه اول، خط مرجع را می‌سازند.
    if len(points) == 2:
        cv2.line(frame, points[0], points[1], (0, 255, 255), 2)

    # نقطه سوم، سمت داخل پارکینگ را مشخص می‌کند.
    if len(points) == 3:
        cv2.circle(frame, points[2], 7, (0, 255, 0), -1)

        normalized = [
            [round(px / width, 6), round(py / height, 6)]
            for px, py in points
        ]

        result = {
            "coordinate_space": "normalized",
            "line": normalized[:2],
            "inside_point": normalized[2],
        }

        print("\nPixel points:", points)
        print("\nNormalized config:")
        print(json.dumps(result, indent=2))

    cv2.imshow(window_name, frame)


cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
cv2.setMouseCallback(window_name, mouse_click)
cv2.imshow(window_name, frame)

print("دو نقطه برای خط و نقطه سوم برای داخل پارکینگ؛ Q برای خروج")

while True:
    if cv2.waitKey(20) & 0xFF in (ord("q"), 27):
        break

cv2.destroyAllWindows()
