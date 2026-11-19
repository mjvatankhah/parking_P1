"""Loopback-only control channel and a detached, single-instance backend host."""
import argparse
import hmac
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time

from .controller import BackendController

logger = logging.getLogger(__name__)
DEFAULT_PORT = 47653


def runtime_directory():
    override = os.environ.get('PLAKINO_RUNTIME_DIR')
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share')))
    return Path(override) if override else base / 'plakino' / 'runtime'


class ControlUnavailable(RuntimeError):
    pass


class BackendClient:
    def __init__(self, directory=None, port=None, timeout=2):
        self.directory = Path(directory) if directory is not None else runtime_directory()
        self.port = int(port if port is not None else os.environ.get('PLAKINO_CONTROL_PORT', DEFAULT_PORT))
        self.timeout = timeout

    def request(self, action='status', payload=None):
        connection = HTTPConnection('127.0.0.1', self.port, timeout=self.timeout)
        try:
            token = (self.directory / 'control.token').read_text(encoding='ascii')
            connection.request('GET' if action in ('status', 'license-request') else 'POST', '/' + action,
                               body=json.dumps(payload).encode() if payload is not None else None,
                               headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            response = connection.getresponse()
            if response.status != 200:
                raise ControlUnavailable('Backend control rejected the request')
            result = json.loads(response.read(1024 * 1024))
            if result.get('protocol') != 1:
                raise ControlUnavailable('Incompatible backend control')
            return result
        except (OSError, ValueError, HTTPException) as exc:
            raise ControlUnavailable('Backend control unavailable') from exc
        finally:
            connection.close()

    def status(self):
        try:
            return self.request()
        except ControlUnavailable:
            return dict(state='unavailable', error='control_unavailable', cameras=[])

    def ensure_host(self):
        try:
            return self.request()
        except ControlUnavailable:
            pass
        # No pipes and no parent-exit hooks: closing the UI leaves the host alive.
        env = os.environ.copy()
        env['PLAKINO_RUNTIME_DIR'] = str(self.directory)
        env['PLAKINO_CONTROL_PORT'] = str(self.port)
        source_root = str(Path(__file__).resolve().parents[2])
        env['PYTHONPATH'] = os.pathsep.join(filter(None, [source_root, env.get('PYTHONPATH')]))
        options = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, close_fds=True, env=env,
                       cwd=str(Path(__file__).resolve().parents[3]))
        if os.name == 'nt':
            options['creationflags'] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options['start_new_session'] = True
        process = subprocess.Popen([sys.executable, '-m', 'computer_vision_v2.runtime.control'], **options)
        # Reap a duplicate/failed launcher without making UI shutdown wait for the host.
        threading.Thread(target=process.wait, name='backend-reaper', daemon=True).start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                return self.request()
            except ControlUnavailable:
                time.sleep(.1)
        raise ControlUnavailable('Backend did not become available; check control port and logs')

    def start(self):
        self.ensure_host()
        return self.request('start')

    def license_request(self):
        self.ensure_host()
        return self.request('license-request')['request']

    def install_license(self, document):
        self.ensure_host()
        return self.request('license-install', document)['license']

    def stop(self):
        return self.request('stop')


class ControlServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, controller, directory, port):
        self.controller = controller
        self.token = secrets.token_urlsafe(32)
        # Bind before writing credentials: concurrent launches cannot replace the owner's token.
        super().__init__(('127.0.0.1', port), ControlHandler)
        try:
            directory = Path(directory)
            directory.mkdir(parents=True, mode=0o700, exist_ok=True)
            temporary = directory / f'control-{os.getpid()}.tmp'
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='ascii') as stream:
                stream.write(self.token)
            temporary.replace(directory / 'control.token')
        except Exception:
            self.server_close()
            raise


class ControlHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def log_message(self, *_args):
        pass

    def do_GET(self):
        self._handle(self.path.lstrip('/'))

    def do_POST(self):
        self._handle(self.path.lstrip('/'))

    def _handle(self, action):
        expected = 'Bearer ' + self.server.token
        if self.headers.get('Origin') or not hmac.compare_digest(self.headers.get('Authorization', ''), expected):
            self.send_error(403)
            return
        allowed = ('status', 'license-request') if self.command == 'GET' else ('start', 'stop', 'license-install')
        if self.path != '/' + action or action not in allowed:
            self.send_error(404)
            return
        try:
            if action == 'license-install':
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 65536:
                    raise ValueError('Invalid length')
                document = json.loads(self.rfile.read(length))
                result = {'license': self.server.controller.install_license(document)}
            elif action == 'license-request':
                result = {'request': self.server.controller.license_request()}
            else:
                result = (self.server.controller.snapshot() if action == 'status'
                          else self.server.controller.command(action))
        except (ValueError, OSError, TypeError):
            self.send_error(400)
            return
        body = json.dumps(result | {'protocol': 1, 'pid': os.getpid()}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)


def serve(controller=None, directory=None, port=None):
    from plakino_logging import configure_logging, shutdown_logging
    configure_logging('pipeline')
    controller = controller or BackendController()
    client = BackendClient(directory, port)
    # A bind failure exits; it must never start an uncontrolled second pipeline.
    try:
        server = ControlServer(controller, client.directory, client.port)
    except OSError:
        logger.exception('Cannot open backend control', extra={'event': 'backend_control_failed'})
        shutdown_logging()
        raise SystemExit(1)
    stopping = threading.Event()
    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.signal(sig, lambda *_: stopping.set())
    server.timeout = .5
    try:
        logger.info('Backend control ready', extra={'event': 'backend_control_ready'})
        while not stopping.is_set():
            server.handle_request()
            controller.snapshot()  # Health transitions are logged even with no UI connected.
    finally:
        server.server_close()
        controller.close()
        shutdown_logging()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description='Plakino backend control')
    parser.add_argument('action', nargs='?', choices=('serve', 'start', 'stop', 'status'), default='serve')
    args = parser.parse_args()
    if args.action == 'serve':
        serve()
    else:
        client = BackendClient()
        print(json.dumps(getattr(client, args.action)(), ensure_ascii=False))


if __name__ == '__main__':
    main()
