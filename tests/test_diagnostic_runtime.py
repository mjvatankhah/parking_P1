from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import json
import unittest
from unittest.mock import patch

from computer_vision_v2.ocr_worker.diagnostic_runtime import runtime_by_camera


class DiagnosticRuntimeTests(unittest.TestCase):
    def test_snapshot_records_effective_settings_and_hashes_without_source_credentials(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'plate.onnx').write_bytes(b'model')
            reader = NS(detector_path=root/'plate.onnx', _fallback_path=None,
                ocr_model_directory=root, det_size=640, conf_thr=.35,
                ocr=NS(_model=NS(preprocessor=NS(image_processor=NS(config=NS(
                    size=[384,32], mirror=True, gray_scale=True, mean=[.5], std=[.2], rescale=1/255, resample=None))))))
            pool = NS(interval=.1, near=.09, stale=5, exit_delay=.75, sample_capacity=50, vehicle_margin=.2)
            config = {'model_path':str(root/'vehicle.onnx'), 'cameras':[
                {'id':'gate', 'type':'rtsp', 'source':'rtsp://private-user:private-secret@host/live',
                 'roi':[[0,0],[1,0],[1,1]], 'line':[[.1,.2],[.3,.4]]}]}
            with patch('computer_vision_v2.ocr_worker.diagnostic_runtime.version', return_value='local'):
                snapshot = runtime_by_camera(config, reader, pool)
            serialized = json.dumps(snapshot)
            self.assertNotIn('private-secret', serialized)
            self.assertNotIn('private-user', serialized)
            self.assertNotIn('source', snapshot['gate']['camera'])
            self.assertEqual(snapshot['gate']['ocr_preprocessing']['size'], [384,32])
            self.assertEqual(len(snapshot['gate']['model_files'][0]['sha256']), 64)
            config['cameras'][0]['roi'][0][0] = .5
            self.assertEqual(snapshot['gate']['camera']['roi'][0][0], 0)
