"""SQL statements used by the database worker.

Camera IDs intentionally use TEXT because the settings JSON uses readable
IDs such as gate-entry-1, and those IDs travel with every pipeline event.
"""

UPSERT_CAMERA = """
INSERT INTO camera (id, source, source_type, role, status)
VALUES (%s, %s, %s, %s, 'on')
ON CONFLICT (id) DO UPDATE
SET source = EXCLUDED.source,
    source_type = EXCLUDED.source_type,
    role = EXCLUDED.role,
    status = 'on',
    updated_at = NOW();
"""

INSERT_VEHICLE = """
INSERT INTO vehicle (plate_number, vehicle_type)
VALUES (%s, %s)
ON CONFLICT (plate_number) DO NOTHING;
"""

INSERT_EVENT = """
INSERT INTO event (camera_id, plate_number, event_type, class_id, confidence, image_path)
VALUES (%s, %s, %s, %s, %s, %s)
RETURNING id, captured_at;
"""

SELECT_OPEN_SESSION = """
SELECT id FROM parking_session
WHERE plate_number = %s AND status = 'open'
ORDER BY id DESC
LIMIT 1
FOR UPDATE;
"""

INSERT_SESSION = """
INSERT INTO parking_session (plate_number, entry_event_id, status)
VALUES (%s, %s, 'open')
RETURNING id;
"""

UPDATE_CLOSE_SESSION = """
UPDATE parking_session
SET exit_event_id = %s, status = 'closed', closed_at = NOW()
WHERE id = %s;
"""
