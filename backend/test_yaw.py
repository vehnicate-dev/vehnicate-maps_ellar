import unittest
from unittest.mock import patch

from yaw import gps_assisted_yaw_positions_at_times


class GpsAssistedYawPositionTests(unittest.TestCase):
    def test_interpolates_inside_yaw_window_without_extrapolating(self):
        with patch(
            "yaw.gps_assisted_yaw_trajectory_with_timestamps",
            return_value=(
                [],
                [[10.0, 20.0], [12.0, 24.0]],
                [1000.0, 2000.0],
            ),
        ):
            positions = gps_assisted_yaw_positions_at_times(
                None,
                None,
                [500.0, 1000.0, 1500.0, 2000.0, 2500.0],
            )

        self.assertEqual(
            positions,
            {
                1000.0: (10.0, 20.0),
                1500.0: (11.0, 22.0),
                2000.0: (12.0, 24.0),
            },
        )


if __name__ == "__main__":
    unittest.main()
