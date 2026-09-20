"""
models/camera.py

A simple, plain data model that represents one configured camera.

We use a Python @dataclass here instead of a plain dict because it gives us:
  - named fields (camera.status instead of camera["status"], fewer typos)
  - a default value for fields we don't always set
  - a to_dict()/from_dict() pair so the rest of the app (or a future
    real backend / JSON file / database) can convert it easily.

Nothing in this file talks to Kivy, a database, or the network.
It is pure data, on purpose, so the UI and the services can both
depend on it without depending on each other.
"""

from dataclasses import dataclass, field

# The two source types allowed by the Camera Settings screen.
SOURCE_TYPE_RTSP = "rtsp"
SOURCE_TYPE_VIDEO_FILE = "video"

# The three "roles" a camera can play at the parking lot gate.
ROLE_ENTRY = "entry"
ROLE_EXIT = "exit"
ROLE_ENTRY_AND_EXIT = "entry_exit"

# Status shown next to the camera name in the UI.
STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"

# Human readable Persian labels used by the UI layer.
SOURCE_TYPE_LABELS = {
    SOURCE_TYPE_RTSP: "RTSP",
    SOURCE_TYPE_VIDEO_FILE: "ویدیو",
}

ROLE_LABELS = {
    ROLE_ENTRY: "ورود",
    ROLE_EXIT: "خروج",
    ROLE_ENTRY_AND_EXIT: "ورود و خروج",
}

STATUS_LABELS = {
    STATUS_ONLINE: "آنلاین",
    STATUS_OFFLINE: "آفلاین",
}


@dataclass
class Camera:
    """One configured camera.

    id:       a short, unique, human-chosen name such as "camera-1".
    source_type: SOURCE_TYPE_RTSP or SOURCE_TYPE_VIDEO_FILE
    source:   the RTSP url ("rtsp://192.168.1.100/stream") or the path
              to a video file, depending on source_type.
    role:     ROLE_ENTRY, ROLE_EXIT or ROLE_ENTRY_AND_EXIT
    status:   STATUS_ONLINE or STATUS_OFFLINE (mock for now; later this
              will be reported by the real backend's CameraManager).
    """

    id: str
    source_type: str = SOURCE_TYPE_RTSP
    source: str = ""
    role: str = ROLE_ENTRY
    status: str = STATUS_OFFLINE
    line: list = field(default_factory=lambda: [[0.2, 0.6], [0.8, 0.6]])
    inside_point: list | None = None
    coordinate_space: str = "normalized"

    def source_type_label(self) -> str:
        return SOURCE_TYPE_LABELS.get(self.source_type, self.source_type)

    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)

    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    def to_dict(self) -> dict:
        """Return the camera object in the pipeline's native JSON schema."""
        return {
            "id": self.id,
            "type": self.source_type,
            "source": self.source,
            "line": self.line,
            "dir": self.role,
            "inside_point": self.inside_point,
            "coordinate_space": self.coordinate_space,
        }

    @staticmethod
    def from_dict(data: dict) -> "Camera":
        return Camera(
            id=data.get("id", ""),
            source_type=data.get("type", SOURCE_TYPE_RTSP),
            source=data.get("source", ""),
            role=data.get("dir", data.get("role", ROLE_ENTRY)),
            status=data.get("status", STATUS_OFFLINE),
            line=data.get("line", [[775, 132], [399, 561]]),
            inside_point=data.get("inside_point"),
            coordinate_space=data.get("coordinate_space", "pixels"),
        )
