"""
tests/test_electronics.py - checks Artemis IV / V, Narc / iNarc and ECM
(Core Rulebook pp.186-188, 192-193, 197, 200, 202, 209 - INTEGRATION__electronics,
2026-10-20), and the ammo-bin names they depend on (INTEGRATION__ammo.parse_bin:
munition variants, and weapons whose bins never linked before - Gauss, AC/10...).

    python tests/test_electronics.py

Real units come from data/meks.zip (extracted to a temporary folder).
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
import INTEGRATION__electronics as electronics  # noqa: E402
import INTEGRATION__ams as ams  # noqa: E402
import INTEGRATION__ammo as ammo  # noqa: E402
import INTEGRATION__expected_damage as expected_damage  # noqa: E402
from INTEGRATION__attack_resolution import DeclaredAttack, SideReport  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from mech_state import clone_mech  # noqa: E402
from damage_resolution import get_weapons  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
_TMP = tempfile.mkdtemp()


def unit(path):
    with zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip")) as z:
        out = z.extract(f"meks/{path}.mtf", _TMP)
    with redirect_stdout(io.StringIO()):
        return parse_mtf(out)


KINTARO = unit("3050U/Kintaro KTO-19")       # Narc beacon (homing pods), Narc-capable SRM 6s / LRM 5
ATLAS_S2 = unit("3050U/Atlas AS7-S2")        # Guardian ECM; LRM 15 + Artemis IV with Artemis-capable ammo
ATLAS_K = unit("3050U/Atlas AS7-K")          # Gauss rifle (its bins never linked before 2026-10-20); AMS
ATLAS_S = unit("3050U/Atlas AS7-S")          # Streak SRM 2s
VIKING = unit("3145/Steiner/Viking IIC")     # Clan LRMs with Artemis V
ONSLAUGHT = unit("3055U/Onslaught SA-OS2")   # Angel ECM
ARCHER = unit("3039u/Archer ARC-2R")         # plain LRM 20s
TABLE = config.CLUSTER_HITS_TABLE


def fresh(template, hex_="0808", facing="N", name="Test", max_heat=30):
    m = clone_mech(template)
    orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": 5,
                                         "min_heat": 0, "max_heat": max_heat}, name)
    return m


def weapon(mech, fragment):
    return next(w for w in get_weapons(mech) if fragment.upper() in w.name.upper().replace(" ", ""))


def kill_slot(mech, slot):
    for loc, slots in mech.crits.items():
        for i, s in enumerate(slots):
            if s is slot:
                mech.destroyed_slot_info[(loc, i)] = {"name": s.name, "instance_id": id(s)}
                return


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def bin_names():
    """Munition variants and the bins that never linked to their weapon."""
    cases = {
        "IS Gauss Ammo": ("ISGaussRifle", "standard"),
        "Clan Gauss Ammo": ("CLGaussRifle", "standard"),
        "IS Ammo AC/10": ("Autocannon/10", "standard"),
        "IS Ammo LRM-20": ("LRM 20", "standard"),
        "IS Ammo LRM-15 Artemis-capable": ("LRM 15", "artemis4"),
        "Clan Ammo LRM-20 (Clan) Artemis V-capable": ("CLLRM20", "artemis5"),
        "ISSRM6 Ammo Narc-capable": ("SRM 6", "narc"),
        "ISNarc Pods": ("ISNarcBeacon", "homing"),
        "CLNarc Pods": ("CLNarcBeacon", "homing"),
        "ISiNarc Pods": ("ISImprovedNarc", "homing"),
        "ISiNarc Explosive Pods": ("ISImprovedNarc", "explosive"),
    }
    for name, (weapon_name, munition) in cases.items():
        entry, got = ammo.parse_bin(name)
        assert entry is not None and (entry["canonical_name"], got) == (weapon_name, munition), (name, entry, got)
    for name in ("IS LB 10-X Cluster Ammo", "ISLBXAC10 CL Ammo", "IS Ammo MML-7 LRM", "Clan Ammo ATM-6 ER"):
        assert ammo.parse_bin(name) == (None, None), name


@check
def gauss_rifle_has_ammo_now():
    """The Atlas AS7-K's Gauss rifle draws from its 'ISGauss Ammo' bins."""
    m = fresh(ATLAS_K)
    gauss = weapon(m, "Gauss")
    assert id(gauss) not in ammo.unavailable_weapons(m) and ammo.bins_for(m, gauss)


@check
def artemis_iv_link_ecm_and_crit():
    """Artemis IV: +2 Cluster with Artemis ammo; blocked by the target's ECM
    and by the attacker's own active stealth armor; gone with the FCS."""
    a, t = fresh(ATLAS_S2, name="Red"), fresh(ARCHER, "0804", "S", "Blue")
    lrm = weapon(a, "LRM15")
    assert electronics.artemis_kind(a, lrm) == 4 and "artemis4" in electronics.munitions(a, lrm)
    fc = electronics.best_control(a, lrm, t)
    assert (fc.munition, fc.tn, fc.cluster) == ("artemis4", 0, 2)
    assert electronics.fire_controls(a, t) == {id(lrm): fc}
    # The ECM-carrying Atlas shot at by its twin: blocked.
    assert electronics.best_control(fresh(ATLAS_S2, name="Blue"), lrm, a).cluster == 0
    assert electronics.hostile_field(a)
    a.has_stealth_armor = True                    # stealth armor on: its ECM stops and it is "as if" jammed
    assert not electronics.hostile_field(a) and electronics.best_control(a, lrm, t).cluster == 0
    a.has_stealth_armor = False
    kill_slot(a, lrm.artemis[0])
    assert electronics.best_control(a, lrm, t).cluster == 0


@check
def artemis_v():
    """Artemis V: -1 to hit and +3 Cluster."""
    a, t = fresh(VIKING, name="Red"), fresh(ARCHER, "0804", "S", "Blue")
    fire = electronics.fire_controls(a, t)
    assert fire and all((fc.munition, fc.tn, fc.cluster) == ("artemis5", -1, 3) for fc in fire.values())
    lrm = next(w for w in get_weapons(a) if id(w) in fire)
    assert attack_resolution.tn_adjuster(a, t)(lrm, "short") == -1


@check
def angel_ecm_unlocks_streaks():
    """A Streak at a target with Angel ECM rolls on the Cluster Hits Table."""
    a, t = fresh(ATLAS_S, name="Red"), fresh(ONSLAUGHT, "0804", "S", "Blue")
    streak = weapon(a, "Streak")
    fc = electronics.best_control(a, streak, t)
    assert not fc.streak_lock
    assert electronics.expected_hit(streak, fc) == 2 * expected_damage.expected_cluster_hits(2)
    assert electronics.best_control(a, streak, fresh(ARCHER)).streak_lock


@check
def narc_pod_lifecycle():
    """A beacon hit sticks a homing pod in the location struck; it works from
    the next phase: -1 to hit, +2 Cluster for Narc-capable missiles; lost with
    its location; blocked by the target's ECM."""
    a, t = fresh(KINTARO, name="Red"), fresh(ARCHER, "0804", "S", "Blue")
    srm = weapon(a, "SRM6")
    beacon = next(w for w in get_weapons(a) if electronics.is_narc(w))
    attack = DeclaredAttack(weapon=beacon, tn=7, roll=8, hit=True, fire=electronics.FireControl("homing"))
    with ScriptedDice([7]):
        attack_resolution._resolve_one_attack(a, t, attack, None)
    assert t.narc_pods == [{"location": "Center Torso", "owner": "Red", "effective": False}]
    assert electronics.best_control(a, srm, t).cluster == 0              # not until the next phase
    electronics.activate_pods(t)
    fc = electronics.best_control(a, srm, t)
    assert (fc.munition, fc.tn, fc.cluster) == ("narc", -1, 2)
    t.locations["Center Torso"]["destroyed"] = True
    assert electronics.best_control(a, srm, t).cluster == 0
    jammer = fresh(ATLAS_S2, "0804", "S", "Blue")
    electronics.attach_pod(jammer, "Left Torso", "Red")
    electronics.activate_pods(jammer)
    assert electronics.best_control(a, srm, jammer).cluster == 0


@check
def pod_value_and_ams():
    """Daniel: a pod is worth the extra damage the owner's Narc missiles get
    from it - 0 once one is on. The target's AMS engages it for half that."""
    a, t = fresh(KINTARO, "0808", "N", "Red"), fresh(ATLAS_K, "0805", "S", "Blue")
    adjust = attack_resolution.tn_adjuster(a, t)
    value = electronics.pod_value(a, t, 3, 7, adjust)
    assert value > 0
    beacon = next(w for w in get_weapons(a) if electronics.is_narc(w))
    attacks = [DeclaredAttack(weapon=beacon, tn=7, roll=9, hit=True, pod_value=value,
                              fire=electronics.FireControl("homing"))]
    rep = SideReport()
    ams.engage(t, a, attacks, rep)
    assert attacks[0].ams is not None and abs(ams.attack_prevented(attacks[0]) - value / 2) < 1e-12
    electronics.attach_pod(t, "Left Torso", "Red")
    assert electronics.pod_value(a, t, 3, 7, adjust) == 0.0
    assert electronics.pod_munition(a, beacon, t) == "homing"          # no explosive pods aboard


@check
def resolution_applies_the_bonus():
    """An Artemis IV hit rolls Cluster +2 (7 -> 9); with AMS engaged, -4 too."""
    a, t = fresh(ATLAS_S2, name="Red"), fresh(ARCHER, "0804", "S", "Blue")
    lrm = weapon(a, "LRM15")
    fc = electronics.best_control(a, lrm, t)
    for ams_on, expect in ((False, TABLE[9][15]), (True, TABLE[5][15])):
        attack = DeclaredAttack(weapon=lrm, tn=7, roll=9, hit=True, fire=fc)
        attack.ams = ams.systems(fresh(ATLAS_K))[0] if ams_on else None
        before = attack_resolution.total_hp(t)
        with ScriptedDice([7]):
            attack_resolution._resolve_one_attack(a, t, attack, None)
        assert before - attack_resolution.total_hp(t) == expect, (ams_on, before - attack_resolution.total_hp(t))


@check
def ammo_take_prefers_the_munition():
    """take() draws the chosen munition first, then falls back."""
    a = fresh(KINTARO)
    srm = weapon(a, "SRM6")
    note, used = ammo.take(a, srm, "narc")
    assert used == "narc" and "Narc-capable" in note
    note, used = ammo.take(a, srm, "artemis4")           # none of that kind: whatever bin is there
    assert used == "narc"


@check
def ranged_phase_runs():
    """A whole Ranged phase between a Narc carrier and an ECM / Artemis
    carrier runs and fires (smoke test)."""
    import INTEGRATION__rng as rng
    a, t = fresh(KINTARO, "0808", "N", "Red"), fresh(ATLAS_S2, "0805", "S", "Blue")
    for m in (a, t):
        m.move_mode, m.move_fc, m.mp_spent = "Stand Still", 0, 0
    with redirect_stdout(io.StringIO()):
        terrain = orchestrator._load_map()
    reports = attack_resolution.run_ranged_combat_phase(a, t, terrain, rng.BattleRNG(1))
    assert reports["Blue"].attacks > 0
    assert not any(electronics.is_narc(x.weapon) for x in reports["Red"].attacks_list)    # ECM: pod worthless


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
        print(f"{failed} of {len(CHECKS)} electronics checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} electronics checks passed.")


if __name__ == "__main__":
    run_all()
