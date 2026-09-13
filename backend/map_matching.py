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