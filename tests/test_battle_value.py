"""
tests/test_battle_value.py - checks Battle Value (2026-10-28, INTEGRATION__battle_value).

    python tests/test_battle_value.py

The anchor is the BV printed in the Technical Readouts for four 'Mechs of the
3039 set (Atlas AS7-D 1,897, Locust LCT-1V 432, Commando COM-2D 541, Jenner
JR7-D 875) - the calculation, ported from MegaMek, has to land on them exactly.
The rest are properties a Battle Value must have: skill moves it by the table,
damage lowers the current value and not the as-built one, and every 'Mech in
the unit pack is priced with no weapon or ammunition missing from the data.
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
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__battle_value as battle_value  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from mech_state import clone_mech  # noqa: E402

config.VERBOSE = False
_TMP = tempfile.mkdtemp()
_ZIP = zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip"))


def unit(name, gunnery=4, piloting=5):
    member = next(n for n in _ZIP.namelist() if n.endswith("/" + name + ".mtf"))
    with redirect_stdout(io.StringIO()):
        mech = parse_mtf(_ZIP.extract(member, _TMP))
    mech.gunnery, mech.piloting = gunnery, piloting
    return mech


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def the_four_published_battle_values():
    for name, published in (("Atlas AS7-D", 1897), ("Locust LCT-1V", 432), ("Commando COM-2D", 541),
                            ("Jenner JR7-D", 875)):
        got = battle_value.battle_value(unit(name))
        assert got == published, f"{name}: {got}, the Technical Readout says {published}"


@check
def skill_scales_the_base_value_by_the_table():
    atlas = unit("Atlas AS7-D")
    base = battle_value.battle_value(atlas, skill=False)
    assert battle_value.battle_value(atlas) == base                     # gunnery 4 / piloting 5 is 1.00
    sharp = unit("Atlas AS7-D", gunnery=3, piloting=4)
    assert battle_value.battle_value(sharp) == round(base * 1.32 + 1e-9), battle_value.battle_value(sharp)
    green = unit("Atlas AS7-D", gunnery=5, piloting=6)
    assert battle_value.battle_value(green) < base < battle_value.battle_value(sharp)
    assert battle_value.skill_factor(0, 0) == 2.42 and battle_value.skill_factor(8, 8) == 0.64


@check
def damage_lowers_the_current_value_and_never_the_built_one():
    atlas = unit("Atlas AS7-D")
    built = battle_value.battle_value(atlas)
    hurt = clone_mech(atlas)
    hurt.locations["Center Torso"]["armor"] = 0
    hurt.locations["Left Arm"]["armor"] = 0
    assert battle_value.battle_value(hurt) == built                      # as built: unchanged
    assert battle_value.battle_value(hurt, current=True) < built
    assert battle_value.battle_value(atlas, current=True) == built       # undamaged: the same number


@check
def a_destroyed_weapon_leaves_the_current_value():
    atlas = unit("Atlas AS7-D")
    built = battle_value.battle_value(atlas, current=True)
    hurt = clone_mech(atlas)
    weapon = next(slot for slots in hurt.crits.values() for slot in slots
                  if getattr(slot, "category", None) == "weapon" and "Autocannon" in slot.name)
    hurt.destroyed_slot_info = {"x": {"name": weapon.name, "instance_id": id(weapon)}}
    assert battle_value.battle_value(hurt, current=True) < built


@check
def the_equipment_data_matches_megameks_numbers():
    items = battle_value._items()
    assert items["mediumlaser"]["bv"] == 46 and items["isgaussrifle"]["bv"] == 320
    assert items["lrm5"]["bv"] == 45 and items["cllrm5"]["bv"] == 55          # IS and Clan launchers share a name
    assert items["isguardianecmsuite"]["bv"] == 61 and items["isantimissilesystem"]["bv"] == 32
    assert "F_DIRECT_FIRE" in items["mediumlaser"]["flags"]


@check
def movement_tables_and_roundings():
    assert [battle_value.tmm(mp) for mp in (0, 2, 3, 4, 5, 7, 10, 18, 25)] == [0, 0, 1, 1, 2, 3, 4, 5, 6]
    assert battle_value.tmm(5, jumped=True) == 3
    assert battle_value._round(2.5) == 3 and battle_value._round(2.49) == 2     # Java's Math.round
    assert [battle_value._engine_multiplier(n) for n in (0, 2, 3, 6)] == [1.0, 0.75, 0.5, 0.25]


@check
def every_unit_in_the_pack_is_priced_with_nothing_missing():
    seen = 0
    for member in _ZIP.namelist():
        if not member.endswith(".mtf") or seen >= 400:
            continue
        with redirect_stdout(io.StringIO()):
            try:
                mech = parse_mtf(_ZIP.extract(member, _TMP))
            except ValueError:
                continue                                                     # a LAM: not a unit this simulator plays
        mech.gunnery, mech.piloting = 4, 5
        missing = battle_value.missing_items(mech)
        assert not missing, f"{member}: no BV data for {missing}"
        assert battle_value.battle_value(mech) > 50, member
        seen += 1
    assert seen >= 300


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
    if failed:
        print(f"{failed} of {len(CHECKS)} battle value checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} battle value checks passed.")


if __name__ == "__main__":
    run_all()
