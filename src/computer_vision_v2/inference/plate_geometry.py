"""Image-only deskew and text-band extraction; masks never enter OCR."""
import cv2
import numpy as np
from dataclasses import dataclass


@dataclass
class PreparedPlate:
    image: object
    quality: float


def prepare_plate(roi):
    h, w = roi.shape[:2]
    if w < 35 or h < 12:
        return None
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    edges = cv2.Canny(big, 35, 100)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=30,
                            minLineLength=w*.4*3, maxLineGap=12)
    angles = []
    if lines is not None:
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            if x2 < x1:
                x1, x2, y1, y2 = x2, x1, y2, y1
            angle = np.degrees(np.arctan2(y2-y1, x2-x1))
            if abs(angle) < 45:
                angles.append((float(angle), float(np.hypot(x2-x1, y2-y1))))
    if not angles:
        return None
    half = sum(length for _, length in angles)/2
    running = 0
    for angle, length in sorted(angles):
        running += length
        if running >= half:
            break
    matrix = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
    rotated = cv2.warpAffine(roi, matrix, (w, h), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_REPLICATE)
    gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(9,w//6), max(5,h//8)))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    _, mask = cv2.threshold(blackhat, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(5,w//12),3))
    merged = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    choices = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if not 2.5 < bw/max(bh,1) < 8 or bw < w*.45 or bh < 8 or bh > h*.5:
            continue
        if x <= 1 or y <= 1 or x+bw >= w-1 or y+bh >= h-1:
            continue
        score = bw*bh*np.exp(-abs(np.log((bw/bh)/4.5)))*np.exp(-2*abs((y+bh/2)/h-.5))
        choices.append((score, (x,y,bw,bh)))
    if not choices:
        return None
    score, (x,y,bw,bh) = max(choices)
    image = rotated[max(0,y-2):min(h,y+bh+2), max(0,x-2):min(w,x+bw+2)].copy()
    return PreparedPlate(image, float(score/(w*h)))
