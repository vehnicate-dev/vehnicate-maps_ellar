from supabase import Client


def _ledger_entry(
    supabase_target: Client,
    receiver_id: str,
    amount: float,
    ellar_type: str,
    comment: str,
    sender_id: str | None = None,
) -> None:
    """Insert one row into the ledger table. sender_id=None means system-issued."""
    if amount == 0.0:
        return
    supabase_target.table("ledger").insert({
        "sender_id":   sender_id,
        "receiver_id": receiver_id,
        "amount":      round(amount, 6),
        "type":        ellar_type,
        "comment":     comment,
    }).execute()


# ------------------------------------------------------------------
# Convenience wrappers used by hexagons_update.py
# ------------------------------------------------------------------

def ledger_discovery_frozen(
    supabase_target: Client,
    to_user_id: str,
    amount: float,
    h3_index: str,
    hex_row_id,          # hexagons.id of the newly inserted rD row
    n: int,               # generation index of the discovering trip
    k: int,               # number of rD flags this trip made
) -> None:
    """Discovery reward — frozen until legit check clears it."""
    comment = (
        f"Discovery reward (frozen) | hex={h3_index} | "
        f"hexagons.roaddefect_id={hex_row_id} | n={n} | k={k}"
    )
    _ledger_entry(supabase_target, to_user_id, amount, "frozen", comment)


# NOTE: no longer called by hexagons_update.py — kept for now since it's
# harmless, but nothing wires into it anymore now that the 5-trip
# "late reward" bonus mechanism has been replaced by instant
# unfreeze-on-first-confirmation (see ledger_confirmation_unfreeze below)
# and the illegitimacy penalty (see ledger_illegit_penalty below). Safe to
# delete if you don't want dead code sitting around — just say the word.
def ledger_discovery_liquid(
    supabase_target: Client,
    to_user_id: str,
    amount: float,
    h3_index: str,
    hex_row_id,
    n: int,
    k: int,
    nd: int,             # number of detections on this rD at time of legit check
    I: float,            # illegitimacy ratio for the trip
    legit_rD: int,       # number of rDs found legit out of k
) -> None:
    """
    Discovery reward unfrozen after legit check.
    Also covers the late-legitimacy top-up for a single rD.
    """
    comment = (
        f"Discovery reward (liquid, post-legit) | hex={h3_index} | "
        f"hexagons.roaddefect_id={hex_row_id} | n={n} | k={k} | nd={nd} | "
        f"I={I:.4f} | legit_rD/k={legit_rD}/{k}"
    )
    _ledger_entry(supabase_target, to_user_id, amount, "liquid", comment)


# NOTE: same as above — no longer called; the late-legitimacy top-up concept
# it backed doesn't exist in the current design. Kept for now, flag if you
# want it removed.
def ledger_late_legit_liquid(
    supabase_target: Client,
    to_user_id: str,
    amount: float,
    h3_index: str,
    hex_row_id,
    n: int,
    k: int,
    nd: int,
) -> None:
    """Late-legitimacy top-up for a single rD that flipped from illegit → legit."""
    comment = (
        f"Late-legitimacy reward (liquid) | hex={h3_index} | "
        f"hexagons.roaddefect_id={hex_row_id} | n={n} | k={k} | nd={nd}"
    )
    _ledger_entry(supabase_target, to_user_id, amount, "liquid", comment)


def ledger_confirmation_liquid(
    supabase_target: Client,
    to_user_id: str,
    amount: float,
    h3_index: str,
    hex_row_id,
    nd: int,
) -> None:
    """Confirmation reward — always immediately liquid."""
    comment = (
        f"Confirmation reward (liquid) | hex={h3_index} | "
        f"hexagons.roaddefect_id={hex_row_id} | nd={nd}"
    )
    _ledger_entry(supabase_target, to_user_id, amount, "liquid", comment)


def ledger_confirmation_unfreeze(
    supabase_target: Client,
    to_user_id: str,
    amount: float,
    h3_index: str,
    hex_row_id,
    n: int,               # generation index of the discoverer's own trip
) -> None:
    """
    Moves a discoverer's original discovery reward from frozen to liquid,
    triggered by the FIRST eligible confirmation of their road defect (i.e.
    the moment it becomes 'legit'). Writes two rows: a debit against frozen
    and a matching credit against liquid, so the ledger reflects the actual
    balance movement rather than a net figure.
    """
    comment = (
        f"Discovery reward unfrozen (first confirmation) | hex={h3_index} | "
        f"hexagons.roaddefect_id={hex_row_id} | n={n}"
    )
    _ledger_entry(supabase_target, to_user_id, -amount, "frozen", comment)
    _ledger_entry(supabase_target, to_user_id, amount, "liquid", comment)


def ledger_illegit_penalty(
    supabase_target: Client,
    from_user_id: str,
    penalty_frozen: float,
    h3_index: str,
    hex_row_id,
    n: int,               # generation index of the discoverer's own trip
) -> None:
    """
    Penalizes a discoverer whose road defect failed the 5-trip legitimacy
    check (never confirmed, confidence stayed below 30): the original frozen
    discovery reward for that defect is removed entirely. There is no
    liquid-side penalty — only the frozen reward is clawed back.
    """
    comment = (
        f"Illegitimate road defect penalty | hex={h3_index} | "
        f"hexagons.roaddefect_id={hex_row_id} | n={n}"
    )
    _ledger_entry(supabase_target, from_user_id, -penalty_frozen, "frozen", comment)