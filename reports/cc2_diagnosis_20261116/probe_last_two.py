import json,cv2,torch
from pathlib import Path
from ultralytics import YOLO
p=Path(__file__).resolve().parent;cfg=json.loads((p/'cc2_config.json').read_text());cap=cv2.VideoCapture(cfg['cameras'][0]['source']);cv2.setNumThreads(2);torch.set_num_threads(2);model=YOLO(cfg['model_path'],task='detect');out=[]
for frame in (310,311,316,321,330):
 cap.set(1,frame-1);ok,im=cap.read();r=model.predict(im,classes=[0,2],conf=.1,imgsz=(384,640),verbose=False)[0]
 out.append({'frame':frame,'boxes':r.boxes.data.tolist()});print(frame,[[round(v,2) for v in b] for b in out[-1]['boxes']])
(p/'last_two_raw.json').write_text(json.dumps(out,indent=2))
