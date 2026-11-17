"""Local owner-account provisioning. Passwords never appear in command arguments."""
import argparse
import getpass
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from computer_vision_v2.database.connection import get_connection
from plakino_ui.models.username import is_username_text
from plakino_ui.services.auth_service import _ensure_schema, hash_password


def provision(username, password, *, reset=False):
    if not is_username_text(username) or username == 'admin':
        raise ValueError('Choose an ASCII username other than the existing pilot admin.')
    if len(password) < 12 or not password.strip():
        raise ValueError('Use a password with at least 12 characters.')
    encoded = hash_password(password)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            _ensure_schema(cursor)
            if reset:
                cursor.execute("UPDATE app_user SET password_hash = %s "
                               "WHERE username = %s AND role = 'superadmin' RETURNING username",
                               (encoded, username))
            else:
                cursor.execute("INSERT INTO app_user (username, password_hash, role) "
                               "VALUES (%s, %s, 'superadmin') ON CONFLICT (username) DO NOTHING "
                               "RETURNING username", (username, encoded))
            if cursor.fetchone() is None:
                raise ValueError('Account exists; no changes made.' if not reset else
                                 'No superadmin account with this username; no changes made.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', default='superadmin')
    parser.add_argument('--reset-password', action='store_true')
    parser.add_argument('--credentials-file', type=Path,
                        help='Generate a random password in a NEW private local file instead of prompting.')
    args = parser.parse_args()
    credentials = None
    try:
        if args.credentials_file:
            credentials = args.credentials_file.expanduser()
            credentials.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            password = secrets.token_urlsafe(24)
            # Exclusive creation prevents replacing an existing credential file.
            fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(f'Username: {args.username}\nPassword: {password}\n')
        else:
            password = getpass.getpass('Superadmin password (at least 12 characters): ')
            if password != getpass.getpass('Repeat password: '):
                raise ValueError('Passwords do not match.')
        provision(args.username, password, reset=args.reset_password)
    except Exception as exc:
        # Do not print DB exception details, which may contain connection secrets.
        if credentials is not None and 'fd' in locals():
            credentials.unlink(missing_ok=True)
        print(str(exc) if isinstance(exc, ValueError) else
              f'Provisioning failed ({type(exc).__name__}); check local database access.', file=sys.stderr)
        return 1
    print('Superadmin account is ready.' + (f' Credentials: {credentials}' if credentials else ''))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
