import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from computer_vision_v2.Line_Manager.select_line_points import (
    Selection, Stage, draw_frame, save_geometry,
)


class LineSelectionTests(unittest.TestCase):
    def selection(self):
        selection = Selection(200, 200)
        for point in ((0, 0), (199, 0), (199, 199), (0, 199)):
            selection.click(point)
        selection.confirm()
        selection.click((40, 100))
        selection.click((100, 100))
        return selection

    def test_straight_line_save_advances_to_side_without_consuming_point(self):
        selection = self.selection()
        self.assertEqual(selection.stage, Stage.LINE)
        selection.confirm()
        self.assertEqual(selection.stage, Stage.SIDE)
        selection.click((70, 50))
        self.assertEqual(selection.geometry()['line'], [[.2, .5], [.5, .5]])
        self.assertEqual(selection.geometry()['inside_point'], [.35, .25])

    def test_third_vertex_automatically_confirms_l(self):
        selection = self.selection()
        selection.click((100, 160))
        self.assertEqual(selection.stage, Stage.SIDE)
        self.assertIsNone(selection.inside_point)
        with self.assertRaises(ValueError):
            selection.geometry()
        selection.click((60, 140))
        self.assertEqual(len(selection.geometry()['line']), 3)

    def test_invalid_clicks_allow_retry(self):
        selection = self.selection()
        with self.assertRaises(ValueError):
            selection.click((100, 100))
        self.assertEqual(len(selection.line), 2)
        selection.confirm()
        with self.assertRaises(ValueError):
            selection.click((70, 100))
        selection.click((70, 60))
        self.assertIsNotNone(selection.inside_point)

    def test_outside_selection_reverses_both_l_sides(self):
        selection = self.selection()
        selection.click((100, 160))
        selection.set_side_mode(True)
        selection.click((150, 50))
        x, y = selection.inside_point
        self.assertLess(x, 100)
        self.assertGreater(y, 100)
        selection.set_side_mode(False)
        self.assertIsNone(selection.inside_point)

    def test_animation_changes_frame_without_modifying_original(self):
        selection = self.selection()
        selection.confirm()
        original = np.zeros((200, 200, 3), np.uint8)
        first = draw_frame(original, selection, (120, 150), timestamp=0)
        second = draw_frame(original, selection, (120, 150), timestamp=.3)
        self.assertFalse(np.array_equal(first, second))
        self.assertFalse(original.any())

    def test_save_preserves_other_settings_and_rejects_changed_camera(self):
        selection = self.selection()
        selection.confirm()
        selection.click((70, 50))
        camera = dict(id='cam', source='video.mp4', type='video', dir='entry_exit')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cameras.json'
            path.write_text(json.dumps(dict(cameras=[camera], extra=42)))
            save_geometry(path, camera, selection)
            saved = json.loads(path.read_text())
            self.assertEqual(saved['extra'], 42)
            self.assertEqual(saved['cameras'][0]['line'], [[.2, .5], [.5, .5]])
            saved['cameras'][0]['source'] = 'other.mp4'
            path.write_text(json.dumps(saved))
            with self.assertRaises(ValueError):
                save_geometry(path, camera, selection)
            self.assertEqual(json.loads(path.read_text()), saved)


if __name__ == '__main__':
    unittest.main()
