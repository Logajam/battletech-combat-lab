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


# =============================================================================
# Per-weapon to-hit modifiers (weapon entries, pp.183-190) - matched on the
# equipment.json canonical name, so .mtf alias spellings don't matter.
# =============================================================================
VSP_MODIFIER_BY_BRACKET = {"short": -3, "medium": -2, "long": -1}   # p.185


def canonical_name(weapon):
    """equipment.json canonical name for a weapon instance (cached on it)."""
    cached = getattr(weapon, "_canonical", None)
    if cached is None:
        from equipment import lookup_equipment
        entry = lookup_equipment(weapon.name or "")
        cached = (entry["canonical_name"] if entry else weapon.name or "").replace(" ", "").replace("-", "").upper()
        try:
            weapon._canonical = cached
        except AttributeError:
            pass
    return cached


def weapon_tn_modifier(weapon, bracket):
    """The weapon's own to-hit modifier (p.185 lasers, p.184 silver bullet
    Gauss, p.187 rocket launchers, p.189 M-pods)."""
    n = canonical_name(weapon)
    if "VSP" in n:
        return VSP_MODIFIER_BY_BRACKET.get(bracket, 0)
    if "XPULSE" in n:
        return -2
    if "PULSE" in n:
        return -1 if n.startswith(("CLER", "ISER", "ER")) else -2      # ER pulse -1, pulse -2
    if "HEAVY" in n and "LASER" in n:
        return 0 if "IMPROVED" in n else 1                             # heavy +1, improved heavy 0
    if "REENGINEERED" in n or "RELASER" in n:
        return -1
    if "SBGR" in n or "SILVERBULLET" in n:
        return -1
    if n.startswith("RL") or "ROCKETLAUNCHER" in n:
        return 1
    if "MPOD" in n:
        return -1
    return 0


def targeting_computer_eligible(weapon):
    """p.200: direct-fire ballistic/energy and pulse weapons, but not Cluster
    weapons, flamers or machine guns."""
    if is_cluster(weapon) or weapon.damage_type not in ("Energy", "Ballistic"):
        return False
    n = canonical_name(weapon)
    return not any(k in n for k in ("FLAMER", "MACHINEGUN", "MGA", "LIGHTMG", "HEAVYMG")) and not n.endswith("MG")


def is_pulse(weapon):
    return "PULSE" in canonical_name(weapon)


def is_ams(weapon):
    """Anti-Missile System or laser AMS (p.206) - a defensive system, never an
    attack (INTEGRATION__ams). APDS (Tactical Operations) is not Core."""
    return "ANTIMISSILESYSTEM" in canonical_name(weapon)
