"""ROI + every-third-frame plate candidates + image-only selection + 3 OCR votes.

All thresholds are experimental. Expected text is used only for evaluation.
"""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
import json,cv2,numpy as np,onnxruntime as ort
from pathlib import Path
from collections import defaultdict,Counter
from geometry import rectify,rectify_text_band
from computer_vision_v2.inference.plate_ocr import PlateReader,DEFAULT_OCR,DEFAULT_LABELS
P=Path(__file__).resolve().parent
ROI=(.10,.10,.75,.65);MIN_SEPARATION=15;K=3
baseline=json.loads((P/'baseline.json').read_text());candidates=[];counts=Counter()
for b in baseline:
 n=b['frame'];x1,y1,x2,y2=b['vehicle_bbox'];cx=(x1+x2)/2/1920;cy=(y1+y2)/2/1080
 if n%3 or not(ROI[0]<=cx<=ROI[2] and ROI[1]<=cy<=ROI[3]):counts['outside_roi_or_sampling']+=1;continue
 counts['sampled_frames']+=1
 v=cv2.imread(str(P/f'vehicle_{n}.png'))
 for k,d in enumerate(b['detections']):
  x1,y1,x2,y2=d['bbox']
  if (x2-x1)/(y2-y1)<1.15:counts['rejected_aspect']+=1;continue
  pad=12;roi=v[max(0,y1-pad):y2+pad,max(0,x1-pad):x2+pad]
  crop,geometry=rectify(roi)
  if crop is None:crop,geometry=rectify_text_band(roi)
  if crop is None:counts['no_geometry']+=1;continue
  # Only image geometry and detector score; no OCR text or expected label used.
  quality=d['score']*geometry['geometry_quality']
  candidates.append({'frame':n,'candidate':k,'quality':quality,'geometry':geometry,'detector_score':d['score'],'crop':crop})
selected=[]
for item in sorted(candidates,key=lambda c:c['quality'],reverse=True):
 if any(abs(item['frame']-s['frame'])<MIN_SEPARATION for s in selected):continue
 selected.append(item)
 if len(selected)==K:break
r=PlateReader.__new__(PlateReader);opt=ort.SessionOptions();opt.intra_op_num_threads=2;opt.inter_op_num_threads=1
r.ocr=ort.InferenceSession(str(DEFAULT_OCR),sess_options=opt,providers=['CPUExecutionProvider']);i=r.ocr.get_inputs()[0];r.ocr_input=i.name;r.ocr_c,r.ocr_h,r.ocr_w=[v if isinstance(v,int) else d for v,d in zip(i.shape[1:],[1,32,128])];r.labels=r._load_labels(DEFAULT_LABELS)
votes=defaultdict(float);occurrences=Counter()
for item in selected:
 crop=item.pop('crop');cv2.imwrite(str(P/f"selected_{item['frame']}.png"),crop)
 text,conf=r._ctc_decode(r.ocr.run(None,{r.ocr_input:r._prep_ocr(crop)})[0]);item.update(text=text,ocr_confidence=conf)
 # Restrict this experiment to the observed single-line private-car format.
 valid=len(text)==8 and text[:2].isdigit() and not text[2].isdigit() and text[3:].isdigit()
 item['valid_format']=valid
 if valid:votes[text]+=conf*item['quality'];occurrences[text]+=1
winner=max(votes,key=votes.get) if votes else None
final=winner if winner is not None and occurrences[winner]>=2 else None
result={'roi':ROI,'frame_spacing':3,'candidate_separation_frames':MIN_SEPARATION,'candidate_count':len(candidates),'stage_counts':dict(counts),'selected':selected,'votes':dict(votes),'occurrences':dict(occurrences),'final_text':final,'decision':'agreed' if final else 'uncertain','expected_for_evaluation_only':'58م87245','correct':final=='58م87245','ocr_calls':len(selected),'last_observed_frame':max(b['frame'] for b in baseline),'scope':'one known exiting track; no multi-car ID-switch validation'}
(P/'selection_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
