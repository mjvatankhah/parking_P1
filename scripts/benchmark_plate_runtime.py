"""Offline ALPR size/thread experiment; no camera, database or capture writes.

Saved plate crops test OCR only. Detector inputs include one real vehicle crop
and diagnostic camera images, not an annotated accuracy/recall benchmark.
"""
import argparse
import gc
import hashlib
import json
import platform
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from computer_vision_v2.inference.plate_ocr import (
    DEFAULT_DETECTOR, DEFAULT_LABELS, DEFAULT_OCR, PlateReader, _letterbox,
)


def summary(values):
    return {"median_ms": float(np.median(values)),
            "p95_ms": float(np.percentile(values, 95)),
            "mean_ms": float(np.mean(values)), "samples_ms": values}


def session(path, threads):
    options = ort.SessionOptions()
    if threads is not None:
        options.intra_op_num_threads = threads
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    return ort.InferenceSession(str(path), sess_options=options,
                               providers=["CPUExecutionProvider"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--sizes", type=int, nargs="+", default=[640, 416, 320])
    parser.add_argument("--threads", nargs="+", default=["default", "1", "2", "4"])
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("rounds must be positive")
    cv2.setNumThreads(1)
    detector_paths = [Path("reports/plate_model_trial/video_091951/vehicle_1.png")]
    detector_paths += sorted(Path("reports/crossing_audit/full_scan").glob("frame_*.jpg"))[::10]
    ocr_paths = sorted(Path("src/captured_plates").glob("*.jpg"))
    paths = {"detector": detector_paths, "ocr": ocr_paths}
    images = {key: [cv2.imread(str(p)) for p in items] for key, items in paths.items()}
    if any(im is None for items in images.values() for im in items):
        raise ValueError("Unreadable benchmark input")
    reader = PlateReader.__new__(PlateReader)
    reader.ocr_c, reader.ocr_h, reader.ocr_w = 1, 32, 128
    reader.labels = reader._load_labels(DEFAULT_LABELS)
    models = {"detector": DEFAULT_DETECTOR, "ocr": DEFAULT_OCR}
    report = {"platform": platform.platform(), "ort": ort.__version__,
              "providers": ort.get_available_providers(), "rounds": args.rounds,
              "cv_threads": 1, "models": {}, "inputs": {}, "results": [],
              "limitations": "Unlabelled local samples; full frames are detector probes, not vehicle crops. Inference-only latency, not live FPS. p95 is descriptive for a small sample."}
    for key, path in models.items():
        report["models"][key] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    for key, items in paths.items():
        report["inputs"][key] = [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                                   "shape": list(im.shape)} for p, im in zip(items, images[key])]
    references = {}
    # Reverse configuration order on alternate rounds to reduce order bias.
    for round_index in range(args.rounds):
        configs = args.threads if round_index % 2 == 0 else args.threads[::-1]
        for config in configs:
            threads = None if config == "default" else int(config)
            # Both sessions remain alive as in the production PlateReader.
            sessions = {key: session(path, threads) for key, path in models.items()}
            for key, sess in sessions.items():
                for size in args.sizes if key == "detector" else [128]:
                    blobs = []
                    for im in images[key]:
                        if key == "detector":
                            boxed = _letterbox(im, size)[0]
                            blob = boxed[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
                        else:
                            blob = reader._prep_ocr(im)
                        blobs.append(blob)
                    name = sess.get_inputs()[0].name
                    for _ in range(2):
                        sess.run(None, {name: blobs[0]})
                    elapsed, outputs, differences = [], [], []
                    cpu_start = time.process_time()
                    for index, blob in enumerate(blobs):
                        start = time.perf_counter()
                        out = sess.run(None, {name: blob})[0]
                        elapsed.append((time.perf_counter() - start) * 1000)
                        ref_key = (key, size, index)
                        if ref_key not in references:
                            references[ref_key] = out.copy()
                        differences.append(float(np.max(np.abs(out - references[ref_key]))))
                        if key == "ocr":
                            text, confidence = reader._ctc_decode(out)
                            outputs.append({"text": text, "confidence": confidence})
                        else:
                            pred = out[0].T
                            best = pred[np.argmax(pred[:, 4])]
                            outputs.append({"best_score": float(best[4]), "box_xywh": best[:4].tolist(),
                                            "detected_at_035": bool(best[4] > .35)})
                    cpu_ms = (time.process_time() - cpu_start) * 1000
                    result = {"round": round_index, "model": key, "size": size, "threads": config,
                              **summary(elapsed), "cpu_ms": cpu_ms,
                              "max_abs_difference_same_size": max(differences), "outputs": outputs}
                    report["results"].append(result)
                    print(json.dumps({k: v for k, v in result.items() if k not in ("outputs", "samples_ms")}), flush=True)
            del sess, sessions
            gc.collect()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
