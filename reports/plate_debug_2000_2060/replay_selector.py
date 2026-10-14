import json,cv2
from pathlib import Path
from types import SimpleNamespace
from computer_vision_v2 import best_crop_selector as selection
from computer_vision_v2.Line_Manager import line_detector as lines
from computer_vision_v2.tracking.frame_info import Detection,TrackedFrame
root=Path(__file__).resolve().parents[2];out=root/'reports/plate_debug_2000_2060'
rows=[json.loads(l) for l in (root/'reports/plate_debug/20261012-200343/results.jsonl').read_text().splitlines()]
rows=[r for r in rows if r.get('track')==1]
config=json.loads((root/'src/reno/data/cameras.json').read_text());cam=config['cameras'][0]
selector=selection.BestCropSelector();line=lines.LineDetectorManager(config);clock=SimpleNamespace(monotonic=lambda:current_time)
selection.time=clock;lines.time=clock
capture=cv2.VideoCapture(str(root/'src/computer_vision_v2/video/Rec 0073.mp4'))
first=min(r['frame'] for r in rows);by_frame={r['frame']:r for r in rows};events=[];changes=[];last_best=None
for n in range(1,max(by_frame)+1):
 ok,f=capture.read()
 if not ok:break
 current_time=n/29.99747378928539
 r=by_frame.get(n)
 detections=[] if r is None else [Detection(r['track'],tuple(r['bbox']),2,r['vehicle_confidence'],r['predicted'])]
 tracked=TrackedFrame(cam['id'],n,current_time,f,detections)
 events.extend(line.update(tracked));selector.update(cam['id'],tracked)
 best=selector.best_frames.get((cam['id'],1))
 if best is not None and best['frame_idx']!=last_best:
  last_best=best['frame_idx'];changes.append({'observed_frame':n,'best_frame':last_best,'score':float(best['score'])})
 if n==2060:
  cv2.imwrite(str(out/'selector_best_through_2060.png'),best['crop']);best2060={'frame':best['frame_idx'],'score':float(best['score']),'shape':list(best['crop'].shape)}
capture.release();result={'clock':'video time, reconstructed; not historical wall time','best_at_2060':best2060,'crossings':events,'selection_changes':changes}
(out/'selector_replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
