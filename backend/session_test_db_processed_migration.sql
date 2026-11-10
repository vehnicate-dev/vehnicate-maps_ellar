-- Apply to the production database that stores canonical sessions.
ALTER TABLE public.sessions
ADD COLUMN IF NOT EXISTS test_db_processed boolean NOT NULL DEFAULT false;
