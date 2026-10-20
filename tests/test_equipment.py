"""
tests/test_equipment.py - checks the heat/movement equipment rules in
INTEGRATION__equipment_systems.py and INTEGRATION__heat.py (Core Rulebook:
Escalating Failure p.180, MASC / supercharger p.204, TSM p.205, torso-
mounted cockpit p.203, coolant pod / radical heat sinks pp.208-209, stealth
systems pp.202, 209, inferno ammo pp.107, 192, aimed shots p.70) and
Daniel's defaults (2026-10-19: always-on stealth, 1-on/1-off cycle, TSM via
min_heat 9, End Phase heat-sink switching).

    python tests/test_equipment.py

Dice are scripted the same way as tests/test_heat.py. Uses
data/TEST_Heat_Gear.mtf: 60 tons, Walk 5, 14 single heat sinks, TSM,
torso-mounted cockpit, MASC, supercharger, radical heat sink system, 2
coolant pods, Chameleon LPS + Guardian ECM, an inferno and a standard SRM 6
bin and an LRM 10 bin; weapons ML / PPC / SRM 6 / LRM 10 (21 heat).
"""

import os
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__heat as heat  # noqa: E402
import INTEGRATION__equipment_systems as equip  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__weapon_selection as weapon_selection  # noqa: E402
from equipment import Equipment  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from mech_state import clone_mech, compute_walk_mp, compute_running_mp, compute_heat_dissipation  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
GEAR = parse_mtf(config.data_path("TEST_Heat_Gear.mtf"))
ASYMPTOTE = parse_mtf(config.data_path("Asymptote II iJ Mpulse.mtf"))


class Picks:
    """Scripts config.pick_number (1D6 and slot picks) inside a ScriptedDice block."""
    def __init__(self, picks):
        self.picks = list(picks)

    def __enter__(self):
        self.saved = config.pick_number
        config.pick_number = lambda n, prompt="": self.picks.pop(0) if self.picks else 1
        return self

    def __exit__(self, *exc):
        config.pick_number = self.saved


def gear(heat_level=0, min_heat=0, max_heat=30, turn=2):
    m = clone_mech(GEAR)
    orchestrator._attach_mech_config(m, {"hex": "0505", "facing": "N", "gunnery": 4, "piloting": 5,
                                         "min_heat": min_heat, "max_heat": max_heat}, "Test")
    m.deactivated_heat_sinks = 0
    m.current_heat = heat_level
    equip.start_turn(m, turn)          # turn 2 = an off turn (radical / MASC / supercharger idle)
    return m


def no_pods(m):
    for p in m.equipment_systems["coolant_pod"]:
        p.pod_used = True


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def detection_and_tsm_heat_settings():
    m = gear()
    counts = {k: len(v) for k, v in m.equipment_systems.items()}
    # ecm: one 2-slot Guardian suite (equipment.json slots fixed to 2 on 2026-10-20; was 2 instances)
    assert counts == {"supercharger": 1, "coolant_pod": 2, "chameleon": 6, "tsm": 5, "ecm": 1,
                      "masc": 3, "radical": 1}, counts
    assert m.has_tsm and m.torso_cockpit and not m.has_stealth_armor
    assert (m.min_heat, m.max_heat) == (9, 30)          # TSM raises min_heat to 9 (Daniel)
    m2 = clone_mech(GEAR)
    orchestrator._attach_mech_config(m2, {"hex": "0505", "facing": "N", "gunnery": 4, "piloting": 5,
                                          "min_heat": 0, "max_heat": 4}, "Test")
    assert (m2.min_heat, m2.max_heat) == (9, 9)          # ...and max_heat to at least that
    assert [b.name for _, b in heat.live_ammo_bins(m, inferno=True)] == ["ISSRM6 Ammo - Inferno"]
    assert len(heat.live_ammo_bins(m, inferno=False)) == 2


@check
def escalating_failure_table_and_cycle():
    """p.180: 3+/5+/7+/10+/11+; an unused turn steps back one."""
    assert [equip.escalating_avoid_tn(n) for n in (1, 2, 3, 4, 5, 9)] == [3, 5, 7, 10, 11, 11]
    m = gear(turn=1)
    with ScriptedDice([3, 5, 6]):
        results = [equip.escalating_roll(m, "masc", "MASC") for _ in range(3)]
    assert results == [True, True, False] and m.escalating_turns["masc"] == 3
    equip.end_turn(m)                                     # masc used this turn: no step back
    assert m.escalating_turns["masc"] == 3
    equip.end_turn(m)
    assert m.escalating_turns["masc"] == 2
    assert equip.cycle_on(m, 1) and not equip.cycle_on(m, 2)   # odd turns on (config default)


@check
def stealth_systems():
    """LPS 6 heat, +1 medium / +2 long; stacks with Null-Signature; off when
    shut down or destroyed. Void needs ECM: +3/+2/+1/+0 by hexes, own +1."""
    m = gear()
    assert equip.active_stealth(m) == ["chameleon"] and equip.stealth_heat(m) == 6
    assert equip.range_stealth_bonus(m) == {"short": 0, "medium": 1, "long": 2}
    m.equipment_systems["null_signature"] = [Equipment("Null Signature System", category="misc")]
    assert equip.stealth_heat(m) == 16 and equip.range_stealth_bonus(m)["long"] == 4
    m.shutdown = True
    assert equip.active_stealth(m) == [] and equip.stealth_heat(m) == 0
    m.shutdown = False

    m.equipment_systems["void_signature"] = [Equipment("Void Signature System", category="misc")]
    assert "void_signature" in equip.active_stealth(m)
    assert [equip.void_signature_modifier(m, h, 0) for h in (0, 1, 2, 3, 5, 6, 9)] == [3, 2, 2, 1, 1, 0, 0]
    assert equip.void_signature_modifier(m, 0, 2) == 2          # 0 hexes but MP spent counts as 1
    assert equip.own_attack_modifier(m) == 1
    ecm = m.equipment_systems["ecm"][0]                         # one ECM slot lost: no ECM, so no Void
    m.destroyed_slot_info[("Left Torso", 99)] = {"name": ecm.name, "instance_id": id(ecm)}
    assert "void_signature" not in equip.active_stealth(m)

    lps = m.equipment_systems["chameleon"][0]                   # any LPS slot lost: LPS destroyed
    m.destroyed_slot_info[("Left Arm", 99)] = {"name": lps.name, "instance_id": id(lps)}
    assert "chameleon" not in equip.active_stealth(m)


@check
def coolant_pod():
    """p.208: +1 per active heat sink, once per pod, one a turn; used only
    when heat would stay above min_heat; a used pod no longer explodes."""
    m = gear(heat_level=20, min_heat=9)
    m.deactivated_heat_sinks = 2                                # 12 active sinks
    with ScriptedDice([]):
        heat.resolve_heat_phase(m, weapon_heat=4)              # 20 + 4 + 6 - 12 = 18 -> pod -12 = 6
    assert m.current_heat == 6
    used = [p for p in m.equipment_systems["coolant_pod"] if getattr(p, "pod_used", False)]
    assert len(used) == 1 and not used[0].is_explosive and used[0].explosion_damage == 0

    m = gear(heat_level=10, min_heat=9)
    with ScriptedDice([]):
        heat.resolve_heat_phase(m, weapon_heat=7)              # 10 + 7 + 6 - 14 = 9: not above min_heat
    assert m.current_heat == 9 and len(equip.unused_coolant_pods(m)) == 2


@check
def radical_heat_sinks():
    """pp.208-209: on its cycle turn, +1 per working sink on a 3+ roll;
    failure destroys it; destroyed = +1 heat moving, +1 firing."""
    m = gear(heat_level=10, min_heat=9, turn=1)
    with ScriptedDice([3]):
        heat.resolve_heat_phase(m, weapon_heat=21)             # 10 + 21 + 6 - 14 - 14 = 9
    assert m.current_heat == 9 and not equip.radical_destroyed(m)
    assert heat.other_heat(gear(turn=1)) == 6 - 14              # planned cooling counted in the budget

    m = gear(heat_level=10, min_heat=9, turn=1)
    no_pods(m)
    with ScriptedDice([2, 12, 12, 12]):                         # radical fails; then shutdown/ammo/inferno rolls
        heat.resolve_heat_phase(m, weapon_heat=21)             # 10 + 21 + 6 - 14 = 23
    assert m.current_heat == 23 and equip.radical_destroyed(m)
    assert heat.movement_heat(m, "Walk", 3) == 2 and heat.movement_heat(m, "Stand Still", 0) == 0
    assert heat.weapon_fire_surcharge(m) == 1


@check
def tsm():
    """p.205: 9+ heat -> +2 Walking MP before heat penalties (Kontio example)."""
    m = gear(heat_level=9)
    heat.apply_heat_effects(m)
    assert m.tsm_active and compute_walk_mp(m) == 5 + 2 - 1 and compute_running_mp(m) == 9
    m.current_heat = 8
    heat.apply_heat_effects(m)
    assert not m.tsm_active and compute_walk_mp(m) == 4
    m.current_heat = 12                                         # -2 cancels the +2 (p.205)
    heat.apply_heat_effects(m)
    assert compute_walk_mp(m) == 5


@check
def masc_and_supercharger():
    """p.204: on-turn rolls before moving; Running MP 2x (one) / 2.5x round
    up (both); failure crits after the move."""
    m = gear(turn=1)
    with ScriptedDice([3, 3]):
        failed = equip.resolve_movement_boosters(m)
    assert failed == [] and compute_running_mp(m) == 13         # ceil(5 x 2.5)
    m = gear(turn=1)
    with ScriptedDice([2, 3]):                                  # MASC fails, supercharger works
        failed = equip.resolve_movement_boosters(m)
    assert failed == ["masc"] and compute_running_mp(m) == 10
    m = gear(turn=2)
    with ScriptedDice([]):
        assert equip.resolve_movement_boosters(m) == [] and compute_running_mp(m) == 8

    m = gear()
    with ScriptedDice([10]), Picks([2, 1, 1]):                  # crit check 10 = 2 crits; 1D6 2 -> Right Leg
        equip.apply_booster_failures(m, ["masc"])
    lost = [k for k in m.destroyed_slot_info if k[0] == "Right Leg"]
    assert len(lost) == 2, m.destroyed_slot_info

    m = gear()
    with ScriptedDice([8]):                                     # 1 crit: top centre-torso Engine slot
        equip.apply_booster_failures(m, ["supercharger"])
    assert m.engine_hits == 1 and m.crits["Center Torso"][0] == "DESTROYED"
    assert not equip.system_live(m, "supercharger")             # failed supercharger is destroyed
    m = gear()
    with ScriptedDice([5]):                                     # no crits - still destroyed
        equip.apply_booster_failures(m, ["supercharger"])
    assert m.engine_hits == 0 and not equip.system_live(m, "supercharger")


@check
def inferno_extra_rolls_and_recheck():
    """pp.107, 192: inferno bins roll their own table from 10 heat; an
    exploding inferno bin adds 30 heat at once, and the new thresholds it
    crosses are rolled for straight away (here: automatic shutdown at 30+,
    a normal ammo roll at 28+)."""
    blasts = []
    saved = heat.apply_explosion
    heat.apply_explosion = lambda m, b, loc: blasts.append(b.name)     # no damage dice in this check
    try:
        m = gear(heat_level=18)
        no_pods(m)
        with ScriptedDice([3, 12]) as dice:          # inferno roll 3 (needs 4) - boom; ammo roll at 28+: 12
            heat.resolve_heat_phase(m, weapon_heat=0)              # 18 + 6 - 14 = 10
        assert blasts == ["ISSRM6 Ammo - Inferno"] and m.current_heat == 40 and m.shutdown
        assert dice.count == 2

        m = gear(heat_level=18)
        no_pods(m)
        with ScriptedDice([4]):                                     # avoided: 4+ at 10
            heat.resolve_heat_phase(m, weapon_heat=0)
        assert m.current_heat == 10 and not blasts[1:]
    finally:
        heat.apply_explosion = saved


@check
def torso_cockpit_life_support():
    """p.203: 1 hit at heat 1-14, 2 at 15+."""
    for level, hits in ((0, 0), (1, 1), (14, 1), (15, 2)):
        m = gear(heat_level=level + 14 - 6)
        no_pods(m)
        m.destroyed_slot_info[("Head", 0)] = {"name": "Life Support", "instance_id": None}
        rolls = ([12] if level >= 14 else []) + ([12] if hits else [])   # shutdown avoid, consciousness
        with ScriptedDice(rolls):
            heat.resolve_heat_phase(m, weapon_heat=0)
        assert m.current_heat == level and m.pilot_hits == hits, (level, m.pilot_hits)


@check
def heat_sink_switching():
    """End Phase (p.103, Daniel): keep only the sinks needed to still reach
    min_heat with every weapon + the hottest move + engine/stealth.
    TEST_Heat_Gear: 0 + 2 run + 21 + 6 LPS = 29; with the radical on next
    turn each sink sheds 2 -> keep (29 - 9) // 2 = 10, switch 4 off."""
    m = gear(min_heat=9)
    heat.choose_heat_sink_deactivation(m, next_turn=1)
    assert m.deactivated_heat_sinks == 4 and compute_heat_dissipation(m) == 10
    heat.choose_heat_sink_deactivation(m, next_turn=2)        # no radical: keep 20 >= 14 -> all on
    assert m.deactivated_heat_sinks == 0
    a = clone_mech(ASYMPTOTE)
    orchestrator._attach_mech_config(a, {"hex": "0505", "facing": "N", "gunnery": 4, "piloting": 5,
                                         "min_heat": 0, "max_heat": 4}, "Test")
    assert a.deactivated_heat_sinks == 0                       # min_heat 0: never switches off


@check
def min_heat_floor_pads_fire():
    """Daniel 2026-10-19: min_heat is the end-of-turn floor. With no chance
    to hit (pre-TN 16) the knapsack fires nothing; padding then adds ENERGY
    weapons (ammo weapons never - Daniel, 2026-08-05) until the turn would
    end at min_heat. Asymptote, 22 dissipation, 5 x 4-heat lasers: min_heat 9
    needs 31 weapon heat, so all 20; min_heat 0 needs nothing.
    Gear mech: only ML + PPC (13) are energy, so 13 even though it can't reach 9."""
    a = clone_mech(ASYMPTOTE)
    orchestrator._attach_mech_config(a, {"hex": "0505", "facing": "N", "gunnery": 4, "piloting": 5,
                                         "min_heat": 9, "max_heat": 30}, "Test")
    for floor, want in ((9, 20), (0, 0)):
        _, _, w_heat = weapon_selection.select_weapons_to_fire(
            a, 3, 16, floor, a.max_heat, dissipation=22, movement_heat=0, other_heat=0)
        assert w_heat == want, (floor, w_heat)
    m = gear(min_heat=9)
    _, _, w_heat = weapon_selection.select_weapons_to_fire(
        m, 3, 16, m.min_heat, m.max_heat, dissipation=14, movement_heat=0, other_heat=heat.other_heat(m))
    assert w_heat == 13, w_heat


@check
def aimed_shots():
    """p.70: aimed shots only at immobile targets, never with cluster weapons;
    head shots +7 vs the centre torso; 1D6 4+ lands on the aimed location."""
    terrain_map = orchestrator._load_map()

    def declare(location, shut_down=True):
        saved = config.AIMED_SHOT_LOCATION
        config.AIMED_SHOT_LOCATION = location
        try:
            a, t = gear(), clone_mech(ASYMPTOTE)
            orchestrator._attach_mech_config(t, {"hex": "0508", "facing": "N", "gunnery": 4, "piloting": 5,
                                                 "min_heat": 0, "max_heat": 4}, "Target")
            a.hex, a.facing = "0505", "S"
            t.shutdown = shut_down
            rep = attack_resolution.SideReport()
            with ScriptedDice([], default=12):
                attack_resolution.declare_attacks(a, t, terrain_map, rep)
            return t, rep.attacks_list
        finally:
            config.AIMED_SHOT_LOCATION = saved

    _, ct = declare("Center Torso")
    assert ct and all((x.aimed_at == "Center Torso") != attack_resolution.is_cluster_weapon(x.weapon) for x in ct)
    _, head = declare("Head")
    tn_ct = {x.weapon.name: x.tn for x in ct if x.aimed_at}
    assert all(x.tn == tn_ct[x.weapon.name] + 7 for x in head if x.aimed_at)
    _, mobile = declare("Center Torso", shut_down=False)
    assert not any(x.aimed_at for x in mobile)

    t, attacks = declare("Center Torso")
    laser = next(x for x in attacks if x.aimed_at)
    before = t.locations["Center Torso"]["armor"]
    with ScriptedDice([], default=7), Picks([4]):
        attack_resolution._resolve_aimed_hit(t, laser.weapon, attack_resolution._damage_type_for(laser.weapon),
                                             "front", laser)
    assert t.locations["Center Torso"]["armor"] < before       # (Hardened armor halves it)


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
    print(f"All {len(CHECKS)} equipment checks passed." if not failed
          else f"{failed} of {len(CHECKS)} equipment checks FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
