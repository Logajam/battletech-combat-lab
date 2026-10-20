"""
INTEGRATION__structure_weight.py  (NEW 2026-10-19, Claude - Pile 4 helper)

Daniel, 2026-10-19: damage that reaches INTERNAL STRUCTURE should count for
more than damage that only strips armor. "Take damage per weapon and multiply
it by the hit location table. Any location where its raw damage is greater
than its raw armor receives bonus expected damage based on the internal
structure potentially destroyed. And we keep it per weapon to avoid markov
chaining the program into the ground."

For one weapon hit (or one cluster group - p.87 groupings) of damage D landing
on a location with `armor` armor and `structure` structure left:

    armor part      = min(D, armor)                      counts 1.0 per point
    structure part  = min(D - armor part, structure)     counts k   per point
    rest            = D - armor part - structure part    counts 1.0 per point
                      (the location is gone; the rest transfers inward, and
                       what it does there is not chased - no chaining)
    worth(D, loc)   = armor part + k * structure part + rest

A weapon's multiplier against a target on an attack side is

    multiplier = sum over the weapon's groups, over the side's hit-table rolls,
                 P(roll) * worth(D, location) / sum of the groups' D

so (expected damage x multiplier) is its worth. k is
config.MOVEMENT_STRUCTURE_WEIGHT (1.0 = off: every multiplier is 1.0).
Locations come from the same table walk the exposure weighting uses
(`hit_spread`): rear hits use rear armor on torsos, a destroyed location
transfers inward (a shot that transfers off the mech counts as 1.0 flat).
The damage a weapon deals in a cluster is the EXPECTED damage per hit, split
into groupings of the weapon's size - expected, not every roll of the cluster
table (the same shortcut expected_damage uses).

Not modeled: an aimed shot at an immobile target (its location is chosen, not
rolled), critical-hit chances from structure damage (the extra worth is a flat
k), and where damage goes after a transfer.
"""

import os
import sys

MECHSIM_DIR = os.environ.get("MECHSIM_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mechsim"))
if MECHSIM_DIR not in sys.path:
    sys.path.insert(0, MECHSIM_DIR)

import INTEGRATION__config as config  # noqa: E402 - registers bare "config" before any MECHSIM import
import INTEGRATION__expected_damage as expected_damage  # noqa: E402
import INTEGRATION__weapon_rules as weapon_rules  # noqa: E402
from damage_resolution import TRANSFER_MAP  # noqa: E402
import hit_location  # noqa: E402

_P_2D6 = {roll: (6 - abs(roll - 7)) / 36 for roll in range(2, 13)}


def hit_spread(mech, side, rolls=None):
    """[(probability, location state dict, armor key)] for a shot on `side`
    of `mech` ('front'/'left'/'right'/'rear') from its CURRENT state. A hit on
    a destroyed location moves inward (TRANSFER_MAP); one that leaves the mech
    is dropped (its probability is simply missing from the list).
    rolls (2026-10-20): [(probability, location name)] of another table -
    the punch / kick tables (INTEGRATION__physical.table_rolls) - instead of
    the standard 2D6 table."""
    if rolls is None:
        if side == "left":
            table = hit_location.HIT_TABLE_LEFT_SIDE
        elif side == "right":
            table = hit_location.HIT_TABLE_RIGHT_SIDE
        else:
            table = hit_location.HIT_TABLE_FRONT_REAR
        # resolve_hit_location also translates quad leg names; its tripod leg
        # sub-roll draws Python's random, which a lookahead must not touch, so
        # a tripod reads the raw table (its Left/Right Leg rows).
        rolls = [(p, table[roll] if mech.mech_type == "tripod" else hit_location.resolve_hit_location(roll, mech, side))
                 for roll, p in _P_2D6.items()]
    spread = []
    for p, loc in rolls:
        while loc is not None and mech.locations.get(loc, {}).get("destroyed"):
            loc = TRANSFER_MAP.get(loc)
        state = mech.locations.get(loc) if loc is not None else None
        if state is None:
            continue
        armor_key = "rear_armor" if side == "rear" and "rear_armor" in state else "armor"
        spread.append((p, state, armor_key))
    return spread


def vulnerability(spread):
    """sum of P(roll) / durability(location) over a hit_spread (see
    INTEGRATION__movement_selection's exposure weighting)."""
    return sum(p / max(1, state[armor_key] + state["structure"]) for p, state, armor_key in spread)


def spread_worth(spread, damage, k):
    """Expected worth of one hit of `damage` rolled on `spread` (a roll that
    leaves the mech counts flat)."""
    covered = sum(p for p, _, _ in spread)
    return damage * (1.0 - covered) + sum(p * worth(damage, state[armor_key], state["structure"], k)
                                          for p, state, armor_key in spread)


def worth(damage, armor, structure, k):
    """Worth of `damage` landing on a location with this armor / structure."""
    armor_part = min(damage, armor)
    structure_part = min(damage - armor_part, structure)
    rest = damage - armor_part - structure_part
    return armor_part + k * structure_part + rest


def weapon_groups(weapon):
    """Damage amounts of the separate location rolls one hit of `weapon`
    makes: a single hit, or the cluster's expected damage split into its
    groupings."""
    total = expected_damage.expected_damage_per_hit(weapon)
    if not weapon_rules.is_cluster(weapon):
        return [total]
    return weapon_rules.damage_groupings(weapon, total)


def multipliers(attacker_weapons, target, side):
    """{id(weapon): multiplier} of `attacker_weapons` fired at `target`'s
    `side`. Weapons with no confirmed damage are left out (they never fire)."""
    k = config.MOVEMENT_STRUCTURE_WEIGHT
    spread = hit_spread(target, side)
    result = {}
    for w in attacker_weapons:
        if w.damage_per_shot is None:
            continue
        groups = weapon_groups(w)
        raw = sum(groups)
        if raw <= 0:
            result[id(w)] = 1.0
            continue
        # a roll whose hit leaves the mech was dropped from the spread: it counts flat
        result[id(w)] = sum(spread_worth(spread, d, k) for d in groups) / raw
    return result
