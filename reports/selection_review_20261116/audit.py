"""Read every available lossless crop; keep inference results for offline selection replay."""
import json,sys,time
from pathlib import Path
from collections import Counter
import cv2,torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from computer_vision_v2.inference.plate_ocr import PlateReader,DEFAULT_LABELS,MODEL_DIR
from computer_vision_v2.inference.hezar_ocr import HezarOCR
OUT=Path(__file__).resolve().parent
labels=json.loads(DEFAULT_LABELS.read_text())
def valid(t):return len(t)>=8 and t[:2].isdigit() and t[-5:].isdigit() and t[2:-5] in labels and not t[2:-5].isdigit()
def decision(rows):
 votes=Counter(r['text'] for r in rows if valid(r['text']) and r['confidence']>=.8)
 ranked=votes.most_common();n=ranked[0][1] if ranked else 0
 return dict(status='read' if n>=2 and (len(ranked)==1 or n>ranked[1][1]) else 'uncertain',votes=dict(votes))
def main():
 torch.set_num_threads(2);ocr=HezarOCR(MODEL_DIR);results=[]
 paths=[]
 for p in (ROOT/'reports/crop_diagnostics').glob('*/manifest.json'):
  d=json.loads(p.read_text())
  if d.get('database_event_id') in range(435,443):paths.append((d['database_event_id'],p,d))
 for eid,p,d in sorted(paths):
  rows=[]; selected={(r['frame_idx'],r['source']) for r in d['ocr_inputs']}
  for s in d['samples']:
   for source in ('raw','geometry'):
    if s.get(source):rows.append(dict(frame=s['frame_idx'],ts=s['ts'],source=source,image=str(p.parent/s[source]),selected=(s['frame_idx'],source) in selected,quality=s['quality']))
  # Include exact OCR inputs after the archive's 80-sample cap, and geometry
  # computed only at recognition time. Their images are still lossless.
  keys={(r['frame'],r['source']) for r in rows}
  for r in d['ocr_inputs']:
   if (r['frame_idx'],r['source']) not in keys and r.get('image'):
    rows.append(dict(frame=r['frame_idx'],ts=None,source=r['source'],image=str(p.parent/r['image']),selected=True,quality=None))
  start=time.monotonic()
  for i in range(0,len(rows),16):
   batch=rows[i:i+16];answers=ocr.recognize([cv2.imread(r['image']) for r in batch])
   for r,(t,c) in zip(batch,answers):r.update(text=t,confidence=c,valid=valid(t))
  result=dict(event=eid,manifest=str(p),historical=d['result']['recognition_status'],archived=decision(d['ocr_inputs']),all=decision(rows),selected=decision([r for r in rows if r['selected']]),rows=rows,seconds=time.monotonic()-start)
  results.append(result); print(eid,'historical',result['historical'],'selected',result['selected'],'all',result['all'],'images',len(rows),flush=True)
  (OUT/'all_ocr.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 if '--require-read' in sys.argv:assert all(r['selected']['status']=='read' for r in results),'Selected crops fail confirmation'
if __name__=='__main__':main()
