"""Serialize lifecycle changes while status requests remain responsive."""
import logging
from pathlib import Path
import json
import threading
import time

from plakino_license import LicenseService

from .health import FrameHealth

logger = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).resolve().parents[2] / 'plakino_ui' / 'data' / 'cameras.json'


def build_pipeline(health, config):
    from computer_vision_v2.main_v2 import Pipeline
    return Pipeline(config, health=health)


class BackendController:
    def __init__(self, factory=build_pipeline, config_path=CONFIG_PATH, license_service=None):
        self.license_service = license_service if license_service is not None else LicenseService()
        self.license_status = dict(valid=False, code="missing")
        self._license_checked = float("-inf")
        self.factory = factory
        self.config_path = config_path
        self.lock = threading.RLock()
        self.pipeline = None
        self.health = None
        self.state = 'stopped'
        self.error = None
        self.operation = None
        self.cancel_start = threading.Event()

    def command(self, action):
        with self.lock:
            if action == 'start':
                if self.state != 'stopped':
                    return self.snapshot()
                self._check_license(force=True)
                if not self.license_status['valid']:
                    return self.snapshot()
                self.state, self.error = 'starting', None
                self.health = None
                self.cancel_start.clear()
                target = self._start
            elif action == 'stop':
                if self.state == 'starting':
                    self.cancel_start.set()
                    self.state = 'stopping'
                    return self.snapshot()
                if self.state in ('stopped', 'stopping'):
                    return self.snapshot()
                self.state = 'stopping'
                target = self._stop
            else:
                raise ValueError('Unknown action')
            self.operation = threading.Thread(target=target, name=f'backend-{action}', daemon=True)
            self.operation.start()
            return self.snapshot()

    def _start(self):
        try:
            config = json.loads(Path(self.config_path).read_text(encoding='utf-8'))
            if not config.get('cameras'):
                raise ValueError('No configured cameras')
            health = FrameHealth(config['cameras'])
            with self.lock:
                self.health = health
            pipeline = self.factory(health, config)
            with self.lock:
                self.pipeline = pipeline
            if self.cancel_start.is_set():
                self._stop()
                return
            with self.lock:
                self._check_license(force=True)
                if not self.license_status["valid"]:
                    self.cancel_start.set()
            if self.cancel_start.is_set():
                self._stop()
                return
            pipeline.start()
            with self.lock:
                cancelled = self.cancel_start.is_set()
                if not cancelled:
                    self.state = 'running'
                    logger.info('Backend running', extra={'event': 'backend_running'})
            if cancelled:
                self._stop()
        except Exception as exc:
            logger.exception('Backend startup failed', extra={'event': 'backend_start_failed'})
            # Retain a failed pipeline until cleanup is confirmed; never run a second one over it.
            with self.lock:
                self.error = f'start_failed:{type(exc).__name__}'
                self.state = 'stopping' if self.pipeline is not None else 'error'
            if self.pipeline is not None:
                self._stop(preserve_error=True)

    def _stop(self, preserve_error=False):
        try:
            pipeline = self.pipeline
            if pipeline is not None and pipeline.stop() is False:
                raise RuntimeError('Shutdown incomplete')
            with self.lock:
                self.pipeline = None
                self.state = 'error' if preserve_error else 'stopped'
                if not preserve_error:
                    self.error = None
            logger.info('Backend stopped', extra={'event': 'backend_stopped'})
        except Exception as exc:
            logger.exception('Backend shutdown failed', extra={'event': 'backend_stop_failed'})
            with self.lock:
                self.state, self.error = 'error', f'stop_failed:{type(exc).__name__}'

    def _check_license(self, force=False):
        checked = force or time.monotonic() - self._license_checked >= 5
        if checked:
            previous = self.license_status.get('code')
            self.license_status = self.license_service.status()
            if previous != self.license_status.get('code'):
                logger.info('License status: %s', self.license_status.get('code'),
                            extra={'event': 'license_status_changed'})
            self._license_checked = time.monotonic()
        needs_stop = self.state in ('starting', 'running') or (
            checked and self.state == 'error' and self.pipeline is not None
            and (self.operation is None or not self.operation.is_alive()))
        if not self.license_status['valid'] and needs_stop:
            self.command('stop')

    def license_request(self):
        with self.lock:
            return self.license_service.request()

    def install_license(self, document):
        with self.lock:
            result = self.license_service.install(document)
            self._check_license(force=True)
            return result

    def snapshot(self):
        with self.lock:
            self._check_license()
            if self.state == 'running' and self.pipeline is not None:
                failed = self.pipeline.failed_workers()
                if failed:
                    self.state, self.error = 'error', 'worker_failed:' + ','.join(failed)
                    logger.error('Backend workers stopped: %s', failed, extra={'event': 'backend_worker_failed'})
            return dict(state=self.state, error=self.error, license=self.license_status,
                        cameras=self.health.snapshot() if self.health is not None else [])

    def close(self):
        self.command('stop')
        operation = self.operation
        if operation is not None:
            operation.join()
