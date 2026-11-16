"""Capture detector measurements before ByteTrack and its matched output."""
import sys,json,contextlib
from pathlib import Path
import cv2,torch,numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from computer_vision_v2.tracking.tracker import CameraTracker
from ultralytics.trackers.byte_tracker import BYTETracker
out=Path(__file__).resolve().parent
if '--fixed' in sys.argv:
 out=out/'fixed_probe';out.mkdir(exist_ok=True)
cfg=json.loads((ROOT/'src/reno/data/cameras.json').read_text());cam=next(c for c in cfg['cameras'] if c['id']=='cc2')
cv2.setNumThreads(2);torch.set_num_threads(2);records=[];original=BYTETracker.update;i=0

def update(self,results,*args,**kwargs):
 raw=results.xyxy.copy().tolist()
 tracked=original(self,results,*args,**kwargs)
 records.append({'frame':i,'raw':raw,'tracked':tracked.tolist()})
 return tracked
BYTETracker.update=update
cap=cv2.VideoCapture(cam['source']);fps=cap.get(5)
with (out/'probe.log').open('w') as log,contextlib.redirect_stdout(log):
 tracker=CameraTracker('cc2',cfg['model_path'],cfg['detection_interval'],roi=cam.get('roi'))
 for i in range(101):
  ok,im=cap.read()
  if not ok:break
  tracker.process(i,i/fps,im)
(out/'box_measurements.json').write_text(json.dumps(records))
for r in records:
 if r['frame'] in (40,45,50,60,70,75,80,85,90,95,100):
  for t in r['tracked']:
   if int(t[4])==1:
    b=r['raw'][int(t[-1])];print(r['frame'],'raw',np.round(b,1).tolist(),'track',np.round(t[:4],1).tolist(),'width ratio',round((t[2]-t[0])/(b[2]-b[0]),2))
if '--require-bounded' in sys.argv:
 for r in records:
  for t in r['tracked']:
   b=r['raw'][int(t[-1])]
   assert t[2]-t[0] < 1.5*(b[2]-b[0]), f"Frame {r['frame']}: track width exceeds 1.5x matched detection"
