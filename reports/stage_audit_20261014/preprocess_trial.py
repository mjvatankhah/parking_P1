"""Compare current OCR input with the model publisher's CRNN recipe.

Recipe reference: AliAkrami1375/Platrix, commit
9e91a2a1e037a2221327efa243f655289c0f9ec9, platrix/preprocessing.py (MIT).
This diagnostic does not change production preprocessing.
"""
import json
from pathlib import Path
import time
import cv2
import numpy as np

from audit import OUT, EXPECTED, ocr_reader, selected_detection, save, benchmark
from computer_vision_v2.inference.plate_geometry import prepare_plate


def publisher_input(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if h < 40:
        gray = cv2.resize(gray, (max(int(w * 40 / h), 1), 40), interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 5, 45, 45)
    gray = cv2.createCLAHE(clipLimit=2., tileGridSize=(8, 8)).apply(gray)
    blurred = cv2.GaussianBlur(gray, (0, 0), 1.)
    gray = cv2.addWeighted(gray, 1.4, blurred, -.4, 0)
    gray = cv2.resize(gray, (128, 32), interpolation=cv2.INTER_AREA)
    return gray[None, None].astype(np.float32) / 255.


def main():
    reader = ocr_reader()
    baseline = json.loads(Path('reports/exit_plate_trial/baseline.json').read_text())
    rows, batch_inputs = [], []
    for entry in baseline:
        n = entry['frame']
        vehicle = cv2.imread(f'reports/exit_plate_trial/vehicle_{n}.png')
        detection = selected_detection(entry, vehicle)
        if detection is None:
            continue
        raw, _, context = detection
        prepared = prepare_plate(context)
        row = dict(frame=n)
        for name, image in [('raw', raw), ('prepared', prepared.image if prepared else None)]:
            if image is None:
                continue
            blob = publisher_input(image)
            text, conf = reader._ctc_decode(reader.ocr.run(None, {reader.ocr_input: blob})[0])
            row[name] = dict(text=text, confidence=conf, correct=text == EXPECTED)
            if name == 'prepared' and n in (306, 339, 345, 348, 357):
                batch_inputs.append(reader._prep_ocr(image))
        rows.append(row)
        save('publisher_preprocess.json', rows)
    summary = {}
    baseline_rows = {r['frame']: r for r in json.loads((OUT/'stages.json').read_text())}
    for stage in ('raw', 'prepared'):
        valid = [r for r in rows if stage in r]
        summary[stage] = dict(n=len(valid),correct=sum(r[stage]['correct'] for r in valid),
                             recovered=[r['frame'] for r in valid if r[stage]['correct']
                                        and not baseline_rows[r['frame']][stage]['correct']],
                             lost=[r['frame'] for r in valid if not r[stage]['correct']
                                   and baseline_rows[r['frame']][stage]['correct']])
    save('publisher_summary.json', summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    assert len(batch_inputs)==5
    batch = np.concatenate(batch_inputs)
    def sequential():
        return [reader._ctc_decode(reader.ocr.run(None,{reader.ocr_input:blob})[0])[0]
                for blob in batch_inputs]
    def together():
        return [reader._ctc_decode(logits)[0]
                for logits in reader.ocr.run(None,{reader.ocr_input:batch})[0]]
    texts = dict(sequential=sequential(), batch=together())
    assert texts['sequential']==texts['batch'],texts
    # Interleave to reduce the effect of time-varying CPU load.
    durations={'sequential':[], 'batch':[]}
    for _ in range(3):
        for name,fn in [('sequential',sequential),('batch',together)]:
            start=time.perf_counter();fn()
            durations[name].append((time.perf_counter()-start)*1000)
    save('batch_timing.json',dict(texts=texts,ms=durations,
                                 median_ms={k:float(np.median(v)) for k,v in durations.items()},
                                 publisher_prep=benchmark(lambda:publisher_input(raw))))


if __name__=='__main__':
    main()
