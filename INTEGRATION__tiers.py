"""
INTEGRATION__tiers.py  (NEW 2026-11-07, Claude) - TIERED MOVEMENT ORDER (Daniel's design, 2026-11-07).

    config.MOVE_ORDER = "tiered"      # default "index" (Princess's move index, forces.move_index)

WHO MOVES FIRST, for a side's Gladiator units. Princess units, and every unit under "index", keep Princess's move
index. The point (Daniel): the order is about INFORMATION and about not getting flanked, not about picking the best
spot for one unit - a unit that can't be reached has nothing to lose by committing early, a unit that is trapped
gains most by waiting to see where everyone else went. Four tiers, fixed once at the start of the Movement Phase:

  0  STANDS STILL    Legate's estimate of the unit's own end spot is the hex it is on. First, the FARTHEST from
                     its nearest enemy first. (Daniel: "units that are going to stand still always move first,
                     starting with the farthest away".) Needs Legate's plan, so not before every unit is on the board.
  1  SAFE            the unit's movement footprint (every hex it could end on) is completely outside the enemy's
                     movement footprint (the union of every enemy's). It can't be reached.
  2  MAY BE FLANKED  the footprints overlap in some hexes.
  3  TRAPPED         every hex the unit could end on is inside the enemy's footprint: it can't escape.

Within tiers 1-3 the SLOWER unit goes first ("in general slower first, then faster"), then roster order.

ENTERING THE BATTLEFIELD uses the same rule (Daniel: "should also apply when entering the battlefield"): a unit still
off the board has the hexes it can enter on as its footprint, and an enemy still off the board counts with its own
entry hexes. There is no "off the board first" rule in this order.

THE FOE for tiers 2 and 3 (Daniel): a Gladiator that may be flanked, or already is, plans its two-ply against the
highest-threat enemy that could flank it, not just the highest-threat enemy (`flankers` below, used by
legate.foe_for). An enemy "could flank" a unit when its footprint reaches a hex next to one the unit could end on.

FOOTPRINT = the (x, y) of every end state `ranged_combat.movement_options` gives (walk, run, jump, every facing),
the hexes other units stand on already left out by that function. A shut-down or immobile unit's footprint is the
hex it stands on. Cost: one movement search per unit at the start of the phase.

Static: tiers are worked out once per Movement Phase, from where everyone starts it (so a unit's tier does not
change as others move). Placeholder simplifications, each a candidate refinement (PROJECT_MAP Section 6):
the enemy footprint is the whole enemy side's union, not per enemy; a "flank" is any reach to a neighbouring hex,
not a reach to a hex in the unit's side or rear arc.
"""

from collections import namedtuple

import INTEGRATION__config as config
import INTEGRATION__forces as forces
import INTEGRATION__ranged_combat as ranged_combat
import hex_geometry
from mech_state import compute_running_mp, compute_jump_mp, is_immobile

STANDS_STILL, SAFE, MAY_BE_FLANKED, TRAPPED = 0, 1, 2, 3
NAMES = {STANDS_STILL: "stands still", SAFE: "safe", MAY_BE_FLANKED: "may be flanked", TRAPPED: "trapped"}

Tier = namedtuple("Tier", "tier speed distance flankers")        # flankers: ids of the enemies that could flank it

_TIERS = {}                  # id(unit) -> Tier, for the phase in progress


def reset():
    _TIERS.clear()


def tier_of(unit):
    return _TIERS.get(id(unit))


def footprint(mech, terrain_map):
    """Every hex (x, y) the mech could end its movement on this turn (see the module docstring)."""
    if mech.hex is not None and (mech.shutdown or is_immobile(mech)):
        return frozenset([hex_geometry.parse_hex_label(mech.hex)])
    edge = mech.home_edge if mech.hex is None else None          # entering the battlefield (p.37)
    return frozenset((st[0], st[1]) for st in ranged_combat.movement_options(mech, terrain_map, None, edge))


def _ring(cells):
    """The cells and every hex next to one of them."""
    out = set(cells)
    for x, y in cells:
        for dx, dy in hex_geometry.FACING_DELTAS.values():
            out.add((x + dx, y + dy))
    return out


def plan_phase(units, terrain_map):
    """The start of the Movement Phase: every standing unit's tier. Stores them (tier_of); logs one line a unit."""
    reset()
    if config.MOVE_ORDER != "tiered":
        return
    import INTEGRATION__legate as legate
    live = forces.standing(units)
    foot = {id(u): footprint(u, terrain_map) for u in live}
    teams = forces.team_names(live)
    enemy_union = {t: frozenset().union(*[foot[id(u)] for u in live if u.team != t]) for t in teams}
    for u in live:
        mine, theirs = foot[id(u)], enemy_union[u.team]
        near = [d for d in (forces.distance(u, e) for e in forces.enemies_of(u, units)) if d is not None]
        distance = min(near) if near else 0
        speed = max(compute_running_mp(u), compute_jump_mp(u))
        own = legate._OWN.get(u.team, {}).get(id(u))
        stands = own is not None and u.hex is not None and own[0] == u.hex
        if stands:
            tier = STANDS_STILL
        elif not (mine & theirs):
            tier = SAFE
        elif mine <= theirs:
            tier = TRAPPED
        else:
            tier = MAY_BE_FLANKED
        flankers = frozenset()
        if tier in (MAY_BE_FLANKED, TRAPPED):
            reach = _ring(mine)
            flankers = frozenset(id(e) for e in forces.enemies_of(u, units) if foot[id(e)] & reach)
        _TIERS[id(u)] = Tier(tier, speed, distance, flankers)
        if config.VERBOSE:
            config.log(f"  [Order] {u.side_name}: {NAMES[tier]} (speed {speed}, {distance} hexes from its nearest enemy, "
                       f"{len(flankers)} could flank it)")


def pick(candidates):
    """Which of a side's waiting units moves next, under MOVE_ORDER "tiered": lowest tier first; tier 0 farthest
    from its enemy first; tiers 1-3 slowest first; ties by roster order (min keeps the first)."""
    def key(u):
        t = _TIERS.get(id(u))
        if t is None:
            return (SAFE, 0, 0)                      # a unit with no tier (appeared mid-phase) goes with the safe ones
        if t.tier == STANDS_STILL:
            return (t.tier, -t.distance, 0)
        return (t.tier, t.speed, 0)
    return min(candidates, key=key)


def flankers_of(unit, pool):
    """The enemies in `pool` that could flank `unit` (tiers 2 and 3 only); the whole pool when it has none or
    the unit has no tier, so a foe is always found."""
    t = _TIERS.get(id(unit))
    if t is None or t.tier not in (MAY_BE_FLANKED, TRAPPED):
        return pool
    narrowed = [f for f in pool if id(f) in t.flankers]
    return narrowed or pool
