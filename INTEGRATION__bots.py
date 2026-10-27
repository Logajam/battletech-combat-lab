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
  "princess"  - a port of MegaMek's Princess (BasicPathRanker, FireControl,
                PhysicalInfo), MegaMek v0.50.07 as the reference. NOT BUILT
                YET - the plan is PROJECT_MAP Section 6, "Princess clone".
                Choosing it stops the run at load time (no silent fallback).

Decision points routed so far: movement (choose_movement). Ranged fire and
physical attacks still go straight to Gladiator's code in attack_resolution /
physical; they get routed here when Princess's FireControl is ported.
"""

import INTEGRATION__config as config
import INTEGRATION__movement_selection as movement_selection

GLADIATOR = "gladiator"
PRINCESS = "princess"
BOTS = (GLADIATOR, PRINCESS)
# Bots whose decisions are built; the rest are refused at load time.
BUILT = (GLADIATOR,)


def bot_for(cfg):
    """The bot named by one side's MECH_*_CONFIG (its "bot" key, else
    config.BOT), checked. Raises on an unknown or unbuilt bot."""
    name = (cfg.get("bot") or config.BOT).lower()
    if name not in BOTS:
        raise ValueError(f"Unknown bot {name!r} - choose one of {', '.join(BOTS)} "
                         f"(config.BOT / MECH_*_CONFIG['bot']).")
    if name not in BUILT:
        raise NotImplementedError(f"The {name!r} bot isn't built yet (PROJECT_MAP Section 6, "
                                  f"'Princess clone'). Use {GLADIATOR!r} for now.")
    return name


def choose_movement(mover, other, terrain_map, battle_rng, moves_first, standup_mp=None, entry_edge=None):
    """The mover's end-of-movement pick, from the mover's own bot. Same
    arguments and return as movement_selection.choose: (pick, note)."""
    if mover.bot == GLADIATOR:
        return movement_selection.choose(mover, other, terrain_map, battle_rng, moves_first,
                                         standup_mp=standup_mp, entry_edge=entry_edge)
    raise NotImplementedError(f"{mover.side_name}: no movement for bot {mover.bot!r}")
