"""Offline comparison on archived JPEG vehicle crops; never writes event data."""
import sys, json
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
import cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates, TrackEvidence, VehicleSample

class LegacyMetadata:
    def __init__(self, session): self.session=session
    def get_modelmeta(self): return SimpleNamespace(custom_metadata_map={'end2end':'False'})
    def __getattr__(self,name): return getattr(self.session,name)

reader=PlateReader()
primary=reader.detector
results=[]
for path in sorted(Path('reports/crop_diagnostics').glob('*/manifest.json')):
    d=json.loads(path.read_text())
    if d.get('database_event_id') not in [409,410,411,415]: continue
    for mode in ['legacy','fixed']:
        reader.detector=LegacyMetadata(primary) if mode=='legacy' else primary
        pool=PlateCandidates(reader)
        state=TrackEvidence(0,(),event=d['event'])
        count=0
        for s in d['samples']:
            img=cv2.imread(str(path.parent/s['vehicle']))
            c=pool._detect_sample(VehicleSample(img,s['ts'],s['frame_idx']))
            count+=c is not None
            pool._store_candidate(state,c)
        pool.tracks['replay']=state
        passage=pool._retire('replay',0)
        r=reader.recognize_candidates(passage.candidates)
        r.pop('image',None)
        row={'event':d['database_event_id'],'mode':mode,'samples':len(d['samples']),'accepted':count,**r}
        results.append(row)
        print(row['event'],mode,'accepted',count,r['recognition_status'],r['plate_text'],dict(Counter(x['text'] for x in r['readings'] if x['valid'] and x['confidence']>=.8)),flush=True)
Path('reports/recent_entries_20261112/model_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
