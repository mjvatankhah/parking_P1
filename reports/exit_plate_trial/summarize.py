import json,cv2,numpy as np,hashlib
from pathlib import Path
from collections import Counter
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
b=json.loads((P/'baseline.json').read_text());g=json.loads((P/'geometry_results.json').read_text());s=json.loads((P/'selection_result.json').read_text());expected='58م87245'
assert all(x['matched_log'] for x in b)
assert s['final_text']==expected and s['ocr_calls']==3
assert all(x['text']==expected for x in s['selected'])
assert all(abs(a['frame']-c['frame'])>=15 for i,a in enumerate(s['selected']) for c in s['selected'][i+1:])
assert all(next(x for x in g if x['frame']==n)['status']=='reject_aspect' for n in (159,210))
raw=[d for x in b for d in x['detections']];corrected=[x for x in g if x['status']=='ocr']
summary={'source':'src/computer_vision_v2/video/InShot_20261012_210725035.mp4','target_track':1,'sampled_logged_frames':len(b),'frame_range':[min(x['frame'] for x in b),max(x['frame'] for x in b)],'baseline_detections':len(raw),'baseline_exact':sum(x['text']==expected for x in raw),'corrected_outputs':len(corrected),'corrected_exact':sum(x['text']==expected for x in corrected),'stage_counts':dict(Counter(x['status'] for x in g)),'selected':s['selected'],'final_text':s['final_text'],'reference':'visual reading of frame_300.png; expected label used only for evaluation','limits':['one vehicle and one exit, not a production accuracy estimate','parameters developed on this clip, not an independent test set','offline replay uses logged vehicle boxes and IDs; does not test online scheduling or ID switches','deskew/text-band extraction is automatic; no manually selected corners','not all candidates become readable, and some cases deliberately abstain']}
(P/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
font=ImageFont.truetype(str(ROOT/'src/reno/assets/fonts/Vazirmatn-Regular.ttf'),23,layout_engine=ImageFont.Layout.BASIC)
small=ImageFont.truetype(str(ROOT/'src/reno/assets/fonts/Vazirmatn-Regular.ttf'),19,layout_engine=ImageFont.Layout.BASIC)
def tile(path,title,text=''):
 im=cv2.imread(str(path));h,w=im.shape[:2];scale=min(420/w,155/h);im=cv2.resize(im,(round(w*scale),round(h*scale)),interpolation=cv2.INTER_NEAREST)
 canvas=Image.new('RGB',(460,245),(25,25,25));draw=ImageDraw.Draw(canvas);draw.text((12,8),title,font=small,fill='white');canvas.paste(Image.fromarray(cv2.cvtColor(im,cv2.COLOR_BGR2RGB)),((460-im.shape[1])//2,42));draw.text((12,204),text,font=font,fill=(255,215,90));return np.array(canvas)
rows=[]
for item in sorted(s['selected'],key=lambda x:x['frame']):
 n=item['frame'];d=next(x for x in b if x['frame']==n)['detections'][0]
 rows.append(np.hstack((tile(P/f'plate_{n}_0.png',f'Frame {n}: original OCR input',d['text']),tile(P/f'selected_{n}.png',f'Frame {n}: automatic deskew + text crop',item['text']))))
cv2.imwrite(str(P/'before_after.jpg'),cv2.cvtColor(np.vstack(rows),cv2.COLOR_RGB2BGR))
neg=[x for x in g if x['status']=='reject_aspect'];tiles=[tile(P/f"plate_{x['frame']}_0.png",f"Frame {x['frame']} - rejected shape",x['baseline']['text']) for x in neg]
while len(tiles)%4:tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(str(P/'rejected_candidates.jpg'),cv2.cvtColor(np.vstack([np.hstack(tiles[i:i+4]) for i in range(0,len(tiles),4)]),cv2.COLOR_RGB2BGR))
files=['src/computer_vision_v2/inference/plate_ocr.py','src/computer_vision_v2/debug_plate.py','src/computer_vision_v2/tracking/tracker.py','src/computer_vision_v2/ocr_worker/models/plate_yolo.onnx','src/computer_vision_v2/ocr_worker/models/ocr_crnn.onnx']
(P/'hashes.json').write_text(json.dumps({f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
