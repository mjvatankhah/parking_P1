"""Compare raw and geometrically prepared OCR for one vehicle crop.

Set IMAGE_PATH below, then run from the project root:
    uv run python test_single_plate.py
"""
import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
# مسیر عکس کراپ ماشین را اینجا وارد کنید؛ مسیر نسبی از ریشه پروژه محاسبه می‌شود.
IMAGE_PATH = "src/Tpicture/InShot_20261022_055527905.jpg"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', nargs='?', type=Path,
                        help='Optional image path overriding IMAGE_PATH')
    parser.add_argument('--output-dir', type=Path,
                        help='Output directory (default: reports/single_plate/<image stem>)')
    parser.add_argument('--confidence', type=float, default=0.35,
                        help='Plate detection threshold (default: 0.35)')
    args = parser.parse_args()
    if not 0 <= args.confidence <= 1:
        parser.error('--confidence must be between 0 and 1')
    if args.image is None and not IMAGE_PATH.strip():
        parser.error('مسیر عکس را در متغیر IMAGE_PATH بالای فایل وارد کنید.')
    image_path = (args.image or Path(IMAGE_PATH)).expanduser()
    if not image_path.is_absolute():
        image_path = ROOT / image_path
    image_path = image_path.resolve()
    if not image_path.is_file():
        parser.error(f'Image does not exist: {image_path}')

    # Also work when the package has not been installed in editable mode.
    sys.path.insert(0, str(ROOT / 'src'))
    import cv2
    import torch
    from computer_vision_v2.inference.plate_geometry import prepare_plate
    from computer_vision_v2.inference.plate_ocr import PlateReader

    vehicle = cv2.imread(str(image_path))
    if vehicle is None:
        parser.error(f'Cannot decode image: {image_path}')
    torch.set_num_threads(2)
    reader = PlateReader(conf_thr=args.confidence)
    detection = reader.detect_plate(vehicle)
    if detection is None:
        print('پلاکی در تصویر پیدا نشد.', file=sys.stderr)
        return 1

    raw, detection_confidence, context = detection
    output_dir = (args.output_dir.expanduser() if args.output_dir else
                  ROOT / 'reports' / 'single_plate' / image_path.stem).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    def save_image(name, image):
        path = output_dir / name
        if not cv2.imwrite(str(path), image):
            raise OSError(f'Could not save image: {path}')
        return str(path)

    raw_path = save_image('plate_raw.png', raw)
    context_path = save_image('plate_context.png', context)
    # Context belongs to this same detection; its margin protects rotation edges.
    prepared = prepare_plate(context)
    raw_text, raw_confidence = reader.ocr.recognize([raw])[0]
    report = {
        'input': str(image_path),
        'detection_confidence': detection_confidence,
        'context_image': context_path,
        'raw': {'text': raw_text, 'confidence': raw_confidence, 'image': raw_path},
        'geometry': {'status': 'unavailable', 'text': None,
                     'confidence': None, 'image': None},
    }
    print(f'اطمینان تشخیص پلاک: {detection_confidence:.4f}')
    print(f'پلاک خام: {raw_text!r} | اطمینان OCR: {raw_confidence:.4f}')
    if prepared is not None:
        geometry_path = save_image('plate_geometry.png', prepared.image)
        geometry_text, geometry_confidence = reader.ocr.recognize([prepared.image])[0]
        report['geometry'] = {
            'status': 'ok', 'text': geometry_text,
            'confidence': geometry_confidence, 'image': geometry_path,
        }
        print(f'پلاک اصلاح هندسی‌شده: {geometry_text!r} | '
              f'اطمینان OCR: {geometry_confidence:.4f}')
    else:
        print('پلاک اصلاح هندسی‌شده: اصلاح هندسی قابل اعتماد پیدا نشد؛ OCR اجرا نشد.')

    report_path = output_dir / 'result.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'گزارش و مسیر تصاویر: {report_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
