"""Gate registration transaction and bounded, real-frame connection checks."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from reno.models.camera import Camera
from reno.services.camera_setup_service import register_and_check


class CameraSetupTests(unittest.TestCase):
    def setUp(self):
        self.db = patch('reno.services.camera_setup_service.get_connection')
        self.connect = self.db.start()
        self.addCleanup(self.db.stop)
        self.cursor = self.connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.side_effect = [None, ('ورودی',)]
        self.probe = patch('reno.services.camera_setup_service.subprocess.run')
        self.run = self.probe.start()
        self.addCleanup(self.probe.stop)
        self.run.return_value.returncode = 0
        self.camera = Camera(id='دوربین ورودی', source='rtsp://127.0.0.1/live')

    def test_persian_names_registered_before_probe_and_retained(self):
        def probe(*args, **kwargs):
            self.connect.return_value.__exit__.assert_called_once()
            return subprocess.CompletedProcess(args, 0)
        self.run.side_effect = probe
        result = register_and_check(self.camera, 'ورودی')
        self.assertTrue(result.success)
        self.assertEqual(self.camera.gate_id, 'ورودی')
        self.cursor.execute.assert_any_call('INSERT INTO gate (id) VALUES (%s) ON CONFLICT (id) DO NOTHING', ('ورودی',))
        self.assertEqual(Camera.from_dict(self.camera.to_dict()).gate_id, 'ورودی')

    def test_database_failure_does_not_probe(self):
        self.connect.side_effect = OSError('unavailable')
        result = register_and_check(self.camera, 'ورودی')
        self.assertFalse(result.success)
        self.assertFalse(result.registered)
        self.run.assert_not_called()

    def test_failed_or_timed_out_probe_keeps_registration_explicit(self):
        for failure in (False, True):
            with self.subTest(timeout=failure):
                self.cursor.fetchone.side_effect = [None, ('ورودی',)]
                self.run.side_effect = subprocess.TimeoutExpired('probe', 12) if failure else None
                self.run.return_value.returncode = 1
                result = register_and_check(self.camera, 'ورودی')
                self.assertFalse(result.success)
                self.assertTrue(result.registered)
                self.assertIn('ثبت شدند', result.message)

    def test_existing_camera_cannot_be_reassigned_to_another_gate(self):
        self.cursor.fetchone.side_effect = [('different-gate',)]
        self.assertFalse(register_and_check(self.camera, 'ورودی').success)
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.run.assert_not_called()

    def test_legacy_gate_mapping_is_preserved(self):
        self.cursor.fetchone.side_effect = [('ورودی',), ('ورودی',)]
        self.assertTrue(register_and_check(self.camera, 'ورودی').success)
        self.assertEqual(self.camera.gate_id, 'ورودی')

    def test_missing_gate_invalid_rtsp_and_missing_video_do_not_register(self):
        self.assertFalse(register_and_check(self.camera, '').success)
        for source in ('https://example.com', 'rtsp://[bad'):
            self.camera.source = source
            self.assertFalse(register_and_check(self.camera, 'ورودی').success)
        self.camera.source_type = 'video'
        self.camera.source = '/missing/file.mp4'
        self.assertFalse(register_and_check(self.camera, 'ورودی').success)
        self.connect.assert_not_called()

    def test_real_video_probe_reads_a_frame(self):
        import cv2
        import numpy as np
        from reno.services.source_probe import main
        from io import StringIO
        import json
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'clip.avi')
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'MJPG'), 25, (64, 48))
            self.assertTrue(writer.isOpened())
            writer.write(np.zeros((48,64,3), dtype=np.uint8))
            writer.release()
            with patch('sys.stdin', StringIO(json.dumps({'source': path, 'type': 'video'}))):
                self.assertEqual(main(), 0)
            Path(path).write_bytes(b'not a video')
            with patch('sys.stdin', StringIO(json.dumps({'source': path, 'type': 'video'}))):
                self.assertEqual(main(), 1)

    def test_equal_names_are_rejected_before_database_or_probe(self):
        for name in ('دوربین ورودی', ' دوربین ورودی '):
            result = register_and_check(self.camera, name)
            self.assertFalse(result.success)
            self.assertIn('نباید یکسان', result.message)
        self.connect.assert_not_called()
        self.run.assert_not_called()

    def test_gate_name_is_preserved_without_prefix_interpretation(self):
        self.cursor.fetchone.side_effect = [None, ('gate:نام انتخابی',)]
        self.assertTrue(register_and_check(self.camera, 'gate:نام انتخابی').success)
        self.assertEqual(self.camera.gate_id, 'gate:نام انتخابی')

    def test_registration_does_not_probe_offline_camera(self):
        from reno.services.camera_setup_service import register_camera
        self.camera.source = 'rtsp://192.0.2.1/unavailable'
        result = register_camera(self.camera, 'ورودی')
        self.assertTrue(result.success)
        self.assertTrue(result.registered)
        self.run.assert_not_called()

    def test_connection_check_does_not_write_database(self):
        from reno.services.camera_setup_service import check_connection
        result = check_connection(self.camera)
        self.assertTrue(result.success)
        self.connect.assert_not_called()
        self.run.assert_called_once()
