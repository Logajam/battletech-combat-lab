"""
INTEGRATION__ams.py  (NEW 2026-10-20, Claude - Pile 2 rules, Pile 4 engagement choice)

Anti-Missile Systems: the standard AMS and the laser AMS (Core Rulebook p.206).

=== RULES (p.206) ===
  - When a Type M (Missile) weapon HITS a 'Mech carrying an AMS, and the attack
    comes from inside the firing arc of the AMS's location, the defender may
    engage the AMS, decided right after the attack roll.
  - Engaged against a Cluster missile weapon: the attacker's Cluster Hits Table
    roll takes -4 (on top of the weapon's own modifier, e.g. MRM -1); a
    modified result below 2 destroys every missile - no damage. (Without AMS
    the roll clamps to 2-12, p.74; with it only the top clamps.)
  - Against a Streak launcher: the Cluster result is 7 (not the automatic 12,
    p.187) on the launcher's column.
  - Against a single missile (Thunderbolt, Narc pod): the defender rolls 1D6,
    4-6 destroys it.
  - Each engagement marks off 1 AMS shot and makes 1 heat; a laser AMS uses no
    ammo and makes 7 heat (Inner Sphere) or 5 (Clan) - equipment.json `heat`.
  - One AMS per attack; each AMS engages at most 2 attacks a turn; a 'Mech with
    more chooses which takes which.
  - AMS only stops Type M weapons. Every equipment.json row with damage_type
    "Missile" is Type M in the Weapons and Equipment Tables (pp.248-254 -
    LRM / SRM / Streak / MRM / ATM / MML / rocket launcher / Thunderbolt / Narc,
    checked 2026-10-20); Arrow IV (unaffected, p.182) has no "Missile" row.
  - Firing an AMS is not an attack: an arm AMS doesn't stop that arm punching
    (and the AMS never fires as a weapon - weapon_selection leaves it out).
  - It can't be engaged with the MechWarrior unconscious (p.206), nor while
    shut down (p.104: activated equipment doesn't work, no actions).
  - Ammo explosions: 2 damage per AMS shot left (p.206) - already what
    INTEGRATION__ammo computes from equipment.json (damage_per_shot 2).

Claude's readings (flagged for Daniel in PROJECT_MAP Section 4):
  - "the attack direction covered by the firing arc of the location" = the
    attacker stands inside the AMS's firing arc, worked out exactly like a
    weapon in that location firing back (INTEGRATION__arcs: torso twist,
    flipped arms, rear-mounted "(R)" AMS, leg / turret AMS).
  - "MechWarrior unconscious": the whole crew (a tripod's gunner can still
    engage with the pilot out) - mech_state.all_crew_unconscious.
  - Engagements are chosen at declaration, from the pre-damage state, like
    every other Ranged-phase choice (both sides declare before damage lands):
    an AMS destroyed by an earlier hit in the same phase still engages.

=== BOT CHOICES (pile 4, Section 6) ===
  - Which hits to engage: the attacker's missile hits this phase, the ones
    whose expected damage the AMS cuts most first (the rule lets the defender
    pick among them when there are more than its AMS can take). Zero-damage
    missiles (Narc pods - their beacon effect isn't modeled) are never engaged.
  - Which AMS takes a hit: the one making the least heat first (standard AMS
    before laser AMS).
  - Heat: an engagement is skipped if it would leave the mech's projected
    end-of-turn heat above max(its max_heat, config.AMS_HEAT_LIMIT) - default
    13, the last level with no shutdown roll (p.104).
  - Expected damage (weapon choice and movement scoring): each damaging
    missile weapon's expected damage is scaled toward its with-AMS value by
    min(1, engagements / missile weapons) - the share the defender can engage,
    an approximation of "the biggest ones get engaged". Heat isn't priced in
    there (laser AMS counts as available), and in movement scoring the
    defender's torso is taken as untwisted.
"""

import functools

import INTEGRATION__config as config
import INTEGRATION__weapon_rules as weapon_rules
import INTEGRATION__expected_damage as expected_damage
import INTEGRATION__arcs as arcs
import INTEGRATION__ammo as ammo
import INTEGRATION__heat as heat
from damage_resolution import get_weapons
from mech_state import all_crew_unconscious, compute_heat_dissipation
import hex_geometry

CLUSTER_MODIFIER = -4          # p.206
STREAK_RESULT = 7              # p.206: a Streak counts as a 7 on its column
SINGLE_MISSILE_KILL = 4        # p.206: 1D6 4-6 destroys a single missile
ENGAGEMENTS_PER_TURN = 2       # p.206, per AMS
_2D6_EXACT = expected_damage._2D6_EXACT


# =============================================================================
# ==========================  WHAT AN AMS CAN ENGAGE  ========================
# =============================================================================
def engageable(weapon):
    """A Type M weapon the bot would engage: one that does damage."""
    return weapon.damage_type == "Missile" and (weapon.damage_per_shot or 0) > 0


def systems(mech):
    """The mech's live AMS (destroyed ones drop out of get_weapons)."""
    return [w for w in get_weapons(mech) if weapon_rules.is_ams(w)]


def can_engage(mech):
    """p.206 (conscious crew) and p.104 (not shut down)."""
    return not mech.shutdown and not all_crew_unconscious(mech)


def covering(mech, attacker_hex, action=None):
    """The mech's live AMS whose firing arc holds `attacker_hex` (a parsed
    (col, row) hex), with the mech's declared torso twist / arm flip / turret
    (or `action`)."""
    from INTEGRATION__attack_resolution import weapon_locations      # attack_resolution imports this module
    found = systems(mech)
    if not found:
        return []
    m_hex = hex_geometry.parse_hex_label(mech.hex)
    facing = hex_geometry.compass_to_facing(mech.facing)
    key = arcs.key_for(arcs.arcs_between(m_hex, attacker_hex), facing,
                       action if action is not None else arcs.current_action(mech), arcs.leg_offsets(mech))
    blocked = arcs.unavailable(mech, found, weapon_locations(mech), key)
    return [w for w in found if id(w) not in blocked]


def shots_left(mech, weapon):
    """AMS shots this AMS can still draw (inf for a laser AMS / unknown data)."""
    if not getattr(weapon, "needs_ammo", False):
        return float("inf")
    bins = ammo.bins_for(mech, weapon)
    if any(b.shots_left is None for b in bins):
        return float("inf")
    return sum(b.shots_left for b in bins)


def engagement_capacity(mech, ams_list):
    """How many attacks `ams_list` can engage this turn: 2 each, limited by
    the shots in the bins they share (identical AMS share bins, p.72)."""
    by_key = {}
    for w in ams_list:
        by_key.setdefault(getattr(w, "ammo_key", None) if getattr(w, "needs_ammo", False) else id(w), []).append(w)
    total = 0
    for ws in by_key.values():
        total += min(ENGAGEMENTS_PER_TURN * len(ws), shots_left(mech, ws[0]))
    return int(total)


# =============================================================================
# ==========================  EXPECTED DAMAGE  ================================
# =============================================================================
@functools.lru_cache(maxsize=None)
def _expected_cluster_hits_engaged(shots, modifier):
    """Expected missiles that connect when an AMS engages a Cluster weapon:
    roll + modifier (incl. -4), below 2 = none, above 12 = 12."""
    total = 0.0
    for roll, p in _2D6_EXACT.items():
        r = roll + modifier
        if r >= 2:
            total += p * config.CLUSTER_HITS_TABLE[min(12, r)][shots]
    return total


def expected_damage_engaged(weapon):
    """E[damage | hit] when an AMS engages the attack (rules above)."""
    if not weapon_rules.is_cluster(weapon):
        return weapon.damage_per_shot * (SINGLE_MISSILE_KILL - 1) / 6     # 1D6 1-3: it gets through
    if weapon_rules.is_streak(weapon):
        return weapon.damage_per_shot * config.CLUSTER_HITS_TABLE[STREAK_RESULT][weapon.rack_size]
    return weapon.damage_per_shot * _expected_cluster_hits_engaged(
        weapon.rack_size, CLUSTER_MODIFIER + weapon_rules.cluster_roll_modifier(weapon))


def damage_prevented(weapon):
    """Expected damage an engagement takes off one hit of `weapon`."""
    return expected_damage.expected_damage_per_hit(weapon) - expected_damage_engaged(weapon)


def damage_factors(weapons, engagements):
    """{id(weapon): multiplier} for an attacker's `weapons` against a target
    that can engage `engagements` attacks from this direction (bot choice in
    the module docstring), or None when the AMS changes nothing."""
    targets = [w for w in weapons if engageable(w)]
    if engagements <= 0 or not targets:
        return None
    share = min(1.0, engagements / len(targets))
    out = {}
    for w in targets:
        base = expected_damage.expected_damage_per_hit(w)
        if base > 0:
            out[id(w)] = 1.0 - share * (1.0 - expected_damage_engaged(w) / base)
    return out


def combine(scale, factors):
    """Multiply two {id(weapon): multiplier} dicts (either may be None)."""
    if not factors:
        return scale
    if not scale:
        return factors
    out = dict(scale)
    for k, v in factors.items():
        out[k] = out.get(k, 1.0) * v
    return out


class Coverage:
    """Movement scoring's view of one mech's AMS: how many attacks it could
    engage from a shooter in each arc, as the mech stands now (untwisted at
    movement time). engagements(arcs_tuple, facing) is memoized."""
    __slots__ = ("mech", "ams", "locs", "legs", "action", "_memo")

    def __init__(self, mech):
        from INTEGRATION__attack_resolution import weapon_locations
        self.mech = mech
        self.ams = systems(mech) if can_engage(mech) else []
        self.locs = weapon_locations(mech) if self.ams else {}
        self.legs = arcs.leg_offsets(mech)
        self.action = arcs.current_action(mech)
        self._memo = {}

    def engagements(self, shooter_arcs, facing):
        """shooter_arcs: arcs.arcs_between(this mech's hex, shooter's hex)."""
        if not self.ams:
            return 0
        k = (shooter_arcs, facing)
        got = self._memo.get(k)
        if got is None:
            key = arcs.key_for(shooter_arcs, facing, self.action, self.legs)
            blocked = arcs.unavailable(self.mech, self.ams, self.locs, key)
            got = self._memo[k] = engagement_capacity(self.mech, [w for w in self.ams if id(w) not in blocked])
        return got


# =============================================================================
# ==========================  ENGAGING (Ranged phase)  ========================
# =============================================================================
def projected_heat(mech, weapon_heat):
    """The mech's heat level at the end of this turn if nothing else changes:
    current + movement + other heat + this phase's weapon / AMS heat - sinks."""
    return (mech.current_heat + mech.movement_heat + heat.other_heat(mech) + weapon_heat
            - compute_heat_dissipation(mech))


def engage(defender, attacker, attacks, defender_report):
    """Assign the defender's AMS to the attacker's declared hits (bot choice
    in the module docstring): sets attack.ams on each engaged attack, marks
    off the shot and adds the heat to defender_report.weapon_heat."""
    hits = [a for a in attacks if a.hit and engageable(a.weapon)]
    if not hits or not systems(defender):
        return
    name = defender.side_name
    if not can_engage(defender):
        config.log(f"  [AMS] {name}: can't engage ({'shut down' if defender.shutdown else 'crew unconscious'}).")
        return
    ams_list = sorted(covering(defender, hex_geometry.parse_hex_label(attacker.hex)), key=lambda w: w.heat or 0)
    if not ams_list:
        config.log(f"  [AMS] {name}: no AMS covers the attack from {attacker.side_name}'s hex.")
        return
    limit = max(defender.max_heat, config.AMS_HEAT_LIMIT)
    used = {}
    for attack in sorted(hits, key=lambda a: damage_prevented(a.weapon), reverse=True):
        for w in ams_list:
            if used.get(id(w), 0) >= ENGAGEMENTS_PER_TURN or shots_left(defender, w) < 1:
                continue
            projected = projected_heat(defender, defender_report.weapon_heat + (w.heat or 0))
            if projected > limit:
                config.log(f"  [AMS] {name}: {w.name} holds - engaging {attack.weapon.name} would end the turn "
                           f"at {projected} heat (limit {limit}).")
                continue
            used[id(w)] = used.get(id(w), 0) + 1
            note = ammo.spend(defender, w)
            defender_report.weapon_heat += w.heat or 0
            attack.ams = w
            config.log(f"  [AMS] {name}'s {w.name} engages {attacker.side_name}'s {attack.weapon.name} "
                       f"(+{w.heat or 0} heat{f'; {note}' if note else ''}).")
            break
