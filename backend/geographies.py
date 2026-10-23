import math
import os
import threading
import time
import requests

GRID = 0.1   # keep equal to CITY_DISCOVERY_GRID_SIZE in the frontend
_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"

# Nominatim rejects generic/placeholder User-Agents (e.g. example.com addresses) with 403.
# Set NOMINATIM_USER_AGENT in your env to something real, e.g. "vehnicate/1.0 (you@yourdomain.com)".
_USER_AGENT = os.environ.get("NOMINATIM_USER_AGENT", "vehnicate/1.0 (vehnicate@gmail.com)")

_geocode_lock = threading.Lock()   # trip worker + backfill share Nominatim's 1 req/sec budget
_last_request = 0.0

# ── Circuit breaker ─────────────────────────────────────────────────────────
# A 403/429 means Nominatim is blocking/throttling us; retrying every bucket
# only makes that worse. Stop calling it for a cooldown period instead.
_BLOCK_COOLDOWN_S = 15 * 60       # pause geocoding this long after a 403/429
_MAX_CONSECUTIVE_FAILURES = 5     # other errors (timeouts etc.) trip it after this many in a row
_blocked_until = 0.0
_consecutive_failures = 0


def _run(query):
    return query.execute()


def bucket_key(lat, lon, grid=GRID):
    # Same formula as SQL: floor(lat/grid)::int::text || ':' || floor(lon/grid)::int::text
    return f"{math.floor(lat / grid)}:{math.floor(lon / grid)}"


def points_to_buckets(points):
    """{key: (lat, lon)} using the first real GPS fix seen in each bucket."""
    buckets = {}
    for lat, lon in points:
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)):
            continue
        buckets.setdefault(bucket_key(lat, lon), (lat, lon))
    return buckets


def _trip_breaker(reason):
    global _blocked_until, _consecutive_failures
    _blocked_until = time.time() + _BLOCK_COOLDOWN_S
    _consecutive_failures = 0
    print(f"[geographies] {reason} — pausing geocoding for {_BLOCK_COOLDOWN_S // 60} min")


def _reverse_geocode(lat, lon):
    """Returns {district, city, state} or None."""
    global _last_request, _consecutive_failures
    with _geocode_lock:
        if time.time() < _blocked_until:
            return None   # breaker open: don't touch Nominatim

        wait = 1.1 - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(
                _NOMINATIM,
                params={"lat": lat, "lon": lon, "format": "json", "zoom": 10, "addressdetails": 1},
                headers={"User-Agent": _USER_AGENT, "Accept-Language": "en"},
                timeout=10,
            )
            r.raise_for_status()
            a = r.json().get("address", {})
            _consecutive_failures = 0
        except Exception as e:
            print(f"[geographies] geocode failed for {lat},{lon}: {e!r}")
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (403, 429):
                _trip_breaker(f"Nominatim returned {status} (blocked/rate-limited)")
            else:
                _consecutive_failures += 1
                if _consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    _trip_breaker(f"{_consecutive_failures} consecutive geocode failures")
            return None
        finally:
            _last_request = time.time()

    raw = (a.get("state_district") or a.get("county") or a.get("city")
           or a.get("town") or a.get("municipality") or a.get("village"))
    if not raw:
        return None
    for suffix in (" district", " taluk", " taluka", " tehsil", " division"):
        if raw.lower().endswith(suffix):
            raw = raw[: -len(suffix)]
    return {"district": raw.strip(), "city": a.get("city"), "state": a.get("state", "")}


def _known_places(supabase_target, keys, run=_run):
    known = {}
    for i in range(0, len(keys), 100):
        chunk = keys[i:i + 100]
        rows = run(
            supabase_target.table("geographies")
            .select("key,district,city,state").in_("key", chunk)
        ).data or []
        for r in rows:
            known[r["key"]] = r
    return known


def _save(supabase_target, key, place, user_ids, run=_run):
    run(supabase_target.rpc("upsert_geography", {
        "p_key": key,
        "p_district": place["district"],
        "p_city": place["city"],
        "p_state": place["state"],
        "p_user_ids": user_ids,
    }))


def add_session_geographies(supabase_target, user_id, points, run=_run):
    """Per-trip hook. Idempotent: known buckets cost no geocoding, they just get the user id merged in."""
    buckets = points_to_buckets(points)
    if not buckets:
        return 0
    known = _known_places(supabase_target, list(buckets), run)
    saved = 0
    for key, (lat, lon) in buckets.items():
        place = known.get(key) or _reverse_geocode(lat, lon)
        if not place:
            continue
        _save(supabase_target, key, place, [str(user_id)], run)
        saved += 1
    print(f"[geographies] {saved}/{len(buckets)} buckets saved for user {user_id}")
    return saved


def backfill_all_geographies(supabase_target, sessions, get_points, run=_run):
    """sessions: [(session_id, user_id)]. get_points(session_id) -> [(lat, lon)]."""
    agg = {}   # key -> {"lat", "lon", "users": set}
    for i, (session_id, user_id) in enumerate(sessions):
        try:
            points = get_points(session_id)
        except Exception as e:
            print(f"[geographies-backfill] session {session_id} skipped: {e!r}")
            continue
        for key, (lat, lon) in points_to_buckets(points).items():
            b = agg.setdefault(key, {"lat": lat, "lon": lon, "users": set()})
            b["users"].add(str(user_id))
        print(f"[geographies-backfill] read session {i + 1}/{len(sessions)}")

    known = _known_places(supabase_target, list(agg), run)
    done = 0
    for key, b in agg.items():
        place = known.get(key) or _reverse_geocode(b["lat"], b["lon"])
        if not place:
            continue
        _save(supabase_target, key, place, sorted(b["users"]), run)
        done += 1
    print(f"[geographies-backfill] finished: {done}/{len(agg)} buckets from {len(sessions)} sessions")
    return done