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
