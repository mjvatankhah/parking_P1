"""Read committed plate events from the pipeline's PostgreSQL database."""

import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from computer_vision_v2.reno.models.plate_record import PlateRecord, DIRECTION_ENTRY, DIRECTION_EXIT
from computer_vision_v2.reno.services.camera_service import camera_service
from computer_vision_v2.reno.services.mock_mode import MOCK_DATA_ENABLED

# A believable-looking set of Persian plate letters, used only to build
# mock plate numbers such as "12الف345".
_PLATE_LETTERS = ["الف", "ب", "ج", "د", "س", "ص", "ط", "ق", "ل", "م", "ن", "و", "ه", "ی"]
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _connect():
    from computer_vision_v2.database.connection import get_connection
    return get_connection(connect_timeout=5)


class PlateService:
    def __init__(self, connection_factory=None):
        self._connect = connection_factory or _connect
        self._mock_records: List[PlateRecord] = []
        if MOCK_DATA_ENABLED:
            self._mock_records = self._generate_mock_records(count=50)

    def get_recent_records(self, limit: int = 50) -> List[PlateRecord]:
        """Return the most recent `limit` records, newest first."""
        if limit <= 0:
            return []
        if MOCK_DATA_ENABLED:
            return self._mock_records[:limit]
        # Each refresh has its own short transaction and connection. Never
        # share the writer's connection across threads/processes.
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SET LOCAL statement_timeout = '5s'")
                cursor.execute(
                    """SELECT plate_number, captured_at, camera_id, event_type, class_id, image_path
                       FROM event
                       ORDER BY captured_at DESC, id DESC
                       LIMIT %s""",
                    (limit,),
                )
                rows = cursor.fetchall()
        records = []
        for plate, captured_at, camera_id, direction, class_id, image_path in rows:
            if image_path:
                path = Path(image_path)
                image_path = str(path if path.is_absolute() else _PROJECT_ROOT / path)
            records.append(PlateRecord(
                plate=plate or "خوانده نشد", date=captured_at.strftime('%Y-%m-%d'),
                time=captured_at.strftime('%H:%M:%S'), camera=camera_id,
                class_id=class_id, direction=direction, image_path=image_path or '',
            ))
        return records

    # -- mock data generation -----------------------------------------
    def _generate_mock_records(self, count: int) -> List[PlateRecord]:
        cameras = camera_service.get_cameras()
        camera_ids = [c.id for c in cameras] or ["camera-1"]

        records = []
        now = datetime.now()
        for i in range(count):
            when = now - timedelta(minutes=i * 7)
            plate = "{:02d}{}{:03d}".format(
                random.randint(10, 99),
                random.choice(_PLATE_LETTERS),
                random.randint(100, 999),
            )
            records.append(
                PlateRecord(
                    plate=plate,
                    date=when.strftime("%Y-%m-%d"),
                    time=when.strftime("%H:%M:%S"),
                    camera=random.choice(camera_ids),
                    direction=random.choice([DIRECTION_ENTRY, DIRECTION_EXIT]),
                )
            )
        return records


# A single shared instance the whole app imports.
plate_service = PlateService()
