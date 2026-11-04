import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
from kivy.clock import Clock
from kivy.core.window import Window
from reno.ui.theme import register_app_font
from reno.ui.components.geometry_dialog import GeometryDialog, DrawingImage, frame_texture
from reno.models.camera import Camera
from computer_vision_v2.Line_Manager.select_line_points import Stage


class GeometryDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        register_app_font()

    def test_click_coordinates_account_for_letterboxing(self):
        image = DrawingImage(size_hint=(None,None),size=(400,400),pos=(20,30),fit_mode='contain')
        image.texture = frame_texture(np.zeros((100,200,3),np.uint8))
        Clock.tick()
        self.assertIsNone(image.source_point(30,40))
        self.assertEqual(image.source_point(220,230),(100,50))
        self.assertEqual(image.source_point(20,330),(0,0))
        self.assertEqual(image.source_point(420,130),(199,99))

    def test_complete_wizard_saves_only_on_final_submit(self):
        camera = Camera('cam',source='clip.avi').to_dict()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'cameras.json'
            path.write_text(json.dumps({'cameras':[camera]}))
            saved = Mock()
            dialog = GeometryDialog(camera,path,saved)
            dialog._loaded(np.zeros((200,200,3),np.uint8))
            dialog._point((40,100))
            dialog._point((160,100))
            dialog._advance()
            self.assertEqual(dialog.selection.stage,Stage.ROI)
            for point in ((10,10),(190,10),(190,190),(10,190)):
                dialog._point(point)
            dialog._advance()
            self.assertEqual(dialog.selection.stage,Stage.SIDE)
            self.assertIsNone(json.loads(path.read_text())['cameras'][0]['roi'])
            dialog._point((80,60))
            with patch('reno.ui.components.geometry_dialog.Thread') as worker:
                dialog._advance()
                worker.call_args.kwargs['target']()
            Clock.tick()
            saved.assert_called_once()
            self.assertEqual(json.loads(path.read_text())['cameras'][0]['inside_point'],[.4,.3])
            self.assertTrue(Path(saved.call_args.args[0]).is_file())

    def test_cancel_does_not_save_and_late_capture_is_ignored(self):
        saved=Mock()
        dialog=GeometryDialog(Camera('cam').to_dict(),Path('/tmp/unused.json'),saved)
        dialog._dismissed()
        dialog._loaded(np.zeros((200,200,3),np.uint8))
        self.assertIsNone(dialog.selection)
        saved.assert_not_called()
