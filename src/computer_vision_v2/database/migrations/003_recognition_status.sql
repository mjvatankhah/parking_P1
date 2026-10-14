BEGIN;
ALTER TABLE event ADD COLUMN IF NOT EXISTS recognition_status TEXT;
ALTER TABLE event ADD COLUMN IF NOT EXISTS recognition_details JSONB NOT NULL DEFAULT '[]'::jsonb;
UPDATE event SET recognition_status = CASE WHEN plate_number IS NULL THEN 'unread' ELSE 'read' END
WHERE recognition_status IS NULL;
ALTER TABLE event ALTER COLUMN recognition_status SET DEFAULT 'unread';
ALTER TABLE event ALTER COLUMN recognition_status SET NOT NULL;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'event_recognition_status_check' AND conrelid = 'event'::regclass) THEN
        ALTER TABLE event ADD CONSTRAINT event_recognition_status_check CHECK (recognition_status IN ('read','uncertain','unread'));
    END IF;
END $$;
COMMIT;
