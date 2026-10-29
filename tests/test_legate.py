"""
tests/test_legate.py - checks Legate (2026-10-28, INTEGRATION__legate): the start-of-phase IF/THEN estimate of
where the enemy force will move, its hex-conflict cascade and loop lock, the choice of foe, and the other
enemies' damage in a Gladiator's move score. Off (config.LEGATE False) and in a duel nothing changes.

    python tests/test_legate.py
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
import INTEGRATION__bots as bots  # noqa: E402
import INTEGRATION__forces as forces  # noqa: E402
import INTEGRATION__legate as legate  # noqa: E402
import INTEGRATION__movement_selection as movement_selection  # noqa: E402
from test_multi_unit import ATLAS, COMMANDO, TERRAIN, fresh  # noqa: E402 - builds the units and the board
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


class Spot:
    """A stand-in for a prepared state: resolve() reads only .label."""

    def __init__(self, label):
        self.label = label


class Who:
    def __init__(self, name):
        self.name = name


def line_up():
    """Two Gladiator Atlases (team A) against three Commandos (team B), all in sight of each other."""
    a1, a2 = fresh(ATLAS, "0808", "N", "A 1", "A"), fresh(ATLAS, "0908", "N", "A 2", "A")
    b1 = fresh(COMMANDO, "0805", "S", "B 1", "B")
    b2 = fresh(COMMANDO, "0806", "S", "B 2", "B")
    b3 = fresh(COMMANDO, "0905", "S", "B 3", "B")
    units = [a1, a2, b1, b2, b3]
    for u in units:
        u.bot = "gladiator"
        u.moved_this_turn = False
    forces.set_battle(units)
    return units


class Legate_on:
    def __enter__(self):
        self.old = config.LEGATE
        config.LEGATE = True
        legate.reset()

    def __exit__(self, *exc):
        config.LEGATE = self.old
        legate.reset()


@check
def two_units_after_one_hex_the_higher_score_keeps_it():
    a, b = Who("a"), Who("b")
    got = legate.resolve([(a, [(9.0, Spot("0101")), (5.0, Spot("0102"))]),
                          (b, [(7.0, Spot("0101")), (6.0, Spot("0103"))])], {})
    assert got[a][1].label == "0101" and got[b][1].label == "0103"


@check
def a_lost_hex_can_displace_a_third_unit_in_a_cascade():
    # A and B both want hex 1 (A scores higher); B's next choice, hex 2, is held by C with a lower score; C moves to hex 3.
    a, b, c = Who("a"), Who("b"), Who("c")
    got = legate.resolve([(c, [(3.0, Spot("0102")), (2.0, Spot("0103"))]),
                          (a, [(9.0, Spot("0101"))]),
                          (b, [(7.0, Spot("0101")), (5.0, Spot("0102"))])], {})
    assert got[a][1].label == "0101" and got[b][1].label == "0102" and got[c][1].label == "0103"


@check
def a_locked_units_hex_is_closed_to_everyone():
    a, b = Who("a"), Who("b")
    got = legate.resolve([(a, [(9.0, Spot("0101")), (1.0, Spot("0104"))])], {b: "0101"})
    assert got[a][1].label == "0104"


@check
def a_unit_with_nothing_left_is_not_placed():
    a, b = Who("a"), Who("b")
    got = legate.resolve([(a, [(9.0, Spot("0101"))]), (b, [(5.0, Spot("0101"))])], {})
    assert a in got and b not in got


@check
def off_and_in_a_duel_there_is_no_plan():
    units = line_up()
    saved, config.LEGATE = config.LEGATE, False                # switched off (on by default since 2026-10-29)
    try:
        legate.plan_turn(units, TERRAIN)
    finally:
        config.LEGATE = saved
    assert legate._PLANS == {}
    duel = [fresh(ATLAS, "0808", "N", "A 1", "A"), fresh(COMMANDO, "0805", "S", "B 1", "B")]
    for u in duel:
        u.bot, u.moved_this_turn = "gladiator", False
    forces.set_battle(duel)
    with Legate_on():
        legate.plan_turn(duel, TERRAIN)
        assert legate._PLANS == {}                             # one enemy: nothing to add
        assert legate.foe_for(duel[0], duel, TERRAIN) is None
        assert bots.choose_foe(duel[0], duel, TERRAIN) is duel[1]


@check
def the_estimate_places_every_enemy_in_its_own_hex_off_the_askers():
    units = line_up()
    a1, a2, b1, b2, b3 = units
    with Legate_on():
        legate.plan_turn(units, TERRAIN)
        plan = legate._PLANS["A"]
        assert set(plan) == {id(b1), id(b2), id(b3)}
        hexes = [plan[id(b)][0] for b in (b1, b2, b3)]
        assert len(set(hexes)) == 3                            # no two enemies share a hex
        assert not set(hexes) & {a1.hex, a2.hex}               # none on a hex the asker stands on
        assert "B" in legate._PLANS                            # the Commandos' side has a Gladiator too
        first = dict(plan)
        legate.plan_turn(units, TERRAIN)
        assert legate._PLANS["A"] == first                     # deterministic


@check
def a_spent_plan_is_cleared_with_the_phase():
    units = line_up()
    with Legate_on():
        legate.plan_turn(units, TERRAIN)
        assert legate._PLANS
        legate.end_phase()
        assert legate._PLANS == {} and legate._RATES == {}


@check
def the_foe_is_a_threat_among_those_yet_to_move():
    units = line_up()
    a1, a2, b1, b2, b3 = units
    with Legate_on():
        legate.plan_turn(units, TERRAIN)
        foe = bots.choose_foe(a1, units, TERRAIN)
        assert foe in (b1, b2, b3)
        for b in (b1, b2):
            b.moved_this_turn = True
        assert bots.choose_foe(a1, units, TERRAIN) is b3      # the only one yet to move
        b3.moved_this_turn = True
        assert bots.choose_foe(a1, units, TERRAIN) in (b1, b2, b3)   # all moved: the most threatening of them


@check
def a_foe_that_has_moved_is_taken_where_it_really_is():
    units = line_up()
    a1, a2, b1, b2, b3 = units
    with Legate_on():
        legate.plan_turn(units, TERRAIN)
        b1.moved_this_turn, b1.hex, b1.facing, b1.move_fc, b1.move_mode, b1.mp_spent = True, "0804", "S", 1, "Walk", 1
        assert legate.foe_state("A", b1) == ("0804", "S", 1, "Walk", 1)
        assert legate.foe_state("A", b2) == legate.estimate_for("A", b2) != ("0804", "S", 1, "Walk", 1)


@check
def several_foes_add_up_the_damage_taken_and_take_the_best_damage_dealt():
    units = line_up()
    a1, a2, b1, b2, b3 = units
    with Legate_on():
        legate.plan_turn(units, TERRAIN)
        extras = legate.Extras(a1, b1, units, TERRAIN, movement_selection._Side(a1))
        assert extras.count == 2                                # the two enemies other than the foe
        spot = movement_selection.ranged_combat.prepare_options(a1, [(*movement_selection.hex_geometry.parse_hex_label(a1.hex), 0, 0, "Stand Still", 0)])[0]
        d, r, dm, rm = extras.adjust(spot, 5.0, 4.0, 1.0, 1.0)
        assert d >= 5.0 and r >= 4.0 and dm == rm == 1.0       # taken only grows, dealt is never less


@check
def the_picker_score_sums_their_future_damage_and_takes_my_best():
    a1, a2, b1, b2, b3 = line_up()
    legate._RATES.clear()
    legate._RATES[(id(a1), id(b1))] = (10.0, 4.0)
    legate._RATES[(id(a1), id(b2))] = (6.0, 5.0)
    saved = config.LEGATE_FIRE_SPLIT
    config.LEGATE_FIRE_SPLIT = "none"                          # every enemy's fire all on me
    try:
        obj = legate.MultiLifetime(a1, [b1, b2])
    finally:
        config.LEGATE_FIRE_SPLIT = saved
    assert obj.mine == 10.0 and obj.theirs == 9.0              # best of mine, sum of theirs
    hp = movement_selection.effective_hp(a1)
    assert abs(obj(3.0, 20.0, 1.0, 1.0, 0.0) - (3.0 + (hp - 20.0) / 9.0 * 10.0)) < 1e-9
    assert obj(3.0, hp + 1, 1.0, 1.0, 0.0) == 3.0              # destroyed: only what it dealt
    legate._RATES.clear()


@check
def an_enemys_future_fire_is_shared_over_the_team_it_can_reach():
    """LEGATE_FIRE_SPLIT "proportional" (2026-10-29): an enemy that hurts both Atlases alike sends me
    half its fire; one that can only hurt me sends me all of it."""
    a1, a2, b1, b2, b3 = line_up()
    legate._RATES.clear()
    for foe, on_a1, on_a2 in ((b1, 4.0, 4.0), (b2, 5.0, 0.0)):
        legate._RATES[(id(foe), id(a1))], legate._RATES[(id(a1), id(foe))] = (on_a1, 7.0), (7.0, on_a1)
        legate._RATES[(id(foe), id(a2))], legate._RATES[(id(a2), id(foe))] = (on_a2, 7.0), (7.0, on_a2)
    saved = config.LEGATE_FIRE_SPLIT
    config.LEGATE_FIRE_SPLIT = "proportional"
    try:
        assert legate.fire_share(b1, a1) == 0.5 and legate.fire_share(b2, a1) == 1.0
        assert legate.MultiLifetime(a1, [b1, b2]).theirs == 4.0 * 0.5 + 5.0
    finally:
        config.LEGATE_FIRE_SPLIT = saved
        legate._RATES.clear()


@check
def herding_charges_a_threatened_spot_beyond_every_seeing_friends_support():
    """LEGATE_HERDING (2026-10-29, Daniel's shape): an Atlas whose friend stands beside it pays nothing;
    far beyond the friend's medium range (where an enemy can still reach it) it pays per hex; standing
    still the friend supports to its long range."""
    a1, a2, b1, b2, b3 = line_up()
    with Legate_on():
        herd = legate._Herd(a1, [a1, a2, b1, b2, b3], TERRAIN)
        assert herd.gap(movement_selection.hex_geometry.parse_hex_label(a1.hex)) == 0.0   # a2 next door
        assert 0 < legate.support_range(a2, False) < legate.support_range(a2, True)   # 14 v 21 hexes
        xy_a2 = movement_selection.hex_geometry.parse_hex_label(a2.hex)
        herd.friends = [(xy_a2, 3, set(range(len(herd.threats))))]                     # supports 3 hexes out
        herd._memo.clear()
        spots = [movement_selection.hex_geometry.parse_hex_label(l) for l in TERRAIN["hexes"]]
        threatened = [xy for xy in spots if any(legate.hex_distance(xy, exy) <= r for exy, r in herd.threats)]
        five_out = [xy for xy in threatened if legate.hex_distance(xy, xy_a2) == 5]
        assert five_out
        assert all(herd.gap(xy) == 2.0 and herd.penalty(xy) == config.LEGATE_HERD_WEIGHT * 2.0 for xy in five_out)
        herd.friends = [(xy_a2, 3, set())]                       # it sees none of the threats: no support
        herd._memo.clear()
        assert herd.gap(five_out[0]) == config.LEGATE_HERD_UNSEEN_GAP
        safe = [xy for xy in spots if xy not in threatened]
        assert not safe or herd.gap(safe[0]) == 0.0              # nothing reaches it: no gap


@check
def a_gladiator_picks_a_move_with_legate_and_without():
    units = line_up()
    a1, a2, b1, b2, b3 = units
    from INTEGRATION__rng import BattleRNG
    with Legate_on():
        legate.plan_turn(units, TERRAIN)
        for flag in (True, False):
            config.LEGATE = flag
            a1.blocked_hex = forces.blocked_xy(a1, units)
            a1.other_unit_hexes = forces.occupied_labels(a1, units)
            try:
                foe = bots.choose_foe(a1, units, TERRAIN)
                pick, note = bots.choose_movement(a1, foe, TERRAIN, BattleRNG(1), True)
            finally:
                a1.blocked_hex = a1.other_unit_hexes = None
            assert pick is not None and note
            assert ("enemies' future on me" in note) == flag     # Legate's own score text only when on


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
        print(f"{failed} of {len(CHECKS)} Legate checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} Legate checks passed.")


if __name__ == "__main__":
    run_all()
