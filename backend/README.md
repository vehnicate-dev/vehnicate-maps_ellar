# Backend database routing

Configure these Supabase credentials:

- `SOURCE_PRODUCTION_URL` and `SOURCE_PRODUCTION_KEY`: production source
  database, including canonical sessions and sensor data.
- `TARGET_PRODUCTION_URL` and `TARGET_PRODUCTION_KEY`: destination for
  production processing and production replay.
- `TARGET_TEST_URL` and `TARGET_TEST_KEY`: isolated destination for test
  processing and test replay.
- `SOURCE_PRODUCTION_DATABASE_URL` (or the existing
  `SOURCE_DATABASE_URL`): PostgreSQL connection used to read sensor rows.

The regular `/Aliv_for_MVP1` webhook checks the test target first. If that
session is absent, it processes the session into the test target; if present,
it processes into the production target. Test-target sessions, vehicles, and
users are copied only for sessions with positive GPS distance. The production
source session's `test_db_processed` field reflects whether its session exists
in the test target.

Apply `session_test_db_processed_migration.sql` to the production source
database before enabling processing. `/replay_all_sessions/test` and
`/replay_all_sessions/production` replay into only their named target; each
replay resets derived data in that target before processing.

To continue without resetting existing results, call
`POST /resume_all_sessions/test` or `POST /resume_all_sessions/production`.
Each resume endpoint reads the latest target session with
`aliv_processed=true` and processes source sessions after that checkpoint in
chronological order. If the target has no completed sessions, it starts with
the earliest source session. Resume never resets target data and does not scan
for unprocessed sessions earlier than the latest completed checkpoint. If map
coverage is missing, replay/resume halts when the trip has more than 20 GPS
points. With 20 or fewer points, it logs and skips the session, then continues.
Other map-data failures are also logged and skipped. Other processing failures
stop the resume; triggering it again continues after the latest completed session.
Both resume endpoints require the `MAP_QUEUE_API_KEY` value in the
`X-API-Key` header.

## Per-session change logger

Apply `migrations/20261115_create_logger_audit.sql` to both the production
database (the shared production source/target) and the separate test target
before deploying the logger-enabled backend. Reapplying the migration also
drops the old `processing_target` column and updates the rollback function;
existing logger rows are retained, but their old target labels are discarded.
The migration installs row-level
triggers on public tables with primary keys. Changes made by session processing
are recorded per changed column; `row_key` identifies the affected row,
`change_order` orders row operations, and `processing_run_id` groups one run.
`created_at` is set to the session's processing completion time in IST.
Each database keeps its own logger, so the logger table has no
`processing_target` column. Test processing writes are logged in the test
database; updates to `test_db_processed` in the shared production source are
reconciled from test-session existence after a rollback.

The logger records changes made after deployment. A full production or test
replay clears that target's logger history and records the rebuilt sessions.
The change history is not a standalone snapshot: reconstruction must start
from the database state at logger activation or the reset state of the most
recent full replay. The migration stops if any public table to be audited does
not have a primary key.

To roll back a session and later sessions in reverse write order, call
`POST /rollback_sessions/production` or `POST /rollback_sessions/test` with
`X-API-Key: <MAP_QUEUE_API_KEY>` and a JSON body such as:

```json
{"session_id": "e5aecd6e-af2d-4c7f-880b-824c3743f678"}
```

Rollback runs against the selected database's logger; test rollback then
reconciles `test_db_processed` in the shared production source from the
sessions that remain in the test database. Rollback records are retained and
marked with `rolled_back_at`; deleted session rows leave their original
session ID in `session_id_original`. The test-database rollback and subsequent
source-flag reconciliation are separate operations, not one cross-database
transaction.

## Regional OSM map matching

The backend selects OSM extracts from the full GPS trace, downloads only the
required extracts from the `road_networks` Supabase bucket, and builds one
combined road graph before matching. The region catalog and its coverage
rectangles are in `map_regions.py`; update the URL and bounds there whenever an
extract is replaced or its coverage changes. The bounds must reflect the
uploaded extract coverage, not just a city or district name.
When replacing a PBF at the same URL, increment that region's
`cache_revision` so running deployments do not keep using a stale local copy.
Coimbatore's expanded bounds are configured with a new cache revision.

Session and user distance totals are calculated from the selected target
database's `matched_gps_data` rows, using consecutive fixes with a non-null
`osm_way_id` or an `is_estimated` GPS-assisted fallback. After filling
unmatched fixes from the speed-derived GPS-assisted trajectory, the backend
map-matches estimates in the context of the complete route and its accepted
road matches. Successful estimated snaps retain `is_estimated=true` and store
their OSM way, direction, and matched coordinates; estimates that cannot be
matched retain their fallback coordinates without claiming a road or direction.

The `region_vs_path.py` diagnostic page reads `matched_gps_data` from the
production target (falling back to the test target when the session has no
production rows) and plots the stored, successfully map-matched estimates in a
separate layer.

Apply `matched_gps_data_estimated_migration.sql` to both test and production
target databases before deploying the fallback code. The migration adds
`is_estimated`, defaulting existing rows to `false`.

PBF files are cached under the system temporary directory by default. Set
`MAP_CACHE_DIR` to use another writable directory. A Railway restart can clear
this cache, so required extracts may be downloaded again.

If any part of a trip falls outside configured extract coverage, or an
extract is missing/unreadable, the live FIFO worker holds that session and
does not process later queued sessions. After uploading a missing file for an
already configured region, call the resume endpoint below. For a new region,
upload `<region_id>.osm.pbf` to `road_networks`, then register it with
`POST /register_map_region`; the registration call resumes a blocked queue.
Its `bounds` are `[min_lon, min_lat, max_lon, max_lat]`:

```json
{
  "region_id": "maharashtra-pune",
  "bounds": [73.6, 18.3, 74.2, 19.2]
}
```

1. Configure a secret `MAP_QUEUE_API_KEY` in Railway.
2. Call the relevant endpoint with that value in the `X-API-Key` header.
Sessions with fewer than five GPS points are skipped before IMU retrieval or
map-extract loading; an existing target session is marked processed.

Region registrations made through the endpoint last only until the process
restarts; add frequently used regions to `map_regions.py` for permanent
configuration. The endpoint retries the blocked session first; later queued
sessions remain behind it. The queue is in memory, so do not restart/redeploy
the service while it is halted or pending sessions will be lost. Bulk replay
logs and skips sessions whose map data is unavailable, then continues in
chronological order. A skipped session remains unprocessed and should be
retried after its map coverage is configured; other processing failures still
halt the replay.
