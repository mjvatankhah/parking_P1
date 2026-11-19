"""Stable, hashed installation and hardware identifiers (never network MACs)."""
import hashlib
import json
import platform
from pathlib import Path
import subprocess


def device_request():
    values = {}
    if platform.system() == 'Linux':
        for name, path in [('installation', '/etc/machine-id'),
                           ('board', '/sys/class/dmi/id/board_serial'),
                           ('product', '/sys/class/dmi/id/product_uuid'),
                           ('board_model', '/sys/class/dmi/id/board_name'),
                           ('board_vendor', '/sys/class/dmi/id/board_vendor')]:
            try:
                values[name] = Path(path).read_text().strip()
            except OSError:
                pass
    elif platform.system() == 'Windows':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography',
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            values['installation'] = winreg.QueryValueEx(key, 'MachineGuid')[0]
        script = '(Get-CimInstance Win32_ComputerSystemProduct).UUID; (Get-CimInstance Win32_BaseBoard).SerialNumber'
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, text=True, timeout=10, check=True,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        for name, value in zip(('product', 'board'), result.stdout.splitlines()):
            values[name] = value.strip()
    else:
        raise ValueError('Unsupported device platform')
    invalid = {'', 'none', 'unknown', 'default string', 'to be filled by o.e.m.',
               '00000000-0000-0000-0000-000000000000', 'ffffffff-ffff-ffff-ffff-ffffffffffff'}
    components = {name: hashlib.sha256(('plakino-device-v1:' + name + ':' + str(value).strip().lower()).encode()).hexdigest()
                  for name, value in values.items() if str(value).strip().lower() not in invalid}
    if 'installation' not in components or len(components) < 2:
        raise ValueError('At least an installation ID and a stable hardware ID are required')
    fingerprint = hashlib.sha256(json.dumps(components, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(version=1, product='plakino', device_id=fingerprint, components=components)
