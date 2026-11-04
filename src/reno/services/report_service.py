"""Filtered traffic queries and streaming Excel export; no UI dependencies."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
import re
import tempfile

from computer_vision_v2.database.connection import get_connection
from computer_vision_v2.database.plate_access import ensure_schema, normalize_plate
from reno.models.plate_record import PlateRecord
from reno.services.xlsx_export import write_xlsx
from reno.ui.vendor.jalaali import Jalaali

@dataclass(frozen=True)
class ReportFilter:
    plate: str = ''
    start: date | None = None
    end: date | None = None

    def __post_init__(self):
        if self.plate.strip() and not normalize_plate(self.plate):
            raise ValueError('شماره پلاک معتبر وارد کنید')
        if self.start and self.end and self.start > self.end:
            raise ValueError('تاریخ شروع نباید بعد از تاریخ پایان باشد')


@dataclass(frozen=True)
class ReportPage:
    records: tuple
    total: int
    offset: int
    limit: int


def conditions(filters):
    clauses, params = [], []
    plate = normalize_plate(filters.plate)
    if plate:
        clauses.append("regexp_replace(translate(COALESCE(plate_number, ''), %s, %s), '[[:space:]‌-]', '', 'g') = %s")
        params.extend(['۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك', '01234567890123456789یک', plate])
    if filters.start:
        clauses.append('captured_at >= %s')
        params.append(datetime.combine(filters.start, time.min).astimezone())
    if filters.end:
        clauses.append('captured_at < %s')
        params.append(datetime.combine(filters.end + timedelta(days=1), time.min).astimezone())
    return (' WHERE ' + ' AND '.join(clauses) if clauses else ''), params


_COLUMNS = 'plate_number, captured_at, camera_id, event_type, class_id, image_path, recognition_status, access_status'
_ORDER = ' ORDER BY captured_at DESC, id DESC'
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def record_from_row(row):
    plate, stamp, camera, direction, class_id, image, status = row[:7]
    stamp = stamp.astimezone()
    if image:
        path = Path(image)
        image = str(path if path.is_absolute() else _PROJECT_ROOT / path)
    return PlateRecord(plate or ('نامطمئن' if status == 'uncertain' else 'خوانده نشد'),
                       stamp.date().isoformat(), stamp.strftime('%H:%M:%S'), camera,
                       class_id=class_id, direction=direction, image_path=image or '',
                       access_status=row[7] if len(row)>7 else 'guest')


class ReportService:
    def __init__(self, connection_factory=None):
        self.connect = connection_factory or get_connection

    def page(self, filters, limit=20, offset=0):
        if limit not in (20,30,50) or offset < 0:
            raise ValueError('Invalid report page bounds')
        where, params = conditions(filters)
        with self.connect() as connection:
            ensure_schema(connection)
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                cursor.execute("SET LOCAL statement_timeout = '5s'")
                cursor.execute('SELECT count(*) FROM event' + where, params)
                total = cursor.fetchone()[0]
                # Deletions may remove the last page between user requests.
                offset = min(offset, ((max(total,1)-1)//limit)*limit)
                cursor.execute('SELECT ' + _COLUMNS + ' FROM event' + where + _ORDER + ' LIMIT %s OFFSET %s',
                               (*params, limit, offset))
                records = tuple(record_from_row(row) for row in cursor.fetchall())
        return ReportPage(records,total,offset,limit)

    def export(self, filters, destination):
        destination = Path(destination).expanduser()
        where, params = conditions(filters)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.xlsx', delete=False) as handle:
                temporary = Path(handle.name)
            with self.connect() as connection:
                ensure_schema(connection)
                with connection.cursor() as setup:
                    setup.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                    setup.execute("SET LOCAL statement_timeout = '30s'")
                with connection.cursor(name='traffic_report_export') as cursor:
                    cursor.execute('SELECT ' + _COLUMNS + ' FROM event' + where + _ORDER, params)
                    def rows():
                        yield ('شماره پلاک','تاریخ شمسی','تاریخ میلادی','ساعت','دوربین','نوع','رویداد','وضعیت پلاک')
                        while batch := cursor.fetchmany(1000):
                            for raw in batch:
                                record = record_from_row(raw)
                                day = date.fromisoformat(record.date)
                                jalali = Jalaali.to_jalaali(day.year,day.month,day.day)
                                yield (record.plate, f"{jalali['jy']:04}/{jalali['jm']:02}/{jalali['jd']:02}",
                                       record.date,record.time,record.camera,record.class_label(),record.direction_label(),record.access_label())
                    count = write_xlsx(temporary, rows())
            temporary.replace(destination)
            return count
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


report_service = ReportService()
