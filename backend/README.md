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

## Regional OSM map matching

The backend selects OSM extracts from the full GPS trace, downloads only the
required extracts from the `road_networks` Supabase bucket, and builds one
combined road graph before matching. The region catalog and its coverage
rectangles are in `map_regions.py`; update the URL and bounds there whenever an
extract is replaced or its coverage changes. The bounds must reflect the
uploaded extract coverage, not just a city or district name.

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

Region registrations made through the endpoint last only until the process
restarts; add frequently used regions to `map_regions.py` for permanent
configuration. The endpoint retries the blocked session first; later queued
sessions remain behind it. The queue is in memory, so do not restart/redeploy
the service while it is halted or pending sessions will be lost. Bulk replay
also halts at the first session whose map coverage is unavailable; it does not
continue to later sessions.
