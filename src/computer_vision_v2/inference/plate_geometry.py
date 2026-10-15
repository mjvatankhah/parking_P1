"""Image-only deskew and text-band extraction; masks never enter OCR."""
import cv2
import numpy as np
from dataclasses import dataclass


@dataclass
class PreparedPlate:
    image: object
    quality: float


def _prepare_deskew(roi):
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


def _rectify_plate(roi):
    """Accept a visible convex plate border; never invent missing corners.

    These are geometric/image checks, not a calibrated probability. Ambiguous,
    clipped, tiny or text-free quadrilaterals fall back to the old deskew path.
    """
    h, w = roi.shape[:2]
    if w < 50 or h < 20:
        return None
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 35, 100)
    _, light = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(light, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    supported = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    choices = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if not .15*w*h < area < .85*w*h:
            continue
        polygon = cv2.approxPolyDP(contour, .01*cv2.arcLength(contour, True), True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        points = polygon.reshape(4, 2).astype(np.float32)
        # Cyclic contour order is preserved; the upper-left corner starts it.
        points = np.roll(points, -int(np.argmin(points.sum(axis=1))), axis=0)
        if points[1, 0] < points[-1, 0]:
            points = points[[0, 3, 2, 1]]
        if (points[:, 0].min() <= 1 or points[:, 1].min() <= 1 or
                points[:, 0].max() >= w-2 or points[:, 1].max() >= h-2):
            continue
        refined = cv2.cornerSubPix(gray, points.copy(), (4, 4), (-1, -1),
                                   (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 20, .05))
        if np.max(np.linalg.norm(refined-points, axis=1)) > 4:
            continue
        if (refined[:, 0].min() <= 1 or refined[:, 1].min() <= 1 or
                refined[:, 0].max() >= w-2 or refined[:, 1].max() >= h-2):
            continue
        points = refined
        sides = np.roll(points, -1, axis=0) - points
        lengths = np.linalg.norm(sides, axis=1)
        width, height = max(lengths[0], lengths[2]), max(lengths[1], lengths[3])
        if width < max(40, .5*w) or height < 12 or not 2.5 < width/height < 6.5:
            continue
        if max(lengths[0], lengths[2])/min(lengths[0], lengths[2]) > 1.6:
            continue
        if max(lengths[1], lengths[3])/min(lengths[1], lengths[3]) > 1.6:
            continue
        cosine = np.sum(-np.roll(sides, 1, axis=0)*sides, axis=1)
        cosine /= np.roll(lengths, 1)*lengths
        if np.any(np.abs(cosine) > .7):
            continue
        # Every side must be supported, not just two convenient parallel lines.
        if any(np.mean(supported[
                np.rint(np.linspace(a[1], b[1], 40)).astype(int),
                np.rint(np.linspace(a[0], b[0], 40)).astype(int)] > 0) < .8
               for a, b in zip(points, np.roll(points, -1, axis=0))):
            continue
        ow, oh = round(float(width)), round(float(height))
        target = np.float32([[0, 0], [ow-1, 0], [ow-1, oh-1], [0, oh-1]])
        matrix = cv2.getPerspectiveTransform(points, target)
        image = cv2.warpPerspective(roi, matrix, (ow, oh), flags=cv2.INTER_CUBIC)
        inside = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, ink = cv2.threshold(inside, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        count, _, stats, centers = cv2.connectedComponentsWithStats(ink)
        glyphs = [i for i in range(1, count)
                  if .25*oh <= stats[i, cv2.CC_STAT_HEIGHT] <= .9*oh
                  and 1 <= stats[i, cv2.CC_STAT_WIDTH] <= .2*ow
                  and stats[i, cv2.CC_STAT_AREA] >= 3
                  and stats[i, 0] > 0 and stats[i, 1] > 0
                  and stats[i, 0]+stats[i, 2] < ow
                  and stats[i, 1]+stats[i, 3] < oh]
        if len(glyphs) < 5:
            continue
        centers = centers[glyphs]
        if np.ptp(centers[:, 0]) < .5*ow or np.std(centers[:, 1]) > .15*oh:
            continue
        choices.append((area, points, image))
    if not choices:
        return None
    choices.sort(key=lambda item: item[0], reverse=True)
    best = choices[0]
    # Multiple distinct plate-like regions are not reliable corner evidence.
    if any(area > .7*best[0] and np.max(np.linalg.norm(points-best[1], axis=1)) > 3
           for area, points, _ in choices[1:]):
        return None
    return best[2]


def prepare_plate(roi):
    original = _prepare_deskew(roi)
    rectified = _rectify_plate(roi)
    if rectified is None:
        return original
    # Retain the established text-band extraction and ranking scale.
    h, w = rectified.shape[:2]
    padded = cv2.copyMakeBorder(rectified, h//2, h//2, w//8, w//8,
                               cv2.BORDER_REPLICATE)
    result = _prepare_deskew(padded)
    if result is None:
        return original
    if original is not None:
        result.quality = original.quality
    return result
