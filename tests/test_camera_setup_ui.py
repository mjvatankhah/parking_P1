"""Settings must validate the gate and publish configuration only after a good probe."""
import unittest
from unittest.mock import patch
from reno.ui.theme import register_app_font
from reno.ui.camera_settings import CameraSettingsScreen
from reno.services.camera_service import camera_service
from reno.services.camera_setup_service import CameraSetupResult
from reno.models.camera import Camera


class CameraSetupUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        register_app_font()

    def setUp(self):
        self.screen = CameraSettingsScreen(name='camera_settings')
        self.addCleanup(self._close_popup)
        self.addCleanup(camera_service.unsubscribe, self.screen._on_cameras_changed)
        self.addCleanup(camera_service.unsubscribe_status, self.screen._on_camera_status_changed)

    def _close_popup(self):
        if self.screen._connection_popup:
            self.screen._connection_popup.dismiss()

    def test_gate_required_before_any_worker_starts(self):
        self.screen._id_input.text = 'دوربین'
        self.screen._source_input.text = 'rtsp://127.0.0.1/live'
        with patch('reno.ui.camera_settings.Thread') as worker:
            self.screen._save()
            worker.assert_not_called()
            self.assertTrue(self.screen._error_label.text)

    def test_check_is_background_and_repeated_click_is_ignored(self):
        self.screen._gate_input.text = 'ورودی'
        self.screen._id_input.text = 'دوربین تست جدید'
        self.screen._source_input.text = 'rtsp://127.0.0.1/live'
        with patch('reno.ui.camera_settings.Thread') as worker:
            self.screen._save()
            self.screen._save()
            worker.assert_called_once()
            self.assertTrue(self.screen._checking)
            self.assertTrue(self.screen._form_card.disabled)

    def test_probe_failure_does_not_publish_camera(self):
        with patch.object(camera_service, 'add_camera') as add:
            self.screen._setup_finished(Camera('test'), True, CameraSetupResult(False, 'اتصال ناموفق', True))
            add.assert_not_called()
            self.assertFalse(self.screen._checking)
            self.assertFalse(self.screen._form_card.disabled)

    def test_success_publishes_gate_mapping_and_keeps_form_for_geometry(self):
        camera = Camera('دوربین', source='rtsp://127.0.0.1/live', gate_id='ورودی')
        with patch.object(camera_service, 'add_camera') as add, patch('reno.ui.camera_settings.show_toast'):
            self.screen._setup_finished(camera, True, CameraSetupResult(True, 'موفق', True))
            add.assert_called_once_with(camera)
            self.assertEqual(self.screen._editing_camera_id, camera.id)
            self.assertEqual(self.screen._gate_input.text, 'ورودی')

    def test_equal_names_show_error_before_worker(self):
        self.screen._gate_input.text = 'ورودی'
        self.screen._id_input.text = ' ورودی '
        self.screen._source_input.text = 'rtsp://127.0.0.1/live'
        with patch('reno.ui.camera_settings.Thread') as worker:
            self.screen._save()
            worker.assert_not_called()
            self.assertTrue(self.screen._error_label.text)

    def test_edit_displays_actual_stored_gate_name(self):
        self.screen._start_edit_mode(Camera('دوربین', gate_id='gate:نام ثبت‌شده'))
        self.assertEqual(self.screen._gate_input.text, 'gate:نام ثبت‌شده')

    def test_connection_button_is_below_source_with_picker_at_right(self):
        source_row = self.screen._source_input.parent
        self.assertIs(source_row.children[0], self.screen._source_picker_button)
        self.assertIs(self.screen._connection_button.parent.parent, source_row.parent)
        self.assertIs(source_row.parent.children[-1], source_row)
        self.assertFalse(hasattr(self.screen, '_line_inputs'))
        self.assertFalse(hasattr(self.screen, '_inside_point_inputs'))

    def test_result_waits_for_okay_for_all_outcomes(self):
        from reno.ui import theme
        from reno.ui.components.common import PrimaryButton
        for success, message in ((True, 'اتصال برقرار شد'), (False, 'دوربین ثبت شد ولی اتصال برقرار نشد')):
            with self.subTest(success=success):
                self.screen._show_connection_result(message, success)
                popup = self.screen._connection_popup
                self.assertFalse(popup.auto_dismiss)
                labels = [w for w in popup.content.walk() if getattr(w, 'text', '') == theme.rtl(message)]
                self.assertEqual(len(labels), 1)
                okay = next(w for w in popup.content.walk() if isinstance(w, PrimaryButton))
                self.assertEqual(okay.text, theme.rtl('باشه'))
                with patch.object(popup, 'dismiss') as dismiss:
                    okay.dispatch('on_release')
                    dismiss.assert_called_once()

    def test_geometry_locked_initially_and_after_failure(self):
        self.assertEqual(self.screen._connection_state, 'initial')
        self.assertTrue(self.screen._geometry_button.disabled)
        self.assertIsNone(self.screen._geometry_details.parent)
        with patch('reno.ui.camera_settings.GeometryDialog') as dialog:
            self.screen._select_geometry()
            dialog.assert_not_called()
        with patch.object(self.screen, '_show_connection_result'):
            self.screen._connection_checked(CameraSetupResult(False, 'خطا'), self.screen._settings_key())
        self.assertEqual(self.screen._connection_state, 'failed')
        self.assertTrue(self.screen._geometry_button.disabled)
        color = self.screen._connection_button.bg_color_normal
        self.assertGreater(color[0], color[1])

    def test_success_unlocks_geometry_and_source_change_invalidates_it(self):
        camera = Camera('cam', source='rtsp://127.0.0.1/live', gate_id='ورودی')
        with patch.object(camera_service,'add_camera'), patch.object(self.screen,'_show_connection_result'):
            self.screen._setup_finished(camera, True, CameraSetupResult(True, 'موفق', True))
            self.screen._connection_checked(CameraSetupResult(True,'اتصال برقرار شد'), self.screen._settings_key())
        self.assertEqual(self.screen._connection_state, 'success')
        self.assertFalse(self.screen._geometry_button.disabled)
        self.assertGreater(self.screen._connection_button.bg_color_normal[1], self.screen._connection_button.bg_color_normal[0])
        with patch.object(camera_service,'get_camera',return_value=camera), patch('reno.ui.camera_settings.GeometryDialog') as dialog:
            self.screen._select_geometry()
            dialog.return_value.open.assert_called_once()
        self.screen._source_input.text = 'rtsp://127.0.0.1/other'
        self.assertEqual(self.screen._connection_state, 'initial')
        self.assertTrue(self.screen._geometry_button.disabled)
        self.assertIsNone(self.screen._verified_settings)

    def test_each_registration_field_invalidates_previous_check(self):
        camera = Camera('cam', source='rtsp://127.0.0.1/live', gate_id='ورودی')
        for field, value in ((self.screen._gate_input,'خروجی'), (self.screen._role_spinner,'changed'),
                             (self.screen._source_type_spinner,'changed'), (self.screen._id_input,'other')):
            with patch.object(camera_service,'add_camera'), patch.object(self.screen,'_show_connection_result'):
                self.screen._setup_finished(camera,True,CameraSetupResult(True,'موفق',True))
                self.screen._connection_checked(CameraSetupResult(True,'اتصال برقرار شد'),self.screen._settings_key())
            field.text = value
            self.assertEqual(self.screen._connection_state,'initial')
            self.assertTrue(self.screen._geometry_button.disabled)

    def test_preview_and_saved_message_only_appear_after_save_below_button(self):
        import tempfile
        from pathlib import Path
        import cv2
        import numpy as np
        from reno.ui import theme
        self.assertIsNone(self.screen._geometry_details.parent)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'preview.png'
            cv2.imwrite(str(path), np.zeros((48,64,3),np.uint8))
            with patch.object(camera_service,'reload'), patch('reno.ui.camera_settings.Clock.schedule_once') as schedule:
                self.screen._geometry_saved(str(path))
            self.assertIsNone(self.screen._geometry_details.parent)
            schedule.call_args.args[0](0)
            popup=self.screen._connection_popup
            self.assertFalse(popup.auto_dismiss)
            from reno.ui.components.common import PrimaryButton
            okay=next(w for w in popup.content.walk() if isinstance(w,PrimaryButton))
            okay.dispatch('on_release')
            self.assertIs(self.screen._geometry_details.parent,self.screen._geometry_section)
            self.assertIs(self.screen._geometry_section.children[-1],self.screen._geometry_button)
            self.assertEqual(self.screen._geometry_hint.text,theme.rtl('مختصات ثبت شد'))
            self.screen._start_add_mode()
            self.assertIsNone(self.screen._geometry_details.parent)
            self.assertEqual(self.screen._geometry_preview.source,'')

    def test_save_never_checks_connection_and_keeps_drawing_locked(self):
        from kivy.clock import Clock
        self.screen._gate_input.text = 'ورودی'
        self.screen._id_input.text = 'دوربین جدید'
        self.screen._source_input.text = 'rtsp://192.0.2.1/offline'
        with patch('reno.ui.camera_settings.Thread') as worker, \
             patch('reno.ui.camera_settings.register_camera', return_value=CameraSetupResult(True,'ثبت شد',True)) as register, \
             patch('reno.ui.camera_settings.check_connection') as check, \
             patch.object(camera_service,'add_camera'), patch.object(self.screen,'_show_connection_result'):
            self.screen._save()
            worker.call_args.kwargs['target']()
            Clock.tick()
            register.assert_called_once()
            check.assert_not_called()
        self.assertEqual(self.screen._connection_state,'initial')
        self.assertTrue(self.screen._geometry_button.disabled)

    def test_check_button_probes_saved_camera_without_registration(self):
        from kivy.clock import Clock
        camera=Camera('cam',source='rtsp://127.0.0.1/live',gate_id='گیت')
        self.screen._start_edit_mode(camera)
        with patch.object(camera_service,'get_camera',return_value=camera), \
             patch('reno.ui.camera_settings.Thread') as worker, \
             patch('reno.ui.camera_settings.register_camera') as register, \
             patch('reno.ui.camera_settings.check_connection',return_value=CameraSetupResult(True,'متصل')) as check, \
             patch.object(self.screen,'_show_connection_result'):
            self.screen._check_connection()
            worker.call_args.kwargs['target']()
            Clock.tick()
            register.assert_not_called()
            check.assert_called_once_with(camera)
        self.assertFalse(self.screen._geometry_button.disabled)

    def test_status_cells_are_colored_text_without_badges(self):
        from reno.ui.components.common import RTLLabel, Badge
        from reno.models.camera import STATUS_ONLINE, STATUS_OFFLINE
        from reno.ui import theme
        for state,color in ((STATUS_ONLINE,'#36B37E'),(STATUS_OFFLINE,'#F87171')):
            camera=Camera('cam',status=state)
            row=self.screen._build_table_row(camera)
            self.assertFalse(any(isinstance(w,Badge) for w in row.walk()))
            label=next(w for w in row.children if isinstance(w,RTLLabel) and w.text==theme.rtl(camera.status_label()))
            self.assertEqual(tuple(label.color),theme.rgba(color))

    def test_operations_column_is_leftmost_and_icons_are_centered(self):
        from kivy.clock import Clock
        from reno.ui import theme
        from reno.ui.camera_settings import _IconOnlyButton
        header=self.screen._build_table_header()
        row=self.screen._build_table_row(Camera('cam'))
        header.size=(800,36)
        row.size=(800,46)
        for _ in range(3):
            Clock.tick()
        self.assertEqual(header.children[-1].text,theme.rtl('عملیات'))
        operations=row.children[-1]
        self.assertAlmostEqual(operations.center_x,header.children[-1].center_x,delta=1)
        icons=[w for w in operations.walk() if isinstance(w,_IconOnlyButton)]
        self.assertEqual(len(icons),2)
        center=(min(w.x for w in icons)+max(w.right for w in icons))/2
        self.assertAlmostEqual(center,operations.center_x,delta=1)
        self.assertTrue(all(abs(w.center_y-operations.center_y)<=1 for w in icons))

    def test_geometry_button_spans_form_and_preview_and_register_are_below(self):
        from kivy.clock import Clock
        from reno.ui.components.common import RTLLabel, PrimaryButton
        from reno.ui import theme
        self.screen._geometry_section.size=(800,46)
        for _ in range(3):
            Clock.tick()
        button=self.screen._geometry_button
        self.assertEqual(button.size_hint_x,1)
        self.assertAlmostEqual(button.width,self.screen._geometry_section.width,delta=1)
        label=next(w for w in button.walk() if isinstance(w,RTLLabel))
        self.assertEqual(label.halign,'center')
        self.assertEqual(self.screen._geometry_preview.pos_hint,{'center_x':.5})
        footer=self.screen._form_card.children[0]
        self.assertTrue(any(isinstance(w,PrimaryButton) and w.text==theme.rtl('ثبت دوربین') for w in footer.walk()))

    def test_geometry_caption_stays_inside_button_when_form_moves(self):
        from kivy.clock import Clock
        from reno.ui.components.common import RTLLabel
        self.screen.size=(1200,900)
        button=self.screen._geometry_button
        self.screen._geometry_section.pos=(80,240)
        self.screen._geometry_section.size=(800,46)
        for _ in range(4):
            Clock.tick()
        label=next(w for w in button.walk() if isinstance(w,RTLLabel))
        self.assertAlmostEqual(label.center_x,button.center_x,delta=1)
        self.assertAlmostEqual(label.center_y,button.center_y,delta=1)
        label.texture_update()
        self.assertGreater(label.texture_size[0],0)
