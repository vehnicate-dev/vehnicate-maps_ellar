from bisect import bisect_left
import math
from collections.abc import Sequence


def estimate_velocity_jerk(
    timestamp_ms: Sequence[float],
    speed_mps: Sequence[float],
    impact_timestamp_ms: float,
) -> float | None:
    fixes = []
    for raw_timestamp, raw_speed in zip(timestamp_ms, speed_mps):
        try:
            timestamp = float(raw_timestamp)
            speed = float(raw_speed)
        except (TypeError, ValueError):
            continue
        if math.isfinite(timestamp) and math.isfinite(speed) and speed >= 0.0:
            fixes.append((timestamp, speed))
    fixes.sort()
    if len(fixes) < 3:
        return None

    times = [fix[0] for fix in fixes]
    speeds = [fix[1] for fix in fixes]
    before_ms = impact_timestamp_ms - 5_000.0
    after_ms = impact_timestamp_ms + 5_000.0
    if before_ms < times[0] or after_ms > times[-1]:
        return None

    before_speed = _interpolate_speed(times, speeds, before_ms)
    impact_speed = _interpolate_speed(times, speeds, impact_timestamp_ms)
    after_speed = _interpolate_speed(times, speeds, after_ms)
    return (after_speed - 2.0 * impact_speed + before_speed) / 25.0


def _interpolate_speed(times: list[float], speeds: list[float], timestamp_ms: float) -> float:
    right = bisect_left(times, timestamp_ms)
    if right < len(times) and times[right] == timestamp_ms:
        return speeds[right]

    left = right - 1
    fraction = (timestamp_ms - times[left]) / (times[right] - times[left])
    return speeds[left] + fraction * (speeds[right] - speeds[left])
