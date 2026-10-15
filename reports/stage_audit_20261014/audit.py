"""Read-only stage ablation on saved images; no production/config/DB writes.

PYTHONPATH=src .venv/bin/python reports/stage_audit_20261014/audit.py
Add --detector for a small real detector benchmark, --large for the trial model.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import time

import cv2
import numpy as np
import onnxruntime as ort

from computer_vision_v2.inference.plate_ocr import (
    PlateReader, DEFAULT_OCR, DEFAULT_LABELS, DEFAULT_DETECTOR, _session)
from computer_vision_v2.inference.plate_geometry import prepare_plate
from computer_vision_v2.ocr_worker.plate_candidates import Candidate, PlateCandidates
from computer_vision_v2.tracking.frame_info import Detection, TrackedFrame

OUT = Path(__file__).resolve().parent
EXPECTED = '58م87245'  # Visually labelled in the previous full-resolution report.


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))


def ocr_reader():
    r = PlateReader.__new__(PlateReader)
    r.ocr = _session(DEFAULT_OCR)
    info = r.ocr.get_inputs()[0]
    r.ocr_input = info.name
    r.ocr_c, r.ocr_h, r.ocr_w = [v if isinstance(v, int) else d
                              for v, d in zip(info.shape[1:], [1, 32, 128])]
    r.labels = r._load_labels(DEFAULT_LABELS)
    return r


def decode(reader, image):
    start = time.perf_counter()
    blob = reader._prep_ocr(image)
    output = reader.ocr.run(None, {reader.ocr_input: blob})[0]
    text, confidence = reader._ctc_decode(output)
    return dict(text=text, confidence=confidence, correct=text == EXPECTED,
                size=[image.shape[1], image.shape[0]],
                ms=(time.perf_counter()-start)*1000)


def clahe(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2., tileGridSize=(4, 4)).apply(gray)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def benchmark(fn, count=20):
    fn()  # Warmup outside measured samples.
    timings = []
    for _ in range(count):
        start = time.perf_counter()
        fn()
        timings.append((time.perf_counter()-start)*1000)
    return dict(n=count, median_ms=float(np.median(timings)),
                p95_ms=float(np.percentile(timings, 95)))


def selected_detection(row, vehicle):
    choices = sorted(row['detections'], key=lambda d: d['score'], reverse=True)
    if not choices:
        return None
    plausible = [d for d in choices if 1.15 <= (d['bbox'][2]-d['bbox'][0]) /
                 max(d['bbox'][3]-d['bbox'][1], 1) <= 8]
    d = (plausible or choices)[0]
    x1, y1, x2, y2 = d['bbox']
    h, w = vehicle.shape[:2]
    if x1 <= 0 or y1 <= 0 or x2 >= w or y2 >= h:
        return None
    pad = max(12, round((x2-x1)*.15))
    return (vehicle[y1:y2, x1:x2].copy(), d['score'],
            vehicle[max(0,y1-pad):min(h,y2+pad), max(0,x1-pad):min(w,x2+pad)].copy())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--detector', action='store_true')
    parser.add_argument('--large', action='store_true')
    args = parser.parse_args()
    reader = ocr_reader()
    model_paths = [DEFAULT_DETECTOR, DEFAULT_OCR, DEFAULT_LABELS]
    save('environment.json', dict(cpu_count=os.cpu_count(), opencv_threads=cv2.getNumThreads(),
                                 ort_version=ort.__version__, opencv_version=cv2.__version__,
                                 ocr_shape=reader.ocr.get_inputs()[0].shape,
                                 ocr_output_shape=reader.ocr.get_outputs()[0].shape,
                                 ocr_labels=len(reader.labels),
                                 hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in model_paths}))
    if args.detector:
        path = DEFAULT_DETECTOR.with_name('plate_yolo_yolov8m.onnx') if args.large else DEFAULT_DETECTOR
        detector = PlateReader(detector_path=path)
        rows = []
        for frame in (159, 300, 348):
            vehicle = cv2.imread(f'reports/exit_plate_trial/vehicle_{frame}.png')
            start = time.perf_counter()
            detection = detector.detect_plate(vehicle)
            row = dict(frame=frame, first_ms=(time.perf_counter()-start)*1000,
                       timing=benchmark(lambda: detector.detect_plate(vehicle), count=3))
            if detection is not None:
                crop, confidence, context = detection
                prepared = prepare_plate(context)
                row.update(score=confidence, raw=decode(reader,crop),
                           prepared=decode(reader,prepared.image) if prepared else None)
                cv2.imwrite(str(OUT/f'det_{"large" if args.large else "current"}_{frame}.png'),crop)
            rows.append(row)
            save('detector_large.json' if args.large else 'detector_current.json', rows)
            print(json.dumps(row,ensure_ascii=False),flush=True)
        return

    # Same pixels and OCR: ordinary crop vs manually identified four corners.
    frame = cv2.imread('reports/plate_debug_1080/frame_510.png')
    corners = np.float32([[325,573],[429,552],[441,580],[330,601]])
    matrix = cv2.getPerspectiveTransform(corners,np.float32([[0,0],[119,0],[119,31],[0,31]]))
    rectified = cv2.warpPerspective(frame,matrix,(120,32))
    manual = {}
    for name, im in dict(axis=frame[550:605,320:445], corners=rectified,
                        corners_clahe=clahe(rectified)).items():
        manual[name] = decode(reader,im)
        cv2.imwrite(str(OUT/f'manual_{name}.png'),im)
    assert not manual['axis']['correct'] and manual['corners']['correct'], manual
    degradation = []
    for width in (120, 100, 80, 60, 40, 30):
        small = cv2.resize(rectified,(width,max(1,round(32*width/120))),interpolation=cv2.INTER_AREA)
        degradation.append(dict(width=width, **decode(reader,small)))
    save('manual.json', dict(variants=manual, downscale=degradation))
    print('MANUAL',json.dumps(manual,ensure_ascii=False),flush=True)

    # Compare raw / actual automatic geometry / CLAHE on identical cached boxes.
    baseline = json.loads(Path('reports/exit_plate_trial/baseline.json').read_text())
    pool = PlateCandidates(reader)
    rows, sample_images = [], {}
    for entry in baseline:
        n = entry['frame']
        vehicle = cv2.imread(f'reports/exit_plate_trial/vehicle_{n}.png')
        detection = selected_detection(entry,vehicle)
        reader.detect_plate = lambda _vehicle, d=detection: d
        h,w = vehicle.shape[:2]
        pool.observe(TrackedFrame('cached',n,n/30.01544071471942,vehicle,
                                 [Detection(1,(0,0,w,h),2,1.)]))
        if detection is None:
            rows.append(dict(frame=n, detected=False))
            continue
        crop,confidence,context = detection
        started=time.perf_counter(); prepared=prepare_plate(context)
        row=dict(frame=n,detected=True,det_conf=confidence,raw=decode(reader,crop),
                 geometry_ms=(time.perf_counter()-started)*1000,
                 prepared=None, prepared_clahe=None)
        # Separate the geometry-only timing from OCR time.
        started=time.perf_counter(); prepare_plate(context)
        row['geometry_ms']=(time.perf_counter()-started)*1000
        if prepared:
            row['prepared']=decode(reader,prepared.image)
            row['prepared_clahe']=decode(reader,clahe(prepared.image))
            sample_images[n]=(crop,prepared.image)
        rows.append(row)
        save('stages.json',rows)
        if n%30==0: print('cached frame',n,flush=True)
    state=pool.tracks[('cached',1)]
    candidates=state.candidates+([state.fallback] if state.fallback else [])
    actual=reader.recognize_candidates(candidates); actual.pop('image')
    prepared_candidates=[c for c in candidates if c.prepared is not None]
    def sharp(c):
        gray=cv2.cvtColor(c.prepared.image,cv2.COLOR_BGR2GRAY)
        edges=cv2.Laplacian(gray,cv2.CV_32F)
        return float(edges[2:-2,2:-2].var())
    ranked={}
    for name,key in dict(geometry=lambda c:c.confidence*c.prepared.quality, sharpness=sharp).items():
        ranked[name]=[dict(frame=c.frame_idx,score=key(c),**decode(reader,c.prepared.image))
                      for c in sorted(prepared_candidates,key=key,reverse=True)]
    save('selection.json',dict(actual=actual, rankings=ranked))
    summary=dict(frames=len(rows),detected=sum(r['detected'] for r in rows))
    for stage in ('raw','prepared','prepared_clahe'):
        valid=[r[stage] for r in rows if r.get(stage)]
        summary[stage]=dict(count=len(valid),correct=sum(r['correct'] for r in valid))
    summary['raw_correct_lost_by_geometry']=[r['frame'] for r in rows if r.get('raw',{}).get('correct')
                                            and not (r.get('prepared') or {}).get('correct')]
    summary['geometry_correct_lost_by_clahe']=[r['frame'] for r in rows if (r.get('prepared') or {}).get('correct')
                                              and not (r.get('prepared_clahe') or {}).get('correct')]
    summary['clahe_recovers']=[r['frame'] for r in rows if not (r.get('prepared') or {}).get('correct')
                              and (r.get('prepared_clahe') or {}).get('correct')]
    save('summary.json',summary)
    # Warm timings on one known plate, not end-to-end throughput.
    row=next(r for r in baseline if r['frame']==348)
    v=cv2.imread('reports/exit_plate_trial/vehicle_348.png')
    raw,_,context=selected_detection(row,v);prepared=prepare_plate(context).image
    save('timing.json',dict(geometry=benchmark(lambda:prepare_plate(context)),
                           ocr=benchmark(lambda:decode(reader,prepared)),
                           clahe=benchmark(lambda:clahe(prepared))))
    # A contact sheet for visual review, with original and prepared sizes labelled.
    from PIL import Image,ImageDraw
    chosen=[n for n in (246,297,306,318,330,339,348,357,372,396) if n in sample_images]
    sheet=Image.new('RGB',(800,len(chosen)*130),(240,240,240));draw=ImageDraw.Draw(sheet)
    for i,n in enumerate(chosen):
        for j,im in enumerate(sample_images[n]):
            pil=Image.fromarray(cv2.cvtColor(im,cv2.COLOR_BGR2RGB));pil.thumbnail((380,95))
            # Enlarge for inspection only; OCR above used the original arrays.
            factor=min(380/im.shape[1],95/im.shape[0])
            pil=Image.fromarray(cv2.cvtColor(im,cv2.COLOR_BGR2RGB)).resize(
                (round(im.shape[1]*factor),round(im.shape[0]*factor)))
            sheet.paste(pil,(j*400,i*130+28))
            draw.text((j*400+4,i*130+4),f'{n} {"raw" if j==0 else "prepared"} {im.shape[1]}x{im.shape[0]}',fill=(0,0,0))
    sheet.save(OUT/'comparison.png')
    print('SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
