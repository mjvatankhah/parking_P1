import cv2,json
from pathlib import Path
P=Path(__file__).resolve().parent
rows={r['frame']:r for r in json.loads((P/'extended_log.json').read_text()) if r.get('track')==1}
c=cv2.VideoCapture('src/computer_vision_v2/video/InShot_20261012_210725035.mp4',cv2.CAP_FFMPEG,[cv2.CAP_PROP_N_THREADS,2])
written=0
for n in range(1,max(rows)+1):
 ok,f=c.read()
 if not ok:raise RuntimeError(n)
 if n%3 or n not in rows or (P/f'vehicle_{n}.png').exists():continue
 r=rows[n];x1,y1,x2,y2=r['bbox'];cv2.imwrite(str(P/f'vehicle_{n}.png'),f[y1:y2,x1:x2]);written+=1
c.release();print('saved additional crops',written,flush=True)
