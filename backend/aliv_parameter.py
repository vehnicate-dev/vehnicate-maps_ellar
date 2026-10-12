import math
from collections.abc import Sequence


GRAVITY_M_S2 = 9.8


def transform_accel_z_to_vehicle_frame(
    accel_x: Sequence[float],
    accel_y: Sequence[float],
    accel_z: Sequence[float],
    user_accel_x: Sequence[float],
    user_accel_y: Sequence[float],
    user_accel_z: Sequence[float],
) -> list[float]:
    rows = list(zip(accel_x, accel_y, accel_z, user_accel_x, user_accel_y, user_accel_z))
    if not rows:
        return []

    initial_rows = rows[:10]
    ax0 = sum(row[0] for row in initial_rows) / len(initial_rows)
    ay0 = sum(row[1] for row in initial_rows) / len(initial_rows)
    az0 = sum(row[2] for row in initial_rows) / len(initial_rows)

    try:
        theta = math.acos(-az0 / GRAVITY_M_S2)
    except ValueError:
        theta = 0.0
    try:
        phi = math.acos(-ay0 / GRAVITY_M_S2)
    except ValueError:
        phi = 0.0

    sin_theta, cos_theta = math.sin(theta), math.cos(theta)
    sin_phi, cos_phi = math.sin(phi), math.cos(phi)
    return [
        -(
            user_x * sin_theta * sin_phi
            - (-user_z) * cos_theta * sin_phi
            + user_y * cos_phi
        )
        for _, _, _, user_x, user_y, user_z in rows
    ]


def calculate_raw_score(
    dp_og: float,
    dp: float,
    gymax: float,
    stdp: float,
    az_rms: float,
) -> float:
    existing_score = ((dp_og + dp) / 2.0) * gymax * stdp
    vertical_acceleration_factor = 1.0 + max(0.0, az_rms) / GRAVITY_M_S2
    return existing_score * vertical_acceleration_factor
