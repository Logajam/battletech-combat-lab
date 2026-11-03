"""
tests/test_saved_state.py - checks saved states (2026-11-03, INTEGRATION__saved_state).

    python tests/test_saved_state.py

A battle saved at the end of a turn and loaded again must play on exactly as the battle
that never stopped: same log, same result. The reference battles check that for duels
(`python tests/check_reference_logs.py --round-trip`); these checks add team battles
(Legate's and Princess's memories), the files themselves, fresh dice, and the settings.
"""

import glob
import io
import json
import os
import shutil
import sys
import tempfile
import traceback
from contextlib import redirect_stdout, redirect_stderr

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__saved_state as saved_state  # noqa: E402

config.VERBOSE = True             # the log is what is compared
config.TIMING = False
with redirect_stdout(io.StringIO()):
    TERRAIN = orchestrator._load_map()

TEAMS = [{"team": "Red", "mtf": "Kintaro KTO-19.mtf", "count": 2, "bot": "gladiator"},
         {"team": "Blue", "mtf": "Atlas AS7-K.mtf", "count": 1, "bot": "princess"},
         {"team": "Blue", "mtf": "Hammerhead.mtf", "count": 1, "bot": "princess"}]


def battle(entries, seed, max_turns, **settings):
    """(log, result) of one battle under `settings` (config names -> values)."""
    names = ["FORCES", "DEPLOYMENT_DEPTH", "WORKERS", "REPLAY_BATTLES"] + list(settings)
    saved = {n: getattr(config, n) for n in names}
    config.FORCES, config.DEPLOYMENT_DEPTH, config.WORKERS, config.REPLAY_BATTLES = entries, 0, 1, 0
    for n, v in settings.items():
        setattr(config, n, v)
    out = io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            roster = config.load_roster()
            result = orchestrator._run_one_roster(1, 1, seed, max_turns, roster, TERRAIN)
    finally:
        for n, v in saved.items():
            setattr(config, n, v)
    return out.getvalue(), result


def outcome(result):
    return (result.turns_taken, result.winner,
            {k: (s.final_hp, s.destroyed, s.final_hex) for k, s in result.units.items()})


def turn_text(log, turn):
    """The log from turn `turn` on."""
    i = log.index(f"\n=== TURN {turn} ===")
    return log[i:]


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def a_team_battle_reloaded_every_turn_plays_exactly_the_same():
    """Gladiator with Legate (its team-fire cache by unit) against Princess's team
    (heat map, posture, last known hexes by unit)."""
    log, result = battle(TEAMS, seed=9, max_turns=8)
    log_rt, result_rt = battle(TEAMS, seed=9, max_turns=8, SAVE_STATE_ROUND_TRIP=True)
    assert result.turns_taken >= 4, result.turns_taken
    assert log_rt == log, "the reloaded battle's log differs"
    assert outcome(result_rt) == outcome(result)


@check
def legates_team_fire_options_survive_a_reload_too():
    """LEGATE_TEAM_VALUE (off by default) fills Legate's team-fire cache, kept from turn
    to turn by unit; HERDING and COHESION read the team's estimated spots."""
    opts = dict(LEGATE_TEAM_VALUE="sum", LEGATE_HERDING=True, LEGATE_COHESION=True)
    log, result = battle(TEAMS, seed=9, max_turns=6, **opts)
    log_rt, result_rt = battle(TEAMS, seed=9, max_turns=6, SAVE_STATE_ROUND_TRIP=True, **opts)
    assert log_rt == log, "the reloaded battle's log differs"
    assert outcome(result_rt) == outcome(result)


@check
def a_saved_file_plays_on_like_the_battle_that_never_stopped():
    folder = tempfile.mkdtemp()
    try:
        log, result = battle(TEAMS, seed=9, max_turns=8, SAVE_STATE_TURNS=(3,), SAVE_STATE_DIR=folder)
        files = glob.glob(os.path.join(folder, "*.json"))
        assert [os.path.basename(f) for f in files] == ["battle1_seed9_turn003.json"], files
        with open(files[0], encoding="utf-8") as f:
            header = json.load(f)
        assert header["turn"] == 3 and header["seed"] == 9 and header["version"] == saved_state.VERSION
        assert set(header["units"]) == set(result.units) and all("hex" in u for u in header["units"].values())
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            played = saved_state.play_on_from(files[0])
        assert outcome(played) == outcome(result)
        assert turn_text(out.getvalue(), 4) == turn_text(log, 4)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@check
def fresh_dice_branch_off_and_the_same_dice_do_not():
    folder = tempfile.mkdtemp()
    try:
        with redirect_stdout(io.StringIO()):
            log, _ = battle(TEAMS, seed=9, max_turns=8, SAVE_STATE_TURNS="all", SAVE_STATE_DIR=folder)
        path = os.path.join(folder, "battle1_seed9_turn002.json")
        runs = []
        for dice in (None, None, 777):
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                saved_state.play_on_from(path, turns=2, fresh_dice=dice)
            runs.append(turn_text(out.getvalue(), 3))
        assert runs[0] == runs[1]                      # the same dice: the same turns, every time
        assert runs[0] != runs[2]                      # fresh dice: a different battle from here
        assert runs[0].split("\n=== TURN 5 ===")[0] == turn_text(log, 3).split("\n=== TURN 5 ===")[0]
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@check
def loading_puts_the_saved_settings_back():
    folder = tempfile.mkdtemp()
    try:
        with redirect_stdout(io.StringIO()):
            battle(TEAMS, seed=9, max_turns=3, SAVE_STATE_TURNS=(1,), SAVE_STATE_DIR=folder, LEGATE_HERDING=True)
        assert not config.LEGATE_HERDING                     # the battle() helper put it back
        path = os.path.join(folder, "battle1_seed9_turn001.json")
        before = config.LEGATE_HERDING
        try:
            saved_state.load(path, apply_settings=False)
            assert config.LEGATE_HERDING == before          # kept today's
            saved_state.load(path)
            assert config.LEGATE_HERDING is True            # the battle's own
        finally:
            config.LEGATE_HERDING = before
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@check
def not_a_saved_state_is_refused():
    for bad in ({"format": "something else"}, {"format": saved_state.FORMAT, "version": 999}):
        try:
            saved_state.restore(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


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
    config.set_active_rng(None)
    print()
    if failed:
        print(f"{failed} of {len(CHECKS)} saved-state checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} saved-state checks passed.")


if __name__ == "__main__":
    run_all()
