import math
import unittest

from aliv_parameter import transform_accel_z_to_vehicle_frame


class TransformAccelZTests(unittest.TestCase):
    def test_matches_aliv_vehicle_frame_transform(self):
        raw_x = [0.0] * 10
        raw_y = [0.0] * 10
        raw_z = [-9.8] * 10
        user_x = [1.0] * 10
        user_y = [2.0] * 10
        user_z = [3.0] * 10

        result = transform_accel_z_to_vehicle_frame(
            raw_x, raw_y, raw_z, user_x, user_y, user_z
        )

        theta = math.acos(-(-9.8) / 9.8)
        phi = math.acos(-(0.0) / 9.8)
        expected = -(
            user_x[0] * math.sin(theta) * math.sin(phi)
            - (-user_z[0]) * math.cos(theta) * math.sin(phi)
            + user_y[0] * math.cos(phi)
        )
        self.assertAlmostEqual(expected, result[0])

    def test_empty_session_has_no_transformed_samples(self):
        self.assertEqual(
            [],
            transform_accel_z_to_vehicle_frame([], [], [], [], [], []),
        )


if __name__ == "__main__":
    unittest.main()
