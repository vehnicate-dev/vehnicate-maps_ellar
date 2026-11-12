import os
import tempfile
import unittest
from unittest.mock import patch

import requests

import map_regions
from map_regions import (
    MapDataUnavailableError,
    ROAD_REGIONS,
    ensure_region_extract,
    register_road_region,
    regions_for_trace,
)


class RegionSelectionTests(unittest.TestCase):
    def test_selects_region_for_single_point(self):
        regions = regions_for_trace([(13.05, 80.10)])
        self.assertEqual([region.region_id for region in regions], ["chennai-metro"])

    def test_selects_all_regions_crossed_by_trace(self):
        regions = regions_for_trace([
            (11.0, 77.0),
            (10.5, 77.8),
        ])
        self.assertEqual(
            {region.region_id for region in regions},
            {"coimbatore", "tiruppur", "dindigul"},
        )

    def test_rejects_route_outside_available_coverage(self):
        with self.assertRaisesRegex(
            MapDataUnavailableError,
            "No configured OSM extract covers the trip",
        ):
            regions_for_trace([
                (13.05, 80.10),
                (12.95, 77.60),
            ])

    def test_rejects_trace_without_valid_coordinates(self):
        with self.assertRaisesRegex(
            MapDataUnavailableError,
            "no valid coordinates",
        ):
            regions_for_trace([(None, None), (float("nan"), 80.0)])

    def test_registers_new_region_for_an_existing_blocked_process(self):
        original_regions = map_regions.ROAD_REGIONS
        try:
            region = register_road_region(
                "test-region",
                (72.0, 18.0, 73.0, 19.0),
            )
            self.assertEqual(region.filename, "test-region.osm.pbf")
            self.assertEqual(
                [item.region_id for item in regions_for_trace([(18.5, 72.5)])],
                ["test-region"],
            )
        finally:
            map_regions.ROAD_REGIONS = original_regions

    def test_rejects_invalid_region_registration(self):
        with self.assertRaisesRegex(ValueError, "region_id"):
            register_road_region("unsafe/name", (72.0, 18.0, 73.0, 19.0))

        with self.assertRaisesRegex(ValueError, "bounds"):
            register_road_region("test-region", (72.0, 19.0, 73.0, 18.0))


class ExtractDownloadTests(unittest.TestCase):
    def test_downloads_extract_to_cache(self):
        region = ROAD_REGIONS[0]

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def raise_for_status(self):
                pass

            def iter_content(self, chunk_size):
                self.assert_chunk_size = chunk_size
                yield b"pbf-data"

        with tempfile.TemporaryDirectory() as cache_dir:
            with patch("map_regions.requests.get", return_value=FakeResponse()):
                path = ensure_region_extract(region, cache_dir)

            self.assertTrue(os.path.isfile(path))
            with open(path, "rb") as extract_file:
                self.assertEqual(extract_file.read(), b"pbf-data")

    def test_404_is_reported_as_unavailable_region(self):
        region = ROAD_REGIONS[0]
        response = requests.Response()
        response.status_code = 404
        error = requests.HTTPError(response=response)

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def raise_for_status(self):
                raise error

        with tempfile.TemporaryDirectory() as cache_dir:
            with patch("map_regions.requests.get", return_value=FakeResponse()):
                with self.assertRaisesRegex(
                    MapDataUnavailableError,
                    "bharuch.*not available in Supabase",
                ):
                    ensure_region_extract(region, cache_dir)

            self.assertEqual(os.listdir(cache_dir), [])


if __name__ == "__main__":
    unittest.main()
