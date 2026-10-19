"""
INTEGRATION__expected_damage.py

Turns a MECHSIM Equipment weapon instance (see equipment.py's Part A fields -
category/weapon_range/damage_per_shot/heat/rack_size, populated by
mtf_parser.build_crit_list() at parse time) into an expected-damage-per-hit
number Pathfinder's scoring can use, per Daniel's confirmed formula
(2026-08-05):

    expected damage = P(hit) x E[damage | hit]

P(hit) is Pathfinder's job (PATHFINDER__combat.py already has hit_probability()
and the TN math). This file only produces E[damage | hit] - the "how much
damage lands, given the shot connects" half.

=== CLUSTER MATH (Daniel, 2026-08-05) ===
"In theory this means adding the expected damage of each roll of the cluster
table and finding the average damage. In reality, it means a look up table
since once you figure out the average damage it stays the same." That's
exactly what expected_cluster_hits() below does: a pure weighted-average
computation over MECHSIM__config.CLUSTER_HITS_TABLE, run once per (shots,
modifier) pair the first time it's needed, then memoized forever after -
never recomputed per shot, per turn, or per battle.

=== KNOWN GAP: which weapons actually use the cluster table (2026-08-05) ===
equipment.json does NOT reliably say whether a weapon resolves as one
guaranteed hit or via the Cluster Hits Table - that distinction only exists
today as a hand-maintained per-weapon-name flag in MECHSIM__config.ATTACK_TABLE
(fixture data for the single-mech test harness, not general).
Checked directly (2026-08-05) before writing this:
  - Missile weapons (damage_type == "Missile") are internally consistent:
    damage_per_shot = 1 (per missile), rack_size = missile count. E.g. LRM 5:
    damage_per_shot=1, rack_size=5. This case is trustworthy - treated as a
    real cluster weapon below, TABLE_COLUMN = rack_size.
  - Ballistic multi-shot weapons (LB-X autocannons, Ultra/Rotary AC
    double/triple-tap) are NOT trustworthy: e.g. every Ultra AC entry has
    damage_type = None (unconfirmed) and rack_size == damage_per_shot (mirrors
    the FULL shot damage, not a submunition count - "5" for a UAC-5 means "5
    damage per shot", not "5 submunitions"). There is no equipment.json field
    encoding the double-tap mechanic at all.
  - HELP(cluster_detection.ballistic_gap): because of the above, this module
    ONLY treats damage_type == "Missile" weapons as cluster weapons. LB-X and
    Ultra/Rotary AC weapons are treated as flat single-hit (damage_per_shot,
    guaranteed once hit) for now - a DELIBERATE simplification, not a silent
    bug. Revisit once equipment.json's Ballistic rows get real damage_type/
    shot-count data (same gap as HAG/Artemis/ammo, deferred 2026-08-05).
"""

import os
import sys

# MECHSIM's own files cross-import each other as plain unprefixed names
# (config.py does `from file_picker import ...`, etc. - that's how the
# original project is written, and it's not being changed here). So this
# can't just `import config` directly - PATHFINDER__config.py would collide
# with the same bare name once the integration project's directories share
# a process. MECHSIM_DIR below points at wherever the MECHSIM project's
# UNPREFIXED files live at runtime (the prefixes are a /mnt/project storage-
# only convention - see INTEGRATION__PROJECT_MAP.md). Adjust this path once
# the real integration directory layout exists; for now it defaults to a
# sibling "mechsim" folder next to this file.
MECHSIM_DIR = os.environ.get("MECHSIM_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mechsim"))
if MECHSIM_DIR not in sys.path:
    sys.path.insert(0, MECHSIM_DIR)

import config  # this is MECHSIM's config.py, resolved via MECHSIM_DIR above


# --- Standard 2d6 EXACT probability per sum (not cumulative - MECHSIM's
# hit_probability-style tables elsewhere are P(>=n); this needs P(==n) to
# weight each Cluster Hits Table row). Pure probability math, not a BT-
# specific number - same "no Daniel confirmation needed" reasoning
# PATHFINDER__combat.py used for its own cumulative table. ---
_2D6_EXACT = {
    2: 1 / 36, 3: 2 / 36, 4: 3 / 36, 5: 4 / 36, 6: 5 / 36,
    7: 6 / 36, 8: 5 / 36, 9: 4 / 36, 10: 3 / 36, 11: 2 / 36, 12: 1 / 36,
}

# Memoization cache for expected_cluster_hits() - keyed (shots, modifier).
# "Once you figure out the average damage it stays the same" (Daniel) - this
# dict is the lookup table that statement describes. Populated lazily the
# first time a given (shots, modifier) pair is asked for, then reused for
# the rest of the process's life - never recomputed.
_EXPECTED_CLUSTER_HITS_CACHE = {}


def expected_cluster_hits(shots, modifier=0):
    """Expected number of submunitions/shots that connect for a Cluster Hits
    Table column `shots` (TABLE_COLUMN - see config.py's HELP(attack_table.
    table_column)), given a CLUSTER_HIT_MODIFIER of `modifier` (0 for a plain
    weapon, nonzero for e.g. Artemis - not wired up yet, but the parameter is
    here so it doesn't need retrofitting later).

    Weighted average over every real 2d6 roll (2-12), each mapped through the
    same clamp resolve_weapon_attack()/cluster_hits_count() apply to an actual
    roll: modified_roll = max(2, min(12, roll + modifier)). Computed once per
    (shots, modifier) pair, cached after that - see module docstring.
    """
    key = (shots, modifier)
    cached = _EXPECTED_CLUSTER_HITS_CACHE.get(key)
    if cached is not None:
        return cached

    total = 0.0
    for roll, p in _2D6_EXACT.items():
        modified_roll = max(2, min(12, roll + modifier))
        row = config.CLUSTER_HITS_TABLE[modified_roll]
        if shots not in row:
            raise ValueError(
                f"No Cluster Hits Table column for {shots} shots - table only covers "
                f"{sorted(row)} shot-columns. Extend config.CLUSTER_HITS_TABLE rather than guessing."
            )
        total += p * row[shots]

    _EXPECTED_CLUSTER_HITS_CACHE[key] = total
    return total


def expected_damage_per_hit(weapon, cluster_hit_modifier=0):
    """E[damage | hit] for one MECHSIM Equipment weapon instance (must have
    category == "weapon" and damage_per_shot populated - raises if not,
    rather than silently returning 0, since a caller asking for this on a
    non-weapon or unconfirmed-data weapon is a real bug to surface, not
    something to paper over).

    Non-cluster (everything except confirmed Missile weapons - see module
    docstring's KNOWN GAP note): flat damage_per_shot, guaranteed once hit.

    Cluster (damage_type == "Missile", rack_size present): damage_per_shot
    (per-submunition damage) x expected_cluster_hits(rack_size, modifier).
    """
    if weapon.category != "weapon":
        raise ValueError(f"expected_damage_per_hit() called on a non-weapon: {weapon.name!r}")
    if weapon.damage_per_shot is None:
        raise ValueError(
            f"{weapon.name!r} has no confirmed damage_per_shot in equipment.json - "
            f"can't compute expected damage. Fix the data rather than guessing here."
        )

    is_cluster = weapon.damage_type == "Missile" and weapon.rack_size is not None
    if not is_cluster:
        return weapon.damage_per_shot

    return weapon.damage_per_shot * expected_cluster_hits(weapon.rack_size, cluster_hit_modifier)
