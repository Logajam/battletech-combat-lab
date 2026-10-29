"""
INTEGRATION__bots.py

Which bot drives each unit (Daniel, 2026-10-27: "The ability to select what
type of bot each unit uses. The current system that makes up the bot shall be
called 'Gladiator'. I would like to make a clone of Megamek's Princess bot to
compare it against.").

Set per side with MECH_*_CONFIG["bot"] (None = config.BOT). The orchestrator
asks this module for a unit's decisions, and this module hands them to that
unit's bot:

  "gladiator" - the bot this project has built so far: movement_selection
                (two-ply, "lifetime" objective, grid search), weapon_selection /
                fire_modes / physical.choose_attack and every Section 6 row.
  "princess"  - a port of MegaMek's Princess: modern (main, 2026-10-26 -
                INTEGRATION__princess_modern) or v0.50.07 (INTEGRATION__princess)
                by config.PRINCESS_VERSION; fire control and physical-attack
                choice (INTEGRATION__princess_fire), at the behavior sliders
                in config.PRINCESS_BEHAVIOR. PROJECT_MAP Section 6, "Princess
                clone", lists what was ported and what wasn't.

Decision points routed here: movement (choose_movement), which weapons fire
(fire_control - wraps the attack phase's weapon choice), and the physical
attack (choose_physical). Every other Section 6 decision (ammunition kind,
rate of fire, MASC, AMS, heat sinks...) is shared by both bots.
"""

import contextlib

import INTEGRATION__config as config
import INTEGRATION__stubs as stubs
import INTEGRATION__movement_selection as movement_selection
import INTEGRATION__forces as forces
import INTEGRATION__legate as legate
import INTEGRATION__princess as princess
import INTEGRATION__princess_group as princess_group
import INTEGRATION__princess_modern as princess_modern
import INTEGRATION__princess_fire as princess_fire
import INTEGRATION__kill_curve as kill_curve
import INTEGRATION__weapon_selection as weapon_selection

GLADIATOR = "gladiator"
PRINCESS = "princess"
BOTS = (GLADIATOR, PRINCESS)
# Bots whose decisions are built; the rest are refused at load time.
BUILT = (GLADIATOR, PRINCESS)


def bot_for(cfg):
    """The bot named by one side's MECH_*_CONFIG (its "bot" key, else
    config.BOT), checked. Raises on an unknown or unbuilt bot."""
    name = (cfg.get("bot") or config.BOT).lower()
    if name not in BOTS:
        raise ValueError(f"Unknown bot {name!r} - choose one of {', '.join(BOTS)} "
                         f"(config.BOT / MECH_*_CONFIG['bot']).")
    if name not in BUILT:
        raise NotImplementedError(f"The {name!r} bot isn't built yet. Use {GLADIATOR!r}.")
    return name


def choose_movement(mover, other, terrain_map, battle_rng, moves_first, standup_mp=None, entry_edge=None):
    """The mover's end-of-movement pick, from the mover's own bot. Same
    arguments and return as movement_selection.choose: (pick, note)."""
    if mover.bot == PRINCESS and config.PRINCESS_VERSION == "modern":
        return princess_modern.choose(mover, other, terrain_map, battle_rng, moves_first,
                                      standup_mp=standup_mp, entry_edge=entry_edge)
    if mover.bot == PRINCESS:
        return princess.choose(mover, other, terrain_map, battle_rng, moves_first,
                               standup_mp=standup_mp, entry_edge=entry_edge)
    return movement_selection.choose(mover, other, terrain_map, battle_rng, moves_first,
                                     standup_mp=standup_mp, entry_edge=entry_edge)


def choose_foe(mover, units, terrain_map):
    """The enemy this unit's movement is planned against: for a Gladiator with Legate on, the enemy
    expected to score highest against it among those yet to move (INTEGRATION__legate.foe_for); else the
    nearest (forces.choose_foe)."""
    if mover.bot == GLADIATOR:
        foe = legate.foe_for(mover, units, terrain_map)
        if foe is not None:
            return foe
    return forces.choose_foe(mover, units) or forces.any_enemy(mover, units)


def choose_target(attacker, units, terrain_map):
    """The one enemy this unit's bot fires at in the Ranged Attack Phase:
    Princess takes the enemy its firing plans rate highest, with the damage
    its friends have already declared counted (INTEGRATION__princess_group).
    For Gladiator, with two or more enemies on the board,
    config.STUB_GLADIATOR_TARGET decides - "kill_curve" is Gladiator's own
    fire director (INTEGRATION__kill_curve: the most mission-kill chance
    added, friends' declared fire counted), "princess_plan" borrows
    Princess's choice (seen through Princess's fire control, see
    princess_eyes), "nearest" is forces.choose_target (in sight, bears,
    nearest)."""
    if attacker.bot == PRINCESS:
        return princess_group.choose_target(attacker, units, terrain_map)
    policy = config.STUB_GLADIATOR_TARGET
    if policy == "kill_curve":
        # Gladiator's own fire director (INTEGRATION__kill_curve) - no stub.
        if len(princess_group.candidates(attacker, units)) >= 2:
            target = kill_curve.choose_target(attacker, units, terrain_map)
            return target if target is not None else forces.choose_target(attacker, units, terrain_map)
    elif policy == "princess_plan":
        enemies = len(princess_group.candidates(attacker, units))
        if enemies >= 2:
            with princess_eyes(attacker):
                target = princess_group.choose_target(attacker, units, terrain_map)
            return stubs.stub_gladiator_target(attacker.side_name, target, enemies)
    elif policy != "nearest":
        raise ValueError(f"Unknown STUB_GLADIATOR_TARGET {policy!r} - choose 'princess_plan', 'kill_curve' "
                         f"or 'nearest'.")
    return forces.choose_target(attacker, units, terrain_map)


def fire_pick(units, terrain_map):
    """Gladiator's FIRING ORDER (config.GLADIATOR_FIRE_ORDER; 2026-10-29, Daniel: "A general rule for
    firing order is Big guns first followed by smaller guns. Its the same rule used on a mech, just
    applied to the entire formation."): within each of its side's selections (the alternation and
    Unequal Numbers stay, p.41), a side's Gladiator units declare biggest guns first - the most
    expected damage this unit could deal any enemy now (kill_curve.firepower, the dry run of its
    own weapon choice) - so the smaller guns that declare later see the big guns' fire in the
    team's damage map and fill in around it. Only matters when Gladiator's target choice reads
    that map (STUB_GLADIATOR_TARGET "kill_curve" / "princess_plan"). Princess units keep roster
    order (MegaMek's order is not cloned), after a mixed side's Gladiators. Returns the pick
    function for forces.fire_order, or None for roster order."""
    teams = [u.team for u in forces.standing(units) if u.bot != PRINCESS]
    if config.GLADIATOR_FIRE_ORDER == "roster" or all(teams.count(t) < 2 for t in teams):
        return None                                  # no side has two Gladiators: nothing to order
    if config.GLADIATOR_FIRE_ORDER != "big_guns_first":
        raise ValueError(f"Unknown GLADIATOR_FIRE_ORDER {config.GLADIATOR_FIRE_ORDER!r} "
                         f"('big_guns_first' or 'roster')")
    guns = {}

    def rank(u):
        if u.bot == PRINCESS:
            return (0, 0.0)
        if id(u) not in guns:
            guns[id(u)] = kill_curve.firepower(u, units, terrain_map)
        return (1, guns[id(u)])

    def pick(candidates):
        best = max(candidates, key=rank)            # max keeps the first of equals: roster order
        if best.bot != PRINCESS and len(candidates) > 1:
            config.log(f"  [Ranged] Firing order: {best.side_name} declares next "
                       f"(big guns first: expected {guns[id(best)]:.1f}).")
        return best
    return pick


# Units whose candidate targets are being scored through Princess's eyes right now (a Gladiator under
# STUB_GLADIATOR_TARGET "princess_plan"): fire_control and plans_physical_with_fire answer as for Princess,
# so the dry-run declaration (attack_resolution.declare_attacks, dry=True) returns Princess's utility.
_PRINCESS_EYES = set()


@contextlib.contextmanager
def princess_eyes(attacker):
    _PRINCESS_EYES.add(id(attacker))
    try:
        yield
    finally:
        _PRINCESS_EYES.discard(id(attacker))


def _as_princess(attacker):
    return attacker.bot == PRINCESS or id(attacker) in _PRINCESS_EYES


def records_declared_damage(attacker):
    """Does this unit's declaration go into its team's damage map (princess_fire.assign_damage), for the
    teammates who pick a target after it? Princess's always does; a Gladiator's does when it borrows
    Princess's target choice (STUB_GLADIATOR_TARGET "princess_plan") or runs its own fire director
    ("kill_curve")."""
    return attacker.bot == PRINCESS or config.STUB_GLADIATOR_TARGET in ("princess_plan", "kill_curve")


def fire_control(attacker):
    """A context for the attack phase's weapon choice: Gladiator's knapsack
    (nothing to change), or Princess's FireControl. The object (or None)
    comes back for the log."""
    if _as_princess(attacker):
        chooser = princess_fire.FireControl(guess=False)
        return weapon_selection.fire_control(chooser), chooser
    return contextlib.nullcontext(), None


def plans_physical_with_fire(attacker):
    """Gladiator plans ranged fire and the physical attack that follows
    together (attack_resolution._physical_planner); Princess fires first and
    picks its physical attack in the Physical phase."""
    return not _as_princess(attacker)


def choose_physical(attacker, target, terrain_map):
    """The attacker's physical attack: (base TN, [options], arc action) or None."""
    if attacker.bot == PRINCESS:
        return princess_fire.choose_physical(attacker, target, terrain_map)
    import INTEGRATION__physical as physical          # physical imports the attack modules
    return physical.choose_attack(attacker, target, terrain_map)
