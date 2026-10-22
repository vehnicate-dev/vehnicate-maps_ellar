import unittest

from main import fetch_all_pages


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client):
        self.client = client
        self.filters = []

    def select(self, columns):
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def order(self, column, desc=False):
        self.client.orders.append((column, desc))
        return self

    def or_(self, expression):
        self.client.cursor_filters.append(expression)
        return self

    def range(self, start, end):
        self.client.ranges.append((start, end))
        return self

    def execute(self):
        return FakeResponse(self.client.pages.pop(0))


class FakeSupabaseClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.orders = []
        self.cursor_filters = []
        self.ranges = []

    def table(self, table):
        return FakeQuery(self)


class FetchAllPagesTests(unittest.TestCase):
    def test_uses_composite_cursor_instead_of_growing_offsets(self):
        pages = [
            [
                {"timestamp_ms": 1, "imu_data_id": 2},
                {"timestamp_ms": 1, "imu_data_id": 4},
            ],
            [
                {"timestamp_ms": 2, "imu_data_id": 1},
                {"timestamp_ms": 3, "imu_data_id": 5},
            ],
            [{"timestamp_ms": 4, "imu_data_id": 1}],
        ]
        client = FakeSupabaseClient(pages)

        result = fetch_all_pages(
            client,
            table="imu_data",
            filters=[("eq", "session_id", "session-1")],
            order_col="timestamp_ms",
            page_size=2,
            tiebreak_col="imu_data_id",
        )

        self.assertEqual([row for page in pages for row in page], result)
        self.assertEqual(
            [
                "timestamp_ms.gt.1,and(timestamp_ms.eq.1,imu_data_id.gt.4)",
                "timestamp_ms.gt.3,and(timestamp_ms.eq.3,imu_data_id.gt.5)",
            ],
            client.cursor_filters,
        )
        self.assertEqual([(0, 1)] * 3, client.ranges)


if __name__ == "__main__":
    unittest.main()
