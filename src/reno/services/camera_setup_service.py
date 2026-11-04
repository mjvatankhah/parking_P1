"""Separate camera registration from bounded, on-demand source connection checks."""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import subprocess
import sys
from urllib.parse import urlsplit

from computer_vision_v2.database.connection import get_connection
from reno.models.camera import Camera


@dataclass(frozen=True)
class CameraSetupResult:
    success: bool
    message: str
    registered: bool = False


def register_camera(camera: Camera, gate_name: str) -> CameraSetupResult:
    gate_name = gate_name.strip()
    if not gate_name or not camera.id.strip() or not camera.source.strip():
        return CameraSetupResult(False, 'نام گیت، نام دوربین و منبع تصویر را وارد کنید')
    if gate_name == camera.id.strip():
        return CameraSetupResult(False, 'نام گیت و دوربین نباید یکسان باشند')
    if camera.source_type not in ('rtsp', 'video') or camera.role not in ('entry', 'exit', 'entry_exit'):
        return CameraSetupResult(False, 'نوع منبع یا کارکرد دوربین معتبر نیست')
    if camera.source_type == 'rtsp':
        try:
            address = urlsplit(camera.source)
            valid_address = address.scheme.lower() in ('rtsp', 'rtsps') and bool(address.hostname)
        except ValueError:
            valid_address = False
        if not valid_address:
            return CameraSetupResult(False, 'آدرس RTSP معتبر وارد کنید')
    else:
        path = Path(camera.source).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        camera.source = str(path.resolve())
    gate_id = gate_name
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT gate_id FROM camera WHERE id = %s', (camera.id,))
                existing = cursor.fetchone()
                if existing:
                    if existing[0] != gate_id:
                        return CameraSetupResult(False, 'این دوربین به گیت دیگری متصل است؛ نام گیت فعلی را وارد کنید')
                    gate_id = existing[0]
                cursor.execute('INSERT INTO gate (id) VALUES (%s) ON CONFLICT (id) DO NOTHING', (gate_id,))
                cursor.execute("""INSERT INTO camera (id, gate_id, source, source_type, role, status)
                    VALUES (%s, %s, %s, %s, %s, 'off')
                    ON CONFLICT (id) DO UPDATE SET source = EXCLUDED.source,
                    source_type = EXCLUDED.source_type, role = EXCLUDED.role
                    WHERE camera.gate_id = EXCLUDED.gate_id RETURNING gate_id""",
                    (camera.id, gate_id, camera.source, camera.source_type, camera.role))
                if cursor.fetchone() is None:
                    raise ValueError("Camera gate mapping changed during registration")
    except Exception as error:
        if getattr(error, 'sqlstate', None) == '23505':
            return CameraSetupResult(False, 'این گیت قبلاً به دوربین دیگری متصل شده است')
        return CameraSetupResult(False, 'ثبت گیت و دوربین در پایگاه داده انجام نشد؛ اتصال را بررسی کنید')
    camera.gate_id = gate_id
    return CameraSetupResult(True, 'گیت و دوربین ثبت شدند', True)


def check_connection(camera: Camera) -> CameraSetupResult:
    """Probe one frame without creating or changing any database record."""
    try:
        environment = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[2])
        environment['PYTHONPATH'] = source_root + os.pathsep + environment.get('PYTHONPATH', '')
        result = subprocess.run(
            [sys.executable, '-m', 'reno.services.source_probe'],
            input=json.dumps({'source': camera.source, 'type': camera.source_type}),
            text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=12, env=environment,
        )
        if result.returncode != 0:
            return CameraSetupResult(False, 'دریافت تصویر از منبع ناموفق بود؛ آدرس و اتصال دوربین را بررسی کنید')
    except subprocess.TimeoutExpired:
        return CameraSetupResult(False, 'مهلت بررسی اتصال تمام شد؛ دوباره تلاش کنید')
    except OSError:
        return CameraSetupResult(False, 'اجرای بررسی اتصال ممکن نشد')
    return CameraSetupResult(True, 'اتصال برقرار شد و تصویر دریافت شد')


def register_and_check(camera: Camera, gate_name: str) -> CameraSetupResult:
    """Compatibility entry point; desktop registration uses register_camera only."""
    if camera.source_type == 'video':
        path = Path(camera.source).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        if not path.is_file():
            return CameraSetupResult(False, 'فایل ویدیویی انتخاب‌شده وجود ندارد')
    registration = register_camera(camera, gate_name)
    if not registration.success:
        return registration
    checked = check_connection(camera)
    return CameraSetupResult(checked.success, registration.message + '؛ ' + checked.message, True)
