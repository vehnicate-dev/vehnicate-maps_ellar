import unittest

from velocity_jerk import estimate_velocity_jerk


class EstimateVelocityJerkTests(unittest.TestCase):
    def test_calculates_central_second_derivative_in_meters_per_second_cubed(self):
        timestamps = list(range(0, 20_001, 1_000))
        speeds = [100.0 + (timestamp / 1_000) ** 2 for timestamp in timestamps]

        result = estimate_velocity_jerk(timestamps, speeds, 10_000)

        self.assertAlmostEqual(2.0, result)

    def test_requires_gps_coverage_five_seconds_on_both_sides(self):
        result = estimate_velocity_jerk(
            [0, 1_000, 2_000, 3_000, 4_000],
            [10, 11, 12, 13, 14],
            2_000,
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
