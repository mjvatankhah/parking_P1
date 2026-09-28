"""Check the existing gate/camera relationship before processing a camera."""

from computer_vision_v2.database.connection import get_connection
from computer_vision_v2.database import queries


class CameraRegistrationError(RuntimeError):
    pass


def prepare_camera(camera):
    """Keep the existing gate ID and synchronize the camera's runtime settings.

    A newly configured camera must first be assigned to its distinct gate ID
    in PostgreSQL. Inventing a gate ID from the camera ID would hide a mapping
    mistake and could corrupt an existing installation.
    """
    camera_id = camera["id"]
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(queries.SELECT_CAMERA_GATE, (camera_id,))
            row = cursor.fetchone()
            if row is None:
                raise CameraRegistrationError(
                    f"Camera {camera_id} has no registered gate/camera relation in PostgreSQL"
                )
            if row[0] == camera_id:
                raise CameraRegistrationError(
                    f"Camera {camera_id} must have a distinct gate ID"
                )
            cursor.execute(
                queries.UPDATE_CAMERA_SETTINGS,
                (camera["source"], camera["type"], camera["dir"], camera_id),
            )
