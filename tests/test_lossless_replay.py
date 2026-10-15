"""Exercise offline scheduling and EOF with real candidate lifetime rules."""
import importlib.util
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import numpy as np

from computer_vision_v2.tracking.frame_info import Detection, TrackedFrame

spec=importlib.util.spec_from_file_location('lossless',Path(__file__).parents[1]/'scripts/replay_video_lossless.py')
replay=importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class Capture:
    def __init__(self, _): self.index=0
    def isOpened(self): return True
    def get(self, key): return 10 if key==replay.cv2.CAP_PROP_FPS else 21
    def read(self):
        self.index+=1
        return (True,np.zeros((100,100,3),np.uint8)) if self.index<=20 else (False,None)
    def release(self): pass


class ReplayTests(unittest.TestCase):
    def test_slow_observer_receives_every_frame_and_eof_finalizes_pending_crossing(self):
        seen=[]
        reader=Mock()
        reader.calls={};reader.seconds={'ocr':0.}
        reader.detect_plate.return_value=None
        reader.recognize_candidates.return_value=dict(image=None,plate_text=None,recognition_status='unread',readings=[])
        tracker=SimpleNamespace(yolo_calls=0,flow_frames=0,flow_fallbacks=0)
        def track(n,ts,image):
            seen.append(n)
            time.sleep(.001)
            return TrackedFrame('cam',n,ts,image,[Detection(1,tuple(np.float32(v) for v in (10,10,90,90)),2,.9)])
        tracker.process=track
        event=dict(camera_id='cam',track_id=1,class_id=2,frame_idx=2,ts=.2,direction='entry')
        lines=Mock()
        lines.update.side_effect=lambda f:[event] if f.frame_idx==2 else []
        config=dict(cameras=[dict(id='cam',type='video',source='test')],model_path='test')
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'run'
            with patch.object(replay.cv2,'VideoCapture',Capture), patch.object(replay,'MeasuredReader',return_value=reader), patch.object(replay,'CameraTracker',return_value=tracker), patch.object(replay,'LineDetectorManager',return_value=lines):
                replay.run(config,output)
            summary=json.loads((output/'summary.json').read_text())
            self.assertEqual(seen,list(range(1,21)))
            self.assertEqual(summary['processed_frames'],summary['decodable_frames'])
            self.assertEqual(summary['metadata_frames'],21)  # Census, not metadata, governs completeness.
            self.assertTrue(summary['complete'])
            self.assertEqual(summary['remaining_pending_events'],0)
            self.assertEqual(summary['finalized_vehicle_events'],1)
            self.assertEqual(summary['vehicle_events'][0]['reason'],'eof')
            reader.recognize_candidates.assert_called_once_with([])


if __name__=='__main__': unittest.main()
