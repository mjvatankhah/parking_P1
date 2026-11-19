"""Signature validation and atomic, authenticated local time history.

Local authentication detects casual edits, not an administrator who can restore a
whole disk or modify this application. Only the backend owns this mutable state.
"""
import base64
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .device import device_request

PUBLIC_KEY = Path(__file__).with_name('issuer_public.pem')
MAX_FILE = 65536


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.license-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class LicenseService:
    def __init__(self, directory=None, public_key=PUBLIC_KEY, device_provider=device_request,
                 wall=time.time, monotonic=time.monotonic):
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share')))
        self.directory = Path(directory) if directory is not None else base / 'plakino' / 'license'
        self.public_key = Path(public_key)
        self.device_provider = device_provider
        self.wall, self.monotonic = wall, monotonic
        self.lock = threading.RLock()
        self.anchor = None
        self._device = None

    def request(self):
        with self.lock:
            if self._device is None:
                try:
                    self._device = self.device_provider()
                except (OSError, ValueError, subprocess.SubprocessError):
                    raise ValueError('device_unavailable') from None
            return self._device.copy()

    def _verify(self, document):
        if not isinstance(document, dict) or set(document) != {'payload', 'signature'}:
            raise ValueError('invalid')
        payload = document['payload']
        try:
            key = serialization.load_pem_public_key(self.public_key.read_bytes())
        except (OSError, ValueError):
            raise ValueError('issuer_not_configured') from None
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError('issuer_not_configured')
        try:
            key.verify(base64.b64decode(document['signature'], validate=True), canonical(payload))
        except (InvalidSignature, ValueError, TypeError):
            raise ValueError('invalid') from None
        if not isinstance(payload, dict) or payload.get('version') != 1 or payload.get('product') != 'plakino':
            raise ValueError('invalid')
        if not isinstance(payload.get('license_id'), str) or not 1 <= len(payload['license_id']) <= 128:
            raise ValueError('invalid')
        for field in ('issued_at', 'expires_at'):
            if type(payload.get(field)) is not int or payload[field] <= 0:
                raise ValueError('invalid')
        if payload['expires_at'] <= payload['issued_at']:
            raise ValueError('invalid')
        if payload.get('device_id') != self.request()['device_id']:
            raise ValueError('wrong_device')
        return payload

    def _read(self):
        path = self.directory / 'state.json'
        if not path.exists():
            # A surviving key is an installation marker; never silently recreate history.
            if (self.directory / 'state.key').exists():
                raise ValueError('state_invalid')
            return None
        try:
            raw = path.read_bytes()
            if len(raw) > MAX_FILE * 16:
                raise ValueError()
            document = json.loads(raw)
            key = (self.directory / 'state.key').read_bytes()
            state = document['state']
            mac = hmac.new(key, canonical(state), hashlib.sha256).hexdigest()
            if len(key) != 32 or not hmac.compare_digest(mac, document['mac']):
                raise ValueError()
            if not isinstance(state['expired'], list) or not math.isfinite(state['last_time']):
                raise ValueError()
            return state
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError('state_invalid') from None

    def _save(self, state, initial=False):
        key_path = self.directory / 'state.key'
        if initial:
            atomic_write(key_path, secrets.token_bytes(32))
        key = key_path.read_bytes()
        atomic_write(self.directory / 'state.json', canonical(dict(
            state=state, mac=hmac.new(key, canonical(state), hashlib.sha256).hexdigest())))

    def _time(self, state):
        now, mono = self.wall(), self.monotonic()
        if not math.isfinite(now) or now <= 0:
            raise ValueError('clock_rollback')
        floor = state['last_time']
        if self.anchor is not None:
            floor = max(floor, self.anchor[0] + max(0, mono - self.anchor[1]))
        effective = max(now, floor)
        self.anchor = (effective, mono)
        state['last_time'] = effective
        return effective, now < floor - 120  # tolerate small clock corrections, never extend expiry

    def _evaluate(self, state):
        payload = self._verify(state['license'])
        now, rollback = self._time(state)
        lid = payload['license_id']
        if now >= payload['expires_at'] and lid not in state['expired']:
            state['expired'].append(lid)
        code = ('expired' if lid in state['expired'] else 'clock_rollback' if rollback else
                'not_yet_valid' if now < payload['issued_at'] else 'valid')
        return dict(valid=code == 'valid', code=code, license_id=lid,
                    expires_at=payload['expires_at'], last_time=now)

    def status(self):
        with self.lock:
            try:
                state = self._read()
                if state is None:
                    return dict(valid=False, code='missing')
                result = self._evaluate(state)
                self._save(state)
                return result
            except (OSError, ValueError, TypeError, KeyError) as exc:
                return dict(valid=False, code=str(exc) if str(exc) in {
                    'invalid', 'issuer_not_configured', 'wrong_device', 'state_invalid',
                    'clock_rollback', 'device_unavailable'} else 'storage_error')

    def install(self, document):
        with self.lock:
            try:
                if len(canonical(document)) > MAX_FILE:
                    raise ValueError('invalid')
                self._verify(document)
                state = self._read()
                initial = state is None
                if initial:
                    state = dict(last_time=0, expired=[], license=document)
                else:
                    # Record expiry of the old license before replacing it.
                    self._evaluate(state)
                    self._save(state)
                candidate = dict(state, expired=list(state['expired']), license=document)
                result = self._evaluate(candidate)
                if not result['valid']:
                    if result['code'] == 'expired':
                        if initial:
                            self._save(candidate, initial=True)
                        else:
                            state['expired'] = candidate['expired']
                            state['last_time'] = candidate['last_time']
                            self._save(state)
                    return result
                self._save(candidate, initial=initial)
                return result
            except (OSError, ValueError, TypeError, KeyError) as exc:
                code = str(exc)
                return dict(valid=False, code=code if code in {'invalid', 'issuer_not_configured',
                    'wrong_device', 'state_invalid', 'clock_rollback', 'device_unavailable'} else 'invalid')
