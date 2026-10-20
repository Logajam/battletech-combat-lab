"""
INTEGRATION__physical.py  (NEW 2026-10-19, Claude - Pile 2 rules, Pile 4 choice)

The Physical Attack Phase (Core Rulebook pp.76-83), replacing the
physical_combat stub: punches, kicks and physical weapons (claws, hatchet,
lance, mace, retractable blade, sword, vibroblades - treated as switched
off, talons on kicks). Charges are INTEGRATION__charge (declared in the
Movement Phase, resolved here). Death-from-above, pushes and clubs are not
built (see results.KNOWN_MISSING_RULES).

  - Who (p.76-77): an adjacent target; a standing, powered, conscious
    attacker; one attack type per turn (both arms may punch). Prone mechs
    can't make physical attacks.
  - Arcs (INTEGRATION__arcs, p.60): for an adjacent target that is the
    front hexside and the two beside it = forward, the rear-side hexsides =
    the side arcs, the back hexside = rear. Kicks: the legs' forward arc
    (actual facing, twists ignored, p.81). Punches / arm weapons: forward or
    that arm's side arc of the TWISTED torso (p.62). Reversed arms: no
    punches or arm weapons (p.62). Tripods (p.236): every physical attack,
    kicks included, only into the twisted torso's forward arc.
  - Torso twist (pp.62, 76): a twist or flip declared in the Ranged phase
    stands; a mech that declared neither may twist now, at the start of its
    physical declaration (one hexside, a tripod any, never prone / quads).
  - Weapons fired this turn from an arm (or the kicking leg) stop that limb
    attacking (pp.79, 81-82).
  - To-hit (p.76): Piloting + attack modifier (punch / kick -1, weapons per
    the p.81 table) + AMM + TMM + terrain + prone target / immobile; never
    heat or sensors. Actuators (pp.81-82): punch - hand +1, lower / upper
    arm +2 each and half damage, shoulder = no punch; kick - foot +1, lower /
    upper leg +2 each and half damage (any leg), a hip hit = no kicks;
    weapons - lower / upper arm +2, a destroyed hand or shoulder = no attack.
  - Damage: punch 1 per 10 tons (round up), kick 1 per 5 tons, weapons per
    the p.81 table (round up); TSM doubles (p.205); talons x1.5 on kicks.
    One grouping each. Tables: punches on the Punch table, kicks on the Kick
    table, weapons on the standard table - by attack direction (p.73).
  - Levels (p.77): within one level only. Standing target one level up:
    punch / weapon only, on the Kick table; one level down: kick / weapon on
    the Punch table. Prone target: kick / weapon (not claws) on the standard
    table at the same level, punch / weapon one level up.
  - All attacks are declared and rolled, then damage lands (p.83). A kicked
    mech, and one that missed a kick, makes a PSR (+0) at the end of the
    phase, joined to the phase's damage PSR (piloting_rolls).

Bot choice (pile 4): the twist and attack type with the most expected
damage; ties keep the torso where it is. The plan is first made in the
Ranged phase (attack_resolution.declare_attacks scores ranged fire + the
physical attack that can follow, holding back the weapons of a limb that
will punch or kick) and in movement scoring (Planner); this phase then
re-picks with what actually happened (fired weapons, falls, damage).
"""

import math

import INTEGRATION__config as config
import INTEGRATION__attack_resolution as attack_resolution
import INTEGRATION__arcs as arcs
import INTEGRATION__structure_weight as structure_weight
from mech_state import DamageType, is_destroyed, is_immobile, mark_consciousness_check_pending
from equipment import Equipment
from damage_resolution import apply_damage
from hit_location import resolve_hit_location
import piloting_rolls
import hex_geometry
import combat
from los import has_los, hex_distance

ARMS = ("Left Arm", "Right Arm")
ARM_SIDE_ARC = {"Left Arm": arcs.LEFT, "Right Arm": arcs.RIGHT}
PUNCH_MOD = -1
KICK_MOD = -1

KICK_TABLE = {"left": ("Left Leg", "Left Leg"), "front": ("Right Leg", "Left Leg"),
              "rear": ("Right Leg", "Left Leg"), "right": ("Right Leg", "Right Leg")}        # (1-3, 4-6), p.81
PUNCH_TABLE = {
    "left": ("Left Torso", "Left Torso", "Center Torso", "Left Arm", "Left Arm", "Head"),
    "front": ("Right Arm", "Right Torso", "Center Torso", "Left Torso", "Left Arm", "Head"),
    "rear": ("Right Arm", "Right Torso", "Center Torso", "Left Torso", "Left Arm", "Head"),
    "right": ("Right Torso", "Right Torso", "Center Torso", "Right Arm", "Right Arm", "Head"),
}

# Physical Weapon Attacks Table, p.81: name fragment -> (TN modifier, tons per point, +damage, table)
PHYSICAL_WEAPONS = (
    ("CLAW", (0, 7, 0, "punch")),
    ("HATCHET", (-1, 5, 0, "standard")),
    ("LANCE", (1, 5, 0, "standard")),
    ("MACE", (1, 4, 0, "standard")),
    ("RETRACTABLEBLADE", (-2, 10, 0, "standard")),
    ("SWORD", (-2, 10, 1, "standard")),
    ("VIBROBLADE", (-2, 10, 1, "standard")),      # switched off (activation not modeled)
)


def _norm(name):
    return (name or "").replace(" ", "").replace("-", "").upper()


def _weapon_kind(slot):
    if not isinstance(slot, Equipment):
        return None
    n = _norm(slot.name)
    return next((spec for frag, spec in PHYSICAL_WEAPONS if frag in n), None)


_QUAD_NAMES = {"Left Arm": "Front Left Leg", "Right Arm": "Front Right Leg"}


def _quad_location(loc, side):
    """Punch / kick table names on a quad (arms are its front legs)."""
    if loc in _QUAD_NAMES:
        return _QUAD_NAMES[loc]
    if loc in ("Left Leg", "Right Leg"):
        return ("Rear " if side == "rear" else "Front ") + loc
    return loc


def table_rolls(table, side, target):
    """[(probability, location)] of the Punch (1D6) or Kick (1D6: 1-3 / 4-6)
    Location Table, p.81, for an attack on `side` of `target`; None for the
    standard 2D6 table."""
    if table == "punch":
        rolls = [(1 / 6, loc) for loc in PUNCH_TABLE[side]]
    elif table == "kick":
        rolls = [(0.5, loc) for loc in KICK_TABLE[side]]
    else:
        return None
    if target.mech_type in ("quad", "quadvee"):
        rolls = [(p, _quad_location(loc, side)) for p, loc in rolls]
    return rolls


class Worth:
    """How much a point of physical damage on each hit table counts against
    `target` (Pile 4 scoring, 2026-10-20): the table's own armor exposure
    (INTEGRATION__movement_selection's exposure factor, computed on the punch /
    kick table instead of the standard one - a kick at stripped legs, a punch's
    1-in-6 head chance) times the structure bonus for damage getting past
    armor there (INTEGRATION__structure_weight, k = MOVEMENT_STRUCTURE_WEIGHT).
    relative=True divides out the standard-table exposure for that side, for a
    caller (movement scoring) that already multiplies by it."""

    def __init__(self, target, relative=False):
        self.target = target
        self.relative = relative
        self._memo = {}
        self._front = structure_weight.vulnerability(structure_weight.hit_spread(target, "front"))

    def _exposure(self, spread):
        if not config.MOVEMENT_EXPOSURE_WEIGHTING or self._front <= 0:
            return 1.0
        return max(config.MOVEMENT_EXPOSURE_MIN,
                   min(config.MOVEMENT_EXPOSURE_MAX, structure_weight.vulnerability(spread) / self._front))

    def factor(self, table, side, damage):
        k = (table, side, damage)
        got = self._memo.get(k)
        if got is None:
            spread = structure_weight.hit_spread(self.target, side, table_rolls(table, side, self.target))
            got = self._exposure(spread)
            if self.relative:
                standard = 1.0 if side == "front" else self._exposure(structure_weight.hit_spread(self.target, side))
                got /= standard
            if damage > 0:
                got *= structure_weight.spread_worth(spread, damage, config.MOVEMENT_STRUCTURE_WEIGHT) / damage
            self._memo[k] = got
        return got


# =============================================================================
# ==========================  LIMB STATE  =====================================
# =============================================================================
def _has_part(mech, loc, part):
    """The design has this actuator in that location (live or destroyed)."""
    return part in mech.crits.get(loc, []) or any(
        l == loc and info["name"] == part for (l, _), info in mech.destroyed_slot_info.items())


def _lost(mech, loc, part):
    return any(l == loc and info["name"] == part for (l, _), info in mech.destroyed_slot_info.items())


def _limb_fired(mech, loc, fired_ids):
    locs = attack_resolution.weapon_locations(mech)
    return any(loc in locs.get(wid, ()) for wid in fired_ids)


class Reach:
    """Where an adjacent target sits for this attacker's physical attacks."""

    def __init__(self, mech, a_hex, facing, t_hex, action, pair=None):
        if pair is None:
            pair = arcs.arcs_between(a_hex, t_hex)
        self.torso_arc = pair[(facing + action.twist) % 6]
        self.tripod = mech.mech_type == "tripod"
        self.flipped = action.flip
        # Kicks use the legs (p.81) - except a tripod's, which follow the torso (p.236).
        self.kick_ok = (self.torso_arc if self.tripod else pair[facing]) == arcs.FORWARD

    def arm_ok(self, arm):
        if self.flipped:
            return False
        if self.tripod:
            return self.torso_arc == arcs.FORWARD
        return self.torso_arc in (arcs.FORWARD, ARM_SIDE_ARC[arm])

    def signature(self):
        """Everything about the geometry the attack options depend on."""
        return (self.arm_ok("Left Arm"), self.arm_ok("Right Arm"), self.kick_ok)


def _strength(mech, per_tons, plus=0):
    dmg = math.ceil(mech.mass / per_tons) + plus
    return dmg * (2 if getattr(mech, "tsm_active", False) else 1)


# =============================================================================
# ==========================  OPTIONS  ========================================
# =============================================================================
def _punch_options(m, rel, fired, table):
    out = []
    for arm in ARMS:
        if arm not in m.locations or m.locations[arm]["destroyed"] or not rel.arm_ok(arm):
            continue
        if _lost(m, arm, "Shoulder") or _limb_fired(m, arm, fired):
            continue
        claw = next((s for s in m.crits[arm] if _weapon_kind(s) and _weapon_kind(s)[3] == "punch"), None)
        mod, dmg, halves = (0, _strength(m, 7), 0) if claw else (PUNCH_MOD, _strength(m, 10), 0)
        if not claw and (not _has_part(m, arm, "Hand Actuator") or _lost(m, arm, "Hand Actuator")):
            mod += 1
        for part in ("Lower Arm Actuator", "Upper Arm Actuator"):
            if (part == "Lower Arm Actuator" and not _has_part(m, arm, part)) or _lost(m, arm, part):
                mod += 2
                halves += 1
        out.append(dict(name=f"{'claw' if claw else 'punch'} ({arm})", mod=mod, damage=dmg // (2 ** halves),
                        table="punch" if table is None else table, limb=arm))
    return out


def _kick_options(m, rel, fired, table):
    if not rel.kick_ok or m.destroyed_hip_locations:
        return []
    legs = [l for l in m.leg_locations if not m.locations[l]["destroyed"]]
    if len(legs) < len(m.leg_locations):
        return []
    mod, halves = KICK_MOD, 0
    for leg in m.leg_locations:                      # actuator effects from either leg apply (p.81)
        if _lost(m, leg, "Foot Actuator"):
            mod += 1
        for part in ("Lower Leg Actuator", "Upper Leg Actuator"):
            if _lost(m, leg, part):
                mod += 2
                halves += 1
    out = []
    for leg in legs:
        if _limb_fired(m, leg, fired):
            continue
        dmg = _strength(m, 5) // (2 ** halves)
        if any(_norm(getattr(s, "name", "")) == "TALONS" for s in m.crits[leg]):
            dmg = round(dmg * 1.5)
        out.append(dict(name=f"kick ({leg})", mod=mod, damage=dmg, table="kick" if table is None else table,
                        kick=True, limb=leg))
    return out


def _weapon_options(m, rel, fired, table, target_prone):
    out = []
    for arm in ARMS:
        if arm not in m.locations or m.locations[arm]["destroyed"] or not rel.arm_ok(arm):
            continue
        if _lost(m, arm, "Shoulder") or _limb_fired(m, arm, fired):
            continue
        for slot in {id(s): s for s in m.crits[arm] if _weapon_kind(s)}.values():
            tn_mod, per, plus, wtable = _weapon_kind(slot)
            if wtable == "punch":
                continue                                # claws are punches
            if _lost(m, arm, "Hand Actuator") and "RETRACTABLEBLADE" not in _norm(slot.name):
                continue
            mod = tn_mod + sum(2 for part in ("Lower Arm Actuator", "Upper Arm Actuator")
                               if (part == "Lower Arm Actuator" and not _has_part(m, arm, part)) or _lost(m, arm, part))
            out.append(dict(name=f"{slot.name} ({arm})", mod=mod, damage=_strength(m, per, plus),
                            table="standard" if table is None else table, limb=arm))
    return out


def attack_options(attacker, target, terrain_map, action=None):
    """{"type": [option, ...]} the attacker could make this phase with arc
    action `action` (default: what it has declared this turn); one type is
    then chosen. Empty when no physical attack is possible."""
    if attacker.prone or is_immobile(attacker) or is_destroyed(attacker) or is_destroyed(target):
        return {}
    return options_at(attacker, hex_geometry.parse_hex_label(attacker.hex),
                      hex_geometry.compass_to_facing(attacker.facing), terrain_map["hexes"][attacker.hex]["level"],
                      hex_geometry.parse_hex_label(target.hex), terrain_map["hexes"][target.hex]["level"],
                      target.prone, getattr(attacker, "weapons_fired_this_turn", frozenset()),
                      arcs.current_action(attacker) if action is None else action)


def options_at(attacker, a_hex, a_facing, a_level, t_hex, t_level, target_prone, fired, action):
    """attack_options for an attacker standing on a_hex facing a_facing (0-5)
    against a target on t_hex - positions given, so movement scoring can ask
    about a spot neither mech stands on yet. The attacker is taken to be able
    to attack (standing, powered, conscious)."""
    if hex_distance(a_hex, t_hex) != 1:
        return {}
    diff = t_level - a_level
    if abs(diff) > 1:
        return {}
    return _options(attacker, Reach(attacker, a_hex, a_facing, t_hex, action), diff, target_prone, fired)


def _options(attacker, rel, diff, target_prone, fired):
    opts = {}
    if target_prone:
        if diff == 0:
            opts["kick"] = _kick_options(attacker, rel, fired, "standard")
            opts["weapon"] = _weapon_options(attacker, rel, fired, None, True)
        elif diff == 1:
            opts["punch"] = _punch_options(attacker, rel, fired, None)
            opts["weapon"] = _weapon_options(attacker, rel, fired, None, True)
    elif diff == 0:
        opts["punch"] = _punch_options(attacker, rel, fired, None)
        opts["kick"] = _kick_options(attacker, rel, fired, None)
        opts["weapon"] = _weapon_options(attacker, rel, fired, None, False)
    elif diff == 1:
        opts["punch"] = _punch_options(attacker, rel, fired, "kick")
        opts["weapon"] = _weapon_options(attacker, rel, fired, "kick", False)
    else:
        opts["kick"] = _kick_options(attacker, rel, fired, "punch")
        opts["weapon"] = _weapon_options(attacker, rel, fired, "punch", False)
    return {k: v for k, v in opts.items() if v}


class _FixedReach:
    """A Reach rebuilt from its signature (all the option builders read)."""

    def __init__(self, signature):
        self._arms = {"Left Arm": signature[0], "Right Arm": signature[1]}
        self.kick_ok = signature[2]

    def arm_ok(self, arm):
        return self._arms[arm]


class Planner:
    """Physical plans for one mech before anything has fired this turn, for
    positions that don't exist yet (movement scoring, the Ranged phase's
    look-ahead). The options only depend on Reach.signature(), the level
    difference and whether the target is prone, so they're built once per
    case. Build a new one when the mech's state changes (damage, TSM)."""

    def __init__(self, mech, worth=None):
        self.mech = mech
        self.worth = worth                 # a Worth for the target, or None for raw expected damage
        self._options = {}
        self._plans = {}
        self._held = {}
        self._cases = {}

    def plans(self, a_hex, a_facing, a_level, t_hex, t_level, target_prone, action, base, side="front"):
        """plans() for the attack, or [] when the target is out of reach."""
        diff = t_level - a_level
        if abs(diff) > 1 or hex_distance(a_hex, t_hex) != 1:
            return []
        return self._plans_for(Reach(self.mech, a_hex, a_facing, t_hex, action).signature(), diff,
                               target_prone, base, side)

    def _plans_for(self, signature, diff, target_prone, base, side="front"):
        case = (signature, diff, target_prone)
        side = side if self.worth is not None else "front"
        got = self._plans.get((case, base, side))
        if got is None:
            options = self._options.get(case)
            if options is None:
                options = self._options[case] = _options(self.mech, _FixedReach(signature), diff, target_prone,
                                                         frozenset())
            got = self._plans[(case, base, side)] = plans(options, base, self.worth, side)
        return got

    def cases(self, pair_arcs, facing, actions, legs):
        """The distinct (ArcKey, reach signature) pairs `actions` give against
        an adjacent target with arcs-tuple pair_arcs - two twists that look
        the same to both the guns and the fists are scored once."""
        k = (pair_arcs, facing, actions, legs)
        got = self._cases.get(k)
        if got is None:
            got = self._cases[k] = tuple(dict.fromkeys(
                (arcs.key_for(pair_arcs, facing, a, legs), Reach(self.mech, None, facing, None, a, pair_arcs).signature())
                for a in actions))
        return got

    def plans_in_case(self, signature, diff, target_prone, base, side="front"):
        return self._plans_for(signature, diff, target_prone, base, side) if abs(diff) <= 1 else []

    def held(self, limbs):
        got = self._held.get(limbs)
        if got is None:
            got = self._held[limbs] = limb_weapon_ids(self.mech, limbs)
        return got


def base_tn(attacker, amm, target_tmm, los_modifier, target_prone_modifier):
    """p.76: Piloting + AMM + TMM + terrain + prone / immobile target; never
    heat or sensors."""
    return attacker.piloting + amm + target_tmm + los_modifier + target_prone_modifier


def _base_tn(attacker, target, terrain_map):
    a_hex, t_hex = hex_geometry.parse_hex_label(attacker.hex), hex_geometry.parse_hex_label(target.hex)
    return base_tn(attacker, combat.MODE_TO_AMM[attacker.move_mode], attack_resolution._target_tmm(target),
                   has_los(a_hex, t_hex, terrain_map).modifier, attack_resolution.prone_target_modifier(target, 1))


def expected_damage(base, picks, worth=None, side="front"):
    """Expected damage of the picks; with a Worth, their worth on `side`."""
    if worth is None:
        return sum(combat.hit_probability(base + o["mod"]) * o["damage"] for o in picks)
    return sum(combat.hit_probability(base + o["mod"]) * o["damage"] * worth.factor(o["table"], side, o["damage"])
               for o in picks)


def limb_weapon_ids(mech, limbs):
    """Weapons that may not fire if `limbs` make physical attacks this turn
    (a split torso/arm weapon counts as in the arm, p.76)."""
    locs = attack_resolution.weapon_locations(mech)
    return frozenset(wid for wid, where in locs.items() if set(where) & set(limbs))


def plans(options, base, worth=None, side="front"):
    """Every physical attack the mech could plan with these options, as
    (expected damage, limbs it uses, picks), best first; the empty plan is
    always included (0.0, (), []). Punches: either arm or both (p.82);
    kicks and physical weapons: one (p.76)."""
    out = [(0.0, (), [])]
    for kind, opts in options.items():
        if kind == "punch":
            groups = [[o] for o in opts] + ([list(opts)] if len(opts) > 1 else [])
        else:
            groups = [[o] for o in opts]
        for g in groups:
            v = expected_damage(base, g, worth, side)
            if v > 0:
                out.append((v, tuple(o["limb"] for o in g), g))
    out.sort(key=lambda p: -p[0])
    return out


def choose_attack(attacker, target, terrain_map):
    """Pile 4: the arc action (twist, if it may still declare one - p.76) and
    attack type (all of its options - e.g. both punches) with the most
    expected damage, weighted by where each table lands (Worth: a kick at
    stripped legs or a punch at a thin head counts for more). Returns
    (base TN, [options], ArcAction) or None."""
    turret = arcs.current_action(attacker).turret
    actions = tuple(dict.fromkeys(a._replace(turret=turret) for a in arcs.arc_options(attacker, phase="physical")))
    side = attack_resolution.attack_side(hex_geometry.parse_hex_label(attacker.hex),
                                         hex_geometry.parse_hex_label(target.hex),
                                         hex_geometry.compass_to_facing(target.facing), terrain_map)
    worth = Worth(target)
    base = None
    value = lambda opts: expected_damage(base, opts, worth, side)  # noqa: E731
    best = None
    for action in actions:
        options = attack_options(attacker, target, terrain_map, action)
        if not options:
            continue
        if base is None:
            base = _base_tn(attacker, target, terrain_map)
        pick = lambda k: options[k] if k == "punch" else [max(options[k], key=lambda o: value([o]))]  # noqa: E731
        kind = max(options, key=lambda k: value(pick(k)))
        picks = pick(kind)
        if value(picks) > 0 and (best is None or value(picks) > value(best[1]) + 1e-12):
            best = (base, picks, action)
    return best


# =============================================================================
# ==========================  PHASE  ==========================================
# =============================================================================
def _location(table, side, target):
    if table == "standard":
        return resolve_hit_location(config.roll_2d6(prompt="Physical hit location"), target, side)
    die = config.pick_number(6, prompt=f"{table} location (1D6)")
    if table == "kick":
        loc = KICK_TABLE[side][0 if die <= 3 else 1]
    else:
        loc = PUNCH_TABLE[side][die - 1]
    if target.mech_type in ("quad", "quadvee"):
        quad = {"Left Arm": "Front Left Leg", "Right Arm": "Front Right Leg",
                "Left Leg": "Rear Left Leg" if side == "rear" else "Front Left Leg",
                "Right Leg": "Rear Right Leg" if side == "rear" else "Front Right Leg"}
        loc = quad.get(loc, loc)
    return loc


def run_physical_phase(mech_a, mech_b, terrain_map, reports):
    """Both mechs declare and roll, then the damage lands, then charges'
    damage and displacement, then PSRs and consciousness checks (p.83)."""
    import INTEGRATION__charge as charge       # charge imports this module
    for m in (mech_a, mech_b):
        rep = reports.get(m.side_name)
        m.weapons_fired_this_turn = frozenset(id(x.weapon) for x in rep.attacks_list) if rep else frozenset()
        piloting_rolls.snapshot_pre_attack_phase(m)
    declared = []
    charges = []
    for attacker, target in ((mech_a, mech_b), (mech_b, mech_a)):
        if getattr(attacker, "charging", None) is not None:
            outcome = charge.declare(attacker, target, terrain_map)
            if outcome is not None:                      # going ahead, or a miss: no other physical attack
                if outcome != "miss" and outcome[1]:
                    charges.append((attacker, target))
                continue
        choice = choose_attack(attacker, target, terrain_map)
        if choice is None:
            continue
        base, picks, action = choice
        if action != arcs.current_action(attacker):
            arcs.declare(attacker, action)
            config.log(f"  [Physical] {attacker.side_name} {arcs.describe(action)} to reach {target.side_name}.")
        side = attack_resolution.attack_side(hex_geometry.parse_hex_label(attacker.hex),
                                             hex_geometry.parse_hex_label(target.hex),
                                             hex_geometry.compass_to_facing(target.facing), terrain_map)
        for o in picks:
            tn = base + o["mod"]
            roll = config.roll_2d6(prompt=f"Physical attack roll ({o['name']})")
            hit = roll >= tn
            config.log(f"  [Physical] {attacker.side_name} -> {target.side_name}: {o['name']} needs {tn} "
                       f"(piloting {attacker.piloting} + base {base - attacker.piloting} + attack {o['mod']:+d}), "
                       f"rolled {roll} -> {'HIT' if hit else 'miss'} ({o['damage']} dmg, {side} side)")
            declared.append((attacker, target, o, hit, side))
    triggers = {mech_a.side_name: [], mech_b.side_name: []}
    for attacker, target, o, hit, side in declared:
        if hit:
            loc = _location(o["table"], side, target)
            config.log(f"    {o['name']} hits {target.side_name}'s {loc} for {o['damage']}.")
            if loc == "Head":
                target.pilot_hits += 1
                mark_consciousness_check_pending(target)
            apply_damage(target, loc, o["damage"], armor_field="rear_armor" if side == "rear" else "armor",
                         damage_type=DamageType.PHYSICAL)
            if o.get("kick"):
                triggers[target.side_name].append(("kicked", 0))
        elif o.get("kick"):
            triggers[attacker.side_name].append(("missed a kick", 0))
    for attacker, target in charges:                     # damage, then displacement (p.78, p.113)
        for name, extra in charge.resolve_hit(attacker, target, terrain_map).items():
            triggers[name].extend(extra)
    for m in (mech_a, mech_b):
        attack_resolution._with_piloting(m, piloting_rolls.resolve_attack_phase_psr,
                                         forced_triggers=tuple(triggers[m.side_name]))
        piloting_rolls.resolve_consciousness_checks(m, "Physical Attack Phase")
