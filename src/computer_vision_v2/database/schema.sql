CREATE TABLE gate (
    id TEXT PRIMARY KEY
);


CREATE TABLE camera (
    id TEXT PRIMARY KEY,
    gate_id TEXT NOT NULL UNIQUE,

    source TEXT NOT NULL,
    source_type TEXT NOT NULL,

    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'off',

    FOREIGN KEY (gate_id) REFERENCES gate(id),

    CHECK (source_type IN ('rtsp', 'video')),
    CHECK (role IN ('entry', 'exit', 'entry_exit')),
    CHECK (status IN ('on', 'off'))
);


CREATE TABLE vehicle (
    plate_number TEXT PRIMARY KEY,
    vehicle_type TEXT NOT NULL,

    CHECK (vehicle_type IN ('car', 'van', 'bus'))
);


CREATE TABLE event (
    id BIGSERIAL PRIMARY KEY,

    camera_id TEXT NOT NULL,
    plate_number TEXT,
    event_type TEXT NOT NULL,
    confidence NUMERIC(4, 3) NOT NULL,
    image_path TEXT,
    captured_at TIMESTAMPTZ NOT NULL,
    class_id INTEGER NOT NULL DEFAULT 2,
    recognition_status TEXT NOT NULL DEFAULT 'unread' CHECK (recognition_status IN ('read', 'uncertain', 'unread')),
    recognition_details JSONB NOT NULL DEFAULT '[]'::jsonb,

    FOREIGN KEY (camera_id) REFERENCES camera(id),
    FOREIGN KEY (plate_number) REFERENCES vehicle(plate_number),

    CHECK (event_type IN ('entry', 'exit')),
    CHECK (confidence >= 0 AND confidence <= 1)
);


CREATE TABLE vehicle_session (
    id BIGSERIAL PRIMARY KEY,

    plate_number TEXT NOT NULL,
    entry_event_id BIGINT NOT NULL,
    exit_event_id BIGINT,

    status TEXT NOT NULL DEFAULT 'open',
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,

    FOREIGN KEY (plate_number) REFERENCES vehicle(plate_number),
    FOREIGN KEY (entry_event_id) REFERENCES event(id),
    FOREIGN KEY (exit_event_id) REFERENCES event(id),

    CHECK (status IN ('open', 'closed'))
);
CREATE TABLE IF NOT EXISTS app_user (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('guard')),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS plate_registry (
    plate_number TEXT PRIMARY KEY,
    permission TEXT NOT NULL CHECK (permission IN ('allowed','blocked')),
    registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE event ADD COLUMN IF NOT EXISTS access_status TEXT NOT NULL DEFAULT 'unknown';
CREATE OR REPLACE FUNCTION snapshot_plate_access() RETURNS trigger AS $$
BEGIN
    IF NEW.class_id <> 2 OR NEW.plate_number IS NULL THEN
        NEW.access_status := 'unknown';
    ELSE
        NEW.access_status := COALESCE((SELECT permission FROM plate_registry WHERE plate_number =
            regexp_replace(translate(NEW.plate_number, '۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك', '01234567890123456789یک'), '[[:space:]‌-]', '', 'g')), 'guest');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS event_plate_access ON event;
CREATE TRIGGER event_plate_access BEFORE INSERT ON event FOR EACH ROW EXECUTE FUNCTION snapshot_plate_access();
