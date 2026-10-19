"""
INTEGRATION__stubs.py  (NEW 2026-10-18, Claude - Pile 1, plus Pile 4 for movement selection)

Every placeholder the end-to-end battle loop needs, one clearly named
function each. Rules for everything in this file (Daniel, 2026-10-18):

  - Each stub prints a loud "STUB: <name> - <what it did instead>" line to
    stderr EVERY time it runs (not gated by VERBOSE).
  - Each run is counted into the current battle's stub report
    (active_stubs()), which ends up on every BattleResult and in the batch
    summary banner - so no result can be read without seeing what was faked.
  - Every tunable value lives in INTEGRATION__config.py's STUB SETTINGS
    block, not here.
  - Nothing here is a BattleTech rule. Where a real rule is missing or
    disputed, the TODO names what to check. MegaMek class/method names in
    the TODOs are from memory and may have been renamed (MegaMek renamed
    Mech -> Mek in recent versions) - grep the MegaMek source to confirm
    before relying on any of them.

When a stub gets replaced by real logic, delete its function and its CONFIG
knobs, and add a Change Record line in INTEGRATION__PROJECT_MAP.md.
"""

import re
import sys
from collections import Counter

import INTEGRATION__config as config
from mech_state import DamageType, all_crew_unconscious

# =============================================================================
# ==========================  REGISTRY  ======================================
# =============================================================================
_ACTIVE = Counter()


def reset_battle_stubs():
    """Called by the orchestrator at the start of every battle."""
    _ACTIVE.clear()


def active_stubs():
    """{stub_name: times_it_ran} for the current battle (plain dict copy)."""
    return dict(_ACTIVE)


def _warn(name, msg):
    _ACTIVE[name] += 1
    sys.stdout.flush()
    print(f"STUB: {name} - {msg}", file=sys.stderr, flush=True)


# =============================================================================
# ==========================  DEPLOYMENT  ====================================
# =============================================================================
def stub_deployment(mech_cfg, side_name):
    """Starting hex/facing. Section 2's build target is: turn 1, initiative
    loser enters from their map edge, winner from the opposite edge. Not
    built - fixed hexes from MECH_*_CONFIG instead.
    TODO: Daniel's Section 2 edge-entry procedure (which edge, how entry MP
    is spent). MegaMek reference for deployment zones: Board deployment-zone
    logic (e.g. Board.isLegalDeployment - name from memory)."""
    _warn("deployment", f"{side_name} placed at fixed CONFIG hex {mech_cfg['hex']} facing "
          f"{mech_cfg['facing']} (edge entry not built)")
    return mech_cfg["hex"], mech_cfg["facing"]


# =============================================================================
# ==========================  MOVEMENT  ======================================
# =============================================================================
def _dist_to_enemy(cand, enemy_xy, hex_geometry, hex_distance):
    return hex_distance(hex_geometry.parse_hex_label(cand["hex"]), enemy_xy)


def stub_select_movement(mover_name, los_candidates, reachable_states, enemy_hex, battle_rng):
    """Picks the mover's end-of-movement state.

    los_candidates: MovementCandidate list from
        INTEGRATION__ranged_combat.evaluate_going_second() - REAL reachable
        states with REAL expected dealt/received against the enemy's current
        position (projection for the first mover, actual for the second).
    reachable_states: every reachable state as dicts {hex, facing, mode, fc,
        mp_spent} - used only when no candidate has LOS.

    The CHOICE is the placeholder: which spot a real bot should pick (what
    scoring formula) is Daniel's open decision (PROJECT_MAP Section 4/6).
    Knobs: STUB_MOVEMENT_POLICY, STUB_NO_LOS_FALLBACK.
    TODO: real scoring formula (PATHFINDER combat.compute_score exists but
    is built on flat HP/weapon dicts); the two-ply look-ahead in
    PATHFINDER__combat_turn.py is not ported. Reference only, not a rule:
    MegaMek's Princess bot path ranking (BasicPathRanker - name from memory).
    """
    import hex_geometry
    from los import hex_distance
    enemy_xy = hex_geometry.parse_hex_label(enemy_hex)

    def tiebreak_pick(pool, primary):
        best = max(primary(c) for c in pool)
        pool = [c for c in pool if primary(c) == best]
        nearest = min(_dist_to_enemy(c, enemy_xy, hex_geometry, hex_distance) for c in pool)
        pool = [c for c in pool if _dist_to_enemy(c, enemy_xy, hex_geometry, hex_distance) == nearest]
        least_recv = min(c.get("received", 0.0) for c in pool)
        pool = [c for c in pool if c.get("received", 0.0) == least_recv]
        return pool[battle_rng.pick_number(len(pool)) - 1]

    if los_candidates:
        cands = [vars(c) for c in los_candidates]
        policy = config.STUB_MOVEMENT_POLICY
        if policy == "random":
            pick = cands[battle_rng.pick_number(len(cands)) - 1]
        elif policy == "max_dealt_minus_received":
            pick = tiebreak_pick(cands, lambda c: round(c["dealt"] - c["received"], 9))
        elif policy == "max_dealt":
            pick = tiebreak_pick(cands, lambda c: round(c["dealt"], 9))
        else:
            raise ValueError(f"Unknown STUB_MOVEMENT_POLICY {policy!r}")
        _warn("movement_selection", f"{mover_name} picked {pick['hex']} {pick['facing']} {pick['mode']} "
              f"(policy={policy}, {len(cands)} LOS candidates, exp. dealt {pick['dealt']:.2f} / "
              f"recv {pick['received']:.2f})")
        return pick

    fallback = config.STUB_NO_LOS_FALLBACK
    if fallback == "stay" or not reachable_states:
        _warn("movement_selection", f"{mover_name} has no reachable spot with LOS - stays put "
              f"(fallback={fallback})")
        return None
    if fallback == "random_reachable":
        pick = reachable_states[battle_rng.pick_number(len(reachable_states)) - 1]
    elif fallback == "closest_to_enemy":
        pick = tiebreak_pick(reachable_states,
                             lambda c: -_dist_to_enemy(c, enemy_xy, hex_geometry, hex_distance))
    else:
        raise ValueError(f"Unknown STUB_NO_LOS_FALLBACK {fallback!r}")
    _warn("movement_selection", f"{mover_name} has no reachable spot with LOS - moved to "
          f"{pick['hex']} {pick['facing']} {pick['mode']} (fallback={fallback})")
    return pick


def stub_walk_movement_psr(mech_name, mode):
    """MECHSIM's check_movement_psr only defines triggers for running and
    jumping (Daniel 2026-07-16). Returns the mode string to check a
    Walk/Stand Still move against, or None for no movement PSR.
    Knob: STUB_WALK_PSR_AS. Only called (and only warns) when the mech
    actually has gyro/hip/leg damage that WOULD trigger under running rules.
    TODO: whether walking with gyro/hip/leg damage requires a PSR. MegaMek
    reference: movement-phase PSR checks in the movement processing code
    (PilotingRollData usages - name from memory)."""
    choice = config.STUB_WALK_PSR_AS
    _warn("walk_movement_psr", f"{mech_name} moved '{mode}' with leg/gyro damage - "
          f"{'no movement PSR made' if choice is None else 'checked as ' + choice}")
    return choice


# =============================================================================
# ==========================  RANGED COMBAT  =================================
# =============================================================================
def stub_unknown_damage_type(weapon):
    """equipment.json damage_type is null for this weapon. Only matters for
    special armor types (armor_rules dispatch). Knob: STUB_UNKNOWN_DAMAGE_TYPE.
    TODO: curate this equipment.json row."""
    dt = DamageType[config.STUB_UNKNOWN_DAMAGE_TYPE]
    _warn("unknown_damage_type", f"{weapon.name} has damage_type null - treated as {dt.name}")
    return dt


def stub_unconfirmed_weapon_data(mech_name, weapons):
    """Makes weapon_selection's silent skip of weapons with null damage/heat/
    range loud. They never fire. No knob.
    TODO: equipment.json curation (e.g. ISLBXAC10); LB-X/Ultra handlers."""
    for w in weapons:
        missing = [f for f in ("damage_per_shot", "heat", "weapon_range") if getattr(w, f) is None]
        if missing:
            _warn("unconfirmed_weapon_data", f"{mech_name}'s {w.name} can't fire - null {', '.join(missing)}")


def stub_ammo(mech_name, weapon):
    """Ammo is unlimited: shots_per_ton is null in equipment.json and bins
    aren't linked to weapons. Warns each time a non-energy weapon fires.
    No knob. (Ammo bins still explode on a crit - that part is real.)
    TODO: shot counts + bin linkage (MegaMek Mounted.getLinked(),
    AmmoType shots - names from memory)."""
    _warn("ammo", f"{mech_name}'s {weapon.name} fired with unlimited ammo")


# One-shot launcher names in equipment.json: "LRM 5 (OS)", "CLLRM10 (OS)",
# "ISSRM2OS", "CLOSStreakLRM5", "CLIOSStreakLRM5", "CLNarcBeacon (OS)".
# A name pattern, not a rule; checked against every weapon entry 2026-10-19
# (45 matches, all one-shots).
_ONE_SHOT_NAME = re.compile(r"\(I?-?OS\)|OS$|^CLI?OS")


def is_one_shot(weapon):
    return bool(_ONE_SHOT_NAME.search(weapon.name or ""))


def stub_one_shot(mech_name, weapon):
    """One-shot (OS/I-OS) launchers have their base launcher's damage/range
    (Daniel, 2026-10-19) but may only fire once per battle. That limit is
    not enforced yet - they fire every turn. Warns each time one fires.
    No knob.
    TODO: track "already fired" per weapon instance (reset per battle by
    clone_mech), then drop it from select_weapons_to_fire's candidates."""
    _warn("one_shot", f"{mech_name}'s {weapon.name} fired again - fire-once limit not enforced")


def detect_rear_mounted(mtf_path):
    """Not a stub itself - scans the raw .mtf text for '(R)' crit lines
    (mtf_parser strips the tag, so the parsed mech can't tell). Returns a
    list of raw names. Read-only; no MECHSIM edit."""
    found = []
    try:
        with open(mtf_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                # crit-slot lines only: skip "key:value" headers and the
                # "Weapons:" summary block ("Name, Location (R)")
                if "(R)" in s.upper() and ":" not in s and "," not in s:
                    found.append(s)
    except OSError:
        pass
    return found


def stub_rear_mounted_weapons(mech_name, rear_lines):
    """Rear-mounted weapons fire forward because the parser drops the '(R)'
    tag. Called once per battle per mech that has any.
    Knob: STUB_REAR_MOUNTED.
    TODO: rear arcs (MegaMek Mounted.isRearMounted(), Compute.isInArc() -
    names from memory). Needs either a parser change (MECHSIM, Daniel's
    call) or an INTEGRATION-side mount table."""
    if rear_lines:
        _warn("rear_mounted_weapons", f"{mech_name} has rear-mounted crit lines {sorted(set(rear_lines))} "
              f"- policy {config.STUB_REAR_MOUNTED}")


def stub_to_hit_modifiers_not_applied(attacker, target, attacker_name, target_name):
    """Warns when a condition is present whose to-hit modifier is NOT
    applied (TN = gunnery + AMM + TMM + LOS + range only). Immobile
    targets (all crew unconscious) DO get MECHSIM's existing -4 TMM - that
    one is applied, not listed here. No knob.
    TODO: MegaMek to-hit assembly (ComputeToHit / WeaponAttackAction.toHit()
    - names from memory): prone target/attacker, sensor hits, arm actuator
    damage. (Minimum range IS applied since 2026-10-19 - part of the
    range modifier in weapon_selection._weapon_range_mod. Heat IS applied
    since 2026-10-19 - INTEGRATION__heat, mech.heat_fire_modifier.)"""
    missing = []
    if target.prone and not all_crew_unconscious(target):
        missing.append("target prone")
    if attacker.prone:
        missing.append("attacker prone")
    destroyed_names = [info["name"] for info in attacker.destroyed_slot_info.values()]
    if "Sensors" in destroyed_names:
        missing.append("attacker sensor hit")
    arm_act = [n for n in destroyed_names if n in ("Shoulder", "Upper Arm Actuator", "Lower Arm Actuator",
                                                    "Hand Actuator")]
    if arm_act:
        missing.append("attacker arm actuator damage")
    if missing:
        _warn("to_hit_modifiers_not_applied", f"{attacker_name} -> {target_name}: {', '.join(missing)}")


# =============================================================================
# ==========================  OTHER PHASES  ==================================
# =============================================================================
def stub_physical_combat(turn_number):
    """Physical Combat phase - deferred by Daniel's scope call. No-op.
    TODO: whole phase (kicks/punches/charges/DFA)."""
    _warn("physical_combat", f"turn {turn_number}: phase skipped (not built)")


def stub_heat_explosion_bin(mech_name, tied, damage_value, unknown_names):
    """Which ammo bin explodes from heat (Core Rulebook p.107): the most
    destructive ammo per shot first, then the bin with the most shots left,
    then the controller's choice. INTEGRATION__heat.choose_exploding_bin
    applies the first step; this stub covers what it can't:
      - shots left: not tracked (ammo is unlimited - see stub_ammo), so
        that tie-break is skipped;
      - controller's choice: a seeded random pick among the tied bins;
      - a bin whose weapon/damage isn't in equipment.json counts as
        damage value 0 (named in the warning).
    `tied`: [(location, bin)] sharing the top damage value. Returns one.
    No knob.
    TODO: shot counts per bin (same data stub_ammo needs), and a real
    controller policy (e.g. prefer a bin behind CASE) - pile-4 decision."""
    pick = tied[config.pick_number(len(tied), prompt="Pick exploding ammo bin") - 1]
    notes = []
    if unknown_names:
        notes.append(f"unknown damage value for {sorted(set(unknown_names))} (counted as 0)")
    if len(tied) > 1:
        notes.append(f"{len(tied)} bins tie at damage value {damage_value}; shots-left tie-break skipped "
                     f"(not tracked), controller's choice made at random")
    _warn("heat_explosion_bin", f"{mech_name}: {'; '.join(notes)} -> {pick[1].name} in {pick[0]}")
    return pick
