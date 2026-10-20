"""
tests/benchmark_turns.py - times one fixed battle, so speed changes are
measured on the same battle every time (added 2026-10-20).

    python tests/benchmark_turns.py            # default battle, first 10 turns
    python tests/benchmark_turns.py 10 tottime # ... plus a cProfile table (slower)

The battle is Asymptote II vs Asymptote II on INTEGRATION__config's default
board (16x17 Grassland) at seed 12345 - the old default matchup, pinned here
(2026-10-20) so the timings stay comparable: the new default (Kontio vs
Hammerhead) ends on turn 1 at this seed. Prints turns, seconds and both final HP
totals - the HP totals must not change for a pure speed change.
Reference points (PROJECT_MAP Change Record): 31.7 s before the 2026-10-20
speed pass, 11.8 s after it, ~14.5 s with all seven physical attacks,
about 25% less after the 2026-10-20 memo sharing (21.5 s -> 16.3 s on a
slower machine). Parallel batches (config.WORKERS) don't show here - this is
one battle.
"""

import cProfile
import io
import os
import pstats
import sys
import time
from contextlib import redirect_stdout

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402


def main():
    turns = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    sort = sys.argv[2] if len(sys.argv) > 2 else None
    config.VERBOSE = False
    config.MECH_RED_MTF = config.MECH_BLUE_MTF = "Asymptote II iJ Mpulse.mtf"
    profile = cProfile.Profile()
    start = time.time()
    if sort:
        profile.enable()
    with redirect_stdout(io.StringIO()):
        result = orchestrator.run_batch(num_simulations=1, seed=12345, max_turns=turns)[0]
    if sort:
        profile.disable()
    print(f"{result.turns_taken} turns in {time.time() - start:.1f} s; final HP red {result.red.final_hp} "
          f"blue {result.blue.final_hp}")
    if sort:
        pstats.Stats(profile).sort_stats(sort).print_stats(30)


if __name__ == "__main__":
    main()
