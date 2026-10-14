import json, pickle
from pathlib import Path
import cv2, torch
from computer_vision_v2.tracking.tracker import CameraTracker
from computer_vision_v2.Line_Manager.line_detector import LineDetectorManager
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates
from computer_vision_v2.inference.plate_ocr import PlateReader
out=Path(__file__).resolve().parent / "last_car_probe"
out.mkdir(exist_ok=True)
torch.set_num_threads(2)
cv2.setNumThreads(2)
cfg=json.loads(Path('src/reno/data/cameras.json').read_text()); cam=cfg['cameras'][0]
reader=PlateReader(); selector=PlateCandidates(reader, **cfg.get('plate_sampling',{}))
tracker=CameraTracker(cam['id'],cfg['model_path'],cfg['detection_interval'],cam['roi'])
lines=LineDetectorManager(cfg)
cap=cv2.VideoCapture(cam['source']); fps=cap.get(cv2.CAP_PROP_FPS)
cap.set(cv2.CAP_PROP_POS_FRAMES,2030)
rows=[]
probes=[]
original_detect=reader.detect_plate
from computer_vision_v2.ocr_worker import plate_candidates as pc
original_prepare=pc.prepare_plate
def detect(vehicle):
    result=original_detect(vehicle)
    row={'frame':idx,'vehicle_shape':list(vehicle.shape),'detected':result is not None}
    probes.append(row)
    if result is not None:
        crop,confidence,context=result
        row.update(confidence=float(confidence),crop_shape=list(crop.shape))
        cv2.imwrite(str(out/f'frame_{idx}_raw.jpg'),crop)
        cv2.imwrite(str(out/f'frame_{idx}_context.jpg'),context)
    (out/'probes.json').write_text(json.dumps(probes,indent=2))
    return result
def prepare(roi):
    result=original_prepare(roi)
    probes[-1]['geometry_ok']=result is not None
    if result is not None:
        cv2.imwrite(str(out/f'frame_{idx}_prepared.jpg'),result.image)
    (out/'probes.json').write_text(json.dumps(probes,indent=2))
    return result
reader.detect_plate=detect
pc.prepare_plate=prepare

for idx in range(2031,2256):
    ok,image=cap.read()
    if not ok: break
    frame=tracker.process(idx,idx/fps,image)
    for passage in selector.observe(frame,lines.update(frame)):
        n=len(rows)+1
        with (out/f'event_{n}.pkl').open('wb') as f: pickle.dump(passage,f)
        result=reader.recognize_candidates(passage.candidates)
        preview=result.pop('image')
        if preview is not None: cv2.imwrite(str(out/f'event_{n}_preview.jpg'),preview)
        for c in passage.candidates:
            cv2.imwrite(str(out/f'event_{n}_frame_{c.frame_idx}_raw.jpg'),c.crop)
            if c.prepared is not None: cv2.imwrite(str(out/f'event_{n}_frame_{c.frame_idx}_prepared.jpg'),c.prepared.image)
        row={'event':passage.event,'completed_frame':idx,'candidate_frames':[c.frame_idx for c in passage.candidates],**result}
        rows.append(row)
        (out/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2,default=float))
        print(json.dumps(row,ensure_ascii=False,default=float),flush=True)
    if idx%150==0: print('progress',idx,flush=True)

cap.release()
(out/'probes.json').write_text(json.dumps(probes,indent=2))
