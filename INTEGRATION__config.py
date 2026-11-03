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

import contextlib
import os
import sys


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
                          # Each battle gets its own seed made from this one
                          # (orchestrator.battle_seed): battle 1 uses SEED itself.
# Parallel batches (2026-10-20): how many battles run at once, one per CPU core.
#   0 = one worker per core; 1 = one battle after another (no extra processes).
# The output is identical either way - each battle has its own seed, and the
# parent prints every battle's log in order. MANUAL_ROLLS always runs one at a time.
WORKERS = 0
# Battle replays (2026-10-20, INTEGRATION__replay): battles 1..REPLAY_BATTLES of
# a run are each saved as a self-contained HTML page in REPLAY_DIR (relative =
# under the repo root) - a hex map to step through, both mechs' damage and
# heat, and the log of each step. 0 = none.
REPLAY_BATTLES = 0
REPLAY_DIR = "replays"
# Saved states (2026-11-03, INTEGRATION__saved_state): at the end of the turns
# listed, battles 1..SAVE_STATE_BATTLES of a run each write a file to
# SAVE_STATE_DIR holding everything needed to play on from there - the units,
# the board as it stands, the dice and the bots' memories. Load one with
# `python INTEGRATION__saved_state.py <file>` to play the rest of the battle.
#   SAVE_STATE_TURNS: () = none; (3, 5) = after turns 3 and 5; "all" = every turn.
SAVE_STATE_TURNS = ()
SAVE_STATE_BATTLES = 1
SAVE_STATE_DIR = "saved_states"
# Test switch (tests/check_reference_logs.py --round-trip): after EVERY turn the
# battle is saved, reloaded from the saved text, and played on from the reloaded
# copy. The log must match a battle that never stopped, byte for byte.
SAVE_STATE_ROUND_TRIP = False
# Compiled hot loops (2026-11-03, trial): use the Rust module `fastcore` (built from
# fastcore/ with maturin) where it is installed. Speed only - the same answers as
# the Python; False (or not installed) = pure Python.
USE_FASTCORE = True
# Where the time goes (2026-10-21, INTEGRATION__timing): TIMING prints a table of
# the time spent in each part of the turn after every batch (it only reads the
# clock - results don't change). PROFILE_FUNCTIONS = N also lists the N
# functions with the most time of their own (cProfile; about 2x slower). 0 = off.
TIMING = True
PROFILE_FUNCTIONS = 0

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
# hex/facing are the STARTING position only with DEPLOYMENT = "fixed_hexes"
# (see DEPLOYMENT below).
#
# DROPPED vs the old TEAM_RED/TEAM_BLUE shape (superseded, not carried
# forward): "weapons" list (real weapons now come from
# MECHSIM__equipment.get_weapons() on the parsed mech), "walking_mp"/
# "running_mp"/"jumping_mp" (computed live from mech_state, not static),
# "max_hp"/"current_hp" (tracked on the BattleMech instance itself).
# "bot" (optional, 2026-10-27, INTEGRATION__bots): which bot decides for this
# unit - None = BOT below.
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

# Which bot drives a unit when its MECH_*_CONFIG has no "bot" key (Daniel,
# 2026-10-27, INTEGRATION__bots):
#   "gladiator" - this project's bot (movement_selection, weapon_selection, ...)
#   "princess"  - a clone of MegaMek's Princess bot (v0.50.07: its path ranker,
#                 fire control and physical choice - INTEGRATION__princess,
#                 INTEGRATION__princess_fire; PROJECT_MAP Section 6, "Princess clone")
BOT = "gladiator"
# Princess's behavior sliders (MegaMek BehaviorSettings, each 0-10); 5 is
# MegaMek's "DEFAULT" behavior. Values: fall shame 10/40/80/100/160/500..500,
# bravery 0.1-3.0 in steps of 0.3, hyper-aggression 0.25/0.5/1/1.5/2/2.5/3/3.5/
# 10/50/500, self-preservation 2.5-25 in steps of 2.5, then 30.
# Which Princess (2026-10-27, Daniel: "Clone the entire modern suit for Princess"):
#   "modern"  - MegaMek main as of commit fd2edfb (2026-10-26): postures, the close-
#               range pull, position holding, physical threat weights, movement-heat
#               and TSM-aware fire control (INTEGRATION__princess_modern)
#   "0.50.07" - the classic ranker first cloned (INTEGRATION__princess)
PRINCESS_VERSION = "modern"
PRINCESS_BEHAVIOR = {
    "fall_shame": 5,
    "bravery": 5,
    "hyper_aggression": 5,
    "self_preservation": 5,
    # The group sliders (2026-10-28, INTEGRATION__princess_group; BehaviorSettings defaults):
    "mutual_support": 5,        # 0-10 -> 0.1 ... 2.0 (default 5 = 1.0): the pull toward the force's hot spot /
                                # the friends' centre, per hex of distance (BasicPathRanker.calculateMutualSupportMod)
    "anti_crowding": 0,         # 0-10 (default 0 = off): a penalty for ending among friends and enemies
    "facing_enemies": 4,        # 1-12: how many of the closest enemies the unit turns to face (their median)
}
# The group behaviors on or off (2026-10-28, Daniel: Princess's mutual support, crowding, ...). Off gives the
# duel-only Princess the earlier recorded runs were made with (still weighing every enemy and the force's
# posture, but with no pull toward its friends or its own earlier ground).
PRINCESS_GROUP = True

# Legate (2026-10-28, Daniel): the multi-unit layer that runs at the start of each Movement Phase so a
# Gladiator-driven unit is not blind to the other enemies (INTEGRATION__legate). False = every Gladiator
# plans against its nearest foe alone, as before. Duels are unchanged either way (one enemy).
# ON by default since 2026-10-29 (Daniel: "Legate on by default in multi unit games." - with the
# Gladiator target stub it took Gladiator from 0 to 4 wins in 20 12 v 12 battles, Change Record).
LEGATE = True
# Legate's IF/THEN search: how many rounds (each round every enemy unit answers, then every unit of the
# asking side answers). A unit that picks a hex it already tried is locked at its best attempt.
LEGATE_ITERATIONS = 12
# How much of an enemy's future fire a Gladiator expects to draw in its life-left estimate
# (INTEGRATION__legate.fire_share, 2026-10-29): "proportional" (its slice of what that enemy could deal
# across the team) or "none" (all of it - the first version, which made lights dive in alone).
LEGATE_FIRE_SPLIT = "proportional"  # with LEGATE_SPLIT_THIS_TURN: best in the 2026-10-30 A/B (Change Record);
                                    # alone it stalled battles (2026-10-29)
# The same share for THIS turn's damage (2026-10-30): without it the split makes HP worth more while this
# turn's damage still counts every enemy as shooting the mover (session 15 probe: 3.4 enemies counted,
# 0.63 really fired) - a mismatch. Only has an effect with LEGATE_FIRE_SPLIT "proportional".
LEGATE_SPLIT_THIS_TURN = True       # default since 2026-10-30 (8 / 4 / 8 v the old 8 / 8 / 4)
# Herding (INTEGRATION__legate._Herd, 2026-10-29, Daniel's shape): a spot an enemy can reach costs
# LEGATE_HERD_WEIGHT damage for each hex it lies beyond the support of every teammate that can see one
# of those enemies (support: the end of the teammate's medium bracket, long if it stands still);
# no teammate sees one: LEGATE_HERD_UNSEEN_GAP hexes. Placeholder weights; off by default (A/B 2026-10-29).
# Cohesion (INTEGRATION__legate._Cohesion, 2026-10-30, Daniel: "Reward staying within a range braket of
# its allies, stronger at short, much weaker at long. And how many allies are in mutual support range."):
# for each teammate (where it will end), a spot inside its short / medium / long bracket (its best weapon
# for each) earns LEGATE_COHESION_REWARD[bracket], and one in mutual support range (within both units'
# support_range: medium, long when standing still) LEGATE_COHESION_MUTUAL more; damage points, taken off
# the damage the spot is expected to take; all times LEGATE_COHESION_SCALE. Placeholder weights.
LEGATE_COHESION = False
LEGATE_COHESION_REWARD = {"short": 2.0, "medium": 1.0, "long": 0.25}
LEGATE_COHESION_MUTUAL = 1.0
LEGATE_COHESION_SCALE = 1.0
# Refinements (2026-10-30, after the first cohesion A/B balled the force up): only the
# LEGATE_COHESION_MAX_ALLIES best-rewarding teammates count (None = all), and with
# LEGATE_COHESION_THREATENED_ONLY a spot no enemy (at its estimated spot) can reach needs no support and
# counts as fully supported.
LEGATE_COHESION_MAX_ALLIES = None
LEGATE_COHESION_THREATENED_ONLY = False
# Whose brackets pair two units (2026-10-30, Daniel: "A fire support unit in the back will feel like its
# out of position because its not in cohesion with a short ranged back stabber up front. The back stabber
# however will feel fine since it has covering fire."): "ally" - the teammate's brackets (does it cover me)
# and mutual support inside BOTH support ranges (the shorter pulls everyone in); "either" - the better
# covering of the two (whichever unit covers the other) and support inside EITHER support range.
LEGATE_COHESION_PAIRING = "ally"
LEGATE_HERDING = False             # 2 a hex changed half the battles but not the results (A/B 2026-10-29)
LEGATE_HERD_WEIGHT = 2.0
LEGATE_HERD_UNSEEN_GAP = 6
# The team's future damage in a Gladiator's move score (INTEGRATION__legate._TeamFire, 2026-10-29, Daniel:
# "aware of the expected distribution of enemy fire ... how that distribution changed across its entire
# force, and the expected loss of future damage"): the enemy's fire this turn is distributed over the whole
# team with the mover at the spot being scored, and the score is dealt + the team's future damage -
# "sum" (each unit's life-left term, times its chance of living through the turn) or "product" (Daniel's
# SUM(future damage) x SUM(future vulnerability), over the team's size); None = off (the mover's own term).
LEGATE_TEAM_VALUE = None
LEGATE_TEAM_FIRE_MODEL = "greedy"   # whom each enemy shoots: its most-hurt target not already doomed
# The exchange (2026-10-29, Daniel: "a valid tactic is to saturate them with targets while swarming them
# down ... 'some of us may die, but that's a sacrifice I'm willing to make'"): with a team value, also count
# the enemy's future damage our team's fire takes off the board this turn (our fire distributed by the same
# rule, each enemy's kill curve), times LEGATE_TEAM_EXCHANGE_WEIGHT - so a move is worth our team's future
# damage plus the enemy's we remove.
LEGATE_TEAM_EXCHANGE = True
LEGATE_TEAM_EXCHANGE_WEIGHT = 1.0

# Deployment (2026-10-19, Core p.37):
#   "home_edge"   - deployment roll; the loser picks a home edge, the winner
#                   gets the opposite one; mechs enter along it on turn 1
#   "fixed_hexes" - start at MECH_*_CONFIG hex/facing (a set scenario)
DEPLOYMENT = "home_edge"
# Which edge the deployment-roll loser picks: "random", or "N"/"E"/"S"/"W".
HOME_EDGE_CHOICE = "random"
# How far in from its home edge a mech may start its movement (Daniel,
# 2026-10-21: "Its value is the number of hexes in from the edge that a mech
# can start its movement"): 0 = the edge hexes only (Core p.37). Read here as
# hexes 0..N in, so 3 = the edge row and the three rows behind it.
DEPLOYMENT_DEPTH = 0
# Daniel's "I can't enter / stuck terrain" override: when no hex within
# DEPLOYMENT_DEPTH lets this mech enter AND still reach the far side of the
# map (by walking or jumping - "stuck" is no path to the other side for this
# unit), it may start this many hexes in instead. INTEGRATION__deployment.
DEPLOYMENT_STUCK_DEPTH = 3

# .mtf files for a headless run (2026-10-18). None = open the tkinter picker.
# Default matchup (Daniel, 2026-10-20): the Kontio vs the Hammerhead, the
# example battle in the game's starter set ("Asymptote is an uninteresting
# match"). The Asymptote II tripod stays in data/ for the tests.
MECH_RED_MTF = "Kontio.mtf"
MECH_BLUE_MTF = "Hammerhead.mtf"

# =============================================================================
# ==========================  MULTI-UNIT BATTLES (2026-10-28)  ===============
# =============================================================================
# Daniel, 2026-10-28: "Multiple units that can be assigned to multiple teams.
# The ideal ranges would probably be a 4 unit lance and a 12 unit company vs
# like forces. But a 20 unit free for all or a 3 way battle between different
# lances are also possibilities that need to be covered by the general
# solution." (INTEGRATION__forces, PROJECT_MAP Section 5.)
#
# FORCES = None  -> the two-'Mech battle above (MECH_RED_* vs MECH_BLUE_*).
# FORCES = [...] -> a list of units, one dict each; MECH_RED_* / MECH_BLUE_*
#                   are then unused. Keys:
#     "team"      the side it fights for (any text; units on different teams
#                 are enemies, a free for all is one team per unit)
#     "mtf"       its .mtf file (resolved under DATA_DIR like MECH_*_MTF)
#     "count"     (optional, default 1) how many of this unit to field
#     "name"      (optional) its label in the logs; default: the team's name
#                 when it has one unit, else "<team> 1", "<team> 2", ...
#     "gunnery", "piloting", "min_heat", "max_heat", "bot", "search",
#     "assumes_enemy_search"   as in MECH_*_CONFIG; any left out come from
#                 FORCE_DEFAULTS
#     "hex", "facing"  where it starts, with DEPLOYMENT = "fixed_hexes" only
# Example, a lance against a lance:
#   FORCES = [{"team": "Red", "mtf": "Atlas AS7-D.mtf", "count": 4},
#             {"team": "Blue", "mtf": "Hammerhead.mtf", "count": 4}]
FORCES = None
FORCE_DEFAULTS = {"facing": "N", "gunnery": 4, "piloting": 5, "min_heat": 0, "max_heat": 4,
                  "bot": None, "search": None, "assumes_enemy_search": None}
# Whom each bot plans its movement against (its "foe"; the other enemies are not
# modeled by the movement scoring - independent bots) and fires at. "nearest":
# the nearest enemy (a fire target must also be in sight). Section 6, 'Target choice'.
FOE_CHOICE = "nearest"
# A 'Mech that passes its domino-effect PSR may step one hex forward or back out of
# the way instead of being pushed on (Core p.114). MegaMek's bots never do
# ("TODO: Bots should figure out how to step out", BotClient) - so neither does
# this one. True: it steps aside whenever a legal hex is open (forward first).
DOMINO_DODGE = False

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
# (1, 3, 5...); False = even turns. (Since 2026-10-20 whether to use them is a
# stub - STUB_ESCALATING_USE below; "cycle" follows this setting.)
ESCALATING_CYCLE_ON_ODD_TURNS = True
# Triple-strength myomer is driven by min_heat (Daniel): a TSM mech's min_heat
# is raised to at least this (TSM works at 9+ heat), and its max_heat to at
# least its min_heat.
TSM_MIN_HEAT = 9
# Anti-Missile Systems (Core p.206, INTEGRATION__ams): an AMS engages the
# incoming missile hits it can, unless that would leave the mech's projected
# end-of-turn heat above max(its max_heat, AMS_HEAT_LIMIT). 13 = the last
# heat level with no shutdown roll (p.104). Matters mostly for laser AMS
# (7 heat IS / 5 Clan per engagement; a standard AMS makes 1).
AMS_HEAT_LIMIT = 13
# Worth of one point of heat put on the enemy (flamers, plasma - pp.102, 189),
# counted as this much damage when the bot prices a heat-causing weapon.
# PLACEHOLDER (Claude 2026-10-20) until Daniel sets it - without it a plasma
# cannon (no damage, 2D6 heat) would never be worth firing.
TARGET_HEAT_WORTH = 0.5
# A BattleMech Taser hit's effect on the target (TO:AUE p.158: shut down 3
# turns on 11+, else +2 to its Piloting / Gunnery and 5 heat a turn for 3
# turns), counted as this much damage when the bot prices a Taser shot.
# PLACEHOLDER (Claude 2026-10-27) until Daniel sets it - without it a Taser
# (1 damage for 6 heat) would never be worth firing.
TASER_EFFECT_WORTH = 5.0
# A TSEMP hit's effect (Interstellar Operations pp.90-91: interference or a
# shutdown through the next turn), counted as this much damage when the bot
# prices a TSEMP shot - and IMP missile effects (+1 to hit, -1 MP, hostile ECM
# through the next turn), this much per +1 level. PLACEHOLDERS (Claude
# 2026-10-28) until Daniel sets them, in the research pile with
# TASER_EFFECT_WORTH and the worth of cluster weapons - without them a TSEMP
# (no damage) would never be worth firing.
TSEMP_EFFECT_WORTH = 5.0
IMP_EFFECT_WORTH = 2.0
# Aimed shots at immobile targets (shut down / crew unconscious, Core p.70):
# the location every eligible weapon aims at, or None for no aimed shots.
# "Head" uses +3 instead of the -4 immobile modifier.
AIMED_SHOT_LOCATION = "Center Torso"

# =============================================================================
# ==========================  MAP LOADING  ===================================
# =============================================================================
# Ported from PATHFINDER__config.py. orchestrator._load_map() loads
# DEFAULT_BOARD_PATH (one board), or - with STITCH_MAPS - the boards named in
# STITCH_BOARDS laid out row-major in a STITCH_GRID_COLS x STITCH_GRID_ROWS
# grid (board_parser.stitch_boards; 2026-10-28, for company-size fights).
# PROMPT_FOR_MAP = True asks a person for the map at the start of a run
# (INTEGRATION__map_picker: one board or a stitched grid, from data/ and the
# data/maps.zip pack; Enter repeats last time's pick) and writes the answer
# into the settings below. Headless runs keep the configured map.
PROMPT_FOR_MAP = False
DEFAULT_BOARD_PATH = "16x17_Grassland_1.board"
STITCH_MAPS = False
# Board files (under DATA_DIR), row-major: left to right, then down. Same-row
# boards must share a height and same-column boards a width; a blank hex row /
# column is inserted at every seam (Daniel, 2026-07-20). Use one name several
# times for a repeated board. Example, a 2 x 1 field of two 16x17 maps:
#   STITCH_MAPS = True; STITCH_GRID_COLS, STITCH_GRID_ROWS = 2, 1
#   STITCH_BOARDS = ["16x17_Grassland_1.board", "16x17_Scattered_Woods.board"]
STITCH_BOARDS = []
STITCH_GRID_COLS = 2
STITCH_GRID_ROWS = 1

# =============================================================================
# ==========================  STUB SETTINGS (2026-10-18)  ====================
# =============================================================================
# Every placeholder in INTEGRATION__stubs.py reads its knobs from here. Each
# stub prints "STUB: <name> - ..." to stderr every time it runs and is
# counted into the battle's active_stubs report. None of these are BT rules -
# they are stand-ins until the real rule/decision exists. Defaults confirmed
# by Daniel 2026-10-18 ("go for it").
#
# (STUB_MOVEMENT_POLICY / STUB_NO_LOS_FALLBACK removed 2026-10-19: movement
# selection is real - INTEGRATION__movement_selection; knobs are in the
# MOVEMENT SETTINGS block below.)
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
# --- Bot decisions still being researched (Daniel, 2026-10-20: "How a bot
# determines what rate to fire at, If it should use MASC, or what kind of ammo
# to use (Apollo goes in this catagory) is still a matter of research"). The
# options are real rules (INTEGRATION__fire_modes, INTEGRATION__electronics,
# INTEGRATION__equipment_systems); these stubs pick one. ---
# Which ammunition kind / guidance / Apollo mode a weapon fires (LB-X slug or
# cluster, ATM standard / ER / HE, MML LRM / SRM, Artemis / Narc-equipped or
# standard missiles, Narc homing or explosive pods):
#   "greedy"   - most expected damage this shot (a homing pod: its worth);
#                ties keep standard ammunition
#   "standard" - standard ammunition / slugs whenever there is some
#   "random"   - a seeded random pick
STUB_MUNITION_POLICY = "greedy"
# How many shots an Ultra (1-2) / Rotary (1-6) autocannon fires:
#   "max" - as many as it can (ammo permitting); "single" - one; "greedy" -
#   most expected damage this shot (a Rotary's jam risk isn't priced)
STUB_RATE_OF_FIRE = "max"
# Try to unjam a jammed Rotary AC (that turn: stand still or walk only).
# True = whenever it's jammed and the mech isn't prone.
STUB_UNJAM = True
# When MASC / a supercharger / a radical heat sink system is used:
#   "cycle"  - Daniel's 1-turn-on / 1-turn-off default (ESCALATING_CYCLE_ON_ODD_TURNS)
#   "always" / "never"
STUB_ESCALATING_USE = "cycle"
# Equipment choices (Daniel, 2026-10-21: wired, the decisions deferred - each is
# a stub in INTEGRATION__stubs).
# Charge with torso spikes declared (p.196): True = always when the mech has them.
STUB_CHARGE_SPIKES = True
# Activate a vibroblade for its attack (p.196): "on" (fixed damage, heat) / "off".
STUB_VIBROBLADE = "on"
# Raise a shield at the start of an attack phase (p.195): "never" / "always".
STUB_RAISE_SHIELD = "never"
# Command console End Phase seat swap (p.203): "when_needed" (pilot out or more hurt) / "never".
STUB_CONSOLE_SWAP = "when_needed"
# Blue Shield particle field damper switched on (p.207): "on" / "off".
STUB_BLUE_SHIELD = "on"
# TAG (p.200): designate the enemy before the Ranged Attack Phase? "when_useful" (the 'Mech has homing
# artillery rounds to use it) / "always" / "never".
STUB_FIRE_TAG = "when_useful"
# TAG aim: "mech" (the enemy - homing rounds hit it in full) / "hex" (the ground it stands on - an easier
# shot, homing rounds then do 5 AE to it) / "easier" (the lower target number).
STUB_TAG_AIM = "mech"
# PPC capacitors (p.188): start the battle charged? "empty" / "charged".
STUB_CAPACITOR_START = "empty"
# Charge a PPC capacitor instead of firing its PPC? "never" / "when_idle" (whenever the PPC isn't fired).
STUB_CAPACITOR_CHARGE = "never"
# Whom a GLADIATOR unit shoots when two or more enemies are on the board (2026-10-29, Daniel: "a good test
# to stub in until we teach gladiator how to focus fire and account for target saturation"):
#   "princess_plan" - Princess's target choice: each enemy scored by Princess's firing-plan utility, with
#                     the damage the unit's teammates already declared this phase counted (an enemy they
#                     are expected to kill scores low - focus fire without overkill). Gladiator still
#                     picks its own weapons at the target, and its declared damage is counted for the
#                     teammates who fire after it.
#   "nearest"       - the old pick (forces.choose_target: in sight, a weapon bears, nearest).
#   "kill_curve"    - NOT a stub: Gladiator's own fire director (2026-10-29, Daniel: "splitting fire to
#                     wreck 2 units is better then hard killing 1 and grazing the other"). Each enemy is
#                     scored by how much this unit's expected damage raises the enemy's chance of a
#                     mission kill (INTEGRATION__kill_curve), on top of what teammates already declared
#                     at it, times the enemy's worth (KILL_CURVE_WEIGHT). Its declaration is counted too.
# Duels are unchanged either way (one enemy).
STUB_GLADIATOR_TARGET = "princess_plan"
# A mission kill for the kill curve (INTEGRATION__kill_curve; 2026-10-29, Daniel: "an immobile, weaponless
# torso with a leg on the ground is still dangerous, if it can spot ... the weight for spotting has not been
# evaluated yet"). An immobile 'Mech is already destroyed under the default rules (FIGHT_TO_THE_DEATH off).
#   "destroyed"         - destroyed only: a 'Mech with no gun that can still move, kick or spot fights on.
#   "no_ranged_weapons" - also once no ranged weapon is left that can fire (spotting worth nothing).
STUB_MISSION_KILL = "destroyed"
# The kill curve (INTEGRATION__kill_curve, 2026-10-29): the chance a 'Mech is mission-killed by N more
# points of damage from its current state, from a small Monte Carlo on the engine's damage code.
KILL_CURVE_GROUP = 5            # damage grouping of the trials (Daniel: "rule of thumb ... 5 point clusters")
KILL_CURVE_TRIALS = 100         # trials a curve (one side of one 'Mech in one damage state; cached)
KILL_CURVE_MAX_DAMAGE = 200     # a trial stops here (more than a turn's fire on one 'Mech)
# What counts as a mission kill ("no longer able to support its teams combat operations", Daniel
# 2026-10-29) is a STUB while spotting has no worth: see STUB_MISSION_KILL below.
# An enemy's worth in the fire director: "output" (its damage a turn, INTEGRATION__future_damage -
# Daniel: "Expected damage output from the target / its vulnerability") or "none" (every kill alike).
KILL_CURVE_WEIGHT = "output"
# Softening in the fire director (2026-10-29): what a share of a kill paid toward later turns is worth
# beside kill chance added this turn (mine / the damage the enemy still needs). 1 = a full kill's worth
# of softening counts as a kill now; near 0, only kills this turn count (a long shot that adds 1% on a
# hurt enemy then beats a full volley into a fresh one).
KILL_CURVE_PROGRESS_WEIGHT = 1.0
# Gladiator's firing order within its side's selections (2026-10-29, Daniel: "Big guns first followed by
# smaller guns. Its the same rule used on a mech, just applied to the entire formation."):
# "big_guns_first" (most expected damage at any enemy now declares first) or "roster" (list order).
GLADIATOR_FIRE_ORDER = "big_guns_first"
# (STUB_REAR_MOUNTED removed 2026-10-19: mtf_parser keeps the "(R)" tag as
# Equipment.rear_mounted; those weapons fire only into the rear arc - Core p.60.)
# (STUB_HEAT_MODE removed 2026-10-18: heat now always carries over turn to
# turn - Daniel. See orchestrator._phase_heat.)

# =============================================================================
# ==========================  MOVEMENT SETTINGS  ==============================
# =============================================================================
# INTEGRATION__movement_selection (Daniel, 2026-10-19). Not BattleTech rules:
# the scoring and search policy for where a mech ends its movement.
#   score = dealt / (received + PSR cost + MOVEMENT_RATIO_EPSILON)
# The first mover scores each spot by the second mover's modeled reply (two-ply).
MOVEMENT_TWO_PLY = True          # False: the first mover scores against the enemy standing still
# Movement search (2026-10-21, Daniel's "guess and follow"; the default since
# 2026-10-21 - Daniel: "I think it should become the default"):
#   "grid"       - a 1-in-7 net of the reachable hexes (the hex grid's own spacing:
#                  every hex is a net hex or touches exactly one; the mover's own hex
#                  is always in it), then from the best MOVEMENT_SEARCH_STARTS net
#                  hexes follow uphill: look at the unchecked neighbours of the best
#                  hex so far, move to the best of them while it improves. A hex
#                  "looked at" scores all its facings and modes. No dice involved.
#                  A second mover (knowing where its enemy stands) also always looks
#                  at the 6 hexes around the enemy (melee).
#   "exhaustive" - every reachable spot ("perfect"; the original).
#   "if_then"    - (Daniel's IF/THEN, 2026-10-28; MOVEMENT_SEARCH only): the first
#                  mover asks "If I hold still then" where would the second mover
#                  reply, takes its best spot against that reply, asks where the
#                  reply to that would be, and so on, back and forth; it stops when an
#                  attempt scores no better (two-ply score) than the one before and
#                  keeps that one before, or picks a spot twice. A second mover
#                  scores every spot, as "exhaustive".
#   "short_list" - (Daniel's "simple short list",
#                  2026-10-24): the first mover looks for the reply only on a rule-of-
#                  thumb list of hexes - next to the first mover, the replier's own
#                  hex, and the hexes at the MOVEMENT_SHORT_LIST_DROPS ranges where
#                  the replier's damage drops most, or one past where the first
#                  mover's does. Each hex is scored once per movement mode at its
#                  best TMM, facing the first mover (its facing isn't searched).
#                  An immobile or prone replier keeps the full model.
#                  As MOVEMENT_SEARCH ("Short-Short", 2026-10-27: "both sides are only
#                  picking from their own short lists"): the mover's own hex and the
#                  hexes at those ranges from the enemy, best few states per hex
#                  (movement_selection.own_short_list), each with the look-ahead
#                  when moving first.
# MOVEMENT_SEARCH: how a mech picks its OWN spot (first mover: which spots get the
# two-ply look-ahead; second mover: its real pick).
# MOVEMENT_ASSUMED_ENEMY_SEARCH: how a first mover ASSUMES the second mover picks its
# reply in the look-ahead.
# Per side (Daniel, 2026-10-21: "See how much of an advantage perfect knowledge is vs
# close enough"): MECH_RED_CONFIG / MECH_BLUE_CONFIG may set "search" and
# "assumes_enemy_search" to override these two for that mech.
MOVEMENT_SEARCH = "grid"
# "short_list" is the default since 2026-10-24 (Daniel: "we push 'Simple Short list' for the
# first movers evaluation"); "grid" was the default before that.
MOVEMENT_ASSUMED_ENEMY_SEARCH = "short_list"
MOVEMENT_SEARCH_STARTS = 1      # "grid": how many of the best net hexes to follow uphill from
# "if_then": 0 = the climb (stop when an attempt scores no better, keep the one before);
# N > 0 = up to N attempts whatever they score, stopping early on a hex it already tried,
# then the best-scoring attempt (Daniel, 2026-10-28: "run like 10 to 15 steps").
MOVEMENT_IF_THEN_STEPS = 0
# "if_then": True = after the back and forth, climb from the best attempt's hex to better
# neighbouring hexes by the two-ply score (Daniel, 2026-10-28: "I like option 2").
# IF/THEN isn't meant as a single 'Mech's default search (Daniel, 2026-10-28): in
# multi-unit games it gives the threat vector of farther units, while stronger
# searches handle the immediate threats.
MOVEMENT_IF_THEN_NEIGHBOUR_CLIMB = True
# "short_list": how many damage-drop ranges per mech go on the list, and the pre-to-hit
# number the rough damage-by-range curve is read at (gunnery 4 + about 2 for movement).
MOVEMENT_SHORT_LIST_DROPS = 2
MOVEMENT_SHORT_LIST_PRE_TN = 6
# Short-Short (own search "short_list", 2026-10-27): True = Daniel's grid search
# ("guess and follow") over the short-list hexes instead of scoring them all
# (Daniel: "if short list hexes tend to be continuous ... a grid search prune on
# them would reduce the total that need to be checked").
MOVEMENT_SHORT_LIST_GRID = False
# "grid": which of the two mirror-image 1-in-7 nets (2026-10-21, Daniel's spin A/B). The
# range-3 net hexes are "2 hexes out, then 1 turning clockwise" or "... counter-clockwise".
MOVEMENT_GRID_SPIN = "clockwise"
MOVEMENT_RATIO_EPSILON = 0.001   # added to the denominator so no-return-fire spots don't divide by zero
# Armor-exposure weighting: damage that lands on thin armor counts for more,
# in both directions (what this mech deals and what it receives). A shot from
# the front counts 1.0; other sides are scaled by how much more of a location's
# durability a point of damage uses there, clamped to [MIN, MAX]. See the
# movement_selection docstring.
MOVEMENT_EXPOSURE_WEIGHTING = True
MOVEMENT_EXPOSURE_MIN = 0.5
MOVEMENT_EXPOSURE_MAX = 3.0
# Add the expected fall damage of the Movement Phase PSR a Run/Jump would force
# (only a damaged mech has one) to the damage received.
MOVEMENT_PSR_COST = True
# Internal-structure damage counts for more than armor damage (Daniel, 2026-10-19):
# per weapon, the part of a hit that gets past a location's armor and into its
# structure counts this many times. 1.0 = off. See INTEGRATION__structure_weight.
MOVEMENT_STRUCTURE_WEIGHT = 2.0
# Which movement objective scores a spot (Daniel, 2026-10-20 - an option to test):
#   "ratio"    - dealt / (received + PSR cost + MOVEMENT_RATIO_EPSILON) (Daniel, 2026-10-19)
#   "lifetime" - dealt + (my HP left after this turn / the enemy's future damage
#                per turn) x my future damage per turn: the damage this mech can
#                expect to deal before it is destroyed. Fights when this turn's
#                trade beats the trades it can expect later; a spot that gets it
#                destroyed (or pushed off the board) keeps only its dealt.
#                Future damage: INTEGRATION__future_damage. HP is armor + rear
#                armor + MOVEMENT_STRUCTURE_WEIGHT x structure (the same units
#                as dealt / received).
MOVEMENT_OBJECTIVE = "lifetime"   # default since 2026-10-21 (Daniel), with the history blend below
MOVEMENT_LIFETIME_INITIATIVE = 0.5          # odds of winning initiative (scales both sides; cancels out)
MOVEMENT_LIFETIME_ATTACKER_MODE = "Walk"    # the attacker's assumed movement for future damage (AMM, heat)
MOVEMENT_LIFETIME_FUTURE_FLOOR = 1.0        # future damage per turn is never taken below this (no divide by zero)
# History blend (Daniel, 2026-10-21: "We can't predict the future. But we can
# record the past ... a mech that is doing well will continue to do well, but a
# mech that is losing becomes more desperate to inflict damage"). Each future
# damage per turn becomes
#     (K x the estimate + damage actually done so far) / (K + turns fought)
# where damage done = how much the OTHER mech's HP (same units: armor + k x
# structure) has really gone down, and turns fought count from the first turn
# either mech lost HP. K = how many turns' worth of trust the estimate gets:
# on the first turn it is all estimate, later the record takes over. None = off.
MOVEMENT_LIFETIME_HISTORY_K = 3.0  # default since 2026-10-21 (Daniel); K 1 vs 3 was within the dice noise

# Charge attacks (Core p.78, INTEGRATION__charge, 2026-10-20): the mover may
# charge an enemy that has finished moving, when a charge in that movement mode
# beats the best ordinary attack and its score beats the normal pick.
CHARGES = True
# Death from above (Core pp.79-80, INTEGRATION__dfa, 2026-10-20): same decision.
DFA = True
# Picking up clubs (Core p.79, INTEGRATION__clubs). ON since 2026-10-21 (Daniel:
# "Clubs do not block weapons fire ... May as well have mechs pick them up if
# they have nothing better to do"): a mech that fires nothing in a Ranged phase
# picks up a club in its hex. Was off (2026-10-20). A smarter decision waits for
# the bot's future-capability planning (PROJECT_MAP Section 6, "Memo").
CLUB_PICKUP = True

# =============================================================================
# ==========================  OPTIONAL RULES  =================================
# =============================================================================
# Cluster damage pooling (Daniel, 2026-10-20: "all cluster damage of a specific
# size is added up and then applied. So 2 LRM 20's that both rolled for 12
# damage would do 5,5,5,5,4"). True: in a Ranged phase, every Cluster hit's
# damage from one attacker with the same grouping size (and damage type) is
# summed, then split into groupings. False: each attack's hits are grouped on
# their own (Core pp.74, 87 read per attack). Default False since 2026-10-21
# (Daniel: "Follow the rules, not my calls") - the rules as written.
POOL_CLUSTER_DAMAGE = False
# Rules where the Core Rulebook offers a choice, or where Daniel's own rule
# differs from it (Daniel, 2026-10-20).
#
# Floating Criticals (Core p.95, optional): a Hit Location roll of 2 re-rolls
# where the shot lands and the critical-hit chance goes there. False = the
# standard Through-Armor Critical (p.91): the damage stays on the torso the 2
# hit, plus one extra critical-hit check there.
FLOATING_CRITICALS = True
#
# Fight to the death (Daniel, 2026-10-20). False (default, Daniel's rule - kept
# 2026-10-21: "fight to the death is set to off because it saves time when the
# situation is hopeless"): the fight is over when a mech is rendered immobile
# for good - a destroyed gyro or both legs destroyed counts as destroyed. True
# (the rules as written): a
# destroyed gyro means a fall and no standing up (p.98) but the mech fights on
# from the ground; both legs destroyed makes it immobile (pp.49, 90) and it
# fights on propped up (p.67); a mech is destroyed when immobile with no ranged
# weapons left (p.99). (Crippled / forced withdrawal: a later option.)
FIGHT_TO_THE_DEATH = False
#
# Passive buildings (Daniel, 2026-10-21: "treat buildings as passive terrain.
# Blocks LOS. Can't be entered. Can be jumped onto"). True: a building hex is
# a block as tall as its roof - it blocks LOS like a hill (p.135), ground
# movement can't enter it, a 'Mech can jump onto the roof (p.50) and walk
# roof to roof (same level or one lower) but not off a roof (p.134); nothing
# damages it. False: the full building rules (forced entry, moving inside,
# damage, collapse - Core pp.130-136) - not built yet, so a map with
# buildings refuses to load.
PASSIVE_BUILDINGS = True

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

# ONE POOL OF DICE (2026-11-03, Daniel: "Do a clean up pass"): every roll of a battle - to-hit,
# hit location, criticals, PSRs, Initiative, the home edge - comes from the battle's own
# INTEGRATION__rng.BattleRNG, which the orchestrator hands over with set_active_rng(). Its state
# is the whole random state of a battle, which is what a saved state stores. Nothing in the
# engine may draw from Python's `random` module or numpy's global generator; tests/test_rng.py
# fails a battle that does. Outside a battle (a test calling roll_2d6() by hand) the rolls come
# from a private unseeded BattleRNG made on first use - the same code path.
_ACTIVE_RNG = None      # the battle's BattleRNG, set by the orchestrator via set_active_rng()
_LOOSE_RNG = None       # the unseeded pool for rolls made outside a battle


def set_active_rng(battle_rng):
    """Hands this module the battle's INTEGRATION__rng.BattleRNG, so roll_2d6()
    / pick_number() draw from it. None = no battle: rolls come from an
    unseeded pool (not reproducible)."""
    global _ACTIVE_RNG
    _ACTIVE_RNG = battle_rng


def active_rng():
    """The pool rolls are drawn from now: the battle's, or the unseeded one."""
    global _LOOSE_RNG
    if _ACTIVE_RNG is not None:
        return _ACTIVE_RNG
    if _LOOSE_RNG is None:
        from INTEGRATION__rng import BattleRNG
        _LOOSE_RNG = BattleRNG(seed=None)
    return _LOOSE_RNG


_log_sink = None   # INTEGRATION__replay's recorder while it records a battle


def set_log_sink(fn):
    """fn(msg) also receives every log line (VERBOSE or not); None = off."""
    global _log_sink
    _log_sink = fn


_quiet_depth = 0   # > 0 inside quiet(): a dry run's log lines are dropped


@contextlib.contextmanager
def quiet():
    """Within the block log() says nothing - for a bot weighing a choice
    with the same code that will later declare it (a dry run)."""
    global _quiet_depth
    _quiet_depth += 1
    try:
        yield
    finally:
        _quiet_depth -= 1


def log(msg=""):
    if _quiet_depth:
        return
    if VERBOSE:
        print(msg)
    if _log_sink is not None:
        _log_sink(msg)


def data_path(path):
    """Resolve a config path: absolute paths pass through, relative ones are
    looked up under DATA_DIR (2026-10-18)."""
    if path is None or os.path.isabs(path):
        return path
    return os.path.join(DATA_DIR, path)


def _next_2d6():
    """The next 2d6 sum from the active pool (bulk-cached inside BattleRNG)."""
    return active_rng().roll_2d6()


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
        return active_rng().pick_number(n)

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


def _unit_label(team, number, of_team, name):
    """A unit's label in the logs (INTEGRATION__forces): its name, else the team's
    name when it is the team's only unit, else '<team> <number>'."""
    if name:
        return name
    return team if of_team == 1 else f"{team} {number}"


def load_roster():
    """Everything a battle needs to field its units: a list of dicts
    {"template": parsed BattleMech, "cfg": its settings (the keys of
    MECH_*_CONFIG plus "team"), "label": its unique label, "team": its team,
    "path": its .mtf}, in the order the units are listed.

    FORCES None: the two-'Mech battle - Red from MECH_RED_*, Blue from
    MECH_BLUE_*, exactly as load_two_mechs() reads them (same printout).
    Otherwise one entry per unit of FORCES (each distinct .mtf is parsed once;
    battles clone the template)."""
    if FORCES is None:
        red, blue, red_path, blue_path = load_two_mechs()
        return [{"template": red, "cfg": dict(MECH_RED_CONFIG, team="Red"), "label": "Red", "team": "Red",
                 "path": red_path},
                {"template": blue, "cfg": dict(MECH_BLUE_CONFIG, team="Blue"), "label": "Blue", "team": "Blue",
                 "path": blue_path}]
    print("=" * 60)
    print("FORCES")
    print("=" * 60)
    specs = []
    for entry in FORCES:
        unknown = set(entry) - {"team", "mtf", "count", "name", "hex", "facing", "gunnery", "piloting", "min_heat",
                                "max_heat", "bot", "search", "assumes_enemy_search"}
        if unknown:
            raise ValueError(f"FORCES entry {entry.get('team')!r}: unknown key(s) {sorted(unknown)}")
        if "team" not in entry or not entry.get("mtf"):
            raise ValueError(f"FORCES entries need a 'team' and an 'mtf': {entry}")
        specs += [dict(entry) for _ in range(int(entry.get("count", 1)))]
    if len(specs) < 2 or len({e["team"] for e in specs}) < 2:
        raise ValueError("FORCES needs at least two units on at least two teams.")
    per_team = {}
    for e in specs:
        per_team[e["team"]] = per_team.get(e["team"], 0) + 1
    parsed = {}
    roster, seen_labels, numbers = [], set(), {}
    for e in specs:
        team = e["team"]
        numbers[team] = numbers.get(team, 0) + 1
        label = _unit_label(team, numbers[team], per_team[team], e.get("name"))
        if label in seen_labels:
            raise ValueError(f"Two units are both called {label!r} - give them different names.")
        seen_labels.add(label)
        path = data_path(e["mtf"])
        if path not in parsed:
            parsed[path] = parse_mtf(path)
        cfg = dict(FORCE_DEFAULTS)
        cfg.update({k: v for k, v in e.items() if k not in ("count", "mtf", "name")})
        if DEPLOYMENT == "fixed_hexes" and not e.get("hex"):
            raise ValueError(f"{label}: DEPLOYMENT is 'fixed_hexes' - the unit needs a 'hex'.")
        cfg.setdefault("hex", None)
        mech = parsed[path]
        print(f"  {label:<16} {team:<10} {mech.chassis} {mech.model}  ({path})")
        roster.append({"template": mech, "cfg": cfg, "label": label, "team": team, "path": path})
    hexes = [r["cfg"]["hex"] for r in roster if r["cfg"].get("hex")]
    if len(hexes) != len(set(hexes)):
        raise ValueError("Two units start in the same hex.")
    print("=" * 60)
    return roster


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
