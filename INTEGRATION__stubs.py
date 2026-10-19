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

import sys
from collections import Counter

import INTEGRATION__config as config
from mech_state import DamageType, all_crew_unconscious
from hit_location import FACING_CHOICES

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


def stub_post_standup_movement(mech_name, remaining_mp):
    """A mech that stood up from prone (MECHSIM resolve_stand_up, real)
    has leftover running MP. What it may do with it, and which AMM/TMM it
    gets, isn't decided. Knob: STUB_POST_STANDUP. Returns (mode, fc).
    TODO: movement after standing (MegaMek get-up handling in movement
    processing, Mek.checkGetUp - name from memory)."""
    _warn("post_standup_movement", f"{mech_name} stood up with {remaining_mp} MP left - stays in hex, "
          f"treated as Stand Still for AMM/TMM (policy={config.STUB_POST_STANDUP})")
    return "Stand Still", 0


# =============================================================================
# ==========================  RANGED COMBAT  =================================
# =============================================================================
def stub_attack_direction(attacker_name, target_name, battle_rng):
    """Which hit-location table (front/left/right/rear) a shot uses. Should
    come from the attacker's position relative to the target's facing; no
    function for that exists yet. Knob: STUB_HIT_TABLE_SIDE.
    TODO: MegaMek Entity.sideTable(...) / ToHitData.SIDE_* (names from
    memory); also how this relates to PATHFINDER's confirmed 60-degree
    rear-arc rule (which currently only decides whether a mech can FIRE)."""
    mode = config.STUB_HIT_TABLE_SIDE
    if mode == "front":
        side = "front"
    elif mode == "mechsim_random":
        side = FACING_CHOICES[battle_rng.pick_number(len(FACING_CHOICES)) - 1]
    else:
        raise ValueError(f"Unknown STUB_HIT_TABLE_SIDE {mode!r}")
    _warn("attack_direction", f"{attacker_name} -> {target_name}: '{side}' hit table ({mode})")
    return side


def stub_cluster_grouping(weapon, total_damage):
    """How connected cluster damage is split into separate hit-location
    rolls. equipment.json has no group-size field. Knob:
    STUB_CLUSTER_GROUPING. Returns a list of damage groups.
    TODO: group size per weapon family - Daniel to confirm; MegaMek missile
    weapon handlers (MissileWeaponHandler / LRMHandler / SRMHandler - names
    from memory). Once known, put it in equipment.json, not here."""
    mode = config.STUB_CLUSTER_GROUPING
    if total_damage <= 0:
        groups = []
    elif mode == "single_group":
        groups = [total_damage]
    elif mode == "per_missile":
        per = weapon.damage_per_shot or 1
        groups = [per] * int(total_damage // per)
        rem = total_damage - per * len(groups)
        if rem > 0:
            groups.append(rem)
    else:
        raise ValueError(f"Unknown STUB_CLUSTER_GROUPING {mode!r}")
    _warn("cluster_grouping", f"{weapon.name}: {total_damage} connected damage -> groups {groups} ({mode})")
    return groups


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
    damage, heat, minimum range (also needs data)."""
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
    if attacker.current_heat > 0:
        missing.append(f"attacker heat {attacker.current_heat}")
    if missing:
        _warn("to_hit_modifiers_not_applied", f"{attacker_name} -> {target_name}: {', '.join(missing)}")


# =============================================================================
# ==========================  OTHER PHASES  ==================================
# =============================================================================
def stub_physical_combat(turn_number):
    """Physical Combat phase - deferred by Daniel's scope call. No-op.
    TODO: whole phase (kicks/punches/charges/DFA)."""
    _warn("physical_combat", f"turn {turn_number}: phase skipped (not built)")


def stub_heat_effects(mech_name, mech):
    """Heat ACCUMULATION is real as of 2026-10-18 (orchestrator._phase_heat:
    heat carries over; movement + weapon heat - dissipation). What's still
    missing is what heat DOES. Runs whenever a mech ends the Heat Phase
    carrying heat or with engine hits. No knob.
    TODO: Heat Scale from Daniel (to-hit and MP penalties, shutdown and
    ammo-explosion avoidance rolls); engine-hit heat (not confirmed for
    this project - not applied). MegaMek heat resolution in the game manager
    (resolveHeat - name from memory). Deciding when to hold fire to cool
    down is bot logic (Daniel: later), not part of this stub."""
    missing = []
    if mech.current_heat > 0:
        missing.append(f"heat {mech.current_heat}: no Heat Scale effects applied")
    if mech.engine_hits > 0:
        missing.append(f"{mech.engine_hits} engine hit(s): no engine heat added")
    if missing:
        _warn("heat_effects", f"{mech_name}: {'; '.join(missing)}")
