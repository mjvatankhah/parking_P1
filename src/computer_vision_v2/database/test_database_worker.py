import queue
from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

from computer_vision_v2.database import database_worker as module


class DatabaseWorkerTests(unittest.TestCase):
    def run_worker(self, item, fetch_results):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.side_effect = fetch_results
        items = queue.Queue()
        items.put(item)
        items.put(None)
        with patch.object(module, "get_connection", return_value=connection):
            module.database_worker(items, lambda: True)
        return connection, cursor

    def test_event_without_plate_skips_vehicle_and_session(self):
        connection, cursor = self.run_worker({
            "camera_id": "cam2", "class_id": 0, "direction": "entry",
            "plate_text": None, "confidence": 0.87, "image_path": None,
        }, [(11,)])
        queries = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(len(queries), 1)
        self.assertIn("INSERT INTO event", queries[0])
        self.assertNotIn("INSERT INTO vehicle ", queries[0])
        self.assertNotIn("vehicle_session", queries[0])
        params = cursor.execute.call_args.args[1]
        self.assertEqual(params[:6], ("cam2", None, "entry", 0, 0.87, None))
        self.assertIsNotNone(params[6].tzinfo)
        self.assertEqual(params[7:], ('unread', '[]'))
        connection.commit.assert_called_once()

    def test_event_with_plate_creates_vehicle_and_entry_session(self):
        connection, cursor = self.run_worker({
            "camera_id": "cam2", "class_id": 2, "direction": "entry",
            "plate_text": "12ب345", "confidence": 0.94,
            "image_path": "plate.jpg",
        }, [(12,), None])
        queries = "\n".join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn("INSERT INTO vehicle ", queries)
        self.assertIn("INSERT INTO event", queries)
        self.assertIn("INSERT INTO vehicle_session", queries)
        connection.commit.assert_called_once()

    def test_uncertain_text_never_opens_vehicle_session(self):
        connection, cursor = self.run_worker({
            'camera_id':'cam2', 'class_id':2, 'direction':'entry',
            'plate_text':'58م87245', 'confidence':.9, 'image_path':None,
            'recognition_status':'uncertain', 'readings':[],
        }, [(12,)])
        self.assertEqual(cursor.execute.call_count,1)
        self.assertIsNone(cursor.execute.call_args.args[1][1])
        self.assertEqual(cursor.execute.call_args.args[1][7],'uncertain')

    def test_connection_failure_reopens_for_next_event(self):
        item = {
            "camera_id": "cam2", "class_id": 0, "direction": "entry",
            "plate_text": None, "confidence": 0.87, "image_path": None,
        }
        items = queue.Queue()
        items.put(dict(item))
        items.put(dict(item))
        items.put(None)
        broken = MagicMock()
        broken.cursor.return_value.execute.side_effect = OSError("connection lost")
        recovered = MagicMock()
        recovered.cursor.return_value.fetchone.return_value = (17,)
        with patch.object(module, "get_connection", side_effect=[broken, recovered]) as connect:
            with self.assertLogs("computer_vision_v2.database.database_worker", level="ERROR"):
                module.database_worker(items, lambda: True)
        self.assertEqual(connect.call_count, 2)
        broken.rollback.assert_called_once()
        recovered.commit.assert_called_once()
        self.assertEqual(items.unfinished_tasks, 0)

    def test_system_time_is_explicit_for_event_and_entry_session(self):
        stamp = datetime(2026, 10, 10, 10, 30, tzinfo=timezone.utc)
        with patch.object(module, 'datetime') as clock:
            clock.now.return_value.astimezone.return_value = stamp
            _, cursor = self.run_worker({
                'camera_id': 'cam2', 'class_id': 2, 'direction': 'entry',
                'plate_text': 'test-plate', 'confidence': .9, 'image_path': None,
            }, [(12,), None])
        cursor.execute.assert_any_call(module.queries.INSERT_EVENT,
            ('cam2', 'test-plate', 'entry', 2, .9, None, stamp, 'read', '[]'))
        cursor.execute.assert_any_call(module.queries.INSERT_SESSION,
                                      ('test-plate', 12, stamp))

    def test_system_time_is_shared_with_session_close(self):
        stamp = datetime(2026, 10, 10, 11, 30, tzinfo=timezone.utc)
        with patch.object(module, 'datetime') as clock:
            clock.now.return_value.astimezone.return_value = stamp
            _, cursor = self.run_worker({
                'camera_id': 'cam2', 'class_id': 2, 'direction': 'exit',
                'plate_text': 'test-plate', 'confidence': .9, 'image_path': None,
            }, [(13,), (7,)])
        cursor.execute.assert_any_call(module.queries.UPDATE_CLOSE_SESSION,
                                      (13, stamp, 7))


if __name__ == "__main__":
    unittest.main()
