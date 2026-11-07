"""
tests/test_tiers.py - checks the tiered movement order (2026-11-07, INTEGRATION__tiers; Daniel's design): the tiers a
unit lands in, the order inside and across tiers, the flanker pool for tiers 2 and 3, that the default order is
untouched, and whole battles (entering the battlefield included) under MOVE_ORDER "tiered".

    python tests/test_tiers.py
"""
import io
import os
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
config.STATS = False
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__forces as forces  # noqa: E402
import INTEGRATION__tiers as tiers  # noqa: E402
from test_multi_unit import fresh, unit_file, run_forces, TERRAIN, ATLAS, COMMANDO  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


class Fake:
    """A stand-in unit for the order checks: only what tiers.pick reads."""
    def __init__(self, name):
        self.name = name


def with_tiers(table):
    """Sets tiers.plan_phase's result by hand: {Fake: (tier, speed, distance, flanker ids)}."""
    tiers.reset()
    for unit, (tier, speed, distance, flankers) in table.items():
        tiers._TIERS[id(unit)] = tiers.Tier(tier, speed, distance, frozenset(flankers))


def tier_names(units):
    saved = config.MOVE_ORDER
    config.MOVE_ORDER = "tiered"
    try:
        with ScriptedDice([], default=7):
            tiers.plan_phase(units, TERRAIN)
        return {u.side_name: tiers.NAMES[tiers.tier_of(u).tier] for u in units}
    finally:
        config.MOVE_ORDER = saved
        tiers.reset()


@check
def pick_orders_tiers_then_speed_and_stand_still_farthest_first():
    a, b, c, d, e, f = (Fake(n) for n in "abcdef")
    with_tiers({a: (tiers.TRAPPED, 2, 3, []), b: (tiers.SAFE, 6, 20, []), c: (tiers.SAFE, 3, 18, []),
                d: (tiers.MAY_BE_FLANKED, 2, 8, []), e: (tiers.STANDS_STILL, 5, 4, []),
                f: (tiers.STANDS_STILL, 5, 12, [])})
    waiting, order = [a, b, c, d, e, f], []
    while waiting:
        nxt = tiers.pick(waiting)
        waiting.remove(nxt)
        order.append(nxt.name)
    # stand-still first (the farthest from its enemy, f, then e); the safe ones slowest first (c, b); then may be
    # flanked (d); trapped last (a)
    assert order == ["f", "e", "c", "b", "d", "a"], order
    tiers.reset()


@check
def equal_tiers_and_speeds_keep_roster_order():
    a, b, c = Fake("a"), Fake("b"), Fake("c")
    with_tiers({a: (tiers.SAFE, 4, 9, []), b: (tiers.SAFE, 4, 9, []), c: (tiers.SAFE, 4, 9, [])})
    assert tiers.pick([b, a, c]) is b
    tiers.reset()


@check
def the_flanker_pool_is_narrowed_only_for_tiers_two_and_three():
    me, f1, f2, f3 = Fake("me"), Fake("f1"), Fake("f2"), Fake("f3")
    pool = [f1, f2, f3]
    with_tiers({me: (tiers.SAFE, 4, 9, [id(f1)])})
    assert tiers.flankers_of(me, pool) == pool                         # safe: the whole pool
    with_tiers({me: (tiers.MAY_BE_FLANKED, 4, 9, [id(f2)])})
    assert tiers.flankers_of(me, pool) == [f2]
    with_tiers({me: (tiers.TRAPPED, 4, 9, [id(f1), id(f3)])})
    assert tiers.flankers_of(me, pool) == [f1, f3]
    with_tiers({me: (tiers.TRAPPED, 4, 9, [])})
    assert tiers.flankers_of(me, pool) == pool                         # no flanker: never an empty pool
    with_tiers({me: (tiers.TRAPPED, 4, 9, [id(f1)])})
    assert tiers.flankers_of(me, [f2, f3]) == [f2, f3]                 # the flanker already moved: the rest
    tiers.reset()
    assert tiers.flankers_of(me, pool) == pool                         # no tier at all (the default order)


@check
def units_out_of_each_others_reach_are_safe():
    a = fresh(COMMANDO, "0101", "S", "A 1", "A")
    b = fresh(COMMANDO, "1516", "N", "B 1", "B")
    assert tier_names([a, b]) == {"A 1": "safe", "B 1": "safe"}


@check
def a_slow_unit_beside_a_fast_one_is_trapped_and_the_fast_one_may_be_flanked():
    slow = fresh(ATLAS, "0808", "N", "A 1", "A")
    fast = fresh(COMMANDO, "0809", "S", "B 1", "B")
    got = tier_names([slow, fast])
    assert got["A 1"] == "trapped", got
    assert got["B 1"] in ("may be flanked", "trapped"), got


@check
def the_flanker_set_holds_the_enemies_that_can_reach_next_to_the_unit():
    slow = fresh(ATLAS, "0301", "N", "A 1", "A")
    fast = fresh(COMMANDO, "0302", "S", "B 1", "B")
    far = fresh(COMMANDO, "1516", "N", "B 2", "B")
    config.MOVE_ORDER = "tiered"
    try:
        with ScriptedDice([], default=7):
            tiers.plan_phase([slow, fast, far], TERRAIN)
        t = tiers.tier_of(slow)
        assert id(fast) in t.flankers and id(far) not in t.flankers, t
    finally:
        config.MOVE_ORDER = "index"
        tiers.reset()


@check
def the_default_order_never_computes_tiers():
    a = fresh(COMMANDO, "0101", "S", "A 1", "A")
    b = fresh(COMMANDO, "1516", "N", "B 1", "B")
    assert config.MOVE_ORDER == "index"
    tiers.plan_phase([a, b], TERRAIN)
    assert tiers.tier_of(a) is None and tiers.tier_of(b) is None


@check
def a_battle_under_the_tiered_order_runs_and_every_unit_has_a_tier_each_turn():
    """Entering the battlefield included: on turn 1 every unit is still off the board and still gets a tier."""
    seen = []
    real = tiers.plan_phase

    def spy(units, terrain_map):
        real(units, terrain_map)
        live = forces.standing(units)
        seen.append((len(live), sum(1 for u in live if tiers.tier_of(u) is not None), sum(1 for u in live if u.hex is None)))

    config.MOVE_ORDER = "tiered"
    tiers.plan_phase = spy
    orchestrator.tiers.plan_phase = spy
    try:
        result = run_forces([{"team": "Red", "mtf": "Kontio.mtf", "count": 4},
                             {"team": "Blue", "mtf": "Hammerhead.mtf", "count": 4}], max_turns=3)
    finally:
        config.MOVE_ORDER = "index"
        tiers.plan_phase = orchestrator.tiers.plan_phase = real
    assert result.winner in ("Red", "Blue", "Draw") and seen, seen
    assert all(units == tiered for units, tiered, _ in seen), seen
    assert seen[0][2] == 8, seen[0]                        # turn 1: all eight still off the board
    assert not tiers._TIERS                                # cleared at the end of the phase


def run_all():
    failed = 0
    for fn in CHECKS:
        try:
            with ScriptedDice([], default=7), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print()
    if failed:
        print(f"{failed} of {len(CHECKS)} tier checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} tier checks passed.")


if __name__ == "__main__":
    run_all()
