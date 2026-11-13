ALTER TABLE public.matched_gps_data
    ADD COLUMN IF NOT EXISTS is_estimated boolean NOT NULL DEFAULT false;
