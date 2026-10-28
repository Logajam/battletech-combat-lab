"""
tests/test_advanced_gear.py - the Tactical Operations: Advanced Units &
Equipment weapons and equipment wired in 2026-10-27 (Daniel: "wire in
functionality of missing weapons, equipment, and hex types already noted"):
HVACs (misfeed, smoke), 'Mech mortars (direct / indirect), the BattleMech
Taser, fluid guns and VGLs (no effect on 'Mechs), shoulder / head turrets,
modular armor, the flail and the chain whip; smoke and active probes
(INTEGRATION__smoke, RULES_REVIEW G34).

    python tests/test_advanced_gear.py

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
import INTEGRATION__advanced_equipment as adv_equip  # noqa: E402
import INTEGRATION__equipment_systems as equip  # noqa: E402
import INTEGRATION__physical as physical  # noqa: E402
import INTEGRATION__smoke as smoke  # noqa: E402
import INTEGRATION__water as water  # noqa: E402
import INTEGRATION__hazards as hazards  # noqa: E402
import INTEGRATION__arcs as arcs  # noqa: E402
import INTEGRATION__ams as ams  # noqa: E402
import INTEGRATION__weapon_rules as weapon_rules  # noqa: E402
import terrain_rules  # noqa: E402
import piloting_rolls  # noqa: E402
from hex_geometry import parse_hex_label  # noqa: E402
from los import has_los, trace_los_path  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from mech_state import clone_mech, compute_walk_mp, compute_jump_mp, DamageType  # noqa: E402
from damage_resolution import get_weapons, apply_damage, resolve_slot_hit  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
_TMP = tempfile.mkdtemp()


def unit(path):
    with zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip")) as z:
        out = z.extract(f"meks/{path}.mtf", _TMP)
    with redirect_stdout(io.StringIO()):
        return parse_mtf(out)


JURN = unit("XTRs/Periphery/Atlas AS-700 Jurn")             # HVAC/10, Beagle probe
MINSK = unit("Golden Century/Minsk 2")                      # Clan 'Mech mortar 4
VINDICATOR = unit("XTRs/Liao/Vindicator VND-3LD (Dao)")     # Mek Taser
STILETTO = unit("XTRs/Steiner/Stiletto STO-6X")             # two shoulder turrets
BANSHEE = unit("XTRs/Steiner/Banshee BNC-11X")              # modular armor
TREBUCHET = unit("XTRs/Periphery/Trebuchet TBT-XK7")        # chain whip, modular armor
POMPIER = unit("XTRs/Republic I/Valiant VLT-3E")             # fluid gun

CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def hexinfo(level=0, **features):
    return {"level": level, "features": dict(features), "impassable": False}


def board(changes=None):
    hexes = {f"{c:02d}{r:02d}": hexinfo() for c in range(1, 17) for r in range(1, 18)}
    hexes.update(changes or {})
    tm = terrain_rules.prepare_board({"width": 16, "height": 17, "hexes": hexes})
    water.set_board(tm)
    hazards.set_board(tm)
    smoke.set_board(tm)
    return tm


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
def slot_counts_from_the_tables():
    """TO:AUE construction table: an HVAC/10 is ONE 6-slot weapon, a Clan
    mortar 4 one 2-slot weapon (each line was read as its own gun before)."""
    assert len(named(JURN, "Hyper Velocity")) == 1
    assert named(JURN, "Hyper Velocity")[0].slots_occupied == 6
    assert len(named(MINSK, "Mortar")) == 1


@check
def hvac_misfeed_and_smoke():
    """p.97: a to-hit 2 destroys the HVAC and explodes one round (10); firing
    fills the hex behind with heavy smoke until the turn after."""
    tm = board()
    a, t = place(JURN, "0808", "N"), place(JURN, "0804", "S", "Blue")
    hvac = named(a, "Hyper Velocity")[0]
    hits = a.pilot_hits
    adv.hvac_misfeed(a, hvac, "Right Torso")
    assert not named(a, "Hyper Velocity") and a.pilot_hits == hits + 1
    adv.hvac_smoke(a, t, tm, 3)
    assert tm["hexes"]["0809"]["smoke"] == {"density": smoke.HEAVY, "until": 4}
    smoke.end_phase(3)
    assert "smoke" in tm["hexes"]["0809"]
    smoke.end_phase(4)
    assert "smoke" not in tm["hexes"]["0809"]


@check
def smoke_in_los_and_probes():
    """Core p.124: heavy smoke = heavy woods (+2), never past 2 a hex with
    woods; an active probe ignores smoke's to-hit within its range (p.197)."""
    xy = parse_hex_label
    tm = board()
    smoke.add("0807", smoke.HEAVY, 9, "test")
    assert has_los(xy("0809"), xy("0805"), tm).modifier == 2
    smoke.add("0806", smoke.LIGHT, 9, "test")                  # 2 + 1 points: blocked (p.58)
    assert not has_los(xy("0809"), xy("0805"), tm).los
    tm = board({"0807": hexinfo(woods=["1"])})
    smoke.add("0807", smoke.HEAVY, 9, "test")                  # light woods + heavy smoke: 2, not 3
    r = has_los(xy("0809"), xy("0805"), tm)
    assert r.los and r.modifier == 2
    tm = board()
    smoke.add("0806", smoke.HEAVY, 9, "test")
    a, t = place(JURN, "0809", "N"), place(JURN, "0804", "S", "Blue")    # Beagle: range 4
    trace = trace_los_path(xy("0809"), xy("0804"), tm)
    assert trace.result.modifier == 2 and smoke.probe_relief(a, t, trace, 5) == 2
    ecm = place(MINSK, "0804", "S", "Blue")                      # its ECM is 5 hexes away: jammed
    assert smoke.probe_relief(a, ecm, trace, 5) == 0
    b = place(BANSHEE, "0809", "N")                              # no probe
    assert smoke.probe_relief(b, t, trace, 5) == 0


@check
def mortar_rules():
    """p.136: +3 fired directly, 2-point groups, AMS can't engage; with no
    LOS it fires indirectly (only the mortar)."""
    mortar = named(MINSK, "Mortar")[0]
    assert weapon_rules.weapon_tn_modifier(mortar, "short") == 3
    assert weapon_rules.damage_groupings(mortar, 8) == [2, 2, 2, 2]
    assert not ams.engageable(mortar)
    tm = board({"0806": hexinfo(4)})                             # a hill: no LOS
    a, t = place(MINSK, "0809", "N"), place(MINSK, "0803", "S", "Blue")
    assert not has_los(parse_hex_label("0809"), parse_hex_label("0803"), tm).los
    rep = attack_resolution.SideReport()
    with ScriptedDice([9]):
        attack_resolution.declare_attacks(a, t, tm, rep)
    assert [x.weapon.name for x in rep.attacks_list] == [mortar.name]


@check
def taser_effects():
    """pp.157-158: 11+ shuts a 'Mech down 3 turns; else +2 Piloting /
    Gunnery and 5 heat a turn for 3 turns; nothing on a unit over 100 tons."""
    a, t = place(VINDICATOR), place(VINDICATOR, "0807", "S", "Blue")
    with ScriptedDice([11]):
        adv.taser_hit(a, t, 2)
    assert t.shutdown and t.taser_shutdown_until == 5
    adv.end_phase(t, 4)
    assert t.shutdown
    adv.end_phase(t, 5)
    assert not t.shutdown
    with ScriptedDice([10]):
        adv.taser_hit(a, t, 6)
    assert adv.interference(t) == 2 and adv.taser_heat(t) == 5
    assert equip.own_attack_modifier(t) >= 2
    base = place(VINDICATOR)
    assert piloting_rolls.special_case_modifier(t) == piloting_rolls.special_case_modifier(base) + 2
    adv.end_phase(t, 9)
    assert adv.interference(t) == 0
    t.mass = 105
    with ScriptedDice([]):
        adv.taser_hit(a, t, 10)                                   # no roll at all
    assert adv.interference(t) == 0 and not t.shutdown


@check
def no_effect_weapons():
    """Fluid guns with water ammo (p.175) don't fire at a 'Mech."""
    m = place(POMPIER)
    guns = [w for w in get_weapons(m) if "Fluid" in w.name]
    assert guns and all(id(w) in adv.no_effect_ids(m) for w in guns)


@check
def shoulder_turrets():
    """TO:AUE p.159: a shoulder turret's weapons bear anywhere but through
    the opposite side's hexsides; a locked turret only its last way."""
    m = place(STILETTO)
    locs = attack_resolution.weapon_locations(m)
    left = [w for w in get_weapons(m) if getattr(w, "turret_mounted", False) and "Left Torso" in locs[id(w)]]
    assert left and arcs.weapon_class(m, left[0], locs[id(left[0])]) == "turret:Left Torso"
    legs = arcs.leg_offsets(m)
    for arc, ok in ((arcs.FORWARD, True), (arcs.LEFT, True), (arcs.REAR, True), (arcs.RIGHT, False)):
        key = arcs.ArcKey(arc, frozenset(), False, None)
        assert (id(left[0]) not in arcs.unavailable(m, left, locs, key)) == ok, arc
    target_arcs = arcs.arcs_between((0, 0), (0, 4))
    behind = next(f for f in range(6) if target_arcs[f] == arcs.FORWARD)    # the way it last fired
    m.mech_turret_dir = {"Left Torso": behind}
    slot = next(i for i, s in enumerate(m.crits["Left Torso"]) if "Turret" in getattr(s, "name", ""))
    resolve_slot_hit(m, "Left Torso", slot, m.crits["Left Torso"][slot], 1, 1)
    assert arcs.mech_turret_locked(m, "Left Torso")
    legs = arcs.leg_offsets(m)
    key = arcs.key_for(target_arcs, 0, arcs.NO_ACTION, legs)
    assert id(left[0]) not in arcs.unavailable(m, left, locs, key)            # still points at it
    key = arcs.key_for(arcs.arcs_between((0, 4), (0, 0)), 0, arcs.NO_ACTION, legs)
    assert id(left[0]) in arcs.unavailable(m, left, locs, key)                # locked away from this one


@check
def modular_armor():
    """p.93: modular armor takes damage first; -1 Walk / Jump MP and +1 PSR
    while any is left; a slot hit destroys its points."""
    m = place(BANSHEE)
    plain = clone_mech(BANSHEE)
    plain.modular_armor = []
    assert m.modular_armor and compute_walk_mp(m) == compute_walk_mp(plain) - 1
    assert piloting_rolls.special_case_modifier(m) == piloting_rolls.special_case_modifier(plain) + 1
    s = m.modular_armor[0]
    loc, field = s.modular_location, s.modular_field
    before = m.locations[loc][field]
    apply_damage(m, loc, 13, armor_field=field, damage_type=DamageType.BALLISTIC)
    assert s.modular_points == 0 and m.locations[loc][field] == before - 3
    other = m.modular_armor[1]
    slot = next(i for i, x in enumerate(m.crits[other.modular_location]) if x is other)
    resolve_slot_hit(m, other.modular_location, slot, other, 1, 1)
    assert other.modular_points == 0
    for x in m.modular_armor:
        x.modular_points = 0
    assert compute_walk_mp(m) == compute_walk_mp(plain) and not adv_equip.active(m)


@check
def melee_weapons():
    """p.101: a chain whip does 3 whatever the 'Mech's weight, at the
    sword's -2."""
    m = place(TREBUCHET)
    whip = [s for s in m.crits["Right Arm"] if "Whip" in getattr(s, "name", "")]
    assert whip and physical._weapon_kind(whip[0]) == (-2, None, 3, "standard")


@check
def every_gauss_rifle_explodes():
    """Core p.184 (Daniel 2026-10-28: "Fix it"): every Gauss rifle's first
    critical hit is a component explosion - light, heavy, HAG too."""
    from equipment import lookup_equipment
    for name in ("ISGaussRifle", "ISLightGaussRifle", "ISHeavyGaussRifle", "ISImprovedHeavyGaussRifle", "ISSBGR",
                 "CLHAG20", "CLAPGaussRifle", "ISMagshotGR"):
        assert lookup_equipment(name)["explosive"], name


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
    for module in (water, hazards, smoke):
        module.set_board(None)
    print()
    if failed:
        print(f"{len(failed)} of {len(CHECKS)} advanced gear checks FAILED: {', '.join(failed)}")
        return 1
    print(f"All {len(CHECKS)} advanced gear checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
