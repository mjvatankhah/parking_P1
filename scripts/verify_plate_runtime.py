"""Check real PlateReader output parity with its original CPU policy offline."""
import argparse
import contextlib
import gc
import io
import json
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from computer_vision_v2.inference.plate_ocr import PlateReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path("reports/alpr_optimization/runtime.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/alpr_optimization/integration.json"))
    args = parser.parse_args()
    inputs = json.loads(args.inputs.read_text())["inputs"]
    report, reference_logits = {}, []
    for policy in ("original", "application"):
        reader = PlateReader(intra_op_num_threads=None) if policy == "original" else PlateReader()
        rows, texts, differences = [], [], []
        options = reader.detector.get_session_options()
        # Exercise preprocessing, NMS, coordinate mapping, crop and CTC. Only
        # suppress persistence and normalize filenames for exact comparison.
        with patch("computer_vision_v2.inference.plate_ocr.cv.imwrite", return_value=True), \
             patch("computer_vision_v2.inference.plate_ocr.time.time", return_value=1000), \
             contextlib.redirect_stdout(io.StringIO()):
            for item in inputs["detector"]:
                result = reader.read(cv2.imread(item["path"]))
                rows.append({"input": item["path"], "result": list(result)})
        for index, item in enumerate(inputs["ocr"]):
            blob = reader._prep_ocr(cv2.imread(item["path"]))
            logits = reader.ocr.run(None, {reader.ocr_input: blob})[0]
            texts.append(list(reader._ctc_decode(logits)))
            if policy == "original":
                reference_logits.append(logits.copy())
            else:
                differences.append(float(np.max(np.abs(logits - reference_logits[index]))))
        report[policy] = {"threads": options.intra_op_num_threads, "reads": rows,
                          "ocr_outputs": texts, "max_abs_ocr_difference": max(differences, default=0)}
        if policy == "application":
            assert options.get_session_config_entry("session.intra_op.allow_spinning") == "0"
            assert reader.ocr.get_session_options().get_session_config_entry("session.intra_op.allow_spinning") == "0"
        del reader
        gc.collect()
    assert report["original"]["reads"] == report["application"]["reads"]
    assert report["original"]["ocr_outputs"] == report["application"]["ocr_outputs"]
    reader = PlateReader(detector_path="/tmp/parking-model-does-not-exist.onnx")
    assert reader.detector.get_inputs()[0].shape == [1, 3, 640, 640]
    assert reader.detector.get_session_options().get_session_config_entry("session.intra_op.allow_spinning") == "0"
    for invalid in (-1, True, 1.5):
        try:
            PlateReader(intra_op_num_threads=invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted invalid thread setting: {invalid!r}")
    report.update(read_outputs_identical=True, ocr_outputs_identical=True,
                  fallback_loaded=True, invalid_options_rejected=True,
                  database_writes=False, capture_writes=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS: {len(inputs['detector'])} real reads, {len(inputs['ocr'])} OCR crops, fallback and option validation")


if __name__ == "__main__":
    main()
