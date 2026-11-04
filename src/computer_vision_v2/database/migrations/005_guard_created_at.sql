-- Existing accounts have unknown creation dates; do not invent historical dates.
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;
ALTER TABLE app_user ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
