"""
INTEGRATION__fire_modes.py  (NEW 2026-10-20, Claude - Pile 2 rules; the CHOICES are stubs)

Everything a weapon may be told to do differently when it fires - the options
are rules, built here; which option the bot takes is a stub
(INTEGRATION__stubs: stub_munition_choice, stub_rate_of_fire, stub_unjam),
because how a bot should decide is still research (Daniel, 2026-10-20: "How a
bot determines what rate to fire at, If it should use MASC, or what kind of
ammo to use (Apollo goes in this catagory) is still a matter of research").

=== RAPID FIRE (Core pp.182, 183) ===
  - Ultra AC: 1 or 2 shots; Rotary AC: 1 to 6. Declared with the attack. Heat
    and ammo for every shot; ONE attack roll; on a hit roll the Cluster Hits
    Table on the column for the shots fired (an Ultra firing two: the 2
    column); each shot that connects rolls its own hit location for the
    weapon's Damage Value. Rapid fire (2+ shots) can't be an aimed shot
    (p.70); a targeting computer still applies (p.201).
  - The Core Ultra AC has no jam rule. A Rotary AC firing 2-3 shots jams on an
    attack roll of 2, 4-5 shots on 3 or less, 6 shots on 4 or less (the shots
    still fire). A jammed RAC can't fire until unjammed: declared in the
    Movement Phase, that turn the mech may only stand still or walk, and at
    the end of the Ranged Attack Phase a Gunnery roll at +3 clears it (p.183).

=== AMMUNITION KINDS (pp.186, 191-193; tables pp.250, 252) ===
  - LB-X cluster rounds (p.192): -1 to hit; a Cluster attack on the column of
    the autocannon's rating, 1-point groupings (each pellet its own location).
    Slugs: the normal single hit.
  - ATM (p.186, table p.252): standard 2 damage a missile, ER 1 (range 1-9 /
    10-18 / 19-27, minimum 4), HE 3 (1-3 / 4-6 / 7-9, no minimum); 6-point
    groupings whatever the round. ER / HE shots per ton are "**" in the table:
    the launcher's own figure (Daniel confirmed, 2026-10-20).
  - MML (p.186, table p.250): LRM rounds 1 damage, minimum 6, 1-7 / 8-14 /
    15-21, C5 groupings; SRM rounds 2 damage, 1-3 / 4-6 / 7-9, C2 groupings.
    (The table prints the LRM groupings as C3/3 ... C9/9 - a typo, Daniel
    2026-10-20: LRM mode is C5.)
  - Artemis / Narc-equipped missiles and Narc homing / explosive pods: the
    rules are INTEGRATION__electronics; picking which kind fires is this
    module's munition choice.
  - Apollo FCS (p.197), linked to an MRM like an Artemis FCS: standard-fire
    mode drops the MRM's -1 Cluster modifier; saturation mode is an
    area-effect attack on the target's hex: the Cluster roll without the -1
    (AMS still applies), hits / 3 damage (rounding normally) in 5-point
    groupings. Attacking a hex (Daniel, 2026-10-20): no target modifiers at
    all - no TMM, no immobile -4 (nor prone target or target stealth) - "so
    its usually gunnery + range + LOS blockers" (+ the attacker's own
    modifiers). The Arrow IV (INTEGRATION__weapon_profiles) is a hex attack too.
  - Not modeled (no unit in data/meks.zip carries them): AC armor-piercing,
    caseless, flak and precision rounds.

=== PLANNING vs DECLARING ===
A weapon's options are priced at a firing solution (range, to-hit number):
expected damage = P(hit) x E[damage | hit], with the target's AMS share
(INTEGRATION__ams) and a Narc pod's worth (INTEGRATION__electronics.pod_value).
`Planner` asks the stub policies which option each weapon would take (silently,
memoized) so weapon choice and movement scoring price the same shot the attack
will fire; when the attack is declared, `Planner.declare` asks again - that call
is the decision, and the stub prints its loud warning then.
"""

from typing import NamedTuple, Optional
import functools

import INTEGRATION__config as config
import INTEGRATION__stubs as stubs
import INTEGRATION__weapon_rules as weapon_rules
import INTEGRATION__expected_damage as expected_damage
import INTEGRATION__electronics as electronics
import INTEGRATION__ammo as ammo
import INTEGRATION__weapon_profiles as wp
from equipment import Equipment
from damage_resolution import get_weapons

_2D6_EXACT = expected_damage._2D6_EXACT

# --- Ammunition-kind profiles (tables pp.250, 252) -----------------------------
# (damage per missile, grouping, range {min, short, medium, long}, shots per ton or None = launcher's)
MML_KINDS = {
    "lrm": (1, 5, {"min": 6, "short": 7, "medium": 14, "long": 21}),
    "srm": (2, 2, {"min": 0, "short": 3, "medium": 6, "long": 9}),
}
MML_SHOTS = {3: {"lrm": 40, "srm": 33}, 5: {"lrm": 24, "srm": 20}, 7: {"lrm": 17, "srm": 14}, 9: {"lrm": 13, "srm": 11}}
ATM_KINDS = {
    "standard": (2, {"min": 4, "short": 5, "medium": 10, "long": 15}),
    "er": (1, {"min": 4, "short": 9, "medium": 18, "long": 27}),
    "he": (3, {"min": 0, "short": 3, "medium": 6, "long": 9}),
}
LBX_CLUSTER_TN = -1
RAC_JAM_AT = ((6, 4), (4, 3), (2, 2))      # (shots at least, jams on a roll of this or less) - p.183
UNJAM_TN_MODIFIER = 3                       # Gunnery + 3 (p.183)
APOLLO_CLUSTER = 1                          # cancels the MRM's -1 (p.197)


def _cn(weapon):
    return weapon_rules.canonical_name(weapon)


def is_ultra(weapon):
    return "ULTRAAC" in _cn(weapon)


def is_rotary(weapon):
    return "ROTARYAC" in _cn(weapon)


def is_lbx(weapon):
    return "LBXAC" in _cn(weapon)


def is_mml(weapon):
    return "MML" in _cn(weapon)


def is_mrm(weapon):
    return _cn(weapon).startswith("MRM")


def max_shots(weapon):
    return 2 if is_ultra(weapon) else (6 if is_rotary(weapon) else 1)


def mml_size(weapon):
    return weapon.rack_size


def has_profile(weapon):
    """Weapons whose damage / range / heat come from INTEGRATION__weapon_profiles
    or the ammunition fired (MML) rather than one equipment.json number."""
    return (is_mml(weapon) or wp.variable_damage(weapon) is not None or wp.is_hag(weapon) or wp.is_mpod(weapon)
            or wp.is_bombast(weapon) or wp.is_arrow(weapon) or wp.is_mga(weapon) or wp.is_infantry_pod(weapon))


# =============================================================================
# ==========================  THE SHOT PLAN  ==================================
# =============================================================================
class ShotPlan(NamedTuple):
    """How one weapon fires this turn. guidance: electronics.FireControl
    (munition, Artemis / Narc to-hit and Cluster changes, Streak lock)."""
    guidance: electronics.FireControl = electronics.PLAIN
    kind: str = ""          # "", "cluster" (LB-X), "er" / "he" (ATM), "lrm" / "srm" (MML), "8" / "12" / "16"
                            # (bombast), "saturation" (Apollo), "artillery" (Arrow IV)
    shots: int = 1          # rapid fire; a machine gun array: the guns it fires
    apollo: bool = False
    bracket: str = ""       # range bracket fired at (variable damage, HAG, M-pod) - set by the Planner

    @property
    def munition(self):
        return self.guidance.munition

    @property
    def hex_attack(self):
        return self.kind in ("saturation", "artillery")

    @property
    def tn(self):
        tn = self.guidance.tn + (LBX_CLUSTER_TN if self.kind == "cluster" else 0)
        if self.kind in wp.BOMBAST:
            tn += wp.BOMBAST[self.kind][1]
        if self.kind == "artillery":
            tn += wp.ARROW_TN
        return tn

    @property
    def note(self):
        parts = [self.guidance.note] if self.guidance.note else []
        if self.kind:
            parts.append({"cluster": "LB-X cluster rounds", "er": "ATM ER", "he": "ATM HE",
                          "lrm": "MML LRM rounds", "srm": "MML SRM rounds", "saturation": "Apollo saturation",
                          "artillery": "artillery at the hex", "array": f"array of {self.shots}"}.get(
                              self.kind, f"{self.kind} damage"))
        if self.shots > 1 and self.kind != "array":
            parts.append(f"rapid fire x{self.shots}")
        if self.apollo and self.kind != "saturation":
            parts.append("Apollo")
        return ", ".join(parts)


PLAIN = ShotPlan()


def damage_per(weapon, plan):
    """Damage of one missile / shot / pellet / slug."""
    if plan.kind == "cluster" or wp.is_hag(weapon) or wp.is_mpod(weapon):
        return 1
    if is_mml(weapon) and plan.kind in MML_KINDS:
        return MML_KINDS[plan.kind][0]
    if "ATM" in _cn(weapon):
        return ATM_KINDS.get(plan.kind or "standard", ATM_KINDS["standard"])[0]
    if plan.kind in wp.BOMBAST:
        return wp.BOMBAST[plan.kind][0]
    if wp.is_arrow(weapon):
        return wp.ARROW_DAMAGE
    if wp.is_infantry_pod(weapon):
        return 0
    table = wp.variable_damage(weapon)
    if table is not None:
        return table.get(plan.bracket or "short", 0)
    if wp.is_rifle(weapon):
        return max(0, (weapon.damage_per_shot or 0) + wp.RIFLE_VS_MECH)
    return weapon.damage_per_shot


def weapon_range(weapon, plan):
    if is_mml(weapon) and plan.kind in MML_KINDS:
        return MML_KINDS[plan.kind][2]
    if "ATM" in _cn(weapon) and plan.kind in ATM_KINDS:
        return ATM_KINDS[plan.kind][1]
    if wp.is_arrow(weapon):
        lo, hi = wp.ARROW_RANGE
        return {"min": 0, "short": hi, "medium": hi, "long": hi, "floor": lo}
    if wp.is_mga(weapon):
        guns = getattr(weapon, "mga_guns", [])
        return guns[0].weapon_range if guns else weapon.weapon_range
    return weapon.weapon_range


def column(weapon, plan):
    """Cluster Hits Table column, or None for a single hit."""
    if wp.is_mga(weapon):
        return plan.shots
    if plan.shots > 1:
        return plan.shots
    if plan.kind == "cluster":
        return weapon.damage_per_shot          # the autocannon's rating
    if wp.is_hag(weapon):
        return wp.hag_size(weapon)
    if wp.is_mpod(weapon):
        return wp.MPOD_COLUMN_BY_BRACKET.get(plan.bracket or "short")
    if wp.is_arrow(weapon):
        return None
    if weapon_rules.is_cluster(weapon):
        return weapon.rack_size
    return None


def grouping(weapon, plan):
    if plan.kind == "saturation":
        return wp.AREA_GROUPING
    if wp.is_hag(weapon):
        return wp.HAG_GROUPING
    if plan.shots > 1 or plan.kind == "cluster" or wp.is_mpod(weapon):
        return damage_per(weapon, plan)       # every shot / pellet its own location
    if is_mml(weapon) and plan.kind in MML_KINDS:
        return MML_KINDS[plan.kind][1]
    return weapon_rules.grouping_size(weapon)


def cluster_modifier(weapon, plan):
    if wp.is_mga(weapon):
        return wp.MGA_CLUSTER
    mod = plan.guidance.cluster + (weapon_rules.cluster_roll_modifier(weapon) if plan.shots == 1 else 0)
    if wp.is_hag(weapon):
        mod += wp.HAG_CLUSTER_BY_BRACKET.get(plan.bracket or "medium", 0)
    return mod + (APOLLO_CLUSTER if plan.apollo else 0)


def heat(weapon, plan):
    if plan.kind in wp.BOMBAST:
        return wp.BOMBAST[plan.kind][2]
    return (weapon.heat or 0) * (1 if wp.is_mga(weapon) else plan.shots)


def aimable(weapon, plan):
    """p.70: no rapid fire, Cluster, area-effect or Flak aimed shots."""
    return (plan.shots == 1 and plan.kind != "cluster" and not plan.hex_attack and not weapon_rules.is_cluster(weapon)
            and not (wp.is_hag(weapon) or wp.is_mpod(weapon) or wp.is_mga(weapon) or wp.is_arrow(weapon)
                     or wp.is_art_cannon(weapon)))


def tc_eligible(weapon, plan):
    if (plan.hex_attack or plan.kind == "cluster" or wp.is_mpod(weapon) or wp.is_arrow(weapon) or wp.is_mga(weapon)
            or wp.is_art_cannon(weapon)):
        return False
    return wp.is_hag(weapon) or weapon_rules.targeting_computer_eligible(weapon)    # HAG: yes (p.201)


def range_mod(weapon, plan, distance):
    import INTEGRATION__weapon_selection as weapon_selection
    wr = weapon_range(weapon, plan)
    if wr is None or wr.get("short") is None:
        return None
    if "floor" in wr:                                    # Arrow IV: 7-17 hexes, no range modifier (p.182)
        return 0 if wr["floor"] <= distance <= wr["long"] else None
    if distance <= wr["short"]:
        bracket = weapon_selection.RANGE_MOD_SHORT
    elif distance <= wr["medium"]:
        bracket = weapon_selection.RANGE_MOD_MEDIUM
    elif distance <= wr["long"]:
        bracket = weapon_selection.RANGE_MOD_LONG
    else:
        return None
    return bracket + weapon_selection._min_range_penalty(wr.get("min") or 0, distance)


def bracket(weapon, plan, distance):
    wr = weapon_range(weapon, plan)
    if wr is None or wr.get("short") is None:
        return None
    for name in ("short", "medium", "long"):
        if distance <= wr[name]:
            return name
    return None


@functools.lru_cache(maxsize=None)
def _expected_hits(col, modifier, engaged, thirds=False):
    """E[hits] on `col` with `modifier`; engaged = an AMS took it (-4 already in
    modifier; below 2 = none, p.206), else the roll clamps to 2-12 (p.74).
    thirds: E[round(hits / 3)] (Apollo saturation, p.197)."""
    total = 0.0
    for roll, p in _2D6_EXACT.items():
        r = roll + modifier
        if engaged and r < 2:
            continue
        hits = config.CLUSTER_HITS_TABLE[max(2, min(12, r))][col]
        total += p * (third(hits) if thirds else hits)
    return total


def third(hits):
    """hits / 3, rounding normally (.5 up)."""
    return int(hits / 3 + 0.5)


def expected_hit(weapon, plan=PLAIN, ams_engaged=False):
    """E[damage | hit] for this plan; with ams_engaged, as if the target's AMS
    took it (Missile weapons only - INTEGRATION__ams)."""
    import INTEGRATION__ams as ams
    dmg = damage_per(weapon, plan) or 0
    if dmg == 0:
        return 0.0
    col = column(weapon, plan)
    if col is None:
        if ams_engaged:
            return dmg * (ams.SINGLE_MISSILE_KILL - 1) / 6
        return dmg
    if weapon_rules.is_streak(weapon) and plan.guidance.streak_lock:
        if ams_engaged:
            return dmg * config.CLUSTER_HITS_TABLE[ams.STREAK_RESULT][col]
        return dmg * col
    mod = cluster_modifier(weapon, plan) + (ams.CLUSTER_MODIFIER if ams_engaged else 0)
    return dmg * _expected_hits(col, mod, ams_engaged, plan.kind == "saturation")


# =============================================================================
# ==========================  OPTIONS  ========================================
# =============================================================================
def apollo_live(mech, weapon):
    link = getattr(weapon, "apollo", None)
    return link is not None and id(link) not in electronics._dead(mech)


def attach(mech):
    """Once per battle: link Apollo FCS to MRMs (same location, slot order, as
    Artemis), clear jams and unjam declarations."""
    mech.unjamming = []
    wp.link_arrays(mech)
    seen, fcs_by_loc, mrm_by_loc = set(), {}, {}
    for loc, slots in mech.crits.items():
        for s in slots:
            if not isinstance(s, Equipment) or id(s) in seen:
                continue
            seen.add(id(s))
            if s.category != "ammo" and "APOLLO" in s.name.upper():
                fcs_by_loc.setdefault(loc, []).append(s)
            elif s.category == "weapon" and is_mrm(s):
                mrm_by_loc.setdefault(loc, []).append(s)
            if s.category == "weapon":
                s.jammed = False
    left_f, left_w = [], []
    for loc in mech.crits:
        f, w = fcs_by_loc.get(loc, []), mrm_by_loc.get(loc, [])
        for a, b in zip(f, w):
            b.apollo = a
        left_f += f[len(w):]
        left_w += w[len(f):]
    for a, b in zip(left_f, left_w):
        b.apollo = a


def bin_kinds(mech, weapon):
    """{(munition, kind)} of the live bins with shots that feed `weapon`
    ({("standard", "")} for a weapon without ammo)."""
    if not getattr(weapon, "needs_ammo", False):
        return {("standard", "")}
    return {(getattr(b, "munition", "standard"), getattr(b, "kind", "")) for b in ammo.bins_for(mech, weapon)}


def rounds_left(mech, weapon, munition, kind):
    if not getattr(weapon, "needs_ammo", False):
        return float("inf")
    bins = [b for b in ammo.bins_for(mech, weapon)
            if getattr(b, "munition", "standard") == munition and getattr(b, "kind", "") == kind]
    if any(b.shots_left is None for b in bins):
        return float("inf")
    return sum(b.shots_left for b in bins)


def kind_options(attacker, weapon, target):
    """Every ammunition kind / guidance / Apollo mode `weapon` could fire now,
    as ShotPlans with 1 shot (the rate is a separate choice)."""
    if electronics.is_narc(weapon):
        kinds = sorted({m for m, _ in bin_kinds(attacker, weapon)}) or ["homing"]
        return [ShotPlan(electronics.FireControl(m)) for m in kinds]
    if wp.is_bombast(weapon):
        return [ShotPlan(kind=k) for k in wp.BOMBAST]
    if wp.is_arrow(weapon):
        return [ShotPlan(kind="artillery")] if ("standard", "") in bin_kinds(attacker, weapon) else []
    if wp.is_mga(weapon):
        guns = [g for g in wp.mga_guns(attacker, weapon) if rounds_left(attacker, g, "standard", "") >= 1]
        return [ShotPlan(kind="array", shots=len(guns))] if guns else []
    out = []
    for munition, kind in sorted(bin_kinds(attacker, weapon)) or [("standard", "")]:
        if is_mml(weapon) and kind not in MML_KINDS:
            continue
        guidance = electronics.control_for(attacker, weapon, target, munition)
        apollo = is_mrm(weapon) and apollo_live(attacker, weapon)
        out.append(ShotPlan(guidance, kind, 1, apollo))
        if apollo:
            out.append(ShotPlan(guidance, "saturation", 1, True))
    return out


def rate_options(attacker, weapon, plan):
    """Shot counts the weapon can fire with this plan's ammunition."""
    if wp.is_mga(weapon):
        return [plan.shots]
    top = min(max_shots(weapon), int(min(max_shots(weapon), rounds_left(attacker, weapon, plan.munition, plan.kind))))
    return list(range(1, max(1, top) + 1))


def jam_threshold(plan):
    """Attack roll at or below which a Rotary AC jams (0 = can't jam)."""
    for at_least, roll in RAC_JAM_AT:
        if plan.shots >= at_least:
            return roll
    return 0


def jammed_ids(mech):
    return frozenset(id(w) for w in get_weapons(mech) if getattr(w, "jammed", False))


# =============================================================================
# ==========================  PRICING / PLANNER  ==============================
# =============================================================================
def special(weapon):
    """Weapons the Planner prices (anything that isn't a plain single shot)."""
    return (weapon.damage_type == "Missile" or max_shots(weapon) > 1 or is_lbx(weapon) or is_mml(weapon)
            or "ATM" in _cn(weapon) or has_profile(weapon) or wp.is_rifle(weapon) or wp.heat_causing(weapon)
            or wp.is_art_cannon(weapon))


class Planner:
    """Prices one attacker's special weapons against one target. adjust(w,
    bracket) is attack_resolution.tn_adjuster's per-weapon TN change (stealth,
    weapon's own, arm crits, aim, TC - TC and aim judged per plan here);
    ams_share = the fraction of missile hits the target's AMS would take."""

    def __init__(self, attacker, target, adjust, ams_share=0.0, pod_values=None, hex_offset=None):
        self.attacker, self.target, self.adjust, self.ams_share = attacker, target, adjust, ams_share
        self.pod_values = pod_values or {}          # {id(beacon): homing pod worth} (attack phase)
        # hex_offset: what to add to pre_tn for an attack on the target's HEX - minus the
        # target's own modifiers (TMM / immobile, prone target, its Void-Signature). None:
        # hex attacks (Apollo saturation, Arrow IV) aren't priced (movement scoring).
        self.hex_offset = hex_offset
        self._kinds = {}
        self._memo = {}

    def kinds(self, weapon):
        got = self._kinds.get(id(weapon))
        if got is None:
            got = self._kinds[id(weapon)] = kind_options(self.attacker, weapon, self.target)
        return got

    def value(self, weapon, plan, distance, pre_tn):
        """(expected worth, TN) of firing `plan`, or None if out of range."""
        from combat import hit_probability
        rm = range_mod(weapon, plan, distance)
        if rm is None:
            return None
        b = bracket(weapon, plan, distance)
        plan = plan._replace(bracket=b or "")
        if plan.hex_attack:
            if self.hex_offset is None:
                return None
            tn = pre_tn + self.hex_offset + rm + self.adjust(weapon, None, plan) + plan.tn
        else:
            tn = pre_tn + rm + self.adjust(weapon, b, plan) + plan.tn + area_immobile_fix(weapon, self.target)
        p = hit_probability(tn)
        if plan.kind == "artillery" or wp.is_art_cannon(weapon):
            # the hex hit; a miss by 1-2 scatters 1 hex - next to the target: the splash (pp.182-183)
            near = hit_probability(tn - 2) - p
            return p * (damage_per(weapon, plan) or 0) + near * wp.splash(weapon), tn
        if electronics.is_narc(weapon):
            worth = (ammo.EXPLOSIVE_POD_DAMAGE.get(weapon.ammo_key, 0) if plan.munition == "explosive"
                     else self.pod_values.get(id(weapon), 0.0))
            return p * worth, tn
        hit = expected_hit(weapon, plan)
        if self.ams_share and weapon.damage_type == "Missile" and hit > 0:
            hit -= self.ams_share * (hit - expected_hit(weapon, plan, ams_engaged=True))
        hit += config.TARGET_HEAT_WORTH * wp.expected_target_heat(weapon)       # flamers, plasma (placeholder worth)
        return p * hit, tn

    def _decide(self, weapon, distance, pre_tn, warn):
        name = self.attacker.side_name
        options = []
        for plan in self.kinds(weapon):
            got = self.value(weapon, plan, distance, pre_tn)
            if got is not None:
                options.append((plan._replace(bracket=bracket(weapon, plan, distance) or ""), got[0]))
        if not options:
            return None
        plan = stubs.stub_munition_choice(name, weapon, options, warn=warn) if len(options) > 1 else options[0][0]
        rates = rate_options(self.attacker, weapon, plan)
        if len(rates) > 1:
            priced = [(n, self.value(weapon, plan._replace(shots=n), distance, pre_tn)[0]) for n in rates]
            plan = plan._replace(shots=stubs.stub_rate_of_fire(name, weapon, priced, warn=warn))
        return plan

    def __call__(self, weapon, distance, pre_tn):
        """(value, heat, plan) for weapon_selection, or None (can't fire here)."""
        key = (id(weapon), distance, pre_tn)
        got = self._memo.get(key, False)
        if got is False:
            plan = self._decide(weapon, distance, pre_tn, warn=False)
            got = None if plan is None else (self.value(weapon, plan, distance, pre_tn)[0], heat(weapon, plan), plan)
            self._memo[key] = got
        return got

    def declare(self, weapon, distance, pre_tn):
        """The decision itself, at attack declaration: the stubs warn here."""
        return self._decide(weapon, distance, pre_tn, warn=True) or PLAIN


def area_immobile_fix(weapon, target):
    """Area-effect weapons never take the immobile -4 (p.181): undo it for an
    artillery cannon's normal attack on an immobile target."""
    from mech_state import is_immobile
    return 4 if wp.is_art_cannon(weapon) and is_immobile(target) else 0


def ams_share(target_capacity, weapons):
    """Fraction of missile hits a target AMS able to engage `target_capacity`
    attacks would take (INTEGRATION__ams bot choice)."""
    n = sum(1 for w in weapons if w.damage_type == "Missile" and (w.damage_per_shot or 0) > 0)
    return min(1.0, target_capacity / n) if target_capacity > 0 and n else 0.0


# =============================================================================
# ==========================  RAC JAMS  =======================================
# =============================================================================
def declare_unjams(mech):
    """Movement Phase start: which jammed RACs the mech tries to clear
    (stub_unjam). A mech trying may only stand still or walk this turn."""
    mech.unjamming = []
    if mech.shutdown:
        return
    mech.unjamming = [w for w in get_weapons(mech) if getattr(w, "jammed", False)
                      and stubs.stub_unjam(mech.side_name, w, prone=mech.prone)]
    if mech.unjamming:
        config.log(f"  [Movement] {mech.side_name} tries to unjam {[w.name for w in mech.unjamming]} "
                   f"(stand still or walk only, p.183).")


def resolve_unjams(mech):
    """End of the Ranged Attack Phase: Gunnery + 3 for each attempt (p.183)."""
    for w in getattr(mech, "unjamming", []):
        if w not in get_weapons(mech):
            continue
        tn = mech.gunnery + UNJAM_TN_MODIFIER
        roll = config.roll_2d6(prompt=f"Unjam roll ({w.name})")
        if roll >= tn:
            w.jammed = False
        config.log(f"  [Ranged] {mech.side_name} unjam {w.name}: needs {tn}, rolled {roll} -> "
                   f"{'cleared' if roll >= tn else 'still jammed'}.")
    mech.unjamming = []
