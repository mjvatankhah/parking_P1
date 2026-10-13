"""Inspect vehicle tracking, plate detection, and OCR on a video or RTSP stream.

From project root: uv run python -m computer_vision_v2.debug_plate
Or from this module's directory: uv run debug_plate.py
"""

import argparse
import json
import math
import time
from functools import lru_cache
from pathlib import Path

import arabic_reshaper
import cv2
import numpy as np
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

from computer_vision_v2.best_crop_selector import BestCropSelector
from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.tracking.tracker import CameraTracker

MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parents[1]
CONFIG_PATH = MODULE_DIR / "reno/data/cameras.json"
FONT_PATH = MODULE_DIR / "reno/assets/fonts/Vazirmatn-Regular.ttf"
VIDEO_SOURCE = str(MODULE_DIR / "video/InShot_20261012_210725035.mp4")
START_SECONDS = 0.0
----------------------------------------------
WINDOW = "Plate debug | Space: pause | N: step | S: save | Q: quit"


class InspectableReader(PlateReader):
    """Capture OCR intermediates using the application's actual pipeline."""

    def read(self, crop):
        self.plate_crop = None
        self.det_conf = None
        self.ocr_conf = None
        self.ocr_input_image = None
        return super().read(crop)

    def detect_plate(self, crop):
        result = super().detect_plate(crop)
        if result is not None:
            self.plate_crop, self.det_conf, _ = result
        return result

    def _prep_ocr(self, crop):
        blob = super()._prep_ocr(crop)
        image = (blob[0].transpose(1, 2, 0) * 255).clip(0, 255).astype(np.uint8)
        self.ocr_input_image = (
            cv2.cvtColor(image[:, :, 0], cv2.COLOR_GRAY2BGR)
            if image.shape[2] == 1 else image[:, :, ::-1].copy()
        )
        return blob

    def _ctc_decode(self, logits):
        result = super()._ctc_decode(logits)
        self.ocr_conf = result[1]
        return result


@lru_cache(maxsize=4)
def font(size):
    return ImageFont.truetype(str(FONT_PATH), size, layout_engine=ImageFont.Layout.BASIC)


def image_panel(image, label, width=640, height=360):
    canvas = np.full((height, width, 3), 25, dtype=np.uint8)
    if image is not None and image.size:
        h, w = image.shape[:2]
        scale = min(width / w, (height - 38) / h)
        scaled = cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))))
        sh, sw = scaled.shape[:2]
        x, y = (width - sw) // 2, 38 + (height - 38 - sh) // 2
        canvas[y:y + sh, x:x + sw] = scaled
    cv2.putText(canvas, label[:88], (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (230, 230, 230), 1)
    return canvas


def text_panel(row, width=1280):
    canvas = Image.new("RGB", (width, 180), (25, 25, 25))
    draw = ImageDraw.Draw(canvas)

    def rtl(message, y):
        draw.text((width - 16, y), get_display(arabic_reshaper.reshape(message)),
                  font=font(21), fill=(235, 235, 235), anchor="rt")

    statuses = {
        "read": "متن پلاک استخراج شد",
        "no_car": "خودرویی شناسایی نشد",
        "no_plate": "محل پلاک پیدا نشد",
        "empty_ocr": "پلاک پیدا شد ولی OCR متنی تولید نکرد",
        "empty_vehicle_crop": "برش خودرو خالی است",
        "inference_error": "خطا در اجرای تشخیص یا OCR",
    }
    rtl(statuses.get(row["status"], row["status"]), 10)
    draw.text((16, 10), f"Frame: {row['frame']}  Time: {row['video_seconds']:.2f}s  "
              f"Track: {row.get('track', '-')}", font=font(18), fill=(230, 230, 230))
    value = row.get("text")
    if value:
        # Render plate glyphs in their original sequence; bidi reverses plate digits.
        glyphs = [arabic_reshaper.reshape(ch) for ch in str(value)]
        f = font(40)
        x = (width - sum(draw.textlength(ch, font=f) for ch in glyphs)) / 2
        for ch in glyphs:
            draw.text((x, 47), ch, font=f, fill=(255, 220, 100))
            x += draw.textlength(ch, font=f)
    conf = row.get("ocr_confidence")
    rtl(f"امتیاز OCR: {conf:.3f}" if conf is not None else "امتیاز OCR: نامشخص", 113)
    rtl("نمایش: فریم، برش خودرو، پلاک تشخیص داده شده و ورودی OCR", 147)
    return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)


def inspect(reader, selector, frame, detection):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = map(int, detection.bbox)
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    crop = frame[y1:y2, x1:x2].copy()
    row = {
        "track": detection.track_id,
        "bbox": [x1, y1, x2, y2],
        "predicted": detection.is_predicted,
        "vehicle_confidence": float(detection.confidence),
        "crop_eligible": selector._score(frame, detection.bbox, detection.confidence) is not None,
    }
    if not crop.size:
        return None, None, None, dict(row, status="empty_vehicle_crop")
    try:
        text, confidence, path = reader.read(crop)
        row.update(
            text=text, confidence=confidence, plate_path=str(path) if path is not None else None,
            detector_confidence=reader.det_conf, ocr_confidence=reader.ocr_conf,
            status="read" if text else "no_plate" if reader.plate_crop is None else "empty_ocr",
        )
    except Exception as exc:
        row.update(status="inference_error", error=f"{type(exc).__name__}: {exc}")
    return crop, reader.plate_crop, reader.ocr_input_image, row


def display_frame(frame, tracked, reader, selector, frame_number, seconds):
    annotated = frame.copy()
    for det in tracked.detections:
        x1, y1, x2, y2 = map(int, det.bbox)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 220, 0), 2)
        cv2.putText(annotated, f"id={det.track_id} class={det.class_id}",
                    (x1, max(20, y1)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 0), 2)

    cars = [det for det in tracked.detections if det.class_id == 2]
    for det in cars or [None]:
        if det is None:
            vehicle = plate = ocr_image = None
            row = {"status": "no_car"}
        else:
            vehicle, plate, ocr_image, row = inspect(reader, selector, frame, det)
        row.update(frame=frame_number, video_seconds=seconds)
        label = f"frame={frame_number} time={seconds:.2f}s track={row.get('track', '-')}"
        dashboard = np.vstack((
            np.hstack((image_panel(annotated, label), image_panel(vehicle, "Vehicle crop"))),
            np.hstack((image_panel(plate, "Plate crop"), image_panel(ocr_image, "OCR input"))),
            text_panel(row),
        ))
        yield row, dashboard


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", default=VIDEO_SOURCE)
    parser.add_argument("--start-seconds", type=float, default=START_SECONDS)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "reports/plate_debug")
    args = parser.parse_args()
    if not math.isfinite(args.start_seconds) or args.start_seconds < 0:
        parser.error("--start-seconds must be a finite nonnegative number")

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    model = Path(config["model_path"])
    if not model.is_absolute():
        model = PROJECT_ROOT / model
    if not model.exists():
        raise FileNotFoundError(f"YOLO model not found: {model}")

    source = args.video
    if "://" not in source:
        source = str(Path(source).expanduser().resolve())
        if not Path(source).is_file():
            raise FileNotFoundError(f"Video not found: {source}")

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open video: {source}")

    output = args.output / time.strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=True)
    tracker = CameraTracker("debug", str(model), config.get("detection_interval", 3))
    reader, selector = InspectableReader(), BestCropSelector()
    paused = False
    fps = cap.get(cv2.CAP_PROP_FPS)
    is_file = "://" not in args.video
    count = 0

    try:
        if args.start_seconds:
            if not is_file:
                raise ValueError("--start-seconds only supports video files")
            if not cap.set(cv2.CAP_PROP_POS_MSEC, args.start_seconds * 1000):
                raise RuntimeError("Could not seek to requested timestamp")
        print(f"Source: {source}\nFPS: {fps:.2f} | Start: {args.start_seconds:.2f}s")
        if not args.headless:
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        stop = False
        with (output / "results.jsonl").open("w", encoding="utf-8") as log:
            while not stop and (not args.max_frames or count < args.max_frames):
                ok, frame = cap.read()
                if not ok:
                    break
                count += 1
                # POS_FRAMES is the next frame index after read; use that for frame number.
                frame_number = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) if is_file else count
                seconds = (max(0, frame_number - 1) / fps) if is_file and fps > 0 else cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                tracked = tracker.process(count, time.monotonic(), frame)

                for row, dashboard in display_frame(frame, tracked, reader, selector, frame_number, seconds):
                    print(json.dumps(row, ensure_ascii=False), flush=True)
                    log.write(json.dumps(row, ensure_ascii=False) + "\n")
                    log.flush()
                    snapshot = output / f"frame_{frame_number}_track_{row.get('track', 'none')}.jpg"
                    if args.headless:
                        if not cv2.imwrite(str(snapshot), dashboard):
                            raise OSError(f"Cannot save image: {snapshot}")
                        continue
                    cv2.imshow(WINDOW, dashboard)
                    while True:
                        key = cv2.waitKey(50 if paused else 1) & 0xFF
                        if key in (27, ord("q")) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                            stop = True
                            break
                        if key == ord("s"):
                            cv2.imwrite(str(snapshot), dashboard)
                            print(f"Saved: {snapshot}")
                        elif key == ord(" "):
                            paused = not paused
                        elif key == ord("n"):
                            paused = True
                            break
                        if not paused:
                            break
    finally:
        cap.release()
        if not args.headless:
            cv2.destroyAllWindows()
        print(f"Processed frames: {count}\nDebug output: {output}")


if __name__ == "__main__":
    main()
