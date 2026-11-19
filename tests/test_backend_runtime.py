"""Control lifecycle and actual frame health, without loading models or a database."""
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, Mock

from computer_vision_v2.runtime.controller import BackendController
from computer_vision_v2.runtime.control import BackendClient, ControlServer, ControlUnavailable
from computer_vision_v2.runtime.health import FrameHealth

CAMERAS = [{'id': 'cam', 'type': 'rtsp', 'source': 'rtsp://secret@camera'}]


def wait_for(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Timed out waiting for backend')


class FakePipeline:
    def __init__(self):
        self.starts = self.stops = 0
        self.failed = []
        self.complete = True

    def start(self):
        self.starts += 1

    def stop(self):
        self.stops += 1
        return self.complete

    def failed_workers(self):
        return self.failed


class BackendLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'cameras.json'
        self.path.write_text(json.dumps({'cameras': CAMERAS}))
        self.pipelines = []
        def factory(*_):
            pipeline = FakePipeline()
            self.pipelines.append(pipeline)
            return pipeline
        self.controller = BackendController(factory, self.path, license_service=Mock(status=lambda: dict(valid=True, code='valid')))
        self.addCleanup(self.controller.close)

    def test_start_is_idempotent_and_restart_reads_new_configuration(self):
        self.controller.command('start')
        wait_for(lambda: self.controller.snapshot()['state'] == 'running')
        for _ in range(5):
            self.controller.command('start')
        self.assertEqual(len(self.pipelines), 1)
        self.assertEqual(self.pipelines[0].starts, 1)
        self.controller.command('stop')
        wait_for(lambda: self.controller.snapshot()['state'] == 'stopped')
        self.path.write_text(json.dumps({'cameras': [dict(CAMERAS[0], id='new')]}))
        self.controller.command('start')
        wait_for(lambda: self.controller.snapshot()['state'] == 'running')
        self.assertEqual(self.controller.snapshot()['cameras'][0]['id'], 'new')
        self.assertEqual(self.pipelines[0].stops, 1)

    def test_stop_during_initialization_cancels_before_start(self):
        entered, release = threading.Event(), threading.Event()
        pipeline = FakePipeline()
        def factory(*_):
            entered.set()
            release.wait(3)
            return pipeline
        self.controller.factory = factory
        self.controller.command('start')
        self.assertTrue(entered.wait(1))
        self.controller.command('stop')
        self.assertEqual(self.controller.snapshot()['state'], 'stopping')
        self.controller.command('start')
        release.set()
        wait_for(lambda: self.controller.snapshot()['state'] == 'stopped')
        self.assertEqual(pipeline.starts, 0)
        self.assertEqual(pipeline.stops, 1)

    def test_failure_visible_and_incomplete_stop_prevents_duplicate_pipeline(self):
        self.controller.command('start')
        wait_for(lambda: self.controller.snapshot()['state'] == 'running')
        self.pipelines[0].failed = ['database_worker']
        self.assertEqual(self.controller.snapshot()['state'], 'error')
        self.pipelines[0].complete = False
        self.controller.command('stop')
        wait_for(lambda: self.controller.snapshot()['state'] == 'error')
        self.controller.command('start')
        self.assertEqual(len(self.pipelines), 1)
        self.pipelines[0].complete = True

    def test_bad_config_is_visible_and_can_be_retried_after_stop(self):
        self.path.write_text('{')
        self.controller.command('start')
        wait_for(lambda: self.controller.snapshot()['state'] == 'error')
        self.assertIn('start_failed', self.controller.snapshot()['error'])
        self.controller.command('stop')
        wait_for(lambda: self.controller.snapshot()['state'] == 'stopped')

    def test_control_authentication_and_bind_prevent_second_owner(self):
        server = ControlServer(self.controller, self.directory.name, 0)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        port = server.server_port
        client = BackendClient(self.directory.name, port)
        self.assertEqual(client.status()['state'], 'stopped')
        with self.assertRaises(OSError):
            ControlServer(self.controller, self.directory.name, port)
        self.assertEqual(client.status()['state'], 'stopped')  # credentials unchanged
        connection = HTTPConnection('127.0.0.1', port)
        connection.request('POST', '/start')
        self.assertEqual(connection.getresponse().status, 403)
        connection.close()
        self.assertEqual(self.controller.state, 'stopped')
        client.start()
        wait_for(lambda: client.status()['state'] == 'running')
        # A new UI client attaches to the existing instance.
        with patch('computer_vision_v2.runtime.control.subprocess.Popen') as spawn:
            self.assertEqual(BackendClient(self.directory.name, port).start()['state'], 'running')
            spawn.assert_not_called()
        client.stop()
        wait_for(lambda: client.status()['state'] == 'stopped')


class FrameHealthTests(unittest.TestCase):
    def test_connected_is_not_processed_stalls_disconnects_and_recovers(self):
        now = [0.]
        health = FrameHealth(CAMERAS, clock=lambda: now[0])
        health.received('cam')
        self.assertEqual(health.snapshot()[0]['state'], 'waiting')
        now[0] = 11
        health.received('cam')
        self.assertEqual(health.snapshot()[0]['state'], 'stalled')
        health.processed('cam')
        self.assertEqual(health.snapshot()[0]['state'], 'processing')
        health.connection('cam', 'disconnected')
        with self.assertLogs('computer_vision_v2.runtime.health', level='ERROR') as logs:
            self.assertEqual(health.snapshot()[0]['state'], 'disconnected')
            health.snapshot()
        self.assertEqual(len(logs.output), 1)
        health.received('cam')
        health.processed('cam')
        self.assertEqual(health.snapshot()[0]['processed'], 2)
        now[0] = 22
        snapshot = health.snapshot()[0]
        self.assertEqual(snapshot['state'], 'no_frames')
        self.assertEqual(snapshot['fps'], 0)
        self.assertNotIn('secret', json.dumps(snapshot))

    def test_video_end_is_not_camera_disconnect(self):
        health = FrameHealth(CAMERAS)
        health.connection('cam', 'ended')
        self.assertEqual(health.snapshot()[0]['state'], 'ended')


@unittest.skipIf(os.name == 'nt', 'POSIX detach smoke test; Windows launch flags tested separately')
class DetachedBackendTests(unittest.TestCase):
    def test_backend_survives_launcher_exit_and_new_client_can_stop_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'cameras.json'
            config.write_text(json.dumps({'cameras': CAMERAS}))
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            worker = f'''
from computer_vision_v2.runtime.control import serve
from computer_vision_v2.runtime.controller import BackendController
class Pipeline:
    def start(self): pass
    def stop(self): return True
    def failed_workers(self): return []
from unittest.mock import Mock
serve(BackendController(lambda *_: Pipeline(), {str(config)!r}, license_service=Mock(status=lambda: dict(valid=True, code='valid'))))
'''
            launcher = f'''
from unittest.mock import patch, Mock
import subprocess, sys
from computer_vision_v2.runtime.control import BackendClient
original = subprocess.Popen
def spawn(command, **options):
    assert options['start_new_session'] is True
    return original([sys.executable, '-c', {worker!r}], **options)
with patch('computer_vision_v2.runtime.control.subprocess.Popen', side_effect=spawn):
    BackendClient().start()
'''
            env = dict(os.environ, PLAKINO_RUNTIME_DIR=directory, PLAKINO_CONTROL_PORT=str(port))
            client = BackendClient(directory, port)
            pid = None
            try:
                subprocess.run([sys.executable, '-c', launcher], env=env, check=True, timeout=15)
                wait_for(lambda: client.status()['state'] == 'running')
                pid = client.request()['pid']
                self.assertNotEqual(pid, os.getpid())
                client.stop()
                wait_for(lambda: client.status()['state'] == 'stopped')
            finally:
                if pid is None:
                    pid = client.status().get('pid')
                if pid is not None:
                    os.kill(pid, signal.SIGTERM)
                    wait_for(lambda: client.status()['state'] == 'unavailable')
