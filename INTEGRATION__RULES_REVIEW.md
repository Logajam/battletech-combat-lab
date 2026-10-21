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
| F9 | Anti-Missile System and laser AMS (was G13) | p.206 | Built 2026-10-20 (`INTEGRATION__ams`). An AMS never engaged; worse, it fired as a 2-damage range-1 weapon. Now it never fires as a weapon; it engages up to 2 missile hits a turn from inside its location's firing arc: the Cluster Hits roll at -4 (below 2: no damage), a Streak counts as a 7, a single missile (Thunderbolt) dies on 1D6 4+; 1 ammo + 1 heat (laser: 7 IS / 5 Clan, no ammo); not while shut down or with the crew unconscious. Weapon choice and movement scoring price it in. Data fix: the IS laser AMS takes 2 critical slots (p.250), equipment.json had 1. |
| F10 | Ammo bins feed their weapons | pp.72-73 | Built 2026-10-20 (`ammo.parse_bin`). Bins whose name differs from the weapon's equipment.json row never linked, so the weapon had no ammo and never fired: "IS Gauss Ammo", "IS Ammo AC/10", every "Artemis-capable" / "Narc-capable" bin, Narc pods... 1,541 of the units in `data/meks.zip` had at least one (the Atlas AS7-K's Gauss rifle never fired). Bins of munitions that aren't modeled stay unlinked on purpose: LB-X cluster, ATM ER / HE, MML modes, Arrow IV, iNarc ECM / haywire / Nemesis pods. |
| F11 | Artemis IV / V fire control (was in G10) | pp.186, 192, 197 | Built 2026-10-20 (`INTEGRATION__electronics`). Linked FCS + matching Artemis ammo: IV +2 on the Cluster Hits Table, V -1 to hit and +3; ATM built-in +2. Lost to the FCS's crit or to hostile ECM. Data fix: Artemis V takes 2 slots (p.254). |
| F12 | Narc / iNarc beacons (were never fired) | pp.188, 193 | Built 2026-10-20. A hit attaches a homing pod (location roll); from the next phase Narc-capable missiles get -1 to hit and +2 Cluster; lost with its location or to the target's ECM; explosive pods 4 / 6 damage. The bot fires the beacon for the pod's worth (Daniel's rule - Section 6), and an AMS engages a pod for half that. Data fixes: beacons do 0 damage (equipment.json had none, so they never fired); IS Narc takes 2 slots, iNarc 3 (p.250). |
| F13 | ECM (was G15) | pp.200-201, 202, 209 | Built 2026-10-20. Guardian / Clan / Angel / Watchdog: an enemy's working ECM blocks the attacker's Artemis and its Narc pods (in a duel the ECM mech is always inside its own radius); Angel also unlocks Streaks. Off when shut down or with a stealth system other than the LPS on; active stealth armor / Void-Signature also jams the mech's own Artemis. Data fix: Guardian, Angel and Watchdog take 2 slots (pp.250, 252). |
| F14 | Rapid fire: Ultra / Rotary AC, Rotary jams and unjamming (was G10) | pp.182-183 | Built 2026-10-20 (`INTEGRATION__fire_modes`). They fired as one flat hit. Now 1-2 / 1-6 shots, heat and ammo per shot, Cluster Hits on the shots column; Rotary jams and unjamming. The Core Ultra AC doesn't jam. The rate is a stub (Daniel: research). |
| F15 | Ammunition kinds: LB-X cluster, ATM ER / HE, MML LRM / SRM; Apollo FCS (was G10 / G16) | pp.186, 192, 197; tables pp.250, 252 | Built 2026-10-20. Those bins fed nothing (the weapons fired slugs / standard rounds, MMLs never). Which kind fires is a stub. Apollo saturation mode waits on Daniel (attacks on a hex). |
| F16 | Weapon slot counts | tables pp.248-254 | Fixed 2026-10-20: wrong counts made a multi-slot weapon several weapons (or merged two into one) - 1,893 units. Split weapons now one item. |
| F17 | IS machine guns | p.248 | Fixed 2026-10-20: no equipment.json row, so they were inert; their "IS Ammo MG" bins had none either. |
| F18 | Variable-damage weapons, HAG, M-pods, MG arrays, bombast lasers, rifles (was G17) | pp.184-190 | Built 2026-10-20 (`INTEGRATION__weapon_profiles`): they couldn't fire (no damage data), or rifles hit 'Mechs for full damage. |
| F19 | Heat-causing weapons put heat on the target | pp.102, 183-184, 189 | Built 2026-10-20: flamers (damage as heat; ER 1), plasma rifle 1D6, plasma cannon 2D6 (Clan flamers and plasma couldn't fire before); outside heat capped at 15 a turn. |
| F20 | Arrow IV and artillery cannons | pp.182-183 | Built 2026-10-20: area effect, hex attacks / no immobile -4, scatter, splash. Distant (18+) Arrow IV and special Arrow munitions not offered. |
| F21 | Actuator Enhancement System | p.206 | Built 2026-10-20: arm AES -1 to that arm's weapons (not split arm / torso) and physical attacks (club / push need both arms); leg AES (all legs) -2 to every PSR, -1 kicks and charges; crit rules. Was deferred ("skip special equipment"). |
| F22 | LOS on the border of two hexes | p.56 | Fixed 2026-10-20: the second hex was often missed (round-half-to-even), so its woods were ignored; along the board edge the off-board / partial hex is never used ("LOS cannot be shifted so that it passes through a partial hex") instead of crashing. The pick is the same from either end, so it holds for all attacks between the pair that turn. |
| F23 | Hardened armor | p.202 | Checked 2026-10-20: all four effects were already built (2 points per pip, -2 TAC while armor remains, +1 PSR, -1 Running MP). |
| F6 | Backward walking (was G1) | pp.45-46, 63 | Built 2026-10-20: a walking mech may step into the hex directly behind it (facing kept); a turn with a backward step never spends more than Walking MP; the hex count for TMM restarts when the mech reverses direction. The battle log marks moves that use it ("includes a backward move"). Not yet offered: backward level changes and backward charges (G11, G12). |
| F24 | Map terrain from MegaMek's map pack (Daniel's 192 16x17 maps, 2026-10-21) | pp.47-48, 53, 122, 127 | Built 2026-10-21: MegaMek "option" lines load (20 maps wouldn't); depth-0 water costs nothing (p.122; 14 maps crashed); stacked terrain adds up (p.47; was G6); jungle costs as woods; rubble +1, swamp +1, sand / mud +0 (MP only - their PSRs are G19); road travel (p.53): +0 terrain and level change -1 only road to road (pavement and roofs count), a road hex entered off the road costs its underlying terrain (was: always +0). |
| F25 | Level-change limits (was G2) | pp.46-47 | Built 2026-10-21: 2 levels a hex, 1 with a destroyed hip; charges' last step too. 74 of the 192 maps have 3+ level cliffs. |
| F26 | Jump landing height (was G3) | p.50 | Built 2026-10-21: no landing higher than start level + Jumping MP. |
| F27 | Passive buildings (Daniel's option, `config.PASSIVE_BUILDINGS`, default on) | pp.46, 50, 130, 134-135 | Built 2026-10-21: a building is a block as tall as its roof (hex level + height, p.130) - blocks LOS like a hill (p.135), can't be entered by ground movement, a jump can land on the roof (p.50), roof to roof same level or one lower, never off a roof on foot (p.134); pushes from the ground into it are blocked. Ignored before (82 maps): mechs walked and shot through buildings. The full rules (forced entry, inside, damage, collapse, support limits, pp.130-136) are a discussion with Daniel first. |
| F28 | Terrain the simulator can't play is refused when the map loads | - | 2026-10-21, `terrain_rules.prepare_board`: bridges, ultra-heavy woods and MegaMek-only terrain (fuel tanks, magma, hazardous liquid, fortified, planted fields, elevators, impassable) stop the map with a list, instead of a crash mid-battle (bridges) or being played as clear. `tests/survey_maps.py` lists which maps play. |
| F29 | Water, part 1 (was G6) | pp.47-48, 50-51, 57, 62, 66-67, 103, 115, 127 | Built 2026-10-21 (`INTEGRATION__water`): a water hex's level is its floor (surface - depth), so going in and out is a level change (p.51) and jumps / LOS / falls see the depth; partial cover standing in depth 1 (p.66; not against a fully submerged attacker); attacks can't cross the water line (p.62); the Underwater Attacks Table - from depth 1 only torso / arm / head weapons at land targets and only leg weapons at submerged ones, only energy weapons from a submerged location (pp.67, 127); underwater range one bracket longer, no long range (p.127); submerged heat sinks dissipate double, at most +6 (p.103); leg jump jets don't fire in depth 1, no jump from depth 2+ (p.50); PSR for running or jumping into depth 1+ water, a failed jump falls the depth (pp.48, 50); falls in water do half damage (p.115). The bot's movement scoring prices all of it. Simplification: the water PSR checks the END hex only (no paths kept), like the TODO for damage PSRs. |
| F30 | Water, part 2 | pp.77, 117, 127 | Built 2026-10-21 (`INTEGRATION__water`): physical attacks in water (p.77) - none at a fully submerged 'Mech from above the water (from depth 1 only a kick), none from under water at a 'Mech on land, half damage to underwater locations, no charge / DFA across the surface; hull breaches (p.127) - an underwater location that takes damage breaches on 2-4, a location with no armor left breaches when under water, a breached location's components stop working, a breached leg counts as destroyed, a side torso takes its arm; drowning (p.117) - life support crit + fully submerged in the End Phase = 1 MechWarrior hit. Movement scoring knows which physical attacks water allows (not the halved damage). Simplification: breached slots are marked destroyed, so they don't soak crits and breached ammo can't explode (Core keeps both). |
| F31 | Deployment depth and stuck terrain; water leftovers | p.37, pp.77, 127 | Built 2026-10-21 (Daniel's calls): a mech may start its movement up to `DEPLOYMENT_DEPTH` (0) hexes in from its home edge, roofs included (no level before it enters); never in a hex where it would be stuck (no path to the far side for this unit - Claude's reading: a hex within 3 of the far edge); none -> the override, `DEPLOYMENT_STUCK_DEPTH` (3) hexes in (`INTEGRATION__deployment`). The Solaris arenas (Hartford Gardens, Scrapyard) now play. Hull breaches no longer destroy slots: they still soak crits and ammo in them still explodes (`damage_resolution.mark_location_nonfunctional`). Movement and attack scoring count physical damage to underwater locations at half (`water.physical_value_factor`). |
| F32 | The movement subphase (Daniel, 2026-10-21: "There is a difference between planning where you want to go which the picker does. And actually getting there") | pp.46-48, 50-51, 110-113, 122, 124 | Built 2026-10-21. On a board where a step can force a terrain PSR (`terrain_rules.has_psr_terrain`), the movement search (`pathfinder._build_terrain_psr`) counts each path's PSRs - rubble +0, sand with a level change, water when running (one per water hex, p.113), a facing change in mud when running (-1), a backward level change (now allowed: one level, a PSR) - and keeps the path with the most hexes, then the fewest PSRs. Movement scoring prices them (`movement_selection._Side.psr_cost`). The orchestrator then walks the path (`_walk_path`, `ranged_combat.path_to`): each PSR is rolled where it happens; a failure falls there (a backward level change: the lower hex), and the mech, with the MP it has left, tries to stand and re-plans from where it lies (`_after_fall_midmove`). Jumps: landing in water or rubble rolls on landing. Flat boards without such terrain keep the old search, results identical. |
| F33 | Artillery scatter held inside the firing arc; machine gun array ammo | pp.182-183, 185 | Fixed 2026-10-21 (Daniel's known issues): a missed Arrow IV / artillery cannon lands in the last hex of its scatter path inside the launcher's firing arc (the target's own hex if the first step leaves it - full damage); an array's guns that share bins share the rounds (1 round left = 1 gun fires). |
| F34 | End-of-movement PSRs for charges and DFAs | pp.78, 80, 113 | Fixed 2026-10-21: movement-mode PSRs (running with a gyro / hip hit, jumping with leg damage) are made at the end of movement (p.113) - the end hex is right. A charging or DFA mech's movement only ends in the Physical phase, after the attack and displacement (pp.78, 80), so its movement-mode PSRs wait until then, joined by a PSR for the hex a successful charger advances into (rubble, sand, water when running) or a DFA lands in (water, rubble) - `movement_attacks.end_of_movement_triggers`. A DFA mech no longer rolls a landing PSR for the hex next to the target it hangs over. |
| F35 | No moving through a mobile enemy's hex | p.48 | Built 2026-10-21: while a mech moves, the enemy's hex is closed to its ground steps (`pathfinder.build_movement_table(blocked=...)`, set by `orchestrator._phase_movement` as `mover.blocked_hex`) unless the enemy is immobile; jumps still pass over it, and a charge still enters it. Was: only ending there was excluded. The bot's modeled reply (two-ply) doesn't apply it (the first mover's spot varies per candidate) - a small modeling gap, not a rules one. 4 reference battles moved differently (fewer reachable spots), same winners. |
| F36 | Water leftovers (was G6) | pp.67, 127 | Built 2026-10-21: hits on a 'Mech standing in depth 1 from a leg weapon in depth 1, or from any weapon of a fully submerged 'Mech, use the Kick Location Table - legs only, no partial cover modifier or leg-hit loss, no aimed shot, no Through-Armor Critical (`water.kick_table_weapon_ids`, `attack_resolution.KICK`); an energy weapon firing from under water uses the next bracket for its damage too (a Snub-Nose PPC at medium deals its long 5; `water.range_adjuster`'s `underwater_ids`, `fire_modes.Planner.damage_bracket`). |
| F37 | Armored components (was G14) - and a parser bug | p.207 | Built 2026-10-21. BUG FIXED: MegaMek's "(armored)" tag wasn't stripped, so on the 37 units that carry it an armored engine / gyro / cockpit / actuator / sensor was inert padding (crits to it did nothing) and an armored weapon (e.g. "ISERPPC (armored)") never fired. Now `mtf_parser` strips the tag and records `mech.armored_slots` (never ammunition; 209 slots in `data/meks.zip`). An attack's critical hit on an armored slot uses up that slot's armor with no other effect (`damage_resolution.resolve_critical`); MASC / supercharger crits ignore the armor (p.207); an armored shoulder / hip not yet hit stops a limb blown off and loses its armor instead. |
| F38 | Jump in place; Minimum Movement (were G5, G8) | pp.49, 50 | Built 2026-10-21 (`ranged_combat._movement_options`): a jump into the 'Mech's own hex for 1 MP, any facing, 0 hexes (+1 TMM for jumping, 3 heat); Minimum Movement - with at least 1 MP, a run into the hex straight ahead when its cost is more than the MP left, if that is the whole move and the hex isn't prohibited or a mobile enemy's (`_minimum_move`; the movement subphase walks it as one step, rolling its terrain PSRs). Not with a charge (p.78) - a minimum move leaves no MP to enter the target's hex anyway. 10 reference battles changed (jump-capable mechs), same winners. |
| F39 | Small and torso-mounted cockpits; tripod leg roll on the battle dice | pp.117, 203 | Built 2026-10-21 (`mech_state.has_small_cockpit` / `has_torso_cockpit`): +1 to every PSR for both (205 small, 34 torso-mounted units in `data/meks.zip`; was deferred, "skip special equipment for now"). Torso-mounted: no MechWarrior hit from head hits (`head_hit_hurts_pilot`), losing the head isn't fatal and later head hits are re-rolled (`hit_location.resolve_hit_location`, the Punch table too), sensor hits +4 to physical attacks (incl. charge / DFA) and PSRs once both head sensors or 3+ sensors are hit (`torso_cockpit_sensor_penalty`). The tripod leg sub-roll now uses the battle's dice (was Python's `random`, outside the seed). 5 Asymptote (tripod) reference battles changed, same winners. |
| F40 | Structure / armor slots take no critical hits - a bug | p.94 | Fixed 2026-10-21. MegaMek writes Inner Sphere filler slots as plain names ("Endo Steel", "Endo-Steel", "Ferro-Fibrous", "Light / Heavy Ferro-Fibrous", "Stealth", "Reactive", "Reflective", "IS Ballistic-Reinforced"...) that don't resolve against equipment.json, and `equipment.is_crit_target` counted any plain name as a target - so on ~1,090 units in `data/meks.zip` 7-28 filler slots soaked critical hits that belong to real components (p.94: such slots are rolled again). Now `equipment.is_structure_or_armor_slot` makes them inapplicable (Clan names already resolved to crit-ineligible entries). 3 reference battles changed (the Akuma, both Atlas / Kintaro), same winners. |
| F41 | Line of sight as the Core Rulebook has it (was D8, G7) | pp.56-58, 66 | Built 2026-10-21 (Daniel: "make sure the LOS rules match those in the rules and fix prone mechs"); `pathfinder/los.py` replaces his simplified 2026-07-19 rules. LOS level = hex level + height (standing 2, prone 1; callers pass `attack_resolution.los_height`, the movement-scoring cache keys on both heights). Terrain between the mechs intervenes if its level is >= both LOS levels or >= the adjacent mech's; an intervening hill / building blocks; intervening woods AND jungle (was woods only) add 1 / 2 points, 3+ block. Partial cover: a standing target next to a hex exactly one level higher on the line, not if the attacker's LOS level is higher; none for a prone target (that hex hides it); depth-1 water as before. A line on a hex border runs along ONE side, the target's pick, for the whole line (was: the worse hex at each step, which could mix both sides). `tests/test_los.py` rebuilds the rulebook's examples (Intervening Terrain Diagram p.58, the Rakshasa p.59, partial cover p.66). 8 reference battles changed; Large Lakes 1 is now a 50-turn draw (the Cataphract hides under water - the anti-stall item), the rest keep their winners. Not modeled: firing at a hex (p.58's adjacent-hex rule). |
| F42 | PSR special cases by the book | pp.51, 111, 236-239 | Built 2026-10-21 (Daniel: "Stand up, tripod, jumping, 4 legged mechs should all have answers in the rules"): each stand attempt -1; a leg destroyed before the round +4 (was +5; "jumped with leg destroyed" is that same +4, note 13); a tripod -1 with no leg destroyed (was -2) and its dedicated pilot -1 to PSRs and physical attacks, +2 when the pilot is disabled (was +3), +2 to ranged attacks when its gunnery officer is disabled; a quad -2 only with no leg destroyed (was always), +1 per lost leg for its first two (+4 from the third), no PSR to stand with all four legs, one lost leg forces no run / jump PSR, two count as a hip hit (one PSR). Not changed: Daniel's quad leg-loss MP / destruction rule (PROJECT_MAP Section 4 question). |
| F43 | Four-legged 'Mechs' leg damage by the book | pp.238-239 | Built 2026-10-21 (Daniel: "Follow the rules, not my calls" - replaces his 2026-07-12 "one fewer lost leg" rule): each of the first two lost legs -1 Walking MP and +1 PSR, two lost legs also a hip hit's effects (one level per hex, a PSR when running); three lost = a biped with one leg lost (Walking MP 1, +4, still mobile, can stand); four = immobile; the first hip hit on a quad has none of the standard effects (no MP, PSR modifier, PSR trigger or level limit), each later one does (`mech_state.hip_effects`, `ground_level_limited`). Not built: quad kicks by arc (front / mule kick, p.238) - a quad still kicks like a biped. |
| F44 | Heavy-duty gyro (was G23) | p.204 | Built 2026-10-21: the .mtf "Gyro:" line is read (`mech.gyro_type`); a heavy-duty gyro is destroyed only by its 4th hit (`mech_state.gyro_destroyed`), each hit is +1 to PSRs (not +2), its hits force no PSR (when taken, or when running), and a jump with any hits is a PSR at +2 in place of the +1s (`piloting_rolls.hd_gyro_jump_adjust`). 57 units. |
| F45 | Heat-dissipating armor (was G26) | p.202 | Built 2026-10-21 (`attack_resolution._heat_armor_damage`, `has_heat_dissipating_armor`): a heat-causing weapon's (flamers, plasma) damage to a location with it is halved, rounding up; a 'Mech with any of it takes no outside heat from those weapons. (Fire hexes / magma: no such terrain yet.) 5 units. |

---

## Gaps — Claude's to build (rough priority)

| # | Rule | Page | Notes |
|---|---|---|---|
| G1 | ~~Backward walking~~ | p.46 | Built 2026-10-20 - see F6. |
| G2 | ~~Level-change limits~~ | pp.46-47 | Built 2026-10-21 - see F25. |
| G3 | ~~Jump landing height~~ | p.50 | Built 2026-10-21 - see F26. |
| G4 | ~~No moving through the enemy's hex~~ | p.48 | Built 2026-10-21 - see F35. |
| G5 | ~~Jump into your own hex (1 MP)~~ | p.50 | Built 2026-10-21 - see F38. |
| G6 | ~~Water, what's left~~ | pp.67, 113, 127 | Built 2026-10-21 - see F36 (the run-through-water PSRs: F32). |
| G19 | ~~Terrain PSRs on entering a hex~~ | pp.48, 122, 124 | Built 2026-10-21 - see F32. |
| G20 | ~~Movement as a path~~ | pp.46-48, 51, 110-113, 122, 124 | Built 2026-10-21 - see F32. Left: mud's -1 isn't priced in scoring (bot). Done 2026-10-21 (F34): the damage PSRs (gyro / hip / leg) falling in the END hex is the rule (p.113: movement-mode PSRs are made at the end of movement); a charger / DFA now rolls them, and the PSR for the hex it enters / lands in, in the Physical phase (pp.78, 80). |
| G21 | Movement scoring ignores hull-breach risk | p.127 | Daniel asked (2026-10-21); DON'T BUILD YET - notes in PROJECT_MAP Section 6 Memo (tied to his cluster-weapon / risky-equipment costing idea). A spot in water is scored for its benefits (heat sinks, partial cover, the water line) and its falls (halved), but not for P(breach) = 1/6 per damaged underwater location (2-4 on 2D6), automatic breaches of armorless locations, or a breach's cost (breached leg = destroyed; torso engine / gyro slots). Deferred (Daniel). |
| G22 | Full building rules (and bridges) | pp.53, 130-136 | Deferred to a later session (Daniel, 2026-10-21); `PASSIVE_BUILDINGS` meanwhile. |
| G7 | ~~Prone mechs are 1 level high for LOS~~ | p.57 | Built 2026-10-21 - see F41. |
| G8 | ~~Minimum Movement~~ | p.49 | Built 2026-10-21 - see F38. |
| G9 | Expected damage ignores leg hits lost to partial cover | p.66 | Movement scoring and weapon choice still count them. LATENT. |
| G10 | ~~Ultra / Rotary rate of fire and jams, LB-X cluster ammo~~ | pp.183-186 | Built 2026-10-20 - F11, F14, F15. |
| G16 | Special munitions left (deferred, Daniel 2026-10-20): AC armor-piercing / caseless / flak / precision rounds, iNarc ECM / haywire / Nemesis pods, Arrow IV homing / inferno / smoke / thunder | pp.190-194 | AC special rounds fire as standard; no unit in `data/meks.zip` carries those rounds or pods. (Apollo saturation built 2026-10-20.) |
| G17 | ~~Variable-damage weapons~~ | pp.184-185 | Built 2026-10-20 - F18. |
| G18 | Bombast laser charging, PPC capacitors, HAG flak mode, distant Arrow IV fire | pp.182, 184-185, 188 | Choices not offered yet (capacitor: not modeled at all). |
| G11 | ~~Backward level change~~ | pp.46-47, 115 | Built 2026-10-21 - see F32 (on boards with any level change: one level, a PSR, not with a destroyed hip, not on a roof; a failure falls in the lower hex). |
| G13 | ~~Anti-Missile System (AMS / laser AMS)~~ | p.206 | Built 2026-10-20 - see F9. 223 of the units that parse carry one. |
| G14 | ~~Armored components~~ | p.207 | Built 2026-10-21 - see F37. |
| G15 | ~~ECM~~ | p.200 | Built 2026-10-20 - see F13. |
| G12 | Charging after a backward step | p.78 | The charge planner uses forward-only paths (the hex count restarts after a backward step and the planner adds the final forward step). Small. |
| G23 | ~~Heavy-duty gyro~~ | p.204 | Built 2026-10-21 - see F44. |
| G24 | Shields, spikes, talons on a DFA, lance in a charge, vibroblade activation | pp.194-196 | Not built (~15 / 12 / 10 / 15 / 9+ units). Shields: raising one, damage taken by it, shield bash. Spikes: -4 physical damage to the location, 2 back to the attacker, +2 a cluster in a charge. Talons: DFA damage x1.5 (kicks already have it). Lance: its charge effects. Vibroblades: activation and heat (today treated as switched off). |
| G25 | Advanced Point Defense System (APDS) | p.206 | Not built - can't fire today (4 units). |
| G26 | ~~Heat-dissipating armor~~ | p.202 | Built 2026-10-21 - see F45. |
| G27 | Blue Shield particle field damper | pp.180, 207 | Not built (4 units): halves PPC damage while active, Escalating Failure after 6 turns, negates stealth, a 5-point explosion if hit while active. |
| G28 | HarJel I / II / III | p.208 | Not built (19 units): HarJel stops breach checks while armor remains (a hit to it breaches the location); II / III repair armor. |
| G29 | Torpedo launchers (LRT / SRT) | p.187 | Not even parsed ("CLLRT15" is an unrecognized component - 27 units): fire only from and to water through water hexes. |
| G30 | Cockpit command console | p.203 | Not built (35 units): a second MechWarrior who can take over as pilot, no ammo-explosion hits for whichever warrior is secondary. |
| G31 | ~~Chemical lasers' ammunition~~ | p.185 | Checked 2026-10-21: they already draw on their bins (30 shots a ton for the medium), run out and explode like any ammo - nothing to fix. |
| G32 | Quad kicks: front kick with front hips only, mule kick | p.238 | Not built - a quad kicks like a biped (from F43). |
| G33 | PPC capacitors | p.188 | Not built (~65 units) - its own bot session (Daniel, 2026-10-21; PROJECT_MAP Pick up here 8). |

No effect in a two-'Mech duel (left out on purpose): C3 / C3i networks (need
team-mates, p.198), active probes and the Watchdog's probe (only hidden units,
p.197), TAG (only designates for homing / semi-guided ammo, p.199). Not Core
Rulebook equipment (can't fire / no effect): TSEMP, mech mortars, iATM, fluid
guns, full-size Thumper / Sniper artillery, nail / rivet guns, vehicular
grenade launchers, industrial tools (chainsaws, drills, hoists...), UMU,
modular armor (survey of `data/meks.zip`, 2026-10-21).

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
| D8 | LOS model | Woods count as intervening if their top (hex + 2) reaches both mechs' LOS levels, or the adjacent mech's; partial cover is lost if the attacker is higher than the target, and a prone mech gets none (pp.57-58, 66) | **Decided 2026-10-21 (Daniel): rules as written** ("make sure the LOS rules match those in the rules and fix prone mechs") - built, F41. | |
| — | Stand-up, tripod, leg destroyed, quads standing (were open in PROJECT_MAP Section 4) | Stand -1; tripod -1; leg destroyed +4; quads stand without a PSR | **Decided 2026-10-21 (Daniel): rules as written** - built, F42. | |

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
