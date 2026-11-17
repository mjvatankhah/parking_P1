"""Non-blocking JSON logging with bounded rotation and credential redaction."""
import atexit
import copy
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import re
import threading

_URL = re.compile(r'(?i)\b(?:rtsp|rtsps|https?)://[^\s\x27\x22<>]+')
_SECRET = re.compile(r'(?i)(password|passwd|token|secret|authorization)(\s*[:=]\s*)([^\s,;]+)')
_FIELDS = ('event', 'camera_id', 'track_id', 'passage_id', 'event_id', 'stage',
           'duration_ms', 'status', 'candidates', 'readings', 'metrics', 'queues', 'dropped_logs')


def redact(text):
    return _SECRET.sub(r'\1\2[REDACTED]', _URL.sub('[REDACTED_URL]', str(text)))


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = dict(time=datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                    level=record.levelname, module=record.name, worker=record.threadName,
                    process=record.process, message=redact(record.getMessage()))
        for key in _FIELDS:
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data['exception'] = redact(self.formatException(record.exc_info))
        # Scrub structured context too. Only explicitly supported fields are emitted.
        def clean(value):
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [clean(item) for item in value]
            return redact(value) if isinstance(value, str) else value
        return json.dumps(clean(data), ensure_ascii=False, default=str)


class QueueSink(logging.Handler):
    def __init__(self, destination):
        super().__init__()
        self.destination = destination
        self.dropped = 0

    def emit(self, record):
        try:
            self.destination.put_nowait(copy.copy(record))
        except queue.Full:
            self.dropped += 1

    def take_dropped(self):
        with self.lock:
            count, self.dropped = self.dropped, 0
            return count


class LogRuntime:
    def __init__(self, directory, role, level=logging.INFO, capacity=2000,
                 max_bytes=10 * 1024 * 1024, backups=5):
        # UI and pipeline can be separate processes: each owns its rotating files.
        directory = Path(directory) / f'{role}-{os.getpid()}'
        directory.mkdir(parents=True, exist_ok=True)
        self.queue = queue.Queue(maxsize=capacity)
        self.sink = QueueSink(self.queue)
        self.handlers = []
        for name, threshold in [('app.jsonl', level), ('error.jsonl', logging.ERROR)]:
            handler = RotatingFileHandler(directory / name, maxBytes=max_bytes,
                                          backupCount=backups, encoding='utf-8')
            handler.setLevel(threshold)
            handler.setFormatter(JsonFormatter())
            self.handlers.append(handler)
        self.bindings = []
        for name in ('computer_vision_v2', 'plakino_ui', 'plakino_logging'):
            logger = logging.getLogger(name)
            self.bindings.append((logger, logger.level))
            logger.setLevel(level)
            logger.addHandler(self.sink)
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._write, name='log-writer', daemon=True)
        self.thread.start()

    def _output(self, record):
        for handler in self.handlers:
            if record.levelno >= handler.level:
                handler.handle(record)

    def _write(self):
        try:
            while not self.stopping.is_set() or not self.queue.empty():
                try:
                    record = self.queue.get(timeout=.2)
                except queue.Empty:
                    continue
                try:
                    self._output(record)
                    dropped = self.sink.take_dropped()
                    if dropped:
                        warning = logging.LogRecord('plakino_logging', logging.WARNING, '', 0,
                                                    'Logging queue overflow', (), None)
                        warning.event, warning.dropped_logs = 'logs_dropped', dropped
                        self._output(warning)
                finally:
                    self.queue.task_done()
        finally:
            for handler in self.handlers:
                handler.close()

    def close(self):
        for logger, level in self.bindings:
            logger.removeHandler(self.sink)
            logger.setLevel(level)
        self.stopping.set()
        self.thread.join(timeout=3)


_runtime = None
_lock = threading.Lock()


def configure_logging(role='app', directory=None, level=logging.INFO):
    global _runtime
    with _lock:
        if _runtime is None:
            directory = directory or Path(__file__).resolve().parents[2] / 'logs'
            _runtime = LogRuntime(directory, role, level)
    return _runtime


def shutdown_logging():
    global _runtime
    with _lock:
        if _runtime is not None:
            _runtime.close()
            _runtime = None


atexit.register(shutdown_logging)
