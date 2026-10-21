"""
tests/test_ams.py - checks Anti-Missile Systems (Core Rulebook p.206,
INTEGRATION__ams, 2026-10-20): the engaged Cluster roll (-4, below 2 = no
damage), Streaks as a 7, single missiles on 1D6 4+, which attacks an AMS can
cover (its location's firing arc), the 2-a-turn limit, ammo and heat, the
crew / shutdown conditions, the laser AMS heat limit, that an AMS never fires
as a weapon, and the expected-damage numbers weapon choice and movement
scoring use.

    python tests/test_ams.py

Real units come from data/meks.zip (extracted to a temporary folder).
"""

import io
import os
import sys
import tempfile
import traceback
import zipfile
from contextlib import redirect_stdout
from types import SimpleNamespace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__ams as ams
import INTEGRATION__weapon_rules as weapon_rules  # noqa: E402
import INTEGRATION__ammo as ammo  # noqa: E402
import INTEGRATION__weapon_selection as weapon_selection  # noqa: E402
import INTEGRATION__ranged_combat as ranged_combat  # noqa: E402
import INTEGRATION__expected_damage as expected_damage  # noqa: E402
from INTEGRATION__attack_resolution import DeclaredAttack, SideReport  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from mech_state import clone_mech  # noqa: E402
from damage_resolution import get_weapons  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
with redirect_stdout(io.StringIO()):
    TERRAIN = orchestrator._load_map()
_TMP = tempfile.mkdtemp()


def unit(path):
    with zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip")) as z:
        out = z.extract(f"meks/{path}.mtf", _TMP)
    with redirect_stdout(io.StringIO()):
        return parse_mtf(out)


ATLAS_K = unit("3050U/Atlas AS7-K")        # IS AMS in the left arm, 1 ton (12 shots); LRM 20
ARCHER = unit("3039u/Archer ARC-2R")       # two LRM 20s
ATLAS_S = unit("3050U/Atlas AS7-S")        # two rear-mounted Streak SRM 2s
MORPHEUS = unit("3055U/Morpheus MRP-3T")   # IS laser AMS in the center torso
TABLE = config.CLUSTER_HITS_TABLE


def fresh(template, hex_="0808", facing="N", name="Test", max_heat=4):
    m = clone_mech(template)
    orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": 5,
                                         "min_heat": 0, "max_heat": max_heat}, name)
    return m


def weapon(mech, fragment):
    return next(w for w in get_weapons(mech) if fragment in w.name)


def hits(w, n=1):
    return [DeclaredAttack(weapon=w, tn=8, roll=9, hit=True) for _ in range(n)]


def thunderbolt():
    return SimpleNamespace(name="Thunderbolt 10", damage_type="Missile", rack_size=None, damage_per_shot=10,
                           category="weapon", heat=5)


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def every_ams_is_recognized():
    """IS / Clan, standard / laser: is_ams; laser heat 7 IS, 5 Clan (p.206)."""
    a = ams.systems(fresh(ATLAS_K))
    assert len(a) == 1 and a[0].heat == 1 and a[0].needs_ammo
    laser = ams.systems(fresh(MORPHEUS))
    assert len(laser) == 1 and laser[0].heat == 7 and not laser[0].needs_ammo
    assert ams.shots_left(fresh(ATLAS_K), a[0]) == 12 and ams.shots_left(fresh(MORPHEUS), laser[0]) == float("inf")


@check
def ams_never_fires_as_a_weapon():
    """Firing an AMS is not an attack (p.206): it is not on the expected
    damage table, so weapon choice never picks it, even next to the target."""
    m = fresh(ATLAS_K)
    a = ams.systems(m)[0]
    assert weapon_selection.build_expected_damage_table(m)[id(a)] == {}
    picked, _, _ = weapon_selection.select_weapons_to_fire(m, 1, 4, 0, 30, dissipation=20, movement_heat=0)
    assert a not in picked and picked


@check
def expected_damage_numbers():
    """LRM 20 engaged: the -4 roll, below 2 nothing; Streak SRM 2: a 7 on the
    2 column; a single missile: half (1D6 4+ destroys it)."""
    lrm = weapon(fresh(ARCHER), "LRM")
    want = sum(p * TABLE[min(12, r - 4)][20] for r, p in expected_damage._2D6_EXACT.items() if r - 4 >= 2)
    assert abs(ams.expected_damage_engaged(lrm) - want) < 1e-12
    assert ams.expected_damage_engaged(lrm) < expected_damage.expected_damage_per_hit(lrm)
    streak = weapon(fresh(ATLAS_S), "Streak")
    assert ams.expected_damage_engaged(streak) == 2 * TABLE[7][2]
    assert ams.expected_damage_engaged(thunderbolt()) == 5.0


@check
def damage_factors_share():
    """One AMS (2 engagements) vs the Archer's two LRM 20s: both fully cut;
    vs four missile weapons, half the cut each (fire_modes.ams_share, priced
    by fire_modes.Planner since 2026-10-20)."""
    import INTEGRATION__fire_modes as fire_modes
    archer, target = fresh(ARCHER), fresh(ATLAS_K, "0804", "S")
    lrms = [w for w in get_weapons(archer) if "LRM" in w.name]
    assert fire_modes.ams_share(2, get_weapons(archer)) == 1.0
    assert fire_modes.ams_share(2, lrms + lrms) == 0.5 and fire_modes.ams_share(0, lrms) == 0.0
    full = ams.expected_damage_engaged(lrms[0]) / expected_damage.expected_damage_per_hit(lrms[0])
    adjust = attack_resolution.tn_adjuster(archer, target)
    plain = fire_modes.Planner(archer, target, adjust, 0.0)(lrms[0], 10, 6)[0]
    for share in (1.0, 0.5):
        got = fire_modes.Planner(archer, target, adjust, share)(lrms[0], 10, 6)[0]
        assert abs(got / plain - (1 - share * (1 - full))) < 1e-12, share


@check
def arc_coverage():
    """A left-arm AMS covers attacks from the forward and left side arcs, not
    the right side or the rear; a torso twist moves it (p.60)."""
    import INTEGRATION__arcs as arcs
    import hex_geometry
    m = fresh(ATLAS_K, "0808", "N")

    def covered(label, action=None):
        return bool(ams.covering(m, hex_geometry.parse_hex_label(label), action))
    # Facing north: 0804 ahead, 0408 to the left (west), 1208 to the right, 0812 behind.
    assert covered("0804") and covered("0408") and not covered("1208") and not covered("0812")
    twist_right = arcs.ArcAction(twist=1)
    assert covered("1208", twist_right) and not covered("0408", twist_right)


@check
def engage_two_per_turn_ammo_and_heat():
    """Each AMS engages at most two attacks a turn: 1 shot and 1 heat each."""
    d, a = fresh(ATLAS_K, "0808", "N", "Red"), fresh(ARCHER, "0804", "S", "Blue")
    lrm = weapon(a, "LRM")
    attacks = hits(lrm, 3) + [DeclaredAttack(weapon=lrm, tn=8, roll=3, hit=False)]
    rep = SideReport()
    ams.engage(d, a, attacks, rep)
    assert [x.ams is not None for x in attacks] == [True, True, False, False]
    assert rep.weapon_heat == 2 and ams.shots_left(d, ams.systems(d)[0]) == 10


@check
def no_engagement_when_it_cannot():
    """From outside the arc, shut down, crew unconscious, out of ammo, or a
    zero-damage missile (Narc): no engagement."""
    a = fresh(ARCHER, "0812", "N", "Blue")
    lrm = weapon(a, "LRM")
    for setup in ("rear", "shutdown", "unconscious", "ammo"):
        d = fresh(ATLAS_K, "0808", "N", "Red")
        if setup != "rear":
            a.hex = "0804"
        if setup == "shutdown":
            d.shutdown = True
        if setup == "unconscious":
            d.crew["pilot"]["unconscious"] = True
        if setup == "ammo":
            for b in ammo.bins_for(d, ams.systems(d)[0]):
                b.shots_left = 0
        attacks, rep = hits(lrm), SideReport()
        ams.engage(d, a, attacks, rep)
        assert attacks[0].ams is None and rep.weapon_heat == 0, setup
        a.hex = "0812"
    d = fresh(ATLAS_K, "0808", "N", "Red")
    narc = SimpleNamespace(name="ISNarcBeacon", damage_type="Missile", rack_size=1, damage_per_shot=0, heat=0)
    attacks = hits(narc)
    ams.engage(d, fresh(ARCHER, "0804", "S"), attacks, SideReport())
    assert attacks[0].ams is None


@check
def laser_ams_heat_limit():
    """A laser AMS (7 heat) engages while the projected end-of-turn heat stays
    at or under max(max_heat, AMS_HEAT_LIMIT); a second engagement that would
    pass it holds."""
    d, a = fresh(MORPHEUS, "0808", "N", "Red"), fresh(ARCHER, "0804", "S", "Blue")
    lrm = weapon(a, "LRM")
    from mech_state import compute_heat_dissipation
    d.current_heat = config.AMS_HEAT_LIMIT + compute_heat_dissipation(d) - 7 - 1   # room for one engagement
    attacks, rep = hits(lrm, 2), SideReport()
    ams.engage(d, a, attacks, rep)
    assert [x.ams is not None for x in attacks] == [True, False] and rep.weapon_heat == 7


def resolve(attack, rolls, defender=None, picks=1):
    d = defender or fresh(ATLAS_K, "0808", "N", "Red")
    before = attack_resolution.total_hp(d)
    with ScriptedDice(rolls, default=7):
        config.pick_number = lambda n, prompt="": picks
        attack_resolution._resolve_one_attack(None, d, attack, None)
    return before - attack_resolution.total_hp(d)


@check
def resolution_cluster_streak_single():
    """Engaged LRM 20: cluster 3 - 4 < 2 = no damage, 11 - 4 = 7 -> the 7 row;
    an engaged Streak SRM 2 counts as a 7 (1 missile); a Thunderbolt dies on a
    1D6 4+, gets through on 1-3."""
    defender = fresh(ATLAS_K, "0808", "N", "Red")
    a = ams.systems(defender)[0]
    lrm = weapon(fresh(ARCHER), "LRM")
    attack = hits(lrm)[0]
    attack.ams = a
    assert resolve(attack, [3]) == 0
    assert resolve(attack, [11]) == TABLE[7][20]                  # then 7s: hit locations
    assert resolve(hits(lrm)[0], [5]) == TABLE[5][20]             # not engaged: as before
    streak = hits(weapon(fresh(ATLAS_S), "Streak"))[0]
    streak.ams = a
    assert resolve(streak, [7]) == 2 * TABLE[7][2]
    tb = hits(thunderbolt())[0]
    tb.ams = a
    assert resolve(tb, [], picks=4) == 0
    assert resolve(tb, [7], picks=3) == 10


@check
def apds():
    """p.206 (2026-10-21): the APDS defends its own 'Mech as an AMS (2 heat,
    1 of 12 shots an engagement, never fired as a weapon); one AMS and one
    APDS on the same attack add up - Cluster roll -8, a Streak's 12 - 10 = 2."""
    osprey = fresh(unit("XTRs/Republic III/Osprey OSP-36"), "0808", "N", "Red", max_heat=30)
    systems = ams.systems(osprey)
    assert systems and all(weapon_rules.is_apds(w) for w in systems)
    a = fresh(ARCHER, "0804", "S", "Blue")
    attacks = hits(weapon(a, "LRM"), 1)
    rep = SideReport()
    ams.engage(osprey, a, attacks, rep)
    assert attacks[0].apds is not None and attacks[0].ams is None and rep.weapon_heat == 2
    assert ams.shots_left(osprey, systems[0]) == 2 * 12 - 1
    both = hits(weapon(fresh(ARCHER), "LRM"))[0]
    both.ams, both.apds = ams.systems(fresh(ATLAS_K))[0], systems[0]
    assert resolve(both, [11]) == TABLE[3][20]                     # 11 - 4 - 4
    streak = hits(weapon(fresh(ATLAS_S), "Streak"))[0]
    streak.ams, streak.apds = both.ams, both.apds
    assert resolve(streak, [7]) == 2 * TABLE[2][2]                 # 12 - 5 - 5


@check
def weapon_choice_and_movement_price_the_ams():
    """The Archer's expected damage against the Atlas AS7-K is lower with the
    AMS covering it than with the AMS gone - in movement scoring too."""
    def dealt(remove_ams):
        mover, defender = fresh(ARCHER, "0812", "N", "Blue"), fresh(ATLAS_K, "0808", "S", "Red")
        if remove_ams:
            for loc, slots in defender.crits.items():
                defender.crits[loc] = ["-Empty-" if getattr(s, "category", None) == "weapon"
                                       and attack_resolution.weapon_rules.is_ams(s) else s for s in slots]
        cands = ranged_combat.evaluate_going_second(mover, defender, TERRAIN)
        return {(c.hex, c.facing, c.mode, c.fc): c.dealt for c in cands}
    with_ams, without = dealt(False), dealt(True)
    assert with_ams.keys() == without.keys()
    assert all(with_ams[k] <= without[k] + 1e-9 for k in with_ams)
    assert any(with_ams[k] < without[k] - 1e-9 for k in with_ams)


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
        print(f"{failed} of {len(CHECKS)} AMS checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} AMS checks passed.")


if __name__ == "__main__":
    run_all()
