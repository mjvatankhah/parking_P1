import unittest
from unittest.mock import MagicMock, patch

from computer_vision_v2.database.camera_registry import CameraRegistrationError, prepare_camera
from computer_vision_v2.database import queries
from computer_vision_v2.streaming.Cameras_Manager import CameraManager


class CameraRegistrationTests(unittest.TestCase):
    camera = {"id": "cam-1", "source": "rtsp://camera", "type": "rtsp", "dir": "entry"}

    def connection(self, gate):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = gate
        return connection, cursor

    def test_existing_distinct_gate_id_is_preserved(self):
        connection, cursor = self.connection(("north-gate",))
        with patch("computer_vision_v2.database.camera_registry.get_connection") as connect:
            connect.return_value.__enter__.return_value = connection
            prepare_camera(self.camera)
        self.assertEqual(cursor.execute.call_count, 2)
        cursor.execute.assert_any_call(queries.SELECT_CAMERA_GATE, ("cam-1",))
        cursor.execute.assert_any_call(
            queries.UPDATE_CAMERA_SETTINGS,
            ("rtsp://camera", "rtsp", "entry", "cam-1"),
        )

    def test_missing_or_same_id_gate_blocks_only_that_camera(self):
        for gate in (None, ("cam-1",)):
            with self.subTest(gate=gate):
                connection, cursor = self.connection(gate)
                with patch("computer_vision_v2.database.camera_registry.get_connection") as connect:
                    connect.return_value.__enter__.return_value = connection
                    with self.assertRaises(CameraRegistrationError):
                        prepare_camera(self.camera)
                self.assertEqual(cursor.execute.call_count, 1)

    def test_bad_camera_does_not_stop_other_camera(self):
        cameras = [dict(self.camera), dict(self.camera, id="cam-2")]
        manager = CameraManager({"model_path": "unused", "cameras": cameras})
        with patch("computer_vision_v2.streaming.Cameras_Manager.prepare_camera") as prepare, \
             patch("computer_vision_v2.streaming.Cameras_Manager.StreamManager") as stream_type:
            prepare.side_effect = [CameraRegistrationError("missing gate"), None]
            with self.assertLogs("computer_vision_v2.streaming.Cameras_Manager", level="ERROR"):
                manager.start_all()
        self.assertEqual(list(manager.streams), ["cam-2"])
        stream_type.return_value.start.assert_called_once()
