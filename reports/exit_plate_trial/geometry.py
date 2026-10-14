"""Experimental, image-only plate geometry. No expected text used for ranking."""
import cv2
import numpy as np

def ordered_quad(points):
 p=np.asarray(points,np.float32).reshape(4,2)
 # Order around centroid, then start at top-left; preserve orientation.
 center=p.mean(axis=0);p=p[np.argsort(np.arctan2(p[:,1]-center[1],p[:,0]-center[0]))]
 start=np.argmin(p.sum(axis=1));p=np.roll(p,-start,axis=0)
 return p

def rectify(roi):
 gray=cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY);h,w=gray.shape
 if min(h,w)<8:return None,{'reason':'too_small'}
 scale=3
 big=cv2.resize(gray,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
 blurred=cv2.GaussianBlur(big,(3,3),0)
 _,binary=cv2.threshold(blurred,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
 edges=cv2.Canny(blurred,40,120)
 candidates=[]
 for mask in (edges,binary,255-binary):
  contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
  for contour in contours:
   for eps in (.015,.025,.04):
    approx=cv2.approxPolyDP(contour,eps*cv2.arcLength(contour,True),True)
    if len(approx)!=4 or not cv2.isContourConvex(approx):continue
    q=ordered_quad(approx.reshape(4,2)/scale)
    # Contours touching the padded ROI boundary describe the crop/background,
    # not a complete observed plate boundary. Do not warp them as a plate.
    if q[:,0].min()<1 or q[:,1].min()<1 or q[:,0].max()>w-2 or q[:,1].max()>h-2:continue
    area=abs(cv2.contourArea(q));fraction=area/(w*h)
    if not .08<fraction<.90:continue
    top=np.linalg.norm(q[1]-q[0]);bottom=np.linalg.norm(q[2]-q[3]);left=np.linalg.norm(q[3]-q[0]);right=np.linalg.norm(q[2]-q[1])
    width=(top+bottom)/2;height=(left+right)/2;ratio=width/max(height,1)
    if not 2.3<ratio<7.5 or width<30 or height<8:continue
    center=q.mean(axis=0);offset=np.linalg.norm((center-np.array([w/2,h/2]))/np.array([w,h]))
    if offset>.35:continue
    # Broad plate prior + coverage; do not rank using OCR or expected plate text.
    quality=fraction*np.exp(-abs(np.log(ratio/4.5)))*np.exp(-2*offset)
    candidates.append((float(quality),q,width,height,ratio))
 if not candidates:return None,{'reason':'no_plate_quad'}
 candidates.sort(key=lambda item:item[0],reverse=True)
 quality,q,width,height,ratio=candidates[0]
 target_width=max(1,round(width));target_height=max(1,round(height))
 dst=np.float32([[0,0],[target_width-1,0],[target_width-1,target_height-1],[0,target_height-1]])
 M=cv2.getPerspectiveTransform(q,dst)
 result=cv2.warpPerspective(roi,M,(target_width,target_height),flags=cv2.INTER_CUBIC)
 return result,{'quad':q.tolist(),'geometry_quality':quality,'aspect':float(ratio),'candidates':len(candidates)}


def rectify_text_band(roi):
    """Deskew dominant edges and locate a compact row of dark characters."""
    h,w=roi.shape[:2]
    if w<35 or h<12:return None,{'reason':'too_small'}
    gray=cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY)
    big=cv2.resize(gray,None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC)
    edges=cv2.Canny(big,35,100)
    lines=cv2.HoughLinesP(edges,1,np.pi/180,threshold=30,minLineLength=w*.4*3,maxLineGap=12)
    angles=[]
    if lines is not None:
        for x1,y1,x2,y2 in lines.reshape(-1,4):
            if x2<x1:x1,x2,y1,y2=x2,x1,y2,y1
            angle=np.degrees(np.arctan2(y2-y1,x2-x1));length=np.hypot(x2-x1,y2-y1)
            if abs(angle)<45:angles.append((float(angle),float(length)))
    if not angles:return None,{'reason':'no_horizontal_edges'}
    # Long edges vote for orientation; do not choose an angle based on OCR text.
    angles.sort();half=sum(x[1] for x in angles)/2;running=0
    for angle,length in angles:
        running+=length
        if running>=half:break
    M=cv2.getRotationMatrix2D((w/2,h/2),angle,1)
    rotated=cv2.warpAffine(roi,M,(w,h),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
    g=cv2.cvtColor(rotated,cv2.COLOR_BGR2GRAY)
    blackhat=cv2.morphologyEx(g,cv2.MORPH_BLACKHAT,cv2.getStructuringElement(cv2.MORPH_RECT,(max(9,w//6),max(5,h//8))))
    _,mask=cv2.threshold(blackhat,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    merged=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_RECT,(max(5,w//12),3)))
    contours,_=cv2.findContours(merged,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    choices=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if not 2.5<bw/max(bh,1)<8 or bw<w*.45 or bh<8 or bh>h*.5:continue
        if x<=1 or y<=1 or x+bw>=w-1 or y+bh>=h-1:continue
        score=bw*bh*np.exp(-abs(np.log((bw/bh)/4.5)))*np.exp(-2*abs((y+bh/2)/h-.5))
        choices.append((score,(x,y,bw,bh)))
    if not choices:return None,{'reason':'no_text_band','angle':angle}
    score,(x,y,bw,bh)=max(choices)
    pad=2;result=rotated[max(0,y-pad):min(h,y+bh+pad),max(0,x-pad):min(w,x+bw+pad)]
    return result,{'method':'edge_deskew_text_band','angle':angle,'rect':[x,y,bw,bh],'geometry_quality':float(score/(w*h)),'aspect':bw/bh}
