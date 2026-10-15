
import logging

from .Streming_Cameras import StreamManager
from computer_vision_v2.database.camera_registry import prepare_camera


logger = logging.getLogger(__name__)

class CameraManager:

    def __init__(self, config_file):
        self.config = config_file
        self.streams = {}
        self.last_idx = {}
        self._ended_cameras = set()

    def start_all(self):

        model_path = self.config["model_path"]
        for camera in self.config["cameras"]:
            try:
                prepare_camera(camera)
                stream_manager = StreamManager(
                    camera['id'], camera["source"], camera['type'], model_path,
                    detection_interval=self.config.get('detection_interval', 3),
                    roi=camera.get('roi'),
                )
                stream_manager.start()
            except Exception as exc:
                logger.error("Camera %s could not start: %s", camera['id'], exc)
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

    def get_finished_cameras(self):
        finished = []
        for camera_id, stream in self.streams.items():
            if camera_id not in self._ended_cameras and stream.ended.is_set():
                last = stream.get_latest_frame()
                if last is None or self.last_idx[camera_id] >= last.frame_idx:
                    self._ended_cameras.add(camera_id)
                    finished.append(camera_id)
        return finished

    def stop_all(self) :
        for camera_id, stream in list(self.streams.items()):
            if stream.stop():
                del self.streams[camera_id]
                self.last_idx.pop(camera_id, None)
