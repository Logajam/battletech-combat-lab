"""
INTEGRATION__weapon_rules.py  (NEW 2026-10-19, Claude - Pile 2)

Per-weapon special rules from the Core Rulebook weapon entries, keyed off
the weapon's .mtf name (the same name-matching approach as
damage_resolution.is_jump_jet). Shared by expected damage
(INTEGRATION__expected_damage), weapon selection and Ranged Combat
(INTEGRATION__attack_resolution), so all three agree.

Cluster weapons (pp.87, 181 "C: Cluster"): a hit rolls on the Cluster Hits
Table, and the damage that lands is split into groupings, each its own
hit-location roll - SRM C2, LRM and MRM C5, ATM C6, anything else 5 (p.87
default). Leftover damage is a last, smaller grouping.
  - Streak SRM / LRM (p.187): on a hit the Cluster result is automatically
    12 (every missile hits; no roll); on a miss the launcher doesn't fire -
    no heat (and no ammo).
  - MRM (p.186): Cluster Hits Table rolls -1.
"""

DEFAULT_GROUPING = 5        # p.87
GROUPING_BY_FAMILY = (      # (name fragment, grouping size), first match wins - p.181
    ("ATM", 6),
    ("SRM", 2),
    ("LRM", 5),
    ("MRM", 5),
)
CLUSTER_MODIFIER_BY_FAMILY = (("MRM", -1),)   # p.186


def _norm(weapon):
    return (weapon.name or "").replace(" ", "").replace("-", "").upper()


def is_cluster(weapon):
    """Rolls on the Cluster Hits Table: a missile weapon with a rack size
    (equipment.json - the same test the project has always used)."""
    return weapon.damage_type == "Missile" and weapon.rack_size is not None


def is_streak(weapon):
    return "STREAK" in _norm(weapon)


def grouping_size(weapon):
    n = _norm(weapon)
    return next((size for fragment, size in GROUPING_BY_FAMILY if fragment in n), DEFAULT_GROUPING)


def cluster_roll_modifier(weapon):
    n = _norm(weapon)
    return sum(mod for fragment, mod in CLUSTER_MODIFIER_BY_FAMILY if fragment in n)


def damage_groupings(weapon, total_damage):
    """Split a cluster hit's damage into groupings (p.87): full groups of the
    weapon's grouping size, leftover last."""
    size = grouping_size(weapon)
    groups = [size] * int(total_damage // size)
    leftover = total_damage - size * len(groups)
    if leftover > 0:
        groups.append(leftover)
    return groups
