-- Apply to the SOURCE Supabase database (SOURCE_URL), outside a transaction.
-- These indexes support process_trip's session filter and stable timestamp/id ordering.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_imu_data_session_timestamp_id
    ON public.imu_data (session_id, timestamp_ms, imu_data_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gps_data_session_timestamp_id
    ON public.gps_data (session_id, timestamp_ms, gps_id);
