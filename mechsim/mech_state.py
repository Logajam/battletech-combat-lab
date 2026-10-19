"""
"What a mech IS" - state container and pure state-query functions.

BattleMech itself is now just a data container (built either from the
hardcoded stress-test fixture below, or from a real unit via
mtf_parser.parse_mtf). All behavior that happens TO a mech (damage, crits,
explosions) lives in damage_resolution.py instead - see
ARCHITECTURE_PROPOSAL.md section 2 for the reasoning.

Functions here take `mech` as an explicit first argument rather than being
methods (e.g. `is_destroyed(mech)` not `mech.is_destroyed()`) - this was a
deliberate choice (ARCHITECTURE_PROPOSAL.md section 5, question 1, "Option
A") to keep the split between this file and damage_resolution.py clean
without a mixin class spanning both.
"""

import copy
import math
from enum import Enum, auto

from equipment import Equipment, equipment_slots, is_crit_target


# ---------------------------------------------------------------------------
# Damage-type / armor-type identity enums.
#
# Ported from the vehicle sim's vehicle_state.py (same module role there -
# "what a vehicle IS" - so co-located here with BattleMech, the mech sim's
# equivalent "what a mech IS" container). See armor_rules.py for the actual
# dispatch math that consumes these; this module only owns identity.
# ---------------------------------------------------------------------------

class DamageType(Enum):
    BALLISTIC = "B"
    ENERGY = "E"
    MISSILE = "M"
    AREA_EFFECT = "AE"
    PHYSICAL = "PHYSICAL"
    REENGINEERED = "R"   # "Holy" - ignores armor-type math entirely, treated
                          # as if armor_type were STANDARD. See
                          # armor_rules._effective_damage_for_location.


DAMAGE_TYPE_BY_CODE = {dt.value: dt for dt in DamageType}


class StructureType(Enum):
    """Ported from the vehicle sim's StructureType (Gap Analysis Stage 3).
    Mech-WIDE, not per-location - unlike ArmorType/Patchwork, there is no
    per-location structure type on a real mech. See armor_rules._consume_structure
    for the actual math."""
    STANDARD = auto()       # includes Endo Steel/Endo-Composite/etc. - no combat-math
                             # difference from Standard, they only affect construction
                             # tonnage, which this sim doesn't model.
    REINFORCED = auto()
    COMPOSITE = auto()


class ArmorType(Enum):
    # HELP(armor_type.no_dispatch_members)
    STANDARD = auto()                  # includes all Ferro-Fibrous variants
    REACTIVE = auto()
    REFLECTIVE = auto()
    HARDENED = auto()
    FERRO_LAMELLOR = auto()
    IMPACT_RESISTANT = auto()
    ANTI_PENETRATIVE_ABLATION = auto()  # crit-roll-modifier-only per RAW (Stage
                                         # 4, out of scope this pass) - no damage
                                         # math branch in armor_rules.py, falls
                                         # through to flat 1:1 like STANDARD.
    BALLISTIC_REINFORCED = auto()
    HEAT_DISSIPATING = auto()          # Real MegaMek armor type with no vehicle-
                                        # sim equivalent to port (vehicle sim
                                        # doesn't model heat). No damage math
                                        # branch in armor_rules.py - falls
                                        # through to flat 1:1, same as STANDARD,
                                        # but kept as its own named member so
                                        # logs/record sheets show the real type
                                        # instead of masking it. Confirm real
                                        # mechanics before adding dispatch logic.


# Standard internal structure points by tonnage (Total Warfare internal structure table).
# CT/ST/Arm/Leg values; Head is always a fixed 3 regardless of tonnage.
STRUCTURE_TABLE = {
    20: {"CT": 6, "ST": 5, "Arm": 3, "Leg": 4}, 25: {"CT": 8, "ST": 6, "Arm": 4, "Leg": 6},
    30: {"CT": 10, "ST": 7, "Arm": 5, "Leg": 7}, 35: {"CT": 11, "ST": 8, "Arm": 6, "Leg": 8},
    40: {"CT": 12, "ST": 10, "Arm": 6, "Leg": 10}, 45: {"CT": 14, "ST": 11, "Arm": 7, "Leg": 11},
    50: {"CT": 16, "ST": 12, "Arm": 8, "Leg": 12}, 55: {"CT": 18, "ST": 13, "Arm": 9, "Leg": 13},
    60: {"CT": 20, "ST": 14, "Arm": 10, "Leg": 14}, 65: {"CT": 21, "ST": 15, "Arm": 10, "Leg": 15},
    70: {"CT": 22, "ST": 15, "Arm": 11, "Leg": 15}, 75: {"CT": 23, "ST": 16, "Arm": 12, "Leg": 16},
    80: {"CT": 25, "ST": 17, "Arm": 13, "Leg": 17}, 85: {"CT": 27, "ST": 18, "Arm": 14, "Leg": 18},
    90: {"CT": 29, "ST": 19, "Arm": 15, "Leg": 19}, 95: {"CT": 30, "ST": 20, "Arm": 16, "Leg": 20},
    100: {"CT": 31, "ST": 21, "Arm": 17, "Leg": 21},
}


def structure_for_tonnage(mass, mech_type="biped"):
    if mass not in STRUCTURE_TABLE:
        raise ValueError(f"No internal structure table entry for {mass} tons "
                          f"(only standard 20-100 in 5-ton steps are supported).")
    t = STRUCTURE_TABLE[mass]
    out = {
        "Head": 3, "Center Torso": t["CT"], "Left Torso": t["ST"], "Right Torso": t["ST"],
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


class BattleMech:
    def __init__(self, mech_type="biped"):
        self.mech_type = mech_type
        self.chassis = ""
        self.model = ""

        self.locations = {
            "Head": {"armor": 9, "structure": 3, "destroyed": False},
            # NOTE: front armor values below are placeholder stress-fixture numbers,
            # NOT transcribed from a real mech. Use MTF_FILE_PATH to load real mech data instead.
            "Center Torso": {"armor": 30, "rear_armor": 14, "structure": 31, "destroyed": False},
            "Left Torso": {"armor": 20, "rear_armor": 10, "structure": 21, "destroyed": False},
            "Right Torso": {"armor": 20, "rear_armor": 10, "structure": 21, "destroyed": False},
        }

        self.crits = {
            "Head": ["Cockpit", "Sensors", "Life Support", "Padding", "Padding"],
            "Center Torso": ["Engine", "Engine", "Engine", "Gyro", "Gyro", "Gyro", "Gyro",
                              "Engine", "Engine", "Engine", "Padding", "Padding"],
            "Left Torso": (
                ["Engine", "Engine", "Padding", "Padding", "Padding", "Padding", "Padding", "Padding"]
                + equipment_slots("LRM Ammo", 1, is_explosive=True, explosion_damage=20)
                + equipment_slots("LRM Ammo", 1, is_explosive=True, explosion_damage=20)
                + ["CASE", "Padding"]
            ),
            "Right Torso": ["Engine", "Engine", "Padding", "Padding", "Padding",
                             "Padding", "Padding", "Padding", "Padding", "Padding"],
        }

        if mech_type in ("quad", "quadvee"):
            # A Quad's four legs are NOT "two normal legs + two arm-shaped front legs" -
            # ALL FOUR get distinct names of their own. "Front Left Leg"/"Front Right Leg"
            # sit where a biped's arms would be; "Rear Left Leg"/"Rear Right Leg" are what
            # a biped would just call "Left Leg"/"Right Leg". All four use LEG
            # structure/armor stats, all four have the same Hip/Upper Leg/Lower Leg/Foot
            # actuator set.
            self.locations["Front Left Leg"] = {"armor": 41, "structure": 21, "destroyed": False}
            self.locations["Front Right Leg"] = {"armor": 41, "structure": 21, "destroyed": False}
            self.locations["Rear Left Leg"] = {"armor": 41, "structure": 21, "destroyed": False}
            self.locations["Rear Right Leg"] = {"armor": 41, "structure": 21, "destroyed": False}
            self.crits["Front Left Leg"] = (
                ["Hip", "Upper Leg", "Lower Leg", "Foot", "Padding", "Padding", "Padding", "Padding", "Padding"]
                + equipment_slots("Ammo", 1, is_explosive=True, explosion_damage=20)
                + ["CASE"]
            )
            self.crits["Front Right Leg"] = (
                ["Hip", "Upper Leg", "Lower Leg", "Foot"]
                + equipment_slots("Gauss Rifle", 7, is_explosive=True)  # 2 dmg/slot -> 14
            )
            self.crits["Rear Left Leg"] = ["Hip", "Upper Leg", "Lower Leg", "Foot", "Padding", "Padding"]
            self.crits["Rear Right Leg"] = ["Hip", "Upper Leg", "Lower Leg", "Foot"]
        else:
            self.locations["Left Arm"] = {"armor": 34, "structure": 17, "destroyed": False}
            self.locations["Right Arm"] = {"armor": 34, "structure": 17, "destroyed": False}
            self.locations["Left Leg"] = {"armor": 41, "structure": 21, "destroyed": False}
            self.locations["Right Leg"] = {"armor": 41, "structure": 21, "destroyed": False}
            self.crits["Left Arm"] = (
                ["Shoulder", "Upper Arm", "Lower Arm", "Hand",
                 "Padding", "Padding", "Padding", "Padding", "Padding"]
                + equipment_slots("Ammo", 1, is_explosive=True, explosion_damage=20)
                + ["CASE"]
            )
            self.crits["Right Arm"] = (
                ["Shoulder", "Upper Arm", "Lower Arm", "Hand"]
                + equipment_slots("Gauss Rifle", 7, is_explosive=True)  # 2 dmg/slot -> 14
            )
            self.crits["Left Leg"] = ["Hip", "Upper Leg", "Lower Leg", "Foot", "Padding", "Padding"]
            self.crits["Right Leg"] = ["Hip", "Upper Leg", "Lower Leg", "Foot"]

        if mech_type == "tripod":
            self.locations["Center Leg"] = {"armor": 41, "structure": 21, "destroyed": False}
            self.crits["Center Leg"] = ["Hip", "Upper Leg", "Lower Leg", "Foot", "Padding", "Padding"]

        if mech_type in ("quad", "quadvee"):
            # All four legs count as "legs" for destruction purposes (Daniel: 2 legs
            # destroyed is still the kill threshold, even with 4 total).
            self.leg_locations = ["Front Left Leg", "Front Right Leg", "Rear Left Leg", "Rear Right Leg"]
            self.limb_locations = list(self.leg_locations)  # no separate arms on a quad
        else:
            self.leg_locations = ["Left Leg", "Right Leg"] + (["Center Leg"] if mech_type == "tripod" else [])
            self.limb_locations = ["Left Arm", "Right Arm"] + self.leg_locations

        if mech_type in ("quad", "quadvee"):
            self.side_torso_child = {"Left Torso": "Front Left Leg", "Right Torso": "Front Right Leg"}
        else:
            self.side_torso_child = {"Left Torso": "Left Arm", "Right Torso": "Right Arm"}

        self.max_armor = {loc: v["armor"] for loc, v in self.locations.items()}
        self.max_rear_armor = {loc: v["rear_armor"] for loc, v in self.locations.items() if "rear_armor" in v}
        self.max_structure = {loc: v["structure"] for loc, v in self.locations.items()}

        # Per-location armor type (Stage 2/5 port from vehicle sim - see
        # armor_rules.py). Defaults to STANDARD for every location; this
        # hardcoded fixture mech never goes through mtf_parser.parse_mtf, so
        # this default is its final value. Real parsed mechs get this
        # overwritten per-location in mtf_parser.parse_mtf, reading each
        # location's own armor header line (never inferred from crit-slot
        # contents - see mtf_parser.py's Known Issue #4 note).
        self.armor_type = {loc: ArmorType.STANDARD for loc in self.locations}

        # Mech-wide (not per-location) structure type - Stage 3 port. Defaults
        # STANDARD for the hardcoded fixture; real parsed mechs get this
        # overwritten in mtf_parser.parse_mtf from the top-level "structure:"
        # header line.
        self.structure_type = StructureType.STANDARD

        # TMM port (Daniel's 2026-07-12 go-ahead - the Gap Analysis originally
        # flagged TMM as "vehicle-only, no mech equivalent"; that call is
        # superseded by this explicit instruction, see Project Map Change
        # Record). base_walk_mp/base_jump_mp are placeholder stress-fixture
        # values (this hardcoded mech never goes through mtf_parser.parse_mtf)
        # - NOT transcribed from a real mech, same caveat as the armor
        # placeholders above. Real parsed mechs get these overwritten in
        # mtf_parser.parse_mtf from the "walk mp:"/"jump mp:" header lines.
        self.base_walk_mp = 4
        self.base_jump_mp = 0

        # Per-leg-location count of destroyed leg actuator crit slots (Hip/
        # Upper Leg Actuator/Lower Leg Actuator/Foot Actuator - Daniel's house
        # rule: each applies a flat -1 to walking MP, no Hip-halves-MP special
        # case like true RAW). Mutated by damage_resolution.resolve_slot_hit
        # at the moment an actuator slot is destroyed - see
        # HELP(leg_actuator.tracking) there. Can't be recovered by re-scanning
        # mech.crits after the fact, since a destroyed slot's cell becomes the
        # bare string "DESTROYED", losing which actuator it used to be. Read
        # by compute_walk_mp below.
        self.destroyed_leg_actuators = {loc: 0 for loc in self.leg_locations}

        # HELP(hip_actuator.tracking)
        # Set of leg location names whose Hip actuator slot has been destroyed
        # (Daniel, 2026-07-16) - destroyed_leg_actuators above only tracks a
        # per-location COUNT across all four actuator types, losing which
        # specific actuator was hit once mech.crits[loc][idx] becomes the bare
        # "DESTROYED" sentinel. piloting_rolls' Movement Phase PSR trigger
        # needs to distinguish "Hip hit" (running-mode trigger) from any other
        # leg actuator, so this is tracked separately, mirroring the
        # destroyed_jump_jet_ids set-based presence-tracking pattern. Mutated
        # by damage_resolution.resolve_slot_hit (single-slot Hip hit) and
        # mark_all_crits_destroyed (location wipe - checked BEFORE the slot is
        # overwritten, same gap class as the jump-jet location-wipe fix).
        self.destroyed_hip_locations = set()

        # Set of id(equipment_instance) for jump-jet Equipment instances that
        # have had at least one of their crit slots destroyed - see
        # HELP(jump_jet.hardcoded_name_match) in damage_resolution.py. Tracked
        # by INSTANCE IDENTITY (not slot count), because Improved Jump Jets
        # now occupy 2 shared slots (Daniel's equipment.json edit) -
        # destroying either slot kills the jump jet's function, but the other
        # slot stays a normal, still-targetable crit entry rather than
        # double-counting the loss when it's eventually hit too. Read by
        # compute_jump_mp below.
        self.destroyed_jump_jet_ids = set()

        # HELP(heat_sink.tracking)
        # Total heat-sink count and type text (e.g. "Single"/"Double") from
        # the .mtf "heat sinks:N Type" header line (Daniel, 2026-08-04). Set
        # by mtf_parser.build_mech_from_mtf(); base_heat_sinks defaults to 0
        # with a parser WARNING if the line is missing (never legitimately
        # absent on a real mech, unlike jump mp). Read by
        # compute_heat_dissipation below - the whole mech is treated as one
        # uniform heat-sink type per this single header line, so a destroyed
        # sink's dissipation rate always comes from heat_sink_type, not
        # re-inspected from its own crit-slot name.
        self.base_heat_sinks = 0
        self.heat_sink_type = "Single"

        # Accumulated heat right now (2026-08-05, INTEGRATION) - the Heat
        # Scale level. Updated once per turn by INTEGRATION__heat.
        # resolve_heat_phase, which also applies the Heat Scale effects
        # below (2026-10-19, Core Rulebook pp.103-107). Can exceed 30
        # (Overflow).
        self.current_heat = 0

        # HELP(heat_scale.effects)
        # Heat Scale effects in force for the CURRENT turn, set at the end of
        # the previous Heat Phase (Core Rulebook p.103: effects other than
        # ammo explosions "begin at the start of the following turn") by
        # INTEGRATION__heat.apply_heat_effects - the thresholds live there.
        #   heat_mp_penalty: Walking MP lost (read by compute_walk_mp below)
        #   heat_fire_modifier: + to ranged to-hit numbers
        #   shutdown: power plant shut down (immobile, can't attack, standing
        #     PSRs fail automatically - pp.104-105). Heat sinks still work.
        self.heat_mp_penalty = 0
        self.heat_fire_modifier = 0
        self.shutdown = False
        # Triple-strength myomer active this turn (heat 9+ at the end of the
        # last Heat Phase, Core p.205): +2 Walking MP, read by compute_walk_mp.
        self.tsm_active = False
        # Heat sinks switched off in the End Phase (Core p.103), in heat-sink
        # units - they dissipate nothing. Read by compute_heat_dissipation.
        self.deactivated_heat_sinks = 0
        # Running MP = Walking MP x this (1.5 normally; 2 with MASC or a
        # supercharger, 2.5 with both - Core p.204). Set per turn by
        # INTEGRATION__equipment_systems; read by compute_running_mp.
        self.run_mp_multiplier = 1.5

        # .mtf "Myomer:" header text (2026-10-19). Only read for super-cooled
        # myomer's movement heat (INTEGRATION__heat.movement_heat).
        self.myomer = "Standard"

        # id(equipment_instance) -> units, for heat-sink Equipment instances
        # that have had at least one crit slot destroyed (Daniel,
        # 2026-08-04). Mirrors destroyed_jump_jet_ids's instance-identity
        # tracking (same reasoning: a multi-slot heat sink must only count
        # once no matter how many of its slots are later hit), but keyed to
        # a units value rather than a bare set, since the bundled "2 Compact
        # Heat Sinks" equipment.json entry represents 2 physical heat sinks
        # destroyed in one instance, not 1 - see
        # HELP(heat_sink.hardcoded_name_match) in damage_resolution.py.
        # Deliberately excludes Radical Heat Sink System (activatable
        # equipment with its own risk mechanic, not a passive dissipation
        # source - not wired in at all, not even as a zero-effect entry).
        # Read by compute_heat_dissipation below.
        self.destroyed_heat_sinks = {}

        # HELP(record_sheet.destroyed_slot_info)
        # (location, zero_based_slot_idx) -> {"name": str, "instance_id": id|None}.
        # Display-only side table (2026-07-14, Claude) - once a crit slot is
        # destroyed, mech.crits[location][idx] becomes the bare sentinel string
        # "DESTROYED", which loses what was actually there. Populated by
        # damage_resolution.resolve_slot_hit() and mark_all_crits_destroyed()
        # at the moment of destruction, read by sim_runner.print_record_sheet()
        # to show identity (and, via instance_id, shared-slot grouping for
        # multi-slot equipment) on an otherwise-bare destroyed slot. Nothing
        # else reads this - is_crit_target/resolve_critical's pool-building
        # and every other resolution-path check still treat "DESTROYED" as an
        # opaque sentinel, unaffected by this table's presence.
        self.destroyed_slot_info = {}

        # Mechanical Jump Booster (2026-07-13, Claude) - separate MP track from
        # standard jump jets, all-or-nothing (a crit to ANY of its slots, anywhere
        # on the mech, disables the whole system - unlike standard jump jets' per-
        # instance chip damage). base_mechanical_jump_booster_mp is read straight
        # off the .mtf's "SIZE:" value (see mtf_parser.py's HELP tag) - 0/absent
        # doubles as "mech doesn't have this system," used to skip the whole logic
        # branch (Daniel, 2026-07-13: "0 skip. Any number use this logic branch").
        # See DESIGN_NOTES_mech.md#mechanical_jump_booster for the full design.
        self.base_mechanical_jump_booster_mp = 0
        self.mechanical_jump_booster_disabled = False

        # Partial Wing (2026-07-14, Claude/Daniel) - +1/+2 jump MP bonus, same
        # all-or-nothing pattern as Mechanical Jump Booster above (a crit to
        # ANY of its slots disables the whole system) rather than standard
        # jump jets' per-instance chip damage - Daniel's explicit call, since
        # unlike Improved Jump Jets' 2-shared-slots-per-instance grouping,
        # Partial Wing's 8 crit lines (4/side torso) are each their own
        # 1-slot Equipment instance with no natural grouping to chip away at.
        # Single boolean does double duty as both "mech has a Partial Wing"
        # (set True by mtf_parser.parse_mtf if any crit slot matches
        # damage_resolution.is_partial_wing) and "it's still functional" (set
        # False the moment any slot is hit) - mirrors
        # base_mechanical_jump_booster_mp's "0 doubles as absent" pattern,
        # just boolean instead of magnitude since there's no SIZE: value to
        # read. Read by compute_jump_mp below. See
        # DESIGN_NOTES_mech.md#partial_wing for the full design.
        self.partial_wing_active = False

        self.pilot_hits = 0

        # HELP(pilot_consciousness.crew_state)
        # Pilot Consciousness Checks (Daniel, 2026-07-17) - see
        # DESIGN_NOTES_mech.md#pilot_consciousness and piloting_rolls.py.
        # mech.pilot_hits (above) stays a single SHARED counter - every hit
        # source that increments it hits every crew member equally (Daniel:
        # "any event that would normally increase the pilot hits counter
        # increases all of their counters") - so there's no separate hit
        # count per role, only separate CONSCIOUSNESS state, since that's
        # the only thing that can diverge between crew members (independent
        # rolls off the same hit count).
        # One entry per crew role this mech_type tracks - "pilot" only for
        # biped/quad; "pilot" + "gunner" for tripod/quadvee (2 separately-
        # rolled crew - Daniel: "All of them roll separately for
        # consciousness checks"); "technical" (superheavy tripod's 3rd crew
        # member) intentionally never populated - no superheavy tripod
        # parsing exists yet, reserved for later.
        #   unconscious: is this crew member currently out?
        #   check_pending: has a pilot-hit happened since this crew member's
        #     last consciousness check that hasn't been rolled yet? Set True
        #     by mark_consciousness_check_pending (called from every
        #     pilot_hits += 1 site) for every NOT-YET-unconscious crew
        #     member; cleared the moment their check is rolled. Never set
        #     for an already-unconscious crew member (Daniel: "there is not
        #     need to make further consciousness checks when the pilot is
        #     unconscious").
        #   went_out_this_turn: 1-turn decay tracking for the wake-up roll
        #     (Daniel: "If the state was changed this turn then the 'Am I
        #     awake' check is not made until the end of the next turn") -
        #     True for the rest of the turn a crew member fails their
        #     consciousness check, reset False at the top of every turn.
        crew_roles = ["pilot", "gunner"] if mech_type in ("tripod", "quadvee") else ["pilot"]
        self.crew = {role: {"unconscious": False, "check_pending": False, "went_out_this_turn": False}
                     for role in crew_roles}

        self.engine_hits = 0
        self.gyro_hits = 0
        self.cockpit_hit = False
        self.explosions = 0
        self.destroyed = False
        self.cause_of_death = None
        self.crippled = False
        self.crippled_at = None

        # HELP(piloting_skill_rolls.prone_state)
        # Piloting Skill Roll system (Daniel, 2026-07-16) - see
        # DESIGN_NOTES_mech.md#piloting_skill_rolls and piloting_rolls.py.
        # `prone`: is the mech currently knocked down? Read/written by
        # piloting_rolls.py; sim_runner.simulate_turn() checks it at the top
        # of each turn's Movement Phase.
        self.prone = False

        # Two fixed-in-time snapshots consumed only by piloting_rolls.py's
        # modifier accumulation - NOT general-purpose mech state, kept here
        # only because BattleMech is the data container (mech_state.py's
        # module docstring). Both are dicts of plain values (no live
        # references), captured by piloting_rolls.snapshot_preexisting_damage
        # and piloting_rolls.snapshot_pre_attack_phase respectively:
        #   preexisting_damage_snapshot: state at the very start of the round
        #     (before this turn's Movement Phase) - source of the "Preexisting
        #     Damage" PSR modifier column (applies to every PSR/seatbelt roll
        #     this turn, per Daniel: "asking those conditions existed at the
        #     start of the round before damage was applied").
        #   pre_attack_phase_snapshot: state after the Movement Phase, before
        #     the Attack Phase's weapon-attack loop - source of the "20+
        #     damage this phase" / "actuator destroyed this phase" / "gyro hit
        #     this phase" triggers, found by diffing against current state
        #     once the attack loop finishes.
        self.preexisting_damage_snapshot = {}
        self.pre_attack_phase_snapshot = {}

        # HELP(movement_mode.tracking)
        # "running" or "jump" - which mode produced this turn's winning TMM
        # (Daniel, 2026-07-16). Set by damage_resolution.compute_tmm (Mechanical
        # Jump Booster counts as "jump" if it wins the tie-break, per Daniel's
        # confirmation it's still a jumping movement type for PSR purposes).
        # Ties go to "running" (Daniel: "it has fewer triggers"). Consumed by
        # piloting_rolls.check_movement_psr for the new Movement Phase PSR
        # trigger (leg actuator/gyro hit + jumping; Hip/gyro hit + running).
        # A mech that stood up from prone this turn never runs through
        # compute_tmm's comparison - resolve_stand_up sets this to "running"
        # directly, since only running MP is ever used to stand.
        self.movement_mode_this_turn = "running"

        # Fixed snapshot of crit-capability taken at the START of the current attack
        # ("round") - see snapshot_round_capability() below and Total Warfare Step 4/5.
        self.round_capable = {}
        snapshot_round_capability(self)

        # Snapshot of how many "Sensors" slots the mech started with, for the official
        # crippling condition "destruction of all sensor critical slots" - captured once,
        # here and again after parse_mtf() assigns real crit data, since the generic
        # fixture's Head layout differs from a real mech's.
        self.initial_sensor_slots = sum(1 for s in self.crits.get("Head", []) if s == "Sensors")


# HELP(clone_mech.deepcopy_replacement)
def clone_mech(mech):
    """Fast, purpose-built replacement for copy.deepcopy(mech) in
    sim_runner.run_monte_carlo()'s per-simulation hot loop (2026-07-22,
    Daniel/Claude - profiling showed generic deepcopy was ~28% of total
    batch runtime). Generic over mech.__dict__ rather than a hardcoded list
    of field names, so it automatically covers every attribute BattleMech
    .__init__ sets AND every attribute mtf_parser.parse_mtf adds afterward
    (.mass, .engine_desc - NOT set by __init__, see the known fixture-mech
    gap noted elsewhere in this file) - a hand-picked field list would
    silently drop anything it doesn't know about, which is the failure mode
    this is specifically designed to avoid.

    Equipment instances get special handling via a per-call identity memo
    (keyed by id() of the ORIGINAL instance): Equipment carries real mutable
    state (.exploded - see damage_resolution.apply_explosion) and is
    intentionally SHARED across multiple crit slots of the same weapon/ammo
    bin (equipment.equipment_slots' docstring: "three lasers are three
    objects, one 7-slot Gauss Rifle is one object"). The memo preserves that
    sharing WITHIN this one clone (three .crits list entries pointing at the
    same original Equipment all resolve to the same NEW Equipment instance),
    while still giving each clone - and the template_mech it was cloned from
    - fully independent Equipment objects, matching copy.deepcopy's own
    memo-based behavior exactly. Equipment itself has no nested mutable
    fields (see equipment.Equipment.__init__ - all scalars), so a shallow
    copy.copy() per instance is sufficient.

    ArmorType/StructureType enum members are immutable and shared by
    reference, not copied - safe, and skips deepcopy's generic (and
    comparatively expensive) reduce/memo machinery for them entirely.

    FLAGGED ASSUMPTION, not exhaustively verified against every possible
    future attribute type: this only special-cases dict/list/set/tuple
    containers plus Equipment; any other mutable custom object type added to
    BattleMech in the future would be shared by reference (like an enum)
    rather than copied, which would be WRONG if that object is ever mutated
    per-mech. As of 2026-07-22, the only non-container, non-primitive,
    non-Equipment attribute types on BattleMech are ArmorType/StructureType
    enum members, which are correctly immutable. Flagging so this gets
    revisited if a new mutable attribute type is ever added to BattleMech."""
    equip_memo = {}

    def _clone_value(v):
        if isinstance(v, Equipment):
            cloned = equip_memo.get(id(v))
            if cloned is None:
                cloned = copy.copy(v)
                equip_memo[id(v)] = cloned
            return cloned
        if isinstance(v, dict):
            return {k: _clone_value(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_clone_value(item) for item in v]
        if isinstance(v, set):
            return set(v)  # elements are always plain strings (location
                            # names) here - immutable, no per-element clone needed
        if isinstance(v, tuple):
            return tuple(_clone_value(item) for item in v)
        # str/int/float/bool/None/Enum members: immutable, share directly
        return v

    new_mech = BattleMech.__new__(BattleMech)
    for key, value in mech.__dict__.items():
        new_mech.__dict__[key] = _clone_value(value)
    return new_mech


def snapshot_round_capability(mech):
    mech.round_capable = {
        loc: any(is_crit_target(s) for s in mech.crits[loc]) for loc in mech.crits
    }


# HELP(pilot_consciousness.helpers)
# Consciousness Number table (Daniel, 2026-07-17) - target number to stay
# conscious after a pilot hit, or to wake back up in the End Phase, keyed
# off mech.pilot_hits at the moment the roll is made. Same table serves
# both roll types (Daniel confirmed, 2026-07-17). No entry for 6+: a mech
# reaching 6 pilot hits is already destroyed (is_destroyed below) before
# any consciousness roll could see that count.
CONSCIOUSNESS_TN_BY_HITS = {1: 3, 2: 5, 3: 7, 4: 10, 5: 11}


def consciousness_target_number(pilot_hits):
    if pilot_hits not in CONSCIOUSNESS_TN_BY_HITS:
        raise ValueError(
            f"No Consciousness Number table entry for {pilot_hits} pilot hits "
            f"(table only covers 1-5; 6+ should be unreachable - is_destroyed() "
            f"kills the mech at 6 pilot hits before a consciousness roll could see that count).")
    return CONSCIOUSNESS_TN_BY_HITS[pilot_hits]


def mark_consciousness_check_pending(mech):
    """Called from every mech.pilot_hits += 1 site (sim_runner._resolve_hit's
    head hit, damage_resolution.apply_explosion, piloting_rolls.resolve_fall's
    seatbelt check) - flags every crew member who isn't already unconscious
    as owing a consciousness check. Never re-flags an already-unconscious
    crew member (Daniel: no further checks needed while already out)."""
    for state in mech.crew.values():
        if not state["unconscious"]:
            state["check_pending"] = True


def all_crew_unconscious(mech):
    """True only once EVERY tracked crew role is unconscious (Daniel: "All
    of them must be unconscious for the immobile state to exist") - for a
    single-pilot mech this is just that pilot; for tripod/quadvee it's
    Pilot AND Gunner both."""
    return all(state["unconscious"] for state in mech.crew.values())


def is_immobile(mech):
    """Immobile in the Core Rulebook's sense (p.49/p.64): shut down, or no
    conscious crew. Skips the Movement Phase and gives attackers the -4
    immobile modifier. (0 MP from damage - both legs destroyed - is already
    a kill in this sim; 0 MP from heat is NOT immobile, p.49.)"""
    return mech.shutdown or all_crew_unconscious(mech)


def pilot_unconscious(mech):
    """Specifically the 'pilot' role (as opposed to 'gunner') - drives the
    +3 piloting-roll modifier (Daniel: "Pilot: If unconscious +3 modifier
    to piloting skill rolls") which is distinct from, and can apply even
    when, all_crew_unconscious is False (e.g. a tripod/quadvee with Pilot
    out but Gunner still conscious)."""
    return mech.crew["pilot"]["unconscious"]


# HELP(is_destroyed.cause_ordering)
def is_destroyed(mech):
    if mech.destroyed:
        return True

    if mech.locations["Center Torso"]["destroyed"]:
        mech.destroyed = True
        mech.cause_of_death = "Center Torso Destroyed"
        return True
    if mech.locations["Head"]["destroyed"]:
        mech.destroyed = True
        mech.cause_of_death = "Head Destroyed"
        return True
    # HELP(leg_kill_threshold.quad_offset)
    leg_kill_threshold = 3 if mech.mech_type in ("quad", "quadvee") else 2
    if sum(1 for leg in mech.leg_locations if mech.locations[leg]["destroyed"]) >= leg_kill_threshold:
        mech.destroyed = True
        mech.cause_of_death = "Legs Destroyed"
        return True

    # Location-destruction causes (above) are checked first and return
    # immediately - deterministic, unambiguous kills. Counter-based causes
    # (below) are only reached if none of those fired. This ordering matters:
    # a location's own crit sweep (mark_all_crits_destroyed) can inflate
    # cockpit_hit/engine_hits/gyro_hits as a side effect of that SAME location
    # being destroyed (e.g. Head destroyed by structure also flags
    # cockpit_hit; Center Torso destroyed also flags its own Engine/Gyro
    # slots) - but since the location-destruction check already fired and
    # returned above, that inflated counter is never read as a false
    # alternate cause for the same event. A legitimate counter-based kill
    # (e.g. engine_hits reaching 3 via a side torso housing XL engine slots,
    # where the side torso itself isn't a lethal location) still correctly
    # falls through and triggers below.
    if mech.cockpit_hit:
        mech.destroyed = True
        mech.cause_of_death = "Cockpit Destroyed"
        return True
    if mech.pilot_hits >= 6:
        mech.destroyed = True
        mech.cause_of_death = "6 Pilot Hits"
        return True
    if mech.engine_hits >= 3:
        mech.destroyed = True
        mech.cause_of_death = "Engine Destroyed"
        return True
    if mech.gyro_hits >= 2:
        mech.destroyed = True
        mech.cause_of_death = "Gyro Destroyed"
        return True

    return False


# HELP(is_crippled.definition)
def is_crippled(mech):
    """Crippling Damage, per the BattleMech Manual (quoted verbatim by Daniel):
      - 4+ points of pilot damage
      - destruction of all sensor crit slots
      - one gyro hit AND one engine hit
      - two engine hits
      - a side torso location destroyed
      - structure damage in 3+ limbs, OR 2+ torso locations (a torso only counts
        if its FRONT armor is also gone - rear armor being gone doesn't count)
    NOT modeled: "loss of all weapons" (>5 hexes range, >5 combined damage) - this
    sim doesn't track individual weapon range/damage/ammo, so this clause can't be
    evaluated. If per-weapon tracking is ever added, come back and add this.
    """
    if mech.pilot_hits >= 4:
        return True

    if mech.initial_sensor_slots > 0:
        current_sensors = sum(1 for s in mech.crits.get("Head", []) if s == "Sensors")
        if current_sensors == 0:
            return True

    if mech.gyro_hits >= 1 and mech.engine_hits >= 1:
        return True
    if mech.engine_hits >= 2:
        return True

    if mech.locations["Left Torso"]["destroyed"] or mech.locations["Right Torso"]["destroyed"]:
        return True

    damaged_limbs = 0
    for limb in mech.limb_locations:
        v = mech.locations[limb]
        if v["destroyed"] or v["structure"] < mech.max_structure[limb]:
            damaged_limbs += 1
    if damaged_limbs >= 3:
        return True

    damaged_torsos = 0
    for t in ["Left Torso", "Right Torso", "Center Torso"]:
        v = mech.locations[t]
        if v["armor"] <= 0 and v["structure"] < mech.max_structure[t]:
            damaged_torsos += 1
    if damaged_torsos >= 2:
        return True

    return False


# HELP(walk_mp.leg_rules)
def compute_walk_mp(mech):
    """Current effective walking MP, per Daniel's 2026-07-12 leg-actuator/
    quad rules (quoted from the BattleMech Manual's Four-Legged 'Mechs
    section - see DESIGN_NOTES_mech.md#walk_mp.leg_rules for the full quote
    and derivation):

    - Biped/Tripod: ANY single leg destroyed forces walking MP to a flat 1,
      overriding whatever the accumulated actuator penalty would otherwise
      be. (Death still happens at 2 legs destroyed - see is_destroyed's
      leg_kill_threshold - so this flat-1 case is only reachable at exactly
      1 leg destroyed.)
    - Quad: per RAW, quad leg loss severity is offset by 1 compared to a
      biped/tripod (Daniel: "Quads get a -1 modifier to their leg destroyed
      count") - 2 legs destroyed forces the same flat-1 as a biped's 1 leg
      lost; 3 legs destroyed is the death threshold (see is_destroyed). A
      quad with exactly 1 leg destroyed does NOT hit the flat-1 case - that
      single destroyed leg instead contributes a flat -1 to the accumulated
      actuator penalty below (RAW: "a -1 MP penalty replaces any penalties
      associated with damaged leg actuators in the destroyed leg") rather
      than counting its individual actuator hits.
    - Otherwise (no leg destroyed forcing the flat-1 case): walking MP is
      base_walk_mp minus 1 per destroyed leg actuator slot (Hip/Upper Leg
      Actuator/Lower Leg Actuator/Foot Actuator - Daniel's house rule, no
      Hip-halves-MP RAW special case), summed across all non-destroyed legs.
    - Floor of 1 always (Daniel, 2026-07-12: confirmed as the deliberate
      choice, not a RAW deviation worth correcting - "functionally the same
      for our purposes").
    - Heat (2026-10-19): mech.heat_mp_penalty (Heat Scale, set by
      INTEGRATION__heat) comes off AFTER the damage floor, and can take
      Walking MP to 0 - Core Rulebook p.104: "A 'Mech can be reduced to 0
      ground movement MP in this fashion". Jumping MP is unaffected.
    TSM (2026-10-19, Core p.205): +2 Walking MP while mech.tsm_active,
    added before the heat penalty comes off.
    """
    return max(0, _damage_walk_mp(mech) + (2 if mech.tsm_active else 0) - mech.heat_mp_penalty)


def _damage_walk_mp(mech):
    """compute_walk_mp before heat: leg damage only, floor 1."""
    destroyed_legs = [loc for loc in mech.leg_locations if mech.locations[loc]["destroyed"]]
    is_quad = mech.mech_type in ("quad", "quadvee")
    effective_destroyed = max(0, len(destroyed_legs) - (1 if is_quad else 0))

    if effective_destroyed >= 1:
        return 1

    penalty = 0
    for loc in mech.leg_locations:
        if loc in destroyed_legs:
            # Only reachable here for a quad with exactly 1 leg destroyed
            # (effective_destroyed == 0 in that case) - flat -1 replaces that
            # leg's own actuator count per the RAW quote above.
            penalty += 1
        else:
            penalty += mech.destroyed_leg_actuators.get(loc, 0)

    return max(1, mech.base_walk_mp - penalty)


# HELP(running_mp.hardened_leg_penalty)
def compute_running_mp(mech):
    """Current effective running MP: ceil(compute_walk_mp(mech) * 1.5), same
    convention as the vehicle sim's flank_mp, minus 1 (floor 1) if Hardened
    armor is present on ANY leg location (Daniel, 2026-07-15: "any leg", and
    the armor_type tag still counts even if that leg is destroyed - checked
    against mech.armor_type, not gated on mech.locations[loc]["destroyed"]).

    Computed off compute_walk_mp's CURRENT (damage-adjusted) value each call,
    not a cached/stored field - so it stays in sync as walk MP changes from
    leg actuator damage over the course of a fight. Not stored on the mech
    object; called fresh wherever running MP is needed (currently only
    damage_resolution.compute_tmm)."""
    running_mp = math.ceil(compute_walk_mp(mech) * mech.run_mp_multiplier)  # 1.5 unless MASC/supercharger

    # running_mp > 0 guard (2026-10-19): heat can take Walking MP to 0, and
    # the Hardened floor of 1 must not hand that mech a Running MP back.
    if running_mp > 0 and any(mech.armor_type.get(loc) == ArmorType.HARDENED for loc in mech.leg_locations):
        running_mp = max(1, running_mp - 1)

    return running_mp


def compute_jump_mp(mech):
    """Current effective jump MP: base_jump_mp minus 1 per DISTINCT jump-jet
    Equipment instance that's had at least one crit slot destroyed (tracked
    incrementally in destroyed_jump_jet_ids - see that field's docstring and
    HELP(jump_jet.hardcoded_name_match) in damage_resolution.py), plus the
    Partial Wing bonus if applicable. No floor below 0 - a mech that's lost
    all its jump jets simply can't jump.

    # HELP(partial_wing.mp_bonus)
    Partial Wing bonus (Daniel, 2026-07-14): +1 MP if mech.mass >= 60,
    +2 MP if mech.mass < 60 - not independently re-derived/verified against
    the rulebook here, taken as given. Only applies if mech.partial_wing_active
    (mtf-detected and not yet crit-disabled - see mech_state.BattleMech.__init__)
    AND the jet-only total above is already > 0 - Daniel: "If somehow the
    base jump mp=0, then the bonus = zero too" (Partial Wing amplifies
    existing jump capability, it doesn't grant jumping from nothing)."""
    jet_mp = max(0, mech.base_jump_mp - len(mech.destroyed_jump_jet_ids))
    if jet_mp == 0 or not mech.partial_wing_active:
        return jet_mp
    return jet_mp + (1 if mech.mass >= 60 else 2)


def compute_heat_dissipation(mech):
    """Current effective heat dissipation: (base_heat_sinks - destroyed units)
    * per-sink rate. Rate is 2 for Double and Laser heat sinks, 1 for
    everything else (Single, Compact) - see
    HELP(heat_sink.hardcoded_name_match) in damage_resolution.py for the
    same substring-match approach used to detect heat sinks in the first
    place. The whole mech is assumed uniform-type per the single .mtf
    header line (mech.heat_sink_type), not re-derived per destroyed
    instance.

    destroyed_heat_sinks is a dict of id(instance) -> units (not a bare
    count), since a destroyed "2 Compact Heat Sinks" equipment.json entry
    represents 2 physical heat sinks lost in a single instance - see that
    field's docstring. sum() over .values() gives total destroyed units
    regardless of how many distinct instances that spans.

    No floor logic needed beyond max(0, ...) - a mech that's lost every
    heat sink simply dissipates nothing, same "can't go negative" shape as
    compute_jump_mp.

    Radical Heat Sink System is never included here - excluded entirely by
    is_heat_sink() (Daniel, 2026-08-04: it's activatable risk-bearing
    equipment, not a passive dissipation source, and is not wired in at
    all yet).

    Partial Wing (2026-10-19, Core Rulebook p.103): a working Partial Wing
    dissipates 3 more heat points per turn, whether or not the mech jumped.
    Deactivated heat sinks (2026-10-19, Core p.103) dissipate nothing."""
    sinks = active_heat_sinks(mech) * heat_sink_rate(mech)
    return sinks + (3 if mech.partial_wing_active else 0)


def heat_sink_rate(mech):
    """Heat points one sink dissipates: 2 for Double/Laser, 1 otherwise."""
    return 2 if any(word in mech.heat_sink_type.replace(" ", "").upper()
                    for word in ("DOUBLE", "LASER")) else 1


def working_heat_sinks(mech):
    """Heat sinks not destroyed (switched on or off)."""
    return max(0, mech.base_heat_sinks - sum(mech.destroyed_heat_sinks.values()))


def active_heat_sinks(mech):
    """Heat sinks not destroyed and not deactivated - the ones coolant pods
    and radical heat sinks boost by 1 each (Core p.208)."""
    return max(0, working_heat_sinks(mech) - mech.deactivated_heat_sinks)


# HELP(mechanical_jump_booster.all_or_nothing_flag)
def compute_mechanical_jump_booster_mp(mech):
    """All-or-nothing: full base_mechanical_jump_booster_mp until any slot
    of the system is crit, then 0 forever (mech.mechanical_jump_booster_disabled
    flag - not instance-id tracking like compute_jump_mp, since any hit
    anywhere on this mech-wide-distributed system takes out the whole thing).
    See DESIGN_NOTES_mech.md#mechanical_jump_booster for the full design."""
    if mech.mechanical_jump_booster_disabled:
        return 0
    return mech.base_mechanical_jump_booster_mp


def display_crits(mech, location):
    return [s.name if isinstance(s, Equipment) else s for s in mech.crits[location]]
