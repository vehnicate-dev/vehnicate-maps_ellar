from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import numpy as np
import math
import time
import queue
import threading
import tempfile
import hmac
from datetime import datetime
from functools import wraps
from contextlib import closing
from uuid import uuid4
import httpx
from supabase import create_client, ClientOptions
import httpcore
import psycopg2
from psycopg2.extras import RealDictCursor
from aliv_module import AlivRoadDefects, edge_slow_mask
from aliv_parameter import median_speed_for_interval
import h3 as h3lib
import os
from dotenv import load_dotenv
from hexagons_update import update_hexagons, record_trip_passes
from zoneinfo import ZoneInfo
from distance import compute_matched_distance
from map_matching import (
    apply_estimated_positions,
    init_map_matcher,
    map_match_estimated_positions,
    map_match_trip,
)
from map_regions import (
    MapCoverageUnavailableError,
    MapDataUnavailableError,
    ensure_region_extract,
    register_road_region,
    regions_for_trace,
)
from velocity_jerk import estimate_velocity_jerk
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header   # added Header
from geographies import add_session_geographies, backfill_all_geographies
from gps_yaw import (
    convert_gyro_z_with_aliv_orientation,
    gps_assisted_yaw_positions_at_times,
)

IST = ZoneInfo("Asia/Kolkata")
"""
Each time a new row is inserted into the "sessions" table, a HTTPS request is triggered
via ngrok carrying session_id, vehicle_id, start_time & end_time.
|
↓
process_trip() fetches IMU rows from imu_data and GPS rows from gps_data (both keyed by
session_id), map-matches the GPS trace onto OSM (map_matching.map_match_trip), persists
the matched trace to matched_gps_data, merges IMU+matched-GPS on nearest timestamp_ms,
then feeds the combined rows into Aliv for road defect detection.

Column mapping summary
──────────────────────
imu_data  : accel_x/y/z  → renamed to accelx/y/z    (Aliv key)
            gyro_x/y/z   → renamed to gyrox/y/z      (Aliv key)
            user_accel_x → renamed to useraccelx      (Aliv key, no underscore!)
            created_at   → mapped to 'timestamp'      (Aliv time key)
gps_data  : latitude, longitude, speed               (Aliv uses these directly — RAW,
            unaffected by map-matching; Aliv's own "has the vehicle moved" gate only
            needs a rough fix, not a road-snapped one)
matched_gps_data : matched_lat, matched_lon, osm_way_id, direction_label,
            match_raw_distance, is_estimated — used by enrich_events() for
            reported defect locations/direction, NOT fed into Aliv.

Aliv time output
────────────────
Aliv rebuilds time_ms internally from 'timestamp' (pd.to_datetime), resamples at 1000/fs ms
intervals, then trims 50 samples off both ends. Its output start_time / end_time are offsets
(in ms) from that internal axis.
To convert back to absolute wall-clock time:
    absolute = timesent_T0 + pd.to_timedelta(aliv_ms + TRIM_OFFSET_MS, unit='ms')
where TRIM_OFFSET_MS = 50 * (1000 / fs) = 625 ms at fs=80.

Session-level flags on `sessions`
──────────────────────────────────
aliv_processed : set True once Aliv has run + hexagons/ellar/distance side effects have
                 fired for this session. process_trip() skips all of that on rerun once
                 this is True, so hexagons/ledger/distance never double-credit.
imu_only       : mount-orientation check (phone camera axis vs. direction of travel).
                 Computed independently of aliv_processed, every run — including reruns
                 of already-processed sessions — so it can be iterated on/tested against
                 historical sessions without needing to reprocess them through Aliv.
"""

load_dotenv()

SOURCE_PRODUCTION_URL = os.environ.get("SOURCE_PRODUCTION_URL", os.environ.get("SOURCE_URL"))
SOURCE_PRODUCTION_KEY = os.environ.get("SOURCE_PRODUCTION_KEY", os.environ.get("SOURCE_KEY"))
SOURCE_DATABASE_URL = os.environ.get(
    "SOURCE_PRODUCTION_DATABASE_URL",
    os.environ.get("SOURCE_DATABASE_URL"),
)
TARGET_PRODUCTION_URL = os.environ.get("TARGET_PRODUCTION_URL", os.environ.get("TARGET_URL"))
TARGET_PRODUCTION_KEY = os.environ.get("TARGET_PRODUCTION_KEY", os.environ.get("TARGET_KEY"))
TARGET_TEST_URL = os.environ.get("TARGET_TEST_URL")
TARGET_TEST_KEY = os.environ.get("TARGET_TEST_KEY")

# Regional OSM extracts are downloaded lazily to this cache when a trip needs
# them. Railway's filesystem is ephemeral, so a deploy may download them again.
MAP_CACHE_DIR = os.environ.get(
    "MAP_CACHE_DIR",
    os.path.join(tempfile.gettempdir(), "vehnicate-road-network-cache"),
)

# Must match AlivRoadDefects(fs=…) below
#ALIV_FS          = 40 # previously 80
#ALIV_TRIM        = 50                              # samples trimmed from each end
#ALIV_TRIM_OFFSET = ALIV_TRIM * (1000 / ALIV_FS)   # 625 ms at fs=80

# ── Mount-orientation (imu_only) constants ──────────────────────────────────
MIN_SPEED_MPS            = 1.5   # GPS fixes below this speed have unreliable course-over-ground
ANGLE_THRESHOLD_DEG       = 35.0  # |mount yaw offset| beyond this → imu_only = True
MIN_ACCEL_ENERGY          = 5.0   # sum(|a_gps|) needed across the trip before trusting the estimate
GRAVITY_LOWPASS_WINDOW_S  = 1.5   # rolling window used to separate gravity from user_accel noise
MIN_COHERENCE = 0.1  # su,sv vector magnitude / energy — below this, the direction estimate is noise-dominated
MIN_GPS_POINTS = 10  # fewer raw fixes than this → skip Aliv (matched distance is still calculated)
MIN_TRIP_DISTANCE_M = 50  # trips that moved less than this overall aren't worth map-matching/Aliv
# Prevent vehicle-distance triggers from underflowing below zero during replay resets.
REPLAY_DISTANCE_ROUNDING_BUFFER_KM = 1e-6
MAP_COVERAGE_REPLAY_HALT_GPS_POINT_THRESHOLD = 20
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://vehnicate.com",
        "https://www.vehnicate.com",
        "http://localhost:5173",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Single-worker trip queue ─────────────────────────────────────────────────
# FastAPI's BackgroundTasks runs sync callables via a thread pool, so several
# webhook-triggered trips arriving close together would otherwise run
# CONCURRENTLY, not one after another. That's unsafe here: hexagons_update.py
# reads a hex's current rows, computes changes in Python, then writes them
# back across several separate calls — two trips landing in the same/nearby
# H3 cell at once can race and lose or duplicate updates. A single worker
# thread pulling from a FIFO queue guarantees the same "one trip fully
# finishes before the next starts" property that /replay_all_sessions already
# has for the bulk-replay case, but for live webhook traffic too.
_trip_queue: "queue.Queue[tuple[str, int, str, str, str, str]]" = queue.Queue()
_pipeline_lock = threading.RLock()
_trip_state_lock = threading.Lock()
_trip_resume_event = threading.Event()
_blocked_trip: tuple[str, int, str, str, str, str] | None = None


def _serialize_pipeline(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _pipeline_lock:
            return function(*args, **kwargs)
    return wrapped


def _trip_worker() -> None:
    global _blocked_trip
    while True:
        trip = _trip_queue.get()
        session_id, vehicle_id, user_id, start_time, end_time, target_role = trip
        while True:
            try:
                process_trip(
                    session_id,
                    vehicle_id,
                    user_id,
                    start_time,
                    end_time,
                    target_role=target_role,
                )
            except MapDataUnavailableError as err:
                with _trip_state_lock:
                    _trip_resume_event.clear()
                    _blocked_trip = trip
                print(
                    f"[trip_worker] HALTED at session={session_id}: {err}. "
                    f"{_trip_queue.qsize()} later session(s) remain queued. "
                    "Upload/fix the required map extract, then call "
                    "POST /resume_trip_queue with X-API-Key."
                )
                _trip_resume_event.wait()
                with _trip_state_lock:
                    _blocked_trip = None
                print(f"[trip_worker] retrying blocked session={session_id}")
                continue
            except Exception as err:
                # Don't let an unexpected trip failure kill the worker.
                print(f"[trip_worker] session={session_id} raised: {err!r}")
            break
        _trip_queue.task_done()


@app.on_event("startup")
def _start_trip_worker() -> None:
    threading.Thread(target=_trip_worker, daemon=True).start()


def _load_map_matcher_for_trace(gps_df: pd.DataFrame) -> None:
    regions = regions_for_trace(
        gps_df[["latitude", "longitude"]].itertuples(index=False, name=None)
    )
    print(
        "[map_matching] session route requires region(s): "
        + ", ".join(region.region_id for region in regions)
    )
    paths = [
        ensure_region_extract(region, MAP_CACHE_DIR)
        for region in regions
    ]
    try:
        init_map_matcher(paths)
    except Exception as err:
        raise MapDataUnavailableError(
            "Unable to build the road graph for region(s) "
            f"{', '.join(region.region_id for region in regions)}: {err!r}"
        ) from err


# ── Supabase client factory ─────────────────────────────────────────────────
# NOTE: create_client() is called fresh at the top of every process_trip()
# run (see below), so clients are never reused across requests. The
# RemoteProtocolError("Server disconnected") failures seen in production
# come from httpx negotiating HTTP/2 with Supabase's edge, then Railway's
# proxy (or Supabase's own load balancer) silently closing an idle HTTP/2
# stream faster than httpx's pool expects — surfacing as a hard disconnect
# instead of a transparent reconnect the way HTTP/1.1 pooling handles it.
# Forcing HTTP/1.1 here removes that failure mode at the source.
_SUPABASE_CLIENT_OPTIONS = ClientOptions(
    httpx_client=httpx.Client(http2=False, timeout=30.0),
)


def _make_supabase_client(
    url: str,
    key: str,
    processing_session_id: str | None = None,
    processing_run_id: str | None = None,
    processing_target: str | None = None,
):
    headers = {}
    if processing_session_id:
        headers["X-Processing-Session-ID"] = processing_session_id
    if processing_run_id:
        headers["X-Processing-Run-ID"] = processing_run_id
    if processing_target:
        headers["X-Processing-Target"] = processing_target
    options = (
        _SUPABASE_CLIENT_OPTIONS.replace(headers=headers)
        if headers
        else _SUPABASE_CLIENT_OPTIONS
    )
    return create_client(url, key, options=options)


def _make_production_source_client(
    processing_session_id: str | None = None,
    processing_run_id: str | None = None,
    processing_target: str | None = None,
):
    if not SOURCE_PRODUCTION_URL or not SOURCE_PRODUCTION_KEY:
        raise RuntimeError("SOURCE_PRODUCTION_URL and SOURCE_PRODUCTION_KEY must be configured")
    return _make_supabase_client(
        SOURCE_PRODUCTION_URL,
        SOURCE_PRODUCTION_KEY,
        processing_session_id,
        processing_run_id,
        processing_target,
    )


def _make_production_target_client(
    processing_session_id: str | None = None,
    processing_run_id: str | None = None,
    processing_target: str | None = None,
):
    if not TARGET_PRODUCTION_URL or not TARGET_PRODUCTION_KEY:
        raise RuntimeError("TARGET_PRODUCTION_URL and TARGET_PRODUCTION_KEY must be configured")
    return _make_supabase_client(
        TARGET_PRODUCTION_URL,
        TARGET_PRODUCTION_KEY,
        processing_session_id,
        processing_run_id,
        processing_target,
    )


def _make_test_target_client(
    processing_session_id: str | None = None,
    processing_run_id: str | None = None,
    processing_target: str | None = None,
):
    if not TARGET_TEST_URL or not TARGET_TEST_KEY:
        raise RuntimeError("TARGET_TEST_URL and TARGET_TEST_KEY must be configured")
    return _make_supabase_client(
        TARGET_TEST_URL,
        TARGET_TEST_KEY,
        processing_session_id,
        processing_run_id,
        processing_target,
    )


def _target_session_exists(supabase_target, session_id: str) -> bool:
    response = _execute_with_retry(
        supabase_target.table("sessions")
        .select("session_id")
        .eq("session_id", session_id)
        .limit(1)
    )
    return bool(response.data)


def _record_passes_safe(supabase_target, gps_df) -> None:
    try:
        record_trip_passes(supabase_target, gps_df, run=_execute_with_retry)
    except Exception as err:
        print(f"[process_trip] pass counting failed: {err!r}")

# ── Retry helper for transient network errors ───────────────────────────────
# Belt-and-suspenders on top of disabling HTTP/2 above: catches the same
# class of transient transport failure (dropped connection, reset, timeout)
# on any individual Supabase call and retries a couple of times with a short
# backoff before giving up. Wrap any query right before .execute(), e.g.:
#   resp = _execute_with_retry(supabase.table("sessions").select("*").eq(...))
_TRANSIENT_EXCEPTIONS = (
    httpcore.RemoteProtocolError,
    httpcore.ConnectError,
    httpcore.ReadTimeout,
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
)


def _execute_with_retry(query, attempts: int = 3, backoff_s: float = 0.5):
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            return query.execute()
        except _TRANSIENT_EXCEPTIONS as err:
            last_err = err
            print(f"  [supabase-retry] attempt {attempt}/{attempts} failed: {err}")
            if attempt < attempts:
                time.sleep(backoff_s * attempt)
    raise last_err


# ── Pydantic models ────────────────────────────────────────────────────────────

class SessionRecord(BaseModel):
    session_id: str
    user_id: str
    vehicle_id: int
    start_time: str
    end_time: str
    status: str
    distance: float
    created_at: str

class WebhookPayload(BaseModel):
    type: str
    table: str
    schema: str
    record: SessionRecord


class MapRegionRegistration(BaseModel):
    region_id: str
    bounds: list[float]


class SessionRollbackRequest(BaseModel):
    session_id: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch_all_pages(
    supabase_client,
    table: str,
    filters: list,
    order_col: str,
    page_size: int = 1000,
    tiebreak_col: str | None = None,   # NEW — must be unique per row
) -> list:
    all_data = []
    start = 0
    cursor = None
    while True:
        query = supabase_client.table(table).select("*")
        for method, *args in filters:
            query = getattr(query, method)(*args)
        query = query.order(order_col, desc=False)
        if tiebreak_col:
            query = query.order(tiebreak_col, desc=False)   # deterministic tiebreak
            if cursor is not None:
                last_order_value, last_tiebreak_value = cursor
                query = query.or_(
                    f"{order_col}.gt.{last_order_value},"
                    f"and({order_col}.eq.{last_order_value},"
                    f"{tiebreak_col}.gt.{last_tiebreak_value})"
                )
            page_range = (0, page_size - 1)
        else:
            page_range = (start, start + page_size - 1)
        try:
            batch = _execute_with_retry(
                query.range(*page_range)
            ).data
        except Exception as err:
            position = f"after {cursor!r}" if tiebreak_col else f"row {start}"
            print(
                f"[fetch_all_pages] {table} page starting {position} failed: {err!r}"
            )
            raise

        if not batch:
            break

        all_data.extend(batch)

        if len(batch) < page_size:
            break

        if tiebreak_col:
            last_row = batch[-1]
            cursor = (last_row[order_col], last_row[tiebreak_col])
            if cursor[0] is None or cursor[1] is None:
                raise ValueError(
                    f"{table} keyset columns {order_col} and {tiebreak_col} "
                    "must not contain null values"
                )
        else:
            start += page_size

    print(f"[fetch_all_pages] {table}: total rows fetched = {len(all_data)}")
    return all_data


_SENSOR_TABLE_KEYS = {
    "imu_data": ("timestamp_ms", "imu_data_id"),
    "gps_data": ("timestamp_ms", "gps_id"),
}


def fetch_sensor_rows(connection, table: str, session_id: str, page_size: int = 1000) -> list:
    """Fetch a session's sensor rows from PostgreSQL using composite keyset pagination."""
    try:
        order_col, tiebreak_col = _SENSOR_TABLE_KEYS[table]
    except KeyError:
        raise ValueError(f"Unsupported sensor table: {table}") from None

    cursor_values = None
    all_rows = []
    page_number = 0
    while True:
        query = f"SELECT * FROM public.{table} WHERE session_id = %s "
        params = [session_id]
        if cursor_values is not None:
            query += f"AND ({order_col}, {tiebreak_col}) > (%s, %s) "
            params.extend(cursor_values)
        query += f"ORDER BY {order_col} ASC, {tiebreak_col} ASC LIMIT %s"
        params.append(page_size)

        try:
            with connection.cursor(cursor_factory=RealDictCursor) as db_cursor:
                db_cursor.execute(query, params)
                batch = db_cursor.fetchall()
        except Exception as err:
            print(
                f"[fetch_sensor_rows] {table} page {page_number} "
                f"after {cursor_values!r} failed: {err!r}"
            )
            raise

        if not batch:
            break

        all_rows.extend(batch)
        if len(batch) < page_size:
            break

        last_row = batch[-1]
        cursor_values = (last_row[order_col], last_row[tiebreak_col])
        if cursor_values[0] is None or cursor_values[1] is None:
            raise ValueError(
                f"{table} keyset columns {order_col} and {tiebreak_col} "
                "must not contain null values"
            )
        page_number += 1

    print(f"[fetch_sensor_rows] {table}: total rows fetched = {len(all_rows)}")
    return all_rows


def sanitize_for_json(obj):
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, list):
        return [sanitize_for_json(i) for i in obj]
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):
        # Covers numpy int64/float64/bool_ and similar scalar types —
        # .item() converts to the nearest native Python type.
        return sanitize_for_json(obj.item())
    return obj

def merge_gps_into_imu(imu_df: pd.DataFrame, gps_df: pd.DataFrame) -> pd.DataFrame:
    """Attach the nearest GPS fix (raw + map-matched) to every IMU row via an
    asof join on timestamp_ms."""
    imu_df = imu_df.sort_values("timestamp_ms").reset_index(drop=True)
    gps_df = gps_df.sort_values("timestamp_ms").reset_index(drop=True)
    return pd.merge_asof(
        imu_df,
        gps_df[[
            "timestamp_ms", "latitude", "longitude", "speed", "bearing",
            "matched_lat", "matched_lon", "osm_way_id", "direction_label",
            "is_estimated",
        ]],
        on="timestamp_ms",
        direction="nearest",
    )


def estimate_gps_positions_from_yaw(imu_rows, gps_df: pd.DataFrame) -> dict:
    try:
        imu = convert_gyro_z_with_aliv_orientation(pd.DataFrame(imu_rows))
        return gps_assisted_yaw_positions_at_times(
            imu,
            gps_df,
            gps_df["timestamp_ms"],
        )
    except ValueError as error:
        print(
            "[map_matching] GPS-assisted position estimates unavailable: "
            f"{error}"
        )
        return {}


def build_aliv_input(df: pd.DataFrame) -> list[dict]:
    """
    Rename columns to the keys Aliv's _normalize_row_keys() recognises and
    add a 'timestamp' column (ISO string) so Aliv can derive its internal time axis.

    Aliv key lookup (from _normalize_row_keys):
        accel  → 'acc_x' | 'accelx' | 'acceleration_x'   ← we use accelx
        gyro   → 'gyro_x' | 'gyrox' | 'rotation_x'       ← we use gyrox
        user   → 'useraccelx'  (NO underscore)
        time   → 'timesent' | 'timestamp'                 ← we use timestamp
        lat    → 'latitude' | 'lat'                       ← already named correctly
        lon    → 'longitude' | 'lon'                      ← already named correctly
        speed  → 'speed'                                   ← already named correctly

    NOTE: intentionally still feeds RAW latitude/longitude to Aliv, not the
    map-matched columns — Aliv only uses these for its coarse "has the
    vehicle moved from the start" gate, not for anything reported downstream.
    """
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    renamed = df.rename(columns={
        "accel_x":     "accelx",
        "accel_y":     "accely",
        "accel_z":     "accelz",
        "gyro_x":      "gyrox",
        "gyro_y":      "gyroy",
        "gyro_z":      "gyroz",
        "user_accel_x": "useraccelx",   # NOTE: no underscore – Aliv looks for 'useraccelx'
        "user_accel_y": "useraccely",
        "user_accel_z": "useraccelz",
    })
    return renamed.to_dict(orient="records")


'''
def aliv_ms_to_absolute(aliv_ms: float, timesent_T0: pd.Timestamp, aliv_trim_offset: float) -> pd.Timestamp:
    """
    Convert an Aliv output time value (ms offset in its resampled+trimmed space)
    back to an absolute UTC timestamp.

        absolute = T0 + TRIM_OFFSET + aliv_ms
    """
    return timesent_T0 + pd.to_timedelta(aliv_trim_offset + aliv_ms, unit="ms")
'''

def enrich_events(
    session_id: str,
    vehicle_id: int,
    user_id: str,
    result: dict,
    df: pd.DataFrame,
    gps_df: pd.DataFrame,
    timesent_T0: pd.Timestamp,
    aliv_trim_offset
) -> list:
    """
    Map Aliv's relative-time events back to absolute UTC timestamps and
    map-matched GPS coordinates using the merged IMU+GPS DataFrame.

    Matching strategy: convert Aliv's start/end ms to absolute timestamps, then find
    the nearest rows in the raw df by created_at (UTC).

    `path` is built from matched_lat/matched_lon (road-snapped), not raw
    latitude/longitude — this is what ultimately lands in imu_events.path and
    then hexagons.lat/lon. `direction_label` is the mode across the event's
    window: a speedbreaker event is ~1-2s long, so direction won't flip
    mid-event, and taking the mode guards against a stray unmatched point
    near a junction skewing a single-point read.

    The event's median positive GPS speed is stored with its raw score inputs
    for the database's global parameter normalization.
    """
    enriched = []

    for event in result.get("speedbreakers", []):
        abs_start_ms = timesent_T0 + pd.to_timedelta(aliv_trim_offset + event["start_time"], unit="ms")
        abs_end_ms   = timesent_T0 + pd.to_timedelta(aliv_trim_offset + event["end_time"],   unit="ms")

        abs_start_ms_int = int(abs_start_ms.timestamp() * 1000)
        abs_end_ms_int   = int(abs_end_ms.timestamp() * 1000)
        median_speed_mps = median_speed_for_interval(
            gps_df["timestamp_ms"].tolist(),
            gps_df["speed"].tolist(),
            abs_start_ms_int,
            abs_end_ms_int,
        )
        if median_speed_mps is None:
            print(
                f"[aliv] No positive GPS speed for event "
                f"{abs_start_ms_int}-{abs_end_ms_int}; retaining the unadjusted legacy parameter."
            )

        subset = df[
            (df["timestamp_ms"] >= abs_start_ms_int) &
            (df["timestamp_ms"] <= abs_end_ms_int)
        ]

        if subset.empty:
            mid_ms = (abs_start_ms_int + abs_end_ms_int) // 2
            idx = (df["timestamp_ms"] - mid_ms).abs().idxmin()
            subset = df.iloc[[idx]]

        start_time = pd.to_datetime(subset["timestamp_ms"].iloc[0], unit="ms", utc=True)
        end_time   = pd.to_datetime(subset["timestamp_ms"].iloc[-1], unit="ms", utc=True)
        jerk_mps3 = estimate_velocity_jerk(
            gps_df["timestamp_ms"].tolist(),
            gps_df["speed"].tolist(),
            int(start_time.timestamp() * 1000),
        )

        lat_lon = (
            subset[["matched_lat", "matched_lon"]]
            .dropna()
            .drop_duplicates()
            .values
            .tolist()
        )
        if not lat_lon:
            continue

        first_lat, first_lon = lat_lon[0][0], lat_lon[0][1]
        h3_index = h3lib.latlng_to_cell(first_lat, first_lon, 9)

        metadata_subset = subset
        if "is_estimated" in metadata_subset.columns:
            metadata_subset = metadata_subset[
                ~metadata_subset["is_estimated"].fillna(False)
            ]

        dir_counts = metadata_subset["direction_label"].dropna().value_counts()
        event_direction = dir_counts.idxmax() if not dir_counts.empty else None

        way_counts = metadata_subset["osm_way_id"].dropna().value_counts()
        event_way_id = int(way_counts.idxmax()) if not way_counts.empty else None

        enriched.append({
            "user_id":    user_id,
            "vehicle_id": vehicle_id,
            "session_id": session_id,
            "h3_index":   h3_index,
            "start_time": pd.to_datetime(start_time, utc=True).astimezone(IST).isoformat(),
            "end_time":   pd.to_datetime(end_time, utc=True).astimezone(IST).isoformat(),
            "jerk_mps3":  jerk_mps3,
            "dp_og":      event["dp_og"],
            "dp":         event["dp"],
            "gymax":      event["gymax"],
            "stdp":       event["stdp"],
            "az_rms":     event["az_rms"],
            "median_speed_mps": median_speed_mps,
            "path":       lat_lon,
            "direction_label": event_direction,
            "osm_way_id": event_way_id,
        })

    return enriched

def estimate_fs(df: pd.DataFrame, time_col: str = "timestamp_ms") -> int:
    diffs = df[time_col].diff().dropna()
    median_gap_ms = diffs.median()
    fs = round(1000 / median_gap_ms)
    print(f"[estimate_fs] median gap={median_gap_ms:.2f}ms → fs={fs}Hz")
    return fs

def run_aliv(rows: list, fs: int) -> dict:
    aliv = AlivRoadDefects(verbose=False, fs=fs)
    result = aliv.analyze_batch(rows)
    print(f"[aliv] Speedbreakers found: {len(result.get('speedbreakers', []))}")
    return result


# ── Session-flag helpers ────────────────────────────────────────────────────

def _get_session_flags(supabase_source, session_id: str) -> dict:
    resp = _execute_with_retry(
        supabase_source.table("sessions")
        .select("aliv_processed, imu_only")
        .eq("session_id", session_id)
    )
    return resp.data[0] if resp.data else {}


def _set_test_db_processed(supabase_production_source, session_id: str, processed: bool) -> None:
    _execute_with_retry(
        supabase_production_source.table("sessions")
        .update({"test_db_processed": processed})
        .eq("session_id", session_id)
    )


def _ensure_test_target_user(supabase_source, supabase_target, user_id: str) -> None:
    target_user = _execute_with_retry(
        supabase_target.table("user_details")
        .select("*")
        .eq("firebaseuid", user_id)
        .limit(1)
    )
    source_user = _execute_with_retry(
        supabase_source.table("user_details")
        .select("*")
        .eq("firebaseuid", user_id)
        .limit(1)
    )
    if not source_user.data:
        raise ValueError(f"Source user_details row for {user_id} was not found.")

    target_user_data = dict(source_user.data[0])
    if target_user.data:
        existing_data = target_user.data[0]
        for column in ("distance", "frozen_ellar", "liquid_ellar"):
            if column in existing_data:
                target_user_data[column] = existing_data[column]
        _execute_with_retry(
            supabase_target.table("user_details")
            .update(target_user_data)
            .eq("firebaseuid", user_id)
        )
        return

    for column in ("distance", "frozen_ellar", "liquid_ellar"):
        if column in target_user_data:
            target_user_data[column] = 0.0
    _execute_with_retry(
        supabase_target.table("user_details").insert(target_user_data)
    )


def _ensure_test_target_vehicle(
    supabase_source,
    supabase_target,
    vehicle_id: int,
    user_id: str,
) -> int:
    source_vehicle = _execute_with_retry(
        supabase_source.table("vehicle_details")
        .select("*")
        .eq("vehicleid", vehicle_id)
        .limit(1)
    )
    if not source_vehicle.data:
        raise ValueError(f"Source vehicle_details row for {vehicle_id} was not found.")

    source_vehicle_data = source_vehicle.data[0]
    target_vehicles = _execute_with_retry(
        supabase_target.table("vehicle_details")
        .select("*")
        .eq("firebaseuid", user_id)
    )
    registration = source_vehicle_data.get("registration")
    if registration:
        for target_vehicle in target_vehicles.data or []:
            if target_vehicle.get("registration") == registration:
                vehicle_data = dict(source_vehicle_data)
                vehicle_data.pop("vehicleid", None)
                vehicle_data["firebaseuid"] = user_id
                _execute_with_retry(
                    supabase_target.table("vehicle_details")
                    .update(vehicle_data)
                    .eq("vehicleid", target_vehicle["vehicleid"])
                )
                return int(target_vehicle["vehicleid"])

    source_vehicle_values = {
        key: value for key, value in source_vehicle_data.items()
        if key != "vehicleid"
    }
    for target_vehicle in target_vehicles.data or []:
        if all(target_vehicle.get(key) == value for key, value in source_vehicle_values.items()):
            return int(target_vehicle["vehicleid"])

    vehicle_data = dict(source_vehicle_data)
    vehicle_data.pop("vehicleid", None)
    vehicle_data["firebaseuid"] = user_id
    inserted_vehicle = _execute_with_retry(
        supabase_target.table("vehicle_details")
        .insert(vehicle_data)
        .select("vehicleid")
    )
    if not inserted_vehicle.data:
        raise RuntimeError(f"Target insert did not return vehicleid for source vehicle {vehicle_id}.")
    return int(inserted_vehicle.data[0]["vehicleid"])


def _ensure_test_target_session(supabase_source, supabase_target, session_id: str) -> int:
    target_session = _execute_with_retry(
        supabase_target.table("sessions")
        .select("session_id, vehicle_id")
        .eq("session_id", session_id)
        .limit(1)
    )
    if target_session.data:
        return int(target_session.data[0]["vehicle_id"])

    source_session = _execute_with_retry(
        supabase_source.table("sessions")
        .select("*")
        .eq("session_id", session_id)
        .limit(1)
    )
    if not source_session.data:
        raise ValueError(f"Source session {session_id} was not found for target event insertion.")

    user_id = source_session.data[0]["user_id"]
    source_vehicle_id = source_session.data[0]["vehicle_id"]
    _ensure_test_target_user(supabase_source, supabase_target, user_id)
    target_vehicle_id = _ensure_test_target_vehicle(
        supabase_source,
        supabase_target,
        source_vehicle_id,
        user_id,
    )
    target_session_data = dict(source_session.data[0])
    target_session_data.pop("test_db_processed", None)
    target_session_data["vehicle_id"] = target_vehicle_id
    target_session_data["distance"] = 0
    target_session_data["aliv_processed"] = False
    for column in ("liquid_ellar", "frozen_ellar"):
        if column in target_session_data:
            target_session_data[column] = 0.0
    _execute_with_retry(
        supabase_target.table("sessions").insert(target_session_data)
    )
    return target_vehicle_id


def _mark_aliv_processed(supabase_store, session_id: str) -> None:
    try:
        _execute_with_retry(
            supabase_store.table("sessions")
            .update({"aliv_processed": True})
            .eq("session_id", session_id)
        )
    except Exception as err:
        print(f"[process_trip] aliv_processed update failed: {err}")


def _update_session_distance(supabase_store, session_id: str, distance_km: float) -> None:
    _execute_with_retry(
        supabase_store.table("sessions")
        .update({"distance": distance_km})
        .eq("session_id", session_id)
    )


def _add_user_distance(supabase_target, user_id: str, distance_km: float) -> None:
    resp = _execute_with_retry(
        supabase_target.table("user_details")
        .select("distance")
        .eq("firebaseuid", user_id)
    )
    if resp.data:
        current_distance = float(resp.data[0].get("distance") or 0.0)
        _execute_with_retry(
            supabase_target.table("user_details")
            .update({"distance": current_distance + distance_km})
            .eq("firebaseuid", user_id)
        )
    else:
        _execute_with_retry(
            supabase_target.table("user_details")
            .insert({"firebaseuid": user_id, "distance": distance_km})
        )


# ── Mount-orientation check (imu_only) ──────────────────────────────────────
# Phone is mounted with its z-axis (camera) meant to point along the vehicle's
# direction of travel. We estimate the yaw offset between the two by
# correlating GPS-derived longitudinal acceleration (ground truth, axis-
# convention-free) against the horizontal components of the phone's gravity-
# compensated acceleration (user_accel_x/y/z), expressed in a basis anchored
# on the phone's own z-axis. No magnetometer is available, so this only works
# when the trip has genuine accel/braking events — see MIN_ACCEL_ENERGY.

def _wrap180(angle_deg: float) -> float:
    """Wrap an angle to (-180, 180]."""
    return (angle_deg + 180) % 360 - 180

def _estimate_gravity(imu_df: pd.DataFrame, window_s: float = GRAVITY_LOWPASS_WINDOW_S) -> np.ndarray:
    """Low-pass the RAW accel (which still contains gravity) to get the
    slowly-varying gravity direction in phone-frame, per IMU row.

    Uses a rolling median (per-axis) rather than a rolling mean: a mean gets
    dragged by short bump/pothole spikes and by sustained braking/accel
    events that approach the window length, both of which bias the inferred
    'down' direction. A median is far less sensitive to that kind of
    short-duration outlier since it only shifts once outliers dominate the
    window.
    """
    fs_local = estimate_fs(imu_df)
    win = max(int(window_s * fs_local), 3)
    if win % 2 == 0:
        win += 1  # odd window keeps the median well-defined/centered

    g = imu_df[["accel_x", "accel_y", "accel_z"]].rolling(win, center=True, min_periods=1).median()
    norm = np.linalg.norm(g.values, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    return g.values / norm

def estimate_mount_yaw_offset(gps_df: pd.DataFrame, imu_df: pd.DataFrame) -> tuple[float, float]:
    """
    Returns (mount_yaw_offset_deg, signal_energy). signal_energy is the sum
    of |GPS-derived accel| across all usable windows — gate on this before
    trusting the angle, since a trip with no accel/braking events carries no
    information about mount alignment.

    Also gates on 'coherence' = |su, sv| / energy: even when total energy is
    high, su/sv can still be small/noise-dominated (e.g. events partially
    cancelling, or a corrupted gravity estimate on a rough/congested trip),
    in which case atan2 becomes extremely sensitive to noise. Low coherence
    is treated the same as low energy — caller should leave imu_only
    untouched rather than trust the angle.
    """
    g = gps_df.sort_values("timestamp_ms").reset_index(drop=True)
    g["speed_prev"] = g["speed"].shift(1)
    g["t_prev"] = g["timestamp_ms"].shift(1)
    g = g.dropna(subset=["speed_prev", "t_prev"])
    g = g[(g["speed"] >= MIN_SPEED_MPS) & (g["speed_prev"] >= MIN_SPEED_MPS)]
    if g.empty:
        return 0.0, 0.0

    dt_s = (g["timestamp_ms"] - g["t_prev"]) / 1000.0
    a_gps = (g["speed"] - g["speed_prev"]) / dt_s    # signed, m/s^2

    imu = imu_df.sort_values("timestamp_ms").reset_index(drop=True)
    gravity_hat = _estimate_gravity(imu)
    camera_hat = np.array([0.0, 0.0, -1.0])
    user_acc = imu[["user_accel_x", "user_accel_y", "user_accel_z"]].values

    u_hats, v_hats = [], []
    fallback_u = np.array([1.0, 0.0, 0.0])
    for gh in gravity_hat:
        u = camera_hat - np.dot(camera_hat, gh) * gh   # camera axis, projected horizontal
        u_norm = np.linalg.norm(u)
        u = u / u_norm if u_norm > 1e-6 else fallback_u
        v = np.cross(gh, u)                          # in-plane, perpendicular to u
        u_hats.append(u)
        v_hats.append(v)
    u_hats, v_hats = np.array(u_hats), np.array(v_hats)

    a_u_all = np.einsum("ij,ij->i", user_acc, u_hats)
    a_v_all = np.einsum("ij,ij->i", user_acc, v_hats)

    su = sv = energy = 0.0
    for t0, t1, ag in zip(g["t_prev"], g["timestamp_ms"], a_gps):
        mask = (imu["timestamp_ms"] >= t0) & (imu["timestamp_ms"] <= t1)
        if not mask.any():
            continue
        su += a_u_all[mask.values].mean() * ag
        sv += a_v_all[mask.values].mean() * ag
        energy += abs(ag)

    if su == 0 and sv == 0:
        return 0.0, energy

    magnitude = math.hypot(su, sv)
    coherence = magnitude / energy if energy > 0 else 0.0
    if coherence < MIN_COHERENCE:
        print(f"[estimate_mount_yaw_offset] low coherence ({coherence:.2f} < {MIN_COHERENCE}), "
            f"su={su:.2f} sv={sv:.2f} energy={energy:.2f} — angle unreliable, treating as zero-energy.")
        return 0.0, 0.0   # forces caller's MIN_ACCEL_ENERGY gate to reject it

    return math.degrees(math.atan2(sv, su)), energy

def _update_imu_only(
    supabase_source,
    session_id: str,
    gps_df: pd.DataFrame,
    imu_df: pd.DataFrame,
    current_imu_only: bool,
    persist: bool = True,
) -> bool:
    """Runs every time process_trip is invoked, independent of aliv_processed,
    so it can be iterated on/tested against sessions already processed by Aliv.

    imu_only defaults to True at the DB level (fail-closed: treat a session as
    IMU-only/unreliable-mount until proven otherwise). This function only ever
    writes when it has a confident measurement:
      - offset within ANGLE_THRESHOLD_DEG  -> write False (mount confirmed aligned)
      - offset beyond ANGLE_THRESHOLD_DEG  -> write True  (mount confirmed misaligned)
    If the signal is too weak or incoherent to trust, it writes nothing and
    leaves the column at whatever it already is.

    Returns the resolved imu_only value (freshly written value, or
    current_imu_only if left untouched / write failed) so the caller can pass
    a single authoritative value down to update_hexagons/ledger. When persist
    is false, it computes the value without writing a session row.
    """
    mount_yaw_deg, signal_energy = estimate_mount_yaw_offset(gps_df, imu_df)
    print(f"[process_trip] mount yaw offset: {mount_yaw_deg:.1f}deg (energy={signal_energy:.1f})")

    if signal_energy < MIN_ACCEL_ENERGY:
        print(f"[process_trip] insufficient accel signal ({signal_energy:.1f} < {MIN_ACCEL_ENERGY}), leaving imu_only untouched.")
        return current_imu_only

    imu_only_value = abs(mount_yaw_deg) > ANGLE_THRESHOLD_DEG
    if not persist:
        print(f"[process_trip] computed imu_only={imu_only_value} without persisting it.")
        return imu_only_value

    try:
        _execute_with_retry(
            supabase_source.table("sessions")
            .update({"imu_only": imu_only_value})
            .eq("session_id", session_id)
        )
        print(f"[process_trip] imu_only set to {imu_only_value} (offset={mount_yaw_deg:.1f}deg, threshold={ANGLE_THRESHOLD_DEG})")
    except Exception as imu_only_err:
        print(f"[process_trip] imu_only update failed: {imu_only_err}")
        return current_imu_only

    return imu_only_value
# ── Core processing ────────────────────────────────────────────────────────────

@_serialize_pipeline
def process_trip(
    session_id: str,
    vehicle_id: int,
    user_id: str,
    start_time: str,
    end_time: str,
    target_role: str = "auto",
):
    print(f"[process_trip] session={session_id} vehicle={vehicle_id} user={user_id} {start_time} → {end_time}")

    try:
        _process_trip_with_audit(
            session_id,
            vehicle_id,
            user_id,
            start_time,
            end_time,
            target_role=target_role,
        )
    except Exception as err:
        # This is a BackgroundTask — an uncaught exception here is otherwise
        # completely invisible to the Supabase trigger (which already got
        # its 200 OK) and easy to miss in Railway's log stream. Surface it
        # loudly so a failed session is at least noticeable, and don't let
        # aliv_processed get set for a run that didn't finish.
        print(f"[process_trip] FAILED for session={session_id}: {err!r}")
        raise


def _process_trip_with_audit(
    session_id: str,
    vehicle_id: int,
    user_id: str,
    start_time: str,
    end_time: str,
    target_role: str = "auto",
) -> None:
    processing_run_id = str(uuid4())
    processing_context: dict[str, str] = {}
    processing_error: Exception | None = None
    try:
        _process_trip_inner(
            session_id,
            vehicle_id,
            user_id,
            start_time,
            end_time,
            target_role=target_role,
            processing_run_id=processing_run_id,
            processing_context=processing_context,
        )
    except Exception as err:
        processing_error = err
        raise
    finally:
        resolved_target = processing_context.get("target_role")
        if resolved_target:
            try:
                completed_at_ist = datetime.now(IST).replace(tzinfo=None).isoformat()
                logger_targets = (
                    [_make_test_target_client(), _make_production_target_client()]
                    if resolved_target == "test"
                    else [_make_production_target_client()]
                )
                for supabase_target in logger_targets:
                    _execute_with_retry(
                        supabase_target.table("logger")
                        .update({"created_at": completed_at_ist})
                        .eq("processing_run_id", processing_run_id)
                    )
            except Exception as audit_err:
                if processing_error is not None:
                    raise RuntimeError(
                        f"Session {session_id} processing failed with "
                        f"{processing_error!r}, and logger completion timestamp "
                        f"could not be recorded: {audit_err!r}"
                    ) from audit_err
                raise


def _process_trip_inner(
    session_id: str,
    vehicle_id: int,
    user_id: str,
    start_time: str,
    end_time: str,
    target_role: str = "auto",
    processing_run_id: str | None = None,
    processing_context: dict[str, str] | None = None,
):
    supabase_source = _make_production_source_client()
    supabase_test = _make_test_target_client()
    source_flags = _get_session_flags(supabase_source, session_id)
    test_session_exists = _target_session_exists(supabase_test, session_id)

    if target_role == "auto":
        target_role = "production" if test_session_exists else "test"
    if target_role not in ("test", "production"):
        raise ValueError(f"Unknown processing target: {target_role}")
    if processing_context is not None:
        processing_context["target_role"] = target_role

    supabase_source = _make_production_source_client(
        session_id,
        processing_run_id,
        target_role,
    )
    supabase_test = _make_test_target_client(
        session_id,
        processing_run_id,
        target_role,
    )
    is_test_target = target_role == "test"

    supabase_target = (
        supabase_test
        if is_test_target
        else _make_production_target_client(
            session_id,
            processing_run_id,
            target_role,
        )
    )
    target_flags = (
        _get_session_flags(supabase_target, session_id)
        if (not is_test_target or test_session_exists)
        else {}
    )
    already_processed = bool(target_flags.get("aliv_processed"))
    session_store = supabase_target
    flags = target_flags or source_flags
    current_imu_only = bool(flags.get("imu_only", True))
    if already_processed:
        print(f"[process_trip] session {session_id} already aliv_processed — will re-check imu_only, then skip duplicate outputs.")
    # ── 1. Fetch IMU data ──────────────────────────────────────────────────────
    if not SOURCE_DATABASE_URL:
        raise RuntimeError("SOURCE_DATABASE_URL must be configured for sensor-data reads")
    with closing(
        psycopg2.connect(
            SOURCE_DATABASE_URL,
            connect_timeout=10,
            sslmode="require",
        )
    ) as source_db:
        imu_rows = fetch_sensor_rows(source_db, "imu_data", session_id)
        print(f"[process_trip] IMU rows fetched: {len(imu_rows)}")
        if not imu_rows:
            print("[process_trip] No IMU data, skipping.")
            return

        # ── 2. Fetch GPS data ──────────────────────────────────────────────────
        gps_rows = fetch_sensor_rows(source_db, "gps_data", session_id)
    print(f"[process_trip] GPS rows fetched: {len(gps_rows)}")
    if not gps_rows:
        print("[process_trip] No GPS data, skipping.")
        return

    gps_df = pd.DataFrame(gps_rows)
    target_vehicle_id = vehicle_id

    if not already_processed and len(gps_rows) >= 2:
        try:
            _load_map_matcher_for_trace(gps_df)
        except MapCoverageUnavailableError as err:
            raise MapCoverageUnavailableError(
                str(err),
                gps_point_count=len(gps_rows),
            ) from err
        gps_df = map_match_trip(gps_df)
        if gps_df["osm_way_id"].isna().any():
            estimated_positions = estimate_gps_positions_from_yaw(
                imu_rows,
                gps_df,
            )
        else:
            estimated_positions = {}
        gps_df = apply_estimated_positions(gps_df, estimated_positions)
        gps_df = map_match_estimated_positions(gps_df)

        matched_records = gps_df[[
            "timestamp_ms", "matched_lat", "matched_lon", "osm_way_id",
            "direction_label", "match_raw_distance", "is_estimated",
        ]].to_dict(orient="records")
        matched_records = [sanitize_for_json(row) for row in matched_records]

        has_accepted_match = any(
            row.get("osm_way_id") is not None
            and row.get("matched_lat") is not None
            and row.get("matched_lon") is not None
            for row in matched_records
        )
        has_usable_positions = has_accepted_match or any(
            row.get("is_estimated")
            and row.get("matched_lat") is not None
            and row.get("matched_lon") is not None
            for row in matched_records
        )
        if is_test_target and has_usable_positions:
            target_vehicle_id = _ensure_test_target_session(
                supabase_source, supabase_target, session_id
            )
            test_session_exists = True
            _set_test_db_processed(supabase_source, session_id, True)

        if has_usable_positions:
            for row in matched_records:
                row["session_id"] = session_id
            try:
                _execute_with_retry(
                    supabase_target.table("matched_gps_data")
                    .delete()
                    .eq("session_id", session_id)
                )
                _execute_with_retry(
                    supabase_target.table("matched_gps_data").insert(matched_records)
                )
            except Exception as match_err:
                raise RuntimeError(
                    f"Could not persist matched GPS rows for session "
                    f"{session_id}: {match_err!r}"
                ) from match_err

            stored_matched_rows = fetch_all_pages(
                supabase_target,
                table="matched_gps_data",
                filters=[("eq", "session_id", session_id)],
                order_col="timestamp_ms",
            )
            total_distance_m = compute_matched_distance(
                pd.DataFrame(stored_matched_rows)
            )
        else:
            total_distance_m = 0.0
    else:
        total_distance_m = 0.0

    print(
        f"[process_trip] matched-road distance from {target_role} target: "
        f"{total_distance_m:.2f} m"
    )

    if test_session_exists:
        _set_test_db_processed(supabase_source, session_id, True)
    elif not is_test_target:
        _set_test_db_processed(supabase_source, session_id, False)

    if len(gps_rows) < MIN_GPS_POINTS:
        print(
            f"[process_trip] Only {len(gps_rows)} GPS points "
            f"(< {MIN_GPS_POINTS}); skipping Aliv."
        )
        if not already_processed and total_distance_m > 0:
            _update_session_distance(session_store, session_id, total_distance_m / 1000)
            _add_user_distance(supabase_target, user_id, total_distance_m / 1000)
        _mark_aliv_processed(session_store, session_id)
        return

    # ── 3. Merge prep + mount-orientation check ─────────────────────────────
    # imu_only doesn't depend on map-matching (it reads raw gps_df + imu_df
    # directly), so it still runs here, before we decide whether to bother
    # matching/Aliv-ing this trip at all — same "every run, regardless of
    # aliv_processed" behavior as before.
    imu_df = pd.DataFrame(imu_rows)
    imu_df["created_at"] = pd.to_datetime(imu_df["created_at"], utc=True, errors="coerce")
    fs = estimate_fs(imu_df, time_col="timestamp_ms")

    imu_only = _update_imu_only(
        session_store,
        session_id,
        gps_df,
        imu_df,
        current_imu_only,
        persist=True,
    )

    if already_processed:
        print("[process_trip] Finished (imu_only re-check only).")
        return

    if total_distance_m <= 0:
        print("[process_trip] No positive-distance data, skipping target records and processing.")
        _update_session_distance(session_store, session_id, 0.0)
        _mark_aliv_processed(session_store, session_id)
        return

    if is_test_target:
        _execute_with_retry(
            supabase_target.table("sessions")
            .update({"imu_only": imu_only})
            .eq("session_id", session_id)
        )

    if total_distance_m < MIN_TRIP_DISTANCE_M:
        print(f"[process_trip] Trip moved only {total_distance_m:.2f}m "
            f"(< {MIN_TRIP_DISTANCE_M}m), skipping map-matching/Aliv.")
        _update_session_distance(session_store, session_id, total_distance_m / 1000)
        _add_user_distance(supabase_target, user_id, total_distance_m / 1000)
        _mark_aliv_processed(session_store, session_id)
        return

    df = merge_gps_into_imu(imu_df, gps_df)
    timesent_T0 = pd.to_datetime(df["timestamp_ms"].iloc[0], unit="ms", utc=True)

    # ── 3b. Update sessions.distance ────────────────────────────────────────
    _update_session_distance(session_store, session_id, total_distance_m / 1000)

    # ── 3c-geo. Record which geographies this trip covered ──────────────────
    try:
        add_session_geographies(
            supabase_target,
            user_id,
            zip(gps_df["latitude"], gps_df["longitude"]),
            run=_execute_with_retry,
        )
    except Exception as geo_err:
        print(f"[process_trip] geographies update failed: {geo_err!r}")

    # ── 3d. Increment cumulative distance in user_details ──────────────────────
    _add_user_distance(supabase_target, user_id, total_distance_m / 1000)

    # ── 4. Run Aliv ──────────────
    aliv_input = build_aliv_input(df)
    result = run_aliv(aliv_input, fs=fs)
    keep = ~edge_slow_mask(gps_df["latitude"].values, gps_df["longitude"].values, gps_df["speed"].values)
    pass_df = gps_df[keep]

    if not result.get("speedbreakers"):
        print("[process_trip] No events detected.")
        _record_passes_safe(supabase_target, pass_df)      # NEW
        _mark_aliv_processed(session_store, session_id)
        return
    aliv_trim_offset = 0 #50 * (1000 / fs)

    # ── 5. Enrich events (matched coordinates + direction_label) ───────────────
    enriched_events = enrich_events(
        session_id, target_vehicle_id, user_id, result, df, gps_df, timesent_T0, aliv_trim_offset
    )
    print(f"[process_trip] Enriched events: {len(enriched_events)}")
    if not enriched_events:
        _record_passes_safe(supabase_target, pass_df)
        _mark_aliv_processed(session_store, session_id)
        return

    enriched_events = [sanitize_for_json(e) for e in enriched_events]

    # ── 6. Insert road defects ─────────────────────────────────────────────────
    # user_id and vehicle_id are not columns on imu_events anymore —
    # they're derivable via session_id. Strip them from the DB insert.
    # direction_label and osm_way_id ARE real columns on imu_events (see
    # migration.sql) and pass through untouched.
    events_for_db = [
        {
            k: v for k, v in e.items()
            if k not in ("vehicle_id", "user_id", "jerk_mps3")
        }
        for e in enriched_events
    ]
    insert_response = _execute_with_retry(
        supabase_target.table("imu_events").insert(events_for_db)
    )
    inserted_events = insert_response.data

    # Re-attach id (renamed), user_id and vehicle_id for the hexagons step.
    for i, event in enumerate(inserted_events):
        event["id"]         = event.pop("imu_events_id")
        event["user_id"]    = enriched_events[i]["user_id"]
        event["vehicle_id"] = target_vehicle_id
        event["jerk_mps3"]  = enriched_events[i]["jerk_mps3"]

    # ── 7. Update hexagons ─────────────────────────────────────────────────────
    try:
        update_hexagons(supabase_target, inserted_events, imu_only, test_mode=False)
    except Exception as hex_err:
        print(f"[hexagons] update failed: {hex_err}")
        raise

    _record_passes_safe(supabase_target, pass_df)
    _mark_aliv_processed(session_store, session_id)
    print("[process_trip] Finished.")


# ── Security middleware ────────────────────────────────────────────────────────

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response


# ── Webhook endpoint ───────────────────────────────────────────────────────────

def _enqueue_session(payload: WebhookPayload, target_role: str = "auto") -> None:
    session = payload.record
    _trip_queue.put((
        session.session_id,
        session.vehicle_id,
        session.user_id,
        session.start_time,
        session.end_time,
        target_role,
    ))


@app.post("/Aliv_for_MVP1")
def Aliv_for_MVP1(payload: WebhookPayload):
    _enqueue_session(payload)
    return {"status": "received"}


@app.post("/resume_trip_queue")
def resume_trip_queue(x_api_key: str = Header(None)):
    _require_map_queue_api_key(x_api_key)

    with _trip_state_lock:
        if _blocked_trip is None:
            raise HTTPException(
                status_code=409,
                detail="The trip queue is not halted for missing map data",
            )
        blocked_session_id = _blocked_trip[0]
        _trip_resume_event.set()

    print(
        f"[trip_worker] manual resume requested for "
        f"blocked session={blocked_session_id}"
    )
    return {
        "status": "resume_requested",
        "session_id": blocked_session_id,
        "queued_sessions": _trip_queue.qsize(),
    }


def _require_map_queue_api_key(x_api_key: str | None) -> None:
    expected = os.environ.get("MAP_QUEUE_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="MAP_QUEUE_API_KEY is not configured",
        )
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/register_map_region")
def register_map_region(
    payload: MapRegionRegistration,
    x_api_key: str = Header(None),
):
    _require_map_queue_api_key(x_api_key)
    try:
        region = register_road_region(payload.region_id, payload.bounds)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    with _trip_state_lock:
        blocked_session_id = _blocked_trip[0] if _blocked_trip else None
        if blocked_session_id:
            _trip_resume_event.set()

    print(
        f"[map_matching] registered region={region.region_id} "
        f"bounds={region.bounds} object={region.filename}"
    )
    if blocked_session_id:
        print(
            f"[trip_worker] resuming blocked session={blocked_session_id} "
            f"after region registration"
        )
    return {
        "status": "registered_and_resuming" if blocked_session_id else "registered",
        "region_id": region.region_id,
        "object": region.filename,
        "session_id": blocked_session_id,
    }


@app.get("/public/ellar-totals")
def get_public_ellar_totals():
    if not TARGET_PRODUCTION_URL or not TARGET_PRODUCTION_KEY:
        raise HTTPException(status_code=503, detail="Ellar totals are unavailable")

    totals = {"frozen_ellar": 0.0, "liquid_ellar": 0.0}
    page_size = 1000
    start = 0

    try:
        supabase_target = _make_production_target_client()
        while True:
            response = _execute_with_retry(
                supabase_target.table("user_details")
                .select("frozen_ellar, liquid_ellar")
                .range(start, start + page_size - 1)
            )
            rows = response.data or []

            for row in rows:
                for column in totals:
                    value = row.get(column)
                    if value is not None:
                        amount = float(value)
                        if math.isfinite(amount):
                            totals[column] += amount

            if len(rows) < page_size:
                break
            start += page_size
    except Exception as err:
        print(f"[ellar-totals] failed to sum user_details: {err}")
        raise HTTPException(status_code=502, detail="Unable to retrieve Ellar totals") from err

    return totals


# ── Full-pipeline replay ─────────────────────────────────────────────────────
# Reprocesses every existing session strictly in order of end_time (oldest trip
# first — the trip that finished first gets discovery rights, matching the
# original chronological order the reward/confidence logic assumes). Each
# endpoint selects one target explicitly, preventing cross-database resets.
# Calls _process_trip_inner() directly rather than round-tripping
# through the webhook: since it's a normal (non-background) function call
# inside this loop, by the time it returns the session's aliv_processed flag
# is already True, so "wait for the flag" is just "the call returned" — no
# webhook, no created_at trick, no polling needed.

@_serialize_pipeline
def _replay_all_sessions_inner(target_role: str) -> None:
    if target_role not in ("test", "production"):
        raise ValueError(f"Unknown replay target: {target_role}")
    with _trip_state_lock:
        if _blocked_trip is not None:
            raise RuntimeError(
                f"Cannot start replay while live queue is halted at "
                f"session={_blocked_trip[0]} for missing map data."
            )
    supabase_source = _make_production_source_client()
    supabase_target = (
        _make_test_target_client()
        if target_role == "test"
        else _make_production_target_client()
    )
    sessions = fetch_all_pages(
        supabase_source,
        table="sessions",
        filters=[("filter", "end_time", "not.is", "null")],   # drop null end_time server-side
        order_col="end_time",
        tiebreak_col="session_id",
    )
    print(
        f"[replay] resetting {target_role} target; "
        f"{len(sessions)} source sessions in chronological order."
    )

    try:
        if target_role == "test":
            _execute_with_retry(
                _make_production_target_client()
                .table("logger")
                .delete()
                .eq("processing_target", "test")
            )
            _delete_all_rows(supabase_target, "logger", "record_id")
            for table_name, key_column in (
                ("ledger", "ledger_id"),
                ("hexagons", "id"),
                ("imu_events", "imu_events_id"),
                ("matched_gps_data", "session_id"),
                ("geographies", "key"),
                ("sessions", "session_id"),
                ("vehicle_details", "vehicleid"),
                ("user_details", "firebaseuid"),
            ):
                _delete_all_rows(supabase_target, table_name, key_column)
            _execute_with_retry(
                supabase_source.table("sessions")
                .update({"test_db_processed": False})
                .not_.is_("session_id", "null")
            )
        else:
            _delete_all_rows(supabase_target, "logger", "record_id")
            _execute_with_retry(supabase_target.rpc("reset_pipeline", {}))
            _delete_all_rows(supabase_target, "matched_gps_data", "session_id")
            _delete_all_rows(supabase_target, "geographies", "key")

            vehicle_rows = fetch_all_pages(
                supabase_target,
                table="vehicle_details",
                filters=[],
                order_col="vehicleid",
            )
            for vehicle in vehicle_rows:
                distance = vehicle.get("distance")
                if distance is None:
                    continue
                _execute_with_retry(
                    supabase_target.table("vehicle_details")
                    .update({
                        "distance": (
                            float(distance) + REPLAY_DISTANCE_ROUNDING_BUFFER_KM
                        )
                    })
                    .eq("vehicleid", vehicle["vehicleid"])
                )

            _execute_with_retry(
                supabase_target.table("sessions")
                .update({
                    "distance": 0,
                    "liquid_ellar": 0,
                    "frozen_ellar": 0,
                    "aliv_processed": False,
                    "imu_only": True,
                })
                .not_.is_("session_id", "null")
            )
            _execute_with_retry(
                supabase_target.table("vehicle_details")
                .update({"distance": 0})
                .not_.is_("vehicleid", "null")
            )
            _execute_with_retry(
                supabase_target.table("user_details")
                .update({
                    "distance": 0,
                    "liquid_ellar": 0,
                    "frozen_ellar": 0,
                })
                .not_.is_("firebaseuid", "null")
            )
    except Exception as err:
        raise RuntimeError(f"Failed to reset {target_role} replay target: {err!r}") from err

    _process_sessions_in_order(
        sessions,
        target_role,
        operation="replay",
    )


def _process_sessions_in_order(
    sessions: list[dict],
    target_role: str,
    operation: str,
) -> None:
    skipped_map_session_count = 0
    for i, session in enumerate(sessions):
        session_id = session["session_id"]
        print(
            f"[{operation}:{target_role}] ({i + 1}/{len(sessions)}) "
            f"session={session_id} end_time={session['end_time']}"
        )

        try:
            _process_trip_with_audit(
                session_id,
                session["vehicle_id"],
                session["user_id"],
                session["start_time"],
                session["end_time"],
                target_role=target_role,
            )
        except MapDataUnavailableError as trip_err:
            if (
                isinstance(trip_err, MapCoverageUnavailableError)
                and trip_err.gps_point_count is not None
                and trip_err.gps_point_count
                > MAP_COVERAGE_REPLAY_HALT_GPS_POINT_THRESHOLD
            ):
                print(
                    f"[{operation}:{target_role}] HALTED at session={session_id}; "
                    f"map coverage is unavailable for a trip with "
                    f"{trip_err.gps_point_count} GPS points "
                    f"(limit={MAP_COVERAGE_REPLAY_HALT_GPS_POINT_THRESHOLD}): "
                    f"{trip_err}"
                )
                raise RuntimeError(
                    f"{target_role} {operation} halted at session={session_id}; "
                    f"map coverage is unavailable for a trip with "
                    f"{trip_err.gps_point_count} GPS points "
                    f"(limit={MAP_COVERAGE_REPLAY_HALT_GPS_POINT_THRESHOLD}); "
                    f"later sessions were not processed: {trip_err}"
                ) from trip_err
            skipped_map_session_count += 1
            gps_count_note = (
                f" (GPS points={trip_err.gps_point_count})"
                if trip_err.gps_point_count is not None
                else ""
            )
            print(
                f"[{operation}:{target_role}] SKIPPED session={session_id} "
                f"because map data is unavailable{gps_count_note}: {trip_err}. "
                "Continuing with the next session."
            )
        except Exception as trip_err:
            print(
                f"[{operation}:{target_role}] HALTED at session {session_id} "
                "after processing failure: "
                f"{trip_err!r}"
            )
            raise RuntimeError(
                f"{target_role} {operation} halted at session={session_id}; "
                "later sessions were not processed to preserve chronological "
                f"processing order: {trip_err!r}"
            ) from trip_err
    print(
        f"[{operation}:{target_role}] finished processing sessions; "
        f"skipped {skipped_map_session_count} session(s) for unavailable map data."
    )


@_serialize_pipeline
def _resume_all_sessions_inner(target_role: str) -> None:
    if target_role not in ("test", "production"):
        raise ValueError(f"Unknown resume target: {target_role}")
    with _trip_state_lock:
        if _blocked_trip is not None:
            raise RuntimeError(
                f"Cannot resume {target_role} processing while live queue is "
                f"halted at session={_blocked_trip[0]} for missing map data."
            )

    supabase_source = _make_production_source_client()
    supabase_target = (
        _make_test_target_client()
        if target_role == "test"
        else _make_production_target_client()
    )
    completed_sessions = fetch_all_pages(
        supabase_target,
        table="sessions",
        filters=[
            ("eq", "aliv_processed", True),
            ("filter", "end_time", "not.is", "null"),
        ],
        order_col="end_time",
        tiebreak_col="session_id",
    )
    source_filters = [("filter", "end_time", "not.is", "null")]
    if completed_sessions:
        last_completed = completed_sessions[-1]
        source_filters.append((
            "or_",
            f"end_time.gt.{last_completed['end_time']},"
            "and("
            f"end_time.eq.{last_completed['end_time']},"
            f"session_id.gt.{last_completed['session_id']}"
            ")",
        ))
        print(
            f"[resume:{target_role}] continuing after "
            f"session={last_completed['session_id']} "
            f"end_time={last_completed['end_time']}"
        )
    else:
        print(
            f"[resume:{target_role}] no completed checkpoint found; "
            "starting from the earliest source session."
        )

    sessions = fetch_all_pages(
        supabase_source,
        table="sessions",
        filters=source_filters,
        order_col="end_time",
        tiebreak_col="session_id",
    )
    print(f"[resume:{target_role}] {len(sessions)} session(s) to process.")
    _process_sessions_in_order(
        sessions,
        target_role,
        operation="resume",
    )


@_serialize_pipeline
def _replay_all_test_sessions_inner():
    _replay_all_sessions_inner("test")


@_serialize_pipeline
def _replay_all_production_sessions_inner():
    _replay_all_sessions_inner("production")


@_serialize_pipeline
def _resume_all_test_sessions_inner():
    _resume_all_sessions_inner("test")


@_serialize_pipeline
def _resume_all_production_sessions_inner():
    _resume_all_sessions_inner("production")


@_serialize_pipeline
def _rollback_session_inner(session_id: str, target_role: str) -> None:
    if target_role not in ("test", "production"):
        raise ValueError(f"Unknown rollback target: {target_role}")

    source_session = _execute_with_retry(
        _make_production_source_client()
        .table("sessions")
        .select("end_time")
        .eq("session_id", session_id)
        .limit(1)
    )
    if not source_session.data:
        raise ValueError(f"Source session {session_id} was not found.")
    session_end_time = source_session.data[0]["end_time"]
    if session_end_time is None:
        raise ValueError(f"Session {session_id} has no end_time.")

    targets = (
        [
            ("test", _make_test_target_client()),
            ("production", _make_production_target_client()),
        ]
        if target_role == "test"
        else [("production", _make_production_target_client())]
    )
    for database_role, supabase_target in targets:
        result = _execute_with_retry(
            supabase_target.rpc(
                "rollback_session_processing",
                {
                    "p_session_id": session_id,
                    "p_session_end_time": session_end_time,
                    "p_processing_target": target_role,
                },
            )
        )
        print(
            f"[rollback:{target_role}] database={database_role} "
            f"result={result.data!r}"
        )


@app.post("/replay_all_sessions/test")
def replay_all_test_sessions(background_tasks: BackgroundTasks):
    background_tasks.add_task(_replay_all_test_sessions_inner)
    return {"status": "test replay started"}


@app.post("/replay_all_sessions/production")
def replay_all_production_sessions(background_tasks: BackgroundTasks):
    background_tasks.add_task(_replay_all_production_sessions_inner)
    return {"status": "production replay started"}


@app.post("/resume_all_sessions/test")
def resume_all_test_sessions(
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(None),
):
    _require_map_queue_api_key(x_api_key)
    background_tasks.add_task(_resume_all_test_sessions_inner)
    return {"status": "test processing resume started"}


@app.post("/resume_all_sessions/production")
def resume_all_production_sessions(
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(None),
):
    _require_map_queue_api_key(x_api_key)
    background_tasks.add_task(_resume_all_production_sessions_inner)
    return {"status": "production processing resume started"}


@app.post("/rollback_sessions/test")
def rollback_test_sessions(
    payload: SessionRollbackRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(None),
):
    _require_map_queue_api_key(x_api_key)
    background_tasks.add_task(
        _rollback_session_inner,
        payload.session_id,
        "test",
    )
    return {"status": "test rollback started", "session_id": payload.session_id}


@app.post("/rollback_sessions/production")
def rollback_production_sessions(
    payload: SessionRollbackRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(None),
):
    _require_map_queue_api_key(x_api_key)
    background_tasks.add_task(
        _rollback_session_inner,
        payload.session_id,
        "production",
    )
    return {
        "status": "production rollback started",
        "session_id": payload.session_id,
    }


def _delete_all_rows(supabase_target, table_name: str, key_column: str) -> None:
    _execute_with_retry(
        supabase_target.table(table_name).delete().not_.is_(key_column, "null")
    )


@_serialize_pipeline
def _session_gps_points(session_id: str):
    with closing(psycopg2.connect(SOURCE_DATABASE_URL, connect_timeout=10, sslmode="require")) as db:
        rows = fetch_sensor_rows(db, "gps_data", session_id)
    return [(r["latitude"], r["longitude"]) for r in rows]


def _backfill_geographies_inner():
    supabase_source = _make_production_source_client()
    supabase_target = _make_production_target_client()
    sessions = fetch_all_pages(
        supabase_source,
        table="sessions",
        filters=[("gte", "distance", MIN_TRIP_DISTANCE_M / 1000)],   # distance is stored in km
        order_col="session_id",
    )
    print(f"[geographies-backfill] {len(sessions)} sessions with distance > 0")
    backfill_all_geographies(
        supabase_target,
        [(s["session_id"], s["user_id"]) for s in sessions],
        _session_gps_points,
        run=_execute_with_retry,
    )


@app.post("/backfill_geographies")
def backfill_geographies(background_tasks: BackgroundTasks, x_api_key: str = Header(None)):
    expected = os.environ.get("BACKFILL_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="BACKFILL_API_KEY not configured")
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    background_tasks.add_task(_backfill_geographies_inner)
    return {"status": "backfill started"}