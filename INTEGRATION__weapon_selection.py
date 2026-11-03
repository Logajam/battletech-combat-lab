"""
INTEGRATION__weapon_selection.py

Pile 4 (bot decision-making): given a mech's live weapon list, its heat state,
and a firing solution's (range, pre-range TN) from Pathfinder, decide which
weapons to fire to maximize expected damage within the mech's heat window.

=== TABLE SHAPE (Daniel, 2026-08-05) ===
"You probably want to use the actual range, not just the bracket. It lets you
skip a translation step (Range to bracket) and also accounts for minimum
range. Turns the search space into a nice 3D array. Weapons, range, Starting
TN axis. And returns the expected damage."

table[weapon_id][distance][pre_tn] -> expected damage for that ONE weapon
fired alone at that distance/pre_tn, or None if distance is outside that
weapon's range envelope (beyond Long). Inside minimum range is NOT out of
range: the weapon can still fire, with the minimum-range penalty folded
into its range modifier (2026-10-19, see _weapon_range_mod). pre_tn is "GATOR minus this weapon's own
Range term" - Gunnery + AMM + TMM + Other - matching PATHFINDER__combat.py's
existing `tn = gunnery + amm + target_tmm + los_modifier + range_mod` shape,
just with range_mod split out per weapon instead of folded in ahead of time.

=== CACHING / RECOMPUTE POLICY (Daniel, 2026-08-05) ===
"I'd only recompute if the Mech state says something has changed since last
turn which requires a recompute. A non-zero heat which is not the same as
last turn counts, but so does actuator damage for weapons in that location.
If heat is zero, and no critical damage has happened... may as well not do
the math again."

Implemented as memoization keyed on (current_heat, frozenset of live weapon
instance ids from damage_resolution.get_weapons()) rather than tracking heat
and crit-damage as two separate signals: the weapon-id-set already changes
the instant a weapon is destroyed (get_weapons() drops it - see its
partial-destruction handling), so it's a strict superset of "did
weapon-affecting critical damage happen" without needing a second check.
Heat value being unchanged from a previously-seen state (including 0, which
just means it was memoized once and reused ever after) reuses that entry.
Cache lives for the process's lifetime - call reset_table_cache() between
separate battle runs. The orchestrator does this at the start of every
battle (2026-10-18): the cache is keyed on id(mech), and Python reuses ids
of garbage-collected clones, so a stale table from a previous battle's
mech could otherwise be picked up.

=== IMPORTS - CHANGED 2026-10-18 (Claude) ===
The old load-MECHSIM-then-purge-sys.modules-then-load-PATHFINDER dance is
REMOVED. It was written against an earlier PATHFINDER combat.py that did
`import config`; that file no longer does (orchestrator docstring,
CORRECTED 2026-09-01). Worse, the purge popped the bare "config" entry -
i.e. INTEGRATION__config's own self-registration - so the very next
`import config` (inside INTEGRATION__expected_damage) failed with
ModuleNotFoundError. Confirmed by a live import test 2026-10-18, not just
by reading. It also purged MECHSIM's cached modules, which risks a second
copy of equipment.py loading and isinstance(slot, Equipment) silently
failing across the two copies. Now: both directories go on sys.path once
and modules import normally. If a real same-name collision ever comes
back, solve it at the orchestrator level, not by purging here.
"""

import contextlib
import os
import sys

MECHSIM_DIR = os.environ.get("MECHSIM_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mechsim"))
PATHFINDER_DIR = os.environ.get("PATHFINDER_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pathfinder"))

for _d in (MECHSIM_DIR, PATHFINDER_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import INTEGRATION__config  # noqa: E402,F401 - ensures bare "config" is registered before MECHSIM imports
import INTEGRATION__expected_damage as expected_damage  # noqa: E402
import INTEGRATION__weapon_rules as weapon_rules  # noqa: E402
import INTEGRATION__fire_modes as fire_modes  # noqa: E402
from damage_resolution import get_weapons  # noqa: E402 - MECHSIM
from combat import hit_probability  # noqa: E402 - PATHFINDER; reuse the confirmed P(2d6>=tn) table, don't reimplement it

# --- Range-bracket TN modifiers - same values PATHFINDER__combat.py uses
# (RANGE_MOD_SHORT/MEDIUM/LONG), duplicated here rather than imported since
# they're plain BT constants, not logic - avoids a second cross-project
# import just for three integers.
RANGE_MOD_SHORT = 0
RANGE_MOD_MEDIUM = 2
RANGE_MOD_LONG = 4

# Bounded pre-TN axis for the table. Gunnery (0-8ish) + AMM (0-3) + TMM (0-6)
# + Other (roughly -2 to +4) covers this range in practice; hit_probability()
# already returns 0.0 for tn > 12 regardless, so a generously wide bound here
# costs a little extra table space, not correctness.
PRE_TN_MIN = 0
PRE_TN_MAX = 16

_TABLE_CACHE = {}  # (mech id, cache key) -> table dict


def reset_table_cache():
    """Clear all memoized tables - see module docstring's caching note."""
    _TABLE_CACHE.clear()


def _min_range_penalty(minimum, distance):
    """Minimum-range to-hit penalty (Daniel, 2026-10-19): +1 for each hex
    the target is inside the weapon's minimum range, i.e.
    (minimum - distance) + 1 when distance <= minimum, else 0. A weapon
    with no listed minimum range has minimum 0 (Daniel), so no penalty at
    any distance >= 1.
    Example: LRM (minimum 6) at range 4 -> +3; at range 6 -> +1; at 7 -> 0."""
    if minimum and distance <= minimum:
        return minimum - distance + 1
    return 0


def range_bracket(weapon, distance):
    """"short" / "medium" / "long" for firing `weapon` at `distance`, or None
    if out of range or the range data is unconfirmed (2026-10-19 - stealth
    systems' TN bonus depends on the bracket)."""
    wr = weapon.weapon_range
    if wr is None or wr.get("short") is None:
        return None
    if distance <= wr["short"]:
        return "short"
    if distance <= wr["medium"]:
        return "medium"
    if distance <= wr["long"]:
        return "long"
    return None


def _weapon_range_mod(weapon, distance):
    """Range TN modifier for firing `weapon` at `distance`: the Short/Medium/
    Long bracket modifier plus the minimum-range penalty (2026-10-19), or
    None if out of range. equipment.json carries minimum range as
    range["min"]; missing means 0 (Daniel: "If a weapon doesn't list a
    minimum range it is zero")."""
    wr = weapon.weapon_range
    if wr is None or wr.get("short") is None:
        return None  # unconfirmed range data - can't place this weapon on the table at all
    if distance <= wr["short"]:
        bracket = RANGE_MOD_SHORT
    elif distance <= wr["medium"]:
        bracket = RANGE_MOD_MEDIUM
    elif distance <= wr["long"]:
        bracket = RANGE_MOD_LONG
    else:
        return None  # beyond Long - can't fire
    return bracket + _min_range_penalty(wr.get("min") or 0, distance)


def _cache_key(mech):
    """(current_heat, frozenset of live weapon instance ids, PPC capacitor
    charges) - see module docstring's caching policy. A charged capacitor
    changes its PPC's damage (INTEGRATION__capacitor, 2026-10-21)."""
    return (mech.current_heat, frozenset(id(w) for w in get_weapons(mech)),
            tuple(c.charged for c in getattr(mech, "capacitors", ())))


def build_expected_damage_table(mech):
    """table[id(weapon)][distance][pre_tn] -> expected damage (float), or the
    distance key simply absent if every weapon is out of range there. Reuses
    a cached table when (current_heat, live-weapon-set) hasn't changed since
    the last call for this mech - see module docstring."""
    key = _cache_key(mech)
    per_mech_cache = _TABLE_CACHE.setdefault(id(mech), {})
    cached = per_mech_cache.get(key)
    if cached is not None:
        return cached

    weapons = get_weapons(mech)
    max_distance = 0
    for w in weapons:
        if w.weapon_range and w.weapon_range.get("long") is not None:
            max_distance = max(max_distance, w.weapon_range["long"])

    table = {}
    for w in weapons:
        wid = id(w)
        table[wid] = {}
        # damage_per_shot missing (unconfirmed equipment.json row) - skip this
        # weapon on the table entirely rather than raising mid-battle; it's
        # simply never selectable until its data is fixed.
        # (2026-10-18: the orchestrator makes this loud every turn via
        # stubs.stub_unconfirmed_weapon_data().)
        if w.damage_per_shot is None:
            continue
        # An AMS is never an attack (Core p.206) - it only engages incoming
        # missiles (INTEGRATION__ams), so it's never selectable here.
        if weapon_rules.is_ams(w):
            continue
        ed_per_hit = expected_damage.expected_damage_per_hit(w)
        for distance in range(0, max_distance + 1):
            range_mod = _weapon_range_mod(w, distance)
            if range_mod is None:
                continue  # out of range at this distance - no entry
            row = {}
            for pre_tn in range(PRE_TN_MIN, PRE_TN_MAX + 1):
                tn = pre_tn + range_mod
                row[pre_tn] = ed_per_hit * hit_probability(tn)
            table[wid][distance] = row

    # Cap the number of cached (heat, weapon-set) states kept per mech - a
    # mech's heat only takes a handful of distinct values across a real
    # battle (it climbs/cools in small steps), so this is a generous safety
    # valve against unbounded growth, not a real constraint in practice.
    if len(per_mech_cache) > 64:
        per_mech_cache.clear()
    per_mech_cache[key] = table
    return table


# Which bot's fire control makes the choice (2026-10-27, INTEGRATION__bots). None =
# Gladiator's knapsack below. A bot that prices fire its own way (Princess,
# INTEGRATION__princess_fire) sets it for the length of its own thinking with
# fire_control(), so its estimates - and only its - use its rules: the other
# bot's movement scoring never sees it.
_FIRE_CONTROL = None


@contextlib.contextmanager
def fire_control(choose):
    """Within the block, select_weapons_to_fire hands its candidates to
    choose(mech, candidates, dissipation, other_heat, planner, side, movement_heat) ->
    (weapons, value, heat); candidates are (weapon, expected damage, heat,
    to-hit number) for every weapon that can fire."""
    global _FIRE_CONTROL
    saved, _FIRE_CONTROL = _FIRE_CONTROL, choose
    try:
        yield
    finally:
        _FIRE_CONTROL = saved


def _best_subset_python(values, heats, heat_budget):
    """Phase 1 of select_weapons_to_fire: the exact 0/1 knapsack (weight = heat, value =
    expected damage). Returns (best value, heat it uses, indices of the chosen candidates).
    dp[h] = (best value using exactly heat h, chosen indices); candidates in order, heats
    visited high to low, a strictly better value replaces; ties go to the first heat level
    reached (dict order) - INTEGRATION__fastcore's Rust copy follows the same order exactly."""
    dp = {0: (0.0, frozenset())}
    for i, (ed, heat_cost) in enumerate(zip(values, heats)):
        for used_heat in sorted(list(dp.keys()), reverse=True):
            new_heat = used_heat + heat_cost
            if new_heat > heat_budget:
                continue
            new_value = dp[used_heat][0] + ed
            existing = dp.get(new_heat)
            if existing is None or new_value > existing[0]:
                dp[new_heat] = (new_value, dp[used_heat][1] | {i})
    best_heat_used = max(dp, key=lambda h: dp[h][0])
    best_value, best_ids = dp[best_heat_used]
    return best_value, best_heat_used, best_ids


def _best_subset_rust(values, heats, heat_budget):
    """fastcore.best_subset (Rust, the same answer as _best_subset_python - tests/test_fastcore.py);
    Python for what it doesn't take (non-integer heat, more than 64 candidates)."""
    if len(values) > 64:
        return _best_subset_python(values, heats, heat_budget)
    try:
        return _fastcore.best_subset(values, heats, heat_budget)
    except TypeError:
        return _best_subset_python(values, heats, heat_budget)


# Compiled hot loops (2026-11-03, trial - the `fastcore/` Rust crate; config.USE_FASTCORE).
# Speed only: the answers are the Python's, so results don't change. Not built = Python.
try:
    import fastcore as _fastcore
    if not hasattr(_fastcore, "knapsack_levels"):       # the repo's own fastcore/ folder imports as an EMPTY package
        _fastcore = None                                # when the wheel is not built: that means "not built" (Claude, 2026-11-03)
except ImportError:
    _fastcore = None


def best_subset(values, heats, heat_budget):
    """Phase 1's knapsack: Rust when built and switched on (config.USE_FASTCORE), else Python."""
    if _fastcore is not None and INTEGRATION__config.USE_FASTCORE:
        return _best_subset_rust(values, heats, heat_budget)
    return _best_subset_python(values, heats, heat_budget)


def select_weapons_to_fire(mech, distance, pre_tn, min_heat, max_heat, dissipation, movement_heat,
                           other_heat=0, tn_adjust=None, unavailable=frozenset(), value_scale=None,
                           weapons=None, table=None, planner=None, side=None):
    """min_heat/max_heat are passed explicitly (the orchestrator reads them
    off the mech's attached scenario config - mech.min_heat/mech.max_heat),
    while current_heat lives on the MECHSIM BattleMech object (mech).

    HEAT BUDGET - CHANGED 2026-10-18 (Daniel): "Max heat is dissipation +
    the set value. So a max heat of 8 will fire weapons until it reaches 8
    more heat than it can dissipate." Movement heat counts against it, and
    heat carries over turn to turn (mech.current_heat). So max_heat is the
    ceiling on the mech's heat level at the END of the turn:
        current_heat + movement_heat + weapon_heat - dissipation <= max_heat
    i.e. weapon heat budget = max_heat + dissipation - current_heat - movement_heat
    (floored at 0). Was: max_heat - current_heat.
    2026-10-19: other_heat (INTEGRATION__heat.other_heat - engine hits,
    stealth systems, minus planned radical cooling) comes out of the budget
    too - the mech generates it whatever it fires, so max_heat still caps
    the end-of-turn level.
    Not addressed (bot logic, later - Daniel): deciding when to hold fire to
    cool back down to zero. As written, a mech that reaches max_heat stays
    there, firing only what it can sink each turn.
    MIN HEAT - CHANGED 2026-10-19 (Daniel: "the mech wants to sit at a
    minimum of [min_heat] remaining heat at the end of the heat phase"):
    min_heat is now the FLOOR on the end-of-turn heat level, the mirror of
    max_heat. Phase 2 pads until
        current_heat + movement_heat + other_heat + weapon_heat - dissipation >= min_heat
    Was: weapon heat generated this turn >= min_heat.

    tn_adjust (2026-10-19): optional f(weapon, bracket) -> int added to that
    weapon's to-hit number - weapon / targeting computer / arm-crit /
    stealth / aimed-shot modifiers, which differ per weapon.
    unavailable (2026-10-19): ids of weapons that can't fire this turn (a
    prone mech's prop arm and legs).

    Two-phase heat-constrained selection (Daniel, 2026-08-05):

    Phase 1: choose the subset of ALL in-range weapons (energy and ammo-fed
    alike) that maximizes total expected damage, subject to total heat
    generated staying within the mech's heat budget this turn
    (see HEAT BUDGET above). Solved as an exact 0/1 knapsack
    - weapon counts per mech are small enough (a handful of hardpoints) that
    this is cheap without needing an approximation.

    Phase 2: if Phase 1's picks leave the turn ending under min_heat, keep adding remaining
    unfired ENERGY weapons (damage_type == "Energy" only - ammo-fed weapons
    excluded per Daniel: "they'll need their own logic suite on if its worth
    using up limited ammo, later") - even zero-expected-damage ones - highest
    expected-damage-first, until the turn would end at min_heat or no eligible
    energy weapons remain. Still hard-capped at the same heat budget; never
    exceeds max_heat even to chase the floor.

    Weapons with damage_type == None (unverified equipment.json rows) are
    treated as NOT eligible for Phase 2's forced-fire - can't confirm they're
    ammo-free, so the safer default is to leave them out of "burn heat
    regardless of hit chance" rather than risk wasting an unidentified ammo
    weapon's shots. See INTEGRATION__expected_damage module docstring for the
    matching data-gap reasoning.

    pre_tn must be inside [PRE_TN_MIN, PRE_TN_MAX] - callers clamp first.

    weapons / table (2026-10-20, speed): get_weapons(mech) and
    build_expected_damage_table(mech), when the caller already holds them
    for a mech whose state can't change between calls (movement scoring).

    value_scale (2026-10-19, movement scoring only): optional {id(weapon):
    multiplier} applied to each weapon's expected damage before the choice -
    INTEGRATION__structure_weight's "structure damage is worth more". The
    returned total is then WORTH, not raw expected damage. None leaves every
    number unchanged. The attack phase passes the target's AMS factors
    (INTEGRATION__ams.damage_factors, 2026-10-20) - None when it has no AMS
    covering the attacker.

    planner (2026-10-20): an INTEGRATION__fire_modes.Planner for this
    attacker and target. Every weapon fire_modes.special() names (missiles,
    rapid-fire and LB-X autocannons, MML, ATM, Narc beacons) is priced by it
    instead of the table - its chosen shot plan's worth and heat (rapid fire:
    heat per shot; ammunition kind, Artemis / Narc, the target's AMS share, a
    Narc pod's worth). tn_adjust is not added for those: the planner applies it.

    side (2026-10-27): the hit-table side the shots land on, when the caller
    knows it - only another bot's fire control (_FIRE_CONTROL) reads it.

    Returns (selected_weapons: list[Equipment], total_expected_damage: float,
    total_heat: int).
    """
    if _FIRE_CONTROL is not None:
        return _other_fire_control(mech, distance, pre_tn, dissipation, other_heat, tn_adjust, unavailable,
                                   weapons, table, planner, side, movement_heat)
    if weapons is None:
        weapons = get_weapons(mech)
    if table is None:
        table = build_expected_damage_table(mech)
    heat_budget, min_weapon_heat = heat_limits(mech, min_heat, max_heat, dissipation, movement_heat, other_heat)
    candidates = fire_candidates(distance, pre_tn, tn_adjust, unavailable, value_scale, weapons, table, planner)
    # --- Phase 1: 0/1 knapsack, weight = heat, value = expected damage. ---
    best_value, best_heat_used, picked = best_subset([ed for _, ed, _ in candidates],
                                                     [heat for _, _, heat in candidates], heat_budget)
    return _finish_choice(candidates, weapons, best_value, best_heat_used, picked, heat_budget, min_heat,
                          min_weapon_heat)


def heat_limits(mech, min_heat, max_heat, dissipation, movement_heat, other_heat):
    """(weapon heat budget, weapon heat the min_heat floor asks for) - see HEAT BUDGET / MIN HEAT above."""
    heat_budget = max(0, max_heat + dissipation - mech.current_heat - movement_heat - other_heat)
    min_weapon_heat = min_heat + dissipation - mech.current_heat - movement_heat - other_heat
    return heat_budget, min_weapon_heat


def fire_candidates(distance, pre_tn, tn_adjust, unavailable, value_scale, weapons, table, planner):
    """[(weapon, value, heat)] that can fire at this distance - in range, with confirmed heat data.
    Independent of the heat budget, so a FireTable keeps them for every movement heat."""
    candidates = []
    for w in weapons:
        if id(w) in unavailable:
            continue
        if planner is not None and fire_modes.special(w):
            if w.heat is None and not fire_modes.has_profile(w):     # (a bombast laser's heat is per shot)
                continue
            got = planner(w, distance, pre_tn)
            if got is None:
                continue
            value, heat_cost, _ = got
            candidates.append((w, value if value_scale is None else value * value_scale.get(id(w), 1.0), heat_cost))
            continue
        row = table.get(id(w), {}).get(distance)
        if row is None:
            continue  # out of range, or no confirmed damage_per_shot
        if w.heat is None:
            continue  # unconfirmed heat cost - can't budget it, skip rather than guess
        tn = pre_tn
        if tn_adjust is not None:
            tn = max(PRE_TN_MIN, min(PRE_TN_MAX, pre_tn + tn_adjust(w, range_bracket(w, distance))))
        value = row[tn] if value_scale is None else row[tn] * value_scale.get(id(w), 1.0)
        candidates.append((w, value, w.heat))
    return candidates


def _finish_choice(candidates, weapons, best_value, best_heat_used, picked, heat_budget, min_heat, min_weapon_heat):
    """Phase 1's pick (candidate indices) plus Phase 2's padding -> (weapons, expected damage, heat)."""
    selected_ids = {id(candidates[i][0]) for i in picked}
    total_heat = best_heat_used
    total_ed = best_value

    # --- Phase 2: pad toward the min_heat floor with unfired energy weapons. ---
    if min_heat > 0 and total_heat < min_weapon_heat:   # heat can't end below 0, so a 0 floor needs nothing
        remaining_budget = heat_budget - total_heat
        energy_leftovers = [
            (w, ed) for w, ed, _ in candidates
            if id(w) not in selected_ids and w.damage_type == "Energy" and w.heat <= remaining_budget
        ]
        energy_leftovers.sort(key=lambda pair: pair[1], reverse=True)
        for w, ed in energy_leftovers:
            if total_heat >= min_weapon_heat:
                break
            if w.heat > heat_budget - total_heat:
                continue
            selected_ids.add(id(w))
            total_heat += w.heat
            total_ed += ed

    selected_weapons = [w for w in weapons if id(w) in selected_ids]
    return selected_weapons, total_ed, total_heat


# =============================================================================
# ==========================  FIRE TABLES  ====================================
# =============================================================================
# Daniel, 2026-11-03: "Choice should be: 'For that target, what is the base TN, and what is
# the range' After that it should just be a look up table to find the precomputed best mix
# of weapons for that situation." Movement scoring asks the same weapon choice for every
# spot it tries, and the spots differ mostly in their movement heat - which only changes
# the heat budget. One knapsack solved at the largest budget holds the answer for every
# smaller one: dp[h] (the best value using exactly heat h) is built only from levels at or
# below h, so filtering it to h <= budget gives exactly what a knapsack solved at that
# budget would - the same levels, values, chosen weapons, and insertion order, so the same
# tie-break. Heat costs must not be negative for that (else: solved per budget, as before).
class FireTable:
    """Weapon choices by (distance, pre-TN, side): the candidates and their knapsack levels
    at the largest budget asked so far; a query's heat only filters them."""

    def __init__(self, mech, tn_adjust, unavailable, weapons, table, planner):
        self.mech, self.tn_adjust, self.unavailable = mech, tn_adjust, unavailable
        self.weapons, self.table, self.planner = weapons, table, planner
        self._rows = {}            # (distance, pre_tn, side) -> [candidates, levels or None, levels' budget]

    def choose(self, distance, pre_tn, side, value_scale, min_heat, max_heat, dissipation, movement_heat,
               other_heat):
        """select_weapons_to_fire's answer, from the table."""
        heat_budget, min_weapon_heat = heat_limits(self.mech, min_heat, max_heat, dissipation, movement_heat,
                                                   other_heat)
        key = (distance, pre_tn, side)
        row = self._rows.get(key)
        if row is None:
            cands = fire_candidates(distance, pre_tn, self.tn_adjust, self.unavailable, value_scale, self.weapons,
                                    self.table, self.planner)
            values, heats = [v for _, v, _ in cands], [h for _, _, h in cands]
            # [candidates, values, heats, any negative heat, knapsack levels, the budget they were solved at]
            row = self._rows[key] = [cands, values, heats, any(h < 0 for h in heats), None, -1]
        cands = row[0]
        if row[3]:                                                      # (no table: solve this budget)
            best = best_subset(row[1], row[2], heat_budget)
        else:
            if heat_budget > row[5]:
                # Solved at this budget; any smaller budget after it is a lookup, a larger one
                # solves again. (Solving at the largest possible budget up front was tried -
                # the bigger knapsacks cost more than the re-solves they saved, 2026-11-03.)
                row[4], row[5] = knapsack_levels(row[1], row[2], heat_budget), heat_budget
            best = best_within(row[4], heat_budget)
        return _finish_choice(cands, self.weapons, best[0], best[1], best[2], heat_budget, min_heat,
                              min_weapon_heat)


# Shared across scorers (2026-11-03, Daniel: "that Cache is only refreshed if the mech takes
# battle damage that changes its options"): every movement evaluator, Legate round and
# future-damage estimate asking the same attacker the same question about the same target
# shares one FireTable. The key holds everything the choice reads (fire_state below, the
# weapons that can't fire, heat dissipation and other heat, and the caller's `share` - the
# scorer's role: aimed or not, AMS engagements, water). Emptied at the start of every turn
# (stealth / equipment switch then) and when a saved state is loaded; tests/test_fire_tables.py
# runs team battles with config.FIRE_TABLE_VERIFY recomputing every shared answer.
_SHARED_TABLES = {}


def reset_shared_tables():
    _SHARED_TABLES.clear()


def fire_state(mech):
    """What a weapon choice reads of a unit beyond its weapons list: its damage (armor,
    structure, every slot, the rounds in each bin, hit counters - kill_curve's signature),
    heat, prone / shut down, TAG, Narc pods, stealth, TSEMP / IMP effects, switched-off
    heat sinks. Not its position (nothing here reads it)."""
    import INTEGRATION__kill_curve as kill_curve
    import INTEGRATION__equipment_systems as equip
    import INTEGRATION__advanced_weapons as adv
    pods = tuple((p.get("location"), p.get("owner"), p.get("effective")) for p in getattr(mech, "narc_pods", ()))
    return (kill_curve._signature(mech), mech.current_heat, getattr(mech, "heat_fire_modifier", 0), mech.prone,
            mech.shutdown, getattr(mech, "tag_designated", False), pods, tuple(equip.active_stealth(mech)),
            adv.as_if_jammed(mech), adv.imp_level(mech), getattr(mech, "deactivated_heat_sinks", 0),
            mech.min_heat, mech.max_heat)


def shared_fire_table(share, mech, tn_adjust, unavailable, weapons, table, planner, dissipation, other_heat,
                      weighted):
    """The FireTable for this question, shared with every scorer that asks the same one."""
    target = planner.target if planner is not None else None
    key = (share, id(mech), fire_state(mech), id(target), fire_state(target) if target is not None else None,
           unavailable, dissipation, other_heat, weighted)
    got = _SHARED_TABLES.get(key)
    if got is None:
        got = _SHARED_TABLES[key] = FireTable(mech, tn_adjust, unavailable, weapons, table, planner)
    return got


def knapsack_levels(values, heats, heat_budget):
    """_knapsack_levels_python, in Rust when built and switched on (config.USE_FASTCORE)."""
    if (_fastcore is not None and INTEGRATION__config.USE_FASTCORE and len(values) <= 64
            and all(type(h) is int for h in heats)):
        return _fastcore.knapsack_levels(values, heats, heat_budget)
    return _knapsack_levels_python(values, heats, heat_budget)


def _knapsack_levels_python(values, heats, heat_budget):
    """_best_subset_python's dp as [(heat, value, chosen indices)] in its insertion order."""
    dp = {0: (0.0, frozenset())}
    for i, (ed, heat_cost) in enumerate(zip(values, heats)):
        for used_heat in sorted(list(dp.keys()), reverse=True):
            new_heat = used_heat + heat_cost
            if new_heat > heat_budget:
                continue
            new_value = dp[used_heat][0] + ed
            existing = dp.get(new_heat)
            if existing is None or new_value > existing[0]:
                dp[new_heat] = (new_value, dp[used_heat][1] | {i})
    return [(h, v, ids) for h, (v, ids) in dp.items()]


def best_within(levels, heat_budget):
    """(value, heat, indices): the first level, in insertion order, with the highest value
    among those within the budget - max() over the dict a knapsack at that budget would build."""
    best = None
    for h, v, ids in levels:
        if h <= heat_budget and (best is None or v > best[0]):
            best = (v, h, ids)
    return best


def _other_fire_control(mech, distance, pre_tn, dissipation, other_heat, tn_adjust, unavailable, weapons, table,
                        planner, side, movement_heat=0):
    """select_weapons_to_fire for another bot's fire control (_FIRE_CONTROL):
    the same candidates Gladiator's knapsack sees (in range, heat known, the
    planner pricing special weapons), unscaled, with each one's to-hit number,
    handed to that bot to choose from."""
    if weapons is None:
        weapons = get_weapons(mech)
    if table is None:
        table = build_expected_damage_table(mech)
    candidates = []
    for w in weapons:
        if id(w) in unavailable:
            continue
        if planner is not None and fire_modes.special(w):
            if w.heat is None and not fire_modes.has_profile(w):
                continue
            got = planner(w, distance, pre_tn)
            if got is None:
                continue
            value, heat_cost, plan = got
            candidates.append((w, value, heat_cost, planner.value(w, plan, distance, pre_tn)[1]))
            continue
        row = table.get(id(w), {}).get(distance)
        if row is None or w.heat is None:
            continue
        tn = pre_tn
        if tn_adjust is not None:
            tn = max(PRE_TN_MIN, min(PRE_TN_MAX, pre_tn + tn_adjust(w, range_bracket(w, distance))))
        candidates.append((w, row[tn], w.heat, tn + _weapon_range_mod(w, distance)))
    return _FIRE_CONTROL(mech, candidates, dissipation, other_heat, planner, side, movement_heat)
