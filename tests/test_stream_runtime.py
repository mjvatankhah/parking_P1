"""Lifecycle tests for live capture without a camera or model files."""

import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from computer_vision_v2.streaming.Streming_Cameras import StreamManager


class FakeTracker:
    def __init__(self):
        self.seen = []
        self.first_started = threading.Event()
        self.release_first = threading.Event()

    def process(self, frame_idx, ts, image):
        self.seen.append(frame_idx)
        if len(self.seen) == 1:
            self.first_started.set()
            self.release_first.wait(2)
        return SimpleNamespace(camera_id="cam", frame_idx=frame_idx, ts=ts,
                               image=image, detections=[])


class StreamRuntimeTests(unittest.TestCase):
    def test_stalled_rtsp_releases_connection_after_first_failed_read(self):
        with patch("computer_vision_v2.streaming.Streming_Cameras.CameraTracker"):
            stream = StreamManager("cam", "rtsp://camera", "rtsp", "unused")

        class StalledSource:
            reads = 0
            released = False

            def connect(self):
                pass

            def get_frame(self):
                self.reads += 1
                return False, None

            def disconnect(self):
                self.released = True

        source = StalledSource()
        stream._create_source = lambda: source

        def stop_at_reconnect(delay):
            if delay >= 1:
                stream._stop.set()
                return True
            return False

        with patch.object(stream._stop, "wait", side_effect=stop_at_reconnect), \
             self.assertLogs("computer_vision_v2.streaming.Streming_Cameras", level="WARNING"):
            stream._capture_loop()
        self.assertTrue(source.released)
        self.assertEqual(source.reads, 1)

    def wait_until(self, condition, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return True
            time.sleep(0.01)
        return False

    def test_rtsp_capture_keeps_only_latest_frame_while_tracking_is_busy(self):
        tracker = FakeTracker()
        with patch("computer_vision_v2.streaming.Streming_Cameras.CameraTracker", return_value=tracker):
            stream = StreamManager("cam", "rtsp://camera", "rtsp", "unused")

        class Source:
            def __init__(self):
                self.reads = 0

            def connect(self):
                pass

            def get_frame(self):
                self.reads += 1
                if self.reads == 1:
                    return True, 1
                if self.reads <= 10:
                    tracker.first_started.wait(2)
                    return True, self.reads
                stream._stop.wait(2)
                return False, None

            def disconnect(self):
                pass

        source = Source()
        stream._create_source = lambda: source
        try:
            stream.start()
            self.assertTrue(tracker.first_started.wait(2))
            self.assertTrue(self.wait_until(lambda: source.reads >= 10))
            tracker.release_first.set()
            self.assertTrue(self.wait_until(lambda: tracker.seen == [1, 10]))
            result = stream.get_latest_frame()
            self.assertEqual(result.frame_idx, 10)
            self.assertGreater(result.ts, 0)
        finally:
            tracker.release_first.set()
            stream.stop()

    def test_failed_connection_and_failed_read_both_reconnect(self):
        tracker = FakeTracker()
        tracker.release_first.set()
        with patch("computer_vision_v2.streaming.Streming_Cameras.CameraTracker", return_value=tracker), \
             patch("computer_vision_v2.streaming.Streming_Cameras.MAX_READ_FAILURES", 1):
            stream = StreamManager("cam", "rtsp://camera", "rtsp", "unused")

            class Source:
                def __init__(self, fail_connect=False, yield_frame=False):
                    self.fail_connect = fail_connect
                    self.yield_frame = yield_frame
                    self.calls = 0

                def connect(self):
                    if self.fail_connect:
                        raise ConnectionError("unreachable")

                def get_frame(self):
                    self.calls += 1
                    if self.yield_frame and self.calls == 1:
                        return True, 1
                    if self.yield_frame:
                        stream._stop.wait(2)
                    return False, None

                def disconnect(self):
                    pass

            sources = [Source(fail_connect=True), Source(), Source(yield_frame=True)]
            attempts = []

            def new_source():
                attempts.append(time.monotonic())
                return sources[min(len(attempts) - 1, 2)]

            stream._create_source = new_source
            try:
                stream.start()
                self.assertTrue(self.wait_until(lambda: len(attempts) >= 3, timeout=4))
                self.assertGreaterEqual(attempts[1] - attempts[0], 0.9)
                self.assertGreaterEqual(attempts[2] - attempts[1], 0.9)
                self.assertTrue(self.wait_until(lambda: stream.get_latest_frame() is not None))
            finally:
                stream.stop()

    def test_reconnect_delay_progression_caps_at_thirty_seconds(self):
        tracker = FakeTracker()
        with patch("computer_vision_v2.streaming.Streming_Cameras.CameraTracker", return_value=tracker):
            stream = StreamManager("cam", "rtsp://camera", "rtsp", "unused")

        class OfflineSource:
            def connect(self):
                raise ConnectionError("offline")

            def disconnect(self):
                pass

        delays = []

        def record_wait(delay):
            delays.append(delay)
            return len(delays) == 7

        stream._create_source = OfflineSource
        with patch.object(stream._stop, "wait", side_effect=record_wait), \
             self.assertLogs("computer_vision_v2.streaming.Streming_Cameras", level="WARNING"):
            stream._capture_loop()
        self.assertEqual(delays, [1, 2, 4, 8, 16, 30, 30])

    def test_offline_camera_does_not_stop_another_camera(self):
        tracker = FakeTracker()
        tracker.release_first.set()
        with patch("computer_vision_v2.streaming.Streming_Cameras.CameraTracker", return_value=tracker):
            offline = StreamManager("offline", "rtsp://bad", "rtsp", "unused")
            online = StreamManager("online", "rtsp://good", "rtsp", "unused")

        class OfflineSource:
            def connect(self):
                raise ConnectionError("offline")

            def disconnect(self):
                pass

        class OnlineSource:
            def __init__(self):
                self.reads = 0

            def connect(self):
                pass

            def get_frame(self):
                self.reads += 1
                if self.reads == 1:
                    return True, 1
                online._stop.wait(2)
                return False, None

            def disconnect(self):
                pass

        offline._create_source = OfflineSource
        online._create_source = OnlineSource
        try:
            with self.assertLogs("computer_vision_v2.streaming.Streming_Cameras", level="WARNING"):
                offline.start()
                online.start()
                self.assertTrue(self.wait_until(lambda: online.get_latest_frame() is not None))
                self.assertIsNone(offline.get_latest_frame())
        finally:
            offline.stop()
            online.stop()

    def test_video_still_processes_every_frame_in_order(self):
        tracker = FakeTracker()
        tracker.release_first.set()
        with patch("computer_vision_v2.streaming.Streming_Cameras.CameraTracker", return_value=tracker):
            stream = StreamManager("cam", "clip.mp4", "video", "unused")

        class Video:
            index = 0

            def connect(self):
                pass

            def get_frame(self):
                self.index += 1
                return (self.index <= 4, self.index)

            def disconnect(self):
                pass

        stream._create_source = Video
        try:
            stream.start()
            self.assertTrue(self.wait_until(lambda: tracker.seen == [1, 2, 3, 4]))
        finally:
            stream.stop()
