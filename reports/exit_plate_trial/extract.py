import cv2,json,numpy as np
from pathlib import Path
P=Path(__file__).resolve().parent
rows=json.loads((P/'source_log.json').read_text());by_frame={r['frame']:r for r in rows if r.get('track')==1}
c=cv2.VideoCapture('src/computer_vision_v2/video/InShot_20261012_210725035.mp4',cv2.CAP_FFMPEG,[cv2.CAP_PROP_N_THREADS,2]);tiles=[]
for n in range(1,901):
 ok,f=c.read()
 if not ok:break
 if n in by_frame and (n%3==0 or n in (1,)):
  r=by_frame[n];x1,y1,x2,y2=r['bbox'];cv2.imwrite(str(P/f'vehicle_{n}.png'),f[y1:y2,x1:x2])
 if n==1 or n%50==0:
  cv2.imwrite(str(P/f'frame_{n}.png'),f);im=cv2.resize(f,(480,270));cv2.putText(im,str(n),(10,28),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,255),2);tiles.append(im)
c.release()
while len(tiles)%4:tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(str(P/'timeline.jpg'),np.vstack([np.hstack(tiles[i:i+4]) for i in range(0,len(tiles),4)]))
# A contact sheet of logged detector crops, preserving their original pixels on disk.
reads=[r for r in rows if r.get('track')==1 and r.get('plate_path')]
t=[]
for r in reads[::max(1,len(reads)//24)]:
 im=cv2.imread(r['plate_path']);h,w=im.shape[:2];s=min(240/w,100/h);im=cv2.resize(im,(round(w*s),round(h*s)));tile=np.full((135,250,3),25,np.uint8);tile[30:30+im.shape[0],:im.shape[1]]=im;cv2.putText(tile,f"f{r['frame']} {r['detector_confidence']:.2f}",(5,20),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1);t.append(tile)
while len(t)%4:t.append(np.zeros_like(t[0]))
cv2.imwrite(str(P/'logged_plates.jpg'),np.vstack([np.hstack(t[i:i+4]) for i in range(0,len(t),4)]))
print('DONE',len(by_frame),'logged frames extracted; timeline through',n,flush=True)
