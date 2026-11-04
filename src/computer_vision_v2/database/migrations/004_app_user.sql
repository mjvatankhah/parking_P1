CREATE TABLE IF NOT EXISTS app_user (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('guard'))
);
