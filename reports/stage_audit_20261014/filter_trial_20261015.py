"""Fixed offline ablation; no production/config/DB changes or parameter search.
Run with PYTHONPATH=src:reports/stage_audit_20261014 from repository root.
"""
import json
import time
from collections import Counter
from pathlib import Path
import cv2
import numpy as np
from audit import ocr_reader, selected_detection, EXPECTED
from computer_vision_v2.inference.plate_geometry import prepare_plate

OUT = Path(__file__).resolve().parent
cv2.setNumThreads(2)

def variants(gray):
    smooth = cv2.GaussianBlur(gray, (0, 0), 1.)
    illumination = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 7.)
    flattened = np.clip(gray.astype(np.float32)/(illumination+1.)*180., 0, 255).astype(np.uint8)
    return {
        'baseline': gray,
        'clahe': cv2.createCLAHE(2., (4, 4)).apply(gray),
        'mild_unsharp': cv2.addWeighted(gray, 1.3, smooth, -.3, 0),
        'illumination_division': flattened,
        'bilateral_clahe': cv2.createCLAHE(2., (4, 4)).apply(cv2.bilateralFilter(gray, 5, 25, 25)),
        'otsu': cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1],
    }

def main():
    images=[]
    for entry in json.loads(Path('reports/exit_plate_trial/baseline.json').read_text()):
        n=entry['frame']
        d=selected_detection(entry, cv2.imread(f'reports/exit_plate_trial/vehicle_{n}.png'))
        if d is None: continue
        prepared=prepare_plate(d[2])
        if prepared is not None:
            images.append((n, cv2.cvtColor(prepared.image, cv2.COLOR_BGR2GRAY)))
    reader=ocr_reader()
    rows=[]
    for index,(n,gray) in enumerate(images):
        outputs={}
        for name,image in variants(gray).items():
            blob=cv2.resize(image,(128,32))[None,None].astype(np.float32)/255.
            text,conf=reader._ctc_decode(reader.ocr.run(None,{reader.ocr_input:blob})[0])
            letter=text[2:-5]
            valid=(len(text)>=8 and text[:2].isdigit() and text[-5:].isdigit()
                   and letter in reader.labels and not letter.isdigit())
            outputs[name]=dict(text=text,confidence=conf,correct=text==EXPECTED,valid=valid)
        rows.append(dict(frame=n,outputs=outputs))
        (OUT/'filter_trial_20261015.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
        if index%5==0: print('completed',index+1,'/',len(images),flush=True)
    selected=[r['frame_idx'] for r in json.loads((OUT/'selection.json').read_text())['actual']['readings']]
    summaries={}
    for name in rows[0]['outputs']:
        chosen=[next(r for r in rows if r['frame']==n)['outputs'][name] for n in selected]
        votes=Counter(r['text'] for r in chosen if r['valid'] and r['confidence']>=.8)
        winner,count=votes.most_common(1)[0] if votes else (None,0)
        summaries[name]=dict(n=len(rows),correct=sum(r['outputs'][name]['correct'] for r in rows),
          recovered=[r['frame'] for r in rows if r['outputs'][name]['correct'] and not r['outputs']['baseline']['correct']],
          lost=[r['frame'] for r in rows if not r['outputs'][name]['correct'] and r['outputs']['baseline']['correct']],
          fixed_top5=dict(frames=selected,votes=dict(votes),status='read' if count>=2 else 'uncertain',text=winner if count>=2 else None))
    # Small images: measure the whole set of six preparations, excluding OCR.
    timings=[]
    for _ in range(30):
        start=time.perf_counter();variants(images[0][1]);timings.append((time.perf_counter()-start)*1000)
    result=dict(expected=EXPECTED,scope='38 correlated frames of one labelled vehicle; development set, not independent validation',
                summaries=summaries,all_six_filters_median_ms=float(np.median(timings)))
    (OUT/'filter_summary_20261015.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__': main()
