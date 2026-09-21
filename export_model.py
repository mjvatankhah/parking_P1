from ultralytics import YOLO
YOLO("yolov8n.pt").export(format="onnx", imgsz=(256, 416))
YOLO("yolov8n.pt").export(format="openvino", imgsz=(256, 416))
