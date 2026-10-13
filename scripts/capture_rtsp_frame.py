"""Save one current frame from the configured RTSP camera without logging its URL."""
import json
import os
from pathlib import Path
import sys

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from computer_vision_v2.streaming.Source_Base import RTSPSource


def main():
    config = json.loads((ROOT / "src/computer_vision_v2/reno/data/cameras.json").read_text())
    camera = next(item for item in config["cameras"] if item["id"] == "cam2")
    destination = ROOT / "reports/rtsp_benchmark/live_frame_704x480.jpg"
    destination.parent.mkdir(parents=True, exist_ok=True)

    original_stderr = os.dup(2)
    quiet_stderr = os.open(os.devnull, os.O_WRONLY)
    source = None
    try:
        os.dup2(quiet_stderr, 2)
        source = RTSPSource(camera["source"])
        source.connect()
        ok, image = source.get_frame()
        if not ok:
            raise RuntimeError("RTSP frame unavailable")
        if not cv2.imwrite(str(destination), image):
            raise OSError("Could not save RTSP frame")
    finally:
        if source is not None:
            source.disconnect()
        os.dup2(original_stderr, 2)
        os.close(original_stderr)
        os.close(quiet_stderr)

    print(f"{image.shape[1]}x{image.shape[0]}")


if __name__ == "__main__":
    main()
