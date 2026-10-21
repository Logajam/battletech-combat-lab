"""INTEGRATION__water.py - the water rules a 'Mech meets in a water hex
(NEW 2026-10-21, Claude; Daniel: water rules "Also Yes as the next task").

Water hexes (terrain_rules.prepare_board): a hex's "level" is its floor, the
surface level minus the depth (Core p.57: "a hex at Depth 2 ... is at Level
-2"; p.47: "the level is the water's surface, and the depth is always
independent of this"), so a 'Mech in water stands on the bottom - level
changes in and out of water (p.51), jump heights (p.50), LOS levels and fall
heights (p.115: falling into water adds the depth) all follow from that.
info["depth"] holds the depth. Depth 0 has no effect on 'Mechs (pp.51, 122).

A 'Mech's water state (p.127):
  GROUND     - not in water of depth 1+.
  PARTIAL    - standing in depth 1: legs submerged, partial cover (p.66).
  SUBMERGED  - standing in depth 2+, or prone in depth 1+: fully submerged.

What this module rules on (each function cites its page):
  - which weapons can fire, for the attacker's and target's states
    (Underwater Attacks Table and Combat in Water, pp.67, 127; attacks can't
    cross the water line, p.62; only energy weapons fire from a submerged
    location, p.127);
  - the underwater range bracket shift (+1 bracket, no long range, p.127);
  - the heat sink bonus (p.103: submerged sinks dissipate double, at most 6
    extra points);
  - jump jets (p.50: leg jets don't fire in depth 1, no jump at depth 2+);
  - falls (p.115: damage halved in depth 1+ water).
PSRs for running or jumping into water live in the orchestrator / movement
scoring (p.48, p.50), partial cover in pathfinder/los.py (p.66).

Not built here yet (RULES_REVIEW G6 part 2): hull breaches (p.127), physical
attacks in water (p.77), the life support / drowning hit (p.117), leg
weapons' kick-table hits between two partially submerged 'Mechs (p.67).

The battle's board is set once per battle (set_board, from
orchestrator.run_battle) so code that only has a mech - heat dissipation,
falls - can find its hex's depth, the way config holds the battle's RNG.
"""

from typing import Dict, FrozenSet, Optional

from damage_resolution import is_heat_sink, is_jump_jet, heat_sink_units
from mech_state import active_heat_sinks, heat_sink_rate, compute_jump_mp

GROUND, PARTIAL, SUBMERGED = "ground", "partial", "submerged"

# p.103: "No more than 6 additional heat points per turn can be dissipated due to water."
MAX_WATER_DISSIPATION = 6

# p.127 Underwater Ranges: an energy weapon firing underwater uses the next
# bracket up (short -> medium, medium -> long; long can't be made). In TN
# terms the Core bracket modifiers step by 2 (0 / +2 / +4, p.69).
UNDERWATER_BRACKET_TN = {"short": 2, "medium": 2}
CANT_FIRE_TN = 99      # a long-range underwater shot can't be made: no chance to hit

_BOARD: Optional[dict] = None


def set_board(terrain_map):
    """The battle's board (orchestrator.run_battle, once per battle)."""
    global _BOARD
    _BOARD = terrain_map


def depth_at(label, terrain_map=None) -> int:
    """Water depth of a hex (0 = dry or depth 0)."""
    board = terrain_map if terrain_map is not None else _BOARD
    if board is None or label is None:
        return 0
    info = board["hexes"].get(label)
    return info.get("depth", 0) if info else 0


def state_at(label, prone=False, terrain_map=None) -> str:
    """GROUND / PARTIAL / SUBMERGED for a 'Mech in `label` (p.127)."""
    d = depth_at(label, terrain_map)
    if d <= 0:
        return GROUND
    if prone or d >= 2:
        return SUBMERGED
    return PARTIAL


def state(mech, terrain_map=None) -> str:
    return state_at(mech.hex, mech.prone, terrain_map)


def submerged_locations(mech, water_state):
    """Locations under water: the legs in depth 1, everything when submerged."""
    if water_state == SUBMERGED:
        return set(mech.locations)
    if water_state == PARTIAL:
        return set(mech.leg_locations)
    return set()


# =============================================================================
# ==========================  RANGED ATTACKS  =================================
# =============================================================================
def blocked_weapon_ids(attacker, weapons, weapon_locs, a_state, t_state) -> Optional[FrozenSet[int]]:
    """ids of the attacker's weapons that can't fire at a target in t_state
    from a_state, or None when no attack can be made at all.
    weapon_locs: {id(weapon): set of locations} (attack_resolution.weapon_locations).

    Underwater Attacks Table (p.127) and Combat in Water (p.67):
      ground    -> ground: all            ground    -> partial: all (target has partial cover)
      ground    -> submerged: none (the water line, p.62)
      partial   -> ground: torso / arm / head weapons only
      partial   -> partial: all          partial   -> submerged: leg weapons only
      submerged -> submerged: all        submerged -> partial: all (legs only hit, no cover)
      submerged -> ground: none
    And p.127: only energy weapons fire from a submerged location."""
    if a_state == GROUND and t_state == GROUND:
        return frozenset()
    if (a_state == GROUND and t_state == SUBMERGED) or (a_state == SUBMERGED and t_state == GROUND):
        return None
    legs = set(attacker.leg_locations)
    under = submerged_locations(attacker, a_state)
    blocked = set()
    for w in weapons:
        locs = weapon_locs.get(id(w), set())
        in_leg = bool(locs & legs)
        if a_state == PARTIAL and t_state == GROUND and in_leg:
            blocked.add(id(w))
        elif a_state == PARTIAL and t_state == SUBMERGED and not in_leg:
            blocked.add(id(w))
        elif locs & under and w.damage_type != "Energy":
            blocked.add(id(w))
    return frozenset(blocked)


def range_adjuster(attacker, weapon_locs, a_state, base_adjust):
    """Wraps an attack_resolution.tn_adjuster for the underwater range
    shift (p.127): an energy weapon in a submerged location fires one
    bracket longer - +2 TN at short and medium, no shot at long. Minimum
    range is unchanged. Returns base_adjust itself when nothing is submerged.
    Not shifted: variable-damage weapons' damage bracket (Core: "applying all
    rules aspects relevant to this new bracket") - none of the weapons that
    vary damage by bracket fires underwater in the test units."""
    under = submerged_locations(attacker, a_state)
    if not under:
        return base_adjust
    submerged_ids = {wid for wid, locs in weapon_locs.items() if locs & under}

    def adjust(weapon, bracket, plan=None):
        tn = base_adjust(weapon, bracket, plan)
        if id(weapon) in submerged_ids and bracket is not None:
            tn += UNDERWATER_BRACKET_TN.get(bracket, CANT_FIRE_TN)
        return tn
    return adjust


# =============================================================================
# ==========================  HEAT, JUMP JETS, FALLS  =========================
# =============================================================================
def _working(mech, location, test):
    """Equipment instances in `location` passing `test`, not destroyed."""
    seen = {}
    for slot in mech.crits.get(location, []):
        if hasattr(slot, "name") and test(slot):
            seen[id(slot)] = slot
    return [s for s in seen.values()]


def dissipation_bonus(mech, water_state=None) -> int:
    """Extra heat dissipated by submerged heat sinks (p.103): each submerged
    sink dissipates twice (a single sink 1 more, a double 2 more), at most 6.
    Depth 1 (standing): the leg-mounted sinks; depth 2+ or prone in depth 1+:
    every sink, engine sinks included (p.103)."""
    water_state = state(mech) if water_state is None else water_state
    if water_state == GROUND:
        return 0
    if water_state == SUBMERGED:
        submerged = active_heat_sinks(mech)
    else:
        submerged = 0
        for loc in mech.leg_locations:
            for sink in _working(mech, loc, is_heat_sink):
                if id(sink) not in mech.destroyed_heat_sinks:
                    submerged += heat_sink_units(sink)
        submerged = min(submerged, active_heat_sinks(mech))
    return min(MAX_WATER_DISSIPATION, submerged * heat_sink_rate(mech))


def jump_mp_lost(mech, water_state=None) -> Optional[int]:
    """Jumping MP the water takes away (p.50): the working leg jump jets in
    depth 1; None = can't jump at all (depth 2+ or prone in water)."""
    water_state = state(mech) if water_state is None else water_state
    if water_state == SUBMERGED:
        return None
    if water_state == PARTIAL:
        return sum(1 for loc in mech.leg_locations for jet in _working(mech, loc, is_jump_jet)
                   if id(jet) not in mech.destroyed_jump_jet_ids)
    return 0


def jump_mp(mech) -> int:
    """The mech's Jumping MP where it stands now (p.50)."""
    lost = jump_mp_lost(mech)
    return 0 if lost is None else max(0, compute_jump_mp(mech) - lost)


def fall_damage_divisor(mech) -> int:
    """p.115: a 'Mech that falls in depth 1+ water takes half damage."""
    return 2 if depth_at(mech.hex) >= 1 else 1


def hexes_by_depth(terrain_map) -> Dict[str, int]:
    """{label: depth} of the board's water hexes of depth 1+."""
    return {label: info["depth"] for label, info in terrain_map["hexes"].items() if info.get("depth", 0) >= 1}
