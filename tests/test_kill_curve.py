"""
tests/test_kill_curve.py - checks the kill curve and Gladiator's fire director
(2026-10-29, INTEGRATION__kill_curve): the chance of a mission kill from N more
damage, built on the engine's damage code with its own dice; and the target
choice that adds the most kill chance, friends' declared fire counted.

    python tests/test_kill_curve.py
"""

import io
import os
import sys
import traceback
from contextlib import redirect_stdout

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__bots as bots  # noqa: E402
import INTEGRATION__forces as forces  # noqa: E402
import INTEGRATION__kill_curve as kill_curve  # noqa: E402
import INTEGRATION__princess_fire as princess_fire  # noqa: E402
from test_multi_unit import ATLAS, COMMANDO, TERRAIN, fresh  # noqa: E402 - builds the units and the board
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def a_curve_rises_from_zero_and_a_light_mech_dies_sooner():
    kill_curve.clear_cache()
    atlas, commando = fresh(ATLAS, "0808", "N", "A"), fresh(COMMANDO, "0806", "S", "C")
    for m in (atlas, commando):
        f = [kill_curve.chance(m, "front", n) for n in range(0, 201, 5)]
        assert f[0] == 0.0 and all(b >= a for a, b in zip(f, f[1:])), f
    assert kill_curve.chance(commando, "front", 100) == 1.0                # 4 tons of armor less than 100
    assert kill_curve.chance(atlas, "front", 50) < kill_curve.chance(commando, "front", 50)
    assert kill_curve.expected_damage_to_kill(commando, "front") < kill_curve.expected_damage_to_kill(atlas, "front")


@check
def the_trials_never_touch_the_battles_dice_and_repeat_exactly():
    kill_curve.clear_cache()
    atlas = fresh(ATLAS, "0808", "N", "A")
    armor = {loc: dict(v) for loc, v in atlas.locations.items()}
    with ScriptedDice([3, 4, 5]) as dice:                  # a test's scripted dice stand for the battle's
        first = list(kill_curve.kills_at(atlas, "rear"))
        assert dice.count == 0
        assert [config.roll_2d6() for _ in range(3)] == [3, 4, 5]
    kill_curve.clear_cache()
    assert kill_curve.kills_at(atlas, "rear") == first     # same design, side and state: same trials
    assert atlas.locations == armor and not atlas.destroyed and atlas.pilot_hits == 0   # the 'Mech is untouched


@check
def damage_already_taken_raises_the_curve_and_is_a_new_cache_entry():
    kill_curve.clear_cache()
    atlas = fresh(ATLAS, "0808", "N", "A")
    before = kill_curve.chance(atlas, "front", 60)
    attack_resolution.apply_damage(atlas, "Center Torso", 50, armor_field="armor")   # armor gone, structure cut
    assert kill_curve.chance(atlas, "front", 60) > before


@check
def a_mission_kill_is_destroyed_unless_the_stub_says_guns_count():
    atlas = fresh(ATLAS, "0808", "N", "A")
    saved = config.STUB_MISSION_KILL
    try:
        config.STUB_MISSION_KILL = "destroyed"
        assert not kill_curve.mission_killed(atlas)
        for w in attack_resolution.get_weapons(atlas):      # every gun destroyed
            atlas.destroyed_slot_info[("test", id(w))] = {"name": w.name, "instance_id": id(w)}
        assert not kill_curve.mission_killed(atlas)          # it can still move, kick and spot
        config.STUB_MISSION_KILL = "no_ranged_weapons"
        assert kill_curve.mission_killed(atlas)
    finally:
        config.STUB_MISSION_KILL = saved


@check
def the_fire_director_finishes_a_wreck_then_turns_once_friends_have_it():
    """Two Gladiator Atlases against two Commandos: one Commando's centre torso is
    open, so the most kill chance is there; once the team has declared enough to
    kill it, the next pick goes to the other Commando (no overkill)."""
    a1, a2 = fresh(ATLAS, "0808", "N", "A 1", "A"), fresh(ATLAS, "0908", "N", "A 2", "A")
    b1, b2 = fresh(COMMANDO, "0806", "S", "B 1", "B"), fresh(COMMANDO, "0805", "S", "B 2", "B")
    units = [a1, a2, b1, b2]
    for m in units:
        m.bot = "gladiator"
    forces.set_battle(units)
    princess_fire.reset_assigned()
    kill_curve.clear_cache()
    attack_resolution.apply_damage(b2, "Center Torso", b2.locations["Center Torso"]["armor"] + 4,
                                   armor_field="armor")
    saved = config.STUB_GLADIATOR_TARGET
    config.STUB_GLADIATOR_TARGET = "kill_curve"
    try:
        assert bots.choose_target(a2, units, TERRAIN) is b2
        princess_fire.assign_damage("A", b2, 200)                 # friends' fire: b2 is as good as dead
        assert bots.choose_target(a2, units, TERRAIN) is b1
        assert bots.records_declared_damage(a2)
    finally:
        config.STUB_GLADIATOR_TARGET = saved
        princess_fire.reset_assigned()


def run_all():
    failed = 0
    for fn in CHECKS:
        try:
            with ScriptedDice([], default=7), redirect_stdout(io.StringIO()):
                fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print()
    if failed:
        print(f"{failed} of {len(CHECKS)} kill curve checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} kill curve checks passed.")


if __name__ == "__main__":
    run_all()
