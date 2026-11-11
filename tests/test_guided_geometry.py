"""Guided selection shares the backend schema and preserves unrelated config."""
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np
from computer_vision_v2.Line_Manager.select_line_points import GuidedSelection, Stage
from reno.models.camera import Camera
from reno.services.geometry_service import capture_frame, persist_selection


class GuidedGeometryTests(unittest.TestCase):
    def selection(self):
        selected = GuidedSelection(200, 200)
        selected.click((40,100))
        selected.click((160,100))
        selected.confirm()
        for point in ((10,10), (190,10), (190,190), (10,190)):
            selected.click(point)
        selected.confirm()
        selected.click((80,60))
        return selected

    def test_steps_require_line_then_roi_then_inside(self):
        selection = GuidedSelection(200,200)
        self.assertEqual(selection.stage, Stage.LINE)
        with self.assertRaises(ValueError):
            selection.confirm()
        selection.click((40,100))
        with self.assertRaises(ValueError):
            selection.click((40,100))
        selection.click((160,100))
        selection.confirm()
        self.assertEqual(selection.stage, Stage.ROI)
        for point in ((10,10),(190,10),(190,190),(10,190)):
            selection.click(point)
        selection.confirm()
        self.assertEqual(selection.stage, Stage.SIDE)
        with self.assertRaises(ValueError):
            selection.geometry()
        with self.assertRaises(ValueError):
            selection.click((80,100))
        selection.click((80,60))
        self.assertEqual(selection.geometry()['inside_point'], [.4,.3])

    def test_empty_roi_can_be_skipped_and_saved_as_full_frame(self):
        selection = GuidedSelection(200, 200)
        selection.click((40, 100))
        selection.click((160, 100))
        selection.confirm()
        selection.confirm()
        self.assertEqual(selection.stage, Stage.SIDE)
        selection.click((80, 60))
        self.assertIsNone(selection.geometry()['roi'])

    def test_roi_must_contain_line_and_back_allows_correction(self):
        selection = self.selection()
        selection.back()
        selection.reset_stage()
        for point in ((5,5),(20,5),(20,20)):
            selection.click(point)
        with self.assertRaises(ValueError):
            selection.confirm()
        self.assertIsNone(selection.inside_point)
        self.assertEqual(selection.stage, Stage.ROI)

    def test_atomic_save_and_preview_survive_model_roundtrip(self):
        camera = Camera('دوربین', source='clip.avi').to_dict()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cameras.json'
            path.write_text(json.dumps({'extra':42, 'cameras':[camera, {'id':'other'}]}))
            preview = persist_selection(path, camera, self.selection(), np.zeros((200,200,3),np.uint8))
            saved = json.loads(path.read_text())
            self.assertEqual(saved['extra'],42)
            self.assertEqual(saved['cameras'][1], {'id':'other'})
            self.assertEqual(saved['cameras'][0]['line'], [[.2,.5],[.8,.5]])
            self.assertEqual(saved['cameras'][0]['roi'], [[.05,.05],[.95,.05],[.95,.95],[.05,.95]])
            self.assertEqual(Camera.from_dict(saved['cameras'][0]).to_dict()['geometry_preview'],preview)
            self.assertTrue(cv2.imread(preview).any())

    def test_source_change_rejects_save_without_leaving_a_preview(self):
        camera = Camera('cam',source='old.avi').to_dict()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cameras.json'
            data = {'cameras':[dict(camera,source='new.avi')]}
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                persist_selection(path,camera,self.selection(),np.zeros((200,200,3),np.uint8))
            self.assertEqual(json.loads(path.read_text()),data)
            self.assertFalse(list((Path(folder)/'geometry_previews').glob('*.png')))

    def test_capture_reads_real_video_in_bounded_child_process(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'clip.avi')
            writer = cv2.VideoWriter(path,cv2.VideoWriter_fourcc(*'MJPG'),25,(200,200))
            self.assertTrue(writer.isOpened())
            writer.write(np.zeros((200,200,3),np.uint8))
            writer.release()
            frame = capture_frame(Camera('cam',source_type='video',source=path).to_dict())
            self.assertEqual(frame.shape,(200,200,3))

    def test_roi_draws_closed_shape_only_after_four_corners_and_rejects_fifth(self):
        from computer_vision_v2.Line_Manager.select_line_points import annotated_frame
        selection = GuidedSelection(200,200)
        selection.click((40,100))
        selection.click((160,100))
        selection.confirm()
        frame = np.zeros((200,200,3),np.uint8)
        for point in ((10,10),(190,10),(190,190)):
            selection.click(point)
            self.assertFalse(annotated_frame(frame,selection)[10,100].any())
        with self.assertRaises(ValueError):
            selection.confirm()
        selection.click((10,190))
        image = annotated_frame(frame,selection)
        self.assertTrue(image[10,100].any())
        self.assertTrue(image[100,10].any())
        before = list(selection.roi)
        with self.assertRaises(ValueError):
            selection.click((100,150))
        self.assertEqual(selection.roi,before)
        self.assertEqual(selection.stage,Stage.ROI)
        selection.confirm()
        self.assertEqual(selection.stage,Stage.SIDE)

    def test_parking_arrow_is_local_and_independent_of_reference_line(self):
        from unittest.mock import patch
        from computer_vision_v2.Line_Manager.select_line_points import annotated_frame
        selection = self.selection()
        frame = np.zeros((200,200,3),np.uint8)
        starts = []
        for line in ([(40,100),(160,100)], [(20,150),(180,150)]):
            selection.line = line
            with patch('computer_vision_v2.Line_Manager.select_line_points.cv2.arrowedLine', wraps=cv2.arrowedLine) as arrow:
                annotated_frame(frame,selection)
                start, end = arrow.call_args.args[1:3]
                self.assertEqual(end,tuple(selection.inside_point))
                self.assertNotIn(start,line)
                starts.append(start)
        self.assertEqual(starts[0],starts[1])
