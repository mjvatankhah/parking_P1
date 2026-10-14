"""Diagnostic only: bypass localization on a visually verified plate region."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import json,cv2,numpy as np,onnxruntime as ort
from computer_vision_v2.inference.plate_ocr import PlateReader,DEFAULT_OCR,DEFAULT_LABELS
out=Path(__file__).resolve().parent
reader=PlateReader.__new__(PlateReader)
opt=ort.SessionOptions();opt.intra_op_num_threads=2;opt.inter_op_num_threads=1
reader.ocr=ort.InferenceSession(str(DEFAULT_OCR),sess_options=opt,providers=['CPUExecutionProvider'])
i=reader.ocr.get_inputs()[0];reader.ocr_input=i.name
reader.ocr_c,reader.ocr_h,reader.ocr_w=[v if isinstance(v,int) else d for v,d in zip(i.shape[1:],[1,32,128])]
reader.labels=reader._load_labels(DEFAULT_LABELS)
f=cv2.imread(str(out/'frame_510.png'))
# Corners marked visually on the full-resolution frame, not model predictions.
points=np.float32([[325,573],[429,552],[441,580],[330,601]])
M=cv2.getPerspectiveTransform(points,np.float32([[0,0],[119,0],[119,31],[0,31]]))
rectified=cv2.warpPerspective(f,M,(120,32))
variants={'manual_axis_aligned':f[550:605,320:445], 'manual_rectified':rectified}
clahe=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(4,4));variants['manual_rectified_clahe']=cv2.cvtColor(clahe.apply(cv2.cvtColor(rectified,cv2.COLOR_BGR2GRAY)),cv2.COLOR_GRAY2BGR)
results=[]
for name,crop in variants.items():
 cv2.imwrite(str(out/f'{name}.png'),crop)
 blob=reader._prep_ocr(crop);logits=reader.ocr.run(None,{reader.ocr_input:blob})[0];text,conf=reader._ctc_decode(logits)
 result={'variant':name,'text':text,'ocr_confidence':conf,'crop_size':[crop.shape[1],crop.shape[0]],'expected_visual_reading':'58م87245'};results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
(out/'manual_ocr.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
