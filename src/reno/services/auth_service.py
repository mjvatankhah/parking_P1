"""Authentication and admin-only guard registration using the shared PostgreSQL DB."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import secrets

from computer_vision_v2.database.connection import get_connection
from reno.models.username import is_username_text, USERNAME_LANGUAGE_ERROR

# Temporary pilot administrator; replace with provisioned accounts before production.
_DEMO_USERNAME = "admin"
_DEMO_PASSWORD = "1234"
ERROR_INVALID_CREDENTIALS = "نام کاربری یا رمز عبور اشتباه است"
_SCHEMA = """CREATE TABLE IF NOT EXISTS app_user (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('guard')),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
)"""


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600_000)
    return f"pbkdf2_sha256$600000${salt}${digest.hex()}"


def verify_password(password, encoded):
    try:
        algorithm, rounds, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256':
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(rounds))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class LoginResult:
    success: bool
    error_message: str = ""
    role: str = ""


def _ensure_schema(cursor):
    cursor.execute(_SCHEMA)
    # Old accounts have no recorded creation time; preserve that as NULL.
    cursor.execute('ALTER TABLE app_user ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ')
    cursor.execute('ALTER TABLE app_user ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP')


@dataclass(frozen=True)
class GuardAccount:
    username: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class GuardListResult:
    success: bool
    guards: tuple[GuardAccount, ...] = ()
    error_message: str = ""

    @property
    def usernames(self):
        return tuple(guard.username for guard in self.guards)


class AuthService:
    def __init__(self):
        self.current_role = ""

    @property
    def is_admin(self):
        return self.current_role == 'admin'

    def logout(self):
        self.current_role = ""

    def login(self, username: str, password: str) -> LoginResult:
        self.logout()
        username = (username or '').strip()
        password = password or ''
        if username and not is_username_text(username):
            return LoginResult(False, USERNAME_LANGUAGE_ERROR)
        if username == _DEMO_USERNAME and password == _DEMO_PASSWORD:
            self.current_role = 'admin'
            return LoginResult(True, role='admin')
        if not username or not password or username == _DEMO_USERNAME:
            return LoginResult(False, ERROR_INVALID_CREDENTIALS)
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    _ensure_schema(cursor)
                    cursor.execute('SELECT password_hash, role FROM app_user WHERE username = %s', (username,))
                    row = cursor.fetchone()
            if row and row[1] == 'guard' and verify_password(password, row[0]):
                self.current_role = 'guard'
                return LoginResult(True, role='guard')
        except Exception:
            return LoginResult(False, 'ارتباط با پایگاه داده برقرار نشد')
        return LoginResult(False, ERROR_INVALID_CREDENTIALS)

    def list_guards(self):
        if not self.is_admin:
            return GuardListResult(False, error_message='فقط مدیر اجازه مشاهده نگهبان‌ها دارد')
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    _ensure_schema(cursor)
                    cursor.execute("SELECT username, created_at FROM app_user WHERE role = 'guard' ORDER BY created_at DESC NULLS LAST, username")
                    guards = tuple(GuardAccount(row[0], row[1]) for row in cursor.fetchall())
            return GuardListResult(True, guards)
        except Exception:
            return GuardListResult(False, error_message='دریافت فهرست نگهبان‌ها انجام نشد؛ اتصال را بررسی کنید')

    def delete_guard(self, username):
        if not self.is_admin:
            return LoginResult(False, 'فقط مدیر اجازه حذف نگهبان دارد')
        if not username or username == _DEMO_USERNAME:
            return LoginResult(False, 'نام کاربری نگهبان معتبر نیست')
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    _ensure_schema(cursor)
                    cursor.execute("DELETE FROM app_user WHERE username = %s AND role = 'guard' RETURNING username", (username,))
                    deleted = cursor.fetchone()
            if not deleted:
                return LoginResult(False, 'این نگهبان وجود ندارد؛ فهرست را به‌روز کنید')
            return LoginResult(True)
        except Exception:
            return LoginResult(False, 'حذف نگهبان انجام نشد؛ اتصال را بررسی کنید')

    def create_guard(self, username, password, confirmation):
        if not self.is_admin:
            return LoginResult(False, 'فقط مدیر اجازه ثبت نگهبان دارد')
        username = (username or '').strip()
        if not username or not password or not password.strip():
            return LoginResult(False, 'نام کاربری و رمز عبور را وارد کنید')
        if not is_username_text(username):
            return LoginResult(False, USERNAME_LANGUAGE_ERROR)
        if password != confirmation:
            return LoginResult(False, 'تکرار رمز عبور یکسان نیست')
        if username == _DEMO_USERNAME:
            return LoginResult(False, 'این نام کاربری برای مدیر رزرو شده است')
        encoded = hash_password(password)
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    _ensure_schema(cursor)
                    cursor.execute("INSERT INTO app_user (username, password_hash, role) VALUES (%s, %s, 'guard') ON CONFLICT (username) DO NOTHING RETURNING username", (username, encoded))
                    created = cursor.fetchone()
            if not created:
                return LoginResult(False, 'این نام کاربری قبلاً ثبت شده است')
        except Exception:
            return LoginResult(False, 'ذخیره در پایگاه داده انجام نشد؛ اتصال را بررسی کنید')
        return LoginResult(True)


auth_service = AuthService()
