"""
tests/test_multi_unit.py - checks the multi-unit battle (2026-10-28,
INTEGRATION__forces / INTEGRATION__domino): teams, Initiative for any number
of sides, the Unequal Numbers rule (Core p.41's tables), who a unit plans
against and shoots at, stacking, home edges for three and four teams, the
domino effect and the accidental fall from above (pp.113-116), and whole
battles with three sides and with a lance against a lance - plus that a
two-'Mech battle fielded as FORCES is the same battle it always was.

    python tests/test_multi_unit.py

Real units come from data/meks.zip (extracted to a temporary folder).
"""

import copy
import io
import os
import sys
import tempfile
import traceback
import zipfile
from contextlib import redirect_stdout, redirect_stderr

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__forces as forces  # noqa: E402
import INTEGRATION__physical as physical  # noqa: E402
import INTEGRATION__movement_selection as movement_selection  # noqa: E402
from INTEGRATION__rng import BattleRNG  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from mech_state import clone_mech, is_destroyed  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
with redirect_stdout(io.StringIO()):
    TERRAIN = orchestrator._load_map()
_TMP = tempfile.mkdtemp()


def unit_file(name):
    with zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip")) as z:
        path = z.extract(f"meks/3039u/{name}.mtf", _TMP)
    with redirect_stdout(io.StringIO()):
        return parse_mtf(path)


CHARGER = unit_file("Charger CGR-1A1")
ATLAS = unit_file("Atlas AS7-D")
COMMANDO = unit_file("Commando COM-2D")


def fresh(template, hex_, facing="N", name="Test", team=None, piloting=5):
    m = clone_mech(template)
    orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": piloting,
                                         "min_heat": 0, "max_heat": 30, "team": team or name}, name)
    m.charging = None
    return m


def crowd(sizes, template=COMMANDO):
    """{team: count} -> units named 'A 1', 'A 2', ... all in far-off hexes."""
    units = []
    for team, n in sizes.items():
        for i in range(n):
            units.append(fresh(template, None, "N", f"{team} {i + 1}", team))
    return units


class Rolls:
    """Dice by prompt: the charge hits, hit locations are 7, a PSR rolls `psr`
    (a domino PSR `domino` if given), the fall-from-above attack `attack`, and
    everything else (criticals...) a harmless 2."""

    def __init__(self, psr=12, domino=None, attack=12):
        self.psr, self.domino, self.attack = psr, domino, attack

    def __enter__(self):
        self.real, self.real_pick = config.roll_2d6, config.pick_number

        def roll(prompt=""):
            if "Charge attack" in prompt:
                return 12
            if "fall from above attack" in prompt:
                return self.attack
            if "location" in prompt:
                return 7
            if "Domino" in prompt and self.domino is not None:
                return self.domino
            if "PSR" in prompt or "Seatbelt" in prompt or "onsciousness" in prompt:
                return self.psr
            return 2
        config.roll_2d6 = roll
        config.pick_number = lambda n, prompt="": 1
        return self

    def __exit__(self, *exc):
        config.roll_2d6, config.pick_number = self.real, self.real_pick


def phase(units, a, t, tm):
    """The Physical Attack Phase with `a` (charging) and `t` the only fighters."""
    physical.run_physical_units(units, lambda u: t if u is a else (a if u is t else None), tm, {})


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def selections(units, order):
    """The team of each selection, in order."""
    return [u.team for u in forces.activation_sequence(units, order, lambda u: True)]


# =============================================================================
# ==========================  WHO ACTS WHEN  ==================================
# =============================================================================
@check
def unequal_numbers_follow_the_books_tables():
    """p.41, example 1 (18 against 10, the bigger side lost Initiative): A moves
    two, B one, until 2 against 2, then one each. Example 2 (14 against 5,
    the smaller side lost): B one, A three, ..., A two to finish."""
    seq = selections(crowd({"A": 18, "B": 10}), ["A", "B"])
    assert len(seq) == 28
    runs = []
    for team in seq:
        if runs and runs[-1][0] == team:
            runs[-1][1] += 1
        else:
            runs.append([team, 1])
    assert [r[1] for r in runs[:16]] == [2, 1] * 8, runs
    assert [r[1] for r in runs[16:]] == [1, 1, 1, 1], runs
    seq = selections(crowd({"A": 14, "B": 5}), ["B", "A"])
    runs = []
    for team in seq:
        if runs and runs[-1][0] == team:
            runs[-1][1] += 1
        else:
            runs.append([team, 1])
    assert [r[1] for r in runs] == [1, 3, 1, 3, 1, 3, 1, 3, 1, 2], runs


@check
def equal_sides_alternate_one_at_a_time():
    assert selections(crowd({"A": 4, "B": 4}), ["B", "A"]) == ["B", "A"] * 4


@check
def three_sides_take_turns_by_the_same_rule():
    """The book gives only the two-sided table; with three sides each takes
    ceil(its units / the smallest other side) at a time (PROJECT_MAP Section 6)."""
    seq = selections(crowd({"A": 6, "B": 2, "C": 2}), ["B", "C", "A"])
    assert seq[:5] == ["B", "C", "A", "A", "A"], seq
    assert sorted(seq) == ["A"] * 6 + ["B"] * 2 + ["C"] * 2
    assert selections(crowd({"A": 1, "B": 1, "C": 1, "D": 1}), ["C", "A", "D", "B"]) == ["C", "A", "D", "B"]


@check
def units_that_cannot_select_go_ahead_of_their_side():
    """p.41: a shut-down or unconscious 'Mech is left out of the tally; it is
    still processed, ahead of its own side's first selection."""
    units = crowd({"A": 2, "B": 2})
    units[0].shutdown = True                                          # A 1
    seq = [u.side_name for u in forces.activation_sequence(units, ["A", "B"], forces.can_select_fire)]
    assert seq[0] == "A 1", seq
    # A has one selection against B's two, so B takes... one at a time: A 2, B 1, B 2 after A 1 (no selection)
    assert seq == ["A 1", "A 2", "B 1", "B 2"], seq


@check
def three_sides_roll_initiative_lowest_first_and_reroll_ties():
    class R:
        def __init__(self, values):
            self.values = iter(values)

        def roll_2d6(self):
            return next(self.values)
    assert forces.initiative_order(["A", "B", "C"], R([7, 5, 9])) == ["B", "A", "C"]
    assert forces.initiative_order(["A", "B", "C"], R([6, 6, 6, 7, 4, 8])) == ["B", "A", "C"]   # all tie, roll again
    assert forces.initiative_order(["A", "B", "C"], R([5, 9, 5, 3, 6])) == ["A", "C", "B"]      # A and C tie: they re-roll
    assert forces.initiative_order(["Red", "Blue"], R([8, 8, 4, 9])) == ["Red", "Blue"]          # two sides: the old reroll


# =============================================================================
# ==========================  WHOM A UNIT FIGHTS  =============================
# =============================================================================
@check
def foe_is_the_nearest_enemy_and_friends_are_not_foes():
    a1, a2 = fresh(COMMANDO, "0505", "N", "A 1", "A"), fresh(COMMANDO, "0506", "N", "A 2", "A")
    b1, c1 = fresh(COMMANDO, "0508", "N", "B 1", "B"), fresh(COMMANDO, "0515", "N", "C 1", "C")
    units = [a1, a2, b1, c1]
    assert forces.choose_foe(a1, units) is b1 and forces.choose_foe(a2, units) is b1
    assert a2 not in forces.enemies_of(a1, units) and a1 not in forces.enemies_of(a1, units)
    b1.destroyed = True
    assert forces.choose_foe(a1, units) is c1
    c1.hex = None                                                     # not on the board yet
    assert forces.choose_foe(a1, units) is c1                         # still the only enemy left
    c1.destroyed = True
    assert forces.choose_foe(a1, units) is None and forces.any_enemy(a1, units) is not None


@check
def target_prefers_sight_then_a_weapon_that_bears_then_distance():
    import INTEGRATION__attack_resolution as attack_resolution
    a = fresh(ATLAS, "0808", "N", "A", "A")
    near, far = fresh(COMMANDO, "0806", "S", "B 1", "B"), fresh(COMMANDO, "0803", "S", "B 2", "B")
    units = [a, near, far]
    assert forces.choose_target(a, units, TERRAIN) is near            # both in sight, both bear: nearest
    real = attack_resolution.weapons_can_bear
    try:
        attack_resolution.weapons_can_bear = lambda attacker, target: target is far
        assert forces.choose_target(a, units, TERRAIN) is far         # no weapon bears on the near one
    finally:
        attack_resolution.weapons_can_bear = real
    adjacent = fresh(COMMANDO, "0809", "N", "B 3", "B")
    units.append(adjacent)
    assert forces.choose_target(a, units, TERRAIN, adjacent_only=True) is adjacent
    assert forces.choose_target(a, [a, near], TERRAIN, adjacent_only=True) is None
    near.team = a.team
    assert forces.choose_target(a, [a, near], TERRAIN) is None        # no enemy at all


# =============================================================================
# ==========================  THE BOARD  ======================================
# =============================================================================
@check
def home_edges_for_two_three_and_four_teams():
    """p.37 for two sides; three or four sides take the next edges, and a
    free for all of twenty shares them (PROJECT_MAP Section 6)."""
    assert orchestrator._edges_for_teams("N", 2) == ["N", "S"]
    assert orchestrator._edges_for_teams("W", 3) == ["W", "E", "N"]
    assert orchestrator._edges_for_teams("W", 4) == ["W", "E", "N", "S"]
    five = orchestrator._edges_for_teams("S", 5)
    assert five[:4] == ["S", "N", "W", "E"] and five[4] == "S"


@check
def deployment_gives_each_team_one_edge():
    units = [fresh(COMMANDO, None, "N", f"{t} {i}", t) for t in "ABC" for i in (1, 2)]
    config.HOME_EDGE_CHOICE = "N"
    try:
        orchestrator._deploy_teams(units, TERRAIN, BattleRNG(seed=3))
    finally:
        config.HOME_EDGE_CHOICE = "random"
    rows = {u.team: u.home_edge_row for u in units}
    assert len({tuple(r) for r in rows.values()}) == 3
    for u in units:
        assert u.hex is None and u.home_edge_row == rows[u.team]


@check
def a_unit_never_ends_in_another_units_hex_and_cannot_cross_a_mobile_enemy():
    mover = fresh(COMMANDO, "0808", "N", "A", "A")
    friend, foe = fresh(COMMANDO, "0807", "N", "A 2", "A"), fresh(COMMANDO, "0806", "N", "B", "B")
    units = [mover, friend, foe]
    mover.blocked_hex = forces.blocked_xy(mover, units)
    mover.other_unit_hexes = forces.occupied_labels(mover, units)
    options = movement_selection.reduced_options(mover, TERRAIN, exclude_hex=mover.other_unit_hexes)
    ends = {f"{x:02d}{y:02d}" for x, y, facing, fc, mode, mp in options}
    assert "0807" not in ends and "0806" not in ends                  # both occupied: no end state there
    assert mover.blocked_hex == frozenset({forces.hex_xy(foe)})                   # only the mobile enemy closes ground steps
    assert mover.other_unit_hexes == frozenset({"0807", "0806"})      # every other unit is a hex it can't end in
    foe.destroyed = True
    assert forces.blocked_xy(mover, units) == frozenset() and forces.occupied_labels(mover, units) == {"0807"}


# =============================================================================
# ==========================  DOMINO  =========================================
# =============================================================================
def charge_into(chain_hexes, charger_hex="0807", target_hex="0806", terrain=None):
    """A successful charge of an Atlas at target_hex; other Atlases stand in chain_hexes."""
    terrain = terrain or TERRAIN
    a, t = fresh(CHARGER, charger_hex, "N", "Red", "Red"), fresh(ATLAS, target_hex, "S", "Blue", "Blue")
    others = [fresh(ATLAS, h, "N", f"Third {i}", f"Third {i}") for i, h in enumerate(chain_hexes, 1)]
    a.hex, a.facing = charger_hex, "N"
    a.move_mode, a.move_fc, a.mp_spent = "Run", 5, 8
    a.charging = t
    forces.set_battle([a, t] + others)
    return a, t, others, terrain


@check
def domino_passed_psr_still_forces_the_third_mech_on_without_a_fall():
    a, t, (third,), tm = charge_into(["0805"])
    with Rolls(psr=12):
        phase([a, t, third], a, t, tm)
    assert t.hex == "0805" and a.hex == "0806", (t.hex, a.hex)
    assert third.hex == "0804" and not third.prone, (third.hex, third.prone)


@check
def domino_failed_psr_makes_the_third_mech_fall():
    a, t, (third,), tm = charge_into(["0805"])
    with Rolls(psr=12, domino=2):
        phase([a, t, third], a, t, tm)
    assert third.hex == "0804" and third.prone, (third.hex, third.prone)
    assert t.hex == "0805"


@check
def domino_chain_continues_and_the_last_mech_with_nowhere_to_go_is_destroyed():
    a, t, others, tm = charge_into(["0803", "0802", "0801"], charger_hex="0805", target_hex="0804")
    third, fourth, fifth = others
    with Rolls(psr=12):
        phase([a, t, third, fourth, fifth], a, t, tm)
    # the Atlas goes to 0803, third to 0802, fourth to 0801, fifth is shoved off the top edge
    assert t.hex == "0803" and third.hex == "0802" and fourth.hex == "0801", (t.hex, third.hex, fourth.hex)
    assert is_destroyed(fifth) and fifth.cause_of_death == "Displaced off the battlefield", fifth.cause_of_death


def stepped_terrain(levels):
    terrain = copy.deepcopy(TERRAIN)
    for label, level in levels.items():
        terrain["hexes"][label]["level"] = level
    return terrain


@check
def displaced_two_levels_down_onto_another_mech_is_an_accidental_fall_from_above():
    tm = stepped_terrain({"0806": 2, "0805": 0})
    a, t, (third,), _ = charge_into(["0805"], terrain=tm)
    before = physical.attack_resolution.total_hp(third)
    with Rolls(psr=12, attack=12):                                    # the falling Atlas hits
        phase([a, t, third], a, t, tm)
    assert t.hex == "0805" and t.prone, (t.hex, t.prone)              # it fell where it landed
    assert physical.attack_resolution.total_hp(third) < before        # and hurt the 'Mech under it
    assert third.hex != "0805"                                        # which was pushed out of the hex


@check
def a_missed_fall_from_above_lands_next_door_and_falls():
    tm = stepped_terrain({"0806": 2, "0805": 0})
    a, t, (third,), _ = charge_into(["0805"], terrain=tm)
    before = physical.attack_resolution.total_hp(third)
    with Rolls(psr=12, attack=2):                                     # the falling Atlas misses
        phase([a, t, third], a, t, tm)
    assert t.hex != "0805" and t.prone and third.hex == "0805", (t.hex, t.prone, third.hex)
    assert physical.attack_resolution.total_hp(third) == before


@check
def a_charger_never_advances_onto_a_mech_the_fall_pushed_into_its_targets_old_hex():
    """2026-10-29 (found in a 12 v 12 battle): the 'Mech fallen upon is displaced to a random
    neighbouring legal hex (p.116) - which may be the hex the charged target just left. The charger
    then advances into an occupied hex: a domino effect (domino.advance_into, as MegaMek), never two
    'Mechs stacked in one hex. Every displacement pick is tried."""
    for pick in range(1, 7):
        tm = stepped_terrain({"0806": 2, "0805": 0})
        a, t, (third,), _ = charge_into(["0805"], terrain=tm)
        with Rolls(psr=12, attack=12):
            config.pick_number = lambda n, prompt="", k=pick: min(k, n)
            phase([a, t, third], a, t, tm)
        spots = [m.hex for m in (a, t, third) if not is_destroyed(m)]
        assert len(spots) == len(set(spots)), (pick, a.hex, t.hex, third.hex)


# =============================================================================
# ==========================  WHOLE BATTLES  ==================================
# =============================================================================
def run_forces(entries, seed=4, max_turns=12, depth=0):
    saved = (config.FORCES, config.DEPLOYMENT_DEPTH, config.WORKERS, config.REPLAY_BATTLES, config.MAX_TURNS)
    config.FORCES, config.DEPLOYMENT_DEPTH, config.WORKERS, config.REPLAY_BATTLES = entries, depth, 1, 0
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            roster = config.load_roster()
            return orchestrator._run_one_roster(1, 1, seed, max_turns, roster, TERRAIN)
    finally:
        config.FORCES, config.DEPLOYMENT_DEPTH, config.WORKERS, config.REPLAY_BATTLES, config.MAX_TURNS = saved


ENTRY = {"mtf": "Kontio.mtf"}


@check
def a_three_way_battle_runs_and_names_every_team():
    result = run_forces([{"team": "A", "mtf": "Kontio.mtf"}, {"team": "B", "mtf": "Hammerhead.mtf"},
                         {"team": "C", "mtf": "Kontio.mtf"}], max_turns=3)
    assert list(result.teams) == ["A", "B", "C"] and set(result.units) == {"A", "B", "C"}
    assert result.turns_taken >= 1
    assert result.winner in ("A", "B", "C", "Draw")


@check
def a_lance_against_a_lance_runs_with_labelled_units():
    result = run_forces([{"team": "Red", "mtf": "Kontio.mtf", "count": 4},
                         {"team": "Blue", "mtf": "Hammerhead.mtf", "count": 4}], max_turns=2)
    assert set(result.units) == {f"Red {i}" for i in range(1, 5)} | {f"Blue {i}" for i in range(1, 5)}
    assert result.teams["Red"].units == 4 and result.red is result.teams["Red"]
    assert result.winner in ("Red", "Blue", "Draw")


@check
def a_five_unit_free_for_all_has_one_team_per_unit():
    result = run_forces([{"team": f"U{i}", "mtf": "Kontio.mtf"} for i in range(1, 6)], max_turns=2)
    assert len(result.teams) == 5 and all(t.units == 1 for t in result.teams.values())


@check
def a_two_mech_battle_fielded_as_forces_is_the_same_battle():
    """FORCES with one Red and one Blue unit, configured as the defaults are,
    plays exactly the default battle (same seed, same dice)."""
    saved_depth = config.DEPLOYMENT_DEPTH
    config.DEPLOYMENT_DEPTH = 0
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            red, blue, _, _ = config.load_two_mechs()
            legacy = orchestrator._run_one_battle(1, 1, 11, 8, red, blue, TERRAIN)
        forced = run_forces([dict(config.MECH_RED_CONFIG, team="Red", mtf=config.MECH_RED_MTF),
                             dict(config.MECH_BLUE_CONFIG, team="Blue", mtf=config.MECH_BLUE_MTF)],
                            seed=11, max_turns=8, depth=0)
    finally:
        config.DEPLOYMENT_DEPTH = saved_depth
    assert (legacy.turns_taken, legacy.red.final_hp, legacy.blue.final_hp, legacy.winner) == \
           (forced.turns_taken, forced.red.final_hp, forced.blue.final_hp, forced.winner)


@check
def no_two_standing_units_share_a_hex_after_a_battle_turn():
    """Stacking (p.49): sample a skirmish turn by turn through the replay data."""
    saved = config.REPLAY_BATTLES
    config.FORCES = [{"team": "A", "mtf": "Kontio.mtf", "count": 2}, {"team": "B", "mtf": "Hammerhead.mtf", "count": 2}]
    config.DEPLOYMENT_DEPTH, config.WORKERS, config.REPLAY_BATTLES = 0, 1, 1
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            roster = config.load_roster()
            result = orchestrator._run_one_roster(1, 1, 5, 4, roster, TERRAIN)
    finally:
        config.FORCES, config.DEPLOYMENT_DEPTH, config.REPLAY_BATTLES = None, 0, saved
    for step in result.replay["steps"]:
        if "moves" in step["phase"] or step["phase"] in ("Heat and end phase",):
            hexes = [s["hex"] for s in step["state"].values() if s["hex"] and not s["destroyed"]]
            assert len(hexes) == len(set(hexes)), (step["turn"], step["phase"], hexes)


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
        print(f"{failed} of {len(CHECKS)} multi-unit checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} multi-unit checks passed.")


if __name__ == "__main__":
    run_all()
