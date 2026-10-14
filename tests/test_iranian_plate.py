"""Plate display must retain the OCR's physical order inside Persian pages."""
import unittest
from kivy.clock import Clock
from reno.ui.theme import register_app_font
from reno.ui.components.iranian_plate import IranianPlate, plate_segments


class IranianPlateTests(unittest.TestCase):
    def test_segments_preserve_digits_and_optional_region(self):
        for text, expected in [
            ('۱۲ ب ۳۴۵ ۶۷', ('۱۲', 'ب', '۳۴۵', '۶۷')),
            ('12الف34567', ('12', 'الف', '345', '67')),
            ('١٢ب٣٤٥٦٧', ('١٢', 'ب', '٣٤٥', '٦٧')),
            ('12ب345', ('12', 'ب', '345', None)),
        ]:
            self.assertEqual(plate_segments(text), expected)
        self.assertIsNone(plate_segments('خوانده نشد'))
        self.assertIsNone(plate_segments(''))

    def test_plate_segments_keep_physical_order_after_resize(self):
        register_app_font()
        plate = IranianPlate('۱۲ب۳۴۵۶۷', size_hint=(None, None))
        for position, size in [((20, 50), (240, 36)), ((400, 100), (320, 40))]:
            plate.pos, plate.size = position, size
            for _ in range(4):
                Clock.tick()
            flag, left, letter, serial, region = reversed(plate.children)
            self.assertLess(flag.x, left.x)
            self.assertLess(left.x, letter.x)
            self.assertLess(letter.x, serial.x)
            self.assertLess(serial.x, region.x)
            self.assertEqual(left.text, '۱۲')
            self.assertEqual(serial.text, '۳۴۵')


if __name__ == '__main__':
    unittest.main()
