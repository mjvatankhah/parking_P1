"""Dashboard aggregates from the event table and live camera state."""
from computer_vision_v2.database.plate_access import normalize_plate, ensure_schema

from dataclasses import dataclass
from datetime import date, timedelta

from computer_vision_v2.database.connection import get_connection
from reno.models.camera import STATUS_ONLINE
from reno.services.camera_service import camera_service
from reno.services.mock_mode import MOCK_DATA_ENABLED
from reno.services.plate_service import plate_service


@dataclass
class DashboardStatistics:
    today_total: int
    unique_vehicles: int
    online_cameras: int
    total_cameras: int
    alerts: int
    inside_vehicles: int = 0
    guest_vehicles: int = 0
    blocked_vehicles: int = 0
    access_counts: tuple[int, int, int, int] = (0, 0, 0, 0)


class DashboardService:
    def get_hourly_flow(self, day=None, camera="", plate=""):
        """24 hourly buckets for one day, with the same camera/plate filters as the table."""
        day = day or date.today()
        plate = normalize_plate(plate)
        hours = [[0, 0] for _ in range(24)]
        if MOCK_DATA_ENABLED:
            for record in plate_service._mock_records:
                if (record.date == day.isoformat()
                        and (not camera or record.camera == camera)
                        and (not plate or plate in normalize_plate(record.plate))
                        and record.direction in ('entry', 'exit')):
                    hours[int(record.time.split(':')[0])][record.direction == 'exit'] += 1
        else:
            conditions = ['captured_at >= %s', 'captured_at < %s']
            params = [day, day + timedelta(days=1)]
            if camera:
                conditions.append('camera_id = %s')
                params.append(camera)
            if plate:
                conditions.append("strpos(regexp_replace(translate(COALESCE(plate_number, ''), %s, %s), '[[:space:]‌-]', '', 'g'), %s) > 0")
                params.extend(['۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك', '01234567890123456789یک', plate])
            with get_connection(connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION READ ONLY')
                    cursor.execute("SET LOCAL statement_timeout = '5s'")
                    cursor.execute("SELECT EXTRACT(HOUR FROM captured_at)::int, "
                                   "count(*) FILTER (WHERE event_type = 'entry'), "
                                   "count(*) FILTER (WHERE event_type = 'exit') FROM event WHERE "
                                   + ' AND '.join(conditions) + ' GROUP BY 1', params)
                    for hour, entries, exits in cursor.fetchall():
                        hours[hour] = [entries, exits]
        return [(hour, *counts) for hour, counts in enumerate(hours)]

    def get_daily_flow(self, end=None, camera="", plate=""):
        """Seven calendar days including end, zero-filled without truncating events."""
        plate = normalize_plate(plate)
        end = end or date.today()
        start = end - timedelta(days=6)
        days = {start + timedelta(days=i): [0, 0] for i in range(7)}
        if MOCK_DATA_ENABLED:
            for record in plate_service._mock_records:
                day = date.fromisoformat(record.date)
                if day in days and (not camera or record.camera == camera) and (not plate or plate in normalize_plate(record.plate)):
                    if record.direction in ('entry', 'exit'):
                        days[day][record.direction == 'exit'] += 1
        else:
            conditions = ["captured_at >= %s", "captured_at < %s"]
            params = [start, end + timedelta(days=1)]
            if camera:
                conditions.append("camera_id = %s")
                params.append(camera)
            if plate:
                conditions.append("strpos(regexp_replace(translate(COALESCE(plate_number, ''), %s, %s), '[[:space:]‌-]', '', 'g'), %s) > 0")
                params.extend(['۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك', '01234567890123456789یک', plate])
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
            records = plate_service._mock_records
            today = date.today().isoformat()
            day = [record for record in records if record.date == today]
            total = len(day)
            unique = len({record.plate for record in day if record.plate != 'خوانده نشد'})
            unread = sum(record.plate == 'خوانده نشد' for record in day)
            valid = [r for r in records if r.plate not in ('خوانده نشد', 'نامطمئن', '')]
            latest = {}
            for record in sorted(valid, key=lambda r: (r.date, r.time)):
                latest[normalize_plate(record.plate)] = record
            inside = sum(r.direction == 'entry' for r in latest.values())
            guests = len({normalize_plate(r.plate) for r in valid if r.date == today and r.access_status == 'guest'})
            blocked = len({normalize_plate(r.plate) for r in valid if r.date == today and r.access_status == 'blocked'})
            allowed_events = sum(r.access_status == 'allowed' for r in day)
            guest_events = sum(r.access_status == 'guest' for r in day)
            blocked_events = sum(r.access_status == 'blocked' for r in day)
        else:
            with get_connection(connect_timeout=5) as connection:
                ensure_schema(connection)
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION READ ONLY')
                    cursor.execute("SET LOCAL statement_timeout = '5s'")
                    cursor.execute('''SELECT count(*), count(DISTINCT plate_number),
                                             count(*) FILTER (WHERE plate_number IS NULL),
                                             count(DISTINCT plate_number) FILTER (WHERE access_status = 'guest'),
                                             count(DISTINCT plate_number) FILTER (WHERE access_status = 'blocked'),
                                             count(*) FILTER (WHERE access_status = 'allowed'),
                                             count(*) FILTER (WHERE access_status = 'guest'),
                                             count(*) FILTER (WHERE access_status = 'blocked')
                                      FROM event
                                      WHERE captured_at >= CURRENT_DATE
                                        AND captured_at < CURRENT_DATE + INTERVAL '1 day' ''')
                    total, unique, unread, guests, blocked, allowed_events, guest_events, blocked_events = cursor.fetchone()
                    cursor.execute("SELECT count(DISTINCT plate_number) FROM vehicle_session WHERE status = 'open'")
                    inside = cursor.fetchone()[0]
        return DashboardStatistics(
            today_total=total, unique_vehicles=unique,
            online_cameras=online, total_cameras=len(cameras),
            alerts=unread + len(cameras) - online,
            inside_vehicles=inside, guest_vehicles=guests, blocked_vehicles=blocked,
            access_counts=(allowed_events, guest_events,
                           total - allowed_events - guest_events - blocked_events, blocked_events),
        )


dashboard_service = DashboardService()
