"""
tests/test_heat.py - checks the Heat Scale rules in INTEGRATION__heat.py
against the Core Rulebook Heat chapter (pp.102-107): the threshold tables,
movement and engine heat, and a scripted Heat Phase for shutdown, restart,
ammo explosions and life-support hits.

    python tests/test_heat.py

Dice are scripted: each check queues the 2D6 results it expects to be
rolled, in order; any further roll (crit checks, fall damage) gets a fixed
default. A check also fails if a queued roll is never used, so a rule that
skips or adds a roll is caught.

Uses data/TEST_Synthetic_Loadout.mtf (10 single heat sinks; ammo bins:
2x LRM 15 and 1x SRM 6 in the torsos, 1x AC/5 in the right arm) and
data/Asymptote II iJ Mpulse.mtf (no ammo).
"""

import os
import sys
import traceback
from types import SimpleNamespace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402 - registers bare "config" first
config.STATS = False  # event log + report off: not part of a test or battery (2026-11-06)
import INTEGRATION__orchestrator as orchestrator  # noqa: E402 - puts pathfinder/ on sys.path
import INTEGRATION__heat as heat  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from mech_state import clone_mech, compute_walk_mp, compute_running_mp, compute_jump_mp, \
    compute_heat_dissipation  # noqa: E402
import piloting_rolls  # noqa: E402

config.VERBOSE = False
SYNTHETIC = parse_mtf(config.data_path("TEST_Synthetic_Loadout.mtf"))
ASYMPTOTE = parse_mtf(config.data_path("Asymptote II iJ Mpulse.mtf"))


class ScriptedDice:
    """Replaces config.roll_2d6 / pick_number for one check."""
    def __init__(self, rolls, default=7):
        self.queue = list(rolls)
        self.default = default
        self.count = 0

    def roll(self, prompt=""):
        self.count += 1
        return self.queue.pop(0) if self.queue else self.default

    def __enter__(self):
        self.saved = config.roll_2d6, config.pick_number
        config.roll_2d6 = self.roll
        config.pick_number = lambda n, prompt="": 1
        return self

    def __exit__(self, *exc):
        config.roll_2d6, config.pick_number = self.saved
        if exc[0] is None:
            assert not self.queue, f"scripted rolls never used: {self.queue}"


def fresh(template=SYNTHETIC, heat_level=0, max_heat=30):
    m = clone_mech(template)
    orchestrator._attach_mech_config(m, {"hex": "0505", "facing": "N", "gunnery": 4, "piloting": 5,
                                         "min_heat": 0, "max_heat": max_heat}, "Test")
    m.current_heat = heat_level
    return m


def traits(ijj=False, xxl=False, scm=False):
    return SimpleNamespace(has_improved_jump_jets=ijj, has_xxl_engine=xxl, has_supercooled_myomer=scm)


# =============================================================================
CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def heat_data_table():
    """p.103 thresholds; only the highest of each type applies (p.104)."""
    mp = {4: 0, 5: 1, 9: 1, 10: 2, 14: 2, 15: 3, 19: 3, 20: 4, 24: 4, 25: 5, 40: 5}
    fire = {7: 0, 8: 1, 12: 1, 13: 2, 16: 2, 17: 3, 23: 3, 24: 4, 35: 4}
    shut = {13: None, 14: 4, 17: 4, 18: 6, 21: 6, 22: 8, 25: 8, 26: 10, 29: 10}
    ammo = {18: None, 19: 4, 22: 4, 23: 6, 27: 6, 28: 8, 35: 8}
    for level, want in mp.items():
        assert heat.mp_penalty_for(level) == want, f"MP penalty at {level}"
    for level, want in fire.items():
        assert heat.fire_modifier_for(level) == want, f"fire modifier at {level}"
    for level, want in shut.items():
        assert heat.shutdown_avoid_tn(level) == want, f"shutdown avoid at {level}"
    for level, want in ammo.items():
        assert heat.ammo_avoid_tn(level) == want, f"ammo avoid at {level}"


@check
def movement_heat():
    """p.102: standard, Improved JJ, XXL, XXL + Improved JJ, super-cooled myomer."""
    cases = [
        (traits(), "Stand Still", 0, 0), (traits(), "Walk", 3, 1), (traits(), "Run", 6, 2),
        (traits(), "Jump", 2, 3), (traits(), "Jump", 5, 5),
        (traits(ijj=True), "Jump", 5, 3), (traits(ijj=True), "Jump", 7, 4),
        (traits(xxl=True), "Stand Still", 0, 2), (traits(xxl=True), "Walk", 2, 4),
        (traits(xxl=True), "Run", 5, 6), (traits(xxl=True), "Jump", 2, 6), (traits(xxl=True), "Jump", 4, 8),
        (traits(ijj=True, xxl=True), "Jump", 2, 3), (traits(ijj=True, xxl=True), "Jump", 5, 5),
        (traits(scm=True), "Walk", 4, 0), (traits(scm=True), "Run", 6, 0), (traits(scm=True), "Jump", 4, 4),
        (traits(xxl=True, scm=True), "Stand Still", 0, 0),
    ]
    for mech, mode, hexes, want in cases:
        got = heat.movement_heat(mech, mode, hexes)
        assert got == want, f"{vars(mech)} {mode} {hexes}: expected {want}, got {got}"


@check
def engine_heat_and_budget():
    """p.102: +5 / +10 total; none while shut down. Budget (Daniel) also
    subtracts it: max 4 + sinks 10 - current 0 - movement 1 - engine 5 = 8."""
    m = fresh(max_heat=4)
    for hits, want in ((0, 0), (1, 5), (2, 10)):
        m.engine_hits = hits
        assert heat.engine_heat(m) == want
    m.engine_hits = 1
    assert heat.weapon_heat_budget(m, 1) == 8
    m.shutdown = True
    assert heat.engine_heat(m) == 0


@check
def mp_and_fire_effects_next_turn():
    """Heat 9 -> -1 Walking MP, Running recalculated, +1 to-hit; heat 25 ->
    Walking 0 (allowed, p.104), Jumping unaffected."""
    m = fresh(heat_level=9)
    heat.apply_heat_effects(m)
    assert (m.heat_mp_penalty, m.heat_fire_modifier) == (1, 1)
    assert compute_walk_mp(m) == 3 and compute_running_mp(m) == 5   # walk 4 -> 3, run ceil(4.5)
    m.current_heat = 25
    heat.apply_heat_effects(m)
    assert compute_walk_mp(m) == 0 and compute_running_mp(m) == 0
    a = fresh(ASYMPTOTE)
    jump_cold = compute_jump_mp(a)
    a.current_heat = 25
    heat.apply_heat_effects(a)
    assert compute_jump_mp(a) == jump_cold > 0


@check
def heat_phase_accumulates_engine_heat():
    """10 + walk 1 + weapons 6 + engine 5 - sinks 10 = 12: no rolls below 14."""
    m = fresh(heat_level=10)
    m.engine_hits = 1
    m.movement_heat = 1
    with ScriptedDice([]):
        heat.resolve_heat_phase(m, weapon_heat=6)
    assert m.current_heat == 12 and not m.shutdown
    assert (m.heat_mp_penalty, m.heat_fire_modifier) == (2, 1)


@check
def shutdown_roll():
    """p.104: at 14, one roll needing 4+."""
    m = fresh(heat_level=10)
    with ScriptedDice([3]):
        heat.resolve_heat_phase(m, weapon_heat=14)     # 10 + 14 - 10 = 14
    assert m.current_heat == 14 and m.shutdown
    m = fresh(heat_level=10)
    with ScriptedDice([4]):
        heat.resolve_heat_phase(m, weapon_heat=14)
    assert not m.shutdown


@check
def shutdown_automatic_at_30_and_unconscious():
    """p.104: no roll at 30+; an unconscious MechWarrior can't override."""
    m = fresh(heat_level=20)
    with ScriptedDice([12]):                            # 12 is the AMMO roll, not a shutdown roll
        heat.resolve_heat_phase(m, weapon_heat=20)     # 20 + 20 - 10 = 30
    assert m.shutdown
    m = fresh(heat_level=10)
    m.crew["pilot"]["unconscious"] = True
    with ScriptedDice([]) as dice:
        heat.resolve_heat_phase(m, weapon_heat=14)     # 10 + 14 - 10 = 14
    assert m.shutdown and dice.count == 0


@check
def restart():
    """p.105: automatic below 14; roll vs the avoid number otherwise; never
    at 30+; no restart roll with an unconscious MechWarrior; no engine heat
    while shut down."""
    m = fresh(heat_level=20)
    m.shutdown = True
    m.engine_hits = 1
    with ScriptedDice([]):
        heat.resolve_heat_phase(m, weapon_heat=0)      # 20 - 10 = 10, no engine heat
    assert m.current_heat == 10 and not m.shutdown

    m = fresh(heat_level=36)
    m.shutdown = True
    with ScriptedDice([9, 12]):                         # restart roll 9 vs 10+, then ammo roll
        heat.resolve_heat_phase(m, weapon_heat=0)      # 26
    assert m.shutdown
    m = fresh(heat_level=36)
    m.shutdown = True
    with ScriptedDice([10, 12]):
        heat.resolve_heat_phase(m, weapon_heat=0)
    assert not m.shutdown

    m = fresh(heat_level=45)
    m.shutdown = True
    with ScriptedDice([12]):                            # only the ammo roll: no restart at 35
        heat.resolve_heat_phase(m, weapon_heat=0)
    assert m.shutdown

    m = fresh(heat_level=30)
    m.shutdown = True
    m.crew["pilot"]["unconscious"] = True
    with ScriptedDice([12]):                            # heat 20: ammo roll only
        heat.resolve_heat_phase(m, weapon_heat=0)
    assert m.shutdown


@check
def ammo_bin_damage_values():
    """p.107: one turn's worth of shots - LRM 15 -> 15, SRM 6 -> 12, AC/5 -> 5."""
    got = sorted((b.name, heat.ammo_bin_damage_value(b)) for _, b in heat.live_ammo_bins(fresh()))
    assert got == [("ISAC5 Ammo", 5), ("ISLRM15 Ammo", 15), ("ISLRM15 Ammo", 15), ("ISSRM6 Ammo", 12)], got


@check
def ammo_explosion():
    """p.107: at 19, shutdown roll first (p.104 order) then one ammo roll
    needing 4+; a failure explodes an LRM 15 bin (highest damage value) and
    the MechWarrior takes 1 hit."""
    m = fresh(heat_level=10)
    bins = heat.live_ammo_bins(m)
    with ScriptedDice([12, 3]):                         # shutdown avoid 12 (6+), ammo 3 (needs 4)
        heat.resolve_heat_phase(m, weapon_heat=19)     # 19
    assert not m.shutdown
    assert [b.name for _, b in bins if b.exploded] == ["ISLRM15 Ammo"]
    assert m.explosions == 1 and m.pilot_hits == 1
    assert not any(b.exploded for _, b in heat.live_ammo_bins(m))

    m = fresh(heat_level=10)
    with ScriptedDice([12, 4]):
        heat.resolve_heat_phase(m, weapon_heat=19)
    assert m.explosions == 0

    a = fresh(ASYMPTOTE, heat_level=30)               # no ammo: no ammo roll at all
    with ScriptedDice([12]) as dice:
        heat.resolve_heat_phase(a, weapon_heat=17)     # 30 + 17 - 22 = 25
    assert a.current_heat == 25 and dice.count == 1   # the shutdown roll only


@check
def life_support_hits():
    """p.107: with life support destroyed, 1 hit at 10-19, 2 at 20+, none below 10."""
    for level, hits in ((9, 0), (10, 1), (19, 1), (20, 2)):
        m = fresh(heat_level=level + 10)
        m.destroyed_slot_info[("Head", 1)] = {"name": "Life Support", "instance_id": None}
        rolls = []
        if level >= 14:
            rolls.append(12)                            # shutdown avoid
        if level >= 19:
            rolls.append(12)                            # ammo avoid
        if hits:
            rolls.append(12)                            # consciousness check
        with ScriptedDice(rolls):
            heat.resolve_heat_phase(m, weapon_heat=0)
        assert m.current_heat == level and m.pilot_hits == hits, (level, m.pilot_hits)


@check
def partial_wing_dissipation():
    """p.103: a working Partial Wing dissipates 3 more."""
    m = fresh()
    base = compute_heat_dissipation(m)
    m.partial_wing_active = True
    assert compute_heat_dissipation(m) == base + 3


@check
def shutdown_mech_in_combat():
    """p.104-105: a shut-down mech is immobile (-4 to hit it), can't attack,
    and a standing shut-down mech's PSR fails automatically."""
    m = fresh()
    m.shutdown = True
    assert attack_resolution._target_tmm(m) == attack_resolution.IMMOBILE_TMM
    rep = attack_resolution.SideReport()
    attack_resolution.declare_attacks(m, fresh(), terrain_map=None, report=rep)
    assert rep.attacks == 0

    piloting_rolls.snapshot_pre_attack_phase(m)
    m.pre_attack_phase_snapshot["total_armor_structure"] += 20   # "took 20+ damage this phase"
    with ScriptedDice([], default=12):                            # a rolled PSR would pass on 12
        attack_resolution._with_piloting(m, piloting_rolls.resolve_attack_phase_psr)
    assert m.prone


@check
def heat_to_hit_modifier_in_tn():
    """The attacker's heat modifier adds straight onto every to-hit number."""
    terrain_map = orchestrator._load_map()
    tns = []
    for mod in (0, 2):
        a, t = fresh(ASYMPTOTE), fresh(ASYMPTOTE)
        a.hex, a.facing, t.hex, t.facing = "0505", "S", "0508", "N"
        a.heat_fire_modifier = mod
        rep = attack_resolution.SideReport()
        with ScriptedDice([], default=7):
            attack_resolution.declare_attacks(a, t, terrain_map, rep)
        tns.append([x.tn for x in rep.attacks_list])
    assert tns[0] and tns[1] == [tn + 2 for tn in tns[0]], tns


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
    print(f"All {len(CHECKS)} heat checks passed." if not failed else f"{failed} of {len(CHECKS)} heat checks FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
