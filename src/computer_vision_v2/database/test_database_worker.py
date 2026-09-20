import queue
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
        self.assertEqual(params, ("cam2", None, "entry", 0, 0.87, None))
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


if __name__ == "__main__":
    unittest.main()
