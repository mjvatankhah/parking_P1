"""Interactive inspection using the application's tracker and plate reader.

Edit VIDEO_SOURCE and START_SECONDS below, then run:
python -m computer_vision_v2.debug_plate
Or pass --start-seconds 60 to start processing one minute into the video.
"""

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import time

import cv2
import numpy as np
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

from computer_vision_v2.best_crop_selector import BestCropSelector
from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.tracking.tracker import CameraTracker

# مسیر فایل یا لینک مستقیم ویدیو / RTSP را اینجا وارد کنید.
VIDEO_SOURCE = "src/computer_vision_v2/video/InShot_20261012_210725035.mp4"
# زمان شروع پردازش ویدیو برحسب ثانیه؛ صفر یعنی ابتدای ویدیو.
START_SECONDS = 50
CONFIG_PATH = Path(__file__).parent / "reno" / "data" / "cameras.json"
WINDOW = "Plate debug | Space: pause | N: next | S: save | Q/Esc: quit"
FONT_PATH = Path(__file__).parent / "reno" / "assets" / "fonts" / "Vazirmatn-Regular.ttf"


@lru_cache(maxsize=4)
def display_font(size):
    # Text is shaped/reordered explicitly below; disable Pillow's second bidi pass.
    return ImageFont.truetype(str(FONT_PATH), size, layout_engine=ImageFont.Layout.BASIC)


def result_panel(row, width=1280):
    """Show the current sample, preserving OCR character order left to right."""
    canvas = Image.new("RGB", (width, 190), (25, 25, 25))
    draw = ImageDraw.Draw(canvas)
    font = display_font(22)

    def persian(text, y, color=(230, 230, 230)):
        draw.text((width - 16, y), get_display(arabic_reshaper.reshape(text)),
                  font=font, fill=color, anchor="rt")

    statuses = {
        "read": "متن تولید شد؛ صحت شماره باید بررسی شود",
        "no_car": "خودرویی شناسایی نشده است",
        "no_plate": "محل پلاک پیدا نشد؛ OCR اجرا نشد",
        "empty_ocr": "محل پلاک پیدا شد؛ OCR متنی تولید نکرد",
        "empty_vehicle_crop": "کراپ خودرو خالی است",
        "inference_error": "خطای پردازش؛ جزئیات در ترمینال و گزارش",
    }
    persian(f"خروجی OCR: {statuses.get(row['status'], row['status'])}", 8)
    draw.text((16, 8), f"Frame: {row.get('frame', '-')}   Track: {row.get('track', '-')}",
              font=font, fill=(230, 230, 230))
    text = row.get("text")
    if text:
        # A plate is a sequence, not an RTL sentence: bidi would reorder its digits.
        glyphs = [arabic_reshaper.reshape(char) for char in text]
        text_font = display_font(44)
        total = sum(draw.textlength(char, font=text_font) for char in glyphs)
        if total > width - 32:
            text_font = display_font(max(12, int(44 * (width - 32) / total)))
            total = sum(draw.textlength(char, font=text_font) for char in glyphs)
        x = (width - total) / 2
        for char in glyphs:
            draw.text((x, 40), char, font=text_font, fill=(255, 220, 100))
            x += draw.textlength(char, font=text_font)
    else:
        draw.text((width // 2, 45), "—", font=display_font(44), fill=(180, 180, 180), anchor="mt")
    score = row.get("ocr_confidence")
    score_text = "—" if score is None else f"{score:.3f}"
    persian(f"امتیاز OCR: {score_text}  |  این امتیاز تضمین صحت متن نیست", 98)
    persian("تصویر پلاک: برش خروجی مدل تشخیص محل پلاک، از عکس خودرو", 130)
    persian("ورودی OCR: همان برش پس از تغییر اندازه و آماده‌سازی؛ تصویرِ بهبود‌یافته نیست", 158)
    return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)


class InspectableReader(PlateReader):
    """Observe intermediate results without duplicating inference or decoding."""

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
        image = (blob[0].transpose(1, 2, 0) * 255).astype(np.uint8)
        self.ocr_input_image = (
            cv2.cvtColor(image[:, :, 0], cv2.COLOR_GRAY2BGR)
            if image.shape[2] == 1 else image[:, :, ::-1].copy()
        )
        return blob

    def _ctc_decode(self, logits):
        result = super()._ctc_decode(logits)
        self.ocr_conf = result[1]
        return result


def panel(image, title, width=640, height=360):
    canvas = np.full((height, width, 3), 25, dtype=np.uint8)
    if image is not None and image.size:
        h, w = image.shape[:2]
        scale = min(width / w, (height - 38) / h)
        resized = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))))
        rh, rw = resized.shape[:2]
        x, y = (width - rw) // 2, 38 + (height - 38 - rh) // 2
        canvas[y:y + rh, x:x + rw] = resized
    cv2.putText(canvas, title, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, .55, (230, 230, 230), 1)
    return canvas


def inspect_vehicle(reader, selector, image, detection):
    h, w = image.shape[:2]
    x1, y1, x2, y2 = map(int, detection.bbox)
    crop = image[max(0, y1):min(h, y2), max(0, x1):min(w, x2)].copy()
    row = {"track": detection.track_id, "bbox": [x1, y1, x2, y2],
           "predicted": detection.is_predicted,
           "vehicle_confidence": float(detection.confidence),
           "crop_eligible": selector._score(image, detection.bbox, detection.confidence) is not None}
    if x2 <= max(0, x1) or y2 <= max(0, y1) or not crop.size:
        return None, None, None, dict(row, status="empty_vehicle_crop")
    try:
        text, confidence, path = reader.read(crop)
        row.update(text=text, confidence=confidence, plate_path=path,
                   detector_confidence=reader.det_conf, ocr_confidence=reader.ocr_conf,
                   status="read" if text else "no_plate" if reader.plate_crop is None else "empty_ocr")
    except Exception as exc:
        row.update(status="inference_error", error=f"{type(exc).__name__}: {exc}")
    return crop, reader.plate_crop, reader.ocr_input_image, row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", default=VIDEO_SOURCE)
    parser.add_argument("--start-seconds", type=float, default=START_SECONDS,
                        help="Start processing at this time in seconds (default: %(default)s)")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("reports/plate_debug"))
    args = parser.parse_args()
    if not args.video:
        parser.error("Set VIDEO_SOURCE in debug_plate.py or pass --video FILE_OR_URL")
    if not math.isfinite(args.start_seconds) or args.start_seconds < 0:
        parser.error("--start-seconds must be a finite, non-negative number")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    model_path = Path(__file__).resolve().parents[2] / config["model_path"]
    tracker = CameraTracker("debug", str(model_path), config.get("detection_interval", 3))
    reader, selector = InspectableReader(), BestCropSelector()
    output = args.output / time.strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(args.video)
    paused, index, stop = False, 0, False
    processed = 0
    try:
        if not capture.isOpened():
            raise RuntimeError("Could not open video source")
        if args.start_seconds:
            fps = capture.get(cv2.CAP_PROP_FPS)
            frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            if fps > 0 and frame_count > 0 and args.start_seconds >= frame_count / fps:
                raise ValueError("Start time must be before the end of the video")
            if not capture.set(cv2.CAP_PROP_POS_MSEC, args.start_seconds * 1000):
                raise RuntimeError("Video source does not support seeking to the requested start time")
            index = int(capture.get(cv2.CAP_PROP_POS_FRAMES))
            print(f"Starting at {args.start_seconds:g} seconds (frame {index + 1}).")
        if not args.headless:
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        with (output / "results.jsonl").open("w", encoding="utf-8") as log:
            while not stop and (not args.max_frames or processed < args.max_frames):
                ok, frame = capture.read()
                if not ok:
                    print("End of video or source disconnected.")
                    break
                index += 1
                processed += 1
                tracked = tracker.process(processed, time.monotonic(), frame)
                annotated = frame.copy()
                cars = [d for d in tracked.detections if d.class_id == 2]
                for det in tracked.detections:
                    x1, y1, x2, y2 = map(int, det.bbox)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 220, 0), 2)
                    cv2.putText(annotated, f"id={det.track_id} class={det.class_id}", (x1, max(20, y1)),
                                cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 220, 0), 2)
                for det in cars or [None]:
                    crop, plate, ocr_image = None, None, None
                    if det is None:
                        row = {"status": "no_car"}
                    else:
                        crop, plate, ocr_image, row = inspect_vehicle(reader, selector, frame, det)
                    row["frame"] = index
                    line = json.dumps(row, ensure_ascii=False)
                    print(line, flush=True)
                    log.write(line + "\n")
                    log.flush()
                    title = f"frame={index} track={row.get('track', '-')} {row['status']}"
                    dashboard = np.vstack((
                        np.hstack((panel(annotated, title), panel(crop, f"Vehicle | eligible={row.get('crop_eligible', '-')}"))),
                        np.hstack((panel(plate, f"Detected plate crop | score={row.get('detector_confidence')}"),
                                   panel(ocr_image, "OCR input | resized / normalized for recognition"))),
                        result_panel(row),
                    ))
                    snapshot = output / f"frame_{index}_track_{row.get('track', 'none')}.jpg"
                    if args.headless:
                        if not cv2.imwrite(str(snapshot), dashboard):
                            raise OSError("Could not save debug image")
                        continue
                    cv2.imshow(WINDOW, dashboard)
                    while True:
                        key = cv2.waitKey(50 if paused else 1) & 0xFF
                        if key in (27, ord("q")) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                            stop = True
                            break
                        if key == ord("s"):
                            if not cv2.imwrite(str(snapshot), dashboard):
                                raise OSError("Could not save debug image")
                            print(f"Saved: {snapshot}")
                        if key == ord(" "):
                            paused = not paused
                        if key == ord("n"):
                            paused = True
                            break
                        if not paused:
                            break
                    if stop:
                        break
    finally:
        capture.release()
        if not args.headless:
            cv2.destroyAllWindows()
        print(f"Debug output: {output}")


if __name__ == "__main__":
    main()
