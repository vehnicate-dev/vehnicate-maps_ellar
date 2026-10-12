import math
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

from aliv_parameter import transform_accel_z_to_vehicle_frame

PAGE_SIZE = 1_000
EVENT_UPDATE_BATCH_SIZE = 100


def _fetch_all_events(target):
    events = []
    offset = 0
    while True:
        response = (
            target.table("imu_events")
            .select("imu_events_id, session_id, start_time, end_time, az_rms")
            .order("imu_events_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        rows = response.data or []
        events.extend(row for row in rows if row.get("az_rms") is None)
        if len(rows) < PAGE_SIZE:
            return events
        offset += len(rows)


def _fetch_session_imu(source, session_id):
    rows = []
    offset = 0
    while True:
        response = (
            source.table("imu_data")
            .select(
                "timestamp_ms, accel_x, accel_y, accel_z, "
                "user_accel_x, user_accel_y, user_accel_z"
            )
            .eq("session_id", session_id)
            .order("timestamp_ms")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        offset += len(batch)


def _event_timestamp_ms(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.timestamp() * 1_000.0


def _numeric_column(rows, column, fallback=None):
    values = []
    for row in rows:
        value = row.get(column)
        if value is None and fallback is not None:
            value = fallback(row)
        values.append(float(value) if value is not None else math.nan)
    return values


def _resampled_vehicle_accel_z(rows):
    timestamps = _numeric_column(rows, "timestamp_ms")
    raw_x = _numeric_column(rows, "accel_x")
    raw_y = _numeric_column(rows, "accel_y")
    raw_z = _numeric_column(rows, "accel_z")
    user_x = _numeric_column(rows, "user_accel_x", lambda row: row.get("accel_x"))
    user_y = _numeric_column(rows, "user_accel_y", lambda row: row.get("accel_y"))
    user_z = _numeric_column(
        rows,
        "user_accel_z",
        lambda row: (
            float(row["accel_z"]) - 9.8
            if row.get("accel_z") is not None
            else None
        ),
    )

    data = pd.DataFrame({
        "timestamp_ms": timestamps,
        "accel_x": raw_x,
        "accel_y": raw_y,
        "accel_z": raw_z,
        "user_accel_x": user_x,
        "user_accel_y": user_y,
        "user_accel_z": user_z,
    }).dropna()
    data = data.sort_values("timestamp_ms").drop_duplicates("timestamp_ms")
    if len(data) < 2:
        return None

    gaps = data["timestamp_ms"].diff().dropna()
    median_gap_ms = float(gaps.median())
    if not math.isfinite(median_gap_ms) or median_gap_ms <= 0:
        return None
    sampling_frequency = round(1_000.0 / median_gap_ms)
    if sampling_frequency <= 0:
        return None

    vehicle_z = transform_accel_z_to_vehicle_frame(
        data["accel_x"].tolist(),
        data["accel_y"].tolist(),
        data["accel_z"].tolist(),
        data["user_accel_x"].tolist(),
        data["user_accel_y"].tolist(),
        data["user_accel_z"].tolist(),
    )

    relative_ms = data["timestamp_ms"].to_numpy(dtype=float)
    relative_ms -= relative_ms[0]
    resample_interval_ms = int(1_000 / sampling_frequency)
    acceleration = pd.Series(
        vehicle_z,
        index=pd.to_timedelta(relative_ms, unit="ms"),
    ).resample(f"{resample_interval_ms}ms").mean().interpolate()
    return float(data["timestamp_ms"].iloc[0]), acceleration


def _event_az_rms(event, session_trace):
    start_epoch_ms, acceleration = session_trace
    start_ms = _event_timestamp_ms(event["start_time"]) - start_epoch_ms
    end_ms = _event_timestamp_ms(event["end_time"]) - start_epoch_ms
    if end_ms < start_ms:
        raise ValueError(f"Event {event['imu_events_id']} ends before it starts.")

    sample_times_ms = acceleration.index.total_seconds().to_numpy() * 1_000.0
    values = acceleration.loc[
        (sample_times_ms >= start_ms) & (sample_times_ms <= end_ms)
    ].to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    return float(np.sqrt(np.mean(np.square(values))))


def _make_clients():
    load_dotenv()
    source_url = os.environ.get("SOURCE_URL")
    source_key = os.environ.get("SOURCE_KEY")
    target_url = os.environ.get("TARGET_URL")
    target_key = os.environ.get("TARGET_KEY")
    if not all((source_url, source_key, target_url, target_key)):
        raise RuntimeError(
            "SOURCE_URL, SOURCE_KEY, TARGET_URL, and TARGET_KEY must be configured."
        )
    return (
        create_client(source_url, source_key),
        create_client(target_url, target_key),
    )


def backfill():
    source, target = _make_clients()
    events = _fetch_all_events(target)
    events_by_session = {}
    for event in events:
        if not event.get("session_id") or not event.get("start_time") or not event.get("end_time"):
            continue
        events_by_session.setdefault(event["session_id"], []).append(event)

    updated = 0
    skipped = len(events) - sum(map(len, events_by_session.values()))

    for session_id, session_events in events_by_session.items():
        imu_rows = _fetch_session_imu(source, session_id)
        session_trace = _resampled_vehicle_accel_z(imu_rows)
        if session_trace is None:
            skipped += len(session_events)
            print(f"[backfill-az] No usable IMU samples for session={session_id}")
            continue

        session_updates = []
        for event in session_events:
            az_rms = _event_az_rms(event, session_trace)
            if az_rms is None or not math.isfinite(az_rms):
                skipped += 1
                print(f"[backfill-az] No acceleration samples for event={event['imu_events_id']}")
                continue
            session_updates.append((event["imu_events_id"], az_rms))

        for offset in range(0, len(session_updates), EVENT_UPDATE_BATCH_SIZE):
            batch = session_updates[offset:offset + EVENT_UPDATE_BATCH_SIZE]
            for event_id, az_rms in batch:
                (
                    target.table("imu_events")
                    .update({"az_rms": az_rms})
                    .eq("imu_events_id", event_id)
                    .execute()
                )
                updated += 1

        print(
            f"[backfill-az] Processed session={session_id}; "
            f"updated={updated}, skipped={skipped}"
        )

    target.rpc("refresh_hexagon_parameters", {}).execute()
    print(
        f"[backfill-az] Complete. Updated {updated} events; "
        f"skipped {skipped}; hexagon parameters refreshed."
    )


if __name__ == "__main__":
    backfill()
