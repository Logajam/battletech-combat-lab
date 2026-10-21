"""
tests/test_weapons.py - checks the weapons that couldn't fire, or fired without
their special rule, before 2026-10-20 (INTEGRATION__weapon_profiles): variable
damage (heavy Gauss, Snub-Nose PPC, VSP lasers), hyper-assault Gauss, M-pods,
machine gun arrays, bombast lasers, rifles, flamer / plasma heat on the target,
Arrow IV and artillery cannons, the Apollo saturation mode (an attack on a hex,
Daniel 2026-10-20), the MML LRM grouping, and pooled cluster damage (optional
rule POOL_CLUSTER_DAMAGE).

    python tests/test_weapons.py

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
import INTEGRATION__fire_modes as fire_modes  # noqa: E402
import INTEGRATION__weapon_profiles as wp  # noqa: E402
import INTEGRATION__heat as heat  # noqa: E402
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


ATLAS_S2 = unit("3050U/Atlas AS7-S2")                  # heavy Gauss (split torso / arm)
AWESOME = unit("3050U/Awesome AWS-10KM")              # Snub-Nose PPCs
BARGHEST = unit("3060u/Barghest BGS-7S")              # medium VSP lasers, ER flamer, MML 7
BLACK_HAWK = unit("3050U/Black Hawk (Nova) F")        # HAG 20
CATAPHRACT_LL = unit("3050U/Cataphract CTF-3LL")      # plasma rifle
BOMBARD = unit("3055U/Bombard BMB-1X")                # M-pods
BOMBARDIER_K = unit("3050U/Bombardier BMB-14K")       # machine gun array
STRIDER = unit("3058Uu/Strider SR1-OX")               # bombast laser
DEEP_LORD = unit("ProtoTypes/Deep Lord RCL-Z1M MilitiaMech")  # heavy rifle
BOMBARDIER_A = unit("3050U/Bombardier BMB-05A")       # Arrow IV
LOKI = unit("3145/Clans/Loki Mk II (Hel) B")          # artillery cannon
TEMPLAR = unit("3067 Unabridged/IS Meks/Templar TLR1-OH")  # MRM 30s + Apollo
ARCHER = unit("3039u/Archer ARC-2R")                  # target / two LRM 20s
TABLE = config.CLUSTER_HITS_TABLE


def fresh(template, hex_="0808", facing="N", name="Red", max_heat=30):
    m = clone_mech(template)
    orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": 5,
                                         "min_heat": 0, "max_heat": max_heat}, name)
    return m


def target():
    return fresh(ARCHER, "0804", "S", "Blue")


def weapon(mech, test):
    return next(w for w in get_weapons(mech) if test(w))


def planner(a, t, hex_offset=None):
    return fire_modes.Planner(a, t, attack_resolution.tn_adjuster(a, t), hex_offset=hex_offset)


def hit(w, plan, side="front"):
    return DeclaredAttack(weapon=w, tn=6, roll=8, hit=True, side=side, fire=plan)


def damage_taken(t, attack, rolls, picks=None):
    before = attack_resolution.total_hp(t)
    with ScriptedDice(rolls, default=7):
        if picks is not None:
            config.pick_number = lambda n, prompt="": picks
        attack_resolution._resolve_one_attack(None, t, attack, None)
    return before - attack_resolution.total_hp(t)


class Knobs:
    def __init__(self, **values):
        self.values = values

    def __enter__(self):
        self.saved = {k: getattr(config, k) for k in self.values}
        for k, v in self.values.items():
            setattr(config, k, v)

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            setattr(config, k, v)


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def variable_damage():
    """Heavy Gauss 25 / 20 / 10; Snub-Nose PPC 10 / 8 / 5; medium VSP 9 / 7 / 5 (by bracket)."""
    t = target()
    for template, test, want in ((ATLAS_S2, wp.is_heavy_gauss, (25, 20, 10)),
                                 (AWESOME, lambda w: "SNPPC" in wp.cn(w), (10, 8, 5)),
                                 (BARGHEST, lambda w: "VARIABLESPEED" in wp.cn(w) or "VSP" in wp.cn(w), (9, 7, 5))):
        a = fresh(template)
        w = weapon(a, test)
        got = tuple(fire_modes.damage_per(w, fire_modes.PLAIN._replace(bracket=b)) for b in ("short", "medium", "long"))
        assert got == want, (w.name, got)
        plan = planner(a, t)(w, w.weapon_range["long"], 6)[2]
        assert plan.bracket == "long" and damage_taken(t, hit(w, plan), []) == want[2]


@check
def hyper_assault_gauss():
    """HAG 20: the 20 column, 1 damage a slug, +2 short / -2 long, 5-point groupings."""
    a, t = fresh(BLACK_HAWK), target()
    hag = weapon(a, wp.is_hag)
    short = planner(a, t)(hag, 3, 6)[2]
    assert fire_modes.column(hag, short) == 20 and fire_modes.cluster_modifier(hag, short) == 2
    assert fire_modes.cluster_modifier(hag, short._replace(bracket="long")) == -2
    assert fire_modes.grouping(hag, short) == 5 and not fire_modes.aimable(hag, short)
    with Knobs(POOL_CLUSTER_DAMAGE=False):
        assert damage_taken(t, hit(hag, short), [5]) == TABLE[7][20]


@check
def m_pod_columns():
    """M-pod: the 15 / 10 / 5 column at 0-1 / 2 / 3 hexes, 1-point hits."""
    a, t = fresh(BOMBARD), target()
    pod = weapon(a, wp.is_mpod)
    cols = [fire_modes.column(pod, planner(a, t)(pod, d, 6)[2]) for d in (1, 2, 3)]
    assert cols == [15, 10, 5] and planner(a, t)(pod, 4, 6) is None


@check
def machine_gun_array():
    """The array fires its location's guns as one attack: +2 on the guns'
    column, every hit to one location; the guns can't fire alone."""
    a, t = fresh(BOMBARDIER_K), target()
    mga = weapon(a, wp.is_mga)
    guns = wp.mga_guns(a, mga)
    assert 1 <= len(guns) <= 4 and {id(g) for g in guns} <= wp.array_gun_ids(a)
    plan = planner(a, t)(mga, 1, 6)[2]
    assert plan.kind == "array" and plan.shots == len(guns) and fire_modes.cluster_modifier(mga, plan) == 2
    before = {k: v["armor"] for k, v in t.locations.items()}
    dmg = damage_taken(t, hit(mga, plan), [8, 7])            # cluster 8 + 2 -> 10; location 7 (CT)
    hits = TABLE[10][len(guns)]
    assert dmg == hits * mga.damage_per_shot
    changed = [k for k, v in t.locations.items() if v["armor"] != before[k]]
    assert changed == ["Center Torso"], changed


@check
def bombast_laser():
    """8 / 12 / 16 damage at +0 / +1 / +2 to hit and 6 / 9 / 12 heat; the
    munition stub picks (greedy)."""
    a, t = fresh(STRIDER), target()
    bl = weapon(a, wp.is_bombast)
    kinds = planner(a, t).kinds(bl)
    assert [(fire_modes.damage_per(bl, p), p.tn, fire_modes.heat(bl, p)) for p in kinds] == \
        [(8, 0, 6), (12, 1, 9), (16, 2, 12)]
    assert planner(a, t)(bl, 3, 4)[2].kind in wp.BOMBAST


@check
def rifles_lose_3_against_mechs():
    a, t = fresh(DEEP_LORD), target()
    rifle = weapon(a, wp.is_rifle)
    assert fire_modes.damage_per(rifle, fire_modes.PLAIN) == rifle.damage_per_shot - 3
    assert damage_taken(t, hit(rifle, fire_modes.PLAIN), []) == rifle.damage_per_shot - 3


@check
def heat_on_the_target():
    """Flamers add their damage as heat (ER flamer 1); plasma rifle 1D6;
    outside heat caps at 15 a turn, added in the Heat Phase."""
    a, t = fresh(BARGHEST), target()
    er = weapon(a, lambda w: "FLAMER" in wp.cn(w))
    damage_taken(t, hit(er, fire_modes.PLAIN), [])
    assert t.outside_heat == 1
    p = fresh(CATAPHRACT_LL)
    rifle = weapon(p, lambda w: "PLASMARIFLE" in wp.cn(w))
    damage_taken(t, hit(rifle, fire_modes.PLAIN), [], picks=6)
    assert t.outside_heat == 7
    t.outside_heat = 40
    t.current_heat, t.movement_heat = 0, 0
    dissipation = heat.compute_heat_dissipation(t)
    with redirect_stdout(io.StringIO()), ScriptedDice([], default=12):
        heat.resolve_heat_phase(t, 0)
    assert t.current_heat == max(0, 15 - dissipation) and t.outside_heat == 0


@check
def arrow_iv():
    """Arrow IV: a hex attack 7-17 hexes away, Gunnery + 4, no range / TMM
    modifier; 20 area-effect damage on a hit; a miss by 1-2 lands next door: 10."""
    a, t = fresh(BOMBARDIER_A), target()
    arrow = weapon(a, wp.is_arrow)
    assert planner(a, t, hex_offset=0)(arrow, 5, 6) is None             # under 7 hexes
    value, _, plan = planner(a, t, hex_offset=-3)(arrow, 10, 6)
    assert plan.kind == "artillery" and plan.tn == 4
    assert planner(a, t)(arrow, 10, 6) is None                           # movement scoring: not priced
    assert damage_taken(t, hit(arrow, plan), []) == 20
    t.hex = "0804"
    miss = DeclaredAttack(weapon=arrow, tn=9, roll=8, hit=False, fire=plan)
    before = attack_resolution.total_hp(t)
    with ScriptedDice([], default=7):
        config.pick_number = lambda n, prompt="": 4                       # direction 4 (down), 1 hex
        attack_resolution._resolve_area_miss(a, t, miss, TERRAIN)
    assert before - attack_resolution.total_hp(t) == 10


@check
def arrow_iv_scatter_held_by_firing_arc():
    """A scatter can't leave the launcher's firing arc: it lands in the last
    hex before it would (pp.182-183; Daniel's known issue, fixed 2026-10-21).
    The Bombardier on 0808 faces NE; its Arrow IV (split left arm / torso)
    fires forward only, so north of the board's top row is the arc's edge."""
    def scatter(target_hex, direction, roll):
        a, t = fresh(BOMBARDIER_A, facing="NE"), target()
        t.hex = target_hex
        arrow = weapon(a, wp.is_arrow)
        plan = fire_modes.ShotPlan(kind="artillery")
        miss = DeclaredAttack(weapon=arrow, tn=9, roll=roll, hit=False, fire=plan)
        before = attack_resolution.total_hp(t)
        with ScriptedDice([], default=7):
            config.pick_number = lambda n, prompt="": direction
            attack_resolution._resolve_area_miss(a, t, miss, TERRAIN)
        return before - attack_resolution.total_hp(t)
    # 0801, direction 6 (upper left): the first hex is already outside - it lands on the target: 20.
    assert scatter("0801", 6, 7) == wp.ARROW_DAMAGE
    # 0902, direction 6, 2 hexes: the second is outside - held 1 hex away (0801): the splash, 10.
    assert scatter("0902", 6, 5) == wp.ARROW_SPLASH
    # The same 2-hex scatter down the board (direction 4) stays in the arc: 2 hexes away, nothing.
    assert scatter("0902", 4, 5) == 0


@check
def machine_gun_array_ammo():
    """Each gun the array fires takes its own round, and guns sharing bins
    share the rounds (Daniel's known issue, checked 2026-10-21): a shared bin
    with 1 round fires one gun, with none the array can't fire, and
    declaring the attack takes one round a gun from the bin."""
    a, t = fresh(BOMBARDIER_K), target()
    mga = weapon(a, wp.is_mga)
    guns = wp.mga_guns(a, mga)
    bins = {id(b): b for g in guns for b in ammo.bins_for(a, g)}
    assert len(guns) == 3 and len(bins) == 1                 # three machine guns on one 100-round bin
    bin_ = next(iter(bins.values()))
    shots = lambda: (planner(a, t)(mga, 1, 6) or (0, 0, fire_modes.ShotPlan(shots=0)))[2].shots
    assert shots() == 3
    assert fire_modes.take_array_rounds(a, mga, 3) and bin_.shots_left == 97
    bin_.shots_left = 2
    assert shots() == 2
    bin_.shots_left = 1
    assert shots() == 1
    fire_modes.take_array_rounds(a, mga, 1)
    assert bin_.shots_left == 0 and planner(a, t)(mga, 1, 6) is None
    # A destroyed gun drops out of the array's column.
    b = fresh(BOMBARDIER_K)
    b_mga = weapon(b, wp.is_mga)
    gun = wp.mga_guns(b, b_mga)[0]
    loc, idx = next((l, i) for l, slots in b.crits.items() for i, s in enumerate(slots) if s is gun)
    b.crits[loc][idx] = "DESTROYED"                           # as damage_resolution.resolve_slot_hit does
    b.destroyed_slot_info[(loc, idx)] = {"name": gun.name, "instance_id": id(gun)}
    assert len(wp.mga_guns(b, b_mga)) == 2 and planner(b, t)(b_mga, 1, 6)[2].shots == 2


@check
def artillery_cannon_no_immobile_bonus():
    """Artillery cannons: a normal attack, but never the immobile -4."""
    a, t = fresh(LOKI), target()
    cannon = weapon(a, wp.is_art_cannon)
    t.shutdown = True
    assert fire_modes.area_immobile_fix(cannon, t) == 4


@check
def apollo_saturation():
    """Saturation: an attack on the hex (no target modifiers), Cluster roll
    without the MRM -1, hits / 3 damage."""
    a, t = fresh(TEMPLAR), target()
    mrm = weapon(a, fire_modes.is_mrm)
    plans = {p.kind: p for p in planner(a, t).kinds(mrm)}
    assert set(plans) == {"", "saturation"}
    assert planner(a, t)._decide(mrm, 5, 6, False).kind == ""             # no hex offset: saturation unpriced
    sat = plans["saturation"]
    v_with_tmm = planner(a, t, hex_offset=0).value(mrm, sat, 5, 9)[1]
    v_no_tmm = planner(a, t, hex_offset=-3).value(mrm, sat, 5, 9)[1]
    assert v_with_tmm - v_no_tmm == 3
    assert damage_taken(t, hit(mrm, sat), [7]) == fire_modes.third(TABLE[7][30])


@check
def mml_lrm_grouping_is_5():
    a = fresh(BARGHEST)
    mml = weapon(a, fire_modes.is_mml)
    lrm = next(p for p in planner(a, target()).kinds(mml) if p.kind == "lrm")
    assert fire_modes.grouping(mml, lrm) == 5


@check
def pooled_cluster_damage():
    """Daniel: two LRM 20 hits of 12 each land as 5, 5, 5, 5, 4 (pooled); the
    per-attack reading: 5, 5, 2 twice."""
    archer = fresh(ARCHER, name="Red")
    lrms = [w for w in get_weapons(archer) if "LRM" in w.name]

    def groups(pool_on):
        t = fresh(ARCHER, "0804", "S", "Blue")
        sizes = []
        real = attack_resolution._resolve_hit

        def spy(target_, damage, *args, **kw):
            sizes.append(damage)
            return real(target_, damage, *args, **kw)
        attack_resolution._resolve_hit = spy
        try:
            with Knobs(POOL_CLUSTER_DAMAGE=pool_on), ScriptedDice([], default=7):
                pool = {} if pool_on else None
                for w in lrms:                                 # cluster roll 7 on the 20 column: 12
                    attack_resolution._resolve_one_attack(archer, t, hit(w, fire_modes.PLAIN), None, pool)
                for (size, dtype, side, cover), parts in (pool or {}).items():
                    attack_resolution._apply_groups(t, sum(d for _, d in parts), size, dtype, side, cover)
        finally:
            attack_resolution._resolve_hit = real
        return sizes
    assert TABLE[7][20] == 12
    assert groups(True) == [5, 5, 5, 5, 4]
    assert groups(False) == [5, 5, 2, 5, 5, 2]


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
        print(f"{failed} of {len(CHECKS)} weapon checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} weapon checks passed.")


if __name__ == "__main__":
    run_all()
