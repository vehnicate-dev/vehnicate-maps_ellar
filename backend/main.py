from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import pandas as pd
from supabase import create_client
from aliv_module import AlivRoadDefects
import h3 as h3lib
import os
from dotenv import load_dotenv
from hexagons_update import update_hexagons
from zoneinfo import ZoneInfo
import math
from distance import compute_total_distance

IST = ZoneInfo("Asia/Kolkata")
"""
Each time a new row is inserted into the "sessions" table, a HTTPS request is triggered
via ngrok carrying session_id, vehicle_id, start_time & end_time.
|
↓
process_trip() fetches IMU rows from imu_data and GPS rows from gps_data (both keyed by
session_id), merges them on nearest timestamp_ms, then feeds the combined rows into Aliv
for road defect detection.

Column mapping summary
──────────────────────
imu_data  : accel_x/y/z  → renamed to accelx/y/z    (Aliv key)
            gyro_x/y/z   → renamed to gyrox/y/z      (Aliv key)
            user_accel_x → renamed to useraccelx      (Aliv key, no underscore!)
            created_at   → mapped to 'timestamp'      (Aliv time key)
gps_data  : latitude, longitude, speed               (Aliv uses these directly)

Aliv time output
────────────────
Aliv rebuilds time_ms internally from 'timestamp' (pd.to_datetime), resamples at 1000/fs ms
intervals, then trims 50 samples off both ends. Its output start_time / end_time are offsets
(in ms) from that internal axis.
To convert back to absolute wall-clock time:
    absolute = timesent_T0 + pd.to_timedelta(aliv_ms + TRIM_OFFSET_MS, unit='ms')
where TRIM_OFFSET_MS = 50 * (1000 / fs) = 625 ms at fs=80.
"""

load_dotenv()

SOURCE_URL = os.environ.get("SOURCE_URL")
SOURCE_KEY = os.environ.get("SOURCE_KEY")
TARGET_URL = os.environ.get("TARGET_URL")
TARGET_KEY = os.environ.get("TARGET_KEY")

# Must match AlivRoadDefects(fs=…) below
#ALIV_FS          = 40 # previously 80
#ALIV_TRIM        = 50                              # samples trimmed from each end
#ALIV_TRIM_OFFSET = ALIV_TRIM * (1000 / ALIV_FS)   # 625 ms at fs=80

app = FastAPI()


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
) -> list:
    """Paginated fetch from a Supabase table.

    filters is a list of (method_name, *args) tuples applied to the query,
    e.g. [("eq", "session_id", sid)].
    """
    all_data = []
    start = 0
    while True:
        query = supabase_client.table(table).select("*")
        for method, *args in filters:
            query = getattr(query, method)(*args)
        batch = (
            query
            .order(order_col, desc=False)
            .range(start, start + page_size - 1)
            .execute()
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
    return obj

def merge_gps_into_imu(imu_df: pd.DataFrame, gps_df: pd.DataFrame) -> pd.DataFrame:
    """Attach the nearest GPS fix to every IMU row via an asof join on timestamp_ms."""
    imu_df = imu_df.sort_values("timestamp_ms").reset_index(drop=True)
    gps_df = gps_df.sort_values("timestamp_ms").reset_index(drop=True)
    return pd.merge_asof(
        imu_df,
        gps_df[["timestamp_ms", "latitude", "longitude", "speed", "bearing"]],
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
    Map Aliv's relative-time events back to absolute UTC timestamps and GPS coordinates
    using the merged IMU+GPS DataFrame.

    Matching strategy: convert Aliv's start/end ms to absolute timestamps, then find
    the nearest rows in the raw df by created_at (UTC).
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
            subset[["latitude", "longitude"]]
            .dropna()
            .drop_duplicates()
            .values
            .tolist()
        )
        if not lat_lon:
            continue

        first_lat, first_lon = lat_lon[0][0], lat_lon[0][1]
        h3_index = h3lib.latlng_to_cell(first_lat, first_lon, 8)

        enriched.append({
            "user_id":    user_id,
            "vehicle_id": vehicle_id,
            "session_id": session_id,
            "h3_index":   h3_index,
            "start_time": pd.to_datetime(start_time, utc=True).astimezone(IST).isoformat(),
            "end_time":   pd.to_datetime(end_time, utc=True).astimezone(IST).isoformat(),
            "parameter":  event["parameter"],
            "path":       lat_lon
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


# ── Core processing ────────────────────────────────────────────────────────────

def process_trip(session_id: str, vehicle_id: int, user_id: str, start_time: str, end_time: str):
    print(f"[process_trip] session={session_id} vehicle={vehicle_id} user={user_id} {start_time} → {end_time}")

    supabase_source = create_client(SOURCE_URL, SOURCE_KEY)
    supabase_target = create_client(TARGET_URL, TARGET_KEY)

    # ── 1. Fetch IMU data ──────────────────────────────────────────────────────
    imu_rows = fetch_all_pages(
        supabase_source,
        table="imu_data",
        filters=[("eq", "session_id", session_id)],
        order_col="timestamp_ms",
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
    )
    print(f"[process_trip] GPS rows fetched: {len(gps_rows)}")
    if not gps_rows:
        print("[process_trip] No GPS data, skipping.")
        return

    # ── 3. Merge IMU + GPS ─────────────────────────────────────────────────────
    imu_df = pd.DataFrame(imu_rows)
    gps_df = pd.DataFrame(gps_rows)

    # Parse created_at to UTC datetime – used both for Aliv's 'timestamp' and for
    # mapping Aliv's output back to absolute time in enrich_events().
    imu_df["created_at"] = pd.to_datetime(imu_df["created_at"], utc=True, errors="coerce")
    fs = estimate_fs(imu_df, time_col="timestamp_ms")

    df = merge_gps_into_imu(imu_df, gps_df)

    # T0: the absolute UTC time of the first IMU row – anchor for Aliv's time axis.
    timesent_T0 = pd.to_datetime(df["timestamp_ms"].iloc[0], unit="ms", utc=True)

    # ── 3b. Compute total distance and update sessions table ───────────────────
    total_distance_m = compute_total_distance(gps_df)
    print(f"[process_trip] Total distance: {total_distance_m:.2f} m")

    try:
        supabase_source.table("sessions") \
            .update({"distance": total_distance_m/1000}) \
            .eq("session_id", session_id) \
            .execute()
    except Exception as dist_err:
        print(f"[process_trip] distance update failed: {dist_err}")
    
    # ── 3c. Increment cumulative distance in user_details ──────────────────────
    try:
        resp = (
            supabase_target
            .table("user_details")
            .select("distance")
            .eq("firebaseuid", user_id)
            .execute()
        )
        if resp.data:
            current_distance = float(resp.data[0]["distance"] or 0.0)
            new_distance = current_distance + (total_distance_m/1000)
            supabase_target.table("user_details") \
                .update({"distance": new_distance}) \
                .eq("firebaseuid", user_id) \
                .execute()
        else:
            supabase_target.table("user_details") \
                .insert({"firebaseuid": user_id, "distance": total_distance_m/1000}) \
                .execute()
    except Exception as user_dist_err:
        print(f"[process_trip] user_details distance update failed: {user_dist_err}")
        
    # ── 4. Run Aliv ──────────────
    aliv_input = build_aliv_input(df)
    result = run_aliv(aliv_input, fs=fs)

    if not result.get("speedbreakers"):
        print("[process_trip] No events detected.")
        return
    aliv_trim_offset = 50 * (1000 / fs)

    # ── 5. Enrich events ───────────────────────────────────────────────────────
    enriched_events = enrich_events(
        session_id, vehicle_id, user_id, result, df, timesent_T0, aliv_trim_offset
    )
    print(f"[process_trip] Enriched events: {len(enriched_events)}")
    if not enriched_events:
        return

    enriched_events = [sanitize_for_json(e) for e in enriched_events]

    # ── 6. Insert road defects ─────────────────────────────────────────────────
    # user_id and vehicle_id are not columns on imu_events anymore —
    # they're derivable via session_id. Strip them from the DB insert.
    events_for_db = [
        {k: v for k, v in e.items() if k not in ("vehicle_id", "user_id")}
        for e in enriched_events
    ]
    insert_response = supabase_target.table("imu_events").insert(events_for_db).execute()
    inserted_events = insert_response.data

    # Re-attach id (renamed), user_id and vehicle_id for the hexagons step.
    for i, event in enumerate(inserted_events):
        event["id"]         = event.pop("imu_events_id")
        event["user_id"]    = enriched_events[i]["user_id"]
        event["vehicle_id"] = enriched_events[i]["vehicle_id"]

    # ── 7. Update hexagons ─────────────────────────────────────────────────────
    try:
        update_hexagons(supabase_target, inserted_events)
    except Exception as hex_err:
        print(f"[hexagons] update failed: {hex_err}")

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
def Aliv_for_MVP1(payload: WebhookPayload, background_tasks: BackgroundTasks):
    session = payload.record
    background_tasks.add_task(
        process_trip,
        session.session_id,
        session.vehicle_id,
        session.user_id,
        session.start_time,
        session.end_time,
    )
    return {"status": "received"}