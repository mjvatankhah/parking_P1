#!/usr/bin/env python3
"""Private issuer tool. Ship only the generated PUBLIC key with the customer app."""
import argparse
import base64
import calendar
from datetime import datetime, timezone, timedelta
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from plakino_license.service import canonical


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)


def issue(request, key, now, days=None, months=None):
    components = request.get('components', {})
    expected = hashlib.sha256(canonical(components)).hexdigest()
    if (request.get('version') != 1 or request.get('product') != 'plakino'
            or request.get('device_id') != expected or len(components) < 2
            or 'installation' not in components):
        raise ValueError('Invalid device request')
    if (days is None) == (months is None) or (days if days is not None else months) <= 0:
        raise ValueError('Specify a positive duration')
    if months is not None:
        index = now.year * 12 + now.month - 1 + months
        year, month = divmod(index, 12)
        month += 1
        end = now.replace(year=year, month=month, day=min(now.day, calendar.monthrange(year, month)[1]))
    else:
        end = now + timedelta(days=days)
    payload = dict(version=1, product='plakino', license_id=str(uuid.uuid4()),
                   device_id=request['device_id'], issued_at=int(now.timestamp()),
                   expires_at=int(end.timestamp()))
    return dict(payload=payload, signature=base64.b64encode(key.sign(canonical(payload))).decode('ascii'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    keys = sub.add_parser('keygen')
    keys.add_argument('--private', required=True, type=Path)
    keys.add_argument('--public', required=True, type=Path)
    sign = sub.add_parser('issue')
    sign.add_argument('--private', required=True, type=Path)
    sign.add_argument('--request', required=True, type=Path)
    sign.add_argument('--output', required=True, type=Path)
    duration = sign.add_mutually_exclusive_group(required=True)
    duration.add_argument('--days', type=int)
    duration.add_argument('--months', type=int)
    args = parser.parse_args()
    try:
        password = getpass.getpass('Private key password: ').encode()
        if not password:
            parser.error('A non-empty private key password is required')
        if args.command == 'keygen':
            if args.private.exists() or args.public.exists() or args.private.resolve() == args.public.resolve():
                parser.error('Key output paths must be distinct and must not exist')
            if password != getpass.getpass('Confirm password: ').encode():
                parser.error('Passwords differ')
            key = Ed25519PrivateKey.generate()
            write_new(args.private, key.private_bytes(serialization.Encoding.PEM,
                      serialization.PrivateFormat.PKCS8, serialization.BestAvailableEncryption(password)))
            write_new(args.public, key.public_key().public_bytes(serialization.Encoding.PEM,
                      serialization.PublicFormat.SubjectPublicKeyInfo))
        else:
            key = serialization.load_pem_private_key(args.private.read_bytes(), password=password)
            if not isinstance(key, Ed25519PrivateKey):
                parser.error('Expected an Ed25519 private key')
            document = issue(json.loads(args.request.read_text()), key, datetime.now(timezone.utc),
                             days=args.days, months=args.months)
            write_new(args.output, canonical(document))
            print('Expires (UTC):', datetime.fromtimestamp(document['payload']['expires_at'], timezone.utc).isoformat())
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
