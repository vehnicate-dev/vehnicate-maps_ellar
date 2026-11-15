import unittest
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import MagicMock, patch

import main
from map_regions import MapCoverageUnavailableError, MapDataUnavailableError


class ReplayMapCoverageTests(unittest.TestCase):
    def test_map_data_failure_skips_session_and_continues_replay(self):
        sessions = [
            {
                "session_id": "uncovered-session",
                "end_time": "2025-01-01T00:00:00Z",
                "vehicle_id": 1,
                "user_id": "user-1",
                "start_time": "2025-01-01T00:00:00Z",
            },
            {
                "session_id": "covered-session",
                "end_time": "2025-01-02T00:00:00Z",
                "vehicle_id": 1,
                "user_id": "user-1",
                "start_time": "2025-01-02T00:00:00Z",
            },
        ]
        target = MagicMock()

        with (
            patch.object(main, "_make_production_source_client"),
            patch.object(main, "_make_production_target_client", return_value=target),
            patch.object(main, "fetch_all_pages", side_effect=[sessions, []]),
            patch.object(main, "_execute_with_retry"),
            patch.object(main, "_delete_all_rows") as delete_rows,
            patch.object(
                main,
                "_process_trip_inner",
                side_effect=[
                    MapDataUnavailableError("no extract covers this trip"),
                    None,
                ],
            ) as process_trip,
            patch("builtins.print") as print_log,
        ):
            main._replay_all_sessions_inner("production")

        self.assertEqual(process_trip.call_count, 2)
        delete_rows.assert_any_call(target, "logger", "record_id")
        self.assertEqual(
            process_trip.call_args_list[1].args[0],
            "covered-session",
        )
        self.assertTrue(
            any(
                "SKIPPED session=uncovered-session" in str(call)
                for call in print_log.call_args_list
            )
        )

    def test_resume_uses_latest_completed_checkpoint_without_resetting_target(self):
        completed_session = {
            "session_id": "last-completed",
            "end_time": "2025-01-01T00:00:00Z",
        }
        pending_session = {
            "session_id": "next-session",
            "end_time": "2025-01-02T00:00:00Z",
            "vehicle_id": 1,
            "user_id": "user-1",
            "start_time": "2025-01-02T00:00:00Z",
        }
        source = MagicMock()
        target = MagicMock()

        with (
            patch.object(main, "_make_production_source_client", return_value=source),
            patch.object(main, "_make_production_target_client", return_value=target),
            patch.object(
                main,
                "fetch_all_pages",
                side_effect=[[completed_session], [pending_session]],
            ) as fetch_all_pages,
            patch.object(main, "_execute_with_retry") as execute,
            patch.object(main, "_delete_all_rows") as delete_rows,
            patch.object(main, "_process_trip_inner") as process_trip,
            patch("builtins.print"),
        ):
            main._resume_all_sessions_inner("production")

        source_query = fetch_all_pages.call_args_list[1].kwargs
        self.assertIn(
            (
                "or_",
                "end_time.gt.2025-01-01T00:00:00Z,"
                "and(end_time.eq.2025-01-01T00:00:00Z,"
                "session_id.gt.last-completed)",
            ),
            source_query["filters"],
        )
        self.assertEqual(process_trip.call_args.args[0], "next-session")
        execute.assert_not_called()
        delete_rows.assert_not_called()

    def test_resume_skips_map_failure_and_continues_to_later_session(self):
        sessions = [
            {
                "session_id": "uncovered-session",
                "end_time": "2025-01-02T00:00:00Z",
                "vehicle_id": 1,
                "user_id": "user-1",
                "start_time": "2025-01-02T00:00:00Z",
            },
            {
                "session_id": "later-session",
                "end_time": "2025-01-03T00:00:00Z",
                "vehicle_id": 1,
                "user_id": "user-1",
                "start_time": "2025-01-03T00:00:00Z",
            },
        ]

        with (
            patch.object(
                main,
                "_process_trip_inner",
                side_effect=[
                    MapDataUnavailableError("no extract covers this trip"),
                    None,
                ],
            ) as process_trip,
            patch("builtins.print") as print_log,
        ):
            main._process_sessions_in_order(sessions, "production", "resume")

        self.assertEqual(process_trip.call_count, 2)
        self.assertEqual(process_trip.call_args_list[1].args[0], "later-session")
        self.assertTrue(
            any(
                "SKIPPED session=uncovered-session" in str(call)
                for call in print_log.call_args_list
            )
        )

    def test_exactly_20_gps_points_skips_uncovered_session(self):
        sessions = [
            {
                "session_id": "uncovered-session",
                "end_time": "2025-01-02T00:00:00Z",
                "vehicle_id": 1,
                "user_id": "user-1",
                "start_time": "2025-01-02T00:00:00Z",
            },
            {
                "session_id": "later-session",
                "end_time": "2025-01-03T00:00:00Z",
                "vehicle_id": 1,
                "user_id": "user-1",
                "start_time": "2025-01-03T00:00:00Z",
            },
        ]

        with (
            patch.object(
                main,
                "_process_trip_inner",
                side_effect=[
                    MapCoverageUnavailableError(
                        "No configured OSM extract covers the trip.",
                        gps_point_count=20,
                    ),
                    None,
                ],
            ) as process_trip,
            patch("builtins.print"),
        ):
            main._process_sessions_in_order(sessions, "production", "resume")

        self.assertEqual(process_trip.call_count, 2)

    def test_more_than_20_gps_points_halts_before_later_sessions(self):
        sessions = [
            {
                "session_id": "uncovered-session",
                "end_time": "2025-01-02T00:00:00Z",
                "vehicle_id": 1,
                "user_id": "user-1",
                "start_time": "2025-01-02T00:00:00Z",
            },
            {
                "session_id": "later-session",
                "end_time": "2025-01-03T00:00:00Z",
                "vehicle_id": 1,
                "user_id": "user-1",
                "start_time": "2025-01-03T00:00:00Z",
            },
        ]

        with (
            patch.object(
                main,
                "_process_trip_inner",
                side_effect=MapCoverageUnavailableError(
                    "No configured OSM extract covers the trip.",
                    gps_point_count=21,
                ),
            ) as process_trip,
            patch("builtins.print"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "21 GPS points",
            ):
                main._process_sessions_in_order(sessions, "production", "resume")

        process_trip.assert_called_once()

    def test_processing_headers_are_attached_to_supabase_client(self):
        with patch.object(main, "create_client", return_value="client") as create_client:
            client = main._make_supabase_client(
                "https://example.test",
                "service-key",
                "session-id",
                "run-id",
                "test",
            )

        self.assertEqual(client, "client")
        headers = create_client.call_args.kwargs["options"].headers
        self.assertEqual(
            headers,
            {
                "X-Processing-Session-ID": "session-id",
                "X-Processing-Run-ID": "run-id",
                "X-Processing-Target": "test",
            },
        )

    def test_completed_processing_run_stamps_only_its_target_logger(self):
        captured = {}

        def fake_process(*args, **kwargs):
            captured.update(kwargs)
            kwargs["processing_context"]["target_role"] = "test"

        test_target = MagicMock()
        production_target = MagicMock()
        with (
            patch.object(main, "_process_trip_inner", side_effect=fake_process),
            patch.object(
                main,
                "_make_test_target_client",
                return_value=test_target,
            ),
            patch.object(
                main,
                "_make_production_target_client",
                return_value=production_target,
            ) as make_production_target,
            patch.object(main, "_execute_with_retry") as execute,
        ):
            main._process_trip_with_audit(
                "session-id",
                1,
                "user-id",
                "start",
                "end",
                target_role="test",
            )

        self.assertEqual(
            str(UUID(captured["processing_run_id"])),
            captured["processing_run_id"],
        )
        self.assertEqual(execute.call_count, 1)
        make_production_target.assert_not_called()

    def test_completion_timestamp_updates_logger_rows_in_bounded_batches(self):
        target = MagicMock()
        queries = []

        def make_query(_table_name):
            query = MagicMock()
            for method_name in ("select", "eq", "order", "range", "update", "in_"):
                getattr(query, method_name).return_value = query
            queries.append(query)
            return query

        target.table.side_effect = make_query
        execute = MagicMock(side_effect=[
            SimpleNamespace(data=[{"record_id": "row-1"}, {"record_id": "row-2"}]),
            None,
            SimpleNamespace(data=[{"record_id": "row-3"}]),
            None,
            SimpleNamespace(data=[]),
        ])

        with (
            patch.object(main, "_LOGGER_STAMP_BATCH_SIZE", 2),
            patch.object(main, "_execute_with_retry", execute),
        ):
            stamped_count = main._stamp_processing_run_completion(
                target,
                "run-id",
                "2026-11-15T12:00:00",
            )

        self.assertEqual(stamped_count, 3)
        self.assertEqual(execute.call_count, 5)
        self.assertEqual(
            [query.range.call_args.args for query in (queries[0], queries[2], queries[4])],
            [(0, 1), (2, 3), (3, 4)],
        )
        self.assertEqual(
            queries[1].in_.call_args.args,
            ("record_id", ["row-1", "row-2"]),
        )
        self.assertEqual(
            queries[3].in_.call_args.args,
            ("record_id", ["row-3"]),
        )

    def test_fewer_than_five_gps_points_skips_before_map_or_imu_fetch(self):
        source = MagicMock()
        test_target = MagicMock()
        source_db = MagicMock()
        gps_rows = [
            {"latitude": 11.0, "longitude": 77.0}
            for _ in range(4)
        ]

        with (
            patch.object(main, "SOURCE_DATABASE_URL", "postgres://source"),
            patch.object(
                main,
                "_make_production_source_client",
                return_value=source,
            ) as make_source,
            patch.object(main, "_make_test_target_client", return_value=test_target),
            patch.object(main, "_get_session_flags", return_value={}),
            patch.object(main, "_target_session_exists", return_value=False),
            patch.object(main.psycopg2, "connect", return_value=source_db),
            patch.object(main, "fetch_sensor_rows", return_value=gps_rows) as fetch_rows,
            patch.object(main, "_load_map_matcher_for_trace") as load_map,
            patch.object(main, "_mark_aliv_processed") as mark_processed,
            patch("builtins.print"),
        ):
            main._process_trip_inner(
                "short-session",
                1,
                "user-1",
                "start",
                "end",
                target_role="test",
            )

        fetch_rows.assert_called_once_with(source_db, "gps_data", "short-session")
        load_map.assert_not_called()
        mark_processed.assert_called_once_with(test_target, "short-session")
        self.assertEqual(make_source.call_args_list, [unittest.mock.call(), unittest.mock.call()])

    def test_test_rollback_only_targets_test_and_resyncs_source_flags(self):
        source = MagicMock()
        test_target = MagicMock()
        execute = MagicMock(side_effect=[
            SimpleNamespace(data=[{"end_time": "2025-01-01T00:00:00Z"}]),
            SimpleNamespace(data={"events_reversed": 1}),
            SimpleNamespace(data=[{"session_id": "session-id"}]),
            SimpleNamespace(data=None),
        ])

        with (
            patch.object(
                main,
                "_make_production_source_client",
                return_value=source,
            ),
            patch.object(
                main,
                "_make_test_target_client",
                return_value=test_target,
            ),
            patch.object(
                main,
                "_make_production_target_client",
            ) as make_production_target,
            patch.object(
                main,
                "fetch_all_pages",
                return_value=[{"session_id": "session-id"}],
            ) as fetch_sessions,
            patch.object(main, "_execute_with_retry", execute),
            patch("builtins.print"),
        ):
            main._rollback_session_inner("session-id", "test")

        self.assertEqual(execute.call_count, 4)
        make_production_target.assert_not_called()
        fetch_sessions.assert_called_once()
        self.assertEqual(
            test_target.rpc.call_args.args[0],
            "rollback_session_processing",
        )
        self.assertEqual(
            source.table.return_value.update.call_args.args[0],
            {"test_db_processed": True},
        )


if __name__ == "__main__":
    unittest.main()
