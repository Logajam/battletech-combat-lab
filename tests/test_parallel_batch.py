"""
tests/test_parallel_batch.py - checks the parallel batch runner
(INTEGRATION__orchestrator.run_batch with config.WORKERS, added 2026-10-20):
each battle's own seed, and that a batch prints exactly the same thing
whether its battles run one after another or several at once.

    python tests/test_parallel_batch.py

The batch checks run short battles (3 battles, 3 turns, verbose) in child
processes from the repo root with INTEGRATION_DATA_DIR=./data, the same way
check_reference_logs.py does, and compare stdout and stderr byte for byte.
"""

import os
import subprocess
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402 - registers bare "config" first
config.STATS = False  # event log + report off: not part of a test or battery (2026-11-06)
import INTEGRATION__orchestrator as orchestrator  # noqa: E402


def _run_batch(workers, extra=()):
    """stdout + stderr of a short 3-battle batch run with `workers` workers."""
    code = "\n".join(
        ["import INTEGRATION__config as config",
         f"config.WORKERS = {workers}",
         "config.NUM_SIMULATIONS = 3",
         "config.MAX_TURNS = 3",
         "config.TIMING = False",
         "config.STATS = False"]      # run times differ between the two runs
        + list(extra)
        + ["import INTEGRATION__orchestrator as orchestrator",
           "results = orchestrator.run_batch()",
           "print('seeds', [r.seed for r in results])"]
    )
    env = dict(os.environ, INTEGRATION_DATA_DIR="./data", PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, f"batch crashed (exit {proc.returncode}):\n{proc.stderr[-2000:]}"
    return proc.stdout, proc.stderr


def check_battle_seeds():
    # Battle 1 keeps the batch seed (so one-battle runs and the reference logs
    # are unchanged); later battles get their own, all different.
    assert orchestrator.battle_seed(12345, 1) == 12345
    seeds = [orchestrator.battle_seed(12345, n) for n in range(1, 101)]
    assert len(set(seeds)) == 100, "two battles of one batch share a seed"
    # Nearby batch seeds don't share battles.
    other = {orchestrator.battle_seed(12346, n) for n in range(1, 101)}
    assert not (set(seeds) & other), "batches seeded 12345 and 12346 share a battle"
    assert orchestrator.battle_seed(None, 5) is None
    # Same inputs, same seed, every time (it's what makes a batch reproducible).
    assert orchestrator.battle_seed(7, 3) == orchestrator.battle_seed(7, 3)


def check_worker_count():
    saved = config.WORKERS, config.MANUAL_ROLLS
    try:
        config.WORKERS, config.MANUAL_ROLLS = 4, False
        assert orchestrator.worker_count(1) == 1      # one battle: no extra processes
        assert orchestrator.worker_count(2) == 2      # never more workers than battles
        assert orchestrator.worker_count(10) == 4
        config.WORKERS = 1
        assert orchestrator.worker_count(10) == 1
        config.WORKERS = 0                            # one per core
        assert orchestrator.worker_count(10_000) == (os.cpu_count() or 1)
        config.WORKERS, config.MANUAL_ROLLS = 4, True
        assert orchestrator.worker_count(10) == 1     # manual rolls ask for input: one at a time
    finally:
        config.WORKERS, config.MANUAL_ROLLS = saved


def check_parallel_matches_serial():
    serial = _run_batch(1)
    parallel = _run_batch(3)
    assert "=== SIMULATION 3/3 ===" in serial[0], "the batch didn't run three battles"
    assert serial[0] == parallel[0], "stdout differs between 1 and 3 workers"
    assert serial[1] == parallel[1], "stderr differs between 1 and 3 workers"


def check_parallel_keeps_runtime_settings():
    # Workers start fresh and re-import config, so settings changed at run time
    # (here: another mech, its heat limit, verbose off) must be handed over.
    extra = ['config.MECH_BLUE_MTF = "TEST_Heat_Gear.mtf"',
             'config.MECH_BLUE_CONFIG["max_heat"] = 30',
             "config.VERBOSE = False"]
    serial = _run_batch(1, extra)
    parallel = _run_batch(3, extra)
    assert "TEST Heat Gear" in serial[0], "the Blue mech setting was not applied"
    assert "=== SIMULATION" not in serial[0], "VERBOSE = False was not applied"
    assert serial == parallel, "a run-time setting didn't reach the workers"


CHECKS = [check_battle_seeds, check_worker_count, check_parallel_matches_serial,
          check_parallel_keeps_runtime_settings]


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
    print(f"All {len(CHECKS)} parallel batch checks passed." if not failed
          else f"{failed} of {len(CHECKS)} parallel batch checks FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
