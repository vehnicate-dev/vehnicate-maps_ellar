"""
Vehnicate GPS -> OSM road map matcher.

Purpose
-------
Map-match a trip's raw GPS trace onto the OSM road network.

Important:
    LeuvenMapMatching's DistanceMatcher can insert non-emitting states.
    Therefore matcher.match(trace) MUST NOT be interpreted as:

        states[i] == GPS observation i

    Instead, the best matching lattice is inspected and only emitting
    BaseMatching objects are used. Each emitting object contains:

        matching.obs       -> index of the original GPS observation
        matching.edge_m    -> matched directed road segment
        matching.edge_m.l1 -> from-node
        matching.edge_m.l2 -> to-node

This file is written for LeuvenMapMatching 1.1.4.

Output columns added to the GPS dataframe
-----------------------------------------
    matched_lat
    matched_lon
    osm_way_id
    direction_label
    match_raw_distance

Accepted match:
    matched_lat/lon      = projection of raw GPS onto matched road segment
    osm_way_id           = OSM way ID
    direction_label      = "forward" / "backward"
    match_raw_distance   = raw GPS -> road distance in metres

Rejected/unmatched match:
    matched_lat/lon      = ORIGINAL raw GPS coordinate
    osm_way_id           = None
    direction_label      = None
    match_raw_distance   = None

The raw GPS row is never dropped.

Requirements
------------
    pip install leuvenmapmatching osmium requests pandas
"""

from __future__ import annotations

import math
import os
from typing import Optional

import osmium as osm
import pandas as pd
import requests

from leuvenmapmatching.map.inmem import InMemMap
from leuvenmapmatching.matcher.distance import DistanceMatcher


# ---------------------------------------------------------------------------
# GLOBAL MAP
# ---------------------------------------------------------------------------

_MAP_CON: Optional[InMemMap] = None


# ---------------------------------------------------------------------------
# MATCHER SETTINGS
# ---------------------------------------------------------------------------

# Maximum acceptable raw-GPS -> road distance.
#
# This is intentionally 50 m for Vehnicate.
# Anything farther away is not trusted as a road match.
MAX_DIST_M = 50.0

# Expected GPS observation noise.
OBS_NOISE_M = 10.0

# Noise used for non-emitting states.
OBS_NOISE_NE_M = 20.0

# Distance-transition noise.
DIST_NOISE_M = 20.0

# Maximum candidate states retained per observation.
MAX_LATTICE_WIDTH = 10


# ---------------------------------------------------------------------------
# BEARING / DESPIKE SETTINGS
# ---------------------------------------------------------------------------

# Below this speed, phone/GPS bearing is too unstable to use.
BEARING_TRUST_SPEED_MPS = 2.5

# If the matched road bearing differs from the GPS bearing by more than
# this amount, a point may be a parallel-road mis-snap.
BEARING_DISAGREEMENT_DEG = 60.0


# ---------------------------------------------------------------------------
# OSM ROAD FILTER
# ---------------------------------------------------------------------------

_ONEWAY_VALUES = {
    "yes",
    "1",
    "true",
}

_DRIVABLE_HIGHWAY_VALUES = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "service",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
}


# ---------------------------------------------------------------------------
# DIRECTED EDGE -> OSM WAY INFORMATION
# ---------------------------------------------------------------------------
#
# Key:
#     (from_node, to_node)
#
# Value:
#     (osm_way_id, direction_label)
#
# direction_label is defined relative to the ORIGINAL node order of the
# OSM way:
#
#     original way direction -> "forward"
#     reverse direction      -> "backward"
#
# This is deliberately NOT based on comparing node IDs numerically.
# OSM node IDs have no relationship to physical travel direction.
# ---------------------------------------------------------------------------

_EDGE_TO_WAY: dict[tuple[int, int], tuple[int, str]] = {}


# ---------------------------------------------------------------------------
# OSM PASS 1
# ---------------------------------------------------------------------------

class _WayCollector(osm.SimpleHandler):
    """
    First pass through the PBF.

    Collect:
        - all nodes needed by drivable ways
        - all directed road segments
        - OSM way IDs
        - direction semantics
    """

    def __init__(self):
        super().__init__()

        self.way_node_ids: set[int] = set()

        # Each entry:
        #
        #   (from_node, to_node, osm_way_id, direction_label)
        #
        self.edges: list[tuple[int, int, int, str]] = []

        self.way_count = 0

    def way(self, w):
        highway = w.tags.get("highway")

        if highway not in _DRIVABLE_HIGHWAY_VALUES:
            return

        oneway_raw = str(w.tags.get("oneway", "")).strip().lower()

        node_ids = [n.ref for n in w.nodes]

        if len(node_ids) < 2:
            return

        for a, b in zip(node_ids, node_ids[1:]):

            # ---------------------------------------------------------------
            # Normal two-way road
            # ---------------------------------------------------------------
            if oneway_raw not in _ONEWAY_VALUES and oneway_raw != "-1":

                # Original OSM way direction.
                self.edges.append(
                    (a, b, w.id, "forward")
                )

                # Reverse travel direction.
                self.edges.append(
                    (b, a, w.id, "backward")
                )

            # ---------------------------------------------------------------
            # Normal one-way road
            # ---------------------------------------------------------------
            elif oneway_raw in _ONEWAY_VALUES:

                # Only the original way direction is legal.
                self.edges.append(
                    (a, b, w.id, "forward")
                )

            # ---------------------------------------------------------------
            # Reversed one-way road
            # ---------------------------------------------------------------
            elif oneway_raw == "-1":

                # OSM way itself runs a -> b, but traffic is allowed b -> a.
                # We therefore label this travel direction "backward" relative
                # to the original OSM way order.
                self.edges.append(
                    (b, a, w.id, "backward")
                )

        self.way_node_ids.update(node_ids)
        self.way_count += 1


# ---------------------------------------------------------------------------
# OSM PASS 2
# ---------------------------------------------------------------------------

class _NodeCollector(osm.SimpleHandler):
    """
    Second PBF pass.

    Only load coordinates for nodes that belong to drivable ways.
    """

    def __init__(self, wanted_ids: set[int], map_con: InMemMap):
        super().__init__()

        self.wanted_ids = wanted_ids
        self.map_con = map_con
        self.added_ids: set[int] = set()

    def node(self, n):
        if n.id not in self.wanted_ids:
            return

        if not n.location.valid():
            return

        self.map_con.add_node(
            n.id,
            (n.location.lat, n.location.lon),
        )

        self.added_ids.add(n.id)


# ---------------------------------------------------------------------------
# BUILD MAP
# ---------------------------------------------------------------------------

def _build_map_from_pbf(osm_pbf_path: str) -> InMemMap:
    """
    Build the LeuvenMapMatching InMemMap from an OSM PBF.

    Two passes are used:
        1. collect road edges and required node IDs
        2. load coordinates for those nodes
    """

    global _EDGE_TO_WAY

    map_con = InMemMap(
        "chennai",
        use_latlon=True,
        use_rtree=True,
        index_edges=True,
    )

    # -----------------------------------------------------------------------
    # PASS 1: roads
    # -----------------------------------------------------------------------

    way_collector = _WayCollector()
    way_collector.apply_file(osm_pbf_path)

    # -----------------------------------------------------------------------
    # PASS 2: nodes
    # -----------------------------------------------------------------------

    node_collector = _NodeCollector(
        way_collector.way_node_ids,
        map_con,
    )

    node_collector.apply_file(osm_pbf_path)

    # -----------------------------------------------------------------------
    # Add directed edges
    # -----------------------------------------------------------------------

    skipped = 0
    edge_to_way: dict[tuple[int, int], tuple[int, str]] = {}

    for from_node, to_node, way_id, direction in way_collector.edges:

        if (
            from_node not in node_collector.added_ids
            or to_node not in node_collector.added_ids
        ):
            skipped += 1
            continue

        try:
            map_con.add_edge(from_node, to_node)
        except Exception:
            continue

        # If several OSM ways happen to use the exact same directed node
        # pair, keep the first one. The geometry is identical at this level.
        edge_to_way.setdefault(
            (from_node, to_node),
            (way_id, direction),
        )

    map_con.purge()

    _EDGE_TO_WAY = edge_to_way

    print(
        f"[map_matching] built graph from "
        f"{way_collector.way_count} ways, "
        f"{len(node_collector.added_ids)} nodes, "
        f"{len(edge_to_way)} directed edges "
        f"({skipped} edges skipped for missing nodes)"
    )

    return map_con


# ---------------------------------------------------------------------------
# GEOMETRY HELPERS
# ---------------------------------------------------------------------------

def _bearing_deg(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Initial bearing from point 1 to point 2.
    """

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dlambda = math.radians(lon2 - lon1)

    y = math.sin(dlambda) * math.cos(phi2)

    x = (
        math.cos(phi1) * math.sin(phi2)
        - math.sin(phi1)
        * math.cos(phi2)
        * math.cos(dlambda)
    )

    return math.degrees(math.atan2(y, x)) % 360.0


def _haversine_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Great-circle distance in metres.
    """

    R = 6371000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(dlambda / 2.0) ** 2
    )

    return 2.0 * R * math.asin(
        math.sqrt(max(0.0, min(1.0, a)))
    )


def _circular_diff_deg(
    a: float,
    b: float,
) -> float:
    """
    Smallest absolute angular difference.
    """

    return abs((a - b + 180.0) % 360.0 - 180.0)


def _project_point_to_segment(
    lat: float,
    lon: float,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
):
    """
    Project a latitude/longitude point onto a short road segment.

    Uses a local equirectangular approximation, which is sufficiently
    accurate for road segments at this scale.
    """

    lat0 = math.radians((lat1 + lat2) / 2.0)

    meters_per_degree = 111320.0

    def to_xy(la, lo):
        return (
            lo * math.cos(lat0) * meters_per_degree,
            la * meters_per_degree,
        )

    px, py = to_xy(lat, lon)

    x1, y1 = to_xy(lat1, lon1)
    x2, y2 = to_xy(lat2, lon2)

    dx = x2 - x1
    dy = y2 - y1

    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq == 0.0:
        t = 0.0
    else:
        t = (
            (px - x1) * dx
            + (py - y1) * dy
        ) / seg_len_sq

        t = max(0.0, min(1.0, t))

    proj_lat = lat1 + t * (lat2 - lat1)
    proj_lon = lon1 + t * (lon2 - lon1)

    proj_x = x1 + t * dx
    proj_y = y1 + t * dy

    dist = math.hypot(
        px - proj_x,
        py - proj_y,
    )

    return proj_lat, proj_lon, dist


# ---------------------------------------------------------------------------
# MATCHING OBJECT HELPERS
# ---------------------------------------------------------------------------

def _is_emitting_matching(matching) -> bool:
    """
    LeuvenMapMatching 1.1.x BaseMatching uses obs_ne == 0 for an emitting
    state.

    The method is kept defensive so this remains compatible with builds
    exposing is_emitting().
    """

    try:
        return bool(matching.is_emitting())
    except AttributeError:
        return getattr(matching, "obs_ne", 0) == 0


def _extract_directed_edge(matching):
    """
    Extract (from_node, to_node) from a LeuvenMapMatching BaseMatching.

    DistanceMatching stores the matched road segment in edge_m.
    """

    edge = getattr(matching, "edge_m", None)

    if edge is None:
        return None

    node1 = getattr(edge, "l1", None)
    node2 = getattr(edge, "l2", None)

    if node1 is None or node2 is None:
        return None

    return node1, node2


# ---------------------------------------------------------------------------
# PARALLEL-ROAD DESPIKE
# ---------------------------------------------------------------------------

def _despike_parallel_road_snaps(
    gps_df: pd.DataFrame,
    matched_edges: list,
) -> None:
    """
    Correct an isolated one-point snap onto a parallel road.

    Example:

        way A
        way A
        way B   <- suspicious isolated point
        way A
        way A

    If the raw GPS bearing strongly disagrees with the B-road direction,
    resnap the point to the neighboring A-road segment.

    This function mutates gps_df in-place.
    """

    way_ids = gps_df["osm_way_id"].tolist()
    n = len(gps_df)

    for i in range(1, n - 1):

        current_edge = (
            matched_edges[i]
            if i < len(matched_edges)
            else None
        )

        if current_edge is None:
            continue

        if way_ids[i] is None:
            continue

        prev_way = way_ids[i - 1]
        next_way = way_ids[i + 1]
        current_way = way_ids[i]

        # Must be an isolated single-road blip.
        if prev_way != next_way:
            continue

        if prev_way == current_way:
            continue

        # ---------------------------------------------------------------
        # GPS speed / bearing
        # ---------------------------------------------------------------

        speed = (
            gps_df["speed"].iat[i]
            if "speed" in gps_df.columns
            else None
        )

        raw_bearing = (
            gps_df["bearing"].iat[i]
            if "bearing" in gps_df.columns
            else None
        )

        if speed is None or raw_bearing is None:
            continue

        try:
            speed = float(speed)
            raw_bearing = float(raw_bearing)
        except (TypeError, ValueError):
            continue

        if not math.isfinite(speed) or not math.isfinite(raw_bearing):
            continue

        if speed < BEARING_TRUST_SPEED_MPS:
            continue

        # ---------------------------------------------------------------
        # Current matched edge bearing
        # ---------------------------------------------------------------

        node1, node2 = current_edge

        try:
            lat1, lon1 = _MAP_CON.node_coordinates(node1)
            lat2, lon2 = _MAP_CON.node_coordinates(node2)
        except Exception:
            continue

        edge_bearing = _bearing_deg(
            lat1,
            lon1,
            lat2,
            lon2,
        )

        disagreement = _circular_diff_deg(
            edge_bearing,
            raw_bearing,
        )

        if disagreement < BEARING_DISAGREEMENT_DEG:
            continue

        # ---------------------------------------------------------------
        # Use previous matched edge as replacement candidate
        # ---------------------------------------------------------------

        prev_edge = (
            matched_edges[i - 1]
            if i - 1 < len(matched_edges)
            else None
        )

        if prev_edge is None:
            continue

        pn1, pn2 = prev_edge

        try:
            plat1, plon1 = _MAP_CON.node_coordinates(pn1)
            plat2, plon2 = _MAP_CON.node_coordinates(pn2)
        except Exception:
            continue

        raw_lat = gps_df["latitude"].iat[i]
        raw_lon = gps_df["longitude"].iat[i]

        try:
            proj_lat, proj_lon, dist_m = _project_point_to_segment(
                raw_lat,
                raw_lon,
                plat1,
                plon1,
                plat2,
                plon2,
            )
        except Exception:
            continue

        # Do NOT accept the despike if the replacement road is also too
        # far away.
        if dist_m > MAX_DIST_M:
            continue

        replacement_info = _EDGE_TO_WAY.get(
            (pn1, pn2)
        )

        if replacement_info is None:
            continue

        replacement_way, replacement_direction = replacement_info

        print(
            f"[map_matching] despiked idx={i}: "
            f"way {current_way} -> {replacement_way}, "
            f"bearing diff={disagreement:.0f}deg, "
            f"distance={dist_m:.1f}m"
        )

        gps_df.at[
            gps_df.index[i],
            "matched_lat"
        ] = proj_lat

        gps_df.at[
            gps_df.index[i],
            "matched_lon"
        ] = proj_lon

        gps_df.at[
            gps_df.index[i],
            "osm_way_id"
        ] = replacement_way

        gps_df.at[
            gps_df.index[i],
            "direction_label"
        ] = replacement_direction

        gps_df.at[
            gps_df.index[i],
            "match_raw_distance"
        ] = dist_m

        # Keep the replacement edge aligned with the observation.
        matched_edges[i] = (pn1, pn2)


# ---------------------------------------------------------------------------
# OSM EXTRACT DOWNLOAD
# ---------------------------------------------------------------------------

def _ensure_osm_extract(
    osm_pbf_path: str,
    osm_pbf_url: str | None,
) -> None:
    """
    Download the OSM extract if it isn't already present.

    Railway's filesystem can be ephemeral, so this may execute once after
    a fresh deployment/container start.
    """

    if os.path.exists(osm_pbf_path):
        return

    if not osm_pbf_url:
        raise RuntimeError(
            f"{osm_pbf_path} not found on disk and OSM_PBF_URL is not set "
            "— nothing to download it from."
        )

    print(
        f"[map_matching] {osm_pbf_path} not found, "
        f"downloading from {osm_pbf_url}"
    )

    with requests.get(
        osm_pbf_url,
        stream=True,
        timeout=120,
    ) as resp:

        resp.raise_for_status()

        with open(osm_pbf_path, "wb") as f:
            for chunk in resp.iter_content(
                chunk_size=1024 * 1024
            ):
                if chunk:
                    f.write(chunk)

    print(
        f"[map_matching] downloaded "
        f"{os.path.getsize(osm_pbf_path):,} bytes "
        f"to {osm_pbf_path}"
    )


# ---------------------------------------------------------------------------
# INITIALIZATION
# ---------------------------------------------------------------------------

def init_map_matcher(
    osm_pbf_path: str,
    osm_pbf_url: str | None = None,
) -> None:
    """
    Initialize the OSM road graph.

    Call this ONCE during FastAPI startup.
    """

    global _MAP_CON

    _ensure_osm_extract(
        osm_pbf_path,
        osm_pbf_url,
    )

    _MAP_CON = _build_map_from_pbf(
        osm_pbf_path
    )

    print(
        f"[map_matching] loaded OSM extract from "
        f"{osm_pbf_path}"
    )


# ---------------------------------------------------------------------------
# MAIN MAP-MATCH FUNCTION
# ---------------------------------------------------------------------------

def map_match_trip(
    gps_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Map-match one trip's GPS dataframe.

    Required columns:
        timestamp_ms
        latitude
        longitude

    Optional columns:
        speed
        bearing

    Returns:
        Same dataframe, sorted by timestamp_ms, with:

            matched_lat
            matched_lon
            osm_way_id
            direction_label
            match_raw_distance

    IMPORTANT:
        Raw GPS points are never dropped.

        If a point cannot be safely map-matched, its matched_lat/lon remain
        equal to the original GPS latitude/longitude and all map metadata is
        set to None.
    """

    if _MAP_CON is None:
        raise RuntimeError(
            "init_map_matcher() must run before map_match_trip()"
        )

    # -----------------------------------------------------------------------
    # Sort
    # -----------------------------------------------------------------------

    gps_df = (
        gps_df
        .sort_values("timestamp_ms")
        .reset_index(drop=True)
        .copy()
    )

    # -----------------------------------------------------------------------
    # Empty input
    # -----------------------------------------------------------------------

    if gps_df.empty:

        gps_df["matched_lat"] = pd.Series(
            dtype=float
        )

        gps_df["matched_lon"] = pd.Series(
            dtype=float
        )

        gps_df["osm_way_id"] = pd.Series(
            dtype="object"
        )

        gps_df["direction_label"] = pd.Series(
            dtype="object"
        )

        gps_df["match_raw_distance"] = pd.Series(
            dtype=float
        )

        return gps_df

    # -----------------------------------------------------------------------
    # Raw trace
    # -----------------------------------------------------------------------

    trace = [
        (
            float(lat),
            float(lon),
        )
        for lat, lon in zip(
            gps_df["latitude"],
            gps_df["longitude"],
        )
    ]

    # -----------------------------------------------------------------------
    # Initialize outputs to SAFE FALLBACK values.
    #
    # This is important:
    #
    #     matched_lat = raw latitude
    #     matched_lon = raw longitude
    #
    # until we have a verified road match.
    # -----------------------------------------------------------------------

    matched_lat = gps_df["latitude"].astype(float).tolist()
    matched_lon = gps_df["longitude"].astype(float).tolist()

    way_ids: list[Optional[int]] = [
        None
    ] * len(gps_df)

    directions: list[Optional[str]] = [
        None
    ] * len(gps_df)

    match_raw_distance: list[Optional[float]] = [
        None
    ] * len(gps_df)

    # One directed edge per GPS observation.
    matched_edges: list[Optional[tuple[int, int]]] = [
        None
    ] * len(gps_df)

    # -----------------------------------------------------------------------
    # LeuvenMapMatching 1.1.4
    # -----------------------------------------------------------------------
    #
    # max_dist is the library's hard emission-distance cutoff.
    #
    # Crucially, we still perform our own projection-distance check below.
    # The library's match is NOT trusted blindly.
    # -----------------------------------------------------------------------

    matcher = DistanceMatcher(
        _MAP_CON,

        max_dist=MAX_DIST_M,
        max_dist_init=MAX_DIST_M,

        obs_noise=OBS_NOISE_M,
        obs_noise_ne=OBS_NOISE_NE_M,

        dist_noise=DIST_NOISE_M,

        non_emitting_states=True,

        max_lattice_width=MAX_LATTICE_WIDTH,
    )

    try:
        states, last_idx = matcher.match(trace)

    except Exception as err:

        print(
            f"[map_matching] match() failed; "
            f"falling back to raw coordinates: {err!r}"
        )

        gps_df["matched_lat"] = matched_lat
        gps_df["matched_lon"] = matched_lon
        gps_df["osm_way_id"] = way_ids
        gps_df["direction_label"] = directions
        gps_df["match_raw_distance"] = match_raw_distance

        print(
            f"[map_matching] matched 0/{len(gps_df)} fixes "
            f"(matcher failure)"
        )

        return gps_df

    # -----------------------------------------------------------------------
    # IMPORTANT:
    #
    # DO NOT use:
    #
    #     states[i]
    #
    # as GPS observation i.
    #
    # Non-emitting states mean that states can contain extra map states.
    #
    # Instead inspect matcher.lattice_best and use:
    #
    #     matching.obs
    #
    # to recover the original GPS observation index.
    # -----------------------------------------------------------------------

    lattice_best = getattr(
        matcher,
        "lattice_best",
        None,
    )

    if not lattice_best:
        print(
            "[map_matching] matcher returned no lattice_best path"
        )

        gps_df["matched_lat"] = matched_lat
        gps_df["matched_lon"] = matched_lon
        gps_df["osm_way_id"] = way_ids
        gps_df["direction_label"] = directions
        gps_df["match_raw_distance"] = match_raw_distance

        return gps_df

    # -----------------------------------------------------------------------
    # Extract only emitting matches.
    #
    # Multiple matching objects may theoretically reference an observation.
    # Keep the last emitting object encountered in the best path.
    # -----------------------------------------------------------------------

    emitting_matches = {}

    for matching in lattice_best:

        if not _is_emitting_matching(matching):
            continue

        obs_idx = getattr(
            matching,
            "obs",
            None,
        )

        if obs_idx is None:
            continue

        try:
            obs_idx = int(obs_idx)
        except (TypeError, ValueError):
            continue

        if obs_idx < 0 or obs_idx >= len(gps_df):
            continue

        emitting_matches[obs_idx] = matching

    # -----------------------------------------------------------------------
    # Project each emitting match onto its directed road edge.
    # -----------------------------------------------------------------------

    rejected_too_far = 0
    rejected_bad_edge = 0

    for obs_idx, matching in sorted(
        emitting_matches.items()
    ):

        edge = _extract_directed_edge(
            matching
        )

        if edge is None:
            rejected_bad_edge += 1
            continue

        node1, node2 = edge

        # ---------------------------------------------------------------
        # Look up OSM way + semantic direction.
        # ---------------------------------------------------------------

        way_info = _EDGE_TO_WAY.get(
            (node1, node2)
        )

        if way_info is None:
            rejected_bad_edge += 1
            continue

        way_id, direction = way_info

        # ---------------------------------------------------------------
        # Get road segment coordinates.
        # ---------------------------------------------------------------

        try:
            lat1, lon1 = _MAP_CON.node_coordinates(
                node1
            )

            lat2, lon2 = _MAP_CON.node_coordinates(
                node2
            )

        except Exception as err:

            print(
                f"[map_matching] node lookup failed for "
                f"edge=({node1},{node2}): {err!r}"
            )

            rejected_bad_edge += 1
            continue

        # ---------------------------------------------------------------
        # Raw GPS coordinate
        # ---------------------------------------------------------------

        raw_lat = float(
            gps_df["latitude"].iat[obs_idx]
        )

        raw_lon = float(
            gps_df["longitude"].iat[obs_idx]
        )

        # ---------------------------------------------------------------
        # Project raw GPS onto road segment.
        # ---------------------------------------------------------------

        try:

            proj_lat, proj_lon, dist_m = (
                _project_point_to_segment(
                    raw_lat,
                    raw_lon,
                    lat1,
                    lon1,
                    lat2,
                    lon2,
                )
            )

        except Exception as err:

            print(
                f"[map_matching] projection failed for "
                f"obs={obs_idx}, edge=({node1},{node2}): "
                f"{err!r}"
            )

            rejected_bad_edge += 1
            continue

        # ---------------------------------------------------------------
        # HARD SAFETY CHECK
        # ---------------------------------------------------------------
        #
        # This is independent of the library's HMM state.
        #
        # If the actual raw-GPS -> road projection is > 50 m,
        # DO NOT allow that road match into downstream processing.
        # ---------------------------------------------------------------

        if not math.isfinite(dist_m):
            rejected_too_far += 1
            continue

        if dist_m > MAX_DIST_M:
            rejected_too_far += 1

            print(
                f"[map_matching] rejected obs={obs_idx}: "
                f"projection distance={dist_m:.1f}m "
                f"> {MAX_DIST_M:.1f}m"
            )

            continue

        # ---------------------------------------------------------------
        # ACCEPT MATCH
        # ---------------------------------------------------------------

        matched_lat[obs_idx] = proj_lat
        matched_lon[obs_idx] = proj_lon

        way_ids[obs_idx] = way_id
        directions[obs_idx] = direction
        match_raw_distance[obs_idx] = dist_m

        matched_edges[obs_idx] = (
            node1,
            node2,
        )

    # -----------------------------------------------------------------------
    # Write primary results
    # -----------------------------------------------------------------------

    gps_df["matched_lat"] = matched_lat
    gps_df["matched_lon"] = matched_lon
    gps_df["osm_way_id"] = way_ids
    gps_df["direction_label"] = directions
    gps_df["match_raw_distance"] = match_raw_distance

    # -----------------------------------------------------------------------
    # Optional isolated parallel-road despike.
    #
    # This uses the correctly observation-aligned matched_edges array.
    # -----------------------------------------------------------------------

    if (
        "bearing" in gps_df.columns
        and "speed" in gps_df.columns
    ):

        _despike_parallel_road_snaps(
            gps_df,
            matched_edges,
        )

    else:

        print(
            "[map_matching] skipping bearing despike — "
            "bearing/speed not in gps_df"
        )

    # -----------------------------------------------------------------------
    # Statistics
    # -----------------------------------------------------------------------

    n_total = len(gps_df)

    n_ok = sum(
        1
        for way in gps_df["osm_way_id"]
        if way is not None
        and not pd.isna(way)
    )

    n_unmatched = n_total - n_ok

    dists = [
        float(d)
        for d in gps_df["match_raw_distance"]
        if d is not None
        and not pd.isna(d)
        and math.isfinite(float(d))
    ]

    if dists:

        avg_dist = sum(dists) / len(dists)
        median_dist = float(
            pd.Series(dists).median()
        )
        max_dist = max(dists)

        print(
            f"[map_matching] matched "
            f"{n_ok}/{n_total} fixes; "
            f"unmatched={n_unmatched}; "
            f"avg={avg_dist:.1f}m; "
            f"median={median_dist:.1f}m; "
            f"max={max_dist:.1f}m; "
            f"rejected_too_far={rejected_too_far}; "
            f"rejected_bad_edge={rejected_bad_edge}; "
            f"last_idx={last_idx}"
        )

    else:

        print(
            f"[map_matching] matched "
            f"{n_ok}/{n_total} fixes; "
            f"unmatched={n_unmatched}; "
            f"no accepted projection distances; "
            f"rejected_too_far={rejected_too_far}; "
            f"rejected_bad_edge={rejected_bad_edge}; "
            f"last_idx={last_idx}"
        )

    return gps_df