"""Customer CLI using the same backend state as the UI."""
import argparse
import json
from pathlib import Path
from computer_vision_v2.runtime.control import BackendClient


def main():
    parser = argparse.ArgumentParser(description='Offline license activation')
    sub = parser.add_subparsers(dest='action', required=True)
    request = sub.add_parser('request')
    request.add_argument('output', type=Path)
    install = sub.add_parser('import')
    install.add_argument('file', type=Path)
    sub.add_parser('status')
    args = parser.parse_args()
    client = BackendClient(timeout=15)
    try:
        if args.action == 'request':
            document = client.license_request()
            with args.output.open('x', encoding='utf-8') as stream:
                json.dump(document, stream, indent=2)
            print(str(args.output))
        elif args.action == 'import':
            with args.file.open('rb') as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                parser.error('License file is too large')
            result = client.install_license(json.loads(raw))
            print(json.dumps(result))
            if not result['valid']:
                raise SystemExit(1)
        else:
            client.ensure_host()
            print(json.dumps(client.status().get('license', {})))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
