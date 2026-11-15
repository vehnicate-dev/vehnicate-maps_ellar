import unittest

from map_regions import ROAD_REGIONS, regions_for_trace


class MapRegionCoverageTests(unittest.TestCase):
    def test_expanded_coimbatore_extract_covers_reported_coordinate(self):
        coimbatore = next(
            region for region in ROAD_REGIONS
            if region.region_id == "coimbatore"
        )

        selected_regions = regions_for_trace([(11.02495, 76.89995)])

        self.assertIn(coimbatore, selected_regions)
        self.assertEqual(
            coimbatore.bounds,
            (76.6556, 10.2200, 77.3000, 11.4064),
        )

    def test_updated_coimbatore_extract_uses_a_new_cache_file(self):
        coimbatore = next(
            region for region in ROAD_REGIONS
            if region.region_id == "coimbatore"
        )

        self.assertEqual(coimbatore.filename, "coimbatore.osm.pbf")
        self.assertEqual(coimbatore.cache_filename, "coimbatore-r2.osm.pbf")


if __name__ == "__main__":
    unittest.main()
