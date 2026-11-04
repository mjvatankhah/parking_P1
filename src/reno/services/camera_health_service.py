"""Periodic source reachability checks independent of preview subscriptions."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread
from dataclasses import replace

from kivy.clock import Clock
from reno.models.camera import STATUS_ONLINE, STATUS_OFFLINE
from reno.services.camera_setup_service import check_connection

CHECK_INTERVAL = 10


class CameraHealthMonitor:
    def __init__(self, cameras, *, check=None):
        self.cameras = cameras
        self.check = check or check_connection
        self._poll = None
        self._busy = False
        self._generation = 0

    def start(self):
        if self._poll is not None:
            return
        self._generation += 1
        self.poll()
        self._poll = Clock.schedule_interval(self.poll, CHECK_INTERVAL)

    def stop(self):
        self._generation += 1
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None

    def poll(self, *_):
        if self._busy:
            return
        snapshots = [replace(camera) for camera in self.cameras.get_cameras()]
        if not snapshots:
            return
        self._busy = True
        generation = self._generation

        def work():
            try:
                with ThreadPoolExecutor(max_workers=2, thread_name_prefix='camera-health') as workers:
                    jobs = {workers.submit(self.check, camera): camera for camera in snapshots}
                    for future in as_completed(jobs):
                        if generation != self._generation:
                            for job in jobs:
                                job.cancel()
                            break
                        camera = jobs[future]
                        try:
                            online = future.result().success
                        except Exception:
                            online = False
                        Clock.schedule_once(lambda _, c=camera, ok=online: self._apply(generation, c, ok))
            finally:
                Clock.schedule_once(lambda _: self._finished())
        Thread(target=work, daemon=True, name='camera-health-cycle').start()

    def _finished(self):
        self._busy = False

    def _apply(self, generation, snapshot, online):
        if generation != self._generation:
            return
        current = self.cameras.get_camera(snapshot.id)
        # A late reply for a removed or edited source cannot overwrite its status.
        if current is None or (current.source, current.source_type) != (snapshot.source, snapshot.source_type):
            return
        self.cameras.set_status(snapshot.id, STATUS_ONLINE if online else STATUS_OFFLINE)
