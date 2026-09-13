"""
Map-matches a trip's raw GPS trace onto the OSM road network so that:
  - noisy/outlier fixes get pulled onto the real road (Viterbi-optimal HMM
    map matching), never left sitting on a building or a pond, and
  - opposite-direction travel over the same physical road gets a distinct
    `direction_label`, so hexagons_update.py's 15m proximity dedup can tell
    two nearby detections on opposite carriageways/lanes apart.

Requires: pip install leuvenmapmatching --break-system-packages
An OSM extract (.osm.pbf) covering the operating area (Chennai) is loaded
once at process startup via init_map_matcher() — never per-request, since
parsing the extract into an InMemMap is expensive.

NOTE: the exact attribute/return shape of `matcher.match()` states and
`InMemMap` node lookups vary slightly across leuvenmapmatching releases —
verify `node1`/`node2`/`node_coordinates` below against the version pinned
in requirements.txt before deploying.
"""
from __future__ import annotations

import pandas as pd
from leuvenmapmatching.map.inmem import InMemMap
from leuvenmapmatching.matcher.distance import DistanceMatcher

_MAP_CON: InMemMap | None = None

# Matcher tuning: obs_noise should reflect realistic crowdsourced GPS error
# (5-15m urban), not the ~7-decimal-place string precision of the raw fixes.
MAX_DIST_M = 50
OBS_NOISE_M = 10


def init_map_matcher(osm_pbf_path: str) -> None:
    """Call once at FastAPI startup (see main.py's startup event)."""
    global _MAP_CON
    _MAP_CON = InMemMap.from_pbf(osm_pbf_path, use_latlon=True)
    print(f"[map_matching] loaded OSM extract from {osm_pbf_path}")


def map_match_trip(gps_df: pd.DataFrame) -> pd.DataFrame:
    """
    gps_df: raw rows with columns timestamp_ms, latitude, longitude.

    Returns gps_df (sorted by timestamp_ms) with four columns appended:
    matched_lat, matched_lon, osm_way_id, direction_label. Fixes that fail
    to map-match keep their raw coordinate as matched_lat/lon and get
    osm_way_id=None, direction_label=None — nothing is dropped, downstream
    code treats a null direction_label as "no info, fall back to
    distance-only".
    """
    if _MAP_CON is None:
        raise RuntimeError("init_map_matcher() must run before map_match_trip()")

    gps_df = gps_df.sort_values("timestamp_ms").reset_index(drop=True)

    if gps_df.empty:
        for col in ("matched_lat", "matched_lon", "osm_way_id", "direction_label"):
            gps_df[col] = None
        return gps_df

    trace = list(zip(gps_df["latitude"], gps_df["longitude"]))

    matcher = DistanceMatcher(
        _MAP_CON,
        max_dist=MAX_DIST_M,
        obs_noise=OBS_NOISE_M,
        non_emitting_states=True,
    )
    try:
        states, _ = matcher.match(trace)
    except Exception as err:
        print(f"[map_matching] match() failed, falling back to raw coords: {err!r}")
        states = [None] * len(trace)

    matched_lat = gps_df["latitude"].tolist()
    matched_lon = gps_df["longitude"].tolist()
    way_ids: list = [None] * len(gps_df)
    directions: list = [None] * len(gps_df)

    n_matched = min(len(states), len(gps_df))
    for i in range(n_matched):
        state = states[i]
        if state is None:
            continue
        node1, node2 = state[0], state[1]
        way_ids[i] = f"{min(node1, node2)}-{max(node1, node2)}"
        directions[i] = "forward" if node1 < node2 else "backward"
        try:
            lat, lon = _MAP_CON.node_coordinates(node2)
            matched_lat[i], matched_lon[i] = lat, lon
        except Exception as err:
            print(f"[map_matching] node lookup failed for node={node2}: {err!r}")

    gps_df["matched_lat"] = matched_lat
    gps_df["matched_lon"] = matched_lon
    gps_df["osm_way_id"] = way_ids
    gps_df["direction_label"] = directions

    n_ok = sum(1 for d in directions if d is not None)
    print(f"[map_matching] matched {n_ok}/{len(gps_df)} fixes")

    return gps_df