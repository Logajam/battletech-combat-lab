"""
INTEGRATION__config.py

THE single config/entry-point for the integration project. Consolidates
MECHSIM__config.py and PATHFINDER__config.py (2026-08-28, Daniel) - both
retired to reference-only in their own standalone projects; this file
carries forward every setting/data table integration code still needs,
plus labeled-but-unwired slots for gaps not yet built. Old dropped fields
(ATTACK_TABLE, per-team weapons/HP/movement placeholders, MOVER_FIRST_TEAM)
are noted inline as superseded, not silently omitted.

DEPLOYMENT NOTE (Claude can't verify this - no access to Daniel's real
project folder): MECHSIM__damage_resolution.py, hit_location.py,
piloting_rolls.py, and mtf_parser.py all do `import config` and expect
this module's roll_2d6()/CLUSTER_HITS_TABLE/etc. at call time. This file
must resolve as `config` for those imports - same requirement the old
MECHSIM__config.py satisfied, now shifted onto this file.

2026-10-18 (Claude, first end-to-end pass - see PROJECT_MAP Section 8):
  - Added MECH_RED_MTF / MECH_BLUE_MTF: when set, load_two_mechs() parses
    these paths directly instead of opening the tkinter picker (headless
    batch runs). Leave None to get the old picker behaviour.
  - Added PILOTING: piloting_rolls.py reads a single global
    config.PILOTING. The orchestrator temporarily sets it to the acting
    mech's own piloting skill around every piloting_rolls call
    (orchestrator._with_piloting) - this value is only the resting default.
  - DEFAULT_BOARD_PATH / mech paths now resolve relative to this file's
    folder (DATA_DIR), not the current working directory.
  - Added SEED and the STUB SETTINGS block (every tunable value for every
    placeholder in INTEGRATION__stubs.py lives here).
"""

import os
import random
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))

MECHSIM_DIR = os.environ.get(
    "MECHSIM_DIR",
    os.path.join(_HERE, "mechsim"),
)
if MECHSIM_DIR not in sys.path:
    sys.path.insert(0, MECHSIM_DIR)

# Folder holding .mtf/.board inputs (2026-10-18). Relative paths below
# resolve against this.
DATA_DIR = os.environ.get("INTEGRATION_DATA_DIR", os.path.join(_HERE, "data"))

# =============================================================================
# ==========================  GLOBAL SETTINGS  ===============================
# =============================================================================
VERBOSE = True
MANUAL_ROLLS = False     # debugging aid - prompts for each roll instead of
                          # rolling randomly. Only sane with NUM_SIMULATIONS=1.
USE_TMM = True            # Target Movement Modifier - adds compute_tmm(target)
                          # to the to-hit threshold before rolling.
                          # NOTE 2026-10-18: not read by the integration path -
                          # TMM always comes from actual hexes moved
                          # (combat.fc_to_tmm), per Daniel 2026-10-18.
NUM_SIMULATIONS = 1       # Monte Carlo batch size.
MAX_TURNS = 500           # hard cap on turns per simulated battle.
SEED = 12345              # BattleRNG seed for a reproducible batch. None = fresh entropy.

if MANUAL_ROLLS:
    VERBOSE = True  # MANUAL_ROLLS is only useful if Daniel can see what's happening

# Resting default only - see module docstring (2026-10-18). The real value
# per roll is each mech's own MECH_*_CONFIG["piloting"].
PILOTING = 5

# =============================================================================
# ==========================  PER-MECH CONFIG  ===============================
# =============================================================================
# hex/facing/gunnery/piloting/min_heat/max_heat - the scenario inputs that
# used to live on PATHFINDER's TEAM_RED/TEAM_BLUE dicts. Attached to each
# cloned mech by orchestrator._attach_mech_config(); gunnery feeds to-hit,
# piloting feeds every PSR via orchestrator._with_piloting(), min/max_heat
# feed weapon_selection.select_weapons_to_fire().
#
# max_heat (Daniel, 2026-10-18): ceiling on the mech's heat LEVEL at the end
# of the turn, after dissipation. Weapon heat budget each turn =
#   max_heat + dissipation - current heat - this turn's movement heat.
# e.g. max_heat 8 from cold: fire until 8 more heat than the sinks can shed.
# min_heat: Phase 2 pads weapon heat generated this turn up to this value.
#
# hex/facing are the STARTING position - see stubs.stub_deployment() (Section
# 2's edge-entry rule isn't built; these fixed hexes stand in for it).
#
# DROPPED vs the old TEAM_RED/TEAM_BLUE shape (superseded, not carried
# forward): "weapons" list (real weapons now come from
# MECHSIM__equipment.get_weapons() on the parsed mech), "walking_mp"/
# "running_mp"/"jumping_mp" (computed live from mech_state, not static),
# "max_hp"/"current_hp" (tracked on the BattleMech instance itself).
MECH_RED_CONFIG = {
    "hex": "0505",
    "facing": "S",
    "gunnery": 4,
    "piloting": 5,
    "min_heat": 0,
    "max_heat": 4,
}
MECH_BLUE_CONFIG = {
    "hex": "1316",
    "facing": "N",
    "gunnery": 4,
    "piloting": 5,
    "min_heat": 0,
    "max_heat": 4,
}

# .mtf files for a headless run (2026-10-18). None = open the tkinter picker.
MECH_RED_MTF = "Asymptote II iJ Mpulse.mtf"
MECH_BLUE_MTF = "Asymptote II iJ Mpulse.mtf"

# =============================================================================
# ==========================  EQUIPMENT SETTINGS (2026-10-19)  ===============
# =============================================================================
# Player choices for heat/movement equipment (Daniel, 2026-10-19: "for the
# moment we'll assume default on"). Rules are in INTEGRATION__equipment_systems
# and INTEGRATION__heat; these are the bot's settings.
#
# Stealth systems (Chameleon LPS, Null-/Void-Signature, stealth armor): always
# active. Coolant pods: one triggered in any Heat Phase where heat would still
# be above min_heat after normal dissipation (not on a radical heat sink turn).
#
# Radical heat sinks, MASC, supercharger: Escalating Failure systems, used on a
# 1-turn-on / 1-turn-off cycle (Daniel). True = "on" turns are the odd turns
# (1, 3, 5...); False = even turns.
ESCALATING_CYCLE_ON_ODD_TURNS = True
# Triple-strength myomer is driven by min_heat (Daniel): a TSM mech's min_heat
# is raised to at least this (TSM works at 9+ heat), and its max_heat to at
# least its min_heat.
TSM_MIN_HEAT = 9
# Aimed shots at immobile targets (shut down / crew unconscious, Core p.70):
# the location every eligible weapon aims at, or None for no aimed shots.
# "Head" uses +3 instead of the -4 immobile modifier.
AIMED_SHOT_LOCATION = "Center Torso"

# =============================================================================
# ==========================  MAP LOADING  ===================================
# =============================================================================
# Ported from PATHFINDER__config.py. orchestrator._load_map() uses
# DEFAULT_BOARD_PATH (single board). PROMPT_FOR_MAP's picker is still not
# built - ignored for now. STITCH_MAPS=True raises NotImplementedError.
PROMPT_FOR_MAP = False
DEFAULT_BOARD_PATH = "16x17_Grassland_1.board"
STITCH_MAPS = False
EXPECTED_MAP_COUNT = 6
STITCH_GRID_COLS = 2
STITCH_GRID_ROWS = 3

# =============================================================================
# ==========================  STUB SETTINGS (2026-10-18)  ====================
# =============================================================================
# Every placeholder in INTEGRATION__stubs.py reads its knobs from here. Each
# stub prints "STUB: <name> - ..." to stderr every time it runs and is
# counted into the battle's active_stubs report. None of these are BT rules -
# they are stand-ins until the real rule/decision exists. Defaults confirmed
# by Daniel 2026-10-18 ("go for it").
#
# Movement selection - how a mover picks one spot from the real reachable-
# and-LOS candidate list (INTEGRATION__ranged_combat.evaluate_going_second):
#   "max_dealt"                - highest expected damage dealt; ties go to the
#                                spot closest to the enemy, then lowest expected
#                                damage received, then a seeded random pick.
#   "max_dealt_minus_received" - highest (dealt - received), same tie-breaks.
#   "random"                   - uniform random candidate.
STUB_MOVEMENT_POLICY = "max_dealt"
# When NO reachable spot has LOS to the enemy:
#   "closest_to_enemy" - reachable spot nearest the enemy (keeps battles closing)
#   "stay"             - don't move
#   "random_reachable" - any reachable spot
STUB_NO_LOS_FALLBACK = "closest_to_enemy"
# (STUB_WALK_PSR_AS removed 2026-10-19: walking never forces a PSR - Core p.111.)
# (STUB_POST_STANDUP removed 2026-10-19: a mech that stands moves on with its
# remaining MP, any facing - Core p.51, orchestrator._phase_movement.)
# (STUB_HIT_TABLE_SIDE removed 2026-10-19: attack direction now comes from
# geometry - INTEGRATION__attack_resolution.attack_side, Core p.73.)
# (STUB_CLUSTER_GROUPING removed 2026-10-19: cluster damage groupings come
# from the Core rules - INTEGRATION__weapon_rules, SRM 2 / LRM, MRM 5 / ATM 6.)
# Damage type used when equipment.json has damage_type null (only matters for
# special armor types in armor_rules): "BALLISTIC" / "ENERGY" / "MISSILE"
STUB_UNKNOWN_DAMAGE_TYPE = "BALLISTIC"
# (STUB_REAR_MOUNTED removed 2026-10-19: mtf_parser keeps the "(R)" tag as
# Equipment.rear_mounted; those weapons fire only into the rear arc - Core p.60.)
# (STUB_HEAT_MODE removed 2026-10-18: heat now always carries over turn to
# turn - Daniel. See orchestrator._phase_heat.)

# =============================================================================
# ==========================  VISUALIZATION (NOT WIRED)  =====================
# =============================================================================
# Ported from PATHFINDER__config.py / MECHSIM__config.py. Not called from
# anywhere yet - useful for a single debug game, not a real Monte Carlo batch.
RENDER_TURN_STATIC = True
RENDER_TURN_GIF = True
RENDER_MOVEMENT_HEATMAP = True
HEATMAP_TEAM = "Red"
HEATMAP_TURN = 0
GENERATE_LETHALITY_GRAPH = True
LETHALITY_GRAPH_FIXED_DIMENSIONS = None
SAVE_RUN_STATS = True

# =============================================================================
# ==========================  RNG / DICE  =====================================
# =============================================================================
# COMPLEXITY FLAG: roll_2d6()'s bulk-numpy-cache + MANUAL_ROLLS + set_active_rng
# fallback chain has real reasoning behind it (perf history, seeding gotchas) -
# trimmed to essentials here per the 2-sentence rule; flagging that the full
# history lives in MECHSIM__config.py's old HELP tags if it's ever needed.
CLUSTER_HITS_TABLE_COLUMNS = tuple(range(1, 31)) + (40,)
_CLUSTER_TABLE_ROWS = {
    2:  (1, 1, 1, 1, 1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 7, 7, 7, 8, 8, 9, 9, 9, 10, 10, 12),
    3:  (1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 7, 7, 7, 8, 8, 9, 9, 9, 10, 10, 12),
    4:  (1, 1, 1, 2, 2, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 9, 10, 10, 10, 11, 11, 11, 12, 12, 18),
    5:  (1, 1, 2, 2, 3, 3, 4, 4, 5, 6, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 13, 14, 15, 16, 16, 17, 17, 17, 18, 18, 24),
    6:  (1, 1, 2, 2, 3, 4, 4, 5, 5, 6, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 13, 14, 15, 16, 16, 17, 17, 17, 18, 18, 24),
    7:  (1, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 13, 14, 15, 16, 16, 17, 17, 17, 18, 18, 24),
    8:  (1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 13, 14, 15, 16, 16, 17, 17, 17, 18, 18, 24),
    9:  (1, 2, 2, 3, 4, 5, 6, 6, 7, 8, 9, 10, 11, 11, 12, 13, 14, 14, 15, 16, 17, 18, 19, 20, 21, 21, 22, 23, 23, 24, 32),
    10: (1, 2, 3, 3, 4, 5, 6, 6, 7, 8, 9, 10, 11, 11, 12, 13, 14, 14, 15, 16, 17, 18, 19, 20, 21, 21, 22, 23, 23, 24, 32),
    11: (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 40),
    12: (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 40),
}
CLUSTER_HITS_TABLE = {
    roll: dict(zip(CLUSTER_HITS_TABLE_COLUMNS, values))
    for roll, values in _CLUSTER_TABLE_ROWS.items()
}

_ACTIVE_RNG = None  # set by the orchestrator via set_active_rng() for a seeded, reproducible batch


def set_active_rng(battle_rng):
    """Hands this module a shared INTEGRATION__rng.BattleRNG instance so
    roll_2d6()/pick_number() draw from it instead of the bare global
    random/numpy modules. Pass None to revert to unseeded behavior."""
    global _ACTIVE_RNG
    _ACTIVE_RNG = battle_rng


def log(msg=""):
    if VERBOSE:
        print(msg)


def data_path(path):
    """Resolve a config path: absolute paths pass through, relative ones are
    looked up under DATA_DIR (2026-10-18)."""
    if path is None or os.path.isabs(path):
        return path
    return os.path.join(DATA_DIR, path)


_DICE_CACHE_CHUNK = 10000
_dice_cache = None
_dice_cache_idx = 0


def _next_2d6():
    """Pulls the next 2d6 sum off the bulk-generated cache (refilling
    _DICE_CACHE_CHUNK at a time), or from _ACTIVE_RNG if set."""
    global _dice_cache, _dice_cache_idx
    if _ACTIVE_RNG is not None:
        return _ACTIVE_RNG.roll_2d6()
    if _dice_cache is None or _dice_cache_idx >= len(_dice_cache):
        _dice_cache = (
            np.random.randint(1, 7, size=_DICE_CACHE_CHUNK)
            + np.random.randint(1, 7, size=_DICE_CACHE_CHUNK)
        ).tolist()
        _dice_cache_idx = 0
    val = _dice_cache[_dice_cache_idx]
    _dice_cache_idx += 1
    return val


def roll_2d6(prompt="Enter 2d6 roll"):
    """Returns a 2d6 sum (2-12) - random unless MANUAL_ROLLS is True, in
    which case it prompts (blank/invalid input falls back to random)."""
    if not MANUAL_ROLLS:
        return _next_2d6()
    raw = input(f"{prompt} (2-12), blank for random: ").strip()
    if raw == "":
        return _next_2d6()
    try:
        val = int(raw)
    except ValueError:
        print("Not a number - rolling randomly instead.")
        return _next_2d6()
    if not (2 <= val <= 12):
        print("Out of range (2-12) - rolling randomly instead.")
        return _next_2d6()
    return val


def pick_number(n, prompt="Pick a number"):
    """Manual-picking counterpart to roll_2d6() - random 1..n unless
    MANUAL_ROLLS is True (same blank/invalid fallback behavior)."""
    def _auto_pick():
        return _ACTIVE_RNG.pick_number(n) if _ACTIVE_RNG is not None else random.randint(1, n)

    if not MANUAL_ROLLS:
        return _auto_pick()
    raw = input(f"{prompt} (1-{n}), blank for random: ").strip()
    if raw == "":
        return _auto_pick()
    try:
        val = int(raw)
    except ValueError:
        print("Not a number - picking randomly instead.")
        return _auto_pick()
    if not (1 <= val <= n):
        print(f"Out of range (1-{n}) - picking randomly instead.")
        return _auto_pick()
    return val


# =============================================================================
# ==========================  MECH LOADING (WIRED)  ==========================
# =============================================================================
# COMPLEXITY FLAG: the self-registration line below and the import order
# that follows it prevent a circular-import failure (mtf_parser -> config ->
# ... -> mtf_parser). Reasoning is nontrivial - see INTEGRATION__PROJECT_MAP.md
# Known Issue #4/#6 rather than re-explaining it here.
sys.modules['config'] = sys.modules[__name__]
from INTEGRATION__file_picker import pick_files, MTF_FILETYPES  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402 - MECHSIM


def _pick_one_mtf(purpose: str, title: str) -> str:
    """Thin wrapper around file_picker.pick_files() for the single-file
    case, keyed by PURPOSE so Red's and Blue's dialogs remember separate
    last-used directories."""
    paths = pick_files(purpose, title, MTF_FILETYPES, count=1)
    return paths[0]


def _resolve_mtf(configured_path, purpose, title):
    """MECH_*_MTF if set (headless), otherwise the tkinter picker."""
    if configured_path:
        return data_path(configured_path)
    return _pick_one_mtf(purpose, title)


def load_two_mechs():
    """Parses Mech Red's and Mech Blue's .mtf files into independent
    BattleMech instances via parse_mtf(). Uses MECH_RED_MTF/MECH_BLUE_MTF
    when set, otherwise prompts with the file picker. Returns
    (mech_red, mech_blue, red_path, blue_path)."""
    print("=" * 60)
    print("MECH SELECTION")
    print("=" * 60)

    print("\n-- Mech RED --")
    red_path = _resolve_mtf(MECH_RED_MTF, "mech_red_mtf", "Select Mech Red's .mtf file")
    mech_red = parse_mtf(red_path)
    print(f"  Loaded: {mech_red.chassis} {mech_red.model}  ({red_path})")

    print("\n-- Mech BLUE --")
    blue_path = _resolve_mtf(MECH_BLUE_MTF, "mech_blue_mtf", "Select Mech Blue's .mtf file")
    mech_blue = parse_mtf(blue_path)
    print(f"  Loaded: {mech_blue.chassis} {mech_blue.model}  ({blue_path})")

    print("=" * 60)
    return mech_red, mech_blue, red_path, blue_path


# =============================================================================
# ==========================  ENTRY POINT  ====================================
# =============================================================================
def run():
    """Superseded 2026-10-18: the real entry point is
    INTEGRATION__orchestrator.run_batch() (INTEGRATION__main.py calls it).
    Kept so `python INTEGRATION__config.py` still does something useful:
    loads both mechs and stops."""
    mech_red, mech_blue, _, _ = load_two_mechs()
    print(f"\nmech_red  = {mech_red.chassis} {mech_red.model}")
    print(f"mech_blue = {mech_blue.chassis} {mech_blue.model}")
    print("For a full battle run: python INTEGRATION__main.py")
    return mech_red, mech_blue


if __name__ == "__main__":
    run()
