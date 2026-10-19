"""
tests/test_weapon_range.py - checks the range modifier, including the
minimum-range penalty (Daniel, 2026-10-19: +1 per hex inside minimum range,
(min - distance) + 1; a weapon with no listed minimum has minimum 0).

    python tests/test_weapon_range.py

Uses fake weapons with hand-written ranges, so it doesn't depend on
equipment.json values. Range bracket modifiers are the existing
weapon_selection constants (Short 0 / Medium +2 / Long +4).
"""

import os
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__weapon_selection as ws  # noqa: E402


class FakeWeapon:
    def __init__(self, name, weapon_range):
        self.name = name
        self.weapon_range = weapon_range


LRM = FakeWeapon("LRM-like", {"min": 6, "short": 7, "medium": 14, "long": 21})
PPC = FakeWeapon("PPC-like", {"min": 3, "short": 6, "medium": 12, "long": 18})
LASER = FakeWeapon("laser, min 0", {"min": 0, "short": 3, "medium": 6, "long": 9})
NO_MIN = FakeWeapon("no min listed", {"short": 3, "medium": 6, "long": 9})
NO_DATA = FakeWeapon("no range data", None)

CASES = [
    # weapon, distance, expected modifier (None = can't fire)
    (LRM, 1, 6),     # short 0 + (6-1+1)
    (LRM, 4, 3),     # short 0 + (6-4+1)
    (LRM, 6, 1),     # at minimum range: still +1
    (LRM, 7, 0),     # just outside minimum, short bracket
    (LRM, 14, 2),    # medium
    (LRM, 21, 4),    # long
    (LRM, 22, None), # beyond long
    (PPC, 2, 2),     # short 0 + (3-2+1)
    (PPC, 3, 1),
    (PPC, 4, 0),
    (LASER, 1, 0),
    (LASER, 9, 4),
    (NO_MIN, 1, 0),  # missing min = 0
    (NO_MIN, 7, 4),
    (NO_DATA, 3, None),
]


def run_all():
    failed = 0
    for weapon, distance, expected in CASES:
        try:
            got = ws._weapon_range_mod(weapon, distance)
            assert got == expected, f"expected {expected}, got {got}"
            print(f"PASS  {weapon.name:15} range {distance:2}: {got}")
        except Exception:
            failed += 1
            print(f"FAIL  {weapon.name:15} range {distance:2}")
            traceback.print_exc()
    print()
    print(f"All {len(CASES)} range checks passed." if not failed else f"{failed} of {len(CASES)} range checks FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
