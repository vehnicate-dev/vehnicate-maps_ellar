import unittest

import pandas as pd

from gps_yaw import gps_assisted_yaw_positions_at_times


class GpsAssistedYawTests(unittest.TestCase):
    def test_interpolates_in_range_without_extrapolating(self):
        imu = pd.DataFrame({
            "timestamp_ms": [0, 1000, 2000],
            "vehicle_yaw_rate_rad_s": [0.0, 0.0, 0.0],
        })
        gps = pd.DataFrame({
            "timestamp_ms": [0, 1000, 2000],
            "latitude": [11.0, 11.00005, 11.0001],
            "longitude": [77.0, 77.0, 77.0],
            "speed": [5.0, 5.0, 5.0],
        })

        positions = gps_assisted_yaw_positions_at_times(
            imu,
            gps,
            [1000, 3000],
        )

        self.assertEqual(set(positions), {1000.0})
        self.assertEqual(len(positions[1000.0]), 2)


if __name__ == "__main__":
    unittest.main()
