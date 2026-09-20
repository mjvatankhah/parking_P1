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
    captured_at TIMESTAMP NOT NULL DEFAULT NOW(),
    class_id INTEGER NOT NULL DEFAULT 2,

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
    opened_at TIMESTAMP NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMP,

    FOREIGN KEY (plate_number) REFERENCES vehicle(plate_number),
    FOREIGN KEY (entry_event_id) REFERENCES event(id),
    FOREIGN KEY (exit_event_id) REFERENCES event(id),

    CHECK (status IN ('open', 'closed'))
);
