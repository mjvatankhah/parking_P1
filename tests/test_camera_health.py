"""Source checks are periodic, bounded, and never depend on a visible preview."""
from dataclasses import replace
import time
from types import SimpleNamespace
from threading import Event, Lock
import unittest
from unittest.mock import Mock, patch

from kivy.clock import Clock
from reno.models.camera import Camera, STATUS_ONLINE, STATUS_OFFLINE
from reno.services.camera_health_service import CameraHealthMonitor, CHECK_INTERVAL


class CameraHealthTests(unittest.TestCase):
    def service(self, count=1):
        cameras = {str(i): Camera(str(i),source=f'rtsp://source/{i}') for i in range(count)}
        service = Mock()
        service.get_cameras.side_effect = lambda: list(cameras.values())
        service.get_camera.side_effect = cameras.get
        service.set_status.side_effect = lambda key,state: setattr(cameras[key],'status',state)
        return service,cameras

    def finish(self, monitor):
        deadline=time.monotonic()+3
        while monitor._busy and time.monotonic()<deadline:
            Clock.tick()
            time.sleep(.005)
        self.assertFalse(monitor._busy)

    def test_periodic_schedule_and_cleanup(self):
        service,_=self.service()
        monitor=CameraHealthMonitor(service)
        with patch.object(monitor,'poll') as poll, patch('reno.services.camera_health_service.Clock.schedule_interval') as schedule:
            monitor.start()
            monitor.start()
            poll.assert_called_once()
            schedule.assert_called_once_with(poll,CHECK_INTERVAL)
            monitor.stop()
            schedule.return_value.cancel.assert_called_once()

    def test_status_changes_without_live_view_and_exceptions_mark_offline(self):
        service,cameras=self.service()
        check=Mock(return_value=SimpleNamespace(success=True))
        monitor=CameraHealthMonitor(service,check=check)
        monitor.poll()
        self.finish(monitor)
        self.assertEqual(cameras['0'].status,STATUS_ONLINE)
        check.side_effect=OSError('unavailable')
        monitor.poll()
        self.finish(monitor)
        self.assertEqual(cameras['0'].status,STATUS_OFFLINE)

    def test_stale_results_after_source_edit_delete_or_stop_are_ignored(self):
        service,cameras=self.service()
        monitor=CameraHealthMonitor(service)
        snapshot=replace(cameras['0'])
        cameras['0'].source='rtsp://other'
        monitor._apply(0,snapshot,True)
        service.set_status.assert_not_called()
        cameras.clear()
        monitor._apply(0,snapshot,True)
        service.set_status.assert_not_called()
        monitor.stop()
        monitor._apply(0,snapshot,True)
        service.set_status.assert_not_called()

    def test_two_checks_maximum_and_cycles_do_not_overlap(self):
        service,_=self.service(5)
        release=Event()
        two_started=Event()
        lock=Lock()
        active=peak=calls=0
        def check(camera):
            nonlocal active,peak,calls
            with lock:
                active+=1
                calls+=1
                peak=max(peak,active)
                if active==2:
                    two_started.set()
            release.wait(2)
            with lock:
                active-=1
            return SimpleNamespace(success=True)
        monitor=CameraHealthMonitor(service,check=check)
        monitor.poll()
        try:
            self.assertTrue(two_started.wait(2))
            monitor.poll()
            self.assertEqual(calls,2)
        finally:
            release.set()
            self.finish(monitor)
        self.assertEqual(peak,2)
        self.assertEqual(calls,5)
