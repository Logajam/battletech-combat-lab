"""
INTEGRATION__princess_fire.py  (NEW 2026-10-27, Claude - the Princess bot, part 1)

MegaMek's Princess bot (v0.50.07, megamek/client/bot/princess) - its fire
control and its physical-attack choice, ported onto this project's rules
engine (Daniel, 2026-10-27: "I would like to make a clone of Megamek's
Princess bot to compare it against"). The movement ranker is
INTEGRATION__princess; the switch between bots is INTEGRATION__bots.

What is Princess's and what is the project's: the RULES (which weapons can
fire, to-hit numbers, cluster hits, ammunition kinds, AMS, arcs, twists)
stay the project's - the same numbers Gladiator sees. Princess's own parts
are the CHOICES: which weapons make up the firing plan (FireControl), how a
plan is valued (calculateUtility), and which physical attack to throw
(PhysicalCalculator - Princess still uses the original test bot's).

=== FIRING PLAN UTILITY (FireControl.calculateUtility) ===
    utility = (expected damage + 10 x expected criticals + 50 x kill chance)
              x log10(2 x target's damage at range 1 + 10)
              - 30 x (expected damage / target HP, when that is 0.5 or more)
              - 5 x heat over the tolerance
  - expected criticals per weapon (WeaponFireInfo.initDamage): 0.028 x 0.611
    x P(hit) (the roll of 2), plus, per hit location (by attack direction,
    ProbabilityCalculator's tables), P(location) x P(hit) when the weapon's
    EXPECTED damage beats the location's armor + structure (that also counts
    as a kill for the center torso and the head), else P(location) x P(hit)
    x 0.611 when it beats the armor alone.
  - kill chance of the plan = 1 - product of (1 - each weapon's).
  - log10(...) is calcTargetPotentialDamageMultiplier: the target's summed
    weapon damage at range 1 (FireControl.getMaxDamageAtRange - cluster
    weapons count their rack size), scaled by max self-preservation (30) /
    self-preservation (15 at the default slider) = 2.
  - heat tolerance (calcHeatTolerance) = heat sinks' dissipation - current
    heat - always-on heat (stealth) + 5. Movement heat is not counted
    (v0.50.07 reads the heat at the start of the turn).
  - Plans (calcFiringPlansUnderHeat): the heatless weapons, then for each
    heat level 1..the alpha strike's heat the best plan made by adding one
    weapon to a cheaper level's plan; the best utility wins, and nothing is
    fired if no plan beats 0. A "guess" (the movement ranker's estimate of a
    spot, both its own fire and the enemy's) takes the alpha strike outright
    when its heat is within the tolerance (guessBestFiringPlanUnderHeat).
  - Torso twists / arm flips: each is tried and the best utility kept
    (determineBestFiringPlan) - the project's arc loop does that, comparing
    the utility this returns.
  Not ported: damage already assigned by friendly units (always 0 in a duel),
  command / strategic / priority targets, ammo conservation, the rotary
  spin-up threshold (rate of fire stays the project's stub).

=== PHYSICAL ATTACKS (PhysicalCalculator.getBestPhysicalAttack) ===
Every punch (each arm, both arms), kick, club / physical weapon and push
is worth P(hit) x damage x punchThroughMod (a bonus for damage that gets
past the armor in the arc it lands on); a kick adds the target's expected
fall damage and subtracts its own from a miss; a push is worth the target's
fall (its total armor if pushed off the board). The best one above 0 is
made. No new torso twist: the attack is made as the mech stands.
"""

import math

import INTEGRATION__config as config
import INTEGRATION__weapon_rules as weapon_rules
from damage_resolution import get_weapons, TRANSFER_MAP  # noqa: E402 - MECHSIM
from mech_state import has_torso_cockpit, compute_walk_mp, compute_jump_mp  # noqa: E402 - MECHSIM
import piloting_rolls  # noqa: E402 - MECHSIM
import hex_geometry  # noqa: E402 - PATHFINDER
from combat import hit_probability  # noqa: E402 - PATHFINDER

# =============================================================================
# ===========================  BEHAVIOR SETTINGS  =============================
# =============================================================================
# BehaviorSettings.java: each slider (0-10) indexes one of these tables.
FALL_SHAME_VALUES = (10, 40, 80, 100, 160, 500, 500, 500, 500, 500, 500)
BRAVERY_VALUES = (0.1, 0.3, 0.6, 0.9, 1.2, 1.5, 1.8, 2.1, 2.4, 2.7, 3.0)
HYPER_AGGRESSION_VALUES = (0.25, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 10, 50, 500)
SELF_PRESERVATION_VALUES = (2.5, 5, 7.5, 10, 12.5, 15, 17.5, 20, 22.5, 25, 30)


def setting(name):
    """A slider's value from config.PRINCESS_BEHAVIOR (its index 0-10)."""
    table = {"fall_shame": FALL_SHAME_VALUES, "bravery": BRAVERY_VALUES,
             "hyper_aggression": HYPER_AGGRESSION_VALUES, "self_preservation": SELF_PRESERVATION_VALUES}[name]
    return table[max(0, min(10, int(config.PRINCESS_BEHAVIOR[name])))]


# =============================================================================
# ===========================  FIRE CONTROL CONSTANTS  ========================
# =============================================================================
DAMAGE_UTILITY = 1.0
CRITICAL_UTILITY = 10.0
KILL_UTILITY = 50.0
OVERHEAT_DISUTILITY = 5.0
TARGET_HP_FRACTION_DEALT_UTILITY = -30.0
TARGET_POTENTIAL_DAMAGE_UTILITY = 1.0
HEAT_TOLERANCE_BONUS = 5          # calcHeatTolerance: "+ 5 // todo add Heat Tolerance to Behavior Settings"
ROLL_TWO = 0.028                  # WeaponFireInfo: "there's always the chance of rolling a '2'"
EXPECTED_CRITICAL_HIT_COUNT = 0.611   # ProbabilityCalculator: (9 + 2 x 5 + 3) / 36

# ProbabilityCalculator's hit-location odds, in Mek location order: head, CT, RT,
# LT, RA, LA, RL, LL. Front and rear fire use the front table (rear armor for a
# rear shot); "right" / "left" are fire from that side.
MEK_LOCATIONS = ("Head", "Center Torso", "Right Torso", "Left Torso", "Right Arm", "Left Arm",
                 "Right Leg", "Left Leg")
QUAD_NAMES = {"Right Arm": "Front Right Leg", "Left Arm": "Front Left Leg",
              "Right Leg": "Rear Right Leg", "Left Leg": "Rear Left Leg"}
HIT_ODDS = {
    "front": tuple(n / 36 for n in (1, 7, 5, 5, 5, 5, 4, 4)),
    "right": tuple(n / 36 for n in (1, 5, 7, 4, 7, 3, 7, 3)),
    "left": tuple(n / 36 for n in (1, 5, 4, 7, 3, 7, 3, 7)),
}
HIT_ODDS["rear"] = HIT_ODDS["front"]


def _location_name(mech, loc):
    return QUAD_NAMES.get(loc, loc) if mech.mech_type in ("quad", "quadvee") else loc


def _armor(mech, loc, rear):
    entry = mech.locations[loc]
    value = entry.get("rear_armor", entry["armor"]) if rear else entry["armor"]
    return max(0, value)


# =============================================================================
# ===========================  DAMAGE ALREADY ASSIGNED  =======================
# =============================================================================
# Princess.damageMap: the expected damage the bot's own units have already
# declared at each enemy this Ranged Attack Phase (filled as each unit's
# attacks are declared, in declaration order; Princess.calculateFiringTurn).
# FireControl.calcDamageAllocationUtility reads it so a team stops piling onto
# an enemy it already expects to kill. Keyed by id(target); one map for the
# phase, because every Princess unit on the board is "the bot's own units"
# (MegaMek counts only the same player's units - not allies - per side; a
# team here is the owner, so the map is kept per team).
ALREADY_DESTROYED_OVERKILL = 100.0     # FireControl.ALREADY_DESTROYED_OVERKILL
_assigned = {}


def reset_assigned():
    """Princess.calculateFiringTurn's start of phase: nothing assigned yet."""
    _assigned.clear()


def assigned_damage(team, target):
    """Princess.getDamageAlreadyAssigned: damage `team`'s units have declared at target."""
    return _assigned.get((team, id(target)), 0.0)


def assign_damage(team, target, damage):
    _assigned[(team, id(target))] = assigned_damage(team, target) + damage


def overkill_fraction(existing, expected, hp):
    """FireControl.calcDamageAllocationUtility: 100 for a target already
    expected destroyed by friends; else the share of the target's HP the
    friends' damage plus this plan's would deal, when that reaches half
    (below that, shoot as normal - no spreading); else 0."""
    if existing / hp >= 1.0:
        return ALREADY_DESTROYED_OVERKILL
    fraction = (existing + expected) / hp
    return fraction if fraction >= 0.5 else 0.0


def max_damage_at_range(mech, distance):
    """FireControl.getMaxDamageAtRange: the summed damage of every weapon in
    range at `distance` (beyond Long is out; inside the minimum range is
    in), no to-hit. Cluster weapons count their rack size ("only a little
    over half of a cluster will generally hit ... still better than just
    discounting them completely"); a weapon without a fixed damage counts 0."""
    total = 0
    for w in get_weapons(mech):
        if weapon_rules.is_ams(w) or not w.weapon_range or w.weapon_range.get("long") is None:
            continue
        if distance > w.weapon_range["long"]:
            continue
        damage = (w.rack_size or 0) if weapon_rules.is_cluster(w) else (w.damage_per_shot or 0)
        if damage > 0:
            total += damage
    return total


def total_hp(mech):
    """Compute.getTargetTotalHP for a 'Mech: armor (front and rear) + structure."""
    return sum(max(0, e["armor"]) + max(0, e.get("rear_armor", 0)) + max(0, e["structure"])
               for e in mech.locations.values() if not e["destroyed"])


def weapon_crits_and_kill(target, side, p_hit, expected, on_hit=None, odds=None):
    """(expected criticals, kill chance) of one weapon with P(hit) p_hit
    against target from `side` - WeaponFireInfo.initDamage. v0.50.07 compares
    the EXPECTED damage (P(hit) x damage on a hit) with each location's armor
    (+ structure); the modern code compares the damage ON A HIT (on_hit given:
    destroyed at >= armor + structure, a critical chance above the armor).
    odds: the hit-location odds to use (default: the standard table by side)."""
    crits = ROLL_TWO * EXPECTED_CRITICAL_HIT_COUNT * p_hit
    kill = 0.0
    odds = odds or HIT_ODDS.get(side or "front", HIT_ODDS["front"])
    rear = side == "rear"
    for i, base in enumerate(MEK_LOCATIONS):
        loc = _location_name(target, base)
        if loc not in target.locations:
            continue
        # A destroyed location passes inward (Mek.getInnerLocation); a destroyed head is skipped.
        while target.locations[loc]["destroyed"] and loc != "Center Torso":
            if loc == "Head" or loc not in TRANSFER_MAP:
                loc = None
                break
            loc = TRANSFER_MAP[loc]
        if loc is None:
            continue
        p_loc = odds[i]
        if p_loc == 0:
            continue
        armor = _armor(target, loc, rear)
        structure = max(0, target.locations[loc]["structure"])
        destroyed = (on_hit >= armor + structure) if on_hit is not None else (expected > armor + structure)
        if destroyed:
            crits += p_loc * p_hit
            if loc == "Center Torso" or (loc == "Head" and not has_torso_cockpit(target)):
                kill += p_loc * p_hit
        elif (on_hit if on_hit is not None else expected) > armor:
            crits += p_loc * p_hit * EXPECTED_CRITICAL_HIT_COUNT
    return crits, kill


# Modern FireControl (2026-10-27): a TSM 'Mech wants its heat up to the activation band.
TSM_DESIRED_HEAT = 9
TSM_HEAT_CEILING = 13
TSM_ACTIVATION_UTILITY = 20.0


def modern():
    """True for the modern Princess (config.PRINCESS_VERSION)."""
    return config.PRINCESS_VERSION == "modern"


def heat_tolerance(mech, dissipation, unavoidable):
    """calcHeatTolerance: sinks - heat the 'Mech carries into the Heat Phase
    whatever it fires (`unavoidable`) + 5. Modern: a TSM 'Mech may run up to
    TSM_HEAT_CEILING at the end of the turn."""
    tolerance = dissipation - unavoidable + HEAT_TOLERANCE_BONUS
    if modern() and getattr(mech, "has_tsm", False):
        tolerance = max(tolerance, dissipation - unavoidable + TSM_HEAT_CEILING)
    return tolerance


def tsm_heat_bonus(mech, dissipation, unavoidable, weapon_heat):
    """applyTsmHeatIncentive: a TSM 'Mech's plan earns up to 20 for ending the
    turn near heat 9 (falling to 0 at 13)."""
    if not getattr(mech, "has_tsm", False) or weapon_heat <= 0:
        return 0.0
    projected = max(0, unavoidable + weapon_heat - dissipation)
    if projected <= 0:
        return 0.0
    if projected < TSM_DESIRED_HEAT:
        return TSM_ACTIVATION_UTILITY * projected / TSM_DESIRED_HEAT
    band = max(1, TSM_HEAT_CEILING - TSM_DESIRED_HEAT)
    return TSM_ACTIVATION_UTILITY * max(0.0, 1.0 - (projected - TSM_DESIRED_HEAT) / band)


# =============================================================================
# ===========================  FIRE CONTROL  ==================================
# =============================================================================
class FireControl:
    """Princess's firing-plan choice, handed to weapon_selection.fire_control.
    guess=True: the movement ranker's estimate (alpha strike when within the
    heat limit); False: the real attack (best plan by utility). One object per
    decision - it caches each target's multiplier and HP. `self_mech`: the
    Princess unit whose move is being ranked (guess mode, modern) - its own
    plans are limited by the tolerance with the move's heat, the enemy's by
    sinks - heat + 5 (calculateMyDamagePotential / calculateDamagePotential)."""

    def __init__(self, guess, self_mech=None):
        self.guess = guess
        self.self_mech = self_mech
        self._target = {}
        self.last = None            # (expected damage, utility) of the last plan chosen (for the log)

    def _target_terms(self, target):
        got = self._target.get(id(target))
        if got is None:
            potential = max_damage_at_range(target, 1)
            scale = SELF_PRESERVATION_VALUES[10] / setting("self_preservation")
            mult = 1.0 if potential == 0 else math.log10(TARGET_POTENTIAL_DAMAGE_UTILITY * scale * potential + 10)
            got = self._target[id(target)] = (mult, max(1, total_hp(target)))
        return got

    def _limits(self, mech, dissipation, other_heat, movement_heat):
        """(utility tolerance, alpha-strike heat limit, unavoidable heat)."""
        if not modern():
            tolerance = dissipation - mech.current_heat - other_heat + HEAT_TOLERANCE_BONUS
            return tolerance, tolerance, mech.current_heat + other_heat
        if not self.guess:                                  # firing: the move is committed (heatBuildup)
            unavoidable = mech.current_heat + movement_heat + other_heat
            tolerance = heat_tolerance(mech, dissipation, unavoidable)
            return tolerance, tolerance, unavoidable
        if mech is self.self_mech:                          # my move, not yet made
            tolerance = heat_tolerance(mech, dissipation, mech.current_heat + other_heat)
            limit = heat_tolerance(mech, dissipation, mech.current_heat + other_heat + movement_heat)
            return tolerance, limit, mech.current_heat + other_heat + movement_heat
        unavoidable = mech.current_heat + movement_heat + other_heat   # the enemy: its move is made
        return (heat_tolerance(mech, dissipation, unavoidable),
                dissipation - mech.current_heat + HEAT_TOLERANCE_BONUS, unavoidable)

    def __call__(self, mech, candidates, dissipation, other_heat, planner, side, movement_heat=0):
        target = planner.target if planner is not None else None
        tolerance, limit, unavoidable = self._limits(mech, dissipation, other_heat, movement_heat)
        mult, hp = self._target_terms(target) if target is not None else (1.0, 1)
        # Damage this unit's friends have already declared at the target (not in a movement guess:
        # Princess leaves its damageMap empty during movement).
        existing = 0.0 if (self.guess or target is None) else assigned_damage(getattr(mech, "team", None), target)
        infos = []
        for w, expected, heat, tn in candidates:
            p = hit_probability(tn) if tn <= 12 else 0.0
            if p <= 0 or expected <= 0:
                continue                         # an impossible shot is never in a plan
            if target is None:
                crits, kill = 0.0, 0.0
            else:
                crits, kill = weapon_crits_and_kill(target, side, p, expected,
                                                    on_hit=expected / p if modern() else None)
            infos.append((w, expected, heat, crits, kill))

        def utility(plan):
            _, ed, crits, survive, heat = plan
            u = (DAMAGE_UTILITY * ed + CRITICAL_UTILITY * crits + KILL_UTILITY * (1 - survive)) * mult
            u += TARGET_HP_FRACTION_DEALT_UTILITY * overkill_fraction(existing, ed, hp)
            return u - OVERHEAT_DISUTILITY * max(0, heat - tolerance)

        def add(plan, info):
            ids, ed, crits, survive, heat = plan
            w, e, h, c, k = info
            return (ids | {id(w)}, ed + e, crits + c, survive * (1 - k), heat + h)

        empty = (frozenset(), 0.0, 0.0, 1.0, 0)
        alpha = empty
        for info in infos:
            alpha = add(alpha, info)
        if self.guess and alpha[4] <= limit:
            return self._result(mech, alpha, utility(alpha))
        # calcFiringPlansUnderHeat: plans[h] = the best plan found with heat h.
        plans = [empty]
        for info in infos:
            if info[2] == 0:
                plans[0] = add(plans[0], info)
        nonzero = [info for info in infos if info[2] != 0]
        for level in range(1, max(0, alpha[4]) + 1):
            best = plans[level - 1]
            best_u = utility(best)
            for info in nonzero:
                left = level - info[2]
                if left >= 0 and id(info[0]) not in plans[left][0]:
                    test = add(plans[left], info)
                    u = utility(test)
                    if u > best_u:
                        best, best_u = test, u
            plans.append(best)
        # getBestFiringPlanUnderHeat - the modern firing choice adds the TSM heat incentive.
        bonus = ((lambda plan: tsm_heat_bonus(mech, dissipation, unavoidable, plan[4]))
                 if modern() and not self.guess else (lambda plan: 0.0))
        chosen, chosen_u = empty, bonus(empty)
        for plan in plans:
            u = utility(plan) + bonus(plan)
            if u > chosen_u:
                chosen, chosen_u = plan, u
        return self._result(mech, chosen, chosen_u)

    def _result(self, mech, plan, u):
        ids = plan[0]
        self.last = (plan[1], u)
        return [w for w in get_weapons(mech) if id(w) in ids], u, plan[4]


# =============================================================================
# ===========================  PHYSICAL ATTACKS  ==============================
# =============================================================================
def punch_through_mod(target, table, side, damage, group):
    """PhysicalCalculator.punchThroughMod: 1 + a bonus for every location in
    the arc whose armor `damage`, taken in hits of `group`, would get
    through - halved for each further pass. table: "standard" / "punch" /
    "kick". (The original reads the right leg twice on the standard table;
    kept.)"""
    if damage <= 0 or group <= 0:
        return 1.0
    loc = lambda name: _location_name(target, name)                     # noqa: E731
    armor = lambda name, rear=False: (_armor(target, loc(name), rear)    # noqa: E731
                                      if loc(name) in target.locations else 0)
    rear = side != "front"
    if table == "standard":
        values = [armor("Head"), armor("Center Torso", rear), armor("Right Torso", rear),
                  armor("Left Torso", rear), armor("Right Arm"), armor("Left Arm"), armor("Right Leg"),
                  armor("Right Leg")]
    elif table == "punch":
        if side == "right":
            values = [armor("Head"), armor("Center Torso"), armor("Right Torso"), armor("Right Arm")]
        elif side == "left":
            values = [armor("Head"), armor("Center Torso"), armor("Left Torso"), armor("Left Arm")]
        else:
            r = side == "rear"
            values = [armor("Head"), armor("Center Torso", r), armor("Right Torso", r), armor("Left Torso", r),
                      armor("Right Arm"), armor("Left Arm")]
    else:                                                                  # kick
        values = []
        if side in ("front", "rear", "right"):
            values.append(armor("Right Leg"))
        if side in ("front", "rear", "left"):
            values.append(armor("Left Leg"))
    multiplier, base, hit_total = 1.0, 0.5, 0.0
    while hit_total <= damage:
        hit_total += group
        multiplier += base * sum(1 for v in values if hit_total > v)
        base /= 2.0
    return multiplier


def falling_damage(p, mech):
    """PhysicalCalculator.calculateFallingDamage: p x P(failing its
    piloting roll) x a tenth of its tonnage."""
    tn = mech.piloting + piloting_rolls.preexisting_modifier(mech)
    return p * (1.0 - hit_probability(tn)) * mech.mass * 0.1


def _mobility(mech, floor=1.0):
    walk = compute_walk_mp(mech)
    jump = compute_jump_mp(mech)
    return math.sqrt(1.0 / walk + jump) if walk > 0 else max(floor, math.sqrt(jump))


def choose_physical(attacker, target, terrain_map):
    """getBestPhysicalAttack: (base TN, [options], arc action) of the attack
    with the most expected worth, or None. Same return as
    physical.choose_attack."""
    import INTEGRATION__physical as physical             # physical imports the attack modules
    import INTEGRATION__attack_resolution as attack_resolution
    import INTEGRATION__arcs as arcs
    from mech_state import is_destroyed
    if is_destroyed(attacker) or is_destroyed(target) or attacker.hex == target.hex:
        return None
    options = physical.attack_options(attacker, target, terrain_map)
    if not options:
        return None
    base = physical._base_tn(attacker, target, terrain_map)
    side = attack_resolution.attack_side(hex_geometry.parse_hex_label(attacker.hex),
                                         hex_geometry.parse_hex_label(target.hex),
                                         hex_geometry.compass_to_facing(target.facing), terrain_map)
    p = lambda o: hit_probability(base + o["mod"])         # noqa: E731
    scored = []
    punches = options.get("punch", [])
    for o in punches:
        d = p(o) * o["damage"]
        scored.append((d * punch_through_mod(target, o["table"], side, d, d), [o]))
    if len(punches) == 2:
        d = sum(p(o) * o["damage"] for o in punches)
        scored.append((d * punch_through_mod(target, punches[0]["table"], side, d, d / 2.0), list(punches)))
    for o in options.get("kick", []):
        d = p(o) * o["damage"]
        d *= punch_through_mod(target, o["table"], side, d, d)
        target_falls = falling_damage(p(o), target)
        self_falls = falling_damage(1.0 - p(o), attacker) * _mobility(attacker, floor=0.0)
        scored.append((d + target_falls - self_falls, [o]))
    for kind in ("club", "weapon"):
        for o in options.get(kind, []):
            d = p(o) * o["damage"]
            scored.append((d * punch_through_mod(target, o["table"], side, d, d), [o]))
    for o in options.get("push", []):
        scored.append((_push_worth(attacker, target, p(o), terrain_map), [o]))
    best = None
    for worth, picks in scored:
        if worth > 0 and (best is None or worth > best[0]):
            best = (worth, picks)
    if best is None:
        return None
    return base, best[1], arcs.current_action(attacker)


def _push_worth(attacker, target, p, terrain_map):
    """getBestPhysicalAttack's push: off the board, the target's total armor
    x P(hit); else its fall (x 1 + levels down), x punchThroughMod (doubled
    into water), x its mobility factor."""
    a_xy = hex_geometry.parse_hex_label(attacker.hex)
    t_xy = hex_geometry.parse_hex_label(target.hex)
    import combat
    import INTEGRATION__water as water
    dx, dy = hex_geometry.FACING_DELTAS[combat._direction_facing(a_xy, t_xy)]
    try:
        label = hex_geometry.hex_label(t_xy[0] + dx, t_xy[1] + dy)
    except ValueError:
        label = None
    hexes = terrain_map["hexes"]
    if label is None or label not in hexes:
        return sum(max(0, e["armor"]) + max(0, e.get("rear_armor", 0)) for e in target.locations.values()) * p
    drop = max(0, hexes[target.hex]["level"] - hexes[label]["level"])
    dmg = falling_damage(p, target) * (1.0 + drop)
    breach = punch_through_mod(target, "standard", "front", dmg, min(dmg, 5.0))
    if breach > 1 and water.depth_at(label, terrain_map) >= 1:
        breach *= 2.0
    return dmg * _mobility(target) * breach
