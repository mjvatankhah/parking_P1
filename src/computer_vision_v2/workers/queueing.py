"""Bounded handoff policy for crossing events between pipeline stages."""

import logging
import queue


logger = logging.getLogger(__name__)


def offer_event(destination, item, stage, *, stopping=False):
    """Wait briefly for an event; report overload instead of blocking forever."""
    try:
        destination.put(item, timeout=2.0 if stopping else 0.5)
        return True
    except queue.Full:
        event = item.get("event", item)
        logger.error(
            "%s queue full; dropped camera=%s track=%s",
            stage, event.get("camera_id"), event.get("track_id"),
        )
        return False
