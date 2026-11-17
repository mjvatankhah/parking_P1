from plakino_logging import configure_logging, FrameMetrics
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
from computer_vision_v2.storage.storage_worker import storage_worker
from computer_vision_v2.ocr_worker.diagnostic_runtime import runtime_by_camera

logger = logging.getLogger(__name__)




class Pipeline:
    def __init__(self, config):
        configure_logging('pipeline')
        self._frame_metrics = {}
        self.config = config
        self.preview = PreviewPublisher(self.config["cameras"])
        self.camera_manager = CameraManager(self.config) 
        self.lines = LineDetectorManager(self.config) 
        self.plate_reader = PlateReader() 
        self.candidates = PlateCandidates(self.plate_reader, **{'deferred': True,
            'diagnostics': config.get('crop_diagnostics', {'enabled': True}),
            **config.get('plate_sampling', {})})
        if self.candidates.diagnostics.get('enabled', False):
            self.candidates.diagnostics = {**self.candidates.diagnostics,
                'runtime_by_camera': runtime_by_camera(config, self.plate_reader, self.candidates)}

        self.frame_queue = queue.Queue(maxsize=30)
        self.ocr_queue = queue.Queue(maxsize=16)
        self.storage_queue = queue.Queue(maxsize=16)
        self.db_queue = queue.Queue(maxsize=200)

        self.running = False
        self._started = False

        self._worker_stages = []
        self._dispatch_thread = None
        self._detection_thread = None
        
    # ساخت و شروع بکارانواع ورکر
    def _start_workers(self, target, args):
        def guarded():
            try:
                target(*args)
            except Exception:
                logger.exception("Worker stopped unexpectedly", extra={"event": "worker_crashed", "stage": target.__name__})
        t = threading.Thread(target=guarded, name=target.__name__, daemon=True)
        t.start()
        return t

    def start(self):
        if self._started:
            raise RuntimeError("Create a new Pipeline to restart after changing camera settings")
        self._started = True
        self.running = True
        logger.info("Pipeline starting", extra={"event": "pipeline_started"})
        self.preview.start()
        alive = lambda: self.running 

        self._worker_stages = [
            (self.frame_queue, self._start_workers(observation_worker, (self.frame_queue, self.ocr_queue, self.lines, self.candidates, alive))),
            (self.ocr_queue, self._start_workers(ocr_worker, (self.ocr_queue, self.storage_queue, self.plate_reader, alive))),
            (self.storage_queue, self._start_workers(storage_worker, (self.storage_queue, self.db_queue, alive))),
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
                dropped = self._dispatch_frame(self.frame_queue,frame)
                if frame.camera_id not in self._frame_metrics:
                    self._frame_metrics[frame.camera_id] = FrameMetrics(frame.camera_id, "observation_queue")
                same_camera_drop = dropped is not None and dropped.camera_id == frame.camera_id
                self._frame_metrics[frame.camera_id].add(received=1, replaced=int(same_camera_drop))
                if dropped is not None and not same_camera_drop:
                    if dropped.camera_id not in self._frame_metrics:
                        self._frame_metrics[dropped.camera_id] = FrameMetrics(dropped.camera_id, "observation_queue")
                    self._frame_metrics[dropped.camera_id].add(replaced=1)
                if time.monotonic() - getattr(self, "_last_queue_log", 0) >= 30:
                    self._last_queue_log = time.monotonic()
                    logger.info("Pipeline queues", extra={"event": "queue_status", "queues": {name: getattr(self, name).qsize() for name in ("frame_queue", "ocr_queue", "storage_queue", "db_queue")}})

    @staticmethod
    def _dispatch_frame(my_queue,frame):
        dropped = None
        try:
            my_queue.put_nowait(frame)
        except queue.Full:
            try:
                dropped = my_queue.get_nowait()
                my_queue.task_done()
            except queue.Empty:
                pass
        
            my_queue.put_nowait(frame)
        return dropped

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
        for index, (input_queue, worker) in enumerate(self._worker_stages):
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
                still_running.extend(self._worker_stages[index:])
                break

        self._worker_stages = still_running
        logger.info("Pipeline stop completed", extra={"event": "pipeline_stopped", "status": "incomplete" if still_running else "stopped"})

#  راه اندازی سیستم از طریق یک کامند
def main():
    BASE_DIR = Path(__file__).resolve().parent
    CONFIG_PATH = BASE_DIR.parent / "plakino_ui" / "data" / "cameras.json"

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
            
