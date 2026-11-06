"""
tests/test_fire_modes.py - checks the weapon-use OPTIONS (INTEGRATION__fire_modes,
2026-10-20) and the stubs that choose among them: rapid fire (Ultra / Rotary
AC, Core pp.182-183) with Rotary jams and unjamming, LB-X cluster rounds
(p.192), ATM ER / HE and MML LRM / SRM ammunition (p.186, tables pp.250, 252),
the Apollo FCS (p.197), and the MASC / supercharger / radical heat sink use
stub. Also the data fixes they rest on: weapon slot counts (a 5-slot Ultra
AC/5 is one weapon), split weapons, IS machine guns and their ammo.

    python tests/test_fire_modes.py

Real units come from data/meks.zip (extracted to a temporary folder).
"""

import io
import os
import sys
import tempfile
import traceback
import zipfile
from contextlib import redirect_stdout
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
config.STATS = False  # event log + report off: not part of a test or battery (2026-11-06)
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__fire_modes as fire_modes  # noqa: E402
import INTEGRATION__ranged_combat as ranged_combat  # noqa: E402
import INTEGRATION__equipment_systems as equip  # noqa: E402
import INTEGRATION__stubs as stubs  # noqa: E402
import INTEGRATION__ammo as ammo  # noqa: E402
from INTEGRATION__attack_resolution import DeclaredAttack  # noqa: E402
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


CATAPHRACT = unit("3050U/Cataphract CTF-3D")             # LB 10-X (slug + cluster bins), Ultra AC/5
EMPEROR = unit("3058Uu/Emperor EMP-6D")                  # two Rotary AC/5s
AKUMA = unit("3067 Unabridged/IS Meks/Akuma AKU-2XK")    # two MML 9s (LRM + SRM bins), Rotary AC/5, Guardian ECM
HIGHLANDER = unit("3060u/Highlander IIC 2")              # ATM 6 with standard, ER and HE bins
TEMPLAR = unit("3067 Unabridged/IS Meks/Templar TLR1-OH")  # MRM 30s with Apollo
ATLAS_S2 = unit("3050U/Atlas AS7-S2")                    # heavy Gauss split between torso and arm
BATTLEMASTER = unit("3039u/BattleMaster BLR-1D")         # IS machine guns, "IS Ammo MG - Full"
MASC_UNIT = unit("3050U/Caesar CES-4R")                  # MASC
TABLE = config.CLUSTER_HITS_TABLE


def fresh(template, hex_="0808", facing="N", name="Test", max_heat=30):
    m = clone_mech(template)
    orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": 5,
                                         "min_heat": 0, "max_heat": max_heat}, name)
    return m


def weapon(mech, fragment):
    return next(w for w in get_weapons(mech) if fragment.upper() in w.name.upper().replace(" ", ""))


def planner(a, t):
    return fire_modes.Planner(a, t, attack_resolution.tn_adjuster(a, t))


class Knobs:
    """Temporarily set config knobs."""
    def __init__(self, **values):
        self.values = values

    def __enter__(self):
        self.saved = {k: getattr(config, k) for k in self.values}
        for k, v in self.values.items():
            setattr(config, k, v)

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            setattr(config, k, v)


def damage_taken(attack, target, rolls):
    before = attack_resolution.total_hp(target)
    with ScriptedDice(rolls, default=7):
        attack_resolution._resolve_one_attack(None, target, attack, None)
    return before - attack_resolution.total_hp(target)


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def one_weapon_per_item():
    """Slot counts from the Core tables: the Cataphract's 6-slot LB 10-X and
    5-slot Ultra AC/5 are one weapon each (were 6 and 5); the Atlas AS7-S2's
    heavy Gauss, split torso / arm, is one weapon in both locations."""
    counts = Counter(w.name for w in get_weapons(fresh(CATAPHRACT)))
    assert counts["ISLBXAC10"] == 1 and counts["ISUltraAC5"] == 1, counts
    atlas = fresh(ATLAS_S2)
    hg = [w for w in get_weapons(atlas) if "HEAVYGAUSS" in w.name.upper()]
    assert len(hg) == 1 and hg[0].slots_occupied == 11
    assert len(attack_resolution.weapon_locations(atlas)[id(hg[0])]) == 2


@check
def is_machine_guns_fire():
    """IS machine guns had no equipment.json row (inert) and their bins no row."""
    m = fresh(BATTLEMASTER)
    mg = weapon(m, "MachineGun")
    assert mg.damage_per_shot == 2 and ammo.bins_for(m, mg) and id(mg) not in ammo.unavailable_weapons(m)


@check
def rapid_fire_options_and_policy():
    """Ultra: 1-2 shots, Rotary 1-6; the rate stub picks the most (default) or one."""
    c, e = fresh(CATAPHRACT, name="Red"), fresh(EMPEROR, "0804", "S", "Blue")
    uac, rac = weapon(c, "UltraAC5"), weapon(e, "RotaryAC5")
    assert fire_modes.rate_options(c, uac, fire_modes.PLAIN) == [1, 2]
    assert fire_modes.rate_options(e, rac, fire_modes.PLAIN) == [1, 2, 3, 4, 5, 6]
    value, heat, plan = planner(c, e)(uac, 3, 6)
    assert plan.shots == 2 and heat == 2 * uac.heat
    with Knobs(STUB_RATE_OF_FIRE="single"):
        assert planner(c, e)(uac, 3, 6)[2].shots == 1
    single = planner(c, e).value(uac, fire_modes.PLAIN, 3, 6)[0]
    assert value > single


@check
def rapid_fire_resolution():
    """A Rotary AC x6 hit rolls the 6 column; each shot is its own 5-point hit."""
    e, t = fresh(EMPEROR, name="Red"), fresh(CATAPHRACT, "0804", "S", "Blue")
    rac = weapon(e, "RotaryAC5")
    attack = DeclaredAttack(weapon=rac, tn=6, roll=8, hit=True, fire=fire_modes.PLAIN._replace(shots=6))
    assert damage_taken(attack, t, [8]) == 5 * TABLE[8][6]
    assert abs(fire_modes.expected_hit(rac, attack.fire) - 5 * sum(
        p * TABLE[r][6] for r, p in fire_modes._2D6_EXACT.items())) < 1e-9


@check
def rotary_jams_and_unjams():
    """Jams on 2 (2-3 shots), 3 or less (4-5), 4 or less (6); a jammed RAC
    can't fire; unjamming: stand still / walk only, then Gunnery + 3."""
    plan = fire_modes.PLAIN
    assert [fire_modes.jam_threshold(plan._replace(shots=n)) for n in range(1, 7)] == [0, 2, 2, 3, 3, 4]
    e = fresh(EMPEROR, name="Red")
    rac = weapon(e, "RotaryAC5")
    rac.jammed = True
    assert id(rac) in fire_modes.jammed_ids(e)
    fire_modes.declare_unjams(e)
    assert e.unjamming == [rac]
    modes = {st[4] for st in ranged_combat.movement_options(e, TERRAIN)}
    assert modes <= {"Stand Still", "Walk"} and "Walk" in modes
    with ScriptedDice([7]):                    # gunnery 4 + 3 = 7
        fire_modes.resolve_unjams(e)
    assert not rac.jammed and e.unjamming == []
    with Knobs(STUB_UNJAM=False):
        rac.jammed = True
        fire_modes.declare_unjams(e)
        assert e.unjamming == []


@check
def lbx_cluster_rounds():
    """LB-X cluster: -1 to hit, the 10 column, 1-point pellets; slugs: one 10-point hit."""
    c, t = fresh(CATAPHRACT, name="Red"), fresh(EMPEROR, "0804", "S", "Blue")
    lbx = weapon(c, "LBXAC10")
    kinds = {p.kind for p in planner(c, t).kinds(lbx)}
    assert kinds == {"", "cluster"}
    cluster = next(p for p in planner(c, t).kinds(lbx) if p.kind == "cluster")
    assert cluster.tn == -1 and fire_modes.column(lbx, cluster) == 10 and fire_modes.grouping(lbx, cluster) == 1
    attack = DeclaredAttack(weapon=lbx, tn=6, roll=8, hit=True, fire=cluster)
    assert damage_taken(attack, t, [7]) == TABLE[7][10]
    with Knobs(STUB_MUNITION_POLICY="standard"):
        assert planner(c, t)(lbx, 9, 6)[2].kind == ""


@check
def mml_and_atm_ammunition():
    """MML 9: LRM rounds 1 damage, minimum 6, 7/14/21; SRM rounds 2 damage,
    3/6/9 (bins 13 / 11 shots). ATM: ER 1 damage out to 27, HE 3 to 9."""
    a, t = fresh(AKUMA, name="Red"), fresh(HIGHLANDER, "0804", "S", "Blue")
    mml = weapon(a, "MML9")
    plans = {p.kind: p for p in planner(a, t).kinds(mml)}
    assert set(plans) == {"lrm", "srm"}
    assert fire_modes.damage_per(mml, plans["lrm"]) == 1 and fire_modes.weapon_range(mml, plans["lrm"])["long"] == 21
    assert fire_modes.damage_per(mml, plans["srm"]) == 2 and fire_modes.weapon_range(mml, plans["srm"])["long"] == 9
    assert planner(a, t)(mml, 15, 6)[2].kind == "lrm"         # SRMs can't reach 15
    shots = sorted(b.shots_left for b in ammo.bins_for(a, mml))
    assert shots == [11, 13, 13], shots
    h = fresh(HIGHLANDER, name="Red")
    atm = weapon(h, "ATM6")
    plans = {p.kind: p for p in planner(h, t).kinds(atm)}
    assert set(plans) == {"", "er", "he"}
    assert fire_modes.damage_per(atm, plans["er"]) == 1 and fire_modes.weapon_range(atm, plans["er"])["long"] == 27
    assert fire_modes.damage_per(atm, plans["he"]) == 3 and fire_modes.weapon_range(atm, plans["he"])["long"] == 9
    assert planner(h, t)(atm, 20, 6)[2].kind == "er"          # only ER reaches 20


@check
def apollo_cancels_the_mrm_penalty():
    """Apollo standard-fire mode: no MRM -1 on the Cluster roll; without it, -1."""
    m, t = fresh(TEMPLAR, name="Red"), fresh(CATAPHRACT, "0804", "S", "Blue")
    mrm = weapon(m, "MRM30")
    plan = planner(m, t)(mrm, 5, 6)[2]
    assert plan.apollo and fire_modes.cluster_modifier(mrm, plan) == 0
    assert fire_modes.cluster_modifier(mrm, plan._replace(apollo=False)) == -1


@check
def escalating_use_stub():
    """MASC use is a stub: "cycle" (Daniel's 1-on / 1-off), "always", "never";
    it warns where the decision is made."""
    stubs.reset_battle_stubs()
    m = fresh(MASC_UNIT)
    m.turn_number = 1
    with Knobs(STUB_ESCALATING_USE="never"):
        equip.resolve_movement_boosters(m)
        assert m.run_mp_multiplier == equip.RUN_MULTIPLIER_BY_BOOSTERS[0]
    assert stubs.active_stubs().get("escalating_use") == 1
    with Knobs(STUB_ESCALATING_USE="always"), ScriptedDice([12]):
        m.turn_number = 2                               # an "off" turn of the cycle
        equip.resolve_movement_boosters(m)
        assert m.run_mp_multiplier == equip.RUN_MULTIPLIER_BY_BOOSTERS[1]


@check
def ranged_phase_with_choices():
    """A whole Ranged phase with rapid fire, LB-X and Rotaries runs, and the
    munition / rate stubs report in."""
    import INTEGRATION__rng as rng
    stubs.reset_battle_stubs()
    a, t = fresh(CATAPHRACT, "0808", "N", "Red"), fresh(EMPEROR, "0805", "S", "Blue")
    for m in (a, t):
        m.move_mode, m.move_fc, m.mp_spent = "Stand Still", 0, 0
    with redirect_stdout(io.StringIO()):
        reports = attack_resolution.run_ranged_combat_phase(a, t, TERRAIN, rng.BattleRNG(3))
    assert reports["Red"].attacks and reports["Blue"].attacks
    assert stubs.active_stubs().get("rate_of_fire", 0) >= 1


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
        print(f"{failed} of {len(CHECKS)} fire-mode checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} fire-mode checks passed.")


if __name__ == "__main__":
    run_all()
