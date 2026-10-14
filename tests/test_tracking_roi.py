import unittest
from unittest.mock import patch
import numpy as np

from computer_vision_v2.tracking.tracker import CameraTracker
from computer_vision_v2.tracking.frame_info import Detection
from reno.models.camera import Camera


class RoiTests(unittest.TestCase):
    def test_crop_mask_restore_and_keep_original_frame(self):
        roi = [[.2,.2],[.8,.2],[.2,.8]]
        with patch('computer_vision_v2.tracking.tracker.YOLO'):
            tracker = CameraTracker('cam','unused',1,roi)
        original = np.full((101,101,3),100,np.uint8)
        with patch.object(tracker,'_detect',return_value=[
            Detection(1,(0,0,20,20),2,.9), Detection(2,(40,40,60,60),2,.9)
        ]) as detect:
            result = tracker.process(1,0.,original)
        given = detect.call_args.args[0]
        self.assertEqual(given.shape,(61,61,3))
        self.assertTrue((given[-1,-1]==0).all())
        self.assertTrue((original==100).all())
        self.assertIs(result.image,original)
        self.assertEqual(len(result.detections),1)
        self.assertEqual(result.detections[0].bbox,(20,20,40,40))

    def test_camera_roundtrip_preserves_roi(self):
        roi=[[0.,0.],[1.,0.],[1.,1.]]
        camera=Camera('cam',roi=roi)
        self.assertEqual(Camera.from_dict(camera.to_dict()).roi,roi)

    def test_invalid_roi_rejected_before_loading_model(self):
        for roi in ([], [[0,0],[1,1]], [[0,0],[2,0],[1,1]], [[0,0],[.5,.5],[1,1]]):
            with patch('computer_vision_v2.tracking.tracker.YOLO') as model:
                with self.assertRaises(ValueError):
                    CameraTracker('cam','unused',roi=roi)
                model.assert_not_called()
