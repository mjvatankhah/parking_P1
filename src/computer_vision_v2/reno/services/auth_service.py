"""
services/auth_service.py

The Login screen never checks a username/password itself - it only
calls `auth_service.login(username, password)` and looks at the result.

That one rule is what lets us swap this mock implementation for a real
one later (checking a database, calling an API, etc.) WITHOUT changing
a single line in ui/login.py.

How to connect your real backend later:
    Replace the body of AuthService.login() with a call into your
    existing backend (for example an HTTP request or a direct Python
    call), keeping the same method name and the same return value
    shape (a LoginResult).
"""

from dataclasses import dataclass

# --- Demo credentials for this UI-only prototype -----------------------
_DEMO_USERNAME = "admin"
_DEMO_PASSWORD = "1234"

ERROR_INVALID_CREDENTIALS = "نام کاربری یا رمز عبور اشتباه است"


@dataclass
class LoginResult:
    success: bool
    error_message: str = ""


class AuthService:
    """Mock authentication service.

    Everything is in-memory and hard-coded on purpose for this UI
    iteration. Swap the inside of `login()` when the real backend is
    ready; keep the method signature the same.
    """

    def login(self, username: str, password: str) -> LoginResult:
        username = (username or "").strip()
        password = (password or "").strip()

        if username == _DEMO_USERNAME and password == _DEMO_PASSWORD:
            return LoginResult(success=True)

        return LoginResult(success=False, error_message=ERROR_INVALID_CREDENTIALS)


# A single shared instance the whole app can import and use, e.g.:
#   from services.auth_service import auth_service
#   result = auth_service.login(username, password)
auth_service = AuthService()
