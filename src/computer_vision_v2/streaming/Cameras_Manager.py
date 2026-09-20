
import json
from .Streming_Cameras import StreamManager

class CameraManager:

    def __init__(self, config_file):
        self.config = config_file
        self.streams = {}
        self.last_idx = {}

    def start_all(self):

        model_path = self.config["model_path"]
        for camera in self.config["cameras"]:
            
            stream_manager = StreamManager(camera['id'],camera["source"],camera['type'],model_path)
            
            # اگر به هر دلیلی دوربین استارت نشد باقی دوربین ها اجراشون متوقف نشه
            try:
            # شروع فرایند همروندی برای این دوربین
                stream_manager.start()
            except Exception as e:
                print (f"camera {camera['id']} fail to start: {e}")
                continue

            self.streams[camera['id']] = stream_manager
            self.last_idx[camera['id']] = -1
    def get_all_frame(self):
        frames = []
        for C_id , sm in self.streams.items():
            f = sm.get_latest_frame()
            if f is None or f.frame_idx == self.last_idx[C_id]:
                continue
            self.last_idx[C_id] = f.frame_idx
            frames.append(f) 
        return frames

    def stop_all(self) :

        for sm in self.streams.values():
            sm.stop()

        self.streams = {}
