"""
INTEGRATION__movement_attacks.py  (NEW 2026-10-20, Claude - Pile 4 helper)

The attacks a mech DECLARES in the Movement Phase - charges (Core p.78,
INTEGRATION__charge) and death from above (pp.79-80, INTEGRATION__dfa) - as
movement-picker options, plus the displacement arithmetic they share with
pushes (p.83, pp.113-115).

Both can only target a mech that has finished moving (or is immobile), so in
a two-mech battle the SECOND mover is the one who can make them. That is also
what the first mover has to fear: its two-ply look-ahead (INTEGRATION__
movement_selection._modeled_reply) asks, for every spot it might end on, the
same question the real second mover will ask - and so it learns to stay away
from spots where a charge or a DFA pays.

=== THE DECISION (Daniel, 2026-10-20) ===
"gate that decision tree to ask if a charge at this movement mode does more
damage than normal attacks and physicals before thinking about it":
  1. For each candidate (stop hex, facing, mode), its expected damage worth
     (exposure x structure weighted, INTEGRATION__physical.Worth, including
     what displacement does - pushed off the board = the target's whole
     remaining armor + structure, pushed 2+ levels down = the fall) must beat
     the best ordinary attack (ranged + physical) any spot in that MODE offers.
  2. Survivors are scored like any spot - dealt / (return fire at the stop hex,
     the target's physical attacks if allowed, the attacker's own expected
     self-damage + movement PSR cost) - and the best is used if its score beats
     the ordinary pick's.

=== INDEX ===
MoverIndex builds the mover's reachable ground states and jump landings ONCE
per decision; finding the charges / DFAs against a given target position is
then a lookup on the target's six neighbours (charges) or a distance / height
check (DFA), cheap enough to run for every first-mover spot in the two-ply.

Not priced: the +2 PSRs after a hit, a 0-level fall's chance after a push or
an ordinary hit (Daniel's PSR rule: only Movement-phase PSRs count), domino
effects (no third mech), wind, water halving.
"""

import dataclasses
import math
from typing import Dict, List, NamedTuple, Optional

import INTEGRATION__config as config
import INTEGRATION__attack_resolution as attack_resolution
import INTEGRATION__physical as physical
import INTEGRATION__water as water
from mech_state import pilot_hit, head_hit_hurts_pilot, torso_cockpit_sensor_penalty  # p.203
from mech_state import is_destroyed, is_immobile, compute_walk_mp, compute_running_mp
import hex_geometry
import combat
import piloting_rolls
from mech_state import ground_level_limited  # pp.90, 99, 238-239
import terrain_rules
from los import hex_distance, hex_line, trace_los_path

IMMOBILE_COMPARATIVE_PILOTING = 4        # p.77
STANDING_HEIGHT, PRONE_HEIGHT = 2, 1     # unit height in levels (pp.57, 79)


class Pose(NamedTuple):
    """Where a (possibly hypothetical) target stands for these attacks."""
    label: str
    xy: tuple
    facing: int            # 0-5
    tmm: int
    prone: bool


def pose_of(mech):
    return Pose(mech.hex, hex_geometry.parse_hex_label(mech.hex), hex_geometry.compass_to_facing(mech.facing),
                attack_resolution._target_tmm(mech), mech.prone)


def pose_at(label, facing_compass, fc, mode, prone=False):
    return Pose(label, hex_geometry.parse_hex_label(label), hex_geometry.compass_to_facing(facing_compass),
                combat.fc_to_tmm(fc, jumped=(mode == "Jump")), prone)


# =============================================================================
# ==========================  SHARED NUMBERS  =================================
# =============================================================================
def groupings(damage):
    return [5] * (damage // 5) + ([damage % 5] if damage % 5 else [])


def comparative_modifier(attacker, target):
    return attacker.piloting - (IMMOBILE_COMPARATIVE_PILOTING if is_immobile(target) else target.piloting)


def terrain_modifier(a_xy, t_xy, terrain_map):
    """The LOS terrain modifier without partial cover (charges ignore it, p.78)."""
    trace = trace_los_path(a_xy, t_xy, terrain_map)
    cover = trace.steps[-1].partial_cover if trace.steps else 0
    return trace.result.modifier - cover


def hit_chance(tn):
    return combat.hit_probability(tn) if tn <= 12 else 0.0


_WORTH: Dict[int, physical.Worth] = {}


def worth_of(mech):
    """physical.Worth for mech, rebuilt when its armor / structure changed."""
    key = (id(mech), sum(v.get("armor", 0) + v.get("rear_armor", 0) + v.get("structure", 0)
                         for v in mech.locations.values()))
    w = _WORTH.get(key)
    if w is None:
        if len(_WORTH) > 256:
            _WORTH.clear()
        w = _WORTH[key] = physical.Worth(mech)
    return w


def table_worth(damage, mech, table, side):
    """Worth of `damage` in 5-point groups rolled on `table` against `side`."""
    w = worth_of(mech)
    return sum(g * w.factor(table, side, g) for g in groupings(damage))


def total_hp(mech):
    return attack_resolution.total_hp(mech)


def apply_groups(mech, damage, table, side, label, spike_wear=False, onto=None):
    """Deal `damage` to mech in 5-point groupings, each rolled on `table`
    ("standard" / "punch" / "kick") against `side` (p.87). Spikes (p.196,
    2026-10-21, INTEGRATION__physical_gear): a grouping that lands on a
    spiked location is cut by 4 (minimum 1); spike_wear - the mech used its
    spikes offensively in this charge, so each spiked location hit rolls to
    lose its cluster. Returns [(location, was it spiked)] in order."""
    import INTEGRATION__physical_gear as gear
    from mech_state import DamageType, mark_consciousness_check_pending
    from damage_resolution import apply_damage
    hits = []
    for g in groupings(damage):
        if is_destroyed(mech):
            return hits
        loc = onto or physical._location(table, side, mech)       # onto: a raised shield's arm (p.195)
        dmg = water.physical_damage(mech, loc, g)                 # halved under water (p.77)
        config.log(f"    {label}: {dmg} to {mech.side_name}'s {loc}"
                   f"{' (halved: under water, p.77)' if dmg != g else ''}.")
        dmg, spiked = gear.spike_reduce(mech, loc, dmg, label)
        dmg = gear.shield_absorb(mech, loc, dmg, side)            # p.195
        if loc == "Head" and head_hit_hurts_pilot(mech):
            pilot_hit(mech, head=True)              # both warriors with a command console (p.203)
        apply_damage(mech, loc, dmg, armor_field="rear_armor" if side == "rear" else "armor",
                     damage_type=DamageType.PHYSICAL)
        if spiked and spike_wear:
            gear.spike_wear(mech, loc)
        hits.append((loc, spiked))
    return hits


# =============================================================================
# ==========================  DISPLACEMENT  ===================================
# =============================================================================
def neighbour(label, direction):
    """The label of the hex one step from `label` in facing direction 0-5,
    or None off the coordinate grid."""
    x, y = hex_geometry.parse_hex_label(label)
    dx, dy = hex_geometry.FACING_DELTAS[direction]
    try:
        return hex_geometry.hex_label(x + dx, y + dy)
    except ValueError:
        return None


def displacement(from_label, direction, terrain_map):
    """Where a mech on from_label pushed one hex in `direction` ends up
    (pp.113-114): ("off", None, 0) off the board (destroyed), ("blocked",
    None, 0) for a hex 3+ levels up (prohibited), else ("moved", label,
    levels dropped).
    Passive buildings (2026-10-21, config.PASSIVE_BUILDINGS): a building
    can't be entered from the ground, so a push from the ground into one is
    blocked like a wall; from a roof the usual level rule applies."""
    to = neighbour(from_label, direction)
    hexes = terrain_map["hexes"]
    if to is None or to not in hexes:
        return "off", None, 0
    if hexes[to].get("building") and not hexes[from_label].get("building"):
        return "blocked", None, 0
    drop = hexes[from_label]["level"] - hexes[to]["level"]
    if drop <= -3:
        return "blocked", None, 0
    return "moved", to, drop


def displacement_worth(target, from_label, direction, terrain_map):
    """What being pushed this way costs the target: its whole remaining
    armor + structure off the board (Daniel: "should probably be evaluated as
    taking 100% damage"), the fall's worth 2+ levels down (p.115:
    ceil(tons/10) x (levels + 1), front table), else 0."""
    kind, _, drop = displacement(from_label, direction, terrain_map)
    if kind == "off":
        return total_hp(target)
    if kind == "moved" and drop >= 2:
        return table_worth(math.ceil(target.mass / 10) * (drop + 1), target, "standard", "front")
    return 0.0


# =============================================================================
# ==========================  INDEX  ==========================================
# =============================================================================
class MoverIndex:
    """The mover's reachable states for movement attacks, built once."""

    def __init__(self, mover, terrain_map, standup_mp=None):
        import INTEGRATION__ranged_combat as ranged_combat     # ranged_combat imports physical first
        self.mover, self.terrain_map, self.standup_mp = mover, terrain_map, standup_mp
        self.walk = compute_walk_mp(mover)
        self.budget = compute_running_mp(mover) if standup_mp is None else standup_mp
        self.level_limit = terrain_rules.max_level_change(ground_level_limited(mover))
        self.ground: Dict[tuple, List[tuple]] = {}
        # Forward-only states: a charge ends with a forward move into the target's hex, and the
        # hex count would restart after a backward step (backward charges not offered - see
        # INTEGRATION__RULES_REVIEW.md).
        for x, y, facing, fc, mode, mp in ranged_combat.movement_options(mover, terrain_map, standup_mp=standup_mp,
                                                                         backward=False):
            if mode != "Jump":
                self.ground.setdefault((x, y, facing), []).append((fc, mp))
        self.jump_mp = water.jump_mp(mover) if standup_mp is None and not mover.prone else 0   # water: p.50
        self.start_label = mover.hex
        self.start_xy = hex_geometry.parse_hex_label(mover.hex) if mover.hex else None
        self.jump_hexes = set()
        if self.jump_mp > 0 and mover.hex is not None:
            sx, sy = self.start_xy
            self.jump_hexes = {(x, y) for x, y, _ in combat.build_jump_states(sx, sy, self.jump_mp, terrain_map)}

    def charge_states(self, pose):
        """[{hex, facing, mode, fc, mp_spent, charge}] - stop next to the
        target facing it with the MP to enter its hex (p.78); fc / mp_spent
        include the move into the target's hex. Best (most hexes, least MP)
        per (hex, mode)."""
        hexes = self.terrain_map["hexes"]
        t_info = hexes[pose.label]
        best = {}
        for d in range(6):
            n = neighbour(pose.label, d)
            if n is None or n not in hexes:
                continue
            nx, ny = hex_geometry.parse_hex_label(n)
            facing = (d + 3) % 6                         # from n, the target is back the way we came
            states = self.ground.get((nx, ny, facing))
            if not states:
                continue
            # The final step into the target's hex follows the ground-movement
            # rules (level-change limit, roofs - terrain_rules.step_cost, pp.46-47, 134).
            cost = terrain_rules.step_cost(hexes[n], t_info, self.level_limit)
            if cost is None:
                continue
            # Water (p.77, INTEGRATION__water): no charge at a fully submerged target from
            # above the water, nor from under water at a target on land.
            allowed = water.physical_allowed(water.state_at(n, False, self.terrain_map),
                                             water.state_at(pose.label, pose.prone, self.terrain_map))
            if allowed is not None and "charge" not in allowed:
                continue
            for fc, mp in states:
                total = mp + cost
                if total > self.budget:
                    continue
                mode = "Run" if self.standup_mp is not None else combat.classify_movement_mode(total, self.walk)
                key = (n, facing, mode)
                cand = (fc + 1, -total)
                if key not in best or cand > best[key]:
                    best[key] = cand
        return [{"hex": n, "facing": hex_geometry.facing_to_compass(f), "mode": m, "fc": fc, "mp_spent": -neg,
                 "charge": True} for (n, f, m), (fc, neg) in best.items()]

    def dfa_states(self, pose):
        """[{hex, facing, mode "Jump", fc, mp_spent, dfa}] - a jump that can
        land on the target's hex (distance, path, and clearing the target's
        LOS level: its hex level + its height, pp.50, 79), stopping in the
        hex next to it along the path."""
        if not self.jump_hexes or pose.xy not in self.jump_hexes:
            return []
        if water.state_at(pose.label, pose.prone, self.terrain_map) == water.SUBMERGED:
            return []                    # out of reach from the air (p.77, INTEGRATION__water)
        dist = hex_distance(self.start_xy, pose.xy)
        hexes = self.terrain_map["hexes"]
        need = hexes[pose.label]["level"] + (PRONE_HEIGHT if pose.prone else STANDING_HEIGHT) \
            - hexes[self.start_label]["level"]
        if dist > self.jump_mp or need > self.jump_mp:
            return []
        if dist == 1:
            stop = self.start_xy
        else:
            stop = hex_line(self.start_xy, pose.xy)[-2][0]
        label = hex_geometry.hex_label(*stop)
        facing = combat._direction_facing(stop, pose.xy)
        return [{"hex": label, "facing": hex_geometry.facing_to_compass(facing), "mode": "Jump", "fc": dist,
                 "mp_spent": dist, "dfa": True}]


# =============================================================================
# ==========================  THE DECISION  ===================================
# =============================================================================
def values(mover, target, pose, state, terrain_map):
    """(dealt worth, attacker self-damage worth, P(hit), TN, raw damage,
    side on target, may the target attack it physically?) for one
    charge / DFA state."""
    import INTEGRATION__charge as charge
    import INTEGRATION__dfa as dfa
    a_xy = hex_geometry.parse_hex_label(state["hex"])
    side = attack_resolution.attack_side(a_xy, pose.xy, pose.facing, terrain_map)
    direction = combat._direction_facing(a_xy, pose.xy)
    # Damage to the target's underwater locations counts half (p.77, INTEGRATION__water).
    t_water = water.state_at(pose.label, pose.prone, terrain_map)
    wet = lambda table, s: water.physical_value_factor(target, t_water, table, s)  # noqa: E731
    if state.get("charge"):
        tn = charge.to_hit(mover, state["mode"], target, a_xy, pose.xy, terrain_map, pose.tmm)
        p = hit_chance(tn)
        dmg = charge.target_damage(mover, combat.fc_to_tmm(state["fc"], jumped=False))
        dealt = p * (table_worth(dmg, target, "standard", side) * wet("standard", side)
                     + displacement_worth(target, pose.label, direction, terrain_map))
        self_cost = p * table_worth(charge.attacker_damage(target), mover, "standard", "front")
        return dealt, self_cost, p, tn, dmg, side, True
    tn = dfa.to_hit(mover, target, pose.tmm)
    p = hit_chance(tn)
    dmg = dfa.target_damage(mover)
    table, t_side = ("standard", "rear") if pose.prone else ("punch", side)
    dealt = p * (table_worth(dmg, target, table, t_side) * wet(table, t_side)
                 + displacement_worth(target, pose.label, direction, terrain_map))
    self_cost = (p * table_worth(dfa.attacker_damage(mover), mover, "kick", "front")
                 + (1 - p) * table_worth(dfa.miss_fall_damage(mover), mover, "standard", "rear"))
    return dealt, self_cost, p, tn, dmg, side, False


def scored_options(mover, target, pose, index, ev, mover_exposure, target_exposure, psr_cost, best_by_mode,
                   target_args, objective, allowed=("charge", "dfa")):
    """[(score, MovementCandidate, state, note)] for the movement attacks that
    pass the gate. ev = MoveEvaluator(mover, target); target_args = the
    (hex, facing, fc, mode, mp_spent) ev.evaluate pins the target at;
    exposures are {side: factor}; objective is movement_selection._objective.
    Each candidate's dealt / received are in the evaluator's units (the
    caller multiplies by the exposure factors), so a movement attack can stand
    in wherever a MovementCandidate does. best_by_mode may also be a function
    returning that dict: it is then called only if some state needs the gate
    (speed only, 2026-10-21 - most spots have no charge or DFA at all)."""
    out = []
    states = []
    if "charge" in allowed and config.CHARGES and not pose.prone:
        states += index.charge_states(pose)
    if "dfa" in allowed and config.DFA:
        states += index.dfa_states(pose)
    if states and callable(best_by_mode):
        best_by_mode = best_by_mode()
    for state in states:
        dealt_abs, self_cost, p, tn, dmg, side, physical_reply = values(mover, target, pose, state,
                                                                        ev.terrain_map)
        if dealt_abs <= best_by_mode.get(state["mode"], 0.0) + 1e-12:
            continue                                   # the gate
        x, y = hex_geometry.parse_hex_label(state["hex"])
        prepared = ev.prepare([(x, y, hex_geometry.compass_to_facing(state["facing"]), state["fc"],
                                state["mode"], state["mp_spent"])])
        cands = ev.evaluate(*target_args, prepared, physical_reply=physical_reply)
        if cands:
            base = cands[0]
        else:
            import INTEGRATION__ranged_combat as ranged_combat
            base = ranged_combat.MovementCandidate(hex=state["hex"], facing=state["facing"], mode=state["mode"],
                                                   fc=state["fc"], mp_spent=state["mp_spent"], distance=1,
                                                   dealt=0.0, received=0.0, side_on_defender=side,
                                                   side_on_mover="front")
        t_mult = target_exposure[side] or 1.0
        m_mult = mover_exposure[base.side_on_mover] or 1.0
        cand = dataclasses.replace(base, dealt=dealt_abs / t_mult, received=base.received + self_cost / m_mult,
                                   side_on_defender=side, attack="charge" if state.get("charge") else "dfa")
        score = objective(cand.dealt, cand.received, t_mult, m_mult,
                          psr_cost(state["mode"], state["fc"], state["hex"], state["facing"], state["mp_spent"]))
        kind = "CHARGE" if state.get("charge") else "DFA"
        out.append((score, cand, state, f"{kind} (TN {tn}, P {p:.2f}, {dmg} dmg)"))
    out.sort(key=lambda t: -t[0])
    return out


def best_by_mode(cands, target_exposure):
    """Best ordinary dealt (x the target's exposure for that side) per mode."""
    best: Dict[str, float] = {}
    for c in cands:
        v = c.dealt * target_exposure[c.side_on_defender]
        if v > best.get(c.mode, 0.0):
            best[c.mode] = v
    return best


def can_be_attacked(target, target_has_moved):
    """Charge / DFA targets: on the board, not destroyed, finished moving or
    immobile (pp.78-79). (A charge also needs it standing - charge_states'
    caller checks; a DFA may land on a prone mech.)"""
    return target.hex is not None and not is_destroyed(target) and (target_has_moved or is_immobile(target))


def end_of_movement_triggers(mech, terrain_map):
    """The PSRs a charging / DFA mech owes when its movement finally ends in
    the Physical Attack Phase (2026-10-21): "after a charge and any
    displacement, the attacker's movement for the turn is finished. If that
    'Mech has critical damage that applies PSRs at the end of the 'Mech's
    movement, those must be resolved at that time" (p.78; DFA the same,
    p.80). As (reason, modifier) triggers joined to the phase's others (one
    roll each, p.110):
      - the hex it advanced into (a successful charge) - rubble, sand with a
        level change, water when running (pp.48, 113); or the hex it landed
        in (a DFA that hit, or one cancelled because the target was
        destroyed) - depth 1+ water, rubble (p.50);
      - the movement-mode PSRs (running with a damaged gyro / hip, jumping
        with damaged legs, p.111), one per trigger.
    Nothing for a mech that is down (a missed DFA falls anyway) or destroyed.
    Simplification: a failed water-landing roll falls 0 levels here, not
    the water's depth (a jump that lands normally falls the depth, p.50)."""
    pending = getattr(mech, "deferred_end_of_move", None)
    mech.deferred_end_of_move = None
    if pending is None or is_destroyed(mech) or mech.prone or mech.hex is None:
        return []
    hexes = terrain_map["hexes"]
    out = []
    if mech.hex != pending["from_hex"]:
        info = hexes[mech.hex]
        if mech.move_mode == "Jump":
            depth = water.depth_at(mech.hex)
            if depth >= 1:
                out.append((f"landed in water at {mech.hex} (depth {depth})", 0))
            if "rubble" in info["features"]:
                out.append((f"landed in rubble at {mech.hex}", 0))
        else:
            for cause in terrain_rules.step_psr_causes(hexes[pending["from_hex"]], info, False,
                                                       mech.move_mode == "Run"):
                out.append((f"entered {cause} at {mech.hex}", terrain_rules.PSR_MODIFIER[cause]))
    mode = pending["mode"]
    trigger = piloting_rolls.movement_psr_trigger(mech, mode) if mode is not None else None
    if trigger:
        out += [(f"end of movement ({mode}, {trigger})", 0)] * piloting_rolls.movement_psr_count(mech, mode)
    return out
