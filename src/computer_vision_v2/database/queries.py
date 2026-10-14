"""SQL shared by camera preparation and event persistence.

Gate and camera have distinct IDs. The database's UNIQUE camera.gate_id
constraint enforces at most one camera for each gate.
"""

SELECT_CAMERA_GATE = """
SELECT camera.gate_id
FROM camera JOIN gate ON gate.id = camera.gate_id
WHERE camera.id = %s
"""

UPDATE_CAMERA_SETTINGS = """
UPDATE camera
SET source = %s, source_type = %s, role = %s
WHERE id = %s
"""

INSERT_VEHICLE = """
INSERT INTO vehicle (plate_number, vehicle_type)
VALUES (%s, %s)
ON CONFLICT (plate_number) DO NOTHING
"""

INSERT_EVENT = """
INSERT INTO event (camera_id, plate_number, event_type, class_id, confidence, image_path, captured_at, recognition_status, recognition_details)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
RETURNING id
"""

SELECT_OPEN_SESSION = """
SELECT id FROM vehicle_session
WHERE plate_number = %s AND status = 'open'
ORDER BY opened_at DESC
LIMIT 1 FOR UPDATE
"""

INSERT_SESSION = """
INSERT INTO vehicle_session (plate_number, entry_event_id, opened_at, status)
VALUES (%s, %s, %s, 'open')
"""

UPDATE_CLOSE_SESSION = """
UPDATE vehicle_session
SET exit_event_id = %s, closed_at = %s, status = 'closed'
WHERE id = %s
"""
