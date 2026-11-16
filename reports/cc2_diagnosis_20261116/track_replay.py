import sys,json,contextlib
from pathlib import Path
import cv2,torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from computer_vision_v2.tracking.tracker import CameraTracker
from computer_vision_v2.Line_Manager.line_detector import LineDetectorManager
out=Path(__file__).resolve().parent
cfg=json.loads((ROOT/'src/reno/data/cameras.json').read_text());cam=next(c for c in cfg['cameras'] if c['id']=='cc2');cfg['cameras']=[cam]
cv2.setNumThreads(2);torch.set_num_threads(2)
cap=cv2.VideoCapture(cam['source']);fps=cap.get(5);rows=[];events=[]
with (out/'tracking.log').open('w') as log,contextlib.redirect_stdout(log):
 tracker=CameraTracker('cc2',cfg['model_path'],cfg['detection_interval'],roi=cam.get('roi'));lines=LineDetectorManager(cfg)
 i=0
 while True:
  ok,im=cap.read()
  if not ok:break
  f=tracker.process(i,i/fps,im);e=lines.update(f);events.extend(e)
  rows.append({'frame':i,'boxes':[{'id':d.track_id,'box':[float(v) for v in d.bbox],'pred':d.is_predicted} for d in f.detections]});i+=1
(out/'tracks.json').write_text(json.dumps(rows));(out/'crossings.json').write_text(json.dumps(events,default=lambda x:float(x),ensure_ascii=False,indent=2));print('frames',i,'crossings',events)
