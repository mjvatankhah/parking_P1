"""Offline audit of the saved DB snapshot and exact archived inputs; no DB writes.

Run from the project root with .venv/bin/python reports/camera001-full-review-20261118/analyze.py
"""
import os
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('MKL_NUM_THREADS', '2')
os.environ.setdefault('MPLCONFIGDIR', '/tmp/plakino-audit-matplotlib')
import csv
import json
import argparse
import math
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import torch

from computer_vision_v2.inference.hezar_ocr import HezarOCR
from computer_vision_v2.inference.plate_geometry import _prepare_deskew, _rectify_plate, has_text_support, prepare_plate
from computer_vision_v2.inference.plate_ocr import DEFAULT_LABELS, DEFAULT_OCR_DIRECTORY, _pad_ocr_crop, _confirmed

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
events = json.loads((ROOT / 'events.json').read_text())
parser = argparse.ArgumentParser()
parser.add_argument('--events', nargs='*', type=int)
args = parser.parse_args()
event_ids = {e['id'] for e in events}
labels = json.loads(DEFAULT_LABELS.read_text())
samples = []
manifests = []
for path in (PROJECT / 'report_traffic/archives').glob('*/manifest.json'):
    manifest = json.loads(path.read_text())
    if manifest['database_event_id'] not in event_ids:
        continue
    manifests.append((path.parent, manifest))
    for sample in manifest['samples']:
        if not sample.get('raw'):
            continue
        image = cv2.imread(str(path.parent / sample['raw']))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        context = cv2.imread(str(path.parent / sample['context']))
        proposal = _prepare_deskew(context)
        samples.append(dict(event=manifest['database_event_id'], frame=sample['frame_idx'],
            width=image.shape[1], height=image.shape[0], mean=float(gray.mean()),
            contrast=float(gray.std()), sharpness=float(cv2.Laplacian(gray, cv2.CV_32F).var()),
            quality=sample['quality'], raw=str(path.parent / sample['raw']),
            context=str(path.parent / sample['context']),
            geometry_accepted=prepare_plate(context) is not None,
            deskew_proposal=proposal is not None,
            deskew_text_support=has_text_support(proposal.image) if proposal else None,
            perspective_proposal=_rectify_plate(context) is not None))
samples.sort(key=lambda s: (s['event'], s['frame']))
(ROOT/'image_metrics.json').write_text(json.dumps(samples, ensure_ascii=False, indent=2))
with (ROOT/'image_metrics.csv').open('w') as out:
    writer = csv.DictWriter(out, fieldnames=list(samples[0]))
    writer.writeheader()
    writer.writerows(samples)

# A scientific contact sheet for visual comparison; images retain their aspect ratio.
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig, axes = plt.subplots(math.ceil(len(samples)/3), 3, figsize=(12, math.ceil(len(samples)/3)*1.5))
for ax, s in zip(axes.flat, samples):
    ax.imshow(cv2.cvtColor(cv2.imread(s['raw']), cv2.COLOR_BGR2RGB), interpolation='nearest')
    ax.set_title(f"Event {s['event']} / frame {s['frame']} / {s['width']}x{s['height']}", fontsize=8)
    ax.axis('off')
fig.suptitle(f'All {len(samples)} archived raw crops from uncertain events (display enlarged)', fontsize=12)
fig.tight_layout()
fig.savefig(ROOT/'raw-crops.png', dpi=140)
plt.close(fig)

print('Image measurements complete; loading local OCR', flush=True)
torch.set_num_threads(2)
ocr = HezarOCR(DEFAULT_OCR_DIRECTORY)
trials_path = ROOT/'offline_trials.json'
trials = json.loads(trials_path.read_text()) if trials_path.exists() else []
def valid(text):
    return len(text) >= 8 and text[:2].isdigit() and text[-5:].isdigit() and text[2:-5] in labels and not text[2:-5].isdigit()

for event in sorted({s['event'] for s in samples}):
    if args.events and event not in args.events:
        continue
    records = [s for s in samples if s['event'] == event]
    for variant in ['raw', 'padded', 'wide_padding', 'context', 'padded_gamma']:
        if any(t['event'] == event and t['source'] == variant for t in trials):
            continue
        images = []
        for s in records:
            raw = cv2.imread(s['raw'])
            h, w = raw.shape[:2]
            if variant == 'raw':
                im = raw
            elif variant == 'context':
                im = cv2.imread(s['context'])
            elif variant == 'wide_padding':
                im = cv2.copyMakeBorder(raw, max(2,h//10), max(2,h//10), max(3,w//5), max(3,w//5), cv2.BORDER_REPLICATE)
            elif variant == 'padded_gamma':
                lut = np.rint((np.arange(256)/255.)**(1/1.6)*255).astype(np.uint8)
                im = cv2.LUT(_pad_ocr_crop(raw), lut)
            else:
                im = _pad_ocr_crop(raw)
            images.append(im)
        answers = ocr.recognize(images)
        readings = [dict(event=event, frame=s['frame'], source=variant, text=t, confidence=c, valid=valid(t))
                    for s,(t,c) in zip(records, answers)]
        trials.extend(readings)
        trials_path.write_text(json.dumps(trials,ensure_ascii=False,indent=2))
        votes = Counter(r['text'] for r in readings if r['valid'] and r['confidence'] >= .8)
        print(json.dumps(dict(event=event, variant=variant, confident_valid=sum(votes.values()),
                              votes=dict(votes), confirmed=_confirmed(readings)),ensure_ascii=False),flush=True)
    (ROOT/'offline_trials.json').write_text(json.dumps(trials,ensure_ascii=False,indent=2))

# Match the original recorded input types only. Extra padding on previously
# successful raw frames is experimental and must never count as another vote.
mismatches=[]
for directory, m in manifests:
    for r in m['ocr_inputs']:
        matching=next((t for t in trials if t['event']==m['database_event_id'] and t['frame']==r['frame_idx'] and t['source']==r['source']),None)
        if matching is None:
            continue
        if matching['text']!=r['text']:
            mismatches.append(dict(event=m['database_event_id'],frame=r['frame_idx'],source=r['source']))
print('Recorded text replay mismatches:',mismatches,flush=True)
checked=sum(any(t['event']==m['database_event_id'] and t['frame']==r['frame_idx'] and t['source']==r['source'] for t in trials) for _,m in manifests for r in m['ocr_inputs'])
(ROOT/'replay_check.json').write_text(json.dumps(dict(checked_inputs=checked,recorded_inputs=sum(len(m['ocr_inputs']) for _,m in manifests),text_mismatches=mismatches),indent=2))
