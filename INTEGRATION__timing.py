"""
INTEGRATION__timing.py  (NEW 2026-10-21, Claude - Pile 1, measurement only)

Where a batch spends its time. Daniel (2026-10-21): "since we're running a
bunch of simulations, may as well put a tracker on them to see where they're
spending their time. We still need more speed, and this gives us the data to
find out what needs to be improved."

  - config.TIMING (default True): named sections of the turn are timed
    (`with timing.section("ranged attacks"):`). Sections nest - a section
    opened inside another is reported under it - so the report reads as a
    tree: movement > picking a spot > two-ply look-ahead. Each battle's
    totals travel back with its BattleResult (parallel workers included) and
    run_batch prints "WHERE THE TIME WENT" after the batch summary.
  - config.PROFILE_FUNCTIONS = N (default 0 = off): every battle also runs
    under cProfile and the N functions with the most time of their own are
    listed after the sections. Much slower (about 2x) - for hunting a specific
    hot spot, not for routine runs.

Timing only reads the clock: a timed battle plays out exactly like an untimed
one. The printed times differ from run to run, so the reference battles and
the tests that compare printed output switch TIMING off.
"""

import cProfile
import marshal
import os
import pstats
import tempfile
import time
from collections import defaultdict
from contextlib import contextmanager

import INTEGRATION__config as config

SEP = " > "

# This process's totals: {"movement > picking a spot": [seconds, calls]}.
_totals = defaultdict(lambda: [0.0, 0])
_stack = []


@contextmanager
def _timed(name):
    _stack.append(name)
    key = SEP.join(_stack)
    start = time.perf_counter()
    try:
        yield
    finally:
        entry = _totals[key]
        entry[0] += time.perf_counter() - start
        entry[1] += 1
        _stack.pop()


@contextmanager
def _off():
    yield


def section(name):
    """Time the block under `name` (nested inside any open section)."""
    return _timed(name) if config.TIMING else _off()


def take():
    """This process's totals since the last take(), as a plain dict, then reset."""
    out = {k: list(v) for k, v in _totals.items()}
    _totals.clear()
    return out


# =============================================================================
# ==========================  FUNCTION PROFILE  ===============================
# =============================================================================
def start_profile():
    """A running cProfile when config.PROFILE_FUNCTIONS > 0, else None."""
    if config.PROFILE_FUNCTIONS <= 0:
        return None
    prof = cProfile.Profile()
    prof.enable()
    return prof


def stop_profile(prof):
    """The profile's raw stats (a plain dict, so it can travel back from a worker)."""
    if prof is None:
        return None
    prof.disable()
    return pstats.Stats(prof).stats


# =============================================================================
# ==========================  REPORT  =========================================
# =============================================================================
def report(results, wall_seconds, workers):
    """Print where the batch's time went (sections, then the function profile)."""
    timings = [r.timing for r in results if r.timing]
    if not timings:
        return
    totals = defaultdict(lambda: [0.0, 0])
    for t in timings:
        for key, (secs, calls) in t.items():
            totals[key][0] += secs
            totals[key][1] += calls
    battle_time = totals.get("battle", [0.0, 0])[0] or sum(v[0] for k, v in totals.items() if SEP not in k)
    turns = sum(r.turns_taken for r in results)

    print()
    print("#" * 70)
    print(f"WHERE THE TIME WENT - {len(results)} battle(s), {turns} turns, {wall_seconds:.0f} s on the clock "
          f"({workers} worker{'s' if workers != 1 else ''})")
    print(f"  {battle_time:.1f} s inside battles = {battle_time / max(1, len(results)):.2f} s a battle, "
          f"{battle_time / max(1, turns):.3f} s a turn")
    print("#" * 70)
    print(f"  {'section':52s} {'share':>6s} {'seconds':>9s} {'calls':>8s} {'ms/call':>8s}")

    def children(parent):
        """The sections directly inside `parent` ("" = top level), most time first."""
        depth = parent.count(SEP) + 1 if parent else 0
        prefix = parent + SEP if parent else ""
        return sorted((k for k in totals if k.startswith(prefix) and k.count(SEP) == depth),
                      key=lambda k: -totals[k][0])

    def show(parent, parent_secs, indent):
        kids = children(parent)
        for key in kids:
            secs, calls = totals[key]
            label = "  " * indent + key.split(SEP)[-1]
            print(f"  {label:52s} {100 * secs / battle_time:5.1f}% {secs:9.1f} {calls:8d} {1000 * secs / max(1, calls):8.2f}")
            show(key, secs, indent + 1)
        if parent and kids:
            rest = parent_secs - sum(totals[k][0] for k in kids)
            if rest > 0.005 * battle_time:
                label = "  " * indent + "(rest of " + parent.split(SEP)[-1] + ")"
                print(f"  {label:52s} {100 * rest / battle_time:5.1f}% {rest:9.1f}")

    battle = "battle" if "battle" in totals else ""
    show(battle, battle_time, 0)

    profiles = [r.profile for r in results if r.profile]
    if profiles:
        _print_profile(profiles)


def _print_profile(profiles):
    """Merge the battles' cProfile stats and list the top functions."""
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, stats in enumerate(profiles):
            path = os.path.join(tmp, f"battle{i}.prof")
            with open(path, "wb") as f:
                marshal.dump(stats, f)
            paths.append(path)
        merged = pstats.Stats(*paths, stream=None)
        print()
        print(f"  Functions with the most time of their own (cProfile, {len(profiles)} battle(s); "
              f"profiling roughly doubles run time, so read shares, not seconds):")
        merged.sort_stats("tottime").print_stats(config.PROFILE_FUNCTIONS)
