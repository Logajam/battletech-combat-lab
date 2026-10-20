# Core Rulebook vs code — rules review

Started 2026-10-20 (Claude). The code checked against the Core Rulebook in
`rules/Battletech_Rule_Reference_Index.zip` (`base/core-rules/*.md`, summaries
in `summary/core-rules/*.yaml`). Every entry cites the page. Status words:

- **FIXED** — clear rule, now in the code (Change Record, Section 8 of the
  PROJECT_MAP).
- **GAP** — clear rule, not built yet; Claude's to build.
- **DANIEL** — the code follows a project rule (MECHSIM / PATHFINDER / an
  earlier Daniel decision) that differs from the Core Rulebook. Not Claude's
  to change (PROJECT_MAP Section 7); Daniel decides.
- **LATENT** — wrong or missing, but cannot happen on the boards in `data/`
  today (the default 16x17 Grassland is all level 0, its only terrain is
  woods). Matters as soon as a board has hills, water or roads.

Chapters covered (first pass complete, 2026-10-20): Playing the Game
(sequence of play, initiative, phases, pp.37-41), Movement (pp.42-53),
Combat (LOS, arcs, to-hit, aimed shots, indirect fire, hit location, cluster
hits, ammo, pp.54-83), Damage (pp.84-99), Piloting Skill Rolls, falling and
MechWarrior damage (pp.110-117), Weapons and Equipment (pp.180-215, the
weapons and equipment a 'Mech duel uses), The Battlefield (pp.118-129: woods
only - conditions, fire, ice, mud, snow, swamp and underwater combat need
terrain or options the simulator doesn't have yet). Already page-checked when
built (2026-10-19/20, not repeated): Heat (pp.102-107), physical attacks
(pp.76-83), attack direction, firing arcs and torso twists.
Not applicable to a two-'Mech duel: indirect fire and spotting (needs a
friendly spotter), C3, multiple targets, hidden units, missions, assets,
artillery.

Checked and matching (second batch): the sequence of play - both sides
declare before damage lands, a 'Mech destroyed in a phase still makes its
declared attacks, PSRs then consciousness at the end of each attack phase
(pp.39-40, 76); initiative with ties re-rolled (p.39); automatic hit at TN 2
or less, automatic miss over 12 (p.72); the whole Cluster Hits Table
(p.74, checked cell by cell); ammo used at declaration, Streaks only on a
hit (pp.72, 187); weapon to-hit modifiers (pulse, heavy, VSP, rocket
launchers, MRM cluster -1, pp.185-187); Gauss rifle component explosion
(2 x slots, pp.96, 184); aimed shots (p.70).

---

## Fixed in this pass

| # | Rule | Page | What was wrong |
|---|---|---|---|
| F1 | Target in woods: +1 light, +2 heavy to hit | p.66, pp.68-69 | Missing entirely. Only woods *between* the mechs counted. The default board has 30 woods hexes, so this changes battles: a mech standing in woods is harder to hit, and the bot now uses that. Added to the LOS result (`pathfinder/los.py`), so ranged fire, physical attacks, charges and movement scoring all get it; DFA already ignores terrain (p.79). |
| F2 | Partial cover is read where callers look | p.66 | The cover value was stored on the step next to the target, but aimed shots and charges read the trace's last step (the target's), so they always saw 0. LATENT (no hills on the default board). |
| F3 | Partial cover never comes from the attacker's own hex | p.57 | At range 1 the code looked at the attacker's hex as the "hex next to the target". LATENT. |
| F4 | A leg hit on a target in partial cover strikes the cover - no damage | pp.66, 73 | Only aimed shots handled cover (by re-rolling). Ordinary hits and missile groups now lose a leg hit to the cover; the floating-critical re-roll re-rolls legs (p.95). LATENT. |
| F5 | A head hit always costs the MechWarrior 1 hit | p.117 | When a hit-location 2 (floating critical, p.95) re-rolled onto the Head, the pilot hit was skipped. |
| F7 | An autocannon's first critical hit doesn't destroy it | p.183 | Any crit destroyed it. Now the first crit to an autocannon of any class (AC, LB-X, Ultra, Rotary, light, ProtoMech) uses up the slot but the gun still fires; a second crit to another of its slots destroys it (a one-slot autocannon takes two hits). |
| F8 | Internal explosions: armor loss and CASE venting | p.96 | Ammo explosion damage was capped at 20 before it reached the explosion code, so: a base over 20 never stripped the armor of the location that took the 20th point (a torso: its rear armor); CASE dropped everything over 10 instead of venting up to 10 into the (rear) armor; CASE II applied 1 and dropped the rest instead of up to 10 into the armor, and its crit checks lacked the -1. Bins now carry the uncapped base damage (shots x Damage Value, p.95); `damage_resolution.apply_explosion` applies the caps. |
| F6 | Backward walking (was G1) | pp.45-46, 63 | Built 2026-10-20: a walking mech may step into the hex directly behind it (facing kept); a turn with a backward step never spends more than Walking MP; the hex count for TMM restarts when the mech reverses direction. The battle log marks moves that use it ("includes a backward move"). Not yet offered: backward level changes and backward charges (G11, G12). |

---

## Gaps — Claude's to build (rough priority)

| # | Rule | Page | Notes |
|---|---|---|---|
| G1 | ~~Backward walking~~ | p.46 | Built 2026-10-20 - see F6. |
| G2 | Ground movement: at most 2 levels up or down per hex; 1 with a destroyed hip or leg | pp.46-47, 90, 99 | The table lets a mech climb or drop any height for 1 MP per level. Already on the PATHFINDER backlog ("elevation cap ... unenforced"). LATENT. |
| G3 | Jump landing height: no higher than start level + Jumping MP | p.50 | Only the hexes *passed over* are checked (`combat.build_jump_states`). LATENT. |
| G4 | No moving through the enemy's hex | p.48 | Only ending in its hex is excluded; a path can pass through it. Small effect on open boards (a 1-MP detour). |
| G5 | Jump into your own hex (1 MP) | p.50 | Not offered. Gains the jump TMM bonus and a free facing without moving. Small. |
| G6 | Running into water, rubble and other terrain PSRs; road movement only along the road (+0 only road-to-road, level change -1); stacked terrain costs add up | pp.48, 53, 110-111 | No board in `data/` has these yet. `terrain_rules` raises on stacked costs (loud, fine for now). Road +0 applies even when entering from off-road. LATENT. |
| G7 | Prone mechs are 1 level high for LOS | p.57 | LOS treats every mech as standing. Affects what a prone mech can see or be seen by over low walls / hills. LATENT on a flat board. |
| G8 | Minimum Movement (1 hex ahead with too few MP) | p.49 | Not offered. Rare (very damaged or heat-slowed mechs). |
| G9 | Expected damage ignores leg hits lost to partial cover | p.66 | Movement scoring and weapon choice still count them. LATENT. |
| G10 | Weapons with special Core rules: Ultra / Rotary rate of fire and jams, LB-X cluster ammo | pp.183-186 | Already known (summary banner). Big for mechs that carry them. |
| G11 | Backward level change: one level up or down, a PSR each time (fall in the lower of the two hexes); not with a destroyed hip | pp.46-47, 115 | Backward steps are only offered into same-level hexes: the movement scoring can't price a PSR in the middle of a move yet. LATENT (flat board). |
| G13 | Anti-Missile System (AMS / laser AMS) | p.206 | Not built at all - an AMS never fires. It should engage up to 2 missile attacks a turn from its arc: the Cluster Hits roll at -4 (below 2: every missile destroyed), a Streak treated as a 7, 1 ammo + 1 heat (laser AMS: no ammo, 7 heat IS / 5 Clan). ~240 of the 4,227 units in `data/meks.zip` carry one. Also belongs in the expected-damage numbers (movement scoring, weapon choice). |
| G14 | Armored components | p.207 | Each armored slot absorbs one crit with no effect. Not parsed. ~37 units. |
| G15 | ECM | p.199 | In a duel it matters by cancelling the target's Artemis bonus (G10) and similar; nothing to do until Artemis is built. |
| G12 | Charging after a backward step | p.78 | The charge planner uses forward-only paths (the hex count restarts after a backward step and the planner adds the final forward step). Small. |

---

## Core Rulebook vs the project's rules — for Daniel (D1-D7 decided 2026-10-20)

These follow MECHSIM / PATHFINDER rules or earlier decisions. The code is
consistent; the question is which version the simulator should use.

| # | Topic | Core Rulebook | The code now | Effect |
|---|---|---|---|---|
| D1 | Gyro destroyed (2nd gyro hit) | Falls, prone for good, can't stand, but keeps fighting (prone fire, p.67) - **not destroyed** (p.98) | **Decided 2026-10-20:** option `config.FIGHT_TO_THE_DEATH`. False (default, Daniel's rule): the fight is over when a mech is rendered immobile for good - destroyed. True: the rule as written; it turns on the ground toward the enemy, one hexside a turn. | Crippled / forced withdrawal: a later option (with a bot movement override). |
| D2 | Both legs destroyed | Immobile, can still prop up and fire; destroyed only if it also has no ranged weapons (pp.90, 99) | **Decided:** same option. True: immobile (-4 to be hit, no movement), fires propped up, destroyed when it has no ranged weapons left. | |
| D3 | Several PSR triggers in one phase | One roll per trigger, every roll uses all the phase's modifiers; stop at the first failure (p.110) | **Decided: rules as written** - built 2026-10-20 (one roll per leg however many actuators; movement PSRs too - see D7). | |
| D4 | Seatbelt check after a fall | Piloting + 1 per level fallen, nothing else; automatic hit if immobile or TN over 12 (p.117) | **Decided: rules as written** - built 2026-10-20. | |
| D5 | Which side a fall damages | 1D6: on a 1 the rear, otherwise the front (p.115) | **Decided: rules as written** - built 2026-10-20 (a failed death from above still lands on its back, p.80). | |
| D6 | Hit-location 2 (Through-Armor Critical) | Standard: a crit check on the torso location hit (p.91). Floating Criticals is an **optional** rule (p.95) | **Decided:** option `config.FLOATING_CRITICALS`, default True (floating); False = the standard rule, built 2026-10-20. | |
| D7 | Running with damaged hips | One PSR per trigger (gyro hit, each leg with a destroyed hip or leg), never more than one per leg (pp.45, 110-111) | **Built with D3:** `piloting_rolls.movement_psr_count`; movement scoring prices all the rolls. | |
| D8 | LOS model (Daniel's simplified rules, `pathfinder/los.py`) | Woods count as intervening if their top (hex + 2) reaches both mechs' LOS levels, so woods one level above the higher mech also count; partial cover is lost if the attacker is higher than the target, and a prone mech gets none (pp.57-58, 66) | Woods count only at exactly the higher mech's level; cover doesn't check either condition | Only matters with hills. Daniel's 2026-07-19 rules say don't change without asking. |
| — | Already open in PROJECT_MAP Section 4 | Stand-up PSR -1; tripod -1; jumped with leg destroyed +4; quads standing | MECHSIM values | Unchanged, still waiting. |

Checked and matching the Core Rulebook (no action): the hit-location table
(p.74); the critical-hit check table and slot choice (pp.90-94; picking
uniformly among the slots that can take a crit is the same odds as the 2D6
block roll with re-rolls); crit transfer (p.95); damage transfer (p.89);
the 20+ damage PSR counts armor + structure lost (p.111 fn.1); immobile
targets -4 (p.64); prone target -2 / +1 (p.66); woods blocking at 3 points
(p.58); TMM table and the +1 for jumping (p.69); walking / running / jumping
modifiers (p.69); leg-actuator MP loss and the 1 MP floor (p.99); physical
attacks have no heat modifier (p.63); MechWarrior hits from explosions and
head hits (p.117).
