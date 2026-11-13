import math

import numpy as np
import pandas as pd


EARTH_RADIUS_M = 6_371_000
YAW_RATE_SMOOTHING_WINDOW = "500ms"
MAX_YAW_RATE_RAD_S = math.radians(45)
MAX_HEADING_OFFSET_FROM_MATCHED_COURSE_RAD = math.radians(20)


def convert_gyro_z_with_aliv_orientation(imu_data):
    required = [
        "timestamp_ms",
        "accel_x",
        "accel_y",
        "accel_z",
        "gyro_x",
        "gyro_y",
        "gyro_z",
    ]
    missing = [column for column in required if column not in imu_data.columns]
    if missing:
        raise ValueError(f"imu_data is missing required columns: {', '.join(missing)}")

    imu = imu_data.copy()
    for column in required:
        imu[column] = pd.to_numeric(imu[column], errors="coerce")
    imu = imu.dropna(subset=required).sort_values("timestamp_ms").reset_index(drop=True)
    if imu.empty:
        raise ValueError(
            "No valid IMU rows with timestamps, accelerometer, and gyro values were found."
        )

    imu = imu.drop_duplicates(subset="timestamp_ms", keep="first").reset_index(drop=True)
    sample_period_ms = imu["timestamp_ms"].diff().dropna().median()
    window_size = max(round(1500 / sample_period_ms), 3) if sample_period_ms > 0 else 3
    if window_size % 2 == 0:
        window_size += 1

    accel = imu[["accel_x", "accel_y", "accel_z"]]
    gravity_up = accel.rolling(window_size, center=True, min_periods=1).median().to_numpy(dtype=float)
    gravity_norm = np.linalg.norm(gravity_up, axis=1, keepdims=True)
    gravity_norm[gravity_norm < 1e-6] = np.nan
    gravity_down_hat = -gravity_up / gravity_norm

    gyro_deg_s = imu[["gyro_x", "gyro_y", "gyro_z"]].to_numpy(dtype=float)
    yaw_rate_deg_s = np.nansum(gyro_deg_s * gravity_down_hat, axis=1)
    imu["vehicle_yaw_rate_rad_s"] = np.deg2rad(yaw_rate_deg_s)
    time_index = pd.to_timedelta(imu["timestamp_ms"], unit="ms")
    imu["vehicle_yaw_rate_rad_s"] = (
        imu.set_index(time_index)["vehicle_yaw_rate_rad_s"]
        .rolling(YAW_RATE_SMOOTHING_WINDOW, center=True, min_periods=1)
        .median()
        .to_numpy()
    )
    return imu


def gps_assisted_yaw_trajectory(imu, gps):
    gps_coordinates, yaw_coordinates, _ = (
        gps_assisted_yaw_trajectory_with_timestamps(imu, gps)
    )
    return gps_coordinates, yaw_coordinates


def gps_assisted_yaw_positions_at_times(imu, gps, target_timestamps):
    _, yaw_coordinates, yaw_timestamps = (
        gps_assisted_yaw_trajectory_with_timestamps(imu, gps)
    )
    yaw_coordinates = np.asarray(yaw_coordinates, dtype=float)
    positions = {}
    for raw_timestamp in target_timestamps:
        try:
            timestamp = float(raw_timestamp)
        except (TypeError, ValueError):
            continue
        if (
            not math.isfinite(timestamp)
            or timestamp < yaw_timestamps[0]
            or timestamp > yaw_timestamps[-1]
        ):
            continue
        positions[timestamp] = (
            float(np.interp(timestamp, yaw_timestamps, yaw_coordinates[:, 0])),
            float(np.interp(timestamp, yaw_timestamps, yaw_coordinates[:, 1])),
        )
    return positions


def gps_assisted_yaw_trajectory_with_timestamps(imu, gps):
    gps_required = ["timestamp_ms", "latitude", "longitude", "speed"]
    missing = [column for column in gps_required if column not in gps.columns]
    if missing:
        raise ValueError(f"gps_data is missing required columns: {', '.join(missing)}")

    gps = gps.copy()
    for column in gps_required:
        gps[column] = pd.to_numeric(gps[column], errors="coerce")
    gps = gps.dropna(subset=["timestamp_ms", "latitude", "longitude"])
    gps = gps[gps["latitude"].between(-90, 90) & gps["longitude"].between(-180, 180)]
    gps = gps.sort_values("timestamp_ms").drop_duplicates("timestamp_ms").reset_index(drop=True)
    if len(gps) < 2:
        raise ValueError("At least two valid GPS fixes are required to plot a trajectory.")

    speed_fixes = gps.dropna(subset=["speed"]).copy()
    speed_fixes = speed_fixes[speed_fixes["speed"] >= 0]
    speed_fixes = speed_fixes.drop_duplicates("timestamp_ms").sort_values("timestamp_ms")
    if len(speed_fixes) < 2:
        raise ValueError("At least two GPS speed readings are required to derive the yaw trajectory.")

    gps_coordinates = gps[["latitude", "longitude"]].to_numpy(dtype=float).tolist()
    origin_lat, origin_lon = gps_coordinates[0]

    imu = imu.sort_values("timestamp_ms").drop_duplicates("timestamp_ms").reset_index(drop=True)
    imu = imu[
        (imu["timestamp_ms"] >= speed_fixes["timestamp_ms"].iloc[0])
        & (imu["timestamp_ms"] <= speed_fixes["timestamp_ms"].iloc[-1])
    ].copy()
    if len(imu) < 2:
        raise ValueError("Not enough IMU samples fall within the GPS speed time range.")

    imu_times = imu["timestamp_ms"].to_numpy(dtype=float)
    gps_times = speed_fixes["timestamp_ms"].to_numpy(dtype=float)
    speeds = np.interp(imu_times, gps_times, speed_fixes["speed"].to_numpy(dtype=float))
    yaw_rates = imu["vehicle_yaw_rate_rad_s"].to_numpy(dtype=float)

    latitude_radians = math.radians(origin_lat)
    longitude_scale = EARTH_RADIUS_M * math.cos(latitude_radians)
    gps_times = gps["timestamp_ms"].to_numpy(dtype=float)
    gps_latitudes = gps["latitude"].to_numpy(dtype=float)
    gps_longitudes = gps["longitude"].to_numpy(dtype=float)
    gps_east = np.deg2rad(gps_longitudes - origin_lon) * longitude_scale
    gps_north = np.deg2rad(gps_latitudes - origin_lat) * EARTH_RADIUS_M
    gps_path = np.column_stack((gps_east, gps_north))
    segment_east = np.diff(gps_east)
    segment_north = np.diff(gps_north)
    segment_headings = np.arctan2(segment_east, segment_north)
    segment_headings[np.hypot(segment_east, segment_north) < 0.5] = np.nan
    if np.isnan(segment_headings).all():
        segment_headings.fill(0.0)
    else:
        segment_headings = (
            pd.Series(segment_headings).ffill().bfill().to_numpy(dtype=float)
        )
    gps_course = np.unwrap(np.concatenate(([segment_headings[0]], segment_headings)))
    matched_course_at_imu = np.interp(imu_times, gps_times, gps_course)

    heading = matched_course_at_imu[0]
    east_m = north_m = 0.0
    yaw_path = [[east_m, north_m]]

    for index in range(1, len(imu_times)):
        delta_time = (imu_times[index] - imu_times[index - 1]) / 1000.0
        if delta_time <= 0:
            continue

        previous_heading = heading
        previous_rate = np.clip(
            yaw_rates[index - 1], -MAX_YAW_RATE_RAD_S, MAX_YAW_RATE_RAD_S
        )
        current_rate = np.clip(
            yaw_rates[index], -MAX_YAW_RATE_RAD_S, MAX_YAW_RATE_RAD_S
        )
        heading += (previous_rate + current_rate) * 0.5 * delta_time
        heading = np.clip(
            heading,
            matched_course_at_imu[index] - MAX_HEADING_OFFSET_FROM_MATCHED_COURSE_RAD,
            matched_course_at_imu[index] + MAX_HEADING_OFFSET_FROM_MATCHED_COURSE_RAD,
        )
        midpoint_heading = (previous_heading + heading) * 0.5
        distance = (speeds[index - 1] + speeds[index]) * 0.5 * delta_time
        east_m += distance * math.sin(midpoint_heading)
        north_m += distance * math.cos(midpoint_heading)
        yaw_path.append([east_m, north_m])

    yaw_path = np.asarray(yaw_path, dtype=float)

    assisted_path = np.empty_like(yaw_path)
    for axis in range(2):
        gps_at_imu = np.interp(imu_times, gps_times, gps_path[:, axis])
        yaw_at_gps = np.interp(gps_times, imu_times, yaw_path[:, axis])
        yaw_anchor_at_imu = np.interp(imu_times, gps_times, yaw_at_gps)
        assisted_path[:, axis] = gps_at_imu + yaw_path[:, axis] - yaw_anchor_at_imu

    yaw_coordinates = [
        [
            origin_lat + math.degrees(north / EARTH_RADIUS_M),
            origin_lon + math.degrees(east / longitude_scale),
        ]
        for east, north in assisted_path
    ]

    return gps_coordinates, yaw_coordinates, imu_times
