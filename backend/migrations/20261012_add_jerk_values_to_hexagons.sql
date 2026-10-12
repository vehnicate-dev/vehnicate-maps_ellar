-- Apply to the TARGET database before deploying the backend changes.
-- Rebuild historical values with `python backfill_jerk_values.py` from backend/.
ALTER TABLE public.hexagons
ADD COLUMN IF NOT EXISTS jerk_values double precision[]
NOT NULL DEFAULT ARRAY[]::double precision[];
