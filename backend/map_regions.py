"""Region catalog and lazy OSM extract downloads for trip map matching."""

from __future__ import annotations

import math
import os
import re
import threading
from dataclasses import dataclass

import requests


class MapDataUnavailableError(RuntimeError):
    """Raised when a trip's complete route cannot be matched with available OSM data."""


@dataclass(frozen=True)
class RoadRegion:
    region_id: str
    bounds: tuple[float, float, float, float]
    url: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


_STORAGE_PREFIX = (
    "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/"
    "road_networks/"
)
_REGIONS_LOCK = threading.RLock()


# Bounds are (minimum longitude, minimum latitude, maximum longitude,
# maximum latitude). They describe the BBBike extract areas, not administrative
# boundaries. Update them if an extract is redrawn.
ROAD_REGIONS = (
    RoadRegion("bharuch", (72.50000, 21.40216, 73.50561, 22.21943),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/bharuch.osm.pbf"),
    RoadRegion("bengaluru", (77.32755, 12.65818, 77.82026, 13.23257),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/bengaluru.osm.pbf"),
    RoadRegion("chennai-metro", (79.60000, 12.50000, 80.35000, 13.55000),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/chennai.osm.pbf"),
    RoadRegion("chittoor-tirupati", (78.06799, 12.62347, 80.05254, 14.05039),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/chittoor.osm.pbf"),
    RoadRegion("coimbatore", (76.900, 10.900, 77.100, 11.200),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/coimbatore.osm.pbf"),
    RoadRegion("dindigul", (77.268, 10.019, 78.338, 10.834),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/dindigul.osm.pbf"),
    RoadRegion("kozhikode", (75.53652, 11.12271, 76.14788, 11.80564),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/kozhikode.osm.pbf"),
    RoadRegion("nilgiris", (76.23387, 11.18863, 77.01849, 11.67299),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/nilgiris.osm.pbf"),
    RoadRegion("panchmahal", (73.35233, 22.28445, 73.93166, 23.10807),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/panchmahal.osm.pbf"),
    RoadRegion("prayagraj", (81.52024, 24.80515, 82.35335, 25.75157),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/prayagraj.osm.pbf"),
    RoadRegion("surat", (72.59554, 20.81509, 73.70092, 21.56518),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/surat.osm.pbf"),
    RoadRegion("tiruchirappalli", (78.16565, 10.29415, 79.01526, 11.40501),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/tiruchirappalli.osm.pbf"),
    RoadRegion("tiruppur", (77.048, 10.231, 77.892, 11.351),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/tiruppur.osm.pbf"),
    RoadRegion("vadodara", (72.75881, 21.82028, 73.56698, 22.80941),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/vadodara.osm.pbf"),
    RoadRegion("vellore", (78.59414, 12.62771, 79.28315, 13.09909),
               "https://mmjusghgeedycrrfdejg.supabase.co/storage/v1/object/public/road_networks/vellore.osm.pbf"),
)


def register_road_region(
    region_id: str,
    bounds: tuple[float, float, float, float],
) -> RoadRegion:
    """Register a new region backed by <region_id>.osm.pbf in Supabase."""
    normalized_id = region_id.strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized_id):
        raise ValueError("region_id must contain only lowercase letters, digits, and hyphens.")

    try:
        normalized_bounds = tuple(float(value) for value in bounds)
    except (TypeError, ValueError) as err:
        raise ValueError("bounds must contain four numeric values.") from err
    if len(normalized_bounds) != 4 or not all(
        math.isfinite(value) for value in normalized_bounds
    ):
        raise ValueError("bounds must contain four finite numeric values.")

    min_lon, min_lat, max_lon, max_lat = normalized_bounds
    if (
        not -180 <= min_lon < max_lon <= 180
        or not -90 <= min_lat < max_lat <= 90
    ):
        raise ValueError(
            "bounds must be ordered as min_lon, min_lat, max_lon, max_lat "
            "within valid coordinate ranges."
        )

    region = RoadRegion(
        normalized_id,
        normalized_bounds,
        f"{_STORAGE_PREFIX}{normalized_id}.osm.pbf",
    )
    global ROAD_REGIONS
    with _REGIONS_LOCK:
        if any(existing.region_id == normalized_id for existing in ROAD_REGIONS):
            raise ValueError(f"region '{normalized_id}' is already configured.")
        ROAD_REGIONS = (*ROAD_REGIONS, region)
    return region


def _segment_region_interval(
    start: tuple[float, float],
    end: tuple[float, float],
    bounds: tuple[float, float, float, float],
) -> tuple[float, float] | None:
    """Return the segment parameter interval inside a lon/lat rectangle."""
    lon1, lat1 = start
    lon2, lat2 = end
    min_lon, min_lat, max_lon, max_lat = bounds
    dx, dy = lon2 - lon1, lat2 - lat1
    entering, leaving = 0.0, 1.0

    for p, q in (
        (-dx, lon1 - min_lon),
        (dx, max_lon - lon1),
        (-dy, lat1 - min_lat),
        (dy, max_lat - lat1),
    ):
        if p == 0:
            if q < 0:
                return None
            continue
        ratio = q / p
        if p < 0:
            entering = max(entering, ratio)
        else:
            leaving = min(leaving, ratio)
        if entering > leaving:
            return None

    return entering, leaving


def _coordinate_at(
    start: tuple[float, float],
    end: tuple[float, float],
    fraction: float,
) -> tuple[float, float]:
    return (
        start[0] + (end[0] - start[0]) * fraction,
        start[1] + (end[1] - start[1]) * fraction,
    )


def _point_regions(
    point: tuple[float, float],
) -> list[RoadRegion]:
    lon, lat = point
    with _REGIONS_LOCK:
        regions = ROAD_REGIONS
    return [
        region
        for region in regions
        if region.bounds[0] <= lon <= region.bounds[2]
        and region.bounds[1] <= lat <= region.bounds[3]
    ]


def regions_for_trace(points) -> list[RoadRegion]:
    """Find all extracts along a GPS trace and reject any uncovered segment."""
    trace: list[tuple[float, float]] = []
    for raw_lat, raw_lon in points:
        try:
            lat, lon = float(raw_lat), float(raw_lon)
        except (TypeError, ValueError):
            continue
        if (
            not math.isfinite(lat)
            or not math.isfinite(lon)
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
        ):
            continue
        trace.append((lon, lat))

    if not trace:
        raise MapDataUnavailableError("The GPS trace has no valid coordinates.")

    selected_ids: set[str] = set()
    with _REGIONS_LOCK:
        regions_catalog = ROAD_REGIONS
    if len(trace) == 1:
        selected_ids.update(region.region_id for region in _point_regions(trace[0]))
        if not selected_ids:
            lon, lat = trace[0]
            raise MapDataUnavailableError(
                f"No configured OSM extract covers the trip near "
                f"latitude={lat:.5f}, longitude={lon:.5f}."
            )
    else:
        for start, end in zip(trace, trace[1:]):
            intervals = []
            for region in regions_catalog:
                interval = _segment_region_interval(start, end, region.bounds)
                if interval is not None:
                    intervals.append((interval[0], interval[1], region))

            intervals.sort(key=lambda item: (item[0], item[1]))
            selected_ids.update(
                region.region_id for _, _, region in intervals
            )
            covered_until = 0.0
            for interval_start, interval_end, region in intervals:
                if interval_start > covered_until + 1e-9:
                    gap_fraction = (covered_until + interval_start) / 2
                    lon, lat = _coordinate_at(start, end, gap_fraction)
                    raise MapDataUnavailableError(
                        f"No configured OSM extract covers the trip near "
                        f"latitude={lat:.5f}, longitude={lon:.5f}."
                    )
                selected_ids.add(region.region_id)
                covered_until = max(covered_until, interval_end)
                if covered_until >= 1.0 - 1e-9:
                    break

            if covered_until < 1.0 - 1e-9:
                lon, lat = _coordinate_at(start, end, (covered_until + 1) / 2)
                raise MapDataUnavailableError(
                    f"No configured OSM extract covers the trip near "
                    f"latitude={lat:.5f}, longitude={lon:.5f}."
                )

    return [
        region for region in regions_catalog
        if region.region_id in selected_ids
    ]


def ensure_region_extract(region: RoadRegion, cache_dir: str) -> str:
    """Return a cached PBF path, downloading it atomically when necessary."""
    os.makedirs(cache_dir, exist_ok=True)
    final_path = os.path.join(cache_dir, region.filename)
    if os.path.isfile(final_path) and os.path.getsize(final_path) > 0:
        return final_path

    temporary_path = final_path + ".part"
    try:
        print(
            f"[map_matching] downloading region={region.region_id} "
            f"from {region.url}"
        )
        with requests.get(
            region.url,
            stream=True,
            timeout=(15, 180),
        ) as response:
            response.raise_for_status()
            with open(temporary_path, "wb") as extract_file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        extract_file.write(chunk)

        if os.path.getsize(temporary_path) == 0:
            raise MapDataUnavailableError(
                f"OSM extract for region '{region.region_id}' downloaded empty."
            )
        os.replace(temporary_path, final_path)
        print(
            f"[map_matching] downloaded region={region.region_id} "
            f"({os.path.getsize(final_path):,} bytes)"
        )
        return final_path
    except requests.HTTPError as err:
        status = err.response.status_code if err.response is not None else None
        if status in (404, 410):
            reason = "is not available in Supabase"
        else:
            reason = f"download failed with HTTP {status}"
        raise MapDataUnavailableError(
            f"OSM extract for region '{region.region_id}' {reason}: {region.url}"
        ) from err
    except requests.RequestException as err:
        raise MapDataUnavailableError(
            f"Could not download OSM extract for region "
            f"'{region.region_id}': {err}"
        ) from err
    except OSError as err:
        raise MapDataUnavailableError(
            f"Could not cache OSM extract for region "
            f"'{region.region_id}': {err}"
        ) from err
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
