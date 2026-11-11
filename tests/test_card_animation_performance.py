"""Animating a border should change UVs without rebuilding its shape."""
import unittest
from unittest.mock import patch
from reno.ui.components.common import Card


class CardAnimationPerformanceTests(unittest.TestCase):
    def test_phase_reuses_geometry_but_resize_rebuilds_it(self):
        card = Card(size=(280, 118), animated_border=True,
                    border_gradient=('#39F5D0', '#247DAD'))
        try:
            before = list(card._frame.vertices)
            with patch('reno.ui.components.common.math.cos', wraps=__import__('math').cos) as cosine:
                card._border_phase = 1
                self.assertEqual(cosine.call_count, 0)
                after = list(card._frame.vertices)
                self.assertEqual(before[0::4], after[0::4])
                self.assertEqual(before[1::4], after[1::4])
                self.assertNotEqual(before[3::4], after[3::4])
                card.width += 20
                self.assertGreater(cosine.call_count, 0)
        finally:
            card._border_animation.cancel()
