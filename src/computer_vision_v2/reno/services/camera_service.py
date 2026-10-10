"""
services/camera_service.py

Holds the list of configured cameras and is the ONLY place in the app
that is allowed to add, edit or delete a camera.

Why a "subscribe" mechanism?
    The Camera Settings screen changes the camera list, but the
    Dashboard screen is the one that needs to redraw its camera
    selector and camera grid when that happens. Instead of Camera
    Settings reaching into the Dashboard screen directly (which would
    tightly couple two screens that shouldn't know about each other),
    the Dashboard simply "subscribes" once:

        camera_service.subscribe(self._on_cameras_changed)

    and camera_service calls every subscribed function after any
    change. This is the same idea as an Excel cell that recalculates
    automatically when a cell it depends on changes.

Configuration is shared with the pipeline in data/cameras.json.
The app periodically calls reload() to pick up edits made outside the UI.
"""

import json
import os
from typing import Callable, List, Optional

from computer_vision_v2.reno.models.camera import Camera, STATUS_ONLINE, STATUS_OFFLINE, ROLE_ENTRY, ROLE_EXIT, SOURCE_TYPE_RTSP, SOURCE_TYPE_VIDEO_FILE
from computer_vision_v2.reno.services.mock_mode import MOCK_DATA_ENABLED

Listener = Callable[[List[Camera]], None]


class CameraService:
    def __init__(self):
        # Real (production) starting state is an EMPTY list - see
        # services/mock_mode.py. The two demo cameras below only exist
        # when RENO_MOCK_DATA=1 is set, for design review / demo runs;
        # they are never mixed into a normal run silently.
        self._store_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cameras.json")
        self._model_path = "yolov8n.pt"
        self._detection_interval = 3
        self._cameras: List[Camera] = self._load()
        if MOCK_DATA_ENABLED:
            self._cameras = [
                Camera(id="camera-1", source_type=SOURCE_TYPE_RTSP,
                       source="rtsp://192.168.1.101/stream", role=ROLE_ENTRY,
                       status=STATUS_ONLINE),
                Camera(id="camera-2", source_type=SOURCE_TYPE_VIDEO_FILE,
                       source="sample_exit.mp4", role=ROLE_EXIT,
                       status=STATUS_OFFLINE),
            ]
        self._listeners: List[Listener] = []
        # Connection state changes much more often than camera configuration.
        # Keep them on a separate channel so a status update cannot cause the
        # dashboard to destroy and recreate its live video widgets.
        self._status_listeners: List[Listener] = []

    # -- reading ----------------------------------------------------
    def get_cameras(self) -> List[Camera]:
        """Return a *copy* of the camera list so callers can't mutate
        our internal state by accident."""
        return list(self._cameras)

    def get_camera(self, camera_id: str) -> Optional[Camera]:
        for camera in self._cameras:
            if camera.id == camera_id:
                return camera
        return None

    def reload(self) -> bool:
        """Publish external config edits while keeping the last valid state."""
        if MOCK_DATA_ENABLED:
            return False
        try:
            cameras = self._load(strict=True)
        except (OSError, ValueError, TypeError):
            # Editors may briefly leave an incomplete file while saving.
            return False
        if [c.to_dict() for c in cameras] == [c.to_dict() for c in self._cameras]:
            return False
        previous = {camera.id: camera for camera in self._cameras}
        self._cameras = [
            previous[camera.id]
            if camera.id in previous and previous[camera.id].to_dict() == camera.to_dict()
            else camera
            for camera in cameras
        ]
        self._notify()
        return True

    # -- writing ------------------------------------------------------
    def add_camera(self, camera: Camera) -> None:
        self._cameras.append(camera)
        self._save()
        self._notify()

    def update_camera(self, camera: Camera) -> None:
        for index, existing in enumerate(self._cameras):
            if existing.id == camera.id:
                self._cameras[index] = camera
                break
        self._save()
        self._notify()

    def delete_camera(self, camera_id: str) -> None:
        self._cameras = [c for c in self._cameras if c.id != camera_id]
        self._save()
        self._notify()

    def _load(self, *, strict=False) -> List[Camera]:
        try:
            with open(self._store_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            # Accept the old list once for a seamless migration, but always
            # save back using the pipeline's native config structure.
            if isinstance(data, dict):
                model_path = data.get("model_path", self._model_path)
                detection_interval = data.get("detection_interval", 3)
                camera_items = data.get("cameras", [])
            else:
                model_path = self._model_path
                detection_interval = self._detection_interval
                camera_items = data
            if not isinstance(camera_items, list) or not all(isinstance(item, dict) for item in camera_items):
                raise ValueError("Camera configuration must contain a list of camera objects")
            cameras = [Camera.from_dict(item) for item in camera_items if isinstance(item, dict)]
            # Connection state is runtime information; never trust a stale
            # "online" value from the previous application session.
            for camera in cameras:
                camera.status = STATUS_OFFLINE
            self._model_path = model_path
            self._detection_interval = detection_interval
            return cameras
        except (OSError, ValueError, TypeError):
            if strict:
                raise
            return []

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
        temporary_path = self._store_path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "model_path": self._model_path,
                    "detection_interval": self._detection_interval,
                    "cameras": [camera.to_dict() for camera in self._cameras],
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
        os.replace(temporary_path, self._store_path)

    def set_status(self, camera_id: str, status: str) -> None:
        """Publish live state without treating it as a config change."""
        camera = self.get_camera(camera_id)
        if camera is None or camera.status == status:
            return
        camera.status = status
        cameras = self.get_cameras()
        for listener in list(self._status_listeners):
            listener(cameras)

    # -- subscribing (observer pattern) --------------------------------
    def subscribe(self, listener: Listener) -> None:
        """Register a function to be called (with the new camera list)
        every time a camera is added, edited or deleted."""
        self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def subscribe_status(self, listener: Listener) -> None:
        self._status_listeners.append(listener)

    def unsubscribe_status(self, listener: Listener) -> None:
        if listener in self._status_listeners:
            self._status_listeners.remove(listener)

    def _notify(self) -> None:
        cameras = self.get_cameras()
        for listener in list(self._listeners):
            listener(cameras)


# A single shared instance the whole app imports, so every screen sees
# the same camera list.
camera_service = CameraService()
