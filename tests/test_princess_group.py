"""
tests/test_princess_group.py - checks Princess's group behaviors (2026-10-28,
INTEGRATION__princess_group): whom a Princess unit fires at when it has several
enemies (the best firing plan, with the damage its friends have already
declared counted - MegaMek's calcDamageAllocationUtility), and that weighing a
target changes nothing (the dry run).

    python tests/test_princess_group.py
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
import INTEGRATION__arcs as arcs  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__bots as bots  # noqa: E402
import INTEGRATION__forces as forces  # noqa: E402
import INTEGRATION__princess_fire as princess_fire  # noqa: E402
import INTEGRATION__princess_group as princess_group  # noqa: E402
import INTEGRATION__princess_memory as princess_memory  # noqa: E402
import INTEGRATION__princess_modern as princess_modern  # noqa: E402
from test_multi_unit import ATLAS, COMMANDO, TERRAIN, fresh  # noqa: E402 - builds the units and the board
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def princess(template, hex_, facing, name, team):
    m = fresh(template, hex_, facing, name, team)
    m.bot = "princess"
    return m


def lance():
    """Two Princess Atlases (team A) facing two Commandos (team B) in sight."""
    a1, a2 = princess(ATLAS, "0808", "N", "A 1", "A"), princess(ATLAS, "0908", "N", "A 2", "A")
    b1, b2 = princess(COMMANDO, "0806", "S", "B 1", "B"), princess(COMMANDO, "0805", "S", "B 2", "B")
    units = [a1, a2, b1, b2]
    forces.set_battle(units)
    princess_fire.reset_assigned()
    return units


@check
def overkill_term_follows_calc_damage_allocation_utility():
    f = princess_fire.overkill_fraction
    assert f(0, 40, 100) == 0.0                    # under half the target's HP: shoot as normal
    assert abs(f(0, 60, 100) - 0.6) < 1e-9         # half or more: the fraction of its HP
    assert abs(f(30, 30, 100) - 0.6) < 1e-9        # friends' damage counts too
    assert f(100, 1, 100) == 100.0                 # friends already expect to destroy it
    assert f(150, 0, 100) == 100.0


@check
def the_damage_map_is_per_team_and_starts_empty_each_phase():
    a1, _, b1, b2 = lance()
    princess_fire.assign_damage("A", b1, 25.0)
    princess_fire.assign_damage("A", b1, 5.0)
    assert princess_fire.assigned_damage("A", b1) == 30.0
    assert princess_fire.assigned_damage("A", b2) == 0.0
    assert princess_fire.assigned_damage("C", b1) == 0.0          # another team's damage isn't ours
    princess_fire.reset_assigned()
    assert princess_fire.assigned_damage("A", b1) == 0.0


@check
def weighing_a_target_changes_nothing():
    a1, a2, b1, b2 = lance()
    lines = []
    config.set_log_sink(lines.append)
    before = (arcs.current_action(a1), a1.hex, a1.facing, a1.current_heat)
    try:
        report = attack_resolution.SideReport()
        with ScriptedDice([]) as dice:                             # no dice are scripted: a roll would fail
            got = attack_resolution.declare_attacks(a1, b1, TERRAIN, report, dry=True)
    finally:
        config.set_log_sink(None)
    assert got is not None and got[0] > 0 and got[1] > 0           # (utility, expected damage)
    assert lines == [] and report.attacks == 0 and not report.attacks_list
    assert (arcs.current_action(a1), a1.hex, a1.facing, a1.current_heat) == before
    assert princess_fire.assigned_damage("A", b1) == 0.0           # only a real declaration assigns


@check
def a_unit_turns_to_another_enemy_once_friends_have_it_covered():
    a1, a2, b1, b2 = lance()
    units = [a1, a2, b1, b2]
    first = princess_group.choose_target(a1, units, TERRAIN)
    other = b2 if first is b1 else b1
    assert first in (b1, b2)
    hp = attack_resolution.total_hp(first)
    princess_fire.assign_damage("A", first, hp * 0.9)             # friends expect 90% of it already
    assert princess_group.choose_target(a2, units, TERRAIN) is other
    princess_fire.assign_damage("A", first, hp)                   # and now they expect it dead
    assert princess_group.choose_target(a2, units, TERRAIN) is other
    princess_fire.reset_assigned()
    assert princess_group.choose_target(a2, units, TERRAIN) is first   # nothing assigned: as before
    princess_fire.assign_damage("B", first, hp)                   # the enemy's own plans don't count for us
    assert princess_group.choose_target(a2, units, TERRAIN) is first


@check
def a_phase_spreads_a_team_over_the_enemies_it_can_kill():
    a1, a2, b1, b2 = lance()
    units = [a1, a2, b1, b2]
    with ScriptedDice([], default=7), redirect_stdout(io.StringIO()):
        reports = attack_resolution.run_ranged_phase(units, lambda u: bots.choose_target(u, units, TERRAIN),
                                                     TERRAIN, None)
    assigned = {foe.side_name: princess_fire.assigned_damage("A", foe) for foe in (b1, b2)}
    assert all(v > 0 for v in assigned.values()), assigned        # each enemy got a unit's fire
    assert reports["A 1"].attacks and reports["A 2"].attacks


@check
def gladiator_and_a_duel_still_use_the_projects_pick():
    a = fresh(ATLAS, "0808", "N", "A", "A")
    near, far = fresh(COMMANDO, "0806", "S", "B 1", "B"), fresh(COMMANDO, "0803", "S", "B 2", "B")
    units = [a, near, far]
    saved = config.STUB_GLADIATOR_TARGET
    config.STUB_GLADIATOR_TARGET = "nearest"                      # the old pick, one switch away
    try:
        assert bots.choose_target(a, units, TERRAIN) is forces.choose_target(a, units, TERRAIN)
    finally:
        config.STUB_GLADIATOR_TARGET = saved
    p = princess(ATLAS, "0808", "N", "P", "P")
    duel = [p, near]
    assert bots.choose_target(p, duel, TERRAIN) is near


@check
def gladiator_borrows_princess_target_choice_and_spreads_its_fire():
    """STUB_GLADIATOR_TARGET "princess_plan" (2026-10-29): a Gladiator with two
    enemies scores them through Princess's fire control, turns away from one its
    teammates are expected to kill, and its own declaration is counted for the
    teammates after it."""
    a1, a2, b1, b2 = lance()
    a1.bot = a2.bot = "gladiator"
    units = [a1, a2, b1, b2]
    saved = config.STUB_GLADIATOR_TARGET
    config.STUB_GLADIATOR_TARGET = "princess_plan"
    try:
        with redirect_stdout(io.StringIO()):
            first = bots.choose_target(a2, units, TERRAIN)
            other = b2 if first is b1 else b1
            princess_fire.assign_damage("A", first, attack_resolution.total_hp(first))   # friends expect it dead
            assert bots.choose_target(a2, units, TERRAIN) is other
        assert a2.bot == "gladiator" and bots.fire_control(a2)[1] is None   # its own weapon choice afterwards
        princess_fire.reset_assigned()
        with ScriptedDice([], default=7), redirect_stdout(io.StringIO()):
            attack_resolution.run_ranged_phase(units, lambda u: bots.choose_target(u, units, TERRAIN), TERRAIN, None)
        assigned = {foe.side_name: princess_fire.assigned_damage("A", foe) for foe in (b1, b2)}
        assert sum(v > 0 for v in assigned.values()) >= 1, assigned       # Gladiator's fire is on the map
    finally:
        config.STUB_GLADIATOR_TARGET = saved


# =============================================================================
# ==========================  THE FORCE'S MEMORY  =============================
# =============================================================================
@check
def a_units_weight_is_its_battle_value_less_a_hundred_per_move_point():
    import INTEGRATION__battle_value as battle_value
    a1 = princess(ATLAS, "0808", "N", "A 1", "A")
    expected = battle_value.battle_value(a1) - 100 * max(a1.base_walk_mp, a1.base_jump_mp)
    assert princess_memory.unit_weight(a1) == expected and expected > 1000
    commando = princess(COMMANDO, "0808", "N", "C", "A")                  # fast and light: counts for little
    assert princess_memory.unit_weight(commando) < princess_memory.unit_weight(a1)


@check
def the_heat_map_credits_moves_fades_them_and_names_a_hot_spot():
    princess_memory.reset()
    a1, a2, b1, b2 = lance()
    heat = princess_memory.team("A").heat
    assert heat.hot_spot("0808") is None                                  # nothing yet
    princess_memory.unit_moved(a1, "0201")                                # a unit moved from 0201 to its hex
    assert heat.activity == {a1.hex: princess_memory.unit_weight(a1)}
    princess_memory.unit_moved(a2, a2.hex)                                # a unit that stayed adds nothing
    assert len(heat.activity) == 1
    a2.move_fc = 3
    princess_memory.unit_moved(a2, "0301")
    assert set(heat.activity) == {a1.hex, a2.hex}
    # The hot spot is the best-rated hex; of the top tier the one nearest the asker.
    assert heat.hot_spot("0808") in (a1.hex, a2.hex)
    # Gladiator moves are not remembered (only Princess has the map).
    g = fresh(COMMANDO, "0505", "N", "G", "A")
    g.bot = "gladiator"
    g.move_fc = 2
    princess_memory.unit_moved(g, "0501")
    assert "0505" not in heat.activity
    # Fading: a hex with no unit of ours on it halves; with one on it, loses 200.
    weight = heat.activity[a1.hex]
    a1.hex = "0810"                                                       # a1 left; its old hex is empty
    heat.last_known[id(a1)] = "0810"
    heat.age([a1, a2])
    assert heat.activity["0808"] == weight // 2
    assert heat.activity[a2.hex] == princess_memory.unit_weight(a2) - 200
    # A map that is mostly empty is cleared of its zeros.
    heat.activity = {"0101": 0, "0102": 0, "0103": 0, "0104": 5}
    heat._trim()
    assert heat.activity == {"0104": 5}
    princess_memory.reset()
    assert princess_memory.team("A").heat.activity == {}


@check
def the_hot_spot_is_the_nearest_of_the_top_rated_hexes():
    princess_memory.reset()
    heat = princess_memory.team("A").heat
    heat.activity = {"0101": 100, "0113": 100}                            # two equal hexes: both are the top tier
    assert heat._rating("0101") == heat._rating("0113")
    assert heat.hot_spot("0102") == "0101" and heat.hot_spot("0112") == "0113"     # the nearer to the asker
    heat.activity = {"0101": 100, "0113": 100, "0107": 10}                # a weak hex between them is no hot spot
    assert heat.hot_spot("0107") in ("0101", "0113")
    heat.activity = {"0707": 50}
    assert heat.hot_spot("0101") == "0707"                                # one hex: always that one
    princess_memory.reset()


# =============================================================================
# ==========================  THE MOVEMENT PICTURE  ===========================
# =============================================================================
@check
def in_a_duel_the_picture_is_the_old_one():
    princess_memory.reset()
    a1 = princess(ATLAS, "0808", "N", "A", "A")
    b1 = princess(COMMANDO, "0803", "S", "B", "B")
    group = princess_group.Group(a1, b1, [a1, b1], True)
    xy = princess_group.hex_geometry.parse_hex_label("0806")
    assert group.foes == [b1] and group.friends == []
    assert group.distance_to_enemy(xy) == princess_group.hex_distance(xy, princess_group.hex_geometry.parse_hex_label("0803"))
    assert group.face_target(xy) == princess_group.hex_geometry.parse_hex_label("0803")
    assert group.support_mod(xy) == 0.0 and group.crowding_mod(xy, 10) == 0.0   # no friends, nothing remembered


@check
def an_enemy_still_to_move_counts_as_farther_by_its_walking_mp():
    a1 = princess(ATLAS, "0808", "N", "A", "A")
    near, far = princess(COMMANDO, "0806", "S", "B 1", "B"), princess(COMMANDO, "0803", "S", "B 2", "B")
    group = princess_group.Group(a1, near, [a1, near, far], True)           # `near` is "still to move"
    xy = princess_group.hex_geometry.parse_hex_label("0808")
    near.moved_this_turn = False
    far.moved_this_turn = True                                              # `far` has moved already
    assert group.has_moved(far) and not group.has_moved(near)
    # near: 2 hexes + its walking MP (6); far: 5 hexes with no bonus -> far is the closest.
    assert group.nearest(xy)[0] is far and group.nearest(xy)[1] == 5


@check
def a_unit_faces_the_median_of_its_closest_enemies_or_the_one_beside_it():
    a1 = princess(ATLAS, "0808", "N", "A", "A")
    foes = [princess(COMMANDO, h, "S", f"B {i}", "B") for i, h in enumerate(("0403", "0405", "0407"), 1)]
    for f in foes:
        f.moved_this_turn = True
    group = princess_group.Group(a1, foes[0], [a1] + foes, False)
    spot = princess_group.hex_geometry.parse_hex_label("0808")
    target = group.face_target(spot)
    assert target == princess_group.hex_geometry.parse_hex_label("0405")    # the middle of the three
    beside = princess_group.hex_geometry.parse_hex_label("0408")
    foes[2].hex = "0408"                                                    # one 1 hex from the spot below
    spot2 = princess_group.hex_geometry.parse_hex_label("0508")
    assert group.face_target(spot2) == beside                               # beside the spot: face it
    assert princess_group.geometric_median([(0, 0), (2, 0), (4, 0)]) == (2, 0)
    assert princess_group.geometric_median([(3, 3)]) == (3, 3)


@check
def mutual_support_pulls_toward_the_hot_spot_or_the_friends_centre():
    princess_memory.reset()
    a1, a2, b1, b2 = lance()
    a1.hex, a2.hex = "0808", "0808"[:2] + "08"
    a2.hex = "0614"
    group = princess_group.Group(a1, b1, [a1, a2, b1, b2], True)
    xy = princess_group.hex_geometry.parse_hex_label
    assert group._anchor == xy("0614")                                      # one friend: its hex is the centre
    assert abs(group.support_mod(xy("0608")) - 6 * 1.0) < 1e-9              # 6 hexes x the default value 1.0
    config_value = princess_group.config.PRINCESS_BEHAVIOR["mutual_support"]
    try:
        princess_group.config.PRINCESS_BEHAVIOR["mutual_support"] = 10
        assert abs(princess_group.Group(a1, b1, [a1, a2, b1, b2], True).support_mod(xy("0608")) - 12.0) < 1e-9
    finally:
        princess_group.config.PRINCESS_BEHAVIOR["mutual_support"] = config_value
    # The heat map's hot spot, once there is one, replaces the friends' centre.
    a2.move_fc = 4
    princess_memory.unit_moved(a2, "0101")
    assert princess_group.Group(a1, b1, [a1, a2, b1, b2], True)._anchor == xy("0614")
    # Switched off: nothing pulls.
    princess_group.config.PRINCESS_GROUP = False
    try:
        assert princess_group.Group(a1, b1, [a1, a2, b1, b2], True).support_mod(xy("0608")) == 0.0
    finally:
        princess_group.config.PRINCESS_GROUP = True
    princess_memory.reset()


@check
def crowding_is_off_by_default_and_counts_friends_and_enemies_when_on():
    princess_memory.reset()
    a1, a2, b1, b2 = lance()
    xy = princess_group.hex_geometry.parse_hex_label
    group = princess_group.Group(a1, b1, [a1, a2, b1, b2], True)
    assert group.crowding_mod(xy("0807"), 12) == 0.0
    princess_group.config.PRINCESS_BEHAVIOR["anti_crowding"] = 5
    try:
        crowd = princess_group.Group(a1, b1, [a1, a2, b1, b2], True).crowding_mod(xy("0807"), 12)
    finally:
        princess_group.config.PRINCESS_BEHAVIOR["anti_crowding"] = 0
    factor = 10.0 / (11 - 5)
    assert crowd > 0 and abs(crowd / factor - round(crowd / factor)) < 1e-9     # factor x a whole count of units


@check
def several_enemies_are_combined_as_the_best_attack_and_all_the_damage_taken():
    one = {"k": (10.0, 4.0, 7.0), "j": (0.0, 0.0, 1.0)}
    two = {"k": (6.0, 9.0, 5.0), "j": (3.0, 0.0, 2.0)}
    assert princess_group.combine_estimates(one, two) == {"k": (10.0, 9.0, 12.0), "j": (3.0, 0.0, 3.0)}


@check
def the_posture_belongs_to_the_force_and_reads_its_centre():
    princess_memory.reset()
    a1, a2, b1, b2 = lance()
    a1.hex, a2.hex, b1.hex, b2.hex = "0101", "0301", "0115", "0315"        # the force's centre 0201: 14 from the foes
    for turn, hexes, want in ((1, ("0115", "0315"), "ATTACK"), (2, ("0113", "0313"), "DEFEND"),
                              (3, ("0113", "0313"), "DEFEND"), (4, ("0113", "0313"), "DEFEND"),
                              (5, ("0113", "0313"), "ATTACK")):
        b1.hex, b2.hex = hexes
        a1.turn_number = a2.turn_number = turn
        group = princess_group.Group(a1, b1, [a1, a2, b1, b2], True)
        assert princess_group.force_posture(a1, group) == want, (turn, want)
        # the force's other unit, asked the same round, gets the same answer without re-deciding
        assert princess_group.force_posture(a2, princess_group.Group(a2, b1, [a1, a2, b1, b2], True)) == want
    princess_memory.reset()


@check
def a_princess_unit_picks_a_move_with_several_enemies_and_friends():
    princess_memory.reset()
    a1, a2, b1, b2 = lance()
    a1.hex, a2.hex, b1.hex, b2.hex = "0808", "0908", "0805", "0605"
    for u in (a1, a2, b1, b2):
        u.turn_number, u.moved_this_turn = 1, False
    for version in ("modern", "0.50.07"):
        saved = config.PRINCESS_VERSION
        config.PRINCESS_VERSION = version
        try:
            pick, note = bots.choose_movement(a1, b1, TERRAIN, None, True)
        finally:
            config.PRINCESS_VERSION = saved
        assert pick is not None and "2 enemies" in note, (version, note)
    princess_memory.reset()


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
        print(f"{failed} of {len(CHECKS)} Princess group checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} Princess group checks passed.")


if __name__ == "__main__":
    run_all()
