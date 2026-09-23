import threading
import time
import unittest
from unittest.mock import Mock, patch

from computer_vision_v2.streaming.Cameras_Manager import CameraManager
from computer_vision_v2.streaming.Streming_Cameras import Frame, StreamManager
from computer_vision_v2.streaming.Source_Base import VideoSource
from computer_vision_v2.reno.models.camera import Camera


class FakeSource:
    def __init__(self, count=8, fps=200, tracker_started=None):
        self.count = count
        self.fps = fps
        self.tracker_started = tracker_started
        self.index = 0
        self.disconnected = False
        self.read_times = []

    def connect(self):
        pass

    def get_fps(self):
        return self.fps

    def get_frame(self):
        if self.index == 1 and self.tracker_started is not None:
            if not self.tracker_started.wait(3):
                raise RuntimeError('Tracker did not start')
        if self.index == self.count:
            return False, None
        self.index += 1
        self.read_times.append(time.monotonic())
        return True, self.index

    def disconnect(self):
        self.disconnected = True


class StreamingTests(unittest.TestCase):
    def test_camera_config_preserves_frame_step(self):
        camera = Camera.from_dict({'id': 'camera', 'type': 'video', 'frame_step': 2})
        self.assertEqual(camera.to_dict()['frame_step'], 2)
        self.assertEqual(Camera.from_dict({'id': 'old-camera'}).frame_step, 0)

    def make_stream(self, tracker, source, frame_step=0):
        with patch('computer_vision_v2.streaming.Streming_Cameras.CameraTracker', return_value=tracker):
            stream = StreamManager('camera', 'unused', 'video', 'unused', frame_step=frame_step)
        stream._creat_source = lambda: source
        return stream

    def test_fixed_step_keeps_every_selected_frame_with_slow_tracker(self):
        for step, expected in ((2, [1, 3, 5, 7]), (3, [1, 4, 7])):
            with self.subTest(step=step):
                calls = []

                def process(frame_idx, ts, image):
                    time.sleep(.02)
                    calls.append(frame_idx)
                    return Frame('camera', frame_idx, ts, image, [])

                source = FakeSource(count=8, fps=1000)
                stream = self.make_stream(Mock(process=process), source, frame_step=step)
                stream.start()
                try:
                    self.assertTrue(stream.read_finished.wait(3))
                    stream.track_thread.join(3)
                    self.assertFalse(stream.track_thread.is_alive())
                    self.assertEqual(calls, expected)
                    self.assertEqual(source.index, 8)
                finally:
                    stream.stop()

    def test_processing_failure_releases_fixed_step_reader(self):
        tracker = Mock()
        tracker.process.side_effect = RuntimeError('inference failed')
        stream = self.make_stream(tracker, FakeSource(), frame_step=2)
        stream.start()
        try:
            self.assertTrue(stream.read_finished.wait(3))
            self.assertTrue(stream.stop_event.is_set())
        finally:
            stream.stop()

    def test_capture_waits_for_warmup_without_consuming_video(self):
        preparing = threading.Event()
        release = threading.Event()
        source = FakeSource(count=1)

        def warmup():
            preparing.set()
            if not release.wait(3):
                raise RuntimeError('Warmup was not released')

        tracker = Mock(warmup=warmup)
        stream = self.make_stream(tracker, source)
        stream.start()
        try:
            self.assertTrue(preparing.wait(3))
            self.assertFalse(stream.model_ready.is_set())
            self.assertIsNone(stream.my_source)
            self.assertEqual(source.index, 0)
            self.assertIsNone(stream.get_latest_raw_frame())
            release.set()
            self.assertTrue(stream.read_finished.wait(3))
            stream.track_thread.join(3)
            self.assertFalse(stream.track_thread.is_alive())
            tracker.process.assert_called_once()
            self.assertEqual(tracker.process.call_args.kwargs['frame_idx'], 1)
        finally:
            release.set()
            stream.stop()

    def test_warmup_failure_stops_waiting_reader(self):
        source = FakeSource()
        tracker = Mock()
        tracker.warmup.side_effect = RuntimeError('model unavailable')
        stream = self.make_stream(tracker, source)
        stream.start()
        try:
            self.assertTrue(stream.read_finished.wait(3))
            self.assertEqual(source.index, 0)
            self.assertFalse(stream.model_ready.is_set())
            tracker.process.assert_not_called()
        finally:
            stream.stop()

    def test_reading_continues_while_tracker_waits_and_skips_old_frames(self):
        started = threading.Event()
        release = threading.Event()
        calls = []

        def process(frame_idx, ts, image):
            calls.append(frame_idx)
            if len(calls) == 1:
                started.set()
                if not release.wait(3):
                    raise RuntimeError('Test did not release tracker')
            return Frame('camera', frame_idx, ts, image, [])

        source = FakeSource(tracker_started=started)
        stream = self.make_stream(Mock(process=process), source)
        stream.start()
        try:
            self.assertTrue(started.wait(3))
            self.assertTrue(stream.read_finished.wait(3))
            # با وجود توقف مدل، دریافت تا آخر فایل پیش رفته است.
            self.assertEqual(stream.get_latest_raw_frame().frame_idx, 8)
            self.assertIsNone(stream.get_latest_frame())
            release.set()
            stream.track_thread.join(3)
            self.assertFalse(stream.track_thread.is_alive())
            self.assertEqual(calls, [1, 8])
            self.assertEqual(stream.get_latest_frame().frame_idx, 8)
            self.assertEqual(stream.get_latest_frame().ts, stream.get_latest_raw_frame().ts)
            self.assertTrue(source.disconnected)
        finally:
            release.set()
            stream.stop()

    def test_video_is_paced_and_stop_interrupts_wait(self):
        source = FakeSource(count=100, fps=10)
        tracker = Mock()
        stream = self.make_stream(tracker, source)
        stream.start()
        try:
            deadline = time.monotonic() + 3
            while source.index < 3 and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertGreaterEqual(source.index, 3)
            self.assertGreaterEqual(source.read_times[2] - source.read_times[0], .18)
        finally:
            stream.stop()
        self.assertTrue(source.disconnected)

    def test_failed_connection_can_be_stopped(self):
        attempted = threading.Event()
        source = Mock()

        def fail():
            attempted.set()
            raise RuntimeError('offline')

        source.connect.side_effect = fail
        stream = self.make_stream(Mock(), source)
        stream.start()
        try:
            self.assertTrue(attempted.wait(3))
        finally:
            stream.stop()
        self.assertTrue(stream.read_finished.is_set())

    def test_raw_and_tracked_results_have_independent_cursors(self):
        manager = CameraManager({})
        raw = Frame('camera', 9, 2, 'raw', [])
        tracked = Frame('camera', 1, 1, 'tracked', [])
        manager.streams['camera'] = Mock(
            get_latest_raw_frame=Mock(return_value=raw),
            get_latest_frame=Mock(return_value=tracked),
        )
        manager.last_idx['camera'] = -1
        manager.last_raw_idx['camera'] = -1
        self.assertEqual(manager.get_all_raw_frames(), [raw])
        self.assertEqual(manager.get_all_frame(), [tracked])
        self.assertEqual(manager.get_all_raw_frames(), [])
        self.assertEqual(manager.get_all_frame(), [])

    def test_invalid_video_fps_has_fallback(self):
        source = VideoSource('unused')
        source.capture = Mock()
        for fps in (0, -1, float('nan'), float('inf')):
            source.capture.get.return_value = fps
            self.assertEqual(source.get_fps(), 25)
        source.capture.get.return_value = 29.97
        self.assertEqual(source.get_fps(), 29.97)


if __name__ == '__main__':
    unittest.main()
