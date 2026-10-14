"""
models/plate_record.py

A plain data model for one recognized-plate log row, shown in the
"Recent records" table on the Dashboard.

Just like models/camera.py, this file has zero UI code and zero
database code in it. It only describes the shape of the data.
"""

from dataclasses import dataclass

DIRECTION_ENTRY = "entry"
DIRECTION_EXIT = "exit"

DIRECTION_LABELS = {
    DIRECTION_ENTRY: "ورود",
    DIRECTION_EXIT: "خروج",
}

CLASS_LABELS = {
    0: "انسان",
    2: "خودرو",
}


@dataclass
class PlateRecord:
    """One recognized-plate event.

    plate:     the plate text, e.g. "12الف345"
    date:      "YYYY-MM-DD" formatted date string
    time:      "HH:MM:SS" formatted time string
    camera:    the id of the camera that captured this event
    direction: DIRECTION_ENTRY or DIRECTION_EXIT
    image_path: optional path to a cropped plate image (empty for mock data)
    """

    plate: str
    date: str
    time: str
    camera: str
    class_id: int = 2
    direction: str = DIRECTION_ENTRY
    image_path: str = ""

    def direction_label(self) -> str:
        return DIRECTION_LABELS.get(self.direction, self.direction)

    def class_label(self) -> str:
        return CLASS_LABELS.get(self.class_id, f"کلاس {self.class_id}")
