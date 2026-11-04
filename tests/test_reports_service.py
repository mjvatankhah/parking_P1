import tempfile
from pathlib import Path
from datetime import date, datetime, timezone
from unittest.mock import MagicMock
import unittest
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from reno.services.report_service import ReportService,ReportFilter,conditions,normalize_plate
from reno.services.xlsx_export import write_xlsx

ROW=('12ب34567',datetime(2026,11,4,12,30,tzinfo=timezone.utc),'gate-camera','entry',2,None,'read')


class ReportServiceTests(unittest.TestCase):
    def connection(self):
        factory=MagicMock()
        connection=factory.return_value.__enter__.return_value
        cursor=connection.cursor.return_value.__enter__.return_value
        return ReportService(factory),connection,cursor

    def test_combined_filters_are_parameterized_and_end_date_inclusive(self):
        filters=ReportFilter('۱۲ ب ۳۴۵۶۷',date(2026,11,1),date(2026,11,4))
        where,params=conditions(filters)
        self.assertEqual(where.count(' AND '),2)
        self.assertNotIn('۱۲',where)
        self.assertEqual(params[2],'12ب34567')
        self.assertEqual(params[-1].date(),date(2026,11,5))
        self.assertEqual(params[-2].date(),date(2026,11,1))
        self.assertEqual(normalize_plate('١٢ب٣٤٥٦٧'),'12ب34567')
        self.assertEqual(normalize_plate('۱۲ي۳۴۵۶۷'),'12ی34567')

    def test_bad_dates_are_rejected(self):
        with self.assertRaises(ValueError):
            ReportFilter(start=date(2026,11,4),end=date(2026,11,1))

    def test_latest_twenty_and_all_pagination_bounds(self):
        service,connection,cursor=self.connection()
        cursor.fetchone.return_value=(85,)
        cursor.fetchall.return_value=[ROW]
        page=service.page(ReportFilter(),20)
        self.assertEqual(page.total,85)
        self.assertEqual(page.records[0].plate,'12ب34567')
        self.assertEqual(cursor.execute.call_args.args[1],(20,0))
        service.page(ReportFilter(),30,30)
        self.assertEqual(cursor.execute.call_args.args[1],(30,30))
        page=service.page(ReportFilter(),30,90)
        self.assertEqual(page.offset,60)
        self.assertEqual(cursor.execute.call_args.args[1],(30,60))

    def test_export_streams_every_filtered_row_without_limit_and_is_atomic(self):
        service,connection,cursor=self.connection()
        cursor.fetchmany.side_effect=[[ROW]*30,[ROW]*7,[]]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'report.xlsx'
            count=service.export(ReportFilter(plate='۱۲ب۳۴۵۶۷'),path)
            self.assertEqual(count,37)
            select=next(call.args for call in cursor.execute.call_args_list if str(call.args[0]).startswith('SELECT'))
            self.assertNotIn('LIMIT',select[0])
            self.assertEqual(select[1][-1],'12ب34567')
            with ZipFile(path) as archive:
                for name in archive.namelist():
                    ET.fromstring(archive.read(name))
                root=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
                ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                self.assertEqual(len(root.findall('s:sheetData/s:row',ns)),38)
                self.assertEqual(root.find('s:sheetViews/s:sheetView',ns).get('rightToLeft'),'1')
            self.assertEqual(list(Path(folder).iterdir()),[path])

    def test_export_failure_preserves_existing_file_and_cleans_temp(self):
        service,connection,cursor=self.connection()
        cursor.fetchmany.side_effect=OSError('db error')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'report.xlsx'
            path.write_bytes(b'previous')
            with self.assertRaises(OSError):
                service.export(ReportFilter(),path)
            self.assertEqual(path.read_bytes(),b'previous')
            self.assertEqual(list(Path(folder).iterdir()),[path])

    def test_formula_like_camera_names_stay_text_and_xml_is_escaped(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'safe.xlsx'
            write_xlsx(path,[['عنوان']*7,['=1+2','<الف & ب>','00123','','','','']])
            with ZipFile(path) as archive:
                root=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
                self.assertNotIn('<f>',archive.read('xl/worksheets/sheet1.xml').decode())
                values=[node.text for node in root.iter() if node.tag.endswith('}t')]
                self.assertIn('=1+2',values)
                self.assertIn('<الف & ب>',values)
                self.assertIn('00123',values)
