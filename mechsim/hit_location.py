"""
Facing / hit-location resolution.

Real Total Warfare tables for front/rear (shared table, differ only in which
armor pool depletes - see damage_resolution.apply_damage) and left/right side
(their own tables, still deplete FRONT armor - only the true rear arc uses
rear armor).
"""

import random
import config

# ---- Hit location tables (Total Warfare - "Left Side / Front-Rear / Right Side") ----
HIT_TABLE_FRONT_REAR = {2: "Center Torso", 3: "Right Arm", 4: "Right Arm", 5: "Right Leg",
             6: "Right Torso", 7: "Center Torso", 8: "Left Torso",
             9: "Left Leg", 10: "Left Arm", 11: "Left Arm", 12: "Head"}

HIT_TABLE_LEFT_SIDE = {2: "Left Torso", 3: "Left Leg", 4: "Left Arm", 5: "Left Arm",
             6: "Left Leg", 7: "Left Torso", 8: "Center Torso", 9: "Right Torso",
             10: "Right Arm", 11: "Right Leg", 12: "Head"}

HIT_TABLE_RIGHT_SIDE = {2: "Right Torso", 3: "Right Leg", 4: "Right Arm", 5: "Right Arm",
             6: "Right Leg", 7: "Right Torso", 8: "Center Torso", 9: "Left Torso",
             10: "Left Arm", 11: "Left Leg", 12: "Head"}

# Tripod leg sub-roll. Base (front/rear, no modifier) is 1d6 straight.
# Right-side facing: Daniel-specified -1 modifier (roll-1, range 0-5).
# Left-side facing: this project's mirrored extrapolation, +1 modifier (roll+1, range
# 2-7) - NOT independently confirmed, see main.py's DELIBERATE SIMPLIFICATIONS notes.
# HELP(tripod_subroll.asymmetric_modifiers)
TRIPOD_LEG_SUBROLL_FRONT = {1: "Right Leg", 2: "Right Leg", 3: "Center Leg",
                             4: "Center Leg", 5: "Left Leg", 6: "Left Leg"}
TRIPOD_LEG_SUBROLL_RIGHT = {0: "Right Leg", 1: "Right Leg", 2: "Right Leg",
                             3: "Center Leg", 4: "Center Leg", 5: "Left Leg"}
TRIPOD_LEG_SUBROLL_LEFT = {2: "Right Leg", 3: "Center Leg", 4: "Center Leg",
                            5: "Left Leg", 6: "Left Leg", 7: "Left Leg"}

# Random facing weighted 3:1:1:1 (front/left/right/rear) to match a mech having 6 real
# hex facings, 3 of which are all "front" and mechanically identical for hit purposes.
FACING_CHOICES = ("front", "front", "front", "left", "right", "rear")


def resolve_hit_location(loc_roll, mech, facing):
    if facing == "left":
        table = HIT_TABLE_LEFT_SIDE
    elif facing == "right":
        table = HIT_TABLE_RIGHT_SIDE
    else:  # front or rear share the same distribution table
        table = HIT_TABLE_FRONT_REAR

    loc = table.get(loc_roll, "Center Torso")
    if mech.mech_type == "tripod" and loc in ("Left Leg", "Right Leg"):
        base_roll = random.randint(1, 6)
        if facing == "right":
            sub_roll = base_roll - 1
            loc = TRIPOD_LEG_SUBROLL_RIGHT[sub_roll]
        elif facing == "left":
            sub_roll = base_roll + 1
            loc = TRIPOD_LEG_SUBROLL_LEFT[sub_roll]
        else:
            sub_roll = base_roll
            loc = TRIPOD_LEG_SUBROLL_FRONT[sub_roll]
        config.log(f"  Tripod leg sub-roll ({facing}): base {base_roll} -> {sub_roll} -> {loc}")
    elif mech.mech_type in ("quad", "quadvee") and loc in ("Left Arm", "Right Arm", "Left Leg", "Right Leg"):
        # Quad: the hit-location tables above are deliberately left as-is - they're
        # written in biped shorthand ("Left Arm"/"Right Arm" for the front pair,
        # "Left Leg"/"Right Leg" for the rear pair) and just mean "whichever limb
        # sits in that table slot." A Quad's real location names are Front Left/
        # Right Leg and Rear Left/Right Leg respectively - translate AFTER the roll
        # rather than duplicating the whole table.
        # HELP(quad_translate.biped_shorthand)
        QUAD_TRANSLATE = {
            "Left Arm": "Front Left Leg", "Right Arm": "Front Right Leg",
            "Left Leg": "Rear Left Leg", "Right Leg": "Rear Right Leg",
        }
        loc = QUAD_TRANSLATE[loc]
    return loc
