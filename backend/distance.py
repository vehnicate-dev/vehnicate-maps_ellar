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