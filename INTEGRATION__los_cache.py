"""
INTEGRATION__los_cache.py  (NEW 2026-10-19, Claude - Pile 3 helper)

Compute-once caches for the geometry questions movement scoring asks over
and over. Two-ply movement selection (INTEGRATION__movement_selection) scores
every first-mover spot against every reply spot, so the same hex pair gets
asked about hundreds of thousands of times per turn. None of the answers
change while a board is loaded, so each is worked out once and remembered.

  pair_info(a, t, terrain_map, a_height=2, t_height=2) -> (LOSResult, entry_dir,
      distance, arcs) for a line from hex a to hex t, the 'Mechs that tall
      (2 standing, 1 prone - p.57). entry_dir is the absolute facing (0-5)
      from t toward the hex the line enters t's hex from - the number attack
      direction (Core p.73) is read from. distance is the hex distance.
      arcs is INTEGRATION__arcs.arcs_between(a, t): the firing arc t is in for
      each of a's 6 facings (Core p.60). (INTEGRATION__attack_resolution.
      attack_side does the entry-direction trace per attack; tests/test_
      movement_selection.py checks the two agree.) Raises ValueError for an off-board
      line, same as los.has_los - and remembers that it did, so it isn't
      retried.
  los(a, t, terrain_map)       -> LOSResult
  board(terrain_map) -> the per-map cache object. Hot loops fetch its rows
      once per call (board.to[t] = {a: info}, board.frm[a] = {t: info}) and
      do plain dict lookups, falling back to pair_info() on a miss.

Nothing here is a rule: it only stores answers from los.py / combat.py.
Memory is bounded - a cache that grows past MAX_ENTRIES is emptied (it just
refills), which matters on big boards like the 50x50 BigBlank.
"""

import os
import sys

PATHFINDER_DIR = os.environ.get("PATHFINDER_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pathfinder"))
if PATHFINDER_DIR not in sys.path:
    sys.path.insert(0, PATHFINDER_DIR)

import combat  # noqa: E402 - PATHFINDER
import INTEGRATION__arcs as arcs  # noqa: E402
from los import trace_los_path, hex_distance, STANDING_HEIGHT  # noqa: E402 - PATHFINDER

MAX_ENTRIES = 250_000


class _Board:
    """Everything cached for one loaded board. `to[t][a]` and `frm[a][t]` hold
    the same info tuple for the line a -> t, so a loop pinned on one hex can
    fetch a single row for either direction. A bad (off-board) line is stored
    as False so `row.get(x) or pair_info(...)` re-raises without retracing."""
    __slots__ = ("terrain_map", "to", "frm", "count")

    def __init__(self, terrain_map):
        self.terrain_map = terrain_map
        self.to = {}
        self.frm = {}
        self.count = 0

    def clear(self):
        self.to.clear()
        self.frm.clear()
        self.count = 0


# (id(terrain_map), attacker height, target height) -> _Board. The board keeps
# the map object, so an id can't be reused by a different map while its entry
# exists. Heights (2026-10-21, p.57): 2 standing, 1 prone - a line's answer
# depends on both 'Mechs' LOS levels, so each height pair has its own cache.
_BOARDS = {}


def reset():
    """Empty every cache (tests; a new board)."""
    _BOARDS.clear()


def board(terrain_map, a_height=STANDING_HEIGHT, t_height=STANDING_HEIGHT) -> _Board:
    key = (id(terrain_map), a_height, t_height)
    b = _BOARDS.get(key)
    if b is None or b.terrain_map is not terrain_map:
        b = _Board(terrain_map)
        _BOARDS[key] = b
    return b


def pair_info(a_hex, t_hex, terrain_map, a_height=STANDING_HEIGHT, t_height=STANDING_HEIGHT):
    b = board(terrain_map, a_height, t_height)
    hit = b.to.get(t_hex, {}).get(a_hex)
    if hit:
        return hit
    if hit is False:
        raise ValueError(f"LOS line {a_hex} -> {t_hex} is off the loaded board (remembered).")
    if b.count >= MAX_ENTRIES:
        b.clear()
    try:
        trace = trace_los_path(a_hex, t_hex, terrain_map, a_height, t_height)
    except ValueError:
        hit = False
    else:
        steps = trace.steps
        # The hex the line crosses into the target's hex from (steps[-2]);
        # a line of length 0 has none (callers never ask - same hex).
        entry_dir = combat._direction_facing(t_hex, steps[-2].hex) if len(steps) >= 2 else 0
        hit = (trace.result, entry_dir, hex_distance(a_hex, t_hex), arcs.arcs_between(a_hex, t_hex))
    b.to.setdefault(t_hex, {})[a_hex] = hit
    b.frm.setdefault(a_hex, {})[t_hex] = hit
    b.count += 1
    if hit is False:
        raise ValueError(f"LOS line {a_hex} -> {t_hex} is off the loaded board.")
    return hit


def los(a_hex, t_hex, terrain_map, a_height=STANDING_HEIGHT, t_height=STANDING_HEIGHT):
    return pair_info(a_hex, t_hex, terrain_map, a_height, t_height)[0]

