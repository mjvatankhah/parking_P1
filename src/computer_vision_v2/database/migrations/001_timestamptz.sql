-- Apply to an existing database after checking SHOW TimeZone. Existing
-- timestamp values are interpreted in that database time zone; no rows are
-- deleted. Already-migrated columns are skipped.
BEGIN;

DO $migration$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'event'
          AND column_name = 'captured_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        EXECUTE 'ALTER TABLE event ALTER COLUMN captured_at TYPE timestamptz '
             || 'USING captured_at AT TIME ZONE current_setting(''TimeZone'')';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'vehicle_session'
          AND column_name = 'opened_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        EXECUTE 'ALTER TABLE vehicle_session ALTER COLUMN opened_at TYPE timestamptz '
             || 'USING opened_at AT TIME ZONE current_setting(''TimeZone'')';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'vehicle_session'
          AND column_name = 'closed_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        EXECUTE 'ALTER TABLE vehicle_session ALTER COLUMN closed_at TYPE timestamptz '
             || 'USING closed_at AT TIME ZONE current_setting(''TimeZone'')';
    END IF;
END
$migration$;

COMMIT;
