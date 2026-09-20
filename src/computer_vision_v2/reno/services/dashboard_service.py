"""
services/dashboard_service.py

Builds the numbers shown in the Dashboard's statistic cards:
  - how many cars went in/out today
  - how many cars went in/out this week
  - how many configured cameras are currently online

The daily/weekly counts are mock (random-ish, based on the mock plate
records). The online-camera count is NOT mock - it is computed live
from services/camera_service.py, so it always matches the Camera
Settings screen.

How to connect your real backend later:
    Replace `_count_today_and_week()` with a real query (for example
    "SELECT count(*) ... WHERE date = today"). Leave get_statistics()
    itself alone - the Dashboard only calls that one method.
"""

from dataclasses import dataclass
from datetime import date

from computer_vision_v2.reno.models.plate_record import PlateRecord
from computer_vision_v2.reno.services.camera_service import camera_service
from computer_vision_v2.reno.services.plate_service import plate_service
from computer_vision_v2.reno.models.camera import STATUS_ONLINE


@dataclass
class DashboardStatistics:
    today_total: int
    week_total: int
    online_cameras: int
    total_cameras: int


class DashboardService:
    def get_statistics(self) -> DashboardStatistics:
        records = plate_service.get_recent_records(limit=1000)
        today_total, week_total = self._count_today_and_week(records)

        cameras = camera_service.get_cameras()
        online_cameras = sum(1 for c in cameras if c.status == STATUS_ONLINE)

        return DashboardStatistics(
            today_total=today_total,
            week_total=week_total,
            online_cameras=online_cameras,
            total_cameras=len(cameras),
        )

    def _count_today_and_week(self, records: list[PlateRecord]) -> tuple[int, int]:
        today_str = date.today().strftime("%Y-%m-%d")
        today_total = sum(1 for r in records if r.date == today_str)
        # Mock data only spans a short window, so "this week" is
        # approximated as "everything we currently have".
        week_total = len(records)
        return today_total, week_total


# A single shared instance the whole app imports.
dashboard_service = DashboardService()
