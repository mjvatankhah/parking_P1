"""Persist recognized crossings using the schema's vehicle and session tables."""

import logging

from computer_vision_v2.database.connection import get_connection
from computer_vision_v2.database import queries


logger = logging.getLogger(__name__)


def _save_event(cursor, item):
    plate_number = item["plate_text"] or None
    if plate_number is not None:
        cursor.execute(queries.INSERT_VEHICLE, (plate_number, "car"))

    cursor.execute(
        queries.INSERT_EVENT,
        (
            item["camera_id"], plate_number, item["direction"], item["class_id"],
            item["confidence"], item["image_path"],
        ),
    )
    event_id = cursor.fetchone()[0]

    if plate_number is None:
        return event_id

    cursor.execute(queries.SELECT_OPEN_SESSION, (plate_number,))
    open_session = cursor.fetchone()
    if item["direction"] == "entry" and open_session is None:
        cursor.execute(queries.INSERT_SESSION, (plate_number, event_id))
    elif item["direction"] == "exit":
        if open_session is None:
            logger.warning("No open session for plate %s", plate_number)
        else:
            cursor.execute(queries.UPDATE_CLOSE_SESSION, (event_id, open_session[0]))
    return event_id


def database_worker(db_queue, running_flag):
    connection = None
    cursor = None
    try:
        while True:
            item = db_queue.get()
            if item is None:
                db_queue.task_done()
                break
            try:
                if connection is None:
                    connection = get_connection()
                    cursor = connection.cursor()
                    logger.info("Database connection established")
                event_id = _save_event(cursor, item)
                connection.commit()
                logger.info("Saved event %s from camera %s", event_id, item["camera_id"])
            except Exception:
                logger.exception("Could not save event from camera %s", item.get("camera_id"))
                if connection is not None:
                    try:
                        connection.rollback()
                    except Exception:
                        logger.warning("Database rollback failed; connection will be reopened")
                    try:
                        if cursor is not None:
                            cursor.close()
                    except Exception:
                        logger.warning("Database cursor cleanup failed")
                    try:
                        connection.close()
                    except Exception:
                        logger.warning("Database connection cleanup failed")
                    connection = cursor = None
            finally:
                db_queue.task_done()
    finally:
        if connection is not None:
            cursor.close()
            connection.close()
