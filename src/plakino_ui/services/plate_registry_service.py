"""Manage current plate permissions; event permissions remain historical snapshots."""
import re
from dataclasses import dataclass
from computer_vision_v2.database.connection import get_connection
from computer_vision_v2.database.plate_access import ensure_schema, normalize_plate


@dataclass(frozen=True)
class RegistryPage:
    plates: tuple
    total: int
    offset: int


class PlateRegistryService:
    def __init__(self,connection_factory=None):
        self.connect=connection_factory or get_connection

    def save(self,plate,permission):
        plate=normalize_plate(plate)
        if not re.fullmatch(r'[0-9]{2}[ء-ی]+(?:[0-9]{3}|[0-9]{5})',plate):
            raise ValueError('پلاک را کامل و با ترتیب دو رقم، حرف، شماره سریال و کد ایران وارد کنید')
        if permission not in ('allowed','blocked','guest'):
            raise ValueError('وضعیت پلاک معتبر نیست')
        with self.connect() as connection:
            ensure_schema(connection)
            with connection.cursor() as cursor:
                if permission=='guest':
                    cursor.execute('DELETE FROM plate_registry WHERE plate_number = %s',(plate,))
                else:
                    cursor.execute('INSERT INTO plate_registry (plate_number,permission) VALUES (%s,%s) ON CONFLICT (plate_number) DO UPDATE SET permission=EXCLUDED.permission', (plate,permission))
        return plate

    def page(self,permission='allowed',offset=0):
        if permission not in ('allowed','blocked','guest') or offset<0:
            raise ValueError('Invalid registry page')
        with self.connect() as connection:
            ensure_schema(connection)
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                cursor.execute("SET LOCAL statement_timeout = '5s'")
                if permission=='guest':
                    query="""WITH observed AS (
                        SELECT regexp_replace(translate(plate_number,'۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك','01234567890123456789یک'),'[[:space:]‌-]','','g') AS plate,
                               max(captured_at) AS seen FROM event WHERE plate_number IS NOT NULL AND class_id=2 GROUP BY 1)
                        SELECT plate,seen FROM observed WHERE NOT EXISTS (SELECT 1 FROM plate_registry WHERE plate_number=observed.plate)"""
                    params=()
                    order=' ORDER BY seen DESC, plate'
                else:
                    query='SELECT plate_number AS plate,registered_at AS seen FROM plate_registry WHERE permission=%s'
                    params=(permission,)
                    order=' ORDER BY seen DESC,plate'
                cursor.execute('SELECT count(*) FROM ('+query+') AS plates',params)
                total=cursor.fetchone()[0]
                offset=min(offset,((max(total,1)-1)//20)*20)
                cursor.execute(query+order+' LIMIT 20 OFFSET %s',(*params,offset))
                return RegistryPage(tuple(row[0] for row in cursor.fetchall()),total,offset)


plate_registry_service=PlateRegistryService()
