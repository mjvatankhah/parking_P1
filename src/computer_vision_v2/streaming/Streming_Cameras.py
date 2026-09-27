import threading
import time
from collections import namedtuple

from .Source_Base import VideoSource , RTSPSource
from computer_vision_v2.tracking.tracker import CameraTracker

Frame = namedtuple('Frame','camera_id frame_idx ts image detections')

class StreamManager:
    def __init__(self,camera_id, source,source_type,model_path,detection_interval=3):
        self.camera_id = camera_id
        self.source = source
        self.source_type = source_type
        self.running = False
        self.thread = None
        self.my_source = None
        self.frame = None
        self.frame_idx = 0
        self.tracker = CameraTracker(camera_id=camera_id, model_path=model_path,
                                     detection_interval=detection_interval)

        # یعنی چی اینجا
        self.lock = threading.Lock()

    def _creat_source (self):
        if self.source_type == 'video':
            return VideoSource(self.source)
        elif self.source_type == 'rtsp':
            return RTSPSource(self.source)
        else:
            
            raise ValueError('unknown source type')
        
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(
            target=self._read_loop,
            daemon=True,
        )

        self.thread.start()
        if self.running:
            return

            
    def _read_loop(self) -> None:

        backoff = 0
        while self.running:
            # مطمین شدن از انصال دوربینها به سیستم
            try:
                self.my_source = self._creat_source()
                self.my_source.connect()
                backoff = 1
                break
            except Exception as e:
                print(f"{self.camera_id} not connect{e}.  retry....")
                # [جلوگیری از درخواست های مجددو و پشت هم برای اتصال]
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
        # خواندن فریم ها بعد از اتصال موفق
        count_framefail= 0
        while self.running:
            
            ret , image = self.my_source.get_frame()
            #.............
            print(f"{self.camera_id}: frame received = {ret}")
            if not ret:
                count_framefail += 1
                if count_framefail > 30:
                    break
                time.sleep(0.1)
                continue

            count_framefail = 0
            tracked_frame = self.tracker.process( frame_idx=self.frame_idx + 1, ts=time.monotonic(), image=image, )
            print(
    f"{self.camera_id}: "
    f"processed frame = {tracked_frame.frame_idx}, "
    f"detections = {len(tracked_frame.detections)}"
)
            self._handle_frame(tracked_frame)
        try:
            self.my_source.disconnect()
        except Exception:
            pass
        self.my_source = None
            


    def _handle_frame(self,tracked_frame):
        with self.lock:
            self.frame_idx = tracked_frame.frame_idx
            self.frame = tracked_frame

    def get_latest_frame(self):
        with self.lock:
            return self.frame
    

    def stop(self) :
        self.running = False
        if self.thread is not None:
            self.thread.join()
            self.thread = None
        if self.my_source is not None:
            try:
                self.my_source.disconnect()
            except Exception:
                pass
