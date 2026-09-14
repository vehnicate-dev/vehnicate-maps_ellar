"""
Map-matches a trip's raw GPS trace onto the OSM road network so that:
  - noisy/outlier fixes get pulled onto the real road (Viterbi-optimal HMM
    map matching), never left sitting on a building or a pond, and
  - opposite-direction travel over the same physical road gets a distinct
    `direction_label`, so hexagons_update.py's 15m proximity dedup can tell
    two nearby detections on opposite carriageways/lanes apart.

Requires: pip install leuvenmapmatching osmium --break-system-packages
An OSM extract (.osm.pbf) covering the operating area (Chennai) is parsed
once at process startup via init_map_matcher() — never per-request, since
walking the whole extract into an InMemMap is expensive.

`InMemMap` has no built-in OSM loader — it has to be built manually from
parsed way/node data (this is the documented pattern from the
leuvenmapmatching project itself, not something bespoke). `pyosmium`
(imported as `osmium`) is used to walk the .pbf file — it ships prebuilt
wheels for Windows/Linux/macOS, unlike `osmread`, which pins a 2016-era
protobuf that no longer builds on modern Python/setuptools.

`matcher.match()` returns one (from_node, to_node) directed-edge label pair
per matched observation — that pair IS the direction of travel along that
edge, so it's used directly as direction_label rather than collapsing it to
a forward/backward string.
"""
from __future__ import annotations
import math

import os
import osmium as osm
import pandas as pd
import requests
from leuvenmapmatching.map.inmem import InMemMap
from leuvenmapmatching.matcher.distance import DistanceMatcher

_MAP_CON: InMemMap | None = None

# Matcher tuning: obs_noise should reflect realistic crowdsourced GPS error
# (5-15m urban), not the ~7-decimal-place string precision of the raw fixes.
MAX_DIST_M = 50
OBS_NOISE_M = 10

BEARING_TRUST_SPEED_MPS = 2.5   # below this, GPS course-over-ground is too noisy to trust
BEARING_DISAGREEMENT_DEG = 60.0  # edge bearing vs. raw GPS bearing beyond this = suspect

_ONEWAY_VALUES = {"yes", "1", "true"}

_DRIVABLE_HIGHWAY_VALUES = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "service",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}

class _WayCollector(osm.SimpleHandler):
    def __init__(self):
        osm.SimpleHandler.__init__(self)
        self.way_node_ids: set = set()
        self.edges: list = []
        self.way_count = 0

    def way(self, w):
        if w.tags.get("highway") not in _DRIVABLE_HIGHWAY_VALUES:
            return
        oneway = w.tags.get("oneway", "").lower() in _ONEWAY_VALUES
        node_ids = [n.ref for n in w.nodes]
        for a, b in zip(node_ids, node_ids[1:]):
            self.edges.append((a, b, oneway))
        self.way_node_ids.update(node_ids)
        self.way_count += 1


class _NodeCollector(osm.SimpleHandler):
    """Pass 2: only add coordinates for node ids collected in pass 1."""

    def __init__(self, wanted_ids: set, map_con: InMemMap):
        osm.SimpleHandler.__init__(self)
        self.wanted_ids = wanted_ids
        self.map_con = map_con
        self.added_ids: set = set()

    def node(self, n):
        if n.id in self.wanted_ids and n.location.valid():
            self.map_con.add_node(n.id, (n.location.lat, n.location.lon))
            self.added_ids.add(n.id)


def _bearing_deg(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return math.degrees(math.atan2(y, x)) % 360

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters. Fine at this scale (10s-100s of m);
    no need for anything more precise than the equirectangular/haversine
    approximation given obs_noise is already ~10-40m."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def _circular_diff_deg(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)

def _project_point_to_segment(lat, lon, lat1, lon1, lat2, lon2):
    """Equirectangular-local projection — fine at road-segment scale (10s of m)."""
    lat0 = math.radians((lat1 + lat2) / 2)
    def to_xy(la, lo):
        return (lo * math.cos(lat0) * 111320, la * 111320)
    px, py = to_xy(lat, lon)
    x1, y1 = to_xy(lat1, lon1)
    x2, y2 = to_xy(lat2, lon2)
    dx, dy = x2 - x1, y2 - y1
    seg_len_sq = dx * dx + dy * dy
    t = 0.0 if seg_len_sq == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
    proj_lat = lat1 + t * (lat2 - lat1)
    proj_lon = lon1 + t * (lon2 - lon1)
    dist = math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
    return proj_lat, proj_lon, dist

def _despike_parallel_road_snaps(gps_df: pd.DataFrame, states: list) -> None:
    """Mutates matched_lat/lon/osm_way_id/direction_label/match_raw_distance
    in-place on gps_df for single-point mis-snaps onto a parallel road,
    detected via GPS-bearing disagreement against the matched edge."""
    way_ids = gps_df["osm_way_id"].tolist()
    n = len(gps_df)

    for i in range(1, n - 1):
        state = states[i] if i < len(states) else None
        if state is None or way_ids[i] is None:
            continue
        if way_ids[i - 1] != way_ids[i + 1] or way_ids[i - 1] == way_ids[i]:
            continue  # not an isolated single-point blip flanked by the same road

        speed = gps_df["speed"].iat[i] if "speed" in gps_df.columns else None
        raw_bearing = gps_df["bearing"].iat[i] if "bearing" in gps_df.columns else None
        if speed is None or raw_bearing is None or speed < BEARING_TRUST_SPEED_MPS:
            continue

        node1, node2 = state[0], state[1]
        try:
            lat1, lon1 = _MAP_CON.node_coordinates(node1)
            lat2, lon2 = _MAP_CON.node_coordinates(node2)
        except Exception:
            continue
        edge_bearing = _bearing_deg(lat1, lon1, lat2, lon2)

        if _circular_diff_deg(edge_bearing, raw_bearing) < BEARING_DISAGREEMENT_DEG:
            continue  # this point's own snap is directionally consistent — leave it

        # Suspect: re-snap onto the neighbors' shared way instead. Reuse the
        # prior point's edge geometry as the candidate segment — good enough
        # since the blip is a single point.
        prev_state = states[i - 1]
        if prev_state is None:
            continue
        pn1, pn2 = prev_state[0], prev_state[1]
        try:
            plat1, plon1 = _MAP_CON.node_coordinates(pn1)
            plat2, plon2 = _MAP_CON.node_coordinates(pn2)
        except Exception:
            continue

        raw_lat, raw_lon = gps_df["latitude"].iat[i], gps_df["longitude"].iat[i]
        proj_lat, proj_lon, dist_m = _project_point_to_segment(
            raw_lat, raw_lon, plat1, plon1, plat2, plon2
        )

        print(f"[map_matching] despiked idx={i}: way {way_ids[i]} -> {way_ids[i-1]} "
            f"(edge/gps bearing diff {_circular_diff_deg(edge_bearing, raw_bearing):.0f}deg)")

        gps_df.at[gps_df.index[i], "matched_lat"] = proj_lat
        gps_df.at[gps_df.index[i], "matched_lon"] = proj_lon
        gps_df.at[gps_df.index[i], "osm_way_id"] = way_ids[i - 1]
        gps_df.at[gps_df.index[i], "direction_label"] = gps_df["direction_label"].iat[i - 1]
        gps_df.at[gps_df.index[i], "match_raw_distance"] = dist_m

def _build_map_from_pbf(osm_pbf_path: str) -> InMemMap:
    map_con = InMemMap("chennai", use_latlon=True, use_rtree=True, index_edges=True)

    # Pass 1: which nodes matter (referenced by a highway way), and the
    # directed edges to build.
    way_collector = _WayCollector()
    way_collector.apply_file(osm_pbf_path)

    # Pass 2: add_node() must run for BOTH endpoints of an edge before
    # add_edge() is called on it — InMemMap.add_edge() raises ValueError
    # otherwise ("Add <id> first as node"). This is why nodes are added
    # here, before any add_edge call below, not the other way around.
    node_collector = _NodeCollector(way_collector.way_node_ids, map_con)
    node_collector.apply_file(osm_pbf_path)

    # Now safe to add edges — but a node can still be missing if it had no
    # valid location in the extract (rare, but skip rather than crash).
    skipped = 0
    for a, b, oneway in way_collector.edges:
        if a not in node_collector.added_ids or b not in node_collector.added_ids:
            skipped += 1
            continue
        map_con.add_edge(a, b)
        if not oneway:
            map_con.add_edge(b, a)

    map_con.purge()  # drop edges referencing nodes that were never added
    print(
        f"[map_matching] built graph from {way_collector.way_count} ways, "
        f"{len(node_collector.added_ids)} nodes ({skipped} edges skipped for missing nodes)"
    )
    return map_con


def _ensure_osm_extract(osm_pbf_path: str, osm_pbf_url: str | None) -> None:
    """Download the extract on first boot if it isn't already on disk.
    Railway's filesystem is ephemeral, so this runs once per fresh
    container/deploy, not once ever — a several-to-tens-of-MB city extract
    downloads in a few seconds, which is fine at startup time."""
    if os.path.exists(osm_pbf_path):
        return
    if not osm_pbf_url:
        raise RuntimeError(
            f"{osm_pbf_path} not found on disk and OSM_PBF_URL is not set "
            "— nothing to download it from."
        )
    print(f"[map_matching] {osm_pbf_path} not found, downloading from {osm_pbf_url}")
    with requests.get(osm_pbf_url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(osm_pbf_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
    print(f"[map_matching] downloaded {os.path.getsize(osm_pbf_path):,} bytes to {osm_pbf_path}")


def init_map_matcher(osm_pbf_path: str, osm_pbf_url: str | None = None) -> None:
    """Call once at FastAPI startup (see main.py's startup event)."""
    global _MAP_CON
    _ensure_osm_extract(osm_pbf_path, osm_pbf_url)
    _MAP_CON = _build_map_from_pbf(osm_pbf_path)
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
        for col in ("matched_lat", "matched_lon", "osm_way_id", "direction_label", "match_raw_distance"):
            gps_df[col] = None
        return gps_df

    trace = list(zip(gps_df["latitude"], gps_df["longitude"]))

    matcher = DistanceMatcher(
        _MAP_CON,
        max_dist=100,          # was 50 — the hard cutoff was very likely the actual bottleneck
        max_dist_init=40,      # give the anchor point more room than mid-trip fixes get
        obs_noise=20,          # was 10 — closer to Chennai's real multipath/urban-canyon error, still tighter than the library's own generic-GPX example (50)
        obs_noise_ne=40,       # explicit, > obs_noise per the library's own guidance
        non_emitting_states=True,
        max_lattice_width=10,   # bounds search cost — not set currently, and matters more once max_dist is widened
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
    match_raw_distance: list = [None] * len(gps_df)  # NEW

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
            # Raw fix vs. where it actually got snapped to — replaces the
            # unused match_confidence column. None (not 0.0) when a fix
            # wasn't matched at all, since matched_lat/lon just fall back
            # to the raw coordinate in that case and a 0.0 distance would
            # misleadingly read as "snapped exactly here."
            match_raw_distance[i] = _haversine_m(
                gps_df["latitude"].iat[i], gps_df["longitude"].iat[i], lat, lon
            )
        except Exception as err:
            print(f"[map_matching] node lookup failed for node={node2}: {err!r}")

    gps_df["matched_lat"] = matched_lat
    gps_df["matched_lon"] = matched_lon
    gps_df["osm_way_id"] = way_ids
    gps_df["direction_label"] = directions
    gps_df["match_raw_distance"] = match_raw_distance  # NEW

    if "bearing" in gps_df.columns and "speed" in gps_df.columns:
        _despike_parallel_road_snaps(gps_df, states)
    else:
        print("[map_matching] skipping bearing despike — bearing/speed not in gps_df")
    
    n_ok = sum(1 for d in directions if d is not None)
    dists = [d for d in match_raw_distance if d is not None]
    avg_dist = sum(dists) / len(dists) if dists else float("nan")
    print(f"[map_matching] matched {n_ok}/{len(gps_df)} fixes, avg match_raw_distance={avg_dist:.1f}m")

    return gps_df