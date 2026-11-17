import json
import logging
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch

from plakino_logging.runtime import LogRuntime, QueueSink
from plakino_logging.metrics import FrameMetrics


class LoggingTests(unittest.TestCase):
    def test_json_rotation_errors_and_redaction(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = LogRuntime(folder, 'test', max_bytes=1200, backups=2)
            logger = logging.getLogger('computer_vision_v2.test')
            try:
                for _ in range(30):
                    logger.info('frame summary')
                try:
                    raise ValueError('rtsp://user:secret@camera/path password=hidden')
                except ValueError:
                    logger.exception('failure', extra={'event': 'failed', 'passage_id': 'abc'})
            finally:
                runtime.close()
            files = list(Path(folder).rglob('app.jsonl*'))
            self.assertLessEqual(len(files), 3)
            errors = list(Path(folder).rglob('error.jsonl'))[0].read_text()
            self.assertNotIn('user:secret', errors)
            self.assertNotIn('hidden', errors)
            record = json.loads(errors)
            self.assertEqual(record['passage_id'], 'abc')
            self.assertIn('ValueError', record['exception'])
            for file in files:
                for line in file.read_text().splitlines():
                    json.loads(line)

    def test_full_queue_never_waits_and_counts_losses(self):
        sink = QueueSink(queue.Queue(maxsize=1))
        record = logging.makeLogRecord({'msg': 'test'})
        sink.handle(record)
        sink.handle(record)
        self.assertEqual(sink.take_dropped(), 1)
        self.assertEqual(sink.take_dropped(), 0)

    def test_frame_replacement_rate_and_window_reset(self):
        with patch('plakino_logging.metrics.time.monotonic', side_effect=[0, 10, 30, 60]):
            metrics = FrameMetrics('cam', 'capture')
            metrics.add(received=60, replaced=10)
            with self.assertLogs('plakino_logging.metrics') as logs:
                metrics.add(received=40, replaced=20)
                metrics.add(received=10, replaced=0)
        self.assertEqual(logs.records[0].metrics['replacement_percent'], 30)
        self.assertEqual(logs.records[1].metrics['replacement_percent'], 0)
