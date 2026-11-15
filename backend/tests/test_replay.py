import unittest
from unittest.mock import MagicMock, patch

import main
from map_regions import MapDataUnavailableError


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
            patch.object(main, "_delete_all_rows"),
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


if __name__ == "__main__":
    unittest.main()
