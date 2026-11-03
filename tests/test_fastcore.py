"""
tests/test_fastcore.py - the Rust module `fastcore` must give the Python's exact answers
(2026-11-03, trial of compiled hot loops).

    python tests/test_fastcore.py

Build it first (needs Rust and maturin):
    cd fastcore && maturin build --release && pip install --force-reinstall target/wheels/*.whl
Not installed: the checks say so and pass - the simulator then runs on pure Python.
"""

import os
import random
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__orchestrator  # noqa: E402,F401 - puts MECHSIM / PATHFINDER on the path
import INTEGRATION__weapon_selection as ws  # noqa: E402

try:
    import fastcore  # noqa: E402
except ImportError:
    fastcore = None


def same(a, b):
    return (a[0], a[1], set(a[2])) == (b[0], b[1], set(b[2]))


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def the_rust_knapsack_matches_the_python_on_random_weapon_sets():
    """Ties on purpose (repeated values and heats, zero heat, zero value), budgets from
    negative to plenty: value, heat AND the chosen weapons must match."""
    rng = random.Random(2026)
    for _ in range(20000):
        n = rng.randint(0, 12)
        values = [rng.choice([0.0, 0.5, 1.25, 2.5, rng.random() * 10]) for _ in range(n)]
        heats = [rng.choice([0, 1, 2, 3, 3, 4, 8, rng.randint(0, 15)]) for _ in range(n)]
        budget = rng.randint(-2, 40)
        want = ws._best_subset_python(values, heats, budget)
        got = fastcore.best_subset(values, heats, budget)
        assert same(want, got), (values, heats, budget, want, got)


@check
def what_rust_does_not_take_falls_back_to_python():
    values, heats = [1.0, 2.0], [1.5, 2]                    # a non-integer heat
    assert same(ws._best_subset_rust(values, heats, 3), ws._best_subset_python(values, heats, 3))
    values, heats = [1.0] * 70, [1] * 70                   # more than 64 candidates
    assert same(ws._best_subset_rust(values, heats, 5), ws._best_subset_python(values, heats, 5))


def run_all():
    if fastcore is None:
        print("SKIP  fastcore is not built here (pure Python is used) - see this file's docstring")
        print("\nAll fastcore checks skipped.")
        return
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
        print(f"{failed} of {len(CHECKS)} fastcore checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} fastcore checks passed.")


if __name__ == "__main__":
    run_all()
