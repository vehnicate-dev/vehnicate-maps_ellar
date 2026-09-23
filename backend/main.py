from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import pandas as pd
import numpy as np
import math
import time
import queue
import threading
import httpx
from supabase import create_client, ClientOptions
import httpcore
from aliv_module import AlivRoadDefects
import h3 as h3lib
import os
from dotenv import load_dotenv
from hexagons_update import update_hexagons
from zoneinfo import ZoneInfo
from distance import compute_total_distance
from map_matching import init_map_matcher, map_match_trip

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
            match_raw_distance — used by enrich_events() for reported
            defect locations/direction, NOT fed into Aliv.

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

SOURCE_URL = os.environ.get("SOURCE_URL")
SOURCE_KEY = os.environ.get("SOURCE_KEY")
TARGET_URL = os.environ.get("TARGET_URL")
TARGET_KEY = os.environ.get("TARGET_KEY")

# Chennai OSM extract used for map-matching. Loaded once at startup;
# downloaded automatically to OSM_PBF_PATH if not already present (Railway's
# filesystem is ephemeral, so this runs on every fresh deploy/restart).
OSM_PBF_PATH = os.environ.get("OSM_PBF_PATH", "chennai.osm.pbf")
OSM_PBF_URL = os.environ.get("OSM_PBF_URL")  # direct .osm.pbf download link

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
MIN_GPS_POINTS = 10  # fewer raw GPS fixes than this → too sparse to trust map-matching/distance/Aliv
MIN_TRIP_DISTANCE_M = 50  # trips that moved less than this overall aren't worth map-matching/Aliv
app = FastAPI()


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
_trip_queue: "queue.Queue[tuple]" = queue.Queue()


def _trip_worker() -> None:
    while True:
        session_id, vehicle_id, user_id, start_time, end_time = _trip_queue.get()
        try:
            process_trip(session_id, vehicle_id, user_id, start_time, end_time)
        except Exception as err:
            # process_trip() already logs and re-raises internally; catch here
            # too so one bad trip can never kill the worker thread and silently
            # stop all future processing.
            print(f"[trip_worker] session={session_id} raised: {err!r}")
        finally:
            _trip_queue.task_done()


@app.on_event("startup")
def _start_trip_worker() -> None:
    threading.Thread(target=_trip_worker, daemon=True).start()


@app.on_event("startup")
def _load_map_matcher() -> None:
    # Parsing the OSM extract into an InMemMap is expensive — do it once per
    # process, never inside process_trip().
    try:
        init_map_matcher(OSM_PBF_PATH, OSM_PBF_URL)
    except Exception as err:
        # Don't crash the whole service if the extract is missing/misconfigured
        # in a given environment — map_match_trip() will raise per-request
        # instead, which surfaces clearly in that trip's background-task log.
        print(f"[startup] map matcher failed to initialize: {err!r}")


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


def _make_supabase_client(url: str, key: str):
    return create_client(url, key, options=_SUPABASE_CLIENT_OPTIONS)


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
    while True:
        query = supabase_client.table(table).select("*")
        for method, *args in filters:
            query = getattr(query, method)(*args)
        query = query.order(order_col, desc=False)
        if tiebreak_col:
            query = query.order(tiebreak_col, desc=False)   # deterministic tiebreak
        batch = _execute_with_retry(
            query.range(start, start + page_size - 1)
        ).data

        if not batch:
            break

        all_data.extend(batch)

        if len(batch) < page_size:
            break

        start += page_size

    print(f"[fetch_all_pages] {table}: total rows fetched = {len(all_data)}")
    return all_data

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
        ]],
        on="timestamp_ms",
        direction="nearest",
    )


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
    """
    enriched = []

    for event in result.get("speedbreakers", []):
        abs_start_ms = timesent_T0 + pd.to_timedelta(aliv_trim_offset + event["start_time"], unit="ms")
        abs_end_ms   = timesent_T0 + pd.to_timedelta(aliv_trim_offset + event["end_time"],   unit="ms")

        abs_start_ms_int = int(abs_start_ms.timestamp() * 1000)
        abs_end_ms_int   = int(abs_end_ms.timestamp() * 1000)

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

        dir_counts = subset["direction_label"].dropna().value_counts()
        event_direction = dir_counts.idxmax() if not dir_counts.empty else None

        way_counts = subset["osm_way_id"].dropna().value_counts()
        event_way_id = int(way_counts.idxmax()) if not way_counts.empty else None

        enriched.append({
            "user_id":    user_id,
            "vehicle_id": vehicle_id,
            "session_id": session_id,
            "h3_index":   h3_index,
            "start_time": pd.to_datetime(start_time, utc=True).astimezone(IST).isoformat(),
            "end_time":   pd.to_datetime(end_time, utc=True).astimezone(IST).isoformat(),
            "parameter":  event["parameter"],
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

def _mark_aliv_processed(supabase_source, session_id: str) -> None:
    try:
        _execute_with_retry(
            supabase_source.table("sessions")
            .update({"aliv_processed": True})
            .eq("session_id", session_id)
        )
    except Exception as err:
        print(f"[process_trip] aliv_processed update failed: {err}")


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
    a single authoritative value down to update_hexagons/ledger.
    """
    mount_yaw_deg, signal_energy = estimate_mount_yaw_offset(gps_df, imu_df)
    print(f"[process_trip] mount yaw offset: {mount_yaw_deg:.1f}deg (energy={signal_energy:.1f})")

    if signal_energy < MIN_ACCEL_ENERGY:
        print(f"[process_trip] insufficient accel signal ({signal_energy:.1f} < {MIN_ACCEL_ENERGY}), leaving imu_only untouched.")
        return current_imu_only

    imu_only_value = abs(mount_yaw_deg) > ANGLE_THRESHOLD_DEG
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

def process_trip(session_id: str, vehicle_id: int, user_id: str, start_time: str, end_time: str):
    print(f"[process_trip] session={session_id} vehicle={vehicle_id} user={user_id} {start_time} → {end_time}")

    try:
        _process_trip_inner(session_id, vehicle_id, user_id, start_time, end_time)
    except Exception as err:
        # This is a BackgroundTask — an uncaught exception here is otherwise
        # completely invisible to the Supabase trigger (which already got
        # its 200 OK) and easy to miss in Railway's log stream. Surface it
        # loudly so a failed session is at least noticeable, and don't let
        # aliv_processed get set for a run that didn't finish.
        print(f"[process_trip] FAILED for session={session_id}: {err!r}")
        raise


def _process_trip_inner(session_id: str, vehicle_id: int, user_id: str, start_time: str, end_time: str):
    supabase_source = _make_supabase_client(SOURCE_URL, SOURCE_KEY)
    supabase_target = _make_supabase_client(TARGET_URL, TARGET_KEY)

    flags = _get_session_flags(supabase_source, session_id)
    already_processed = bool(flags.get("aliv_processed"))
    current_imu_only = bool(flags.get("imu_only", True))  # fail-closed default, matches DB default
    if already_processed:
        print(f"[process_trip] session {session_id} already aliv_processed — will still re-check imu_only, will skip Aliv/hexagons/distance.")
    # ── 1. Fetch IMU data ──────────────────────────────────────────────────────
    imu_rows = fetch_all_pages(
        supabase_source,
        table="imu_data",
        filters=[("eq", "session_id", session_id)],
        order_col="timestamp_ms",
        tiebreak_col="imu_data_id",
    )
    print(f"[process_trip] IMU rows fetched: {len(imu_rows)}")
    if not imu_rows:
        print("[process_trip] No IMU data, skipping.")
        return

    # ── 2. Fetch GPS data ──────────────────────────────────────────────────────
    gps_rows = fetch_all_pages(
        supabase_source,
        table="gps_data",
        filters=[("eq", "session_id", session_id)],
        order_col="timestamp_ms",
        tiebreak_col="gps_id",
    )
    print(f"[process_trip] GPS rows fetched: {len(gps_rows)}")
    if not gps_rows:
        print("[process_trip] No GPS data, skipping.")
        return

    if len(gps_rows) < MIN_GPS_POINTS:
        print(f"[process_trip] Only {len(gps_rows)} GPS points (< {MIN_GPS_POINTS}), "
            f"marking aliv_processed and skipping map-matching/Aliv.")
        _mark_aliv_processed(supabase_source, session_id)
        return

    gps_df = pd.DataFrame(gps_rows)

    # ── 2a. Total distance, computed on RAW fixes before spending anything on
    # map-matching — a session that barely moved doesn't need a road-snapped
    # trace or an Aliv run either.
    total_distance_m = compute_total_distance(gps_df)
    print(f"[process_trip] Total distance: {total_distance_m:.2f} m")

    # ── 3. Merge prep + mount-orientation check ─────────────────────────────
    # imu_only doesn't depend on map-matching (it reads raw gps_df + imu_df
    # directly), so it still runs here, before we decide whether to bother
    # matching/Aliv-ing this trip at all — same "every run, regardless of
    # aliv_processed" behavior as before.
    imu_df = pd.DataFrame(imu_rows)
    imu_df["created_at"] = pd.to_datetime(imu_df["created_at"], utc=True, errors="coerce")
    fs = estimate_fs(imu_df, time_col="timestamp_ms")

    imu_only = _update_imu_only(supabase_source, session_id, gps_df, imu_df, current_imu_only)

    if already_processed:
        print("[process_trip] Finished (imu_only re-check only).")
        return

    if total_distance_m < MIN_TRIP_DISTANCE_M:
        print(f"[process_trip] Trip moved only {total_distance_m:.2f}m "
            f"(< {MIN_TRIP_DISTANCE_M}m), marking aliv_processed and skipping map-matching/Aliv.")
        try:
            _execute_with_retry(
                supabase_source.table("sessions")
                .update({"distance": total_distance_m / 1000})
                .eq("session_id", session_id)
            )
        except Exception as dist_err:
            print(f"[process_trip] distance update failed: {dist_err}")
        _mark_aliv_processed(supabase_source, session_id)
        return

    # ── 3a. Map-match GPS onto OSM and persist the matched trajectory ──────────
    gps_df = map_match_trip(gps_df)

    matched_records = gps_df[[
        "timestamp_ms", "matched_lat", "matched_lon", "osm_way_id",
        "direction_label", "match_raw_distance",
    ]].to_dict(orient="records")
    matched_records = [sanitize_for_json(r) for r in matched_records]
    for r in matched_records:
        r["session_id"] = session_id
    try:
        _execute_with_retry(
            supabase_source.table("matched_gps_data").insert(matched_records)
        )
    except Exception as match_err:
        print(f"[process_trip] matched_gps_data insert failed: {match_err}")

    df = merge_gps_into_imu(imu_df, gps_df)
    timesent_T0 = pd.to_datetime(df["timestamp_ms"].iloc[0], unit="ms", utc=True)

    # ── 3b. Update sessions.distance ────────────────────────────────────────
    try:
        _execute_with_retry(
            supabase_source.table("sessions")
            .update({"distance": total_distance_m / 1000})
            .eq("session_id", session_id)
        )
    except Exception as dist_err:
        print(f"[process_trip] distance update failed: {dist_err}")

    # ── 3c. Increment cumulative distance in user_details ──────────────────────
    try:
        resp = _execute_with_retry(
            supabase_target
            .table("user_details")
            .select("distance")
            .eq("firebaseuid", user_id)
        )
        if resp.data:
            current_distance = float(resp.data[0]["distance"] or 0.0)
            new_distance = current_distance + (total_distance_m/1000)
            _execute_with_retry(
                supabase_target.table("user_details")
                .update({"distance": new_distance})
                .eq("firebaseuid", user_id)
            )
        else:
            _execute_with_retry(
                supabase_target.table("user_details")
                .insert({"firebaseuid": user_id, "distance": total_distance_m/1000})
            )
    except Exception as user_dist_err:
        print(f"[process_trip] user_details distance update failed: {user_dist_err}")

    # ── 4. Run Aliv ──────────────
    aliv_input = build_aliv_input(df)
    result = run_aliv(aliv_input, fs=fs)

    if not result.get("speedbreakers"):
        print("[process_trip] No events detected.")
        _mark_aliv_processed(supabase_source, session_id)
        return
    aliv_trim_offset = 50 * (1000 / fs)

    # ── 5. Enrich events (matched coordinates + direction_label) ───────────────
    enriched_events = enrich_events(
        session_id, vehicle_id, user_id, result, df, timesent_T0, aliv_trim_offset
    )
    print(f"[process_trip] Enriched events: {len(enriched_events)}")
    if not enriched_events:
        _mark_aliv_processed(supabase_source, session_id)
        return

    enriched_events = [sanitize_for_json(e) for e in enriched_events]

    # ── 6. Insert road defects ─────────────────────────────────────────────────
    # user_id and vehicle_id are not columns on imu_events anymore —
    # they're derivable via session_id. Strip them from the DB insert.
    # direction_label and osm_way_id ARE real columns on imu_events (see
    # migration.sql) and pass through untouched.
    events_for_db = [
        {k: v for k, v in e.items() if k not in ("vehicle_id", "user_id")}
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
        event["vehicle_id"] = enriched_events[i]["vehicle_id"]

    # ── 7. Update hexagons ─────────────────────────────────────────────────────
    try:
        update_hexagons(supabase_target, inserted_events, imu_only)
    except Exception as hex_err:
        print(f"[hexagons] update failed: {hex_err}")

    _mark_aliv_processed(supabase_source, session_id)
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

@app.post("/Aliv_for_MVP1")
def Aliv_for_MVP1(payload: WebhookPayload):
    session = payload.record
    _trip_queue.put((
        session.session_id,
        session.vehicle_id,
        session.user_id,
        session.start_time,
        session.end_time,
    ))
    return {"status": "received"}


# ── Full-pipeline replay ─────────────────────────────────────────────────────
# Wipes hexagons/imu_events/ledger + user_details balances, then reprocesses
# every existing session strictly in order of end_time (oldest trip first —
# the trip that finished first gets discovery rights, matching the original
# chronological order the reward/confidence logic assumes). Calls
# _process_trip_inner() directly in-process rather than round-tripping
# through the webhook: since it's a normal (non-background) function call
# inside this loop, by the time it returns the session's aliv_processed flag
# is already True, so "wait for the flag" is just "the call returned" — no
# webhook, no created_at trick, no polling needed.

def _replay_all_sessions_inner():
    supabase_source = _make_supabase_client(SOURCE_URL, SOURCE_KEY)
    supabase_target = _make_supabase_client(TARGET_URL, TARGET_KEY)

    print("[replay] resetting hexagons/imu_events/ledger + user_details balances")
    try:
        _execute_with_retry(supabase_target.rpc("reset_pipeline", {}))
    except Exception as err:
        print(f"[replay] reset_pipeline failed, aborting replay: {err!r}")
        return

    sessions = fetch_all_pages(
        supabase_source, table="sessions", filters=[], order_col="end_time",
    )
    total_fetched = len(sessions)
    sessions = [s for s in sessions if s.get("end_time")]
    skipped = total_fetched - len(sessions)
    print(f"[replay] {len(sessions)} sessions to reprocess (skipped {skipped} with null end_time), oldest end_time first")

    for i, session in enumerate(sessions):
        session_id = session["session_id"]
        print(f"[replay] ({i + 1}/{len(sessions)}) session={session_id} end_time={session['end_time']}")

        try:
            _execute_with_retry(
                supabase_source.table("sessions")
                .update({"distance": 0, "aliv_processed": False, "imu_only": True})
                .eq("session_id", session_id)
            )
        except Exception as reset_err:
            print(f"[replay] failed to reset session {session_id}, skipping: {reset_err!r}")
            continue

        try:
            _process_trip_inner(
                session_id,
                session["vehicle_id"],
                session["user_id"],
                session["start_time"],
                session["end_time"],
            )
        except Exception as trip_err:
            # Log loudly and move on — one bad trip (e.g. missing IMU/GPS
            # data) shouldn't stall the other 45.
            print(f"[replay] session {session_id} FAILED: {trip_err!r} — continuing to next session")
            continue

    print("[replay] Finished replaying all sessions.")


@app.post("/replay_all_sessions")
def replay_all_sessions(background_tasks: BackgroundTasks):
    background_tasks.add_task(_replay_all_sessions_inner)
    return {"status": "replay started"}