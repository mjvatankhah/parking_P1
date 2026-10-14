"""
اندازه‌گیری این‌که وقت هر فریم دقیقاً کجا خرج می‌شود.

اجرا (از ریشه‌ی پروژه):
    uv run python scripts/profile_pipeline.py --video src/computer_vision_v2/video/c5.mp4

اگر خواستی سایزهای دیگر را هم امتحان کنی:
    uv run python scripts/profile_pipeline.py --video ... --imgsz 640 480 416 320
برای مقایسه‌ی مدل export شده (imgsz را نده؛ اندازه موقع export ثابت شده است):
    uv run python scripts/profile_pipeline.py --video ... --model models/vehicle/yolov8n_openvino_model/
    uv run python scripts/profile_pipeline.py --video ... --model models/vehicle/yolov8n.onnx
اگر GPU انویدیا داری و می‌خواهی اجباری تست کنی:
    uv run python scripts/profile_pipeline.py --video ... --device 0

خروجی برای هر imgsz این ستون‌هاست (همه به میلی‌ثانیه، میانگین روی فریم‌ها):
    decode   : خواندن فریم از ویدیو (cap.read)
    pre      : آماده‌سازی تصویر برای شبکه (کوچک کردن، نرمال کردن)
    infer    : خود شبکه YOLO
    post     : NMS و ساخت خروجی
    track    : ByteTrack + بقیه‌ی سربارهای ultralytics (تقریبی: کل - pre - infer - post)
    fps      : 1000 / (decode + کل model.track)  ← همان چیزی که حلقه‌ی StreamManager تجربه می‌کند

25 fps یعنی مجموع همه‌ی ستون‌ها باید زیر 40 ms باشد.
"""
import argparse
import os
import statistics as st
import time
from pathlib import Path

import cv2

VEHICLE_CLASSES = [0, 2]  # همان مقدار tracker.py


def hardware_report():
    print(f"CPU cores          : {os.cpu_count()}")
    try:
        import re

        with open("/proc/cpuinfo", encoding="utf-8") as f:
            info = f.read()
        model = re.search(r"model name\s*:\s*(.+)", info)
        print(f"CPU model          : {model.group(1) if model else '?'}")
        print(f"AVX2 supported     : {bool(re.search(r'\bavx2\b', info))}   <-- بدون AVX2 مدل‌های export شده سود کمتری می‌دهند")
    except OSError:
        pass
    try:
        import torch

        print(f"torch              : {torch.__version__}")
        print(f"CUDA available     : {torch.cuda.is_available()}   <-- اگر GPU انویدیا داری و اینجا False است، مهم‌ترین مشکل همین است")
        print(f"torch threads      : {torch.get_num_threads()}")
    except Exception as exc:  # noqa: BLE001
        print(f"torch could not be imported: {exc}")
    print()


def bench(video, model_path, imgsz, device, warmup, max_frames):
    from ultralytics import YOLO

    model = YOLO(model_path)  # مدل تازه => tracker تازه، تا اجراها روی هم اثر نگذارند
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {video}")

    kwargs = dict(persist=True, classes=VEHICLE_CLASSES, verbose=False, tracker="bytetrack.yaml")
    if imgsz:  # فقط برای مدل .pt؛ مدل export شده اندازه‌ی ثابت خودش را دارد
        kwargs["imgsz"] = imgsz
    if device:
        kwargs["device"] = device

    rows = []
    seen = 0
    while seen < max_frames:
        t0 = time.perf_counter()
        ok, image = cap.read()
        t1 = time.perf_counter()
        if not ok:
            break
        results = model.track(image, **kwargs)
        t2 = time.perf_counter()
        seen += 1
        if seen <= warmup:  # چند فریم اول به خاطر گرم شدن مدل کندتر است؛ حساب نمی‌کنیم
            continue
        sp = results[0].speed
        wall = (t2 - t1) * 1000
        rows.append(
            dict(
                decode=(t1 - t0) * 1000,
                wall=wall,
                pre=sp["preprocess"],
                infer=sp["inference"],
                post=sp["postprocess"],
                track=max(0.0, wall - sp["preprocess"] - sp["inference"] - sp["postprocess"]),
            )
        )
    cap.release()
    return rows


def summarize(label, rows):
    if not rows:
        print(f"{label}: no frames measured")
        return
    mean = lambda k: st.mean(r[k] for r in rows)
    per_frame = [r["decode"] + r["wall"] for r in rows]
    p95 = sorted(per_frame)[int(len(per_frame) * 0.95) - 1]
    fps = 1000.0 / st.mean(per_frame)
    print(
        f"{label:>10} | decode {mean('decode'):5.1f} | pre {mean('pre'):5.1f} | "
        f"infer {mean('infer'):6.1f} | post {mean('post'):5.1f} | track {mean('track'):5.1f} | "
        f"total {st.mean(per_frame):6.1f} (p95 {p95:6.1f}) | {fps:5.1f} fps"
    )


def print_cost(lines=100):
    """هزینه‌ی print در ترمینال خودت (WSL/Windows Terminal می‌تواند کند باشد)."""
    t = time.perf_counter()
    for _ in range(lines):
        print("YOLO CONF:", [0.91, 0.84, 0.77])
    per_print = (time.perf_counter() - t) * 1000 / lines
    print(f"\nprint cost in your terminal: {per_print:.3f} ms per print "
          f"(حلقه‌ی فعلی ~6 تا print در هر فریم دارد => {per_print * 6:.2f} ms/frame)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    default_model = Path(__file__).resolve().parents[1] / "models/vehicle/yolov8n.pt"
    ap.add_argument("--model", default=str(default_model))
    ap.add_argument("--imgsz", type=int, nargs="+", default=[640, 480, 416, 320])
    ap.add_argument("--device", default=None, help="مثلاً 0 برای GPU یا cpu")
    ap.add_argument("--warmup", type=int, default=15)
    ap.add_argument("--max-frames", type=int, default=180)
    args = ap.parse_args()

    hardware_report()
    print(f"{'imgsz':>10} | ms per frame (mean over steady-state frames)")
    print("-" * 110)
    is_pt = args.model.lower().endswith(".pt")
    sizes = args.imgsz if is_pt else [None]  # مدل export شده: اندازه ثابت است، sweep بی‌معنی است
    for size in sizes:
        rows = bench(args.video, args.model, size, args.device, args.warmup, args.max_frames)
        summarize(str(size) if size else "as-export", rows)
    print_cost()


if __name__ == "__main__":
    main()
