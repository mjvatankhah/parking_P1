import json
import logging
from pathlib import Path
from collections import Counter
from .plate_geometry import prepare_plate


import cv2 as cv
import numpy as np
import onnxruntime as ort

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "ocr_worker" / "models"
DEFAULT_DETECTOR = MODEL_DIR / "iranian_plate_yolo26n.onnx"
DEFAULT_FALLBACK = MODEL_DIR / "plate_yolo_fallback.onnx"
DEFAULT_OCR = MODEL_DIR / "ocr_crnn.onnx"
DEFAULT_LABELS = MODEL_DIR / "ocr_crnn.labels.json"
# منطق پشت این کد بررسی شود
def _session(path):
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])

def _letterbox(image, size=640):
    h , w = image.shape[:2]
    scale = min(size / w, size / h)
    nw , nh = int(round(w*scale)), int(round(h * scale))
    resized = cv.resize(image, (nw,nh))
    canvas = np.full((size,size,3),114,dtype=np.uint8)
    dx , dy = (size - nw) // 2, (size - nh) // 2
    canvas [dy:dy + nh, dx: dx + nw] = resized
    return canvas ,scale, dx, dy
# توضیح دقیق تر این قطعه کد
def _nms(boxes, scores, iou_thr=0.45):
    idxs = scores.argsort()[::-1]
    keep = []
    while idxs.size > 0:
        i = idxs[0]
        keep.append(i)
        if idxs.size == 1:
            break
        rest = idxs[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        area_r = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        iou = inter / (area_i + area_r - inter + 1e-9)
        idxs = rest[iou < iou_thr]
    return keep

class PlateReader:
    def __init__(self, detector_path=DEFAULT_DETECTOR,
                ocr_path=DEFAULT_OCR,
                labels_path =DEFAULT_LABELS,
                fallback_detector_path=DEFAULT_FALLBACK,
                conf_thr=0.35
    ):
        self.conf_thr = conf_thr

        self._fallback_path = fallback_detector_path
        self._fallback_detector = None
        self._fallback_attempted = False

        # اماده کردن مدل ها
        try:
            self.detector = _session(detector_path)
        except Exception:
            if fallback_detector_path is None:
                raise
            self.detector = _session(fallback_detector_path)
            self._fallback_attempted = True

        self.ocr = _session(ocr_path)
        

        self.det_input = self.detector.get_inputs()[0].name
        self.det_size = 640
        
        

        self.ocr_input = self.ocr.get_inputs()[0].name
        ocr_shape = self.ocr.get_inputs()[0].shape
        self.ocr_batch_size = ocr_shape[0] if isinstance(ocr_shape[0], int) else None
        
        self.ocr_h = ocr_shape[2] if isinstance(ocr_shape[2], int) else 32
        self.ocr_w = ocr_shape[3] if isinstance(ocr_shape[3], int) else 128
        self.ocr_c = ocr_shape[1] if isinstance(ocr_shape[1], int) else 1

        self.labels = self._load_labels(labels_path)

    @staticmethod
    def _load_labels(labels_path):
        with open(labels_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if "labels" in data:
                data = data["labels"]
            elif "characters" in data:
                data = data["characters"]
            else:
                # dict به شکل {"0": "الف", ...}
                data = [data[k] for k in sorted(data, key=lambda x: int(x))]
        return list(data)

    
    # ---------- تشخیص پلاک --------
    def detect_plate(self, vehicle_crop):
        result = self._detect_plate(vehicle_crop, self.detector, self.det_input)
        if result is not None:
            return result
        # Load once, on the first miss. A missing optional model must not stop playback.
        if not self._fallback_attempted:
            self._fallback_attempted = True
            if self._fallback_path is not None:
                try:
                    self._fallback_detector = _session(self._fallback_path)
                except Exception:
                    logging.getLogger(__name__).warning(
                        "Could not load plate fallback detector", exc_info=True)
        if self._fallback_detector is None:
            return None
        return self._detect_plate(vehicle_crop, self._fallback_detector,
                                  self._fallback_detector.get_inputs()[0].name)

    def _detect_plate(self, vehicle_crop, detector, input_name):
        img, scale, dx, dy = _letterbox(vehicle_crop, self.det_size)
        blob = img[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        out = detector.run(None, {input_name: blob})[0]
        pred = np.squeeze(out)
        if pred.ndim != 2:
            return None
        # خروجی yolov8: (4+nc, N) -> ترانهاده
        if pred.shape[0] < pred.shape[1]:
            pred = pred.T
        boxes_xywh = pred[:, :4]
        scores = pred[:, 4:].max(axis=1) if pred.shape[1] > 4 else pred[:, 4]
        mask = scores > self.conf_thr
        if not mask.any():
            return None
        boxes_xywh, scores = boxes_xywh[mask], scores[mask]

        xy = np.empty_like(boxes_xywh)
        xy[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
        xy[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
        xy[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
        xy[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2

        keep = _nms(xy, scores)
        plausible = [i for i in keep if 1.15 <= (xy[i,2]-xy[i,0])/max(xy[i,3]-xy[i,1],1) <= 8]
        best = plausible[0] if plausible else keep[0]
        x1, y1, x2, y2 = xy[best]
        x1 = (x1 - dx) / scale
        x2 = (x2 - dx) / scale
        y1 = (y1 - dy) / scale
        y2 = (y2 - dy) / scale

        h, w = vehicle_crop.shape[:2]
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(w, int(x2)), min(h, int(y2))
        if x2 <= x1 or y2 <= y1 or x1 == 0 or y1 == 0 or x2 == w or y2 == h:
            return None
        plate_crop = vehicle_crop[y1:y2, x1:x2].copy()

        # A minimum context margin keeps small glyphs away from the rotation edge.
        pad = max(12, round((x2-x1)*.15))
        context = vehicle_crop[max(0,y1-pad):min(h,y2+pad), max(0,x1-pad):min(w,x2+pad)].copy()
        return plate_crop, float(scores[best]), context

    @staticmethod
    def _select_reserved(pairs, groups, score):
        """Three quality choices plus two time-separated recent choices."""
        quality_ids, recent_ids = set(groups['quality']), set(groups['recent'])
        best = sorted((p for p in pairs if p[0].frame_idx in quality_ids),
                      key=score, reverse=True)
        selected = best[:3]
        seen = {c.frame_idx for c, _ in selected}
        recent = sorted((p for p in pairs if p[0].frame_idx in recent_ids
                         and p[0].frame_idx not in seen), key=lambda p: p[0].ts)
        # Endpoints maximize the time separation of the two recent choices.
        extra = [recent[0]] if recent else []
        if len(recent) > 1:
            extra.append(recent[-1])
        selected.extend(extra)
        seen.update(c.frame_idx for c, _ in extra)
        # Shared frames count once; fill missing slots when evidence permits.
        for pair in best[3:] + recent:
            if len(selected) >= 5:
                break
            if pair[0].frame_idx not in seen:
                selected.append(pair)
                seen.add(pair[0].frame_idx)
        return selected

    def _recognize_batch(self, images):
        """Decode one group; padding for fixed-size models never creates votes."""
        if not images:
            return []
        tensors = [self._prep_ocr(image) for image in images]
        batch_size = self.ocr_batch_size or len(tensors)
        decoded = []
        for start in range(0, len(tensors), batch_size):
            chunk = tensors[start:start + batch_size]
            count = len(chunk)
            padded = chunk + [chunk[-1]] * (batch_size - count)
            logits = self.ocr.run(None, {
                self.ocr_input: np.concatenate(padded, axis=0),
            })[0]
            if logits.ndim != 3 or logits.shape[0] != batch_size:
                raise ValueError(f'Expected batch-first OCR logits, got {logits.shape}')
            decoded.extend(self._ctc_decode(logits[i]) for i in range(count))
        return decoded

    def recognize_candidates(self, candidates):
        """Read up to five raw and five geometry images in separate batches.

        Each selected image casts its own vote if its format is valid and its
        OCR confidence reaches 0.8, including two versions of the same frame.
        """
        prepared = []
        by_frame = {}
        for candidate in candidates:
            if candidate.frame_idx in by_frame:
                continue
            by_frame[candidate.frame_idx] = candidate
            result = candidate.prepared
            if result is None:
                try:
                    result = prepare_plate(candidate.context if candidate.context is not None else candidate.crop)
                except Exception:
                    logging.getLogger(__name__).exception('Plate geometry failed during recognition')
            prepared.append((candidate, result))
        geometric = [pair for pair in prepared if pair[1] is not None]
        groups = getattr(candidates, 'selection_groups', None)
        if groups is not None:
            geometry = self._select_reserved(
                geometric, groups['geometry'], lambda pair: pair[0].confidence * pair[1].quality)
            raw = self._select_reserved(prepared, groups['raw'], lambda pair: pair[0].quality)
        else:
            # Standalone callers and the single-candidate fallback have no reserves.
            geometry = sorted(geometric, key=lambda pair: pair[0].confidence * pair[1].quality,
                              reverse=True)[:5]
            raw = sorted(prepared, key=lambda pair: pair[0].quality, reverse=True)[:5]
        readings, images = [], []
        for source, selected in (('raw', raw), ('geometry', geometry)):
            batch_images = [c.crop if source == 'raw' else result.image
                            for c, result in selected]
            decoded = self._recognize_batch(batch_images)
            for (candidate, _), image, (text, confidence) in zip(selected, batch_images, decoded):
                letter = text[2:-5]
                valid = (len(text) >= 8 and text[:2].isdigit() and text[-5:].isdigit()
                         and letter in self.labels and not letter.isdigit())
                reading = dict(text=text, confidence=confidence, valid=valid, source=source)
                reserve_groups = groups[source] if groups is not None else {}
                readings.append(dict(
                    reading, frame_idx=candidate.frame_idx, conflict=False,
                    reserves=[name for name, frames in reserve_groups.items()
                              if candidate.frame_idx in frames],
                    alternatives=[reading.copy()],
                ))
                images.append(image)
        votes = Counter(r['text'] for r in readings if r['valid'] and r['confidence'] >= .8)
        ranked = votes.most_common()
        winner, count = ranked[0] if ranked else (None, 0)
        runner_up = ranked[1][1] if len(ranked) > 1 else 0
        status = ('read' if count >= 2 and count > runner_up else
                  'uncertain' if any(r['text'] for r in readings) else 'unread')
        matching = [r['confidence'] for r in readings
                    if r['valid'] and r['confidence'] >= .8 and r['text'] == winner]
        confidence = sum(matching) / len(matching) if matching else 0.
        fallback_image = images[0] if images else candidates[0].crop if candidates else None
        image = next((im for im,r in zip(images,readings)
                      if r['valid'] and r['confidence'] >= .8 and r['text'] == winner), fallback_image)
        return dict(plate_text=winner if status == 'read' else None,
                    recognition_status=status, confidence=confidence,
                    readings=readings, image=image)

        # ---------- OCR -------
    def _prep_ocr(self, plate_crop):
        img = plate_crop
        if self.ocr_c == 1:
            img = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
        img = cv.resize(img, (self.ocr_w, self.ocr_h))
        img = img.astype(np.float32) / 255.0
        
        if self.ocr_c == 1:
            img = img[None, None, :, :]
        else:
            img = img[:, :, ::-1].transpose(2, 0, 1)[None]
        return np.ascontiguousarray(img, dtype=np.float32)

    def _ctc_decode(self, logits):
        arr = np.squeeze(logits)

        if arr.ndim != 2:
            return "", 0.0

        exp = np.exp(arr - arr.max(axis=-1, keepdims=True))
        probs = exp / exp.sum(axis=-1, keepdims=True)

        ids = probs.argmax(axis=-1)
        confs = probs.max(axis=-1)

        chars = []
        char_confs = []
        prev = -1

        for i, c in zip(ids, confs):

            i = int(i)

            if i != prev and i != 32:
                chars.append(str(self.labels[i]))
                char_confs.append(float(c))

            prev = i

        text = "".join(chars)

        conf = float(np.mean(char_confs)) if char_confs else 0.0

        return text, conf

    def read(self, vehicle_crop):
        """کراپ خودرو -> (متن پلاک، اطمینان)"""
        det = self.detect_plate(vehicle_crop)
        if det is None:
            return None, 0.0 , None
        plate_crop, det_conf, context = det
        prepared = prepare_plate(context)
        if prepared is not None:
            plate_crop = prepared.image
        image_path = None
        blob = self._prep_ocr(plate_crop)
        out = self.ocr.run(None, {self.ocr_input: blob})[0]
        text, ocr_conf = self._ctc_decode(out)
        if not text:
            return None, 0.0 , image_path
        return text, float(det_conf * 0.3 + ocr_conf * 0.7), image_path

        
        
    
