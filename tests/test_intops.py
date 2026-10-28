"""
tests/test_intops.py - the Interstellar Operations weapons wired in
2026-10-28 from Daniel's pasted rules (TSEMP, Repeating TSEMP, iATM with IMP
and IIW rounds), the inferno missiles IIW needs (Core p.192), and the
MegaMek values Daniel asked for (Improved weapons' slots and ammo, the
nail / rivet gun) - INTEGRATION__advanced_weapons.

    python tests/test_intops.py

Real units come from data/meks.zip (extracted to a temporary folder). Dice
are scripted the same way as tests/test_heat.py.
"""

import io
import os
import sys
import tempfile
import traceback
import zipfile
from contextlib import redirect_stdout

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__advanced_weapons as adv  # noqa: E402
import INTEGRATION__equipment_systems as equip  # noqa: E402
import INTEGRATION__electronics as electronics  # noqa: E402
import INTEGRATION__fire_modes as fire_modes  # noqa: E402
import INTEGRATION__ammo as ammo  # noqa: E402
import INTEGRATION__weapon_rules as weapon_rules  # noqa: E402
from INTEGRATION__attack_resolution import DeclaredAttack  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from mech_state import clone_mech, compute_walk_mp, compute_jump_mp  # noqa: E402
from damage_resolution import get_weapons  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
_TMP = tempfile.mkdtemp()


def unit(path):
    with zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip")) as z:
        out = z.extract(f"meks/{path}.mtf", _TMP)
    with redirect_stdout(io.StringIO()):
        return parse_mtf(out)


INQUISITOR = unit("Turning Points/TP Irian/Inquisitor II ITW-200")    # TSEMP Cannon; industrial structure
TEMPLAR = unit("XTRs/RISC/Templar TLR1-ORISC")                       # Repeating TSEMP
HELLION = unit("3145/NTNU RS/Hellion G")                             # TSEMP One-Shot
TURKINA = unit("WoR Supplemental/Turkina Z")                         # four iATM 12s
BULL_SHARK = unit("Videogame (Apocryphal)/Bull Shark BSK-M3")        # two Improved AC/5s
NAJA = unit("Golden Century/Naja")                                   # two Improved SRM 6s
FOX = unit("Golden Century/Fox CS-1")                                # two Improved LRM 15s
DEVASTATOR = unit("Golden Century/Devastator DVS-2-EC")              # two Improved Gauss Rifles
JABBERWOCKY = unit("3075/Jabberwocky ConstructionMech JAW-66D")      # nail / rivet guns
CARBINE = unit("XTRs/Caveat Emptor/Carbine CON-9M-D ConstructionMech MOD")   # ICE engine

CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def place(template, hex_="0808", facing="N", side="Red"):
    m = clone_mech(template)
    with redirect_stdout(io.StringIO()):
        orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": 5,
                                             "min_heat": 0, "max_heat": 30}, side)
    m.move_mode, m.move_fc, m.movement_heat, m.turn_number = "Walk", 1, 1, 1
    return m


def named(m, fragment):
    return [w for w in get_weapons(m) if fragment in w.name]


@check
def slot_counts_and_ammo():
    """Each multi-slot weapon is one weapon (they were read as one per slot),
    and the Improved weapons' bins now feed them (MegaMek's values)."""
    assert len(named(INQUISITOR, "TSEMP")) == 1 and named(INQUISITOR, "TSEMP")[0].slots_occupied == 5
    assert len(named(TEMPLAR, "TSEMP")) == 1 and named(TEMPLAR, "TSEMP")[0].explosion_damage == 14
    assert len(named(HELLION, "TSEMP")) == 1 and named(HELLION, "TSEMP")[0].explosion_damage == 6
    assert len(named(TURKINA, "iATM")) == 4
    assert len(named(BULL_SHARK, "Improved")) == 2
    assert len(named(NAJA, "Improved")) == 2
    assert len(named(FOX, "Improved")) == 2
    for template, fragment, shots in ((DEVASTATOR, "Improved Gauss", 8), (NAJA, "Improved SRM", 15),
                                      (BULL_SHARK, "Improved Auto", 20), (FOX, "Improved LRM", 8)):
        m = place(template)
        w = named(m, fragment)[0]
        bins = ammo.bins_for(m, w)
        assert bins and not w.ammo_unknown and bins[0].shots_left % shots == 0, (fragment, bins)
    igr = named(DEVASTATOR, "Improved Gauss")[0]
    assert igr.is_explosive and igr.explosion_damage == 12          # 2 a slot (Core p.96)


@check
def unit_type_and_engine():
    """IndustrialMech = industrial structure (MegaMek); ICE engine; fusion."""
    assert INQUISITOR.is_industrial and not TURKINA.is_industrial
    assert adv.ice_engine(CARBINE) and not adv.fusion_engine(CARBINE)
    assert not adv.ice_engine(TURKINA) and adv.fusion_engine(TURKINA)


@check
def tsemp_effects_table():
    """IO p.91: a BattleMech shuts down on 9+, interference on 7-8, through
    the End Phase of the next turn; -2 at 100+ tons, nothing at 200+;
    +1 for each earlier TSEMP hit this turn; IndustrialMechs 6-7 / 8+."""
    a, t = place(INQUISITOR), place(TURKINA, "0807", "S", "Blue")       # Turkina: 95 tons, BattleMech
    with ScriptedDice([9]):
        adv.tsemp_hit(a, t, 2)                                            # 95 tons: no modifier, 9 shuts it down
    assert t.shutdown and t.tsemp_hits == (2, 1)
    t = place(TURKINA, "0807", "S", "Blue")
    t.mass = 100
    with ScriptedDice([9]):
        adv.tsemp_hit(a, t, 2)                                            # 9 - 2 = 7: interference
    assert not t.shutdown and adv.tsemp_interference(t) == 2
    assert equip.own_attack_modifier(t) >= 2 and electronics.as_if_jammed(t)
    assert adv.own_attack_modifier(t, physical=True) == 0                 # weapon attacks only
    with ScriptedDice([10]):
        adv.tsemp_hit(a, t, 2)                                            # 10 - 2 + 1 (second hit) = 9: shutdown
    assert t.shutdown and t.tsemp_shutdown_until == 3
    adv.end_phase(t, 2)
    assert t.shutdown and adv.held_down(t)
    adv.end_phase(t, 3)
    assert not t.shutdown and adv.tsemp_interference(t) == 0
    t.mass = 200
    with ScriptedDice([]):
        adv.tsemp_hit(a, t, 5)                                            # no roll at all
    assert not t.shutdown
    i = place(INQUISITOR, "0807", "S", "Blue")                            # IndustrialMech: shutdown on 8+
    with ScriptedDice([8]):
        adv.tsemp_hit(a, i, 2)
    assert i.shutdown


@check
def tsemp_firing():
    """The firer suffers interference; the Cannon can't fire next turn; a fired
    One-Shot can't explode; a Repeating TSEMP blows up on an attack roll of 2."""
    a = place(INQUISITOR)
    cannon = named(a, "TSEMP")[0]
    assert adv.tsemp_fired(a, cannon, 8, 2, "Left Arm")
    assert adv.tsemp_interference(a) == 2 and id(cannon) in ammo.unavailable_weapons(a)
    adv.end_phase(a, 2)
    assert id(cannon) in ammo.unavailable_weapons(a)                      # turn 3: still recharging
    adv.end_phase(a, 3)
    assert id(cannon) not in ammo.unavailable_weapons(a) and adv.tsemp_interference(a) == 0
    h = place(HELLION)
    one = named(h, "TSEMP")[0]
    assert one.one_shot and one.is_explosive
    adv.tsemp_fired(h, one, 8, 2, "Left Torso")
    assert not one.is_explosive and not adv.recharging(one)
    r = place(TEMPLAR)
    rep = named(r, "TSEMP")[0]
    assert adv.tsemp_fired(r, rep, 8, 2, "Right Arm") and not adv.recharging(rep)    # fires every turn
    before = r.locations["Right Arm"]["structure"]
    assert not adv.tsemp_fired(r, rep, 2, 3, "Right Arm")
    assert rep.exploded and all(s is not rep for s in r.crits["Right Arm"])
    assert r.locations["Right Arm"]["destroyed"] or r.locations["Right Arm"]["structure"] < before


@check
def iatm_fires_as_a_streak():
    """Fired directly the iATM is a Streak: every missile hits on a hit (no
    Cluster roll); a miss doesn't fire (no ammo spent)."""
    m = place(TURKINA)
    w = named(m, "iATM")[0]
    assert weapon_rules.is_streak(w)
    plan = fire_modes.ShotPlan(electronics.FireControl("standard"))
    assert fire_modes.expected_hit(w, plan) == 2 * 12
    imp = plan._replace(kind="imp")
    assert fire_modes.damage_per(w, imp) == 1 and fire_modes.weapon_range(w, imp)["short"] == 3
    iiw = plan._replace(kind="iiw")
    assert fire_modes.is_inferno(iiw) and fire_modes.damage_per(w, iiw) == 0
    assert fire_modes.expected_hit(w, iiw) == 12 * 2 * config.TARGET_HEAT_WORTH


@check
def imp_effects():
    """Every 3 IMP missiles: hostile ECM, +1 to hit, -1 Walking / Jumping MP
    (at most 2), +1 heat; until the End Phase of the next turn; later strikes
    while it lasts add no to-hit / MP effect."""
    t = place(TURKINA, "0807", "S", "Blue")
    walk, jump = compute_walk_mp(t), compute_jump_mp(t)
    adv.imp_hit(t, 7, 2)
    assert adv.imp_level(t) == 2 and compute_walk_mp(t) == walk - 2 and compute_jump_mp(t) == max(0, jump - 2)
    assert electronics.as_if_jammed(t) and adv.own_attack_modifier(t, physical=True) == 2
    assert t.outside_heat == 2
    adv.imp_hit(t, 12, 3)                                                  # next turn, still affected
    assert t.imp_until == 3 and t.outside_heat == 2 + 4                  # heat still comes
    adv.end_phase(t, 3)
    assert adv.imp_level(t) == 0 and compute_walk_mp(t) == walk
    c = place(CARBINE, "0807", "S", "Blue")                               # ICE: no MP or heat effect
    walk = compute_walk_mp(c)
    adv.imp_hit(c, 6, 2)
    assert adv.imp_level(c) == 2 and compute_walk_mp(c) == walk and getattr(c, "outside_heat", 0) == 0


@check
def inferno_missiles():
    """p.192: inferno missiles deal 2 heat each, no damage."""
    a, t = place(TURKINA), place(TURKINA, "0807", "S", "Blue")
    w = named(a, "iATM")[0]
    plan = fire_modes.ShotPlan(electronics.FireControl("standard"), kind="iiw")
    armor = dict((k, v["armor"]) for k, v in t.locations.items())
    attack = DeclaredAttack(weapon=w, tn=4, roll=8, hit=True, side="front", fire=plan)
    with ScriptedDice([]):
        attack_resolution._resolve_one_attack(a, t, attack, None)
    assert t.outside_heat == 24 and armor == {k: v["armor"] for k, v in t.locations.items()}
    bin_ = next(b for b in ammo.bins_for(a, w))
    bin_.munition, bin_.kind = "inferno", ""
    assert ("inferno", "") in fire_modes.bin_kinds(a, w)


@check
def nail_gun():
    """MegaMek: 1D6 a hit, nothing to a location that still has armor."""
    a, t = place(JABBERWOCKY), place(TURKINA, "0807", "S", "Blue")
    w = named(a, "Nail")[0]
    attack = DeclaredAttack(weapon=w, tn=4, roll=8, hit=True, side="front", fire=fire_modes.PLAIN)
    before = {k: (v["armor"], v["structure"]) for k, v in t.locations.items()}
    with ScriptedDice([7]):                                                 # Center Torso, armored
        attack_resolution._resolve_one_attack(a, t, attack, None)
    assert before == {k: (v["armor"], v["structure"]) for k, v in t.locations.items()}
    t.locations["Center Torso"]["armor"] = 0
    with ScriptedDice([7]):                                                 # bare: 1D6 (scripted 1)
        attack_resolution._resolve_one_attack(a, t, attack, None)
    assert t.locations["Center Torso"]["structure"] == before["Center Torso"][1] - 1
    assert fire_modes.special(w) and adv.nail_worth(t, "front") > 0


def run_all():
    failed = []
    for fn in CHECKS:
        try:
            with redirect_stdout(io.StringIO()):
                fn()
            print(f"  {fn.__name__}: PASS")
        except Exception:
            failed.append(fn.__name__)
            print(f"  {fn.__name__}: FAILED")
            traceback.print_exc()
    print(f"{len(CHECKS) - len(failed)} of {len(CHECKS)} checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
