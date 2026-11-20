"""
INTEGRATION__structure_table.py - the internal structure table for the Combat Lab art (tokens, shells).

Copied 2026-11-20 from the retired Python engine's mechsim/mech_state.py (the same numbers the Rust engine uses,
engine/core/src/mech_state.rs) when the Python engine was removed: the art code only needs this one table.
Core Rulebook p.48 Internal Structure Table (superheavy head: MegaMek).
"""

STRUCTURE_TABLE = {
    10: {"CT": 4, "ST": 3, "Arm": 1, "Leg": 2}, 15: {"CT": 5, "ST": 4, "Arm": 2, "Leg": 3},
    20: {"CT": 6, "ST": 5, "Arm": 3, "Leg": 4}, 25: {"CT": 8, "ST": 6, "Arm": 4, "Leg": 6},
    30: {"CT": 10, "ST": 7, "Arm": 5, "Leg": 7}, 35: {"CT": 11, "ST": 8, "Arm": 6, "Leg": 8},
    40: {"CT": 12, "ST": 10, "Arm": 6, "Leg": 10}, 45: {"CT": 14, "ST": 11, "Arm": 7, "Leg": 11},
    50: {"CT": 16, "ST": 12, "Arm": 8, "Leg": 12}, 55: {"CT": 18, "ST": 13, "Arm": 9, "Leg": 13},
    60: {"CT": 20, "ST": 14, "Arm": 10, "Leg": 14}, 65: {"CT": 21, "ST": 15, "Arm": 10, "Leg": 15},
    70: {"CT": 22, "ST": 15, "Arm": 11, "Leg": 15}, 75: {"CT": 23, "ST": 16, "Arm": 12, "Leg": 16},
    80: {"CT": 25, "ST": 17, "Arm": 13, "Leg": 17}, 85: {"CT": 27, "ST": 18, "Arm": 14, "Leg": 18},
    90: {"CT": 29, "ST": 19, "Arm": 15, "Leg": 19}, 95: {"CT": 30, "ST": 20, "Arm": 16, "Leg": 20},
    100: {"CT": 31, "ST": 21, "Arm": 17, "Leg": 21},
    105: {"CT": 32, "ST": 22, "Arm": 17, "Leg": 22}, 110: {"CT": 33, "ST": 23, "Arm": 18, "Leg": 23},
    115: {"CT": 35, "ST": 24, "Arm": 19, "Leg": 24}, 120: {"CT": 36, "ST": 25, "Arm": 20, "Leg": 25},
    125: {"CT": 38, "ST": 26, "Arm": 21, "Leg": 26}, 130: {"CT": 39, "ST": 27, "Arm": 21, "Leg": 27},
    135: {"CT": 41, "ST": 28, "Arm": 22, "Leg": 28}, 140: {"CT": 42, "ST": 29, "Arm": 23, "Leg": 29},
    145: {"CT": 44, "ST": 31, "Arm": 24, "Leg": 31}, 150: {"CT": 45, "ST": 32, "Arm": 25, "Leg": 32},
    155: {"CT": 47, "ST": 33, "Arm": 26, "Leg": 33}, 160: {"CT": 48, "ST": 34, "Arm": 26, "Leg": 34},
    165: {"CT": 50, "ST": 35, "Arm": 27, "Leg": 35}, 170: {"CT": 51, "ST": 36, "Arm": 28, "Leg": 36},
    175: {"CT": 53, "ST": 37, "Arm": 29, "Leg": 37}, 180: {"CT": 54, "ST": 38, "Arm": 30, "Leg": 38},
    185: {"CT": 56, "ST": 39, "Arm": 31, "Leg": 39}, 190: {"CT": 57, "ST": 40, "Arm": 31, "Leg": 40},
    195: {"CT": 59, "ST": 41, "Arm": 32, "Leg": 41}, 200: {"CT": 60, "ST": 42, "Arm": 33, "Leg": 42},
}

SUPERHEAVY_MIN_TONS = 105                  # Core p.240: superheavy 'Mechs weigh 105-200 tons
SUPERHEAVY_HEAD = 4                        # MegaMek: a superheavy's head has 4 structure points


def structure_for_tonnage(mass, mech_type="biped"):
    if mass not in STRUCTURE_TABLE:
        raise ValueError(f"No internal structure table entry for {mass} tons "
                          f"(10-200 in 5-ton steps are supported).")
    t = STRUCTURE_TABLE[mass]
    out = {
        "Head": SUPERHEAVY_HEAD if mass >= SUPERHEAVY_MIN_TONS else 3, "Center Torso": t["CT"], "Left Torso": t["ST"], "Right Torso": t["ST"],
        "Left Leg": t["Leg"], "Right Leg": t["Leg"], "Center Leg": t["Leg"],
    }
    if mech_type in ("quad", "quadvee"):
        # Confirmed by Daniel directly: a Quad's front legs use the same "Leg"
        # structure points as its rear legs, NOT the "Arm" column - even though
        # they occupy the arm's crit-slot position in the .mtf file.
        out["Front Left Leg"] = t["Leg"]
        out["Front Right Leg"] = t["Leg"]
        out["Rear Left Leg"] = t["Leg"]
        out["Rear Right Leg"] = t["Leg"]
    else:
        out["Left Arm"] = t["Arm"]
        out["Right Arm"] = t["Arm"]
    return out
