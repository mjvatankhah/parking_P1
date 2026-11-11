"""Geometry contracts for the dashboard's status breakdown."""
import unittest
from kivy.clock import Clock
from reno.ui import theme
from reno.ui.components.traffic_breakdown import TrafficBreakdown


class TrafficBreakdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        theme.register_app_font()

    def test_total_stays_at_ring_center_when_panel_moves_and_resizes(self):
        panel = TrafficBreakdown()
        for pos, size in [((83, 117), (760, 350)), ((210, 34), (1100, 350))]:
            panel.pos, panel.size = pos, size
            for _ in range(5):
                Clock.tick()
            ring = panel.ring
            self.assertAlmostEqual(ring.total_label.center_x, ring._image.center_x)
            self.assertEqual(ring.center_text.center, ring._image.center)
            self.assertLess(abs(ring.total_label.center_y - ring._image.center_y), 20)

    def test_three_status_cards_share_a_compact_centered_row(self):
        panel = TrafficBreakdown(size=(760, 350))
        for _ in range(5):
            Clock.tick()
        cards = [value.parent for value in panel.values.values()]
        self.assertEqual(len(cards), 3)
        self.assertEqual(len({round(card.y) for card in cards}), 1)
        self.assertEqual(len({round(card.x) for card in cards}), 3)

        self.assertLess(panel.legend.width, panel.width - 100)
        self.assertAlmostEqual(panel.legend.center_x, panel.center_x)
        ordered = sorted(cards, key=lambda card: card.x)
        for left, right in zip(ordered, ordered[1:]):
            self.assertGreaterEqual(right.x - left.right, 18)

    def test_only_known_statuses_contribute_to_ring_and_total(self):
        panel = TrafficBreakdown()
        panel.set_data((10, 3, 99, 1))
        self.assertEqual(set(panel.values), {'allowed', 'guest', 'blocked'})
        self.assertEqual(panel.ring.counts, (10, 3, 1))
        self.assertEqual(panel.ring.total_label.text, theme.fa_number('14'))
        panel.set_data((0, 0, 99, 0))
        self.assertEqual(panel.ring.counts, (0, 0, 0))
        self.assertEqual(panel.ring.total_label.text, theme.fa_number('0'))
        self.assertTrue(all(value.text == theme.fa_number('0')
                            for value in panel.values.values()))
