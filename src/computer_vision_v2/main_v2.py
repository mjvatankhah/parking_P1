import json
import queue
import logging
import threading
import time
from pathlib import Path
import os
# پابتورچ میخواهد برای سریع شدن بعضی از پزدازش ها از(nnpack)
# استفاده کند اما سخت افزار فعلی این قابلیت رو ندارد 
# سطح لاگ پایتورچ رو روی حالت ارور بزار لذا پیام های هشدار چاپ نمیشوند
os.environ["TORCH_CPP_LOG_LEVEL"] = "ERROR"

from computer_vision_v2.streaming.Cameras_Manager import CameraManager
from computer_vision_v2.preview import PreviewPublisher
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates
from computer_vision_v2.Line_Manager.line_detector import LineDetectorManager
from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.workers.workers import observation_worker, plate_detection_worker
from computer_vision_v2.ocr_worker.ocr_worker_v2 import ocr_worker
from computer_vision_v2.database.database_worker import database_worker

logger = logging.getLogger(__name__)




class Pipeline:
    def __init__(self, config):
        self.config = config
        self.preview = PreviewPublisher(self.config["cameras"])
        self.camera_manager = CameraManager(self.config) 
        self.lines = LineDetectorManager(self.config) 
        self.plate_reader = PlateReader() 
        self.candidates = PlateCandidates(self.plate_reader, **{'deferred': True, **config.get('plate_sampling', {})})

        self.frame_queue = queue.Queue(maxsize=30)
        self.ocr_queue = queue.Queue(maxsize=16)
        self.db_queue = queue.Queue(maxsize=200)

        self.running = False
        self._started = False

        self._worker_stages = []
        self._dispatch_thread = None
        self._detection_thread = None
        
    # ساخت و شروع بکارانواع ورکر
    def _start_workers(self, target, args):
        t = threading.Thread(target = target, args = args, daemon=True)
        t.start()
        return t

    def start(self):
        if self._started:
            raise RuntimeError("Create a new Pipeline to restart after changing camera settings")
        self._started = True
        self.running = True
        self.preview.start()
        alive = lambda: self.running 

        self._worker_stages = [
            (self.frame_queue, self._start_workers(observation_worker, (self.frame_queue, self.ocr_queue, self.lines, self.candidates, alive))),
            (self.ocr_queue, self._start_workers(ocr_worker, (self.ocr_queue, self.db_queue, self.plate_reader, alive))),
            (self.db_queue, self._start_workers(database_worker, (self.db_queue, alive))),
        ]
        self._detection_thread = self._start_workers(
            plate_detection_worker, (self.candidates, self.ocr_queue, alive))
        self.camera_manager.start_all()
        if not self.camera_manager.streams:
            self.stop()
            raise RuntimeError("No camera could start; check camera and gate registration")

        self._dispatch_thread = self._start_workers(self._run_pipline, ())

    def _run_pipline(self):
        while self.running:
            frames = self.camera_manager.get_all_frame()
            if not frames :
                time.sleep(0.005)
                continue
            for frame in frames:
                self.preview.publish(frame)
                self._dispatch_frame(self.frame_queue,frame)

    @staticmethod
    def _dispatch_frame(my_queue,frame):
        try:
            my_queue.put_nowait(frame)
        except queue.Full:
            try:
                my_queue.get_nowait()
                my_queue.task_done()
            except queue.Empty:
                pass
        
            my_queue.put_nowait(frame)

    def stop(self):
        self.running = False
        if self._dispatch_thread is not None:
            self._dispatch_thread.join(timeout=5)
            if self._dispatch_thread.is_alive():
                logger.error("Pipeline dispatch did not stop within five seconds")
            else:
                self._dispatch_thread = None

        self.camera_manager.stop_all()
        self.preview.stop()

        # Stop the added detector before shutting down its downstream OCR worker.
        detection_thread = getattr(self, '_detection_thread', None)
        if detection_thread is not None:
            detection_thread.join(timeout=30)
            if detection_thread.is_alive():
                logger.error('Plate detector did not stop; downstream workers remain available')
                return
            self._detection_thread = None

        # هر مرحله تمام شود، سپس مرحله بعد سیگنال پایان بگیرد.
        still_running = []
        for input_queue, worker in self._worker_stages:
            if not worker.is_alive():
                logger.error("Pipeline worker %s stopped unexpectedly", worker.name)
                continue
            try:
                input_queue.put(None, timeout=5)
            except queue.Full:
                logger.error("Pipeline worker %s did not free its queue", worker.name)
            worker.join(timeout=5)
            if worker.is_alive():
                logger.error("Pipeline worker %s did not stop", worker.name)
                still_running.append((input_queue, worker))

        self._worker_stages = still_running

#  راه اندازی سیستم از طریق یک کامند
def main():
    BASE_DIR = Path(__file__).resolve().parent
    CONFIG_PATH = BASE_DIR.parent / "reno" / "data" / "cameras.json"

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    pipeline = Pipeline(config=config)
    pipeline.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pipeline.stop()

# راه اندازی سیتم زمان اجرا مستقیم ماژول
if __name__ == "__main__":
    main()
            
