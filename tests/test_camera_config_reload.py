import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from computer_vision_v2.reno.models.camera import STATUS_ONLINE, STATUS_OFFLINE
from computer_vision_v2.reno.services.camera_service import CameraService


class CameraConfigReloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'cameras.json'
        self.write_config('old.mp4')
        with patch('computer_vision_v2.reno.services.camera_service.os.path.join',
                   return_value=str(self.path)):
            self.service = CameraService()
        self.listener = Mock()
        self.service.subscribe(self.listener)

    def write_config(self, source):
        self.path.write_text(json.dumps({
            'model_path': 'yolov8n.pt', 'detection_interval': 3,
            'cameras': [{'id': 'cam2', 'type': 'video', 'source': source}],
        }), encoding='utf-8')

    def test_external_source_change_replaces_camera_and_notifies_monitoring(self):
        previous = self.service.get_camera('cam2')
        self.service.set_status('cam2', STATUS_ONLINE)
        self.write_config('new.mp4')
        self.assertTrue(self.service.reload())
        current = self.service.get_camera('cam2')
        self.assertIsNot(current, previous)
        self.assertEqual(current.source, 'new.mp4')
        self.assertEqual(current.status, STATUS_OFFLINE)
        self.listener.assert_called_once_with([current])

    def test_unchanged_config_keeps_live_camera_and_does_not_restart_streams(self):
        previous = self.service.get_camera('cam2')
        self.service.set_status('cam2', STATUS_ONLINE)
        self.assertFalse(self.service.reload())
        self.assertIs(self.service.get_camera('cam2'), previous)
        self.assertEqual(previous.status, STATUS_ONLINE)
        self.listener.assert_not_called()

    def test_partial_write_keeps_last_valid_config_then_retries(self):
        self.path.write_text('{', encoding='utf-8')
        self.assertFalse(self.service.reload())
        self.assertEqual(self.service.get_camera('cam2').source, 'old.mp4')
        self.listener.assert_not_called()
        self.write_config('new.mp4')
        self.assertTrue(self.service.reload())
        self.assertEqual(self.service.get_camera('cam2').source, 'new.mp4')

    def test_deleted_config_keeps_live_cameras(self):
        self.path.unlink()
        self.assertFalse(self.service.reload())
        self.assertEqual(self.service.get_camera('cam2').source, 'old.mp4')
        self.listener.assert_not_called()

    def test_external_camera_removal_notifies_monitoring(self):
        self.path.write_text(json.dumps({'cameras': []}), encoding='utf-8')
        self.assertTrue(self.service.reload())
        self.assertEqual(self.service.get_cameras(), [])
        self.listener.assert_called_once_with([])

    def test_save_preserves_sampling_and_roi(self):
        config=json.loads(self.path.read_text())
        config['plate_sampling']={'capacity':8,'interval':.2}
        config['cameras'][0]['roi']=[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]
        self.path.write_text(json.dumps(config))
        self.service.reload()
        self.service._save()
        saved=json.loads(self.path.read_text())
        self.assertEqual(saved['plate_sampling'],config['plate_sampling'])
        self.assertEqual(saved['cameras'][0]['roi'],config['cameras'][0]['roi'])
