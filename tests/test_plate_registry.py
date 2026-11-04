from pathlib import Path
import unittest
from unittest.mock import MagicMock,patch
from reno.services.plate_registry_service import PlateRegistryService
from reno.services.report_service import record_from_row
from datetime import datetime,timezone


class PlateRegistryTests(unittest.TestCase):
    def setUp(self):
        self.connect=MagicMock()
        self.cursor=self.connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.service=PlateRegistryService(self.connect)
        self.schema=patch('reno.services.plate_registry_service.ensure_schema')
        self.schema.start()
        self.addCleanup(self.schema.stop)

    def test_save_normalizes_plate_and_only_changes_registry(self):
        self.assertEqual(self.service.save('۱۲ ب ۳۴۵۶۷','blocked'),'12ب34567')
        query,params=self.cursor.execute.call_args.args
        self.assertIn('ON CONFLICT',query)
        self.assertEqual(params,('12ب34567','blocked'))
        self.assertNotIn('event',query)
        self.service.save('12ب34567','allowed')
        self.assertEqual(self.cursor.execute.call_args.args[1],('12ب34567','allowed'))

    def test_guest_removes_registration_without_changing_events(self):
        self.service.save('12ب34567','guest')
        query,params=self.cursor.execute.call_args.args
        self.assertTrue(query.startswith('DELETE FROM plate_registry'))
        self.assertEqual(params,('12ب34567',))

    def test_invalid_plate_or_category_never_opens_database(self):
        for plate,permission in (('','allowed'),('abc','blocked'),('12ب34567','other')):
            with self.assertRaises(ValueError):
                self.service.save(plate,permission)
        self.connect.assert_not_called()

    def test_guest_group_is_observed_plates_absent_from_registry_and_paginated(self):
        self.cursor.fetchone.return_value=(45,)
        self.cursor.fetchall.return_value=[('12ب34567',None)]
        result=self.service.page('guest',20)
        self.assertEqual(result.total,45)
        self.assertEqual(result.plates,('12ب34567',))
        query,params=self.cursor.execute.call_args.args
        self.assertIn('NOT EXISTS',query)
        self.assertIn('LIMIT 20 OFFSET %s',query)
        self.assertEqual(params,(20,))

    def test_event_reader_preserves_historical_status(self):
        raw=('12ب34567',datetime.now(timezone.utc),'cam','entry',2,None,'read','blocked')
        record=record_from_row(raw)
        self.assertEqual(record.access_status,'blocked')
        self.assertEqual(record.access_label(),'غیرمجاز')
        unknown=record_from_row((*raw[:7],'unknown'))
        self.assertEqual(unknown.access_label(),'نامشخص')
