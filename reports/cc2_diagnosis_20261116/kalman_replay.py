"""Isolate aspect-ratio lag with recorded matched boxes; no detector or optical flow."""
import json,sys
from pathlib import Path
import numpy as np
from ultralytics.trackers.byte_tracker import STrack
from ultralytics.trackers.utils.kalman_filter import KalmanFilterXYAH
rows=json.loads((Path(__file__).parent/'box_measurements.json').read_text())
initial=next(r for r in rows if r['frame']==35)['raw'][0]
def xyah(box):
 x1,y1,x2,y2=box
 return np.array([(x1+x2)/2,(y1+y2)/2,(x2-x1)/(y2-y1),y2-y1])
def run(reset_aspect=False):
 k=KalmanFilterXYAH();mean,cov=k.initiate(xyah(initial));results=[]
 for r in rows:
  if r['frame']<=35:continue
  t=next((t for t in r['tracked'] if int(t[4])==1),None)
  if t is None:continue
  b=r['raw'][int(t[-1])];measurement=xyah(b)
  if r['frame']!=40:mean,cov=k.predict(mean,cov)
  mean,cov=k.update(mean,cov,measurement)
  if reset_aspect:mean[2]=measurement[2]
  width=mean[2]*mean[3];ratio=width/(b[2]-b[0])
  if not reset_aspect:
   np.testing.assert_allclose(width,t[2]-t[0],rtol=1e-5)
  results.append({'frame':r['frame'],'measured_aspect':round(measurement[2],3),'estimated_aspect':round(mean[2],3),'width_ratio':round(ratio,3)})
 return results
base=run();changed=run(True)
print('Initial visible box aspect:',round(xyah(initial)[2],3))
for b,c in zip(base,changed):
 if b['frame'] in (40,50,60,75,80,95):print(b,'aspect-only reset width ratio:',c['width_ratio'])
print('Exact historical widths reproduced using Kalman alone.')
assert max(r['width_ratio'] for r in base)>3.5
assert max(r['width_ratio'] for r in changed)<1.1
if '--require-bounded' in sys.argv:
 assert max(r['width_ratio'] for r in base)<1.5,'Kalman aspect lag inflates the moving vehicle box'
