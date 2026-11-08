"""
INTEGRATION__stack.py  (NEW 2026-11-07, Claude) - STACKED COVERAGE (Daniel, 2026-11-07: "Gladiator needs to have a
tendency to stack their damage heat maps v a target's movement profile up to the limit of damage needed to take out that
target's toughness"; "Full kill" - the limit is the target's whole HP).

    config.STACK = True            # default False
    config.STACK_WEIGHT = 1.0      # score points of "dealt" a point of added coverage is worth
    config.STACK_QUANTILE = None   # None: the mean over the enemy's footprint; 0.25: its 25th percentile; 0: the minimum

For each enemy E (units on the board), the team's damage on E is the sum of the teammates' damage fields on E
(INTEGRATION__peril: each teammate's weapons over everywhere it could end, line of sight and cover applied; a teammate
that has moved counts at its real spot). E picks where to go, so the damage that matters is read over E's FOOTPRINT (its
real spot once it has moved): hex by hex, the stacked damage capped at E's toughness (`movement_selection.effective_hp`:
armor + rear armor + k x structure, the units the score is in), then averaged (or a low quantile: "can it get out of the
stack"). A candidate spot for the mover adds its own damage on E's footprint hexes from THAT spot; the term is how much
that adds to the capped coverage, summed over the enemies, times STACK_WEIGHT, and joins the mover's damage dealt.
Past the cap a hex earns nothing, so the mover is pulled to the enemy the stack does not yet cover.

A teammate's reach is its PEAK (it picks its own best spot), the mover's is exact (one spot).
"""

import numpy as np

import INTEGRATION__config as config
import INTEGRATION__movement_selection as movement_selection
import INTEGRATION__peril as peril
import INTEGRATION__vision as vision
import hex_geometry


class Stack:
    def __init__(self, mover, enemies, friends, terrain_map):
        self.vt = vision.table(terrain_map)
        self.mover = mover
        self.terrain_map = terrain_map
        self.cells = []                      # per enemy: (rows, cap, stacked damage on those rows, mover's table)
        for e in enemies:
            rows = self.vt.rows(peril.footprint_for(e, terrain_map))
            if not len(rows):
                continue
            stacked = np.zeros(len(rows))
            for f in friends:
                stacked += peril.field_for(f, e, terrain_map, vt=self.vt).peak[rows]
            table = peril.profile_table(mover, e)
            if table is None:
                continue
            cap = movement_selection.effective_hp(e)
            self.cells.append((rows, cap, stacked, table))
        self._base = [self._cover(np.minimum(cap, stacked)) for _, cap, stacked, _ in self.cells]
        self._gain = {}                      # (x, y) -> gain

    @staticmethod
    def _cover(capped):
        q = config.STACK_QUANTILE
        return float(capped.mean() if q is None else np.quantile(capped, q))

    def gain(self, hex_xy):
        """Coverage the mover adds by standing on hex_xy (summed over the enemies, in score points)."""
        g = self._gain.get(hex_xy)
        if g is not None:
            return g
        i = self.vt.index.get(hex_xy)
        total = 0.0
        if i is not None:
            for (rows, cap, stacked, table), base in zip(self.cells, self._base):
                last = table.shape[1] - 1
                dist = np.minimum(self.vt.dist[i, rows], last)
                mine = np.where(self.vt.seen[i, rows], table[self.vt.mod[i, rows], dist], 0.0)
                total += self._cover(np.minimum(cap, stacked + mine)) - base
        g = self._gain[hex_xy] = config.STACK_WEIGHT * total
        return g
