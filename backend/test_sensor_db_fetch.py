import unittest

from main import fetch_sensor_rows


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params):
        self.connection.queries.append((query, params))
        self.rows = self.connection.pages.pop(0)

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, pages):
        self.pages = list(pages)
        self.queries = []

    def cursor(self, cursor_factory=None):
        return FakeCursor(self)


class FetchSensorRowsTests(unittest.TestCase):
    def test_uses_postgres_keyset_query_without_offset(self):
        pages = [
            [
                {"timestamp_ms": 10, "imu_data_id": 1},
                {"timestamp_ms": 10, "imu_data_id": 2},
            ],
            [{"timestamp_ms": 11, "imu_data_id": 1}],
        ]
        connection = FakeConnection(pages)

        result = fetch_sensor_rows(
            connection,
            "imu_data",
            "session-1",
            page_size=2,
        )

        self.assertEqual([row for page in pages for row in page], result)
        first_query, first_params = connection.queries[0]
        second_query, second_params = connection.queries[1]
        self.assertIn("FROM public.imu_data WHERE session_id = %s", first_query)
        self.assertIn("ORDER BY timestamp_ms ASC, imu_data_id ASC LIMIT %s", first_query)
        self.assertNotIn("OFFSET", first_query.upper())
        self.assertIn("(timestamp_ms, imu_data_id) > (%s, %s)", second_query)
        self.assertNotIn("OFFSET", second_query.upper())
        self.assertEqual(["session-1", 2], first_params)
        self.assertEqual(["session-1", 10, 2, 2], second_params)

    def test_rejects_tables_outside_sensor_allowlist(self):
        with self.assertRaisesRegex(ValueError, "Unsupported sensor table"):
            fetch_sensor_rows(FakeConnection([]), "sessions", "session-1")


if __name__ == "__main__":
    unittest.main()
