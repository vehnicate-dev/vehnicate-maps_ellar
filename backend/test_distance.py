import unittest

import pandas as pd

from distance import compute_matched_distance


class MatchedDistanceTests(unittest.TestCase):
    def test_uses_matched_coordinates_in_timestamp_order(self):
        rows = pd.DataFrame([
            {
                "timestamp_ms": 2000,
                "matched_lat": 13.001,
                "matched_lon": 80.0,
                "osm_way_id": 12,
            },
            {
                "timestamp_ms": 1000,
                "matched_lat": 13.0,
                "matched_lon": 80.0,
                "osm_way_id": 12,
            },
        ])

        distance = compute_matched_distance(rows)
        self.assertGreater(distance, 100)
        self.assertLess(distance, 120)

    def test_ignores_unmatched_fallbacks_and_does_not_bridge_them(self):
        rows = pd.DataFrame([
            {
                "timestamp_ms": 1000,
                "matched_lat": 13.0,
                "matched_lon": 80.0,
                "osm_way_id": 12,
            },
            {
                "timestamp_ms": 2000,
                "matched_lat": 13.1,
                "matched_lon": 80.0,
                "osm_way_id": None,
            },
            {
                "timestamp_ms": 3000,
                "matched_lat": 13.002,
                "matched_lon": 80.0,
                "osm_way_id": 12,
            },
        ])

        self.assertEqual(compute_matched_distance(rows), 0.0)

    def test_returns_zero_if_fewer_than_two_consecutive_matches(self):
        rows = pd.DataFrame([
            {
                "timestamp_ms": 1000,
                "matched_lat": 13.0,
                "matched_lon": 80.0,
                "osm_way_id": 12,
            }
        ])

        self.assertEqual(compute_matched_distance(rows), 0.0)

    def test_counts_estimated_segments_without_bridging_raw_fallbacks(self):
        rows = pd.DataFrame([
            {
                "timestamp_ms": 1000,
                "matched_lat": 13.0,
                "matched_lon": 80.0,
                "osm_way_id": 12,
                "is_estimated": False,
            },
            {
                "timestamp_ms": 2000,
                "matched_lat": 13.001,
                "matched_lon": 80.0,
                "osm_way_id": None,
                "is_estimated": True,
            },
            {
                "timestamp_ms": 3000,
                "matched_lat": 13.002,
                "matched_lon": 80.0,
                "osm_way_id": None,
                "is_estimated": False,
            },
            {
                "timestamp_ms": 4000,
                "matched_lat": 13.003,
                "matched_lon": 80.0,
                "osm_way_id": None,
                "is_estimated": True,
            },
            {
                "timestamp_ms": 5000,
                "matched_lat": 13.004,
                "matched_lon": 80.0,
                "osm_way_id": 12,
                "is_estimated": False,
            },
        ])

        distance = compute_matched_distance(rows)
        self.assertGreater(distance, 200)
        self.assertLess(distance, 230)


if __name__ == "__main__":
    unittest.main()
