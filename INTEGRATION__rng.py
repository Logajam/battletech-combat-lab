"""
INTEGRATION__rng.py

Single shared, seedable RNG source for the whole integration (Section 5's
RNG seeding decision, resolved 2026-08-04). New file, not an edit to either
source project's own logic - see INTEGRATION__PROJECT_MAP.md Section 5.

Design, per Daniel (2026-08-04): "a cache of random numbers created by
numpy... occasionally additional random numbers should be created to deal
with critical hits... using a single rng seed these numbers should be
reproducible between runs... picked for optimization purposes." That maps
onto two draw patterns:

  - roll_2d6() - the HIGH-VOLUME hot-path roll (every to-hit/hit-location/
    cluster/PSR/consciousness check). Keeps MECHSIM__config.py's existing
    bulk-cache trick (originally ~12x faster than one-at-a-time randint()
    calls, ~18% of total Monte Carlo runtime before that fix - see that
    file's roll_2d6.numpy_cache HELP tag) - just made INSTANCE-scoped here
    instead of using numpy's single unseeded global generator, so it's
    seedable per BattleRNG object rather than per-process.
  - pick_number(n) - the LOW-VOLUME "which crit slot got hit" draw. Not
    cached in bulk on purpose - Daniel's own framing above is "occasionally
    additional random numbers," i.e. this doesn't need roll_2d6()'s
    bulk-cache treatment.

Also exposes random() as a plain passthrough - PATHFINDER__combat.py's
resolve_combat_roll() already accepts an injectable `rng` param and only
ever calls rng.random() on it (confirmed by reading that file directly,
2026-08-04) - so a BattleRNG instance satisfies that duck-typed interface
with zero changes needed on the Pathfinder side.

One seed -> one BattleRNG instance -> every roll anywhere in a batch
(Mech_Simulator's hit/crit/PSR rolls AND Pathfinder's to-hit rolls) draws
from the same reproducible stream. See MECHSIM__config.set_active_rng()
for how Mech_Simulator's existing roll_2d6()/pick_number() pick this up
when the integration orchestrator sets one.
"""

import numpy as np


class BattleRNG:
    """Seedable, numpy-backed RNG shared across the whole integration.

    seed=None (default) behaves like today's two source projects: draws
    come from fresh OS entropy each time, no reproducibility guarantee -
    same as not seeding at all. Pass an int seed to make an entire batch's
    dice reproducible run to run.
    """

    _CHUNK = 10000  # same chunk size as MECHSIM__config.py's original cache

    def __init__(self, seed=None):
        self.seed = seed
        self._gen = np.random.default_rng(seed)
        self._dice_cache = None
        self._dice_cache_idx = 0

    def roll_2d6(self):
        """Bulk-cached 2d6 sum (2-12). Same distribution and same bulk-chunk
        approach as MECHSIM__config.py's original _next_2d6() - refills
        _CHUNK values at a time instead of drawing one at a time - just
        pulled from this instance's own seeded Generator instead of the
        bare global np.random module, so it's reproducible per-instance."""
        if self._dice_cache is None or self._dice_cache_idx >= len(self._dice_cache):
            self._dice_cache = (
                self._gen.integers(1, 7, size=self._CHUNK)
                + self._gen.integers(1, 7, size=self._CHUNK)
            ).tolist()
            self._dice_cache_idx = 0
        val = self._dice_cache[self._dice_cache_idx]
        self._dice_cache_idx += 1
        return val

    def pick_number(self, n):
        """Uncached single draw, 1..n inclusive - for the occasional 'which
        crit slot got hit' pick. Deliberately NOT bulk-cached like
        roll_2d6() - this is the low-volume draw pattern, not the hot path."""
        if n < 1:
            raise ValueError(f"pick_number(n) needs n >= 1, got {n}")
        return int(self._gen.integers(1, n + 1))

    def random(self):
        """Plain float in [0, 1). Satisfies PATHFINDER__combat.py's
        resolve_combat_roll()'s rng.random() call - no changes needed on
        the Pathfinder side to accept a BattleRNG instance as its rng=."""
        return float(self._gen.random())

    def __repr__(self):
        return f"<BattleRNG seed={self.seed!r}>"
