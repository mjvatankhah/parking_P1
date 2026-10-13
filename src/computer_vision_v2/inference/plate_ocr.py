import json
from pathlib import Path
import time


import cv2 as cv
import numpy as np
import onnxruntime as ort

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "ocr_worker" / "models"
DEFAULT_DETECTOR = MODEL_DIR / "plate_yolo.onnx"
DEFAULT_FALLBACK = MODEL_DIR / "plate_yolo_fallback.onnx"
DEFAULT_OCR = MODEL_DIR / "ocr_crnn.onnx"
DEFAULT_LABELS = MODEL_DIR / "ocr_crnn.labels.json"
def _session(path, intra_op_num_threads=0):
    options = ort.SessionOptions()
    if intra_op_num_threads is not None:
        # OCR and detection share the CPU with capture and vehicle tracking.
        # Sleeping workers avoid competing with those stages between reads.
        options.intra_op_num_threads = intra_op_num_threads
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    return ort.InferenceSession(str(path), sess_options=options,
                                providers=["CPUExecutionProvider"])

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
                conf_thr=0.35,
                *, intra_op_num_threads=0,
    ):
        # 0 keeps automatic thread count; None also restores default spinning.
        if intra_op_num_threads is not None and (
            isinstance(intra_op_num_threads, bool)
            or not isinstance(intra_op_num_threads, int)
            or intra_op_num_threads < 0
        ):
            raise ValueError("intra_op_num_threads must be a non-negative integer or None")
        self.conf_thr = conf_thr

        # اماده کردن مدل ها
        try:
            self.detector = _session(detector_path, intra_op_num_threads)
        except Exception:
            self.detector = _session(fallback_detector_path, intra_op_num_threads)

        self.ocr = _session(ocr_path, intra_op_num_threads)
        

        self.det_input = self.detector.get_inputs()[0].name
        self.det_size = 640
        
        

        self.ocr_input = self.ocr.get_inputs()[0].name
        ocr_shape = self.ocr.get_inputs()[0].shape
        
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
        img, scale, dx, dy = _letterbox(vehicle_crop, self.det_size)
        blob = img[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        out = self.detector.run(None, {self.det_input: blob})[0]
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
        best = keep[int(np.argmax(scores[keep]))]
        x1, y1, x2, y2 = xy[best]
        x1 = (x1 - dx) / scale
        x2 = (x2 - dx) / scale
        y1 = (y1 - dy) / scale
        y2 = (y2 - dy) / scale

        h, w = vehicle_crop.shape[:2]
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(w, int(x2)), min(h, int(y2))
        if x2 <= x1 or y2 <= y1:
            return None
        plate_crop = vehicle_crop[y1:y2, x1:x2].copy()

        save_dir = save_dir = Path(__file__).resolve().parents[2] / "captured_plates"
        save_dir.mkdir(parents=True, exist_ok=True)

        image_path = save_dir / f"plate_{int(time.time() * 1000)}.jpg"
        cv.imwrite(str(image_path), plate_crop)

        
        return vehicle_crop[y1:y2, x1:x2].copy(), float(scores[best]) , str(image_path)

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
        print(
        "[PlateReader DEBUG]",
        "type=", type(vehicle_crop),
        "shape=", getattr(vehicle_crop, "shape", None)
    )
        det = self.detect_plate(vehicle_crop)
        if det is None:
            return None, 0.0 , None
        plate_crop, det_conf , image_path = det
        blob = self._prep_ocr(plate_crop)
        out = self.ocr.run(None, {self.ocr_input: blob})[0]
        text, ocr_conf = self._ctc_decode(out)
        if not text:
            return None, 0.0 , image_path
        return text, float(det_conf * 0.3 + ocr_conf * 0.7), image_path

        
        
    
