import math
import h3 as h3lib
from supabase import Client
from ledger import (
    ledger_discovery_frozen,
    ledger_discovery_liquid,
    ledger_late_legit_liquid,
    ledger_confirmation_liquid,
)

# ---------------------------------------------------------------------------
# Geometry helpers.. haversine to compute the distance btw two coordinates
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _weighted_centroid(
    old_lat: float, old_lon: float, old_count: int,
    new_lat: float, new_lon: float,
) -> tuple[list, int]:
    n = old_count + 1
    lat = (old_lat * old_count + new_lat) / n
    lon = (old_lon * old_count + new_lon) / n
    return [lat, lon], n


PROXIMITY_THRESHOLD_M = 15  # metres


def _find_nearby_key(coord: list, existing: dict) -> str | None:
    lat, lon = float(coord[0]), float(coord[1])
    for key, row in existing.items():
        elat, elon = float(row["location"][0]), float(row["location"][1])
        if _haversine_m(lat, lon, elat, elon) < PROXIMITY_THRESHOLD_M:
            return key
    return None


def _compute_confidence(existing: dict, N: int, target_keys: set[str]) -> dict[str, float]:
    if not target_keys:
        return {}
    if N == 0:
        return {key: 0.0 for key in target_keys}
    if N == 1:
        return {key: 100.0 for key in target_keys}

    rd_trip_sets: list[tuple[str, set]] = [
        (key, set(row["rd_trip_ids"] or []))
        for key, row in existing.items()
    ]

    result: dict[str, float] = {}
    for ego_key, ego_trips in rd_trip_sets:
        if ego_key not in target_keys:
            continue

        union_others: set = set()
        for key, trip_set in rd_trip_sets:
            if key == ego_key:
                continue
            union_others |= trip_set

        u_i = len(union_others)
        if u_i == 0:
            result[ego_key] = 0.0
            continue

        t_i_and_u_i = len(ego_trips & union_others)

        raw = (t_i_and_u_i / u_i) * 100.0
        result[ego_key] = max(0.0, min(100.0, raw))

    return result


def _credit_liquid_ellar(supabase_target: Client, user_id: str, amount: float) -> None:
    if amount == 0.0:
        return
    resp = (
        supabase_target
        .table("user_details")
        .select("liquid_ellar")
        .eq("firebaseuid", user_id)
        .execute()
    )
    if resp.data:
        new_balance = float(resp.data[0]["liquid_ellar"] or 0.0) + amount
        supabase_target.table("user_details").update(
            {"liquid_ellar": new_balance}
        ).eq("firebaseuid", user_id).execute()
    else:
        supabase_target.table("user_details").insert(
            {"firebaseuid": user_id, "liquid_ellar": amount}
        ).execute()


def _credit_frozen_ellar(supabase_target: Client, user_id: str, amount: float) -> None:
    if amount == 0.0:
        return
    resp = (
        supabase_target
        .table("user_details")
        .select("frozen_ellar")
        .eq("firebaseuid", user_id)
        .execute()
    )
    if resp.data:
        new_balance = float(resp.data[0]["frozen_ellar"] or 0.0) + amount
        supabase_target.table("user_details").update(
            {"frozen_ellar": new_balance}
        ).eq("firebaseuid", user_id).execute()
    else:
        supabase_target.table("user_details").insert(
            {"firebaseuid": user_id, "frozen_ellar": amount}
        ).execute()


def _check_trip_legitimacy(
    supabase_target: Client,
    existing: dict,
    hex_trip_id: list,
    hex_user_id: list,
    hex_k: list,
    ellar_user_hex: list,
    trip_index: int,
    h3_index: str,
) -> list:
    examined_trip_id = hex_trip_id[trip_index]
    examined_user    = hex_user_id[trip_index]
    n                = trip_index + 1
    k_trip           = hex_k[trip_index]

    if k_trip <= 0:
        return ellar_user_hex

    rds_in_trip: list[dict] = []
    for row in existing.values():
        nd_arr          = row.get("nd") or []
        rd_trip_ids_arr = row.get("rd_trip_ids") or []
        if not nd_arr or not rd_trip_ids_arr:
            continue
        if nd_arr[0] == examined_user and rd_trip_ids_arr[0] == examined_trip_id:
            rds_in_trip.append(row)

    if not rds_in_trip:
        return ellar_user_hex

    illegit_count = 0
    legit_count = 0
    for row in rds_in_trip:
        confirmed  = bool(row.get("confirmed", False))
        confidence = float(row.get("confidence") or 0.0)
        was_legit  = bool(row.get("legit", False))

        is_legit = confirmed or (confidence > 30.0)

        if is_legit:
            legit_count += 1
            if not was_legit and row.get("id") is not None:
                supabase_target.table("hexagons").update(
                    {"legit": True}
                ).eq("id", row["id"]).execute()
                row["legit"] = True

                if n <= 99:
                    late_reward = (
                        (4 - 2 * math.log10(n)) + (99 - n) / 10
                    ) / math.sqrt(k_trip)
                else:
                    late_reward = 1.0 / k_trip

                _credit_liquid_ellar(supabase_target, examined_user, late_reward)

                nd_val = len(row.get("nd") or [])
                ledger_late_legit_liquid(
                    supabase_target, examined_user, late_reward,
                    h3_index, row["id"], n, k_trip, nd_val,
                )
                print(
                    f"  [late-legit] trip_idx={trip_index} n={n} "
                    f"rd_id={row['id']} late_reward={late_reward:.4f} "
                    f"user={examined_user}"
                )
        else:
            illegit_count += 1
    I = illegit_count / k_trip
    legit_rD = legit_count
    if illegit_count == 0:
        return ellar_user_hex

    I = illegit_count / k_trip

    if n <= 99:
        penalty = ((4 - 2 * math.log10(n)) + (99 - n) / 10) * math.sqrt(k_trip) * I
    else:
        discovery_earning = ellar_user_hex[trip_index] if trip_index < len(ellar_user_hex) else 0.0
        penalty = 1.01 * discovery_earning * I

    current_eu = ellar_user_hex[trip_index] if trip_index < len(ellar_user_hex) else 0.0
    net_eu     = max(0.0, current_eu - penalty)
    ellar_user_hex[trip_index] = net_eu

    _credit_liquid_ellar(supabase_target, examined_user, net_eu)
    ledger_discovery_liquid(
        supabase_target, examined_user, net_eu,
        h3_index,
        None,
        n, k_trip,
        nd=len(rds_in_trip),
        I=I,
        legit_rD=legit_rD,
    )
    print(
        f"  [legit-check] trip_idx={trip_index} n={n} k={k_trip} "
        f"illegit={illegit_count} I={I:.3f} penalty={penalty:.4f} "
        f"net_eu={net_eu:.4f} user={examined_user}"
    )

    return ellar_user_hex


def update_hexagons(supabase_target: Client, new_events: list) -> None:
    if not new_events:
        return

    new_events_sorted = sorted(new_events, key=lambda e: e["start_time"])

    by_hex: dict[str, list] = {}
    for event in new_events_sorted:
        by_hex.setdefault(event["h3_index"], []).append(event)

    for h3_index, events in by_hex.items():
        _process_hex_incremental(supabase_target, h3_index, events)


def _process_hex_incremental(
    supabase_target: Client,
    h3_index: str,
    new_events: list,
) -> None:

    # Fetch rows from this hex AND its immediate ring-1 neighbors, so points
    # near a cell boundary can still be matched against nearby points that
    # happen to fall in an adjacent H3 cell (avoids false "new discovery"
    # splits purely due to grid-cell edges).
    neighbor_cells = list(h3lib.grid_disk(h3_index, 1))

    hexagons_response = (
        supabase_target
        .table("hexagons")
        .select(
            "id, h3_index, location, nd_count, user_id, trip_id, k, ellar_hex, ellar_user, "
            "nd, event_id, parameters, confirmed, rd_trip_ids, confidence, legit"
        )
        .in_("h3_index", neighbor_cells)
        .execute()
    )

    # existing_same_hex: rows belonging ONLY to h3_index — this is the set whose
    # trip/user/ellar summary arrays (hex_user_id, hex_trip_id, hex_k, ellar_user_hex)
    # and DB writes (h3_index column) are authoritative for this hex.
    # existing: ALL rows (same hex + neighbors) — used only for proximity matching.
    existing: dict[str, dict] = {}
    existing_same_hex: dict[str, dict] = {}
    for row in hexagons_response.data:
        loc = row["location"]
        key = f"{float(loc[0]):.6f},{float(loc[1]):.6f}"
        existing[key] = row
        if row["h3_index"] == h3_index:
            existing_same_hex[key] = row

    if existing_same_hex:
        sample_row     = next(iter(existing_same_hex.values()))
        old_trip_ids   = sample_row["trip_id"]        or []
        old_user_ids   = sample_row["user_id"]        or []
        old_k          = sample_row["k"]              or []
        old_ellar_user = sample_row.get("ellar_user") or []
        ell_hex        = float(sample_row.get("ellar_hex") or 0.0)
    else:
        old_trip_ids   = []
        old_user_ids   = []
        old_k          = []
        old_ellar_user = []
        ell_hex        = 0.0

    trip_summary: dict[str, dict] = {}
    for i, (tid, uid, k_val) in enumerate(zip(old_trip_ids, old_user_ids, old_k)):
        eu = float(old_ellar_user[i]) if i < len(old_ellar_user) else 0.0
        trip_summary[tid] = {
            "userid":     uid,
            "min_ts":     None,
            "k":          k_val,
            "ellar_user": eu,
        }

    for event in new_events:
        tid = event["session_id"]
        ts  = event["start_time"]
        if tid not in trip_summary:
            trip_summary[tid] = {
                "userid":     event["user_id"],
                "min_ts":     ts,
                "k":          1,
                "ellar_user": 0.0,
            }
        else:
            trip_summary[tid]["k"] += 1
            cur_ts = trip_summary[tid]["min_ts"]
            if cur_ts is None or ts < cur_ts:
                trip_summary[tid]["min_ts"] = ts

    existing_trips = [(tid, info) for tid, info in trip_summary.items() if info["min_ts"] is None]
    new_trips      = sorted(
        [(tid, info) for tid, info in trip_summary.items() if info["min_ts"] is not None],
        key=lambda x: x[1]["min_ts"],
    )
    sorted_trips = existing_trips + new_trips

    hex_user_id    = [info["userid"]      for _, info in sorted_trips]
    hex_trip_id    = [tid                 for tid, _   in sorted_trips]
    hex_k          = [info["k"]           for _, info  in sorted_trips]
    ellar_user_hex = [info["ellar_user"]  for _, info  in sorted_trips]

    trip_index_map: dict[str, int] = {tid: i for i, tid in enumerate(hex_trip_id)}

    og       = 0
    ell_user = 0.0

    seen_event_ids: set = set()
    for row in existing_same_hex.values():
        for stored_eid in (row.get("event_id") or []):
            seen_event_ids.add(stored_eid)

    for event in new_events:
        path = event.get("path") or []
        uid  = event["user_id"]
        eid  = event["id"]
        tid  = event["session_id"]

        if eid in seen_event_ids:
            continue
        seen_event_ids.add(eid)

        for coord in path:
            lat, lon   = float(coord[0]), float(coord[1])
            nearby_key = _find_nearby_key(coord, existing)

            if nearby_key is not None:
                row = existing[nearby_key]

                if tid in (row.get("rd_trip_ids") or []):
                    continue

                old_loc   = row["location"]
                old_count = int(row.get("nd_count") or len(row.get("nd") or []))

                new_loc, new_count = _weighted_centroid(
                    float(old_loc[0]), float(old_loc[1]), old_count,
                    lat, lon,
                )
                new_key = f"{new_loc[0]:.6f},{new_loc[1]:.6f}"

                nd_array          = (row["nd"]          or []) + [uid]
                rd_trip_ids_array = (row["rd_trip_ids"] or []) + [tid]
                eid_array         = (row["event_id"]    or []) + [eid]
                param_array       = (row["parameters"]  or []) + [event["parameter"]]

                confirmed = len(nd_array) > 1

                # Geometry/membership fields are always safe to update — they
                # describe this specific point regardless of which hex it's in.
                update_payload = {
                    "location":          new_loc,
                    "nd_count":          new_count,
                    "nd":                nd_array,
                    "rd_trip_ids":       rd_trip_ids_array,
                    "event_id":          eid_array,
                    "parameters":        param_array,
                    "confirmed":         confirmed,
                    "last_confirmed_at": event["start_time"],
                }

                # Only stamp hex-level summary arrays (user_id/trip_id/k) if
                # this row's TRUE h3_index matches the hex currently being
                # processed. A row pulled in from a neighbor cell (matched via
                # the proximity check, not because it actually lives in this
                # hex) must keep its own hex's summary arrays untouched —
                # otherwise this hex's trip history overwrites the neighbor
                # hex's trip history on a row it doesn't actually own.
                same_hex = row["h3_index"] == h3_index
                if same_hex:
                    update_payload["user_id"] = hex_user_id
                    update_payload["trip_id"] = hex_trip_id
                    update_payload["k"]       = hex_k

                supabase_target.table("hexagons").update(update_payload).eq("id", row["id"]).execute()

                updated_row = {
                    **row,
                    "location":    new_loc,
                    "nd_count":    new_count,
                    "nd":          nd_array,
                    "rd_trip_ids": rd_trip_ids_array,
                    "event_id":    eid_array,
                    "parameters":  param_array,
                    "confirmed":   confirmed,
                }
                if same_hex:
                    updated_row["user_id"] = hex_user_id
                    updated_row["trip_id"] = hex_trip_id
                    updated_row["k"]       = hex_k

                if new_key != nearby_key:
                    del existing[nearby_key]
                existing[new_key] = updated_row
                if same_hex:
                    if nearby_key in existing_same_hex and new_key != nearby_key:
                        del existing_same_hex[nearby_key]
                    existing_same_hex[new_key] = updated_row

                og_discoverer = (row["nd"] or [None])[0]
                if uid != og_discoverer:
                    nD = len(nd_array)
                    if nD <= 95:
                        conf_reward = (0.4 - 0.2 * math.log10(nD))
                        ell_user += conf_reward

                        ledger_confirmation_liquid(
                            supabase_target, uid, conf_reward,
                            h3_index, row["id"], nD,
                        )

            else:
                og += 1
                new_row = {
                    "h3_index":    h3_index,
                    "location":    [lat, lon],
                    "nd_count":    1,
                    "user_id":     hex_user_id,
                    "trip_id":     hex_trip_id,
                    "k":           hex_k,
                    "nd":          [uid],
                    "rd_trip_ids": [tid],
                    "event_id":    [eid],
                    "parameters":  [event["parameter"]],
                    "confirmed":   False,
                    "legit":       False,
                }
                insert_resp = supabase_target.table("hexagons").insert(new_row).execute()

                new_key = f"{lat:.6f},{lon:.6f}"
                cached  = insert_resp.data[0] if insert_resp.data else {**new_row, "id": None}
                existing[new_key] = cached
                existing_same_hex[new_key] = cached

    tid = new_events[-1]["session_id"]
    N   = trip_index_map.get(tid, len(hex_trip_id) - 1) + 1

    rD = len(existing_same_hex)

    if N <= 99:
        og_reward = (4 - 2 * math.log10(N)) * math.sqrt(og)
    else:
        value_rD  = ell_hex / rD if rD > 0 else 0.0
        og_reward = value_rD * og

    cur_trip_idx = trip_index_map.get(tid)
    if cur_trip_idx is not None:
        ellar_user_hex[cur_trip_idx] += og_reward

    ell_hex += og_reward

    user_id = new_events[-1]["user_id"]

    _credit_frozen_ellar(supabase_target, user_id, og_reward)

    if og_reward > 0.0:
        cur_trip_n = trip_index_map.get(tid, len(hex_trip_id) - 1) + 1
        cur_k      = hex_k[trip_index_map[tid]] if tid in trip_index_map else og

        new_rd_ids = [
            row.get("id") for row in existing_same_hex.values()
            if (row.get("nd") or [None])[0] == user_id
            and (row.get("rd_trip_ids") or [None])[0] == tid
        ]

        per_rd_reward = og_reward / max(len(new_rd_ids), 1)
        for rd_id in new_rd_ids:
            ledger_discovery_frozen(
                supabase_target, user_id, per_rd_reward,
                h3_index, rd_id, cur_trip_n, cur_k,
            )

    total_trips = len(hex_trip_id)
    if total_trips > 20:
        legit_trip_index = total_trips - 21
        ellar_user_hex = _check_trip_legitimacy(
            supabase_target,
            existing_same_hex,
            hex_trip_id,
            hex_user_id,
            hex_k,
            ellar_user_hex,
            legit_trip_index,
            h3_index,
        )

    N_total        = len(hex_trip_id)
    all_keys       = set(existing_same_hex.keys())
    confidence_map = _compute_confidence(existing_same_hex, N_total, all_keys)

    for key, row in existing_same_hex.items():
        row_id = row.get("id")
        if row_id is None:
            continue
        supabase_target.table("hexagons").update({
            "ellar_hex":  ell_hex,
            "ellar_user": ellar_user_hex,
            "confidence": confidence_map.get(key, 0.0),
            "user_id":    hex_user_id,
            "trip_id":    hex_trip_id,
            "k":          hex_k,
        }).eq("id", row_id).execute()

    _credit_liquid_ellar(supabase_target, user_id, ell_user)

    print(
        f"[hexagons] h3={h3_index} | trips={len(sorted_trips)} | "
        f"new_events={len(new_events)} | og={og} | rD={rD} | "
        f"og_reward={og_reward:.4f} | ell_user(conf)={ell_user:.4f} | "
        f"ell_hex={ell_hex:.4f}"
    )