"""Dashboard aggregates from the event table and live camera state."""

from dataclasses import dataclass
from datetime import date, timedelta

from computer_vision_v2.database.connection import get_connection
from computer_vision_v2.reno.models.camera import STATUS_ONLINE
from computer_vision_v2.reno.services.camera_service import camera_service
from computer_vision_v2.reno.services.mock_mode import MOCK_DATA_ENABLED
from computer_vision_v2.reno.services.plate_service import plate_service


@dataclass
class DashboardStatistics:
    today_total: int
    unique_vehicles: int
    online_cameras: int
    total_cameras: int
    alerts: int


class DashboardService:
    def get_daily_flow(self, end=None, camera="", plate=""):
        """Seven calendar days including end, zero-filled without truncating events."""
        end = end or date.today()
        start = end - timedelta(days=6)
        days = {start + timedelta(days=i): [0, 0] for i in range(7)}
        if MOCK_DATA_ENABLED:
            for record in plate_service._mock_records:
                day = date.fromisoformat(record.date)
                if day in days and (not camera or record.camera == camera) and (not plate or plate in record.plate):
                    if record.direction in ('entry', 'exit'):
                        days[day][record.direction == 'exit'] += 1
        else:
            conditions = ["captured_at >= %s", "captured_at < %s"]
            params = [start, end + timedelta(days=1)]
            if camera:
                conditions.append("camera_id = %s")
                params.append(camera)
            if plate:
                conditions.append("strpos(COALESCE(plate_number, ''), %s) > 0")
                params.append(plate)
            with get_connection(connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION READ ONLY')
                    cursor.execute("SET LOCAL statement_timeout = '5s'")
                    cursor.execute("SELECT captured_at::date, count(*) FILTER (WHERE event_type = 'entry'), "
                                   "count(*) FILTER (WHERE event_type = 'exit') FROM event WHERE "
                                   + ' AND '.join(conditions) + " GROUP BY captured_at::date", params)
                    for day, entries, exits in cursor.fetchall():
                        days[day] = [entries, exits]
        return [(day.isoformat(), *counts) for day, counts in days.items()]

    def get_statistics(self) -> DashboardStatistics:
        cameras = camera_service.get_cameras()
        online = sum(camera.status == STATUS_ONLINE for camera in cameras)
        if MOCK_DATA_ENABLED:
            records = plate_service.get_recent_records(limit=1000)
            today = date.today().isoformat()
            day = [record for record in records if record.date == today]
            total = len(day)
            unique = len({record.plate for record in day if record.plate != 'خوانده نشد'})
            unread = sum(record.plate == 'خوانده نشد' for record in day)
        else:
            with get_connection(connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION READ ONLY')
                    cursor.execute("SET LOCAL statement_timeout = '5s'")
                    cursor.execute('''SELECT count(*), count(DISTINCT plate_number),
                                             count(*) FILTER (WHERE plate_number IS NULL)
                                      FROM event
                                      WHERE captured_at >= CURRENT_DATE
                                        AND captured_at < CURRENT_DATE + INTERVAL '1 day' ''')
                    total, unique, unread = cursor.fetchone()
        return DashboardStatistics(
            today_total=total, unique_vehicles=unique,
            online_cameras=online, total_cameras=len(cameras),
            alerts=unread + len(cameras) - online,
        )


dashboard_service = DashboardService()
