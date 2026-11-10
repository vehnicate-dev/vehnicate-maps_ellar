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