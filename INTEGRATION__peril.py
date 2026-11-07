"""
INTEGRATION__peril.py  (NEW 2026-11-07, Claude) - THE PERIL HEAT MAP (Daniel's design; PROJECT_MAP Pick up here 000000).

    field = peril.unit_field(attacker, target, terrain_map)      # one attacker's damage field over the board
    total = peril.team_field(enemies, target, terrain_map)       # a side's Peril: the fields added

For every attacker: its weapons' damage-over-range table (future_damage.range_profile, the damage the unit does
at each distance to `target`) is laid on every spot the attacker could end its move on (tiers.footprint: walk, run,
jump, every facing, or the entry hexes when it is still off the board), and the per-board visibility table
(INTEGRATION__vision: no line of sight, no damage; woods and partial cover add to the to-hit number, so the damage
comes from the profile built for that modifier) filters it. The result per board hex h:

    peak[h]  = the most damage the attacker could bring to h from ANY spot it can reach (worst case for whoever
               stands on h)
    mean[h]  = the same averaged over all its spots (a flat guess at how likely each spot is)

The arcs are ignored: a unit that can move picks its facing at the end of the move, so its damage reaches every
direction. (A unit that stands still is tied to its facing; add its arc later - PROJECT_MAP 000000.)

`target` is the unit the damage is figured against (its own movement mode, size and so on set the to-hit numbers);
for a team's Peril on one of its own units, pass that unit. Memory is one attackers' N x spots slice at a time.
Nothing is cached across turns: a unit's footprint changes every turn.
"""

import numpy as np

import INTEGRATION__tiers as tiers
import INTEGRATION__vision as vision
import INTEGRATION__future_damage as future_damage


class Field:
    """One attacker's (or one side's) damage over the board: arrays indexed like vision.VisionTable.hexes."""
    __slots__ = ("vt", "peak", "mean")

    def __init__(self, vt, peak, mean):
        self.vt, self.peak, self.mean = vt, peak, mean

    def at(self, hex_xy, kind="peak"):
        i = self.vt.index.get(hex_xy)
        return 0.0 if i is None else float(getattr(self, kind)[i])

    def __add__(self, other):
        return Field(self.vt, self.peak + other.peak, self.mean + other.mean)


def empty(vt):
    return Field(vt, np.zeros(len(vt.hexes)), np.zeros(len(vt.hexes)))


def profile_table(attacker, target):
    """T[c, d]: the attacker's damage on target at distance d with c extra to-hit points (c = 0..3), one extra column
    of zeros past the longest reach so a distance can be clipped into it. None for a unit that can't fire."""
    base = future_damage.range_profile(attacker, target)
    if not base:
        return None
    reach = len(base)                                        # distances 0 .. reach - 1
    table = np.zeros((vision.MOD_CLASSES, reach + 1))
    table[0, :reach] = base
    for c in range(1, vision.MOD_CLASSES):
        prof = future_damage.range_profile(attacker, target, extra_tn=c)
        table[c, :len(prof)] = prof
    return table


def unit_field(attacker, target, terrain_map, spots=None, vt=None):
    """The attacker's Field (see the module docstring). `spots`: the (x, y) hexes it could end on; default
    tiers.footprint. An attacker that can't fire gives an empty field."""
    vt = vt or vision.table(terrain_map)
    table = profile_table(attacker, target)
    if table is None:
        return empty(vt)
    rows = vt.rows(tiers.footprint(attacker, terrain_map) if spots is None else spots)
    if not len(rows):
        return empty(vt)
    last = table.shape[1] - 1
    seen, mod, dist = vt.seen[rows], vt.mod[rows], np.minimum(vt.dist[rows], last)
    damage = np.where(seen, table[mod, dist], 0.0)
    return Field(vt, damage.max(axis=0), damage.mean(axis=0))


def team_field(attackers, target, terrain_map, vt=None):
    """The fields of every attacker added: what a side can do to `target` standing on each hex."""
    vt = vt or vision.table(terrain_map)
    total = empty(vt)
    for a in attackers:
        total = total + unit_field(a, target, terrain_map, vt=vt)
    return total
