from pathlib import Path

from ultralytics import YOLO


MODEL_PATH = Path(__file__).resolve().parents[1] / "models/vehicle/yolov8n.pt"


if __name__ == "__main__":
    YOLO(str(MODEL_PATH)).export(format="onnx", imgsz=(256, 416))
    YOLO(str(MODEL_PATH)).export(format="openvino", imgsz=(256, 416))
