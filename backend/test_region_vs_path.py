import unittest

import folium

from region_vs_path import create_region_path_map, fetch_session_rows


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client):
        self.client = client

    def select(self, columns):
        self.client.columns = columns
        return self

    def eq(self, column, value):
        self.client.filters.append(("eq", column, value))
        return self

    def gte(self, column, value):
        self.client.filters.append(("gte", column, value))
        return self

    def lte(self, column, value):
        self.client.filters.append(("lte", column, value))
        return self

    def order(self, column, desc=False):
        return self

    def or_(self, expression):
        self.client.cursor_filters.append(expression)
        return self

    def range(self, start, end):
        self.client.ranges.append((start, end))
        return self

    def execute(self):
        return FakeResponse(self.client.pages.pop(0))


class FakeClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.columns = None
        self.filters = []
        self.cursor_filters = []
        self.ranges = []

    def table(self, table):
        return FakeQuery(self)


class SessionRowsFetchTests(unittest.TestCase):
    def test_uses_keyset_pagination_and_requested_timestamp_range(self):
        columns = ["timestamp_ms", "gyro_z", "imu_data_id"]
        rows = [
            {"timestamp_ms": 100, "gyro_z": 1.0, "imu_data_id": 1},
            {"timestamp_ms": 100, "gyro_z": 2.0, "imu_data_id": 2},
            {"timestamp_ms": 110, "gyro_z": 3.0, "imu_data_id": 1},
        ]
        client = FakeClient([rows[:2], rows[2:]])

        result = fetch_session_rows(
            client,
            "imu_data",
            "session-1",
            "imu_data_id",
            columns=columns,
            timestamp_range=(90, 120),
            page_size=2,
        )

        self.assertEqual(rows, result)
        self.assertEqual(",".join(columns), client.columns)
        self.assertIn(("gte", "timestamp_ms", 90), client.filters)
        self.assertIn(("lte", "timestamp_ms", 120), client.filters)
        self.assertEqual(
            [
                "timestamp_ms.gt.100,"
                "and(timestamp_ms.eq.100,imu_data_id.gt.2)"
            ],
            client.cursor_filters,
        )
        self.assertEqual([(0, 1), (0, 1)], client.ranges)


class RegionPathMapTests(unittest.TestCase):
    def test_routes_have_independent_toggleable_layers(self):
        route_map = create_region_path_map(
            raw_coordinates=[(11.0, 77.0), (11.1, 77.1)],
            matched_route=[(11.0, 77.0), (11.1, 77.1)],
            regions=[],
            yaw_route=[(11.0, 77.0), (11.1, 77.1)],
        )
        groups = {
            child.layer_name: child
            for child in route_map._children.values()
            if isinstance(child, folium.FeatureGroup)
        }

        self.assertTrue(
            {"Raw GPS", "Map-matched GPS", "GPS-assisted yaw"}.issubset(groups)
        )
        self.assertTrue(
            any(isinstance(child, folium.LayerControl) for child in route_map._children.values())
        )
        for layer_name, color in (
            ("Raw GPS", "red"),
            ("Map-matched GPS", "blue"),
            ("GPS-assisted yaw", "yellow"),
        ):
            polylines = [
                child
                for child in groups[layer_name]._children.values()
                if isinstance(child, folium.PolyLine)
            ]
            self.assertEqual(len(polylines), 1)
            self.assertEqual(polylines[0].options["color"], color)


if __name__ == "__main__":
    unittest.main()
