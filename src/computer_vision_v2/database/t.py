import queue

from computer_vision_v2.database.database_worker import database_worker


db_queue = queue.Queue()


test_item = {
    "camera_id": "cam2",
    "track_id": 2,
    "direction": "exit",
    "plate_text": "TEST123",
    "confidence": 0.950,
    "image_path": "",
}


db_queue.put(test_item)
db_queue.put(None)


database_worker(
    db_queue,
    lambda: True
)