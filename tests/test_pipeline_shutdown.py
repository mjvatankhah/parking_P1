"""A stalled stage must not hold shutdown forever."""

import queue
import unittest
from unittest.mock import Mock

from computer_vision_v2.main_v2 import Pipeline
from computer_vision_v2.workers.queueing import offer_event


class PipelineShutdownTests(unittest.TestCase):
    def test_full_event_queue_reports_failure_instead_of_blocking(self):
        destination = queue.Queue(maxsize=1)
        destination.put(object())
        with self.assertLogs("computer_vision_v2.workers.queueing", level="ERROR"):
            self.assertFalse(offer_event(destination, {"camera_id": "cam", "track_id": 1}, "db"))
        self.assertEqual(destination.qsize(), 1)

    def test_dead_worker_does_not_block_stop_on_full_input_queue(self):
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.running = True
        pipeline._dispatch_thread = None
        pipeline.camera_manager = Mock()
        pipeline.preview = Mock()
        full_queue = queue.Queue(maxsize=1)
        full_queue.put(object())
        dead_worker = Mock()
        dead_worker.is_alive.return_value = False
        pipeline._worker_stages = [(full_queue, dead_worker)]

        with self.assertLogs("computer_vision_v2.main_v2", level="ERROR"):
            pipeline.stop()

        dead_worker.join.assert_not_called()
        pipeline.camera_manager.stop_all.assert_called_once()
        pipeline.preview.stop.assert_called_once()
