"""Parking calendar and display timezone, independent of the host timezone."""
from datetime import datetime
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")


def today():
    return datetime.now(TEHRAN).date()
