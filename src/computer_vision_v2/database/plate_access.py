"""Plate policy schema and normalization shared by UI services and event ingestion."""
from pathlib import Path
import re
from threading import Lock

_LOCK=Lock()
_READY=False
_DIGITS=str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك','01234567890123456789یک')


def normalize_plate(value):
    return re.sub(r'[\s\-\u200c]','',value.translate(_DIGITS))


def ensure_schema(connection):
    global _READY
    with _LOCK:
        if _READY:
            return
        script=(Path(__file__).parent/'migrations/006_plate_access.sql').read_text()
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '3s'")
                cursor.execute("SET LOCAL statement_timeout = '10s'")
                cursor.execute(script)
        _READY=True
