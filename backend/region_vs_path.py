import os
from pathlib import Path

import folium
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

import yaw
from map_regions import (
    ROAD_REGIONS,
    MapDataUnavailableError,
    _segment_region_interval,
    regions_for_trace,
)


PAGE_SIZE = 1000
CARTO_TILE_KEY = "cb1_2gzd_1_d14af46dbfbc5d8f214caf08"


def fetch_session_rows(
    client,
    table,
    session_id,
    tiebreak_column=None,
    columns=None,
    timestamp_range=None,
    page_size=PAGE_SIZE,
):
    rows = []
    start = 0
    cursor = None

    while True:
        query = (
            client.table(table)
            .select(",".join(columns) if columns else "*")
            .eq("session_id", session_id)
            .order("timestamp_ms", desc=False)
        )
        if timestamp_range is not None:
            query = query.gte("timestamp_ms", timestamp_range[0]).lte(
                "timestamp_ms", timestamp_range[1]
            )
        if tiebreak_column:
            query = query.order(tiebreak_column, desc=False)
            if cursor is not None:
                last_timestamp, last_tiebreak = cursor
                query = query.or_(
                    f"timestamp_ms.gt.{last_timestamp},"
                    f"and(timestamp_ms.eq.{last_timestamp},"
                    f"{tiebreak_column}.gt.{last_tiebreak})"
                )
            page_range = (0, page_size - 1)
        else:
            page_range = (start, start + page_size - 1)
        response = query.range(*page_range).execute()
        batch = response.data or []
        if not batch:
            break

        rows.extend(batch)
        if len(batch) < page_size:
            break
        if tiebreak_column:
            last_row = batch[-1]
            cursor = (last_row["timestamp_ms"], last_row[tiebreak_column])
            if cursor[0] is None or cursor[1] is None:
                raise ValueError(
                    f"{table} keyset columns timestamp_ms and "
                    f"{tiebreak_column} must not contain null values."
                )
        else:
            start += page_size

    return rows


def matched_coordinates(matched_rows):
    matched = pd.DataFrame(matched_rows)
    required = ["timestamp_ms", "matched_lat", "matched_lon", "osm_way_id"]
    missing = [column for column in required if column not in matched.columns]
    if missing:
        raise ValueError(
            f"matched_gps_data is missing required columns: {', '.join(missing)}"
        )

    for column in ("timestamp_ms", "matched_lat", "matched_lon"):
        matched[column] = pd.to_numeric(matched[column], errors="coerce")
    matched = matched.dropna(
        subset=["timestamp_ms", "matched_lat", "matched_lon", "osm_way_id"]
    )
    matched = matched.sort_values("timestamp_ms", kind="stable")
    matched = matched.drop_duplicates("timestamp_ms", keep="first")
    return matched[["matched_lat", "matched_lon"]].to_numpy(dtype=float).tolist()


def intersecting_regions(coordinates):
    regions = []
    points = [(longitude, latitude) for latitude, longitude in coordinates]
    for region in ROAD_REGIONS:
        if any(
            _segment_region_interval(start, end, region.bounds) is not None
            for start, end in zip(points, points[1:])
        ) or any(
            region.bounds[0] <= longitude <= region.bounds[2]
            and region.bounds[1] <= latitude <= region.bounds[3]
            for longitude, latitude in points
        ):
            regions.append(region)
    return regions


def create_region_path_map(
    raw_coordinates,
    matched_route,
    regions,
    coverage_error=None,
    yaw_route=None,
):
    if not raw_coordinates:
        raise ValueError("No raw production GPS points are available to plot.")

    route_map = folium.Map(
        location=raw_coordinates[0],
        zoom_start=7,
        control_scale=True,
        tiles=None,
    )
    folium.TileLayer(
        tiles=(
            "https://{s}.basemaps.cartocdn.com/dark_all/"
            "{z}/{x}/{y}{r}.png?key=" + CARTO_TILE_KEY
        ),
        attr="© OpenStreetMap contributors © CARTO",
        name="CARTO Dark",
        subdomains="abcd",
        max_zoom=20,
        control=False,
    ).add_to(route_map)
    folium.TileLayer(
        tiles=(
            "https://{s}.basemaps.cartocdn.com/dark_only_labels/"
            "{z}/{x}/{y}{r}.png?key=" + CARTO_TILE_KEY
        ),
        attr="© CARTO",
        name="CARTO labels",
        subdomains="abcd",
        max_zoom=20,
        control=False,
        overlay=True,
    ).add_to(route_map)

    if coverage_error:
        folium.Marker(
            raw_coordinates[0],
            tooltip="Map coverage incomplete",
            popup=(
                "The backend would not download any regions for this session "
                "because route coverage is incomplete.<br><br>"
                f"{coverage_error}"
            ),
            icon=folium.Icon(color="red", icon="warning-sign"),
        ).add_to(route_map)

    region_group = folium.FeatureGroup(
        name=(
            "Route-selected region bounds"
            if not coverage_error
            else "Intersecting region bounds (coverage incomplete)"
        ),
        show=True,
    )
    colors = ("green", "purple", "orange", "darkred", "cadetblue", "darkblue")
    bounds_to_fit = list(raw_coordinates)
    for index, region in enumerate(regions):
        min_lon, min_lat, max_lon, max_lat = region.bounds
        rectangle = [
            [min_lat, min_lon],
            [min_lat, max_lon],
            [max_lat, max_lon],
            [max_lat, min_lon],
        ]
        color = colors[index % len(colors)]
        folium.Polygon(
            rectangle,
            color=color,
            weight=3,
            fill=True,
            fill_color=color,
            fill_opacity=0.12,
            tooltip=f"{region.region_id} ({region.filename})",
            popup=(
                f"<b>{region.region_id}</b><br>"
                f"Extract: {region.filename}<br>"
                f"Bounds (min_lon, min_lat, max_lon, max_lat): "
                f"{region.bounds}"
            ),
        ).add_to(region_group)
        bounds_to_fit.extend(
            [[min_lat, min_lon], [max_lat, max_lon]]
        )
    region_group.add_to(route_map)

    raw_group = folium.FeatureGroup(name="Raw GPS", show=True)
    folium.PolyLine(
        raw_coordinates,
        color="red",
        weight=3,
        opacity=0.85,
        tooltip="Raw GPS route used by backend region selection (production source)",
    ).add_to(raw_group)
    folium.CircleMarker(
        raw_coordinates[0],
        radius=5,
        color="green",
        fill=True,
        tooltip="Raw GPS start",
    ).add_to(raw_group)
    folium.CircleMarker(
        raw_coordinates[-1],
        radius=5,
        color="red",
        fill=True,
        tooltip="Raw GPS end",
    ).add_to(raw_group)
    raw_group.add_to(route_map)

    matched_group = folium.FeatureGroup(name="Map-matched GPS", show=True)
    if matched_route:
        folium.PolyLine(
            matched_route,
            color="blue",
            weight=4,
            opacity=0.9,
            tooltip="Matched GPS route (test target)",
        ).add_to(matched_group)
        bounds_to_fit.extend(matched_route)
    matched_group.add_to(route_map)

    yaw_group = folium.FeatureGroup(name="GPS-assisted yaw", show=True)
    if yaw_route:
        folium.PolyLine(
            yaw_route,
            color="yellow",
            weight=4,
            opacity=0.9,
            tooltip="GPS-assisted yaw route",
        ).add_to(yaw_group)
        bounds_to_fit.extend(yaw_route)
    yaw_group.add_to(route_map)

    route_map.fit_bounds(bounds_to_fit)
    folium.LayerControl(collapsed=False).add_to(route_map)
    return route_map


def main():
    if not yaw.sessionid or yaw.sessionid == "PASTE_SESSION_ID_HERE":
        raise ValueError("Set the sessionid near the top of yaw.py before running.")

    load_dotenv(Path(__file__).resolve().parent / ".env")
    source_url = os.environ.get(
        "SOURCE_PRODUCTION_URL", os.environ.get("SOURCE_URL")
    )
    source_key = os.environ.get(
        "SOURCE_PRODUCTION_KEY", os.environ.get("SOURCE_KEY")
    )
    target_url = os.environ.get("TARGET_TEST_URL")
    target_key = os.environ.get("TARGET_TEST_KEY")
    if not source_url or not source_key:
        raise RuntimeError(
            "Set SOURCE_PRODUCTION_URL and SOURCE_PRODUCTION_KEY "
            "(or SOURCE_URL and SOURCE_KEY) in the environment or backend .env."
        )
    if not target_url or not target_key:
        raise RuntimeError(
            "Set TARGET_TEST_URL and TARGET_TEST_KEY in the environment "
            "or backend .env."
        )

    source_client = create_client(source_url, source_key)
    target_client = create_client(target_url, target_key)
    raw_rows = fetch_session_rows(
        source_client,
        "gps_data",
        yaw.sessionid,
        "gps_id",
    )
    if not raw_rows:
        raise ValueError(
            f"No production gps_data rows found for session {yaw.sessionid}."
        )
    raw_coordinates = yaw.build_raw_gps_coordinates(raw_rows)

    gps_timestamps = pd.to_numeric(
        pd.DataFrame(raw_rows)["timestamp_ms"],
        errors="coerce",
    ).dropna()
    if gps_timestamps.empty:
        raise ValueError(
            f"No valid GPS timestamps found for session {yaw.sessionid}."
        )

    imu_rows = fetch_session_rows(
        source_client,
        "imu_data",
        yaw.sessionid,
        "imu_data_id",
        columns=(
            "timestamp_ms",
            "accel_x",
            "accel_y",
            "accel_z",
            "gyro_x",
            "gyro_y",
            "gyro_z",
            "imu_data_id",
        ),
        timestamp_range=(
            gps_timestamps.min(),
            gps_timestamps.max(),
        ),
    )
    if not imu_rows:
        raise ValueError(
            f"No production imu_data rows found for session {yaw.sessionid}."
        )
    imu = yaw.convert_gyro_z_with_aliv_orientation(pd.DataFrame(imu_rows))
    _, yaw_route = yaw.gps_assisted_yaw_trajectory(
        imu,
        pd.DataFrame(raw_rows),
    )

    try:
        regions = regions_for_trace(raw_coordinates)
        coverage_error = None
    except MapDataUnavailableError as error:
        regions = intersecting_regions(raw_coordinates)
        coverage_error = str(error)

    matched_rows = fetch_session_rows(
        target_client,
        "matched_gps_data",
        yaw.sessionid,
    )
    matched_route = matched_coordinates(matched_rows) if matched_rows else []
    route_map = create_region_path_map(
        raw_coordinates,
        matched_route,
        regions,
        coverage_error,
        yaw_route=yaw_route,
    )

    output_path = Path(__file__).resolve().parent / "region_vs_path.html"
    route_map.save(str(output_path))
    print(f"Saved region and route map: {output_path}")
    print(f"Session: {yaw.sessionid}")
    print(f"Raw production GPS points: {len(raw_coordinates)}")
    print(f"Matched test-target GPS points: {len(matched_route)}")
    print(f"GPS-assisted yaw points: {len(yaw_route)}")
    if coverage_error:
        print(f"Backend coverage result: no regions would be fetched: {coverage_error}")
    else:
        print(
            "Regions selected by the backend: "
            + ", ".join(region.region_id for region in regions)
        )
    print("Open region_vs_path.html in a browser to inspect the map.")


if __name__ == "__main__":
    main()
