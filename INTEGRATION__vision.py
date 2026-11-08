"""
INTEGRATION__vision.py  (NEW 2026-11-07, Claude) - THE PER-BOARD VISIBILITY TABLE (Peril heat map, stage 1).

    table = vision.table(terrain_map)        # built once per board, then remembered
    table.index[(x, y)]                      # row / column of a hex
    table.seen[i, j]                         # True when hex i sees hex j (both 'Mechs standing)
    table.mod[i, j]                          # the to-hit modifier the line picks up (woods, partial cover), clipped 0..3
    table.dist[i, j]                         # hex distance

Static: nothing here changes while a board is loaded (smoke aside: INTEGRATION__smoke calls `invalidate`, the table is
rebuilt on the next use). Every answer comes from INTEGRATION__los_cache.pair_info (Rust when built), so the table agrees
with the rules code line for line. Whether a line exists is symmetric for two standing 'Mechs, but the modifier it picks up is NOT always (14% of
random pairs on the battery field differ: the traced line runs a different side of a hex edge), so every ordered pair
is asked: row = the firer's hex, column = the target's. Cost: one N x N table, about 7 us a pair cold (544 hexes:
~2 s; 2 x 2 boards ~8 s; 3 x 3 ~42 s), kept in memory (3 arrays: 544 hexes is 1.2 MB).
"""

import numpy as np

import hex_geometry

import INTEGRATION__los_cache as los_cache

MOD_CLASSES = 4                       # modifier 0, +1, +2, +3 or worse (clipped): the classes the damage profiles are built for

_TABLES = {}                          # id(terrain_map) -> (terrain_map, VisionTable)


class VisionTable:
    __slots__ = ("terrain_map", "hexes", "index", "seen", "mod", "dist", "build_seconds")

    def __init__(self, terrain_map, hexes, seen, mod, dist, seconds):
        self.terrain_map = terrain_map
        self.hexes = hexes                                     # [(x, y)], the row order
        self.index = {h: i for i, h in enumerate(hexes)}
        self.seen, self.mod, self.dist = seen, mod, dist
        self.build_seconds = seconds

    def rows(self, spots):
        """The row numbers of a collection of (x, y) hexes (any off the board are skipped)."""
        return np.fromiter((self.index[s] for s in spots if s in self.index), dtype=np.int32)


def _hex_list(terrain_map):
    out = []
    for label in terrain_map["hexes"]:
        out.append(hex_geometry.parse_hex_label(label))        # labels count from 1, (x, y) from 0
    return sorted(out)


def build(terrain_map):
    import time
    start = time.perf_counter()
    hexes = _hex_list(terrain_map)
    n = len(hexes)
    seen = np.zeros((n, n), dtype=bool)
    mod = np.zeros((n, n), dtype=np.int8)
    dist = np.zeros((n, n), dtype=np.int16)
    pair = los_cache.pair_info
    for i in range(n):
        a = hexes[i]
        seen[i, i] = True
        for j in range(n):
            if j == i:
                continue
            t = hexes[j]
            try:
                res, _entry, d, _arcs = pair(a, t, terrain_map)
            except ValueError:
                d = los_cache.hex_distance(a, t)
            else:
                seen[i, j] = res.los
                mod[i, j] = max(0, min(MOD_CLASSES - 1, res.modifier)) if res.los else 0
            dist[i, j] = d
    return VisionTable(terrain_map, hexes, seen, mod, dist, time.perf_counter() - start)


def table(terrain_map):
    hit = _TABLES.get(id(terrain_map))
    if hit is None or hit[0] is not terrain_map:
        hit = (terrain_map, build(terrain_map))
        _TABLES[id(terrain_map)] = hit
    return hit[1]


def invalidate():
    """Smoke changed the board: forget the tables."""
    _TABLES.clear()


def asymmetric_sample(vt, count=2000, seed=1):
    """How many of `count` random pairs answer differently from the reverse line (a check; the modifier is the part that differs)."""
    import random
    rng = random.Random(seed)
    n, bad = len(vt.hexes), 0
    for _ in range(count):
        i, j = rng.randrange(n), rng.randrange(n)
        if i == j:
            continue
        try:
            fwd = los_cache.pair_info(vt.hexes[i], vt.hexes[j], vt.terrain_map)[0]
            back = los_cache.pair_info(vt.hexes[j], vt.hexes[i], vt.terrain_map)[0]
        except ValueError:
            continue
        if fwd.los != back.los or (fwd.los and fwd.modifier != back.modifier):
            bad += 1
    return bad
