import math as m
from typing import List, Dict, Any
import pandas as pd
import numpy as np
from scipy.signal import butter, filtfilt
from aliv_parameter import (
    GRAVITY_M_S2,
    calculate_raw_score,
    transform_accel_z_to_vehicle_frame,
)

# Events near the start/end of a trip AND slow are discarded (phone being
# mounted / unmounted).
EDGE_RADIUS_M = 30.0
EDGE_MAX_SPEED_MPS = 2.5


def _haversine_m_np(lat0, lon0, lats, lons):
    R = 6_371_000.0
    p0 = np.radians(lat0)
    p1 = np.radians(lats)
    dphi = p1 - p0
    dl = np.radians(lons - lon0)
    a = np.sin(dphi / 2) ** 2 + np.cos(p0) * np.cos(p1) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))

def speed_unavailable(lat, lon, speed) -> bool:
    """
    True if the trip has no usable speed data: every valid fix has a speed of
    0, NaN, None or negative (some devices report -1 for "unknown").
    """
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    spd = np.asarray(speed, dtype=float)
    valid = np.isfinite(lat) & np.isfinite(lon) & (lat != 0) & (lon != 0)
    if not valid.any():
        return True
    s = spd[valid]
    return not np.any(np.isfinite(s) & (s > 0))


def edge_slow_mask(lat, lon, speed) -> np.ndarray:
    """
    True for every fix that is within EDGE_RADIUS_M of the trip's first or last
    valid fix AND slower than EDGE_MAX_SPEED_MPS. Rows must be in time order.

    If the trip has no usable speed data (all speeds 0/missing), the speed
    condition is dropped and only the distance rule applies.

    Shared by Aliv (event filter) and main.py (pass counting) so both use the
    exact same rule.
    """
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    spd = np.nan_to_num(np.asarray(speed, dtype=float), nan=0.0)

    valid = np.isfinite(lat) & np.isfinite(lon) & (lat != 0) & (lon != 0)
    if not valid.any():
        return np.zeros(len(lat), dtype=bool)

    idx = np.flatnonzero(valid)
    near = np.zeros(len(lat), dtype=bool)
    for ref in (idx[0], idx[-1]):
        d = _haversine_m_np(lat[ref], lon[ref], lat, lon)
        near |= valid & (d < EDGE_RADIUS_M)

    if speed_unavailable(lat, lon, speed):
        return near                      # distance-only fallback

    return near & (spd < EDGE_MAX_SPEED_MPS)

class AlivRoadDefects:
    def __init__(self, fs=80, verbose=False):
        self.fs = fs
        self.verbose = verbose

    # ==========================================================
    # SAME NORMALIZATION LAYER AS YOUR OLD PIPELINE
    # ==========================================================

    def _normalize_row_keys(self, row):
        def get_val(keys, default=0.0):
            for k in keys:
                if k in row and row[k] is not None:
                    return float(row[k])
            return default

        ax = get_val(['acc_x', 'accelx', 'acceleration_x'])
        ay = get_val(['acc_y', 'accely', 'acceleration_y'])
        az = get_val(['acc_z', 'accelz', 'acceleration_z'])

        gx = get_val(['gyro_x', 'gyrox', 'rotation_x'])
        gy = get_val(['gyro_y', 'gyroy', 'rotation_y'])
        gz = get_val(['gyro_z', 'gyroz', 'rotation_z'])

        ts = row.get('timesent') or row.get('timestamp')

        return {
            'timesent': ts,
            'accelx': ax, 'accely': ay, 'accelz': az,
            'gyrox': gx, 'gyroy': gy, 'gyroz': gz,
            'useraccelx': get_val(['useraccelx'], ax),
            'useraccely': get_val(['useraccely'], ay),
            'useraccelz': get_val(['useraccelz'], az - 9.8),
            'latitude': get_val(['latitude', 'lat']),
            'longitude': get_val(['longitude', 'lon']),
            'speed': get_val(['speed'])
        }

    def _rows_to_df(self, rows):
        rows = [self._normalize_row_keys(r) for r in rows]
        df = pd.DataFrame(rows)

        ts = pd.to_datetime(df['timesent'], errors='coerce', utc=True)
        df['time_ms'] = (ts - ts.iloc[0]).dt.total_seconds() * 1000
        df['time_ms'] = df['time_ms'].astype(int)
        return df

    # ==========================================================
    # OG FUNCTIONS (UNCHANGED)
    # ==========================================================

    def phone_to_vehicle(self, df):
        g = GRAVITY_M_S2
        ax, ay, az = df['accelx'], df['accely'], df['accelz']
        Ax, Ay, Az = df['useraccelx'], df['useraccely'], -df['useraccelz']
        Gx, Gy, Gz = df['gyrox'], df['gyroy'], df['gyroz']

        ax0 = ax[:10].mean()
        ay0 = ay[:10].mean()
        az0 = az[:10].mean()

        """
        for the phone, (if kept horizontal with the screen directly facing you):
        x - downwards
        y - right
        z - towards you
        """
        try: theta = m.acos(-az0 / g) #basically like the phone's pitch... yaw and roll dont affect az0
        except: theta = 0.0
        try: phi = m.acos(-ay0 / g) #the phone's yaw... roll and pitch dont affect ay0
        except: phi = 0.0

        AX = -Ax * m.cos(theta) - Az * m.sin(theta)
        AY = -(Ax * m.sin(theta) * m.cos(phi) +
               Az * m.cos(theta) * m.cos(phi) -
               Ay * m.sin(phi))
        AZ = -(Ax * m.sin(theta) * m.sin(phi)
       - Az * m.cos(theta) * m.sin(phi)
       + Ay * m.cos(phi))

        GX = -Gx * m.cos(theta) + Gz * m.sin(theta)
        GY = -(Gx * m.sin(theta) * m.cos(phi) +
               Gz * m.cos(theta) * m.cos(phi) -
               Gy * m.sin(phi))
        GZ = -(-Gx * m.sin(theta) * m.sin(phi) -
               Gz * m.cos(theta) * m.sin(phi) +
               Gy * m.cos(phi))

        # if the phone is placed horizontally with the camera above instead of below,
        # negate AX, AY, GX, GY. otherwise, comment out the below line!!
        #AX, AY, GX, GY = -AX, -AY, -GX, -GY

        df['acc_x'], df['acc_y'], df['acc_z'] = AX, AY, AZ
        df['gyro_x'], df['gyro_y'], df['gyro_z'] = GX, GY, GZ

        return df

    def butter_bandpass(self, x, low, high, order=1):
        nyq = 0.5 * self.fs
        b, a = butter(order, [low / nyq, high / nyq], btype='band')
        if len(x) <= 3 * max(len(a), len(b)):
            return x
        return filtfilt(b, a, x)

    def Chunking(self, df, angle, ang_vel):
        threshold = 0.0001
        l = len(df) - 1
        pointer = 0
        def_ChunkSize = 10
        Chunks = {}

        while pointer < l:
            initial = pointer
            hi = min(pointer + def_ChunkSize - 1, l)
            vmax = max(df[ang_vel].iloc[pointer:hi + 1])

            if abs(vmax) <= threshold:
                y1 = df[angle].iloc[pointer]
                pointer = min(pointer + def_ChunkSize, l)
                y2 = df[angle].iloc[pointer]
                i_d = y2 - y1
                f_d = i_d

                q = abs(df[ang_vel].iloc[min(pointer + 5, l)])
                while q <= threshold and f_d * i_d > 0 and pointer + 5 < l:
                    y1 = df[angle].iloc[pointer]
                    y2 = df[angle].iloc[min(pointer + 5, l)]
                    f_d = y2 - y1
                    pointer += 5
                    q = abs(df[ang_vel].iloc[pointer])
            else:
                y1 = df[angle].iloc[pointer]
                pointer = min(pointer + def_ChunkSize, l)
                y2 = df[angle].iloc[pointer]
                i_d = y2 - y1
                f_d = i_d

                q = abs(df[ang_vel].iloc[min(pointer + 1, l)])
                while q >= threshold and f_d * i_d > 0 and pointer + 5 < l:
                    y1 = df[angle].iloc[pointer]
                    y2 = df[angle].iloc[min(pointer + 5, l)]
                    f_d = y2 - y1
                    pointer += 5
                    q = abs(df[ang_vel].iloc[pointer])

            Chunks[initial] = max(pointer - 1, initial)
            if pointer == initial:
                pointer += def_ChunkSize

        return Chunks

    # ==========================================================
    # MAIN ENTRY (MATCHES YOUR OLD PIPELINE)
    # ==========================================================

    def analyze_batch(self, rows):
        print("Rows received:", len(rows))
        if not rows:
            print('no rows received!!!')
            return {'speedbreakers': []}

        df = self._rows_to_df(rows)
        df = self.phone_to_vehicle(df)

        valid_gps = df[(df.latitude != 0) & (df.longitude != 0) & df.latitude.notna() & df.longitude.notna()]
        if valid_gps.empty:
            print("No valid GPS coordinates found, skipping analysis")
            return {"speedbreakers": []}

        # Fixes within EDGE_RADIUS_M of the first/last fix AND slower than
        # EDGE_MAX_SPEED_MPS. Computed on the raw rows (before resampling) and
        # carried through the resample as a 0/1 column.
        df['edge_slow'] = edge_slow_mask(
            df['latitude'].values, df['longitude'].values, df['speed'].values
        ).astype(float)

        # ---- OG logic unchanged below ----
        Pitch = [0]
        pitch = 0.0
        for i in range(1, len(df)):
            dt = (df['time_ms'][i] - df['time_ms'][i - 1]) / 1000
            pitch += df['gyro_y'][i] * dt
            Pitch.append(pitch)
        df['Pitch'] = Pitch

        df['timestamp'] = pd.to_timedelta(df['time_ms'], unit='ms')

        num_cols = df.select_dtypes(include=[np.number]).columns.difference(['time_ms'])

        df_resampled = (
            df.set_index('timestamp', drop=False)[num_cols]
            .resample(f"{int(1000 / self.fs)}ms")
            .mean()
            .interpolate()
            .reset_index(drop=True)
        )

        df_resampled['time_ms'] = (df_resampled.index * (1000.0 / self.fs)).astype(int)
        df = df_resampled

        filt_pitch = self.butter_bandpass(df['Pitch'].values, 0.46, 1.5)
        if len(filt_pitch) < 100:
            return {'speedbreakers': []}

        filt_pitch = filt_pitch[50:-50]
        gyro_y = df['gyro_y'].values[50:-50]
        vehicle_accel_z = df['acc_z'].values[50:-50]
        time_f = df['time_ms'].values[50:-50]
        edge_slow_f = df['edge_slow'].values[50:-50] > 0   # same indexing as filt_pitch

        df_f = pd.DataFrame({
            'Pitch': filt_pitch,
            'gyro_y': gyro_y,
            'acc_z': vehicle_accel_z,
            'time_ms': time_f,
        })

        chunks = self.Chunking(df_f, 'Pitch', 'gyro_y')
        s = np.std(filt_pitch) * 1.0
        events, buf, active = [], [], False
        discarded_edge = 0

        raw_time = df['time_ms'].values
        raw_pitch = df['Pitch'].values

        for i in (chunks):
            if abs(filt_pitch[i]) >= s:
                buf.append(i)
                active = True

            if active and abs(filt_pitch[i]) < s:
                if len(buf) >= 2:
                    si, ei = buf[0], buf[-1]
                    ts, te = time_f[si], time_f[ei]

                    rs = np.searchsorted(raw_time, ts, side='right') - 1
                    re = np.searchsorted(raw_time, te, side='right') - 1
                    rs, re = max(0, rs), max(rs, re)

                    dp = np.max(filt_pitch[si:ei+1]) - np.min(filt_pitch[si:ei+1])
                    stdp = np.std(filt_pitch[si:ei+1])
                    gymax = np.max(np.abs(gyro_y[si:ei+1]))
                    dpOG = np.max(raw_pitch[rs:re+1]) - np.min(raw_pitch[rs:re+1])
                    az_rms = np.sqrt(np.mean(np.square(vehicle_accel_z[si:ei+1])))

                    p = calculate_raw_score(dpOG, dp, gymax, stdp, az_rms)

                    if p != 0:
                        # near the start/end of the trip AND slow -> phone being mounted/unmounted
                        if edge_slow_f[si:ei+1].any():
                            discarded_edge += 1
                        else:
                            events.append({
                                'start_time': ts,
                                'end_time': te,
                                'dp_og': float(dpOG),
                                'dp': float(dp),
                                'gymax': float(gymax),
                                'stdp': float(stdp),
                                'az_rms': float(az_rms),
                            })

                buf, active = [], False
        print("number of events: ", len(events), "| discarded near start/end & slow:", discarded_edge)
        return {'speedbreakers': events}