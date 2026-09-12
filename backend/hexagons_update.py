import math
import h3 as h3lib
from supabase import Client
from ledger import (
    ledger_discovery_frozen,
    ledger_confirmation_liquid,
    ledger_confirmation_unfreeze,
    ledger_illegit_penalty,
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
) -> tuple[tuple[float, float], int]:
    n = old_count + 1
    lat = (old_lat * old_count + new_lat) / n
    lon = (old_lon * old_count + new_lon) / n
    return (lat, lon), n


PROXIMITY_THRESHOLD_M = 15  # metres


def _find_nearby_key(coord: list, existing: dict) -> str | None:
    lat, lon = float(coord[0]), float(coord[1])
    for key, row in existing.items():
        elat, elon = float(row["lat"]), float(row["lon"])
        if _haversine_m(lat, lon, elat, elon) < PROXIMITY_THRESHOLD_M:
            return key
    return None


def _compute_confidence(existing: dict, N: int, target_keys: set[str]) -> dict[str, float]:
    # Unchanged from the previous implementation — the design doc treats
    # "confidence" as a given input (used only in the confirmed-or-confidence
    # >= 30 legitimacy test) and doesn't specify how it's computed, so this
    # is left untouched.
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
    # Also used for debits — pass a negative amount.
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
    # Also used for debits — pass a negative amount.
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


def _get_session_multiplier(supabase_target: Client, session_id: str, default: float) -> float:
    """
    Design doc requires that when unfreezing a discoverer's escrow (on first
    confirmation) or penalizing them (illegitimacy check), the multiplier used
    is the ORIGINAL discovering trip's own imu_only status — not the
    multiplier of whatever trip is currently being processed.

    Looks this up against the `sessions` table (session_id / imu_only
    columns, per main.py). Falls back to `default` (the current trip's
    multiplier) if the lookup fails, so nothing hard-crashes.
    """
    try:
        resp = (
            supabase_target
            .table("sessions")
            .select("imu_only")
            .eq("session_id", session_id)
            .execute()
        )
        if resp.data:
            return 0.5 if resp.data[0].get("imu_only") else 1.0
    except Exception as err:
        print(f"  [session-lookup] failed for session_id={session_id}: {err}")
    return default


def update_hexagons(supabase_target: Client, new_events: list, imu_only: bool = False) -> None:
    if not new_events:
        return

    new_events_sorted = sorted(new_events, key=lambda e: e["start_time"])

    by_hex: dict[str, list] = {}
    for event in new_events_sorted:
        by_hex.setdefault(event["h3_index"], []).append(event)

    for h3_index, events in by_hex.items():
        _process_hex_incremental(supabase_target, h3_index, events, imu_only)


def _process_hex_incremental(
    supabase_target: Client,
    h3_index: str,
    new_events: list,
    imu_only: bool = False,
) -> None:
    reward_multiplier = 0.5 if imu_only else 1.0

    # Fetch rows from this hex AND its immediate ring-1 neighbors, so points
    # near a cell boundary can still be matched against nearby points that
    # happen to fall in an adjacent H3 cell.
    neighbor_cells = list(h3lib.grid_disk(h3_index, 1))

    hexagons_response = (
        supabase_target
        .table("hexagons")
        .select(
            "id, h3_index, lat, lon, nd_count, user_id, trip_id, k, "
            "frozen_ellar_hex, liquid_ellar_hex, ellar_user, "
            "nd, event_id, parameters, confirmed, rd_trip_ids, confidence, legit"
        )
        .in_("h3_index", neighbor_cells)
        .execute()
    )

    existing: dict[str, dict] = {}
    existing_same_hex: dict[str, dict] = {}
    for row in hexagons_response.data:
        key = f"{float(row['lat']):.6f},{float(row['lon']):.6f}"
        existing[key] = row
        if row["h3_index"] == h3_index:
            existing_same_hex[key] = row

    if existing_same_hex:
        sample_row       = next(iter(existing_same_hex.values()))
        old_trip_ids     = sample_row["trip_id"]        or []
        old_user_ids     = sample_row["user_id"]        or []
        old_k            = sample_row["k"]              or []
        old_ellar_user   = sample_row.get("ellar_user") or []
        frozen_ellar_hex = float(sample_row.get("frozen_ellar_hex") or 0.0)
        liquid_ellar_hex = float(sample_row.get("liquid_ellar_hex") or 0.0)
    else:
        old_trip_ids     = []
        old_user_ids     = []
        old_k            = []
        old_ellar_user   = []
        frozen_ellar_hex = 0.0
        liquid_ellar_hex = 0.0

    trip_summary: dict[str, dict] = {}
    for i, (tid, uid, k_val) in enumerate(zip(old_trip_ids, old_user_ids, old_k)):
        eu = float(old_ellar_user[i]) if i < len(old_ellar_user) else 0.0
        trip_summary[tid] = {"userid": uid, "min_ts": None, "k": k_val, "ellar_user": eu}

    for event in new_events:
        tid = event["session_id"]
        ts  = event["start_time"]
        if tid not in trip_summary:
            trip_summary[tid] = {"userid": event["user_id"], "min_ts": ts, "k": 1, "ellar_user": 0.0}
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

    hex_user_id    = [info["userid"]     for _, info in sorted_trips]
    hex_trip_id    = [tid                for tid, _   in sorted_trips]
    hex_k          = [info["k"]          for _, info  in sorted_trips]
    ellar_user_hex = [info["ellar_user"] for _, info  in sorted_trips]

    trip_index_map: dict[str, int] = {tid: i for i, tid in enumerate(hex_trip_id)}

    # rD = current count of unique road defects in this hexagon. Kept live as
    # we insert new ones below (used by the N>99 discovery-reward branch).
    rD_running = len(existing_same_hex)

    # Per-user balance deltas, applied once at the end.
    frozen_delta: dict[str, float] = {}
    liquid_delta: dict[str, float] = {}

    def _bump_frozen(uid: str, amount: float) -> None:
        if amount:
            frozen_delta[uid] = frozen_delta.get(uid, 0.0) + amount

    def _bump_liquid(uid: str, amount: float) -> None:
        if amount:
            liquid_delta[uid] = liquid_delta.get(uid, 0.0) + amount

    seen_event_ids: set = set()
    for row in existing_same_hex.values():
        for stored_eid in (row.get("event_id") or []):
            seen_event_ids.add(stored_eid)

    discovery_count    = 0
    confirmation_count = 0

    for event in new_events:
        path = event.get("path") or []
        uid  = event["user_id"]
        eid  = event["id"]
        tid  = event["session_id"]

        if eid in seen_event_ids:
            continue
        seen_event_ids.add(eid)

        trip_idx = trip_index_map.get(tid)
        N = (trip_idx + 1) if trip_idx is not None else len(hex_trip_id)
        cur_k = hex_k[trip_idx] if trip_idx is not None else 1

        for coord in path:
            lat, lon   = float(coord[0]), float(coord[1])
            nearby_key = _find_nearby_key(coord, existing)

            if nearby_key is not None:
                # --------------------------------------------------------
                # Confirmation of an existing road defect
                # --------------------------------------------------------
                row = existing[nearby_key]

                if tid in (row.get("rd_trip_ids") or []):
                    continue  # already recorded this trip against this RD

                old_lat, old_lon = float(row["lat"]), float(row["lon"])
                old_count = int(row.get("nd_count") or len(row.get("nd") or []))
                (new_lat, new_lon), new_count = _weighted_centroid(
                    old_lat, old_lon, old_count, lat, lon,
                )
                new_key = f"{new_lat:.6f},{new_lon:.6f}"

                prior_nd         = row.get("nd") or []
                discoverer_uid   = prior_nd[0] if prior_nd else None
                discoverer_trip  = (row.get("rd_trip_ids") or [None])[0]
                # Unique users who've confirmed before (excludes the
                # discoverer's own original flag).
                prior_confirmers = set(prior_nd[1:])
                was_legit_before = bool(row.get("legit", False))

                nd_array          = prior_nd + [uid]
                rd_trip_ids_array = (row["rd_trip_ids"] or []) + [tid]
                eid_array         = (row["event_id"]    or []) + [eid]
                param_array       = (row["parameters"]  or []) + [event["parameter"]]

                # Anyone re-encountering an existing RD marks it confirmed —
                # discoverer or stranger. "legit" is reserved for a stranger.
                is_legit_now = was_legit_before

                is_discoverer   = (uid == discoverer_uid)
                already_flagged = uid in prior_confirmers
                eligible = (not is_discoverer) and (not already_flagged)

                if eligible:
                    confirmation_count += 1
                    nD = len(prior_confirmers) + 1
                    confirmation_reward = reward_multiplier * (2 - math.log10(nD))
                    _bump_liquid(uid, confirmation_reward)
                    liquid_ellar_hex += confirmation_reward
                    ledger_confirmation_liquid(
                        supabase_target, uid, confirmation_reward,
                        h3_index, row["id"], nD,
                    )

                    is_legit_now = True

                    if not was_legit_before and discoverer_uid is not None and discoverer_trip is not None:
                        disc_idx = trip_index_map.get(discoverer_trip)
                        if disc_idx is not None:
                            N_of_discoverer = disc_idx + 1
                            disc_multiplier = _get_session_multiplier(
                                supabase_target, discoverer_trip, default=reward_multiplier,
                            )
                            unfreeze_amt = disc_multiplier * (4 - 2 * math.log10(N_of_discoverer))
                            _bump_frozen(discoverer_uid, -unfreeze_amt)
                            _bump_liquid(discoverer_uid, unfreeze_amt)
                            # Moves the amount from the hex's frozen pool to
                            # its liquid pool — it's the same reward, just no
                            # longer escrowed.
                            frozen_ellar_hex -= unfreeze_amt
                            liquid_ellar_hex += unfreeze_amt
                            ledger_confirmation_unfreeze(
                                supabase_target, discoverer_uid, unfreeze_amt,
                                h3_index, row["id"], N_of_discoverer,
                            )
                        else:
                            print(
                                f"  [unfreeze] discoverer trip {discoverer_trip} not found in "
                                f"hex_trip_id for h3={h3_index}, rd_id={row['id']} — skipped"
                            )

                update_payload = {
                    "lat":               new_lat,
                    "lon":               new_lon,
                    "nd_count":          new_count,
                    "nd":                nd_array,
                    "rd_trip_ids":       rd_trip_ids_array,
                    "event_id":          eid_array,
                    "parameters":        param_array,
                    "confirmed":         True,
                    "legit":             is_legit_now,
                    "last_confirmed_at": event["start_time"],
                }

                same_hex = row["h3_index"] == h3_index
                if same_hex:
                    update_payload["user_id"] = hex_user_id
                    update_payload["trip_id"] = hex_trip_id
                    update_payload["k"]       = hex_k

                supabase_target.table("hexagons").update(update_payload).eq("id", row["id"]).execute()

                updated_row = {**row, **update_payload}
                if new_key != nearby_key:
                    del existing[nearby_key]
                existing[new_key] = updated_row
                if same_hex:
                    if nearby_key in existing_same_hex and new_key != nearby_key:
                        del existing_same_hex[nearby_key]
                    existing_same_hex[new_key] = updated_row

            else:
                # --------------------------------------------------------
                # Brand-new, unique road defect
                # --------------------------------------------------------
                discovery_count += 1

                if N <= 99:
                    discovery_reward = reward_multiplier * (4 - 2 * math.log10(N))
                else:
                    discovery_reward = (
                        reward_multiplier * (frozen_ellar_hex / rD_running) if rD_running > 0 else 0.0
                    )

                new_row = {
                    "h3_index":    h3_index,
                    "lat":         lat,
                    "lon":         lon,
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
                rD_running += 1

                _bump_frozen(uid, discovery_reward)
                frozen_ellar_hex += discovery_reward
                if trip_idx is not None:
                    ellar_user_hex[trip_idx] += discovery_reward

                ledger_discovery_frozen(
                    supabase_target, uid, discovery_reward,
                    h3_index, cached.get("id"), N, cur_k,
                )

    # Check whether the trip discovering 5 trips ago earned legitimacy for
    # what it found, before writing final balances.
    total_trips = len(hex_trip_id)
    if total_trips > 10:
        total_frozen_penalty = _check_illegit_defects(
            supabase_target,
            existing_same_hex,
            hex_trip_id,
            hex_user_id,
            h3_index,
            trip_index=total_trips - 11,
            frozen_delta=frozen_delta,
            reward_multiplier=reward_multiplier,
        )
        # Any frozen reward clawed back from a discoverer must also come
        # back out of this hexagon's frozen pool.
        frozen_ellar_hex -= total_frozen_penalty

    # --- Apply accumulated balance deltas ----------------------------------
    for uid, amount in frozen_delta.items():
        _credit_frozen_ellar(supabase_target, uid, amount)
    for uid, amount in liquid_delta.items():
        _credit_liquid_ellar(supabase_target, uid, amount)

    # --- Persist hex-level summary fields on every remaining row ----------
    N_total        = len(hex_trip_id)
    all_keys       = set(existing_same_hex.keys())
    confidence_map = _compute_confidence(existing_same_hex, N_total, all_keys)

    for key, row in existing_same_hex.items():
        row_id = row.get("id")
        if row_id is None:
            continue
        supabase_target.table("hexagons").update({
            "frozen_ellar_hex": frozen_ellar_hex,
            "liquid_ellar_hex": liquid_ellar_hex,
            "ellar_user":       ellar_user_hex,
            "confidence":       confidence_map.get(key, 0.0),
            "user_id":          hex_user_id,
            "trip_id":          hex_trip_id,
            "k":                hex_k,
        }).eq("id", row_id).execute()

    print(
        f"[hexagons] h3={h3_index} | trips={len(sorted_trips)} | "
        f"new_events={len(new_events)} | discoveries={discovery_count} | "
        f"confirmations={confirmation_count} | rD={rD_running} | "
        f"frozen_ellar_hex={frozen_ellar_hex:.4f} | liquid_ellar_hex={liquid_ellar_hex:.4f}"
    )


def _check_illegit_defects(
    supabase_target: Client,
    existing_same_hex: dict,
    hex_trip_id: list,
    hex_user_id: list,
    h3_index: str,
    trip_index: int,
    frozen_delta: dict,
    reward_multiplier: float,
) -> float:
    """
    10 trips after a given trip discovered road defects in this hex, check
    whether each of those defects earned legitimacy (confirmed==True, by
    discoverer or stranger, or confidence >= 30). Anything that didn't is
    discarded, and its discoverer is penalized: the original frozen discovery
    reward for that RD is removed entirely (no liquid-side penalty).

    Returns the total frozen amount clawed back across all discarded rDs, so
    the caller can also subtract it from the hexagon's running frozen pool.
    """
    if trip_index < 0 or trip_index >= len(hex_trip_id):
        return 0.0

    examined_trip_id = hex_trip_id[trip_index]
    examined_user     = hex_user_id[trip_index]
    N_of_discoverer   = trip_index + 1

    rds_in_trip: list[tuple[str, dict]] = []
    for key, row in existing_same_hex.items():
        rd_trip_ids_arr = row.get("rd_trip_ids") or []
        if rd_trip_ids_arr and rd_trip_ids_arr[0] == examined_trip_id:
            rds_in_trip.append((key, row))

    if not rds_in_trip:
        return 0.0

    disc_multiplier = _get_session_multiplier(
        supabase_target, examined_trip_id, default=reward_multiplier,
    )

    discard = []
    total_frozen_penalty = 0.0
    for key, row in rds_in_trip:
        confirmed  = bool(row.get("confirmed", False))
        confidence = float(row.get("confidence") or 0.0)

        if confirmed or confidence >= 30.0:
            continue  # legit enough — no action

        penalty_frozen = disc_multiplier * (4 - 2 * math.log10(N_of_discoverer))

        frozen_delta[examined_user] = frozen_delta.get(examined_user, 0.0) - penalty_frozen
        total_frozen_penalty += penalty_frozen

        ledger_illegit_penalty(
            supabase_target, examined_user, penalty_frozen,
            h3_index, row.get("id"), N_of_discoverer,
        )

        discard.append((key, row.get("id")))
        print(
            f"  [illegit] trip={examined_trip_id} n={N_of_discoverer} "
            f"rd_id={row.get('id')} frozen_penalty={penalty_frozen:.4f} "
            f"user={examined_user}"
        )

    for key, row_id in discard:
        if row_id is not None:
            try:
                supabase_target.table("hexagons").delete().eq("id", row_id).execute()
            except Exception as del_err:
                print(f"  [illegit] failed to discard rd_id={row_id}: {del_err}")
        existing_same_hex.pop(key, None)

    return total_frozen_penalty