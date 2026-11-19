"""Real signatures, durable time history and backend enforcement, without ML/DB."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from plakino_license.service import LicenseService, canonical
from computer_vision_v2.runtime.controller import BackendController
from computer_vision_v2.runtime.control import BackendClient, ControlServer
from scripts.issue_license import issue


class OfflineLicenseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = Ed25519PrivateKey.generate()
        self.public = self.root / 'public.pem'
        self.public.write_bytes(self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        components = dict(installation='a' * 64, product='b' * 64)
        self.device = dict(version=1, product='plakino', components=components,
                           device_id=hashlib.sha256(canonical(components)).hexdigest())
        self.now = [1800000000.]
        self.mono = [100.]
        self.service = self.new_service()

    def new_service(self):
        return LicenseService(self.root / 'state', self.public, lambda: self.device,
                              wall=lambda: self.now[0], monotonic=lambda: self.mono[0])

    def license(self, days=15, key=None):
        return issue(self.device, key or self.key, datetime.fromtimestamp(self.now[0], timezone.utc), days=days)

    def test_linux_request_hashes_stable_components_and_rejects_missing_hardware(self):
        from plakino_license.device import device_request
        values = {'/etc/machine-id': 'installation-secret',
                  '/sys/class/dmi/id/board_name': 'board-model',
                  '/sys/class/dmi/id/board_vendor': 'board-vendor'}
        def read(path, *args, **kwargs):
            if str(path) not in values:
                raise PermissionError()
            return values[str(path)]
        with patch('plakino_license.device.platform.system', return_value='Linux'), \
                patch('pathlib.Path.read_text', read):
            first = device_request()
            self.assertEqual(first, device_request())
            self.assertEqual(len(first['components']), 3)
            self.assertNotIn('installation-secret', json.dumps(first))
            values.pop('/sys/class/dmi/id/board_name')
            values.pop('/sys/class/dmi/id/board_vendor')
            with self.assertRaises(ValueError):
                device_request()

    def test_disk_failure_blocks_processing(self):
        self.service.install(self.license())
        with patch('plakino_license.service.atomic_write', side_effect=OSError('disk full')):
            self.assertEqual(self.service.status()['code'], 'storage_error')

    def test_signature_device_and_invalid_import_preserve_active_license(self):
        self.assertEqual(self.service.status()['code'], 'missing')
        valid = self.license()
        self.assertTrue(self.service.install(valid)['valid'])
        tampered = json.loads(json.dumps(valid))
        tampered['payload']['expires_at'] += 999999
        self.assertEqual(self.service.install(tampered)['code'], 'invalid')
        self.assertEqual(self.service.install(self.license(key=Ed25519PrivateKey.generate()))['code'], 'invalid')
        other = LicenseService(self.root / 'other', self.public,
                               lambda: dict(self.device, device_id='other'))
        self.assertEqual(other.install(valid)['code'], 'wrong_device')
        self.assertEqual(self.service.status()['license_id'], valid['payload']['license_id'])

    def test_expiry_survives_restart_rollback_and_reimport_then_renews(self):
        old = self.license(days=1)
        self.service.install(old)
        self.now[0] += 86400
        self.assertEqual(self.service.status()['code'], 'expired')
        self.now[0] -= 86400
        service = self.new_service()
        self.assertEqual(service.status()['code'], 'expired')
        self.assertEqual(service.install(old)['code'], 'expired')
        self.now[0] += 86401
        self.assertTrue(service.install(self.license(days=30))['valid'])
        self.assertEqual(service.install(old)['code'], 'expired')
        self.assertTrue(service.status()['valid'])

    def test_rollback_blocks_and_correct_clock_recovers_without_extending_term(self):
        self.service.install(self.license())
        self.now[0] += 1000
        self.service.status()
        self.now[0] -= 500
        self.assertEqual(self.new_service().status()['code'], 'clock_rollback')
        self.now[0] += 500
        self.assertTrue(self.new_service().status()['valid'])

    def test_monotonic_time_expires_even_when_wall_clock_is_frozen(self):
        self.service.install(self.license(days=1))
        self.mono[0] += 86400
        self.assertEqual(self.service.status()['code'], 'expired')

    def test_corrupt_and_missing_history_fail_closed(self):
        self.service.install(self.license())
        state = self.root / 'state' / 'state.json'
        original = state.read_bytes()
        document = json.loads(original)
        document['state']['last_time'] = 1
        state.write_bytes(canonical(document))
        self.assertEqual(self.service.status()['code'], 'state_invalid')
        self.assertEqual(self.service.install(self.license())['code'], 'state_invalid')
        state.write_bytes(original)
        (state.parent / 'state.key').unlink()
        self.assertEqual(self.service.status()['code'], 'state_invalid')

    def test_missing_history_with_surviving_key_is_not_reinitialized(self):
        self.service.install(self.license())
        (self.root / 'state' / 'state.json').unlink()
        self.assertEqual(self.service.install(self.license())['code'], 'state_invalid')

    def test_initial_expired_import_cannot_be_revived_by_rollback(self):
        old = self.license(days=1)
        self.now[0] += 86400
        self.assertEqual(self.service.install(old)['code'], 'expired')
        self.now[0] -= 86400
        self.assertEqual(self.new_service().install(old)['code'], 'expired')

    def test_calendar_months_and_bad_duration(self):
        now = datetime(2028, 8, 31, tzinfo=timezone.utc)
        doc = issue(self.device, self.key, now, months=6)
        self.assertEqual(datetime.fromtimestamp(doc['payload']['expires_at'], timezone.utc).date().isoformat(), '2029-02-28')
        with self.assertRaises(ValueError):
            issue(self.device, self.key, now, days=0)

    def test_backend_start_and_expiry_are_enforced_without_ui(self):
        config = self.root / 'cameras.json'
        config.write_text(json.dumps({'cameras': [{'id': 'one', 'source': 'test.mp4', 'type': 'video'}]}))
        pipeline = Mock(stop=Mock(return_value=True), failed_workers=Mock(return_value=[]))
        factory = Mock(return_value=pipeline)
        controller = BackendController(factory, config, self.service)
        self.addCleanup(controller.close)
        controller.command('start')
        factory.assert_not_called()
        controller.install_license(self.license(days=1))
        controller.command('start')
        controller.operation.join(2)
        self.assertEqual(controller.snapshot()['state'], 'running')
        self.now[0] += 86400
        controller._license_checked = float('-inf')
        controller.snapshot()
        controller.operation.join(2)
        self.assertEqual(controller.snapshot()['state'], 'stopped')
        self.assertEqual(controller.snapshot()['license']['code'], 'expired')
        pipeline.stop.assert_called_once()
        controller.command('start')
        self.assertEqual(factory.call_count, 1)

    def test_expiration_during_model_loading_prevents_start(self):
        config = self.root / 'cameras.json'
        config.write_text(json.dumps({'cameras': [{'id': 'one', 'source': 'test.mp4', 'type': 'video'}]}))
        self.service.install(self.license(days=1))
        pipeline = Mock(stop=Mock(return_value=True))
        def factory(*_):
            self.now[0] += 86400
            return pipeline
        controller = BackendController(factory, config, self.service)
        self.addCleanup(controller.close)
        controller.command('start')
        controller.operation.join(2)
        pipeline.start.assert_not_called()
        self.assertEqual(controller.snapshot()['license']['code'], 'expired')

    def test_control_import_and_request_leave_processing_stopped(self):
        controller = BackendController(license_service=self.service)
        server = ControlServer(controller, self.root / 'control', 0)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        client = BackendClient(self.root / 'control', server.server_port)
        self.assertEqual(client.license_request(), self.device)
        self.assertTrue(client.install_license(self.license())['valid'])
        self.assertEqual(client.status()['state'], 'stopped')


if __name__ == '__main__':
    unittest.main()
