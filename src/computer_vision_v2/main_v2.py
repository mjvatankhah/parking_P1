import json
import queue
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
from computer_vision_v2.best_crop_selector import BestCropSelector
from computer_vision_v2.Line_Manager.line_detector import LineDetectorManager
from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.workers.workers import line_worker , crop_worker
from computer_vision_v2.ocr_worker.ocr_worker_v2 import ocr_worker
from computer_vision_v2.database.database_worker import database_worker





class Pipeline:
    def __init__(self, config):
        self.config = config
        self.preview = PreviewPublisher(self.config["cameras"])
        self.camera_manager = CameraManager(self.config) 
        self.lines = LineDetectorManager(self.config) 
        self.selector = BestCropSelector() 
        self.plate_reader = PlateReader() 

        self.line_queue = queue.Queue(maxsize=25) # drop - oldest
        self.crop_queue = queue.Queue(maxsize=25) # drop - oldest
        self.cross_queue = queue.Queue(maxsize=300) 
        self.ocr_queue = queue.Queue(maxsize=300) 
        self.db_queue = queue.Queue(maxsize=200)

        self.running = False

        self._threads = [] # نگه داری رفرنس هر نخ برای متوقف کرن و جوین دادن اونها
        self._worker_stages = []
        self._dispatch_thread = None
        
    # ساخت و شروع بکارانواع ورکر
    def _start_workers(self, target, args):
        t = threading.Thread(target = target, args = args, daemon=True)
        t.start()
        self._threads.append(t)
        return t

    def start(self):
        self.running = True
        self.preview.start()
        alive = lambda: self.running 

        self._worker_stages = [
            (self.line_queue, self._start_workers(line_worker, (self.line_queue, self.cross_queue, self.lines, alive))),
            (self.crop_queue, self._start_workers(crop_worker, (self.crop_queue, self.cross_queue, self.ocr_queue, self.selector, alive))),
            (self.ocr_queue, self._start_workers(ocr_worker, (self.ocr_queue, self.db_queue, self.plate_reader, alive))),
            (self.db_queue, self._start_workers(database_worker, (self.db_queue, alive))),
        ]
        self.camera_manager.start_all()

        self._dispatch_thread = self._start_workers(self._run_pipline, ())

    def _run_pipline(self):
        while self.running:
            frames = self.camera_manager.get_all_frame()
            if not frames :
                time.sleep(0.005)
                continue
            for frame in frames:
                self.preview.publish(frame)
                self._dispatch_frame(self.line_queue,frame,"line_queue")
                self._dispatch_frame(self.crop_queue,frame,"crop_queue")

    @staticmethod
    def _dispatch_frame(my_queue,frame,name):
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
            self._dispatch_thread.join()

        self.preview.stop()

        # هر مرحله تمام شود، سپس مرحله بعد سیگنال پایان بگیرد.
        for input_queue, worker in self._worker_stages:
            input_queue.put(None)
            worker.join()
            
        self._worker_stages.clear()
        self.camera_manager.stop_all()

#  راه اندازی سیستم از طریق یک کامند
def main():
    BASE_DIR = Path(__file__).resolve().parent
    CONFIG_PATH = BASE_DIR / "reno" / "data" / "cameras.json"

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
            

