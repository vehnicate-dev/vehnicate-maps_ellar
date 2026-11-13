import math

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def compute_total_distance(gps_df) -> float:
    """Sum haversine distances between consecutive GPS points (sorted by timestamp_ms)."""
    df = gps_df.sort_values("timestamp_ms").reset_index(drop=True)
    if len(df) < 2:
        return 0.0

    total = 0.0
    lats = df["latitude"].to_numpy()
    lons = df["longitude"].to_numpy()

    for i in range(1, len(df)):
        total += haversine(lats[i - 1], lons[i - 1], lats[i], lons[i])

    return total


def compute_matched_distance(matched_rows) -> float:
    """Sum consecutive road-matched or estimated fixes, ignoring raw fallbacks."""
    df = matched_rows.copy()
    required = {
        "timestamp_ms",
        "matched_lat",
        "matched_lon",
        "osm_way_id",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(
            "Matched GPS rows are missing required columns: "
            + ", ".join(sorted(missing))
        )

    if "is_estimated" not in df.columns:
        df["is_estimated"] = False
    else:
        df["is_estimated"] = df["is_estimated"].fillna(False).astype(bool)

    df = df.sort_values("timestamp_ms")
    total = 0.0
    previous_point = None
    for row in df.itertuples(index=False):
        is_estimated = bool(row.is_estimated)
        has_road_match = False
        try:
            way_id = float(row.osm_way_id)
            has_road_match = math.isfinite(way_id)
        except (TypeError, ValueError):
            pass
        if not has_road_match and not is_estimated:
            previous_point = None
            continue
        try:
            lat, lon = float(row.matched_lat), float(row.matched_lon)
        except (TypeError, ValueError):
            previous_point = None
            continue
        if (
            not math.isfinite(lat)
            or not math.isfinite(lon)
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
        ):
            previous_point = None
            continue
        if previous_point is not None:
            previous_lat, previous_lon = previous_point
            total += haversine(previous_lat, previous_lon, lat, lon)
        previous_point = (lat, lon)
    return total