"""INTEGRATION__deployment.py - where a mech may start its movement when it
enters the battlefield from its home edge (NEW 2026-10-21, Claude).

Daniel, 2026-10-21:
  - "A mech's level before it enters is undefined. So it can enter on top of
    those level 5 walls. But it could also get stuck up there which is bad.
    (I think defining stuck as no path to the other side of the map is
    possible for this unit.)"
  - "Add a deployment option. Default is 0 with a 'I can't enter/stuck
    terrain' override. Its value is the number of hexes in from the edge that
    a mech can start its movement. The override sets it at 3."

So (config.DEPLOYMENT_DEPTH, config.DEPLOYMENT_STUCK_DEPTH):
  - A mech may start its movement in a hex 0..DEPLOYMENT_DEPTH hexes in from
    its home edge (0 = the edge hexes, Core p.37) - roofs included, since
    nothing is climbed (terrain_rules.step_cost with no hex left behind).
  - It may only start where it can enter and is NOT STUCK: from that hex this
    unit can still reach the far side of the map (Claude's reading: a hex up
    to DEPLOYMENT_STUCK_DEPTH in from the opposite edge), walking (terrain_rules.
    step_cost with its level-change limit) or jumping (combat.build_jump_states
    with its Jumping MP there - water takes leg jets, INTEGRATION__water).
  - No such hex: the override - DEPLOYMENT_STUCK_DEPTH hexes in. Still none:
    no start hex at all, and the mech is destroyed when it can't enter (p.37).
"""

from collections import deque
from typing import Dict, List, Set

import INTEGRATION__config as config
import INTEGRATION__water as water
from mech_state import is_superheavy, ground_level_limited  # pp.90, 99, 238-239
import terrain_rules
import combat
import hex_geometry
from mech_state import compute_jump_mp

EDGE_NAMES = ("N", "E", "S", "W")
OPPOSITE_EDGE = {"N": "S", "S": "N", "E": "W", "W": "E"}


def band(terrain_map, edge, depth) -> List[str]:
    """Hex labels 0..depth hexes in from `edge` (CCRR: column 1-width, row
    1-height), edge row first. A row (N / S) or column (W / E) of the grid is
    one hex further in."""
    w, h = terrain_map["width"], terrain_map["height"]
    labels = []
    for k in range(depth + 1):
        if edge in ("N", "S"):
            row = 1 + k if edge == "N" else h - k
            if 1 <= row <= h:
                labels += [f"{c:02d}{row:02d}" for c in range(1, w + 1)]
        else:
            col = 1 + k if edge == "W" else w - k
            if 1 <= col <= w:
                labels += [f"{col:02d}{r:02d}" for r in range(1, h + 1)]
    return [lab for lab in labels if lab in terrain_map["hexes"]]


def _jump_mp_at(mech, label, terrain_map):
    """The mech's Jumping MP standing (not prone) in `label` (p.50)."""
    lost = water.jump_mp_lost(mech, water.state_at(label, False, terrain_map, is_superheavy(mech)))
    return 0 if lost is None else max(0, compute_jump_mp(mech) - lost)


def _moves(mech, label, terrain_map, level_limit, jumping=True) -> Set[str]:
    """Hexes this unit can get to from `label` in one ground step or (when
    `jumping`) one jump."""
    hexes = terrain_map["hexes"]
    info = hexes[label]
    out = set()
    for n in neighbours(label, terrain_map):
        if terrain_rules.step_cost(info, hexes[n], level_limit) is not None:
            out.add(n)
    jump = _jump_mp_at(mech, label, terrain_map) if jumping else 0
    if jump > 0:
        x, y = hex_geometry.parse_hex_label(label)
        out |= {hex_geometry.hex_label(sx, sy) for (sx, sy, _f) in combat.build_jump_states(x, y, jump, terrain_map)}
    return out


def neighbours(label, terrain_map):
    x, y = hex_geometry.parse_hex_label(label)
    for dx, dy in hex_geometry.FACING_DELTAS.values():
        try:
            n = hex_geometry.hex_label(x + dx, y + dy)
        except ValueError:
            continue
        if n in terrain_map["hexes"]:
            yield n


def reaches(mech, start, goal: Set[str], terrain_map, moves_cache=None) -> bool:
    """Can this unit get from `start` to any hex in `goal`, over as many turns
    as it likes (Daniel's "no path to the other side of the map")? Walking
    alone is tried first (cheap); jumps only if that fails. moves_cache: a
    dict shared between calls for one mech and board (speed only)."""
    level_limit = terrain_rules.max_level_change(ground_level_limited(mech), is_superheavy(mech))
    cache = {} if moves_cache is None else moves_cache
    for jumping in (False, True):
        if jumping and compute_jump_mp(mech) <= 0:
            break
        seen, queue = {start}, deque([start])
        while queue:
            here = queue.popleft()
            if here in goal:
                return True
            key = (here, jumping)
            nxt_set = cache.get(key)
            if nxt_set is None:
                nxt_set = cache[key] = _moves(mech, here, terrain_map, level_limit, jumping)
            for nxt in nxt_set:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
    return False


def start_hexes(mech, terrain_map, edge) -> Dict[str, object]:
    """{"hexes": [labels the mech may start its movement in], "depth": the
    depth used, "stuck": [enterable hexes within it left out as stuck]}."""
    # "The other side of the map" (Claude's reading): any hex up to
    # DEPLOYMENT_STUCK_DEPTH in from the far edge - the far edge itself can be
    # solid wall (Solaris arenas), and that band mirrors where the enemy may start.
    far = set(band(terrain_map, OPPOSITE_EDGE[edge], max(config.DEPLOYMENT_STUCK_DEPTH, config.DEPLOYMENT_DEPTH)))
    good_cache: Dict[str, bool] = {}
    moves_cache: Dict[tuple, Set[str]] = {}

    def usable(depth):
        ok, stuck = [], []
        for label in band(terrain_map, edge, depth):
            if terrain_rules.step_cost(None, terrain_map["hexes"][label]) is None:
                continue
            if label not in good_cache:
                good_cache[label] = reaches(mech, label, far, terrain_map, moves_cache)
            (ok if good_cache[label] else stuck).append(label)
        return ok, stuck

    depth = config.DEPLOYMENT_DEPTH
    ok, stuck = usable(depth)
    if not ok and config.DEPLOYMENT_STUCK_DEPTH > depth:
        depth = config.DEPLOYMENT_STUCK_DEPTH
        ok, stuck = usable(depth)
    return {"hexes": ok, "depth": depth, "stuck": stuck}
