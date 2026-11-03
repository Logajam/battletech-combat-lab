"""
tests/test_rng.py - checks the one pool of dice (2026-11-03, Daniel: "Do a clean up pass").

    python tests/test_rng.py

Every roll of a battle has to come from the battle's own INTEGRATION__rng.BattleRNG:
its state is the whole random state of the battle, which is what a saved state stores
and restores. A draw from Python's `random` module or numpy's global generator would
be invisible to a save, so a reloaded battle would drift from the original. These
checks run real battles with those generators booby-trapped.
"""

import io
import os
import random
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
from INTEGRATION__rng import BattleRNG  # noqa: E402

config.VERBOSE = False
with redirect_stdout(io.StringIO()):
    TERRAIN = orchestrator._load_map()

# The module-level draws of Python's `random` and numpy's legacy global generator.
_PY_DRAWS = ("random", "randint", "randrange", "choice", "choices", "shuffle", "sample", "uniform",
             "gauss", "getrandbits", "triangular")
_NP_DRAWS = ("random", "rand", "randn", "randint", "random_sample", "choice", "shuffle", "permutation",
             "integers", "uniform", "normal")


class StrayDraw(AssertionError):
    pass


class Booby:
    """Within the block, any draw from Python's `random` module or numpy's
    global generator raises StrayDraw (naming which one)."""

    def __enter__(self):
        self.saved = []
        for module, names, label in ((random, _PY_DRAWS, "random"), (np.random, _NP_DRAWS, "np.random")):
            for name in names:
                if hasattr(module, name):
                    self.saved.append((module, name, getattr(module, name)))
                    setattr(module, name, self._trap(f"{label}.{name}"))
        return self

    @staticmethod
    def _trap(label):
        def trap(*args, **kwargs):
            raise StrayDraw(f"a battle drew from {label}() - outside the battle's BattleRNG")
        return trap

    def __exit__(self, *exc):
        for module, name, fn in self.saved:
            setattr(module, name, fn)


def run_forces(entries, seed, max_turns):
    saved = (config.FORCES, config.DEPLOYMENT_DEPTH, config.WORKERS, config.REPLAY_BATTLES)
    config.FORCES, config.DEPLOYMENT_DEPTH, config.WORKERS, config.REPLAY_BATTLES = entries, 0, 1, 0
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            roster = config.load_roster()
            return orchestrator._run_one_roster(1, 1, seed, max_turns, roster, TERRAIN)
    finally:
        config.FORCES, config.DEPLOYMENT_DEPTH, config.WORKERS, config.REPLAY_BATTLES = saved
        config.set_active_rng(None)


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def a_team_battle_draws_only_from_its_own_pool():
    """Both bots (Gladiator with Legate and the kill curve, Princess), a tripod
    (its leg sub-roll was the last stray, fixed 2026-10-21) and Initiative for
    two teams."""
    with Booby():
        result = run_forces([{"team": "Red", "mtf": "Asymptote II iJ Mpulse.mtf", "count": 2, "bot": "gladiator"},
                             {"team": "Blue", "mtf": "Hammerhead.mtf", "count": 2, "bot": "princess"}],
                            seed=21, max_turns=4)
    assert result.turns_taken >= 1


@check
def a_duel_draws_only_from_its_own_pool():
    with Booby(), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        red, blue, _, _ = config.load_two_mechs()
        try:
            result = orchestrator._run_one_battle(1, 1, 12345, 6, red, blue, TERRAIN)
        finally:
            config.set_active_rng(None)
    assert result.turns_taken >= 1


@check
def rolls_outside_a_battle_come_from_a_private_pool():
    """A test calling roll_2d6() by hand gets a BattleRNG too, not a global generator."""
    config.set_active_rng(None)
    with Booby():
        rolls = [config.roll_2d6() for _ in range(200)] + [config.pick_number(6) for _ in range(50)]
    assert all(2 <= r <= 12 for r in rolls[:200]) and all(1 <= r <= 6 for r in rolls[200:])
    assert isinstance(config.active_rng(), BattleRNG)


@check
def the_battle_pool_is_the_one_set():
    pool = BattleRNG(seed=3)
    twin = BattleRNG(seed=3)
    config.set_active_rng(pool)
    try:
        got = [config.roll_2d6() for _ in range(30)] + [config.pick_number(20) for _ in range(30)]
    finally:
        config.set_active_rng(None)
    want = [twin.roll_2d6() for _ in range(30)] + [twin.pick_number(20) for _ in range(30)]
    assert got == want


def run_all():
    failed = 0
    for fn in CHECKS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print()
    if failed:
        print(f"{failed} of {len(CHECKS)} RNG checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} RNG checks passed.")


if __name__ == "__main__":
    run_all()
