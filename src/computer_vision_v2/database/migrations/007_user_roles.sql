-- Preserve existing accounts; no account is promoted by this migration.
ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_role_check;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
        WHERE conrelid = 'app_user'::regclass AND conname = 'app_user_roles_v2_check') THEN
        ALTER TABLE app_user ADD CONSTRAINT app_user_roles_v2_check
            CHECK (role IN ('guard', 'admin', 'superadmin'));
    END IF;
END $$;
