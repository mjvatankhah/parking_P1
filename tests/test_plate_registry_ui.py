import unittest
from unittest.mock import patch
from kivy.clock import Clock
from reno.ui import theme
from reno.ui.plate_registration import PlateRegistrationScreen
from reno.services.plate_registry_service import RegistryPage
from reno.models.plate_record import PlateRecord
from reno.ui.components.traffic_record import TrafficRecordRow,detection_header
from reno.ui.components.common import RTLLabel
from reno.ui.components.traffic_chart import TrafficChart


class PlateRegistryUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        theme.register_app_font()

    def test_three_groups_and_save_to_blacklist(self):
        screen=PlateRegistrationScreen(name='plate_registration')
        self.assertEqual(set(screen.tabs),{'allowed','guest','blocked'})
        screen.plate.text='۱۲ب۳۴۵۶۷'
        screen.permission.text=theme.rtl('غیرمجاز')
        with patch('reno.ui.plate_registration.Thread') as thread,patch('reno.ui.plate_registration.plate_registry_service.save') as save,patch.object(screen,'_load'):
            screen._save()
            thread.call_args.kwargs['target']()
            Clock.tick()
            save.assert_called_once_with('۱۲ب۳۴۵۶۷','blocked')
            self.assertEqual(screen.category,'blocked')
        screen.on_leave()

    def test_access_column_is_shared_by_dashboard_and_reports(self):
        header=detection_header()
        self.assertTrue(any(isinstance(w,RTLLabel) and w.text==theme.rtl('وضعیت پلاک') for w in header.children))
        for status,title in (('allowed','مجاز'),('guest','میهمان'),('blocked','غیرمجاز')):
            row=TrafficRecordRow(PlateRecord('12ب34567','2026-11-04','12:00','cam',access_status=status))
            self.assertEqual(row._access_label.text,theme.rtl(title))

    def test_chart_has_two_fading_areas_with_original_data(self):
        chart=TrafficChart(size=(600,320))
        chart.set_metric('both')
        chart.set_data([('2026-11-01',10,5),('2026-11-02',15,20),('2026-11-03',8,12)])
        chart._draw()
        axes=chart._figure.axes[0]
        self.assertEqual(len(axes.images),2)
        self.assertEqual(len(axes.lines),2)
        for image in axes.images:
            alpha=image.get_array()[:,:,3]
            self.assertEqual(float(alpha[0,0]),0)
            self.assertGreater(float(alpha[-1,0]),0)
            self.assertLess(float(alpha[-1,0]),.3)
