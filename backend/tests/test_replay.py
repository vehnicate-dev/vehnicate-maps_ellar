import unittest
from uuid import UUID
from types import SimpleNamespace
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

    def test_completed_processing_run_is_stamped_in_both_test_and_production_logs(self):
        captured = {}

        def fake_process(*args, **kwargs):
            captured.update(kwargs)
            kwargs["processing_context"]["target_role"] = "test"

        with (
            patch.object(main, "_process_trip_inner", side_effect=fake_process),
            patch.object(main, "_make_test_target_client", return_value=MagicMock()),
            patch.object(main, "_make_production_target_client", return_value=MagicMock()),
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
        self.assertEqual(execute.call_count, 2)

    def test_test_rollback_dispatches_to_test_and_production_databases(self):
        test_target = MagicMock()
        production_target = MagicMock()
        execute = MagicMock(side_effect=[
            SimpleNamespace(data=[{"end_time": "2025-01-01T00:00:00Z"}]),
            SimpleNamespace(data={"events_reversed": 1}),
            SimpleNamespace(data={"events_reversed": 1}),
        ])

        with (
            patch.object(main, "_make_production_source_client"),
            patch.object(
                main,
                "_make_test_target_client",
                return_value=test_target,
            ),
            patch.object(
                main,
                "_make_production_target_client",
                return_value=production_target,
            ),
            patch.object(main, "_execute_with_retry", execute),
            patch("builtins.print"),
        ):
            main._rollback_session_inner("session-id", "test")

        self.assertEqual(execute.call_count, 3)
        self.assertEqual(
            test_target.rpc.call_args.args[0],
            "rollback_session_processing",
        )
        self.assertEqual(
            production_target.rpc.call_args.args[0],
            "rollback_session_processing",
        )
        for target in (test_target, production_target):
            self.assertEqual(
                target.rpc.call_args.args[1]["p_processing_target"],
                "test",
            )


if __name__ == "__main__":
    unittest.main()
