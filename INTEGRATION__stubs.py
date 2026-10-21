"""
INTEGRATION__stubs.py  (NEW 2026-10-18, Claude - Pile 1; movement selection moved out 2026-10-19)

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
# (Movement selection was the stub `stub_select_movement` here until 2026-10-19;
# it is now INTEGRATION__movement_selection - a real decision, not a placeholder.)

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
    import INTEGRATION__fire_modes as fire_modes     # fire_modes imports this module
    for w in weapons:
        if fire_modes.has_profile(w):
            continue                     # MML: damage and range come from the ammunition (2026-10-20)
        missing = [f for f in ("damage_per_shot", "heat", "weapon_range") if getattr(w, f) is None]
        if missing:
            _warn("unconfirmed_weapon_data", f"{mech_name}'s {w.name} can't fire - null {', '.join(missing)}")


def stub_ammo_data(mech_name, weapon):
    """This weapon's shots per ton isn't in equipment.json (not in the Core
    Rulebook tables - e.g. HVACs, Improved ACs), so its ammo is unlimited.
    Warns each time it fires. No knob.
    TODO: shots_per_ton for these rows from Tactical Operations' tables."""
    _warn("ammo_data", f"{mech_name}'s {weapon.name} fired with unlimited ammo (no shots-per-ton data)")


# --- Weapon-use decisions (Daniel 2026-10-20: still research) ----------------
def stub_munition_choice(mech_name, weapon, options, warn=True):
    """Which ammunition kind / guidance / Apollo mode `weapon` fires
    (INTEGRATION__fire_modes options: [(ShotPlan, expected worth)]).
    Knob: STUB_MUNITION_POLICY. Returns the ShotPlan.
    TODO: a real policy - ammo is limited and some kinds suit some ranges
    (Memo, PROJECT_MAP Section 6)."""
    policy = config.STUB_MUNITION_POLICY

    def plain(plan):
        return plan.munition in ("standard", "homing") and plan.kind in ("", "standard")
    if policy == "random":
        plan = options[config.pick_number(len(options), prompt=f"Pick ammo ({weapon.name})") - 1][0]
    elif policy == "standard":
        plan = next((p for p, _ in options if plain(p)), options[0][0])
    else:
        plan = max(options, key=lambda o: (round(o[1], 9), plain(o[0])))[0]
    if warn:
        _warn("munition_choice", f"{mech_name}'s {weapon.name}: "
              f"{', '.join(f'{p.note or p.munition} {v:.2f}' for p, v in options)} -> "
              f"{plan.note or plan.munition} (policy {policy})")
    return plan


def stub_rate_of_fire(mech_name, weapon, priced, warn=True):
    """Shots an Ultra / Rotary AC fires ([(shots, expected damage)]).
    Knob: STUB_RATE_OF_FIRE. TODO: weigh heat, ammo and a Rotary's jam risk."""
    policy = config.STUB_RATE_OF_FIRE
    if policy == "single":
        shots = priced[0][0]
    elif policy == "greedy":
        shots = max(priced, key=lambda o: (round(o[1], 9), -o[0]))[0]
    else:
        shots = priced[-1][0]
    if warn:
        _warn("rate_of_fire", f"{mech_name}'s {weapon.name}: {len(priced)} rates possible -> {shots} shot"
              f"{'s' if shots > 1 else ''} (policy {policy})")
    return shots


def stub_unjam(mech_name, weapon, prone=False):
    """Try to unjam a jammed Rotary AC this turn (stand still / walk only).
    Knob: STUB_UNJAM (never while prone). TODO: weigh the lost movement."""
    attempt = bool(config.STUB_UNJAM) and not prone
    _warn("unjam", f"{mech_name}'s {weapon.name} is jammed -> {'tries to unjam' if attempt else 'stays jammed'}")
    return attempt


def stub_escalating_use(mech_name, label, cycle_on, warn=True):
    """Use MASC / supercharger / radical heat sinks this turn? cycle_on: what
    Daniel's 1-on / 1-off cycle says. Knob: STUB_ESCALATING_USE.
    TODO: weigh this turn's gain against the rising failure chance (Memo)."""
    policy = config.STUB_ESCALATING_USE
    use = cycle_on if policy == "cycle" else policy == "always"
    if warn:
        _warn("escalating_use", f"{mech_name}'s {label}: {'used' if use else 'not used'} this turn (policy {policy})")
    return use


# --- Equipment choices (Daniel 2026-10-21: "Wire in equipment that requires
# choice ... but defer the actual bot decision making for later") ------------
def stub_charge_spikes(mech_name, clusters):
    """Declare torso spikes for a charge (p.196: +2 damage a cluster, but each
    spiked location the charge damages risks losing its cluster)? Knob:
    STUB_CHARGE_SPIKES. TODO: weigh the damage against the spikes' defensive
    worth later (Memo)."""
    use = bool(config.STUB_CHARGE_SPIKES)
    _warn("charge_spikes", f"{mech_name}'s {clusters} torso spike cluster(s): {'used' if use else 'not used'} "
                           f"in the charge")
    return use


def stub_vibroblade(mech_name, blade, warn=True):
    """Activate a vibroblade for this attack (p.196: fixed damage and heat)?
    Knob: STUB_VIBROBLADE ("on" / "off"). TODO: weigh the extra damage
    against the heat (Memo)."""
    on = config.STUB_VIBROBLADE == "on"
    if warn:
        _warn("vibroblade", f"{mech_name}'s {blade}: {'activated' if on else 'not activated'}")
    return on


def stub_raise_shield(mech_name, phase, arms):
    """Raise a shield this phase (p.195: more locations protected, but nothing
    behind it attacks)? arms: the arms with a usable shield. Returns the arm
    to raise, or None. Knob: STUB_RAISE_SHIELD ("never" / "always").
    TODO: raise when the shielded locations have nothing worth firing (Memo)."""
    arm = arms[0] if config.STUB_RAISE_SHIELD == "always" and arms else None
    _warn("raise_shield", f"{mech_name} ({phase}): {'raises its ' + arm + ' shield' if arm else 'keeps its shield lowered'}")
    return arm


def stub_console_swap(mech_name, pilot_hits, secondary_hits, pilot_out):
    """End Phase: swap the pilot and the command console's warrior (p.203)?
    Knob: STUB_CONSOLE_SWAP ("when_needed": when the pilot is out or more
    hurt than the secondary / "never"). TODO: a real policy (Memo)."""
    swap = (config.STUB_CONSOLE_SWAP == "when_needed"
            and (pilot_out or pilot_hits > secondary_hits) and secondary_hits < 6)
    _warn("console_swap", f"{mech_name}: pilot {pilot_hits} hits{' (out)' if pilot_out else ''}, console "
                          f"{secondary_hits} - {'swap' if swap else 'no swap'}")
    return swap


# =============================================================================
# ==========================  OTHER PHASES  ==================================
# =============================================================================
def stub_heat_explosion_bin(mech_name, tied, damage_value, unknown_names):
    """Which ammo bin explodes from heat (Core Rulebook p.107): the most
    destructive ammo per shot first, then the bin with the most shots left,
    then the controller's choice. INTEGRATION__heat.choose_exploding_bin
    applies the first two steps; this stub covers what it can't:
      - controller's choice: a seeded random pick among the still-tied bins;
      - a bin whose weapon/damage isn't in equipment.json counts as
        damage value 0 (named in the warning).
    `tied`: [(location, bin)] sharing the top damage value. Returns one.
    No knob.
    TODO: a real controller policy (e.g. prefer a bin behind CASE) - pile-4
    decision."""
    pick = tied[config.pick_number(len(tied), prompt="Pick exploding ammo bin") - 1]
    notes = []
    if unknown_names:
        notes.append(f"unknown damage value for {sorted(set(unknown_names))} (counted as 0)")
    if len(tied) > 1:
        notes.append(f"{len(tied)} bins tie at damage value {damage_value} and shots left; "
                     f"controller's choice made at random")
    _warn("heat_explosion_bin", f"{mech_name}: {'; '.join(notes)} -> {pick[1].name} in {pick[0]}")
    return pick
