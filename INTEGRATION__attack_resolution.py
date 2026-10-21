"""
INTEGRATION__attack_resolution.py  (NEW 2026-10-18, Claude - Pile 2 resolution driven by Pile 3 geometry)

The Ranged Combat phase with real dice: the seam PROJECT_MAP Section 2
calls "the main seam this project exists to close" -
PATHFINDER los/combat (to-hit) -> MECHSIM hit_location/damage_resolution/
armor_rules (resolution).

Cannibalized from MECHSIM__sim_runner.py (per the 2026-08-30 Pile 1
reconciliation decision):
  - _resolve_hit()           -> _resolve_hit() here, unchanged logic, except
                                the hit-table side comes from
                                attack_side() (Core p.73 attack direction)
                                instead of config.FACING (the TAC re-roll
                                uses the same side as the original hit).
  - resolve_weapon_attack()  -> _resolve_one_attack() here. To-hit number now
                                comes from real geometry instead of
                                config.GUNNERY + to_hit_modifier + tmm; weapon
                                data comes from the parsed Equipment instance
                                instead of a hand-written ATTACK_TABLE row.
sim_runner.py itself is not imported.

=== SEQUENCE (PROJECT_MAP Section 2 step 4) ===
"Loser fires first, winner second; effects resolve simultaneously."
  1. snapshot_round_capability + snapshot_pre_attack_phase for both mechs.
  2. DECLARE both sides' attacks from the pre-damage state: LOS, rear-arc
     firing block, to-hit number, weapon selection (heat-constrained
     knapsack, INTEGRATION__weapon_selection - budget = max_heat +
     dissipation - current heat - this turn's movement heat - engine
     heat, Daniel 2026-10-18), and the to-hit roll for each
     chosen weapon. Because both declare before any damage lands, a mech
     destroyed this phase still gets its shots off (simultaneous).
  3. APPLY: loser's hits land first, then winner's (only matters for log
     order and crit-slot state, not for who gets to fire).
  4. Attack Phase PSR + consciousness checks for both (MECHSIM, real).

=== TO-HIT NUMBER ===
TN = gunnery + AMM(attacker's actual movement mode)
              + TMM(target's actual hexes moved; +1 if it jumped)
              + LOS modifier (woods/partial cover) + range bracket
              + attacker's heat modifier (2026-10-19, Heat Scale: +1 at 8,
                +2 at 13, +3 at 17, +4 at 24 - INTEGRATION__heat)
All pieces but heat are Daniel-confirmed PATHFINDER rules; heat is Core
Rulebook p.104. TMM uses ACTUAL hexes
moved (combat.fc_to_tmm), per Daniel 2026-10-18 - MECHSIM's
compute_tmm() (max available MP) is NOT used here.
Exception: an immobile target (whole crew unconscious, or shut down -
mech_state.is_immobile) uses MECHSIM's existing "TMM -4" convention
(piloting_rolls.resolve_movement_phase).
A shut-down attacker makes no attacks (Core Rulebook p.104).
The range term includes the minimum-range penalty (2026-10-19,
weapon_selection._weapon_range_mod).
Also (2026-10-19, replacing stub_to_hit_modifiers_not_applied):
  - each weapon's own modifier (INTEGRATION__weapon_rules: pulse -2, ER pulse
    -1, heavy laser +1, rocket launcher +1, ...) and a targeting computer's
    -1 for eligible weapons (p.200);
  - arm critical hits (p.97-98): shoulder +4 for that arm's weapons
    (overriding its other arm crits), upper arm actuator +1;
  - sensor hits (p.98): one +2, two = no ranged attacks (torso-mounted
    cockpit p.203: +2, +4, then none);
  - prone target (p.66): -2 from an adjacent hex, +1 otherwise;
  - firing while prone (p.67): +2, propped on the arm whose weapons matter
    least - nothing fires from that arm or the legs; no arm left = no fire.
    Tripods with no leg / hip damage +1 and only lose leg weapons; quads with
    none fire as if standing, damaged quads prop on a leg (p.231).

Stealth (2026-10-19, INTEGRATION__equipment_systems, Core pp.202, 209):
a target's active LPS / Null-Signature / stealth armor add +1 at medium and
+2 at long range to each weapon's TN; its Void-Signature System adds +3 to
+0 by how far it moved; the attacker's own Void-Signature adds +1.

AIMED SHOTS (2026-10-19, Core p.70): against an immobile target, every
eligible weapon (not Cluster / Area-Effect - so no LRM/SRM racks) aims at
config.AIMED_SHOT_LOCATION. Aiming at the head drops the -4 immobile
modifier and adds +3 instead; partial cover's modifier doesn't apply to an
aimed shot, legs can't be aimed at behind it, and a missed aim that rolls
a leg rerolls. A hit then rolls 1D6: 4+ strikes the aimed location,
otherwise the normal hit-location roll.

ANTI-MISSILE SYSTEMS (2026-10-20, Core p.206, rules in INTEGRATION__ams): once
both sides have declared, each defender's AMS engage the missile hits against
it (attack.ams); an engaged hit rolls its Cluster Hits roll at -4 (below 2: no
damage), a Streak counts as a 7, a single missile dies on 1D6 4+. The AMS heat
lands on the defender's weapon heat. Weapon choice prices the target's AMS in
(ams.damage_factors as value_scale).

For weapon SELECTION the pre-range TN is clamped into
weapon_selection's table bounds (0-16); the actual to-hit ROLL uses the
real, unclamped TN.
"""

from dataclasses import dataclass, field
from typing import List, Optional

import INTEGRATION__config as config
import INTEGRATION__stubs as stubs
import INTEGRATION__weapon_selection as weapon_selection
import INTEGRATION__heat as heat
import INTEGRATION__equipment_systems as equip
import INTEGRATION__weapon_rules as weapon_rules
import INTEGRATION__arcs as arcs
import INTEGRATION__clubs as clubs
import INTEGRATION__ammo as ammo
import INTEGRATION__ams as ams
import INTEGRATION__electronics as electronics
import INTEGRATION__fire_modes as fire_modes
import INTEGRATION__physical_gear as gear  # noqa: E402 - shields, p.195
import INTEGRATION__weapon_profiles as weapon_profiles
import INTEGRATION__timing as timing
import INTEGRATION__water as water
from mech_state import pilot_hit, head_hit_hurts_pilot, tripod_gunner_modifier, is_destroyed  # noqa: E402 - pp.203, 236
from mech_state import DamageType, ArmorType, is_immobile, snapshot_round_capability, \
    mark_consciousness_check_pending, compute_heat_dissipation, arm_aes_working
import armor_rules
from hit_location import resolve_hit_location
from damage_resolution import apply_damage, check_critical, cluster_hits_count, get_weapons, TRANSFER_MAP
import piloting_rolls

import hex_geometry
import combat
from los import hex_distance, trace_los_path, STANDING_HEIGHT, PRONE_HEIGHT

# equipment.json damage_type strings -> MECHSIM DamageType. A name mapping,
# not a rule. Anything else (incl. null) goes through stub_unknown_damage_type.
DAMAGE_TYPE_BY_NAME = {
    "Energy": DamageType.ENERGY,
    "Ballistic": DamageType.BALLISTIC,
    "Missile": DamageType.MISSILE,
}

IMMOBILE_TMM = -4  # MECHSIM piloting_rolls.resolve_movement_phase convention (immobile target)
KICK = "kick"                          # DeclaredAttack.cover: hits use the Kick Location Table (pp.67, 127)
AIMED_HEAD_ADJUST = -IMMOBILE_TMM + 3  # p.70: head shots drop the -4 and take +3 instead
AIMED_SHOT_SUCCESS = 4                 # 1D6 4+ hits the aimed location


@dataclass
class DeclaredAttack:
    weapon: object
    tn: int
    roll: int
    hit: bool
    side: str = "front"              # hit table: attack direction (attack_side)
    aimed_at: Optional[str] = None   # aimed-shot location (immobile target)
    cover: object = False            # True: partial cover, leg hits strike it (p.66); KICK: legs only (p.67)
    ams: object = None               # the target's AMS engaging this hit (p.206, INTEGRATION__ams)
    apds: object = None              # ... and / or its APDS (p.206, 2026-10-21)
    fire: object = None              # fire_modes.ShotPlan: ammunition, Artemis / Narc, rapid fire, Apollo
    pod_value: float = 0.0           # Narc beacon: the homing pod's worth (electronics.pod_value)


@dataclass
class SideReport:
    """What one mech did this phase - feeds BattleResult totals."""
    attacks: int = 0
    hits: int = 0
    damage_dealt: float = 0.0
    weapon_heat: int = 0
    attacks_list: List[DeclaredAttack] = field(default_factory=list)


def total_hp(mech):
    """Daniel's HP scalar (PROJECT_MAP Section 5): armor + rear armor + structure."""
    return sum(v.get("armor", 0) + v.get("rear_armor", 0) + v.get("structure", 0)
               for v in mech.locations.values())


def _with_piloting(mech, fn, *args, **kwargs):
    """piloting_rolls.py reads one global config.PILOTING; set it to this
    mech's own skill for the duration of the call (no MECHSIM edit)."""
    saved = config.PILOTING
    config.PILOTING = mech.piloting
    try:
        return fn(mech, *args, **kwargs)
    finally:
        config.PILOTING = saved


def _target_tmm(target):
    if is_immobile(target):
        return IMMOBILE_TMM
    return combat.fc_to_tmm(target.move_fc, jumped=(target.move_mode == "Jump"))


_SIDE_BY_RELATIVE_HEXSIDE = {0: "front", 1: "right", 2: "right", 3: "rear", 4: "left", 5: "left"}


def los_height(mech):
    """A 'Mech's height for line of sight (p.57): 2 standing, 1 prone."""
    return PRONE_HEIGHT if mech.prone else STANDING_HEIGHT


def attack_side(a_hex, t_hex, target_facing, terrain_map, a_height=STANDING_HEIGHT, t_height=STANDING_HEIGHT):
    """Attack direction (Core p.73): the hexside of the target's hex that
    the line of sight crosses, read against the target's facing (a prone
    mech uses the same facing). Front and rear hit zones are one hexside
    each, the sides two each (Attack Direction Diagram). A line exactly on
    a border uses the hex the LOS rules chose (los.trace_los_path)."""
    steps = trace_los_path(a_hex, t_hex, terrain_map, a_height, t_height).steps
    entry = steps[-2].hex                      # the hex the line enters the target's hex from
    relative = (combat._direction_facing(t_hex, entry) - target_facing) % 6
    return _SIDE_BY_RELATIVE_HEXSIDE[relative]


def is_cluster_weapon(weapon):
    """Rolls on the Cluster Hits Table (INTEGRATION__weapon_rules)."""
    return weapon_rules.is_cluster(weapon)


def aimed_shot_location(target, partial_cover=False):
    """Where aimed shots at `target` go this phase (p.70), or None: only at
    an immobile target, only if config.AIMED_SHOT_LOCATION names one of its
    live locations, and not at a leg behind partial cover."""
    loc = config.AIMED_SHOT_LOCATION
    if loc is None or not is_immobile(target) or loc not in target.locations:
        return None
    if target.locations[loc]["destroyed"] or (partial_cover and loc in target.leg_locations):
        return None
    return loc


def aimed_tn_adjust(aim, cover_modifier):
    """TN change for an aimed shot: no partial-cover modifier; head +7."""
    return -cover_modifier + (AIMED_HEAD_ADJUST if aim == "Head" else 0)


# --- Attacker / target conditions (2026-10-19) --------------------------------
ARM_LOCATIONS = ("Left Arm", "Right Arm")
SENSOR_MODIFIER_BY_HITS = {0: 0, 1: 2}                    # p.98; 2+ hits: no ranged attacks
TORSO_COCKPIT_SENSOR_MODIFIER_BY_HITS = {0: 0, 1: 2, 2: 4}  # p.203; 3+ hits: none
PRONE_FIRE_MODIFIER = 2                                   # p.67
TRIPOD_PRONE_FIRE_MODIFIER = 1                            # p.231
PRONE_TARGET_ADJACENT = -2                                # p.66
PRONE_TARGET_FAR = 1


def weapon_locations(mech):
    """{id(weapon): set of locations its slots sit in} - live and destroyed slots."""
    locs = {}
    for location, slots in mech.crits.items():
        for slot in slots:
            if getattr(slot, "category", None) == "weapon":
                locs.setdefault(id(slot), set()).add(location)
    for (location, _), info in mech.destroyed_slot_info.items():
        if info["instance_id"] is not None:
            locs.setdefault(info["instance_id"], set()).add(location)
    return locs


def _destroyed_names(mech, location=None):
    return [info["name"] for (loc, _), info in mech.destroyed_slot_info.items()
            if location is None or loc == location]


def sensor_modifier(mech):
    """Ranged-attack TN modifier from sensor hits, or None if they can't fire."""
    hits = _destroyed_names(mech).count("Sensors")
    table = TORSO_COCKPIT_SENSOR_MODIFIER_BY_HITS if getattr(mech, "torso_cockpit", False) \
        else SENSOR_MODIFIER_BY_HITS
    return table.get(hits)


def arm_actuator_modifier(mech, locations):
    """+4 for a weapon in an arm with a destroyed shoulder (overrides that
    arm's other crits), else +1 for a destroyed upper arm actuator."""
    worst = 0
    for arm in set(locations) & set(ARM_LOCATIONS):
        lost = _destroyed_names(mech, arm)
        worst = max(worst, 4 if "Shoulder" in lost else (1 if "Upper Arm Actuator" in lost else 0))
    return worst


def arm_aes_modifier(mech, locations):
    """-1 for a weapon mounted in an arm with working AES (Core p.206); a
    weapon split between an arm and a torso gets no bonus."""
    locations = set(locations)
    if len(locations) == 1 and locations <= set(ARM_LOCATIONS) and arm_aes_working(mech, next(iter(locations))):
        return -1
    return 0


def has_targeting_computer(mech):
    dead = {info["instance_id"] for info in mech.destroyed_slot_info.values()}
    return any(getattr(s, "name", "").replace(" ", "").upper().endswith("TARGETINGCOMPUTER") and id(s) not in dead
               for slots in mech.crits.values() for s in slots)


def prone_target_modifier(target, distance):
    if not target.prone:
        return 0
    return PRONE_TARGET_ADJACENT if distance <= 1 else PRONE_TARGET_FAR


def _weapon_value(weapon):
    if weapon_rules.is_ams(weapon):
        return 0                     # never fires as a weapon (p.206)
    return (weapon.damage_per_shot or 0) * (weapon.rack_size or 1)


def prone_fire(mech):
    """(TN modifier, ids of weapons that can't fire), or None if a prone mech
    can't fire at all (p.67, p.231). (0, empty) when standing."""
    if not mech.prone:
        return 0, frozenset()
    locs = weapon_locations(mech)
    weapons = get_weapons(mech)
    in_loc = lambda place: {id(w) for w in weapons if place & locs.get(id(w), set())}   # noqa: E731
    legs = set(mech.leg_locations)
    legs_ok = not mech.destroyed_hip_locations and not any(mech.locations[l]["destroyed"] for l in legs)
    if mech.mech_type in ("quad", "quadvee"):
        if legs_ok:
            return 0, frozenset()
        usable = [l for l in legs if not mech.locations[l]["destroyed"]]
        prop = min(usable, key=lambda l: sum(_weapon_value(w) for w in weapons if id(w) in in_loc({l})))
        return PRONE_FIRE_MODIFIER, frozenset(in_loc({prop}))
    if mech.mech_type == "tripod" and legs_ok:
        return TRIPOD_PRONE_FIRE_MODIFIER, frozenset(in_loc(legs))
    arms = [a for a in ARM_LOCATIONS if a in mech.locations and not mech.locations[a]["destroyed"]]
    if not arms:
        return None
    prop = min(arms, key=lambda a: sum(_weapon_value(w) for w in weapons if id(w) in in_loc({a})))
    return PRONE_FIRE_MODIFIER, frozenset(in_loc(legs | {prop}))


def arc_unavailable(attacker, key):
    """Ids of weapons that can't bear on a target seen as `key` (an
    INTEGRATION__arcs.ArcKey: the twisted torso's arc, which legs see it
    forward, flipped arms, turret) - Core pp.60-62, rules in INTEGRATION__arcs."""
    return arcs.unavailable(attacker, get_weapons(attacker), weapon_locations(attacker), key)


def firing_conditions(attacker):
    """Attacker-side ranged conditions: (TN modifier, unavailable weapon ids,
    note), or None if it can't make ranged attacks this turn."""
    sensors = sensor_modifier(attacker)
    prone = prone_fire(attacker)
    if sensors is None or prone is None:
        return None
    note = []
    if sensors:
        note.append(f"sensors +{sensors}")
    if prone[0] or prone[1]:
        note.append(f"prone +{prone[0]}")
    gunner = tripod_gunner_modifier(attacker)       # a tripod's gunnery officer disabled, p.236
    if gunner:
        note.append(f"tripod gunner out +{gunner}")
    return sensors + prone[0] + gunner, prone[1], ", ".join(note)


def tn_adjuster(attacker, target, aim=None, cover_modifier=0):
    """f(weapon, bracket, plan=None) -> per-weapon TN change for
    select_weapons_to_fire: the weapon's own modifier, targeting computer, arm
    crits, arm AES (p.206), the target's range-stealth bonus, and the aimed-shot change for
    weapons that can aim. With a fire_modes.ShotPlan (2026-10-20), aiming and
    the targeting computer follow the plan (no aimed rapid fire or LB-X cluster
    shot, no TC for cluster rounds); the plan's own TN change (Artemis V, Narc,
    LB-X cluster) is added by fire_modes, not here."""
    stealth = equip.range_stealth_bonus(target)
    aim_adjust = aimed_tn_adjust(aim, cover_modifier) if aim else 0
    tc = has_targeting_computer(attacker)
    locs = weapon_locations(attacker)

    def adjust(weapon, bracket, plan=None):
        tn = stealth.get(bracket, 0) if bracket else 0
        tn += weapon_rules.weapon_tn_modifier(weapon, bracket)
        tn += arm_actuator_modifier(attacker, locs.get(id(weapon), ()))
        tn += arm_aes_modifier(attacker, locs.get(id(weapon), ()))
        aiming = aim and (fire_modes.aimable(weapon, plan) if plan is not None else not is_cluster_weapon(weapon))
        if aiming:
            tn += aim_adjust
        # TC -1 (p.200): not on head shots, nor on a pulse weapon's aimed shot.
        eligible = fire_modes.tc_eligible(weapon, plan) if plan is not None else \
            weapon_rules.targeting_computer_eligible(weapon)
        if tc and eligible and not (aiming and (aim == "Head" or weapon_rules.is_pulse(weapon))):
            tn -= 1
        return tn
    return adjust


def _physical_planner(attacker, target, terrain_map):
    """f(ArcAction) -> physical.plans for an attack on the adjacent target
    later this turn (nothing fired yet), or None if the attacker can't make
    one (prone, immobile)."""
    import INTEGRATION__physical as physical      # physical imports this module
    if attacker.prone or is_immobile(attacker):
        return None
    base = physical._base_tn(attacker, target, terrain_map)
    a_hex, t_hex = hex_geometry.parse_hex_label(attacker.hex), hex_geometry.parse_hex_label(target.hex)
    a_facing = hex_geometry.compass_to_facing(attacker.facing)
    a_level, t_level = terrain_map["hexes"][attacker.hex]["level"], terrain_map["hexes"][target.hex]["level"]

    planner = physical.Planner(attacker)
    t_water = water.state(target, terrain_map)
    allowed = water.physical_allowed(water.state(attacker, terrain_map), t_water)  # p.77

    push = planner.push_plan(a_hex, a_facing, a_level, target, target.hex, t_level, base, "front", terrain_map)
    if allowed is not None and "push" not in allowed:
        push = []

    def plans_for(action):
        got = planner.plans(a_hex, a_facing, a_level, t_hex, t_level, target.prone, action, base,
                            allowed=allowed, t_water=t_water) or [(0.0, (), [])]
        return got + push if push and not action.flip else got
    return plans_for


def declare_attacks(attacker, target, terrain_map, report: SideReport):
    """Step 2 above for one attacker. Rolls to-hit for every selected
    weapon; returns nothing (fills report)."""
    import INTEGRATION__physical as physical      # physical imports this module
    a_name, t_name = attacker.side_name, target.side_name
    if attacker.shutdown:
        config.log(f"  [Ranged] {a_name}: shut down - no attacks.")
        return
    if getattr(attacker, "charging", None) is not None or getattr(attacker, "dfa", None) is not None:
        what = "charging" if getattr(attacker, "charging", None) is not None else "in a death from above on"
        config.log(f"  [Ranged] {a_name}: {what} {t_name} - no ranged attacks this turn (pp.78-79).")
        return
    a_hex = hex_geometry.parse_hex_label(attacker.hex)
    t_hex = hex_geometry.parse_hex_label(target.hex)
    if a_hex == t_hex:
        config.log(f"  [Ranged] {a_name}: same hex as target - no attack (undefined).")
        return

    stubs.stub_unconfirmed_weapon_data(a_name, get_weapons(attacker))

    heights = (los_height(attacker), los_height(target))          # prone: 1 level (p.57)
    trace = trace_los_path(a_hex, t_hex, terrain_map, *heights)
    los = trace.result
    cover = trace.steps[-1].partial_cover      # partial cover (p.66): leg hits strike the cover
    if not los.los:
        config.log(f"  [Ranged] {a_name}: no LOS to {t_name} - holds fire.")
        return
    a_facing = hex_geometry.compass_to_facing(attacker.facing)
    pair_arcs = arcs.arcs_between(a_hex, t_hex)
    arc_choices = arcs.arc_keys(pair_arcs, a_facing, arcs.arc_options(attacker), arcs.leg_offsets(attacker))
    if all(len(arc_unavailable(attacker, key)) == len(get_weapons(attacker)) for key, _ in arc_choices):
        config.log(f"  [Ranged] {a_name}: no weapon can bear on {t_name} "
                   f"({arcs.ARC_NAMES[pair_arcs[a_facing]]} arc) - can't fire.")
        return

    distance = hex_distance(a_hex, t_hex)
    amm = combat.MODE_TO_AMM[attacker.move_mode]
    tmm = _target_tmm(target)
    heat_mod = attacker.heat_fire_modifier
    stealth_mod = equip.void_signature_modifier(target) + equip.own_attack_modifier(attacker)
    conditions = firing_conditions(attacker)
    if conditions is None:
        config.log(f"  [Ranged] {a_name}: can't make ranged attacks (sensors destroyed, or prone with no arm to prop on).")
        return
    cond_mod, unavailable, cond_note = conditions
    unavailable = (unavailable | ammo.unavailable_weapons(attacker) | fire_modes.jammed_ids(attacker)
                   | weapon_profiles.array_gun_ids(attacker) | shielded_weapon_ids(attacker))
    # Water (2026-10-21, INTEGRATION__water, pp.62, 67, 127): attacks can't cross
    # the water line; from depth 1 only some weapons can bear; only energy weapons
    # fire from a submerged location.
    a_water, t_water = water.state(attacker, terrain_map), water.state(target, terrain_map)
    w_locs = weapon_locations(attacker)
    water_blocked = water.blocked_weapon_ids(attacker, get_weapons(attacker), w_locs, a_water, t_water)
    if water_blocked is None:
        config.log(f"  [Ranged] {a_name} ({a_water}) can't attack {t_name} ({t_water}) "
                   f"across the water line (p.62) - holds fire.")
        return
    unavailable = unavailable | water_blocked
    # Legs-only hits on a 'Mech standing in depth 1 (pp.67, 127): the Kick table, not partial cover.
    kick_ids = water.kick_table_weapon_ids(attacker, get_weapons(attacker), w_locs, a_water, t_water)
    prone_mod = prone_target_modifier(target, distance)
    other_mod = cond_mod + prone_mod
    pre_tn = attacker.gunnery + amm + tmm + los.modifier + heat_mod + stealth_mod + other_mod

    aim = None
    if is_immobile(target) and config.AIMED_SHOT_LOCATION:
        aim = aimed_shot_location(target, partial_cover=cover > 0)
    adjust = water.range_adjuster(attacker, w_locs, a_water, tn_adjuster(attacker, target, aim, cover))
    side = attack_side(a_hex, t_hex, hex_geometry.compass_to_facing(target.facing), terrain_map, *heights)
    sel_pre_tn = max(weapon_selection.PRE_TN_MIN, min(weapon_selection.PRE_TN_MAX, pre_tn))
    # Special weapons (missiles, rapid fire, LB-X, MML, ATM, Narc) are priced by a fire_modes
    # Planner (2026-10-20): the ammunition / rate the stubs would pick, Artemis / Narc / ECM,
    # the target's AMS share (p.206) and a Narc pod's worth (Daniel).
    usable = [w for w in get_weapons(attacker) if id(w) not in unavailable]
    k = ams.engagement_capacity(target, ams.covering(target, a_hex)) if ams.can_engage(target) else 0
    pod_values = {}
    if any(electronics.is_narc(w) for w in usable):
        worth = electronics.pod_value(attacker, target, distance, sel_pre_tn, adjust)
        pod_values = {id(w): worth for w in usable if electronics.is_narc(w)}
    # An attack on the target's hex (Apollo saturation, Arrow IV) takes none of the target's
    # modifiers (Daniel 2026-10-20: no TMM, not even the immobile -4).
    hex_offset = -(tmm + prone_mod + equip.void_signature_modifier(target))
    planner = fire_modes.Planner(attacker, target, adjust, fire_modes.ams_share(k, usable), pod_values, hex_offset)

    dissipation = compute_heat_dissipation(attacker) + water.dissipation_bonus(attacker)
    other = heat.other_heat(attacker)
    # Torso twist / arm flip / turret (pp.61-62): declared with the attacks, so try each
    # one the mech may make and keep the one with the most expected damage; no change wins ties.
    # Next to the target the choice also counts the physical attack that can follow (pp.76, 82):
    # the twist stands for the Physical phase, and a limb that punches or kicks can't have
    # fired - so each (action, physical plan) is scored as ranged + physical expected damage.
    plans_for = _physical_planner(attacker, target, terrain_map) if distance == 1 else None
    actions = arcs.arc_options(attacker) if plans_for else tuple(a for _, a in arc_choices)
    legs = arcs.leg_offsets(attacker)
    picked_cache = {}
    best = None
    for action in actions:
        key = arcs.key_for(pair_arcs, a_facing, action, legs)
        for phys_value, limbs, phys_picks in (plans_for(action) if plans_for else ((0.0, (), []),)):
            held = physical.limb_weapon_ids(attacker, limbs) if limbs else frozenset()
            picked = picked_cache.get((key, held))
            if picked is None:
                picked = picked_cache[(key, held)] = weapon_selection.select_weapons_to_fire(
                    attacker, distance, sel_pre_tn, attacker.min_heat, attacker.max_heat,
                    dissipation=dissipation, movement_heat=attacker.movement_heat, other_heat=other,
                    tn_adjust=adjust, unavailable=unavailable | arc_unavailable(attacker, key) | held,
                    planner=planner)
            total = picked[1] + phys_value
            if best is None or total > best[0] + 1e-12:
                best = (total, picked, key, action, phys_picks, phys_value, held)
    _, (weapons, exp_dmg, weapon_heat), chosen_key, chosen, phys_picks, phys_value, held = best
    if not weapons:
        chosen = arcs.current_action(attacker)._replace(turret=chosen.turret)   # nothing fires: declare no change
    arcs.declare(attacker, chosen)
    if arcs.describe(chosen) and weapons:
        config.log(f"  [Ranged] {a_name} {arcs.describe(chosen)} "
                   f"({t_name} is in its torso's {arcs.ARC_NAMES[chosen_key.torso_arc]} arc after that).")
    held_names = sorted({w.name for w in get_weapons(attacker)
                         if id(w) in held - unavailable and not weapon_rules.is_ams(w)})
    if phys_picks and held_names:
        config.log(f"  [Ranged] {a_name} holds {held_names} back for the Physical phase "
                   f"(plans {', '.join(o['name'] for o in phys_picks)}, expected {phys_value:.2f}).")
    budget = heat.weapon_heat_budget(attacker, attacker.movement_heat)
    surcharge = heat.weapon_fire_surcharge(attacker) if weapons else 0

    config.log(f"  [Ranged] {a_name} -> {t_name}: range {distance}, base TN {pre_tn} "
               f"(gunnery {attacker.gunnery} + AMM {amm} [{attacker.move_mode}] + TMM {tmm} "
               f"+ LOS {los.modifier} + heat {heat_mod}{f' + stealth {stealth_mod}' if stealth_mod else ''}"
               f"{f' + {cond_note}' if cond_note else ''}{f' + prone target {prone_mod}' if prone_mod else ''}); "
               f"firing {[w.name for w in weapons] or 'nothing'}{f' (aimed at {aim})' if aim else ''} "
               f"(weapon heat {weapon_heat}{f' +{surcharge} damaged radical' if surcharge else ''} of budget "
               f"{budget} = max {attacker.max_heat} + sink {dissipation} - current {attacker.current_heat} "
               f"- movement {attacker.movement_heat} - other {other}; expected dmg {exp_dmg:.2f})")
    # The decisions themselves (stubs warn here): each special weapon's ammunition / rate.
    plans = {id(w): planner.declare(w, distance, sel_pre_tn) for w in weapons if fire_modes.special(w)}
    electronics.log_controls(a_name, plans, weapons)

    report.weapon_heat += weapon_heat + surcharge
    for w in weapons:
        # Ammo is marked off at declaration - except Streaks, only on a hit (p.72, p.187) -
        # from a bin of the chosen munition; if none is left the shot is what the bin fired.
        plan = plans.get(id(w), fire_modes.PLAIN)
        ammo_note = ""
        if weapon_profiles.is_mga(w):         # an array: one round from each machine gun it fires
            ammo_note = fire_modes.take_array_rounds(attacker, w, plan.shots)
        elif not weapon_rules.is_streak(w):
            kind = None if not fire_modes.special(w) or plan.kind in weapon_profiles.BOMBAST \
                or plan.kind in ("saturation", "artillery") else plan.kind
            notes = [ammo.take(attacker, w, plan.munition, kind) for _ in range(plan.shots)]
            ammo_note = notes[-1][0]
        if fire_modes.special(w) and plan.hex_attack:
            range_mod = fire_modes.range_mod(w, plan, distance)
            extra = hex_offset + adjust(w, None, plan) + plan.tn
        elif fire_modes.special(w):
            range_mod = fire_modes.range_mod(w, plan, distance)
            extra = adjust(w, fire_modes.bracket(w, plan, distance), plan) + plan.tn + fire_modes.area_immobile_fix(w, target)
        else:
            range_mod = weapon_selection._weapon_range_mod(w, distance)
            extra = adjust(w, weapon_selection.range_bracket(w, distance))
        w_aim = aim if aim and fire_modes.aimable(w, plan) else None
        if id(w) in kick_ids:
            extra -= cover                     # p.67: "this does not count as partial cover"
            w_aim = None                       # it can only hit the legs, by the Kick table
        tn = pre_tn + range_mod + extra
        roll = config.roll_2d6(prompt=f"To-hit roll ({w.name})")
        hit = roll >= tn
        config.log(f"    {w.name}{f' x{plan.shots}' if plan.shots > 1 else ''}: needs {tn} (range mod +{range_mod}"
                   f"{f', modifiers {extra:+d}' if extra else ''}){f' aimed at {w_aim}' if w_aim else ''}, "
                   f"rolled {roll} -> {'HIT' if hit else 'miss'}{f' [{ammo_note}]' if ammo_note else ''}")
        jam_at = fire_modes.jam_threshold(plan) if fire_modes.is_rotary(w) else 0
        if roll <= jam_at:
            w.jammed = True
            config.log(f"      {w.name} JAMS (roll {roll} with {plan.shots} shots, p.183) - the shots still fire.")
        if weapon_rules.is_streak(w):
            if hit:
                note = ammo.spend(attacker, w)
                if note:
                    config.log(f"      [{note}]")
            else:
                report.weapon_heat -= w.heat or 0    # a Streak that misses doesn't fire (p.187)
                config.log(f"      Streak missed - launcher doesn't fire: no heat, no ammo.")
        report.attacks += 1
        report.attacks_list.append(DeclaredAttack(weapon=w, tn=tn, roll=roll, hit=hit, side=side,
                                                  aimed_at=w_aim, cover=KICK if id(w) in kick_ids else cover > 0,
                                                  fire=plan,
                                                  pod_value=pod_values.get(id(w), 0.0)))


def _damage_type_for(weapon):
    dt = DAMAGE_TYPE_BY_NAME.get(weapon.damage_type)
    return dt if dt is not None else stubs.stub_unknown_damage_type(weapon)


def _resolve_hit(target, damage, damage_type, side, tag="", reroll_legs=False, cover=False, heat_weapon=False):
    """Cannibalized from MECHSIM__sim_runner._resolve_hit() - same logic:
    hit-location roll, head-hit pilot damage, floating TAC on a 2, then
    apply_damage(). Only change: `side` is passed in (attack_side) rather
    than read from config.FACING.
    cover (2026-10-20, Core pp.66, 73): the target is in partial cover - a hit
    location roll that comes up a leg strikes the cover instead, no damage (the
    floating TAC re-roll re-rolls legs instead, p.95). cover == KICK
    (2026-10-21, pp.67, 127): the hit is on a 'Mech standing in depth 1 from a
    leg weapon in depth 1 or from under water - the Kick Location Table (1D6,
    legs only; no 2 on 2D6, so no Through-Armor Critical)."""
    armor_field = "rear_armor" if side == "rear" else "armor"
    if cover == KICK:
        import INTEGRATION__physical as physical     # physical imports this module
        loc = physical._location("kick", side, target)
        config.log(f"      {tag}Kick Location Table ({side}; legs only under water, p.67): {loc}.")
        apply_damage(target, loc, _protected(target, loc, damage, side, heat_weapon), armor_field=armor_field,
                     damage_type=damage_type)
        return loc
    loc_roll = config.roll_2d6(prompt=f"{tag}Hit location roll")
    loc = resolve_hit_location(loc_roll, target, side)
    config.log(f"      {tag}Hit location roll {loc_roll} ({side} table): {loc}.")
    while reroll_legs and loc in target.leg_locations:   # aimed shot behind partial cover (p.70)
        loc_roll = config.roll_2d6(prompt=f"{tag}Hit location re-roll (legs in cover)")
        loc = resolve_hit_location(loc_roll, target, side)
        config.log(f"      {tag}Legs behind partial cover - re-rolled {loc_roll}: {loc}.")
    if cover and loc in target.leg_locations:
        config.log(f"      {tag}Leg hit strikes the partial cover - no damage (p.66).")
        return None

    if loc == "Head" and head_hit_hurts_pilot(target):
        pilot_hit(target, head=True)              # both warriors with a command console (p.203)
        config.log(f"      Head hit - pilot takes 1 hit ({target.pilot_hits}/6), regardless of armor.")

    if loc_roll == 2 and config.FLOATING_CRITICALS and not target.locations[loc]["destroyed"]:
        config.log("      Roll of 2 - Through-Armor Critical (floating) triggered.")
        tac_side = side
        tac_loc_roll = config.roll_2d6(prompt="  TAC (Through-Armor Critical) location roll")
        tac_loc = resolve_hit_location(tac_loc_roll, target, tac_side)
        tac_armor_field = "rear_armor" if tac_side == "rear" else "armor"
        config.log(f"      Floating TAC re-roll: {tac_loc_roll} -> {tac_loc}")
        while cover and tac_loc in target.leg_locations:     # p.95: legs in partial cover re-roll
            tac_loc_roll = config.roll_2d6(prompt="  TAC location re-roll (legs in cover)")
            tac_loc = resolve_hit_location(tac_loc_roll, target, tac_side)
            config.log(f"      Legs behind partial cover - re-rolled {tac_loc_roll}: {tac_loc}.")
        if tac_loc == "Head" and head_hit_hurts_pilot(target):
            # Fixed 2026-10-20: a head hit always costs the MechWarrior 1 hit (p.117),
            # including when the floating re-roll lands on the head.
            pilot_hit(target, head=True)              # both warriors with a command console (p.203)
            config.log(f"      Head hit - pilot takes 1 hit ({target.pilot_hits}/6), regardless of armor.")
        apply_damage(target, tac_loc, _protected(target, tac_loc, damage, tac_side, heat_weapon),
                     armor_field=tac_armor_field, damage_type=damage_type)
        config.log("      Additional critical hit due to TAC.")
        _tac_check(target, tac_loc, tac_armor_field, damage_type, location_destroyed=False)
        return tac_loc

    # Standard Through-Armor Critical (config.FLOATING_CRITICALS False, Core p.91):
    # the damage lands where the 2 put it, plus one critical-hit check there. A TAC
    # on a location already destroyed goes where its damage transfers (p.89).
    tac_loc = None
    if loc_roll == 2 and not config.FLOATING_CRITICALS and damage >= 1:
        tac_loc = loc
        while tac_loc is not None and target.locations[tac_loc]["destroyed"]:
            tac_loc = TRANSFER_MAP.get(tac_loc)

    apply_damage(target, loc, _protected(target, loc, damage, side, heat_weapon), armor_field=armor_field,
                 damage_type=damage_type)

    if tac_loc is not None:
        config.log(f"      Roll of 2 - Through-Armor Critical: extra critical-hit check at {tac_loc}.")
        _tac_check(target, tac_loc, armor_field, damage_type,
                   location_destroyed=target.locations[tac_loc]["destroyed"])
    return loc


def _tac_check(target, loc, armor_field, damage_type, location_destroyed):
    """The Through-Armor Critical's own critical-hit check at `loc` (p.91),
    with the armor-type modifier (armor_rules.crit_roll_modifier) read after
    the hit, as the floating version always did."""
    loc_state = target.locations[loc]
    armor_key = armor_field if armor_field in loc_state else "armor"
    armor_type = ArmorType.STANDARD if damage_type == DamageType.REENGINEERED \
        else target.armor_type.get(loc, ArmorType.STANDARD)
    modifier = armor_rules.crit_roll_modifier(
        target.structure_type, armor_type, armor_present=loc_state[armor_key] > 0)
    check_critical(target, loc, location_destroyed=location_destroyed, modifier=modifier)


def _d6(n):
    return sum(config.pick_number(6, prompt="Heat 1D6") for _ in range(n))


def has_heat_dissipating_armor(mech):
    return any(t == ArmorType.HEAT_DISSIPATING for t in mech.armor_type.values())


def _heat_armor_damage(target, loc, damage, heat_weapon):
    """Heat-dissipating armor (p.202, 2026-10-21): damage from a heat-causing
    weapon to a location armored with it is halved, rounding up."""
    if heat_weapon and target.armor_type.get(loc) == ArmorType.HEAT_DISSIPATING and damage:
        halved = -(-damage // 2)
        config.log(f"      Heat-dissipating armor at {loc}: {damage} -> {halved} (p.202).")
        return halved
    return damage


def shielded_weapon_ids(mech):
    """Weapons behind a raised shield this phase (p.195): none of them fires,
    rear-mounted ones aside."""
    blocked = gear.raised_blocks(mech)
    if not blocked:
        return frozenset()
    locs = weapon_locations(mech)
    return frozenset(id(w) for w in get_weapons(mech)
                     if locs.get(id(w), set()) & blocked and not getattr(w, "rear_mounted", False))


def _protected(target, loc, damage, side, heat_weapon=False):
    """Damage that reaches `loc` after the target's shield (p.195) and then its
    heat-dissipating armor (p.202) - 2026-10-21."""
    return _heat_armor_damage(target, loc, gear.shield_absorb(target, loc, damage, side), heat_weapon)


def _target_heat(target, weapon):
    """A heat-causing weapon's hit (flamers, plasma - weapon_profiles): outside
    heat on the target, applied (at most 15 a turn) in its Heat Phase - none
    on a 'Mech with any heat-dissipating armor (p.202, 2026-10-21)."""
    got = weapon_profiles.target_heat(weapon, _d6)
    if got and has_heat_dissipating_armor(target):
        config.log(f"      {weapon.name}: heat-dissipating armor - no heat to {target.side_name} (p.202).")
        return
    if got:
        target.outside_heat = getattr(target, "outside_heat", 0) + got
        config.log(f"      {weapon.name}: +{got} heat to {target.side_name} (outside heat, p.102).")


def _resolve_one_attack(attacker, target, attack: DeclaredAttack, battle_rng, pool=None):
    """Cannibalized from MECHSIM__sim_runner.resolve_weapon_attack() (the
    post-to-hit half): one hit for a flat weapon, or a Cluster Hits Table roll
    and one _resolve_hit per damage group. Since 2026-10-20 the shot plan
    (attack.fire, INTEGRATION__fire_modes) sets the column, damage per missile /
    shot / pellet and grouping: rapid fire (each shot its own location),
    LB-X cluster rounds (1-point pellets), ATM / MML ammunition, Artemis /
    Narc / Apollo Cluster changes, an Angel-unlocked Streak."""
    w = attack.weapon
    if electronics.is_narc(w):
        _resolve_pod(attacker, target, attack)
        return
    plan = attack.fire or fire_modes.PLAIN
    _target_heat(target, w)
    if plan.kind == "artillery" or weapon_profiles.is_art_cannon(w):
        dmg = fire_modes.damage_per(w, plan)
        config.log(f"    {w.name} hits {target.side_name}'s hex: {dmg} area-effect damage (pp.182-183).")
        _resolve_area(target, dmg, attack.side, attack.cover)
        return
    per = fire_modes.damage_per(w, plan)
    if not per:
        config.log(f"    {w.name} hit - zero damage weapon, no damage resolution.")
        return
    side = attack.side
    col = fire_modes.column(w, plan)
    streak = weapon_rules.is_streak(w) and plan.guidance.streak_lock
    mod = fire_modes.cluster_modifier(w, plan)
    note = f" ({plan.note})" if plan.note else ""
    dtype = _damage_type_for(w)
    engaged = [x for x in (attack.ams, attack.apds) if x is not None]   # an AMS and / or an APDS (p.206)
    if engaged and col is None:
        for system in engaged:                       # a single missile: each engaged system rolls 1D6
            die = config.pick_number(6, prompt="AMS 1D6 (single missile)")
            if die >= ams.SINGLE_MISSILE_KILL:
                config.log(f"    {w.name} hit - {system.name} rolls 1D6 {die}: missile destroyed, no damage (p.206).")
                return
            config.log(f"    {w.name} hit - {system.name} rolls 1D6 {die}: the missile gets through.")
    if attack.aimed_at:
        _resolve_aimed_hit(target, w, per, dtype, side, attack)
        return
    if col is None:
        per = equip.blue_shield_damage(target, w, per)       # a PPC vs an active Blue Shield (p.207)
        config.log(f"    {w.name} hit for {per}{note}:")
        _resolve_hit(target, per, dtype, side, cover=attack.cover, heat_weapon=weapon_profiles.heat_causing(w))
        return
    if col == 0:
        config.log(f"    {w.name} hit - no guns left to fire.")
        return
    names = " + ".join(x.name for x in engaged)
    if streak and engaged:
        # AMS / APDS: the Streak counts as a 12 then -5 each - a 7, or a 2 with both (p.206).
        result = max(2, 12 - ams.STREAK_CUT * len(engaged))
        hits = cluster_hits_count(col, result)
        config.log(f"    {w.name} hit: Streak engaged by {names} - result {result} on the "
                   f"{col}-column table -> {hits} connect ({hits * per} dmg).")
    elif streak:
        hits = col                            # Streak: Cluster result is automatically 12 (p.187)
        config.log(f"    {w.name} hit: Streak - all {hits} missiles hit ({hits * per} dmg).")
    elif engaged:
        # AMS / APDS (p.206): -4 more each; below 2 every missile is destroyed (only the top clamps).
        raw = config.roll_2d6(prompt=f"Cluster hits roll ({w.name})")
        mod += ams.CLUSTER_MODIFIER * len(engaged)
        if raw + mod < 2:
            config.log(f"    {w.name} hit: cluster roll {raw} {mod:+d} (AMS {names}){note} = {raw + mod} "
                       f"- below 2, every missile destroyed, no damage.")
            return
        hits = cluster_hits_count(col, min(12, raw + mod))
        config.log(f"    {w.name} hit: cluster roll {raw} {mod:+d} (AMS {names}){note} on the "
                   f"{col}-column table -> {hits} connect ({hits * per} dmg).")
    else:
        raw = config.roll_2d6(prompt=f"Cluster hits roll ({w.name})")
        cluster_roll = max(2, min(12, raw + mod))     # p.74: results clamp to 2-12
        hits = cluster_hits_count(col, cluster_roll)
        config.log(f"    {w.name} hit: cluster roll {raw}{f' {mod:+d}' if mod else ''}{note} on the "
                   f"{col}-column table -> {hits} connect ({hits * per} dmg).")
    total = hits * per
    if weapon_profiles.is_mga(w):
        # Machine gun array (p.185): one hit location roll, every hit there one at a time.
        loc = _resolve_hit(target, per, dtype, side, tag="Array: ", cover=attack.cover)
        for _ in range(hits - 1):
            if loc is None or target.destroyed:
                break
            if loc == "Head" and head_hit_hurts_pilot(target):
                pilot_hit(target, head=True)              # both warriors with a command console (p.203)
            apply_damage(target, loc, _protected(target, loc, per, side), armor_field="rear_armor" if side == "rear" else "armor",
                         damage_type=dtype)
        return
    if plan.kind == "saturation":
        total = fire_modes.third(hits)
        config.log(f"      Apollo saturation: {hits} missiles / 3 = {total} area-effect damage (p.197).")
        _resolve_area(target, total, side, attack.cover)
        return
    size = fire_modes.grouping(w, plan)
    if pool is not None:
        # Optional rule (Daniel): every cluster hit's damage of one grouping size is added up
        # and grouped together at the end of the attacker's resolution (run_ranged_combat_phase).
        pool.setdefault((size, dtype, side, attack.cover), []).append((w.name, total))
        return
    _apply_groups(target, total, size, dtype, side, attack.cover)


def _apply_groups(target, total, size, dtype, side, cover, label=""):
    """`total` damage in `size`-point groupings, the remainder last (p.87)."""
    groups = [size] * int(total // size) + ([total - size * int(total // size)] if total % size else [])
    for i, dmg in enumerate(groups, start=1):
        _resolve_hit(target, dmg, dtype, side, tag=f"{label}Group {i}/{len(groups)}: ", cover=cover)


def _resolve_area(target, damage, side, cover):
    """Area-effect damage on a 'Mech in the hex: 5-point groupings, standard
    hit location table, partial cover as normal (pp.87, 181-182)."""
    _apply_groups(target, damage, weapon_profiles.AREA_GROUPING, DamageType.MISSILE, side, cover, "AE ")


def _in_firing_arc(attacker, weapon, xy):
    """Can `weapon` bear on hex `xy` (doubled coords) with the attacker's
    facing and this turn's declared twist / flip / turret (pp.60-62)?"""
    key = arcs.key_for(arcs.arcs_between(hex_geometry.parse_hex_label(attacker.hex), xy),
                       hex_geometry.compass_to_facing(attacker.facing),
                       arcs.current_action(attacker), arcs.leg_offsets(attacker))
    return id(weapon) not in arc_unavailable(attacker, key)


def _resolve_area_miss(attacker, target, attack, terrain_map):
    """A missed Arrow IV / artillery cannon scatters (pp.182-183): 1D6
    direction (1 = up the map, clockwise), MOF / 2 hexes rounding up. The
    impact point can't leave the launcher's firing arc: it lands in the last
    hex along the scatter path before it would (pp.182, 183 - fixed
    2026-10-21, Daniel: "Firing arc is an issue"); held back all the way, it
    lands in the target's own hex and deals the full area-effect damage.
    Landing next to the target deals it the splash (Arrow IV and Long Tom 10,
    else none); off the board, nothing (p.181)."""
    w = attack.weapon
    mof = attack.tn - attack.roll
    dist = -(-mof // 2)
    direction = config.pick_number(6, prompt="Arrow IV scatter direction 1D6") - 1
    tx, ty = hex_geometry.parse_hex_label(target.hex)
    dx, dy = hex_geometry.FACING_DELTAS[direction]
    # Walk the scatter path a hex at a time; stop before the first hex outside the arc.
    steps = 0
    while steps < dist and _in_firing_arc(attacker, w, (tx + dx * (steps + 1), ty + dy * (steps + 1))):
        steps += 1
    impact = (tx + dx * steps, ty + dy * steps)
    held = f" (held to {steps} by the firing arc, pp.182-183)" if steps < dist else ""
    if steps == 0:
        dmg = fire_modes.damage_per(w, attack.fire or fire_modes.PLAIN)
        config.log(f"    {w.name} missed by {mof}: scatters {dist} hex{'es' if dist > 1 else ''} "
                   f"(direction {direction + 1}), but the firing arc holds it in {target.side_name}'s hex: "
                   f"{dmg} area-effect damage (pp.182-183).")
        _resolve_area(target, dmg, attack.side, attack.cover)
        return
    if not weapon_profiles.splash(w):
        config.log(f"    {w.name} missed - the shell lands {steps} hex{'es' if steps > 1 else ''} away "
                   f"from {target.side_name}{held} (no splash).")
        return
    try:
        label = hex_geometry.hex_label(*impact)
    except ValueError:
        label = None
    on_board = label is not None and label in terrain_map["hexes"]
    config.log(f"    {w.name} missed by {mof}: scatters {dist} hex{'es' if dist > 1 else ''} "
               f"(direction {direction + 1}){held} to {label or 'off the board'}"
               f"{'' if on_board else ' - off the board, no effect'}.")
    if on_board and steps == 1:
        side = attack_side(impact, (tx, ty), hex_geometry.compass_to_facing(target.facing), terrain_map)
        dmg = weapon_profiles.splash(w)
        config.log(f"      {target.side_name} is next to the impact: {dmg} area-effect damage.")
        _resolve_area(target, dmg, side, False)


def _resolve_pod(attacker, target, attack):
    """A Narc / iNarc beacon hit (pp.188, 193): the target's AMS may kill the
    pod (1D6 4+, p.206); an explosive pod does its damage; a homing pod sticks
    in the location struck (a leg behind partial cover: the cover) and works
    from the next phase (INTEGRATION__electronics)."""
    w = attack.weapon
    munition = (attack.fire or fire_modes.PLAIN).munition
    for system in (x for x in (attack.ams, attack.apds) if x is not None):
        die = config.pick_number(6, prompt="AMS 1D6 (Narc pod)")
        if die >= ams.SINGLE_MISSILE_KILL:
            config.log(f"    {w.name} hit - {system.name} rolls 1D6 {die}: pod destroyed (p.206).")
            return
        config.log(f"    {w.name} hit - {system.name} rolls 1D6 {die}: the pod gets through.")
    if munition == "explosive":
        dmg = ammo.EXPLOSIVE_POD_DAMAGE.get(w.ammo_key, 0)
        config.log(f"    {w.name} hit: explosive pod for {dmg}:")
        _resolve_hit(target, dmg, DamageType.MISSILE, attack.side, cover=attack.cover)
        return
    roll = config.roll_2d6(prompt="Hit location roll (Narc pod)")
    loc = resolve_hit_location(roll, target, attack.side)
    if attack.cover == KICK:
        import INTEGRATION__physical as physical
        loc = physical._location("kick", attack.side, target)
    elif attack.cover and loc in target.leg_locations:
        config.log(f"    {w.name} hit: location roll {roll} -> {loc}, behind partial cover - the pod strikes the cover.")
        return
    electronics.attach_pod(target, loc, attacker.side_name)
    config.log(f"    {w.name} hit: homing pod attached to {target.side_name}'s {loc} (location roll {roll}); "
               f"works from the next phase{' - but its ECM blocks it' if electronics.narc_blocked(target) else ''}.")


def _resolve_aimed_hit(target, weapon, damage, dtype, side, attack):
    """p.70: 1D6 4+ puts the hit on the aimed location; otherwise roll
    normally (re-rolling legs behind partial cover). damage: this shot's
    damage (fire_modes.damage_per - a variable-damage weapon's by range; it
    was weapon.damage_per_shot, empty for a Heavy Gauss Rifle - fixed
    2026-10-21 when an aimed shot from one crashed a battle)."""
    die = config.pick_number(6, prompt="Aimed shot 1D6")
    if die < AIMED_SHOT_SUCCESS:
        config.log(f"    {weapon.name} hit for {damage}: aimed at {attack.aimed_at}, "
                   f"1D6 {die} - rolls for location.")
        _resolve_hit(target, damage, dtype, side, reroll_legs=attack.cover,
                     heat_weapon=weapon_profiles.heat_causing(weapon))
        return
    config.log(f"    {weapon.name} hit for {damage}: aimed at {attack.aimed_at}, 1D6 {die} - on target.")
    loc = attack.aimed_at
    if loc == "Head" and head_hit_hurts_pilot(target):
        pilot_hit(target, head=True)              # both warriors with a command console (p.203)
        config.log(f"      Head hit - pilot takes 1 hit ({target.pilot_hits}/6), regardless of armor.")
    apply_damage(target, loc, _protected(target, loc, damage, side, weapon_profiles.heat_causing(weapon)),
                 armor_field="rear_armor" if side == "rear" else "armor", damage_type=dtype)


def run_ranged_combat_phase(mover_first, mover_second, terrain_map, battle_rng):
    """Whole phase, per the SEQUENCE in the module docstring. Returns
    {side_name: SideReport}."""
    reports = {mover_first.side_name: SideReport(), mover_second.side_name: SideReport()}
    pairs = ((mover_first, mover_second), (mover_second, mover_first))

    for m in (mover_first, mover_second):
        snapshot_round_capability(m)
        piloting_rolls.snapshot_pre_attack_phase(m)
        if not is_destroyed(m):
            gear.declare_raise(m, "Ranged")               # p.195 - a stub decides

    with timing.section("choosing weapons and twists"):
        for attacker, target in pairs:
            declare_attacks(attacker, target, terrain_map, reports[attacker.side_name])
            # Nothing to shoot this turn: maybe pick up a club instead (p.79, INTEGRATION__clubs).
            clubs.maybe_pick_up(attacker, terrain_map, fired_anything=bool(reports[attacker.side_name].attacks_list))

    # AMS (p.206): engaged right after the attack rolls, before any damage lands.
    for attacker, target in pairs:
        ams.engage(target, attacker, reports[attacker.side_name].attacks_list, reports[target.side_name])

    with timing.section("resolving hits and damage"):
        for attacker, target in pairs:
            rep = reports[attacker.side_name]
            hp_before = total_hp(target)
            pool = {} if config.POOL_CLUSTER_DAMAGE else None
            for attack in rep.attacks_list:
                if attack.hit:
                    rep.hits += 1
                    _resolve_one_attack(attacker, target, attack, battle_rng, pool)
                elif (attack.fire is not None and attack.fire.kind == "artillery") or weapon_profiles.is_art_cannon(attack.weapon):
                    _resolve_area_miss(attacker, target, attack, terrain_map)
            for (size, dtype, side, cover), parts in (pool or {}).items():
                total = sum(d for _, d in parts)
                if len(parts) > 1:
                    config.log(f"    Cluster damage pooled ({size}-point groupings): "
                               f"{' + '.join(f'{n} {d}' for n, d in parts)} = {total}.")
                else:
                    config.log(f"    {parts[0][0]}: {total} damage in {size}-point groupings.")
                _apply_groups(target, total, size, dtype, side, cover)
            rep.damage_dealt += hp_before - total_hp(target)

    for m in (mover_first, mover_second):
        gear.lower(m)                         # a raised shield lowers at the end of the phase (p.195)
        electronics.activate_pods(m)          # pods that hit this phase work from the next (p.193)
        fire_modes.resolve_unjams(m)          # Rotary AC unjam attempts (p.183)
    for m in (mover_first, mover_second):
        _with_piloting(m, piloting_rolls.resolve_attack_phase_psr)
        piloting_rolls.resolve_consciousness_checks(m, "Attack Phase")

    return reports
