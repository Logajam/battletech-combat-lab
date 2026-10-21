# Mech-vs-Mech Integration — Project Map

Single source of truth. Replaces `INTEGRATION__PROJECT_MAP.md` (old),
`MECHSIM____BattleTech_Sim___Project_Map.md`, `PATHFINDER__PROJECT_MAP_movement.md`,
and both projects' `DESIGN_NOTES*`/`CALL_GRAPH*`/`CHANGE_RECORD_ARCHIVE*` files.
Those are superseded — don't consult them. History before 2026-08-28 is
archived, not carried forward here; this doc tracks current state and
open items only.

**Naming:** `MECHSIM__*` / `PATHFINDER__*` = source-project files, kept as
reference. `INTEGRATION__*` = new orchestrator files. Never let one
source project's file overwrite the other's same-named file.

---

## 0. WHERE WE ARE (2026-10-21, end of session 4) — read this first

**Session 4 in one paragraph (all merged to `main`, PRs #18-#31):** one-command
checks (`tests/run_checks.py`); default matchup Kontio vs Hammerhead (the
starter set's example battle); Actuator Enhancement System (p.206); battle
REPLAYS (shareable HTML pages); LOS on the border of two hexes fixed (p.56 -
the second hex was often missed, and the board edge crashed); the two-ply
models MASC / supercharger speed; a new movement objective, Daniel's
"lifetime" with a history blend, A/B-tested and made the DEFAULT; a time
tracker on every batch; reference battles capped at 50 turns. Details and
A/B numbers: Change Record (Section 8), Daniel's calls: Section 5.

**Maps (2026-10-21, the parallel maps instance - merged after PR #31):**
Daniel's MegaMek map pack is `data/maps.zip` (346 maps, 192 of them 16x17);
`python tests/survey_maps.py` says which play and what stops the rest.
165 of the 192 16x17 maps play (31 did before - the rest crashed, didn't
load, or had buildings / cliffs silently ignored). Built: costs and stacking,
road travel, level-change limits, jump landing height, PASSIVE buildings
(`config.PASSIVE_BUILDINGS`), and a load-time refusal of terrain not built
yet. Water part 1 (F29, `INTEGRATION__water`): depth as level, partial
cover, the water line, underwater weapons / ranges, heat sinks, jump jets,
water PSRs, halved falls. Water part 2 (F30): physical attacks in water,
hull breaches, drowning. Deployment (F31, `INTEGRATION__deployment`):
start up to `DEPLOYMENT_DEPTH` hexes in, roofs allowed, never stuck - the
override goes 3 in (the Solaris arenas play now). The movement subphase
(F32): the picker plans, the mech walks the path rolling each terrain PSR
where it happens (water when running, rubble, sand, mud, backward level
changes), and re-plans after a fall. The full building rules are deferred
to a later session (Daniel, 2026-10-21). Details: RULES_REVIEW F24-F28, G6, G19; Section 4
"Map terrain waiting on rules".

**Hand-off for a new instance.** Daniel's goal: "beat the simulator into
shape." He is not a GitHub person - **Claude runs the logistics** (Daniel,
2026-10-20: "You're in charge of the logistics"): work on the session's
`claude/...` branch, commit, push, open a PR to `main`, and merge it once the
tests pass (no CI is configured - the local tests are the gate); tell Daniel
in plain words what changed. If the branch's last PR is already merged,
restart the branch from `origin/main` before new work. **Show Daniel battles
as replays** (`config.REPLAY_BATTLES`, publish the page from `replays/` with
the Artifact tool, give him the link) - he doesn't run the code himself.
Section 7 has the standing instructions; Section 5 Daniel's decisions; the
Change Record (Section 8, newest first) every change with page cites.
**Daniel expects Claude to keep working without pausing** at natural
checkpoints - stop only for his calls (rules / scope).

**Session setup (cloud container):** `pip install -r requirements.txt`;
unzip `rules/Battletech_Rule_Reference_Index.zip` OUTSIDE the repo (e.g.
`/home/user/rules_lib/`) - Core Rulebook in `base/core-rules/*.md` (a `[p.N]`
marker PRECEDES page N's text), condensed and page-cited in
`summary/core-rules/*.yaml` (fast to read); unzip `data/meks.zip` outside the
repo when wider unit testing is needed. Then confirm a clean baseline:
`python tests/run_checks.py --bench` (about 3.5 min).

**It runs end to end.** `.mtf` in → turn-by-turn battle on a real board →
batch summary (+ "WHERE THE TIME WENT" table) out: `python INTEGRATION__main.py`.
Settings (mech files, board, seed, batch size, worker count, OPTIONAL RULES,
movement objective, replays, timing - every knob) are in
`INTEGRATION__config.py`. Default (Daniel, 2026-10-20): Kontio (Red, 40 t:
TSM, claws, stealth armor + ECM, supercharger, lasers) vs Hammerhead (Blue,
45 t: hardened armor, leg AES, large pulse, Streak SRM 6), the starter set's
example battle, on 16x17 Grassland (flat, level 0, 30 woods hexes), seed
12345, 1 battle, verbose, home-edge deployment. Layout: `INTEGRATION__*.py`
at the top; `mechsim/` and `pathfinder/` hold the source-project modules;
`data/` the boards, test mechs and `meks.zip` (4,227 MegaMek units, 4,162
parse); `rules/` the rules library zip; `reference_logs/` same-seed sample
battles; `replays/` and `run_stats/` (git-ignored) generated output.

**After any change, from the repo root:** `python tests/run_checks.py` -
one command, about 3 min: every `tests/test_*.py` (14 files) and every
reference battle (13), side by side, one line each, all must pass. Reference
battles stop at 50 turns (`check_reference_logs.TEST_BATTLE_MAX_TURNS`,
Daniel); one that hits the cap prints a NOTE ("a possible flaw") - today
only the Asymptote mirror (the stall, Pick up here 0). A reference log may
differ only when the change is MEANT to alter results - then look at a fresh
battle, run `python tests/check_reference_logs.py --update`, and say so in
the Change Record (Daniel has OK'd regenerating them for intended changes).
For anything on the hot path add `--bench` (10 turns of the Asymptote mirror,
pinned so timings stay comparable - a pure speed change must keep its HP
totals, currently 501 / 495 since the 2026-10-21 lifetime default; ~15 s in
the cloud container; it prints where the time went). Bot changes: compare
with `python tests/ab_batches.py` (same seeds, several settings side by side).

**What's built (all Core Rulebook, page-cited in the code):**
- Batches: `config.WORKERS` battles at once, one per CPU core (0 = all
  cores); each battle has its own seed (`orchestrator.battle_seed`, battle 1
  = SEED) and the output is identical for any worker count
  (`tests/test_parallel_batch.py`). `BattleResult.seed` replays a battle.
- Movement: `INTEGRATION__movement_selection.choose` scores every reachable
  spot, exposure- and structure-weighted, TWO-PLY for the first mover (the
  modeled reply now moves at its MASC / supercharger speed). DEFAULT objective
  since 2026-10-21 (Daniel): "lifetime" = dealt now + (HP left / enemy future
  damage per turn) x my future damage per turn (`INTEGRATION__future_damage`:
  0.5 x best heat-limited expected damage at gunnery + walking + the target's
  best TMM), each future rate blended with the battle's real record,
  (K x estimate + damage really done) / (K + turns fought), K = 3. "ratio" =
  dealt / (received + PSR cost + .001) is still a setting
  (`config.MOVEMENT_OBJECTIVE`). Closing fallback when nothing deals damage.
  Backward walking (pp.45-46; same-level steps only). Speed:
  `ranged_combat.MoveEvaluator` memos are shared by arc class and by
  blocked-weapon set.
- Arcs and arc actions (`INTEGRATION__arcs`, Section 4a).
- Ranged combat: heat-limited weapon choice, to-hit modifiers incl. the
  target-in-woods +1 / +2 (p.66, in `pathfinder/los.py`'s result), attack
  direction, cluster groupings, ammo, rear-mounted weapons, aimed shots,
  partial cover (leg hits strike the cover). Ranged fire and the following
  physical attack are planned together.
- Physical: all seven attack types (punch, kick, physical weapons, clubs -
  pick-up OFF, pushes, charges, DFA), each weighted by its own hit table.
- Damage: floating or standard TACs (option), autocannons survive their
  first crit (p.183), internal explosions with the 20 cap, armor loss and
  CASE / CASE II venting (p.96).
- Anti-Missile Systems, standard and laser (p.206, `INTEGRATION__ams`,
  2026-10-20): engage up to 2 missile hits a turn each from inside their
  arc (Cluster roll -4, Streak as a 7, single missile 1D6 4+), with ammo
  and heat; never fire as weapons; priced into weapon choice and movement
  scoring.
- Artemis IV / V, Narc / iNarc beacons and ECM (`INTEGRATION__electronics`,
  2026-10-20): Cluster / to-hit bonuses, pods, ECM blocking, Angel vs
  Streaks; the bot picks the munition per shot and fires a beacon for the
  pod's worth. Ammo bins now feed their weapons whatever MegaMek calls them
  (Gauss, AC/10, Artemis- / Narc-capable... - many never fired before).
- Actuator Enhancement System (p.206, `mech_state.arm_aes_working` /
  `leg_aes_working`, 2026-10-20): arm AES -1 to that arm's weapons (not
  arm / torso split ones) and physical attacks (club / push only with both
  arms); leg AES (all legs) -2 to every PSR and -1 to kicks and charges; a crit
  to any leg AES slot loses the leg effects, to an arm's only that arm's.
- Battle replays (`INTEGRATION__replay`, 2026-10-20): `config.REPLAY_BATTLES`
  = N saves battles 1-N of a run as self-contained HTML pages in
  `config.REPLAY_DIR` (`replays/`, git-ignored): hex map stepped through
  deployment / each movement / ranged / physical / heat-and-end, both record
  sheets (armor, rear, structure per location with this step's damage), heat,
  status, and each step's log. Recording changes nothing in the battle
  (`tests/test_replay.py`). **Share battles with Daniel this way**: publish
  the page with the Artifact tool and give him the link (he doesn't run
  the code himself).
- Time tracker (`INTEGRATION__timing`, 2026-10-21): every batch ends with a
  "WHERE THE TIME WENT" table (`config.TIMING`); `config.PROFILE_FUNCTIONS`
  adds a per-function profile. The benchmark prints it too.
- Map terrain (2026-10-21, `pathfinder/terrain_rules.py`): Movement Costs
  Table (p.48) with stacking (p.47), road travel (p.53), at most 2 levels a
  step (1 with a destroyed hip, pp.46-47), jump landing height (p.50),
  passive buildings (option `PASSIVE_BUILDINGS`, default on: block LOS,
  can't be walked into, jump onto the roof, roof-to-roof moves, p.134);
  `terrain_rules.prepare_board` refuses terrain not built yet when the map
  loads. Water (`INTEGRATION__water`, part 1): a water hex's level is its
  floor; partial cover in depth 1; the water line; which weapons fire from /
  at water and underwater ranges; submerged heat sinks; jump jets; PSRs for
  running / jumping in; halved falls - priced in movement scoring too.
  Part 2: physical attacks in water, hull breaches, drowning.
- Heat (pp.102-107) and heat equipment; piloting rolls one per trigger
  (p.110); seatbelt checks (p.117); falls with the 1D6 side roll (p.115) and
  multiple levels; displacement; deployment from home edges.
- OPTIONAL RULES (config, Daniel 2026-10-20): `FLOATING_CRITICALS` (default
  True), `FIGHT_TO_THE_DEATH` (default False = a mech immobile for good -
  destroyed gyro / both legs - is destroyed; True = rules as written).
- Weapon-use options (`INTEGRATION__fire_modes`, 2026-10-20): Ultra / Rotary
  AC rapid fire (Rotary jams and unjamming), LB-X slug / cluster rounds, ATM
  standard / ER / HE, MML LRM / SRM, Apollo standard-fire mode - the rules are
  built, the CHOICE is a stub (Daniel: "still a matter of research");
  Apollo saturation mode (an attack on the hex, Daniel's ruling).
- Every Core weapon fires (`INTEGRATION__weapon_profiles`, 2026-10-20):
  variable damage (heavy Gauss, Snub-Nose PPC, VSP), HAG, M-pods, machine
  gun arrays, bombast lasers, rifles, flamer / plasma heat on the target
  (outside heat, max 15), Arrow IV and artillery cannons (area effect,
  scatter). Optional rule `POOL_CLUSTER_DAMAGE` (default True, Daniel):
  cluster damage of one grouping size is summed before grouping.
- Remaining loud stubs (`INTEGRATION__stubs.py`): weapon data gaps
  (`ammo_data`, `unconfirmed_weapon_data`, `unknown_damage_type`),
  `heat_explosion_bin` (a controller choice), and the weapon-use decisions
  (`munition_choice`, `rate_of_fire`, `unjam`, `escalating_use` - MASC /
  supercharger / radical heat sinks).

**Rules review:** `INTEGRATION__RULES_REVIEW.md` - first pass over the whole
Core Rulebook done 2026-10-20: what was fixed (F1-F23), the gap list (G2-G18,
Claude's to build), and the Core-vs-project questions (D1-D7 decided, D8
open). Read it before building rules.

**Pick up here (open, roughly in priority order):**
0. **Anti-stall rule for the bot** (Daniel, 2026-10-21: "Anti-stall rule for
   the bot is added to the future tasks list"). Under the lifetime default,
   mirror matches stall: the Asymptote mirror ran 488 turns (shots in only 55),
   because with equal future damage each side fights only when a trade beats
   1:1. Design it with Daniel (ideas so far: force an attack after N turns
   without firing); test with `tests/ab_batches.py` and replays. Reference
   battles are capped at 50 turns meanwhile, and every batch summary flags
   battles that hit the turn cap.
1. **Speed** (Daniel: "We still need more speed"). The time tracker says the
   two-ply look-ahead is ~95% of run time: reply scoring (`MoveEvaluator.evaluate`
   for each modeled reply) ~70%, the per-reply candidate loop in
   `movement_selection._modeled_reply` ~21%, reply charges / DFA ~4%; ranged,
   physical, heat and End Phase together under 0.2%. A speed-only change must
   keep the benchmark's 501 / 495 and every reference log.
2. **Known issues Daniel asked to fix later** (Section 4, "Known issues to
   fix later"): Arrow IV / artillery scatter must stay inside the firing arc;
   machine gun array ammo per gun needs a check / test.
3. **Research: how the bot should decide** rate of fire, MASC use and which
   ammunition (Daniel, 2026-10-20) - today stubs (`STUB_MUNITION_POLICY`,
   `STUB_RATE_OF_FIRE`, `STUB_UNJAM`, `STUB_ESCALATING_USE`); goes with the
   future-capability Memo (item 4). Daniel's ideas: (a) a lookup table of
   known best solutions per weapon by range and starting to-hit number;
   (b) raise a cluster weapon's expected value by its odds of a critical hit
   given the target's armor. Deferred: specialty ammo. Placeholder to set:
   `TARGET_HEAT_WORTH`. Questions for Daniel: Section 4.
4. **The bot's future-capability planning** - Section 6 "Memo" (Daniel,
   2026-10-20). Needed for clubs, MASC, Rotary ACs (jam risk) and similar.
5. **Crippled / forced withdrawal** (Daniel, 2026-10-20): an option plus a
   bot movement-picker override - not started.
6. Attack-caused PSRs (kick, club, push, charge, DFA, 20+ damage) aren't
   priced in movement scoring - Daniel's rule so far is "only Movement-phase
   PSRs count". A bot target choosing the clearer hex on a two-hex LOS line
   (p.56) isn't modeled (Section 6).
7. **Maps** (see above): leftovers - water (G6), the subphase's (G20: damage
   PSRs in the END hex, charge's last step, mud's -1 in scoring), and
   **pricing hull-breach risk in movement scoring** (Daniel, 2026-10-21: "How
   does the bot price the chance of a breach if it falls or takes damage in
   water?" - today it doesn't: falls and incoming fire in water are priced
   as on land (falls halved); the 2-4 breach chance per damaged underwater
   location, the automatic breach of an armorless one, and what a breach
   costs (a leg = destroyed, a torso's engine / gyro slots) are not counted,
   while water's benefits - sink bonus, cover, the water line - are);
   **deferred to a later session (Daniel, 2026-10-21): the full building
   rules** (forced entry, inside, damage, collapse, bridges, pp.53, 130-136 -
   a discussion first; passive buildings stand in until then); terrain PSRs
   mid-move (G19 rubble / sand / mud, G11 backward level changes) and in a
   spot's cost; prone LOS height (G7); Section 4 "Map terrain waiting on
   rules" (Daniel is hunting the rules); `PROMPT_FOR_MAP` / `STITCH_MAPS`.
8. Waiting on Daniel (Section 4): stand-up PSR -1, tripod -1, jumped with leg
   destroyed +4 (MECHSIM: +5), quads standing; D8 (LOS model); does HOLDING a
   club stop arm / torso weapons firing?
9. Later (Daniel agreed 2026-10-20): a setup shell GUI (the replay viewer
   exists); a compiled hot path (Cython / Rust for `MoveEvaluator.evaluate`)
   once the rules settle - not a rewrite; evolutionary tuning of the bot's
   settings with batches (discussed 2026-10-20, not started).

**Housekeeping:** reference logs regenerated 2026-10-21 (lifetime default,
50-turn cap) and match the code. Speed history (10-turn benchmark): 31.7 s →
11.8 s → ~14.5 s (all physical attacks) → ~25% less (memo sharing) → ~15 s
today; battles changed in between, so compare only like with like.

---

## 1. SCOPE

Two fully-specified mechs (parsed `.mtf` + pilot skills) + one map →
repeated simulated battles, full turn-by-turn movement/positioning/LOS/
to-hit/per-location damage-crit-PSR resolution, until destruction or
turn-limit → reset, repeat, aggregate stats (win rate, survivor
condition, attacks-to-kill, cause-of-death).

Neither source project alone does this: PATHFINDER has real positioning/
to-hit but a flat-float placeholder HP pool; MECHSIM has real per-location
damage/crit/PSR but only fires an abstract table at one static mech (no
opponent, no positioning, no to-hit). **As of 2026-10-18 the integration
does both, with stubs where rules are missing.**

---

## 2. TURN STRUCTURE (Daniel, 2026-07-25 — build target)

1. Pick map, pick mechs.
2. **Initiative** — roll; loser acts first this turn.
3. **Movement** — turn 1: loser enters from their edge, winner from
   opposite edge; turn 2+: continue from position. Loser moves first both
   cases.
4. **Ranged Combat** — loser fires first, winner second; effects resolve
   simultaneously.
5. **Physical Combat** — if eligible. *(deferred — see Section 4)*
6. **Heat** — heat effects applied (Core Rulebook pp.102-107, 2026-10-19).
7. **End Phase** — cleanup. *(scoped to unconscious-pilot recovery roll only
   — see Section 4)*

| Phase | Where | Status (2026-10-18) |
|---|---|---|
| Deployment | `orchestrator._deploy_home_edges()` | **REAL (Core p.37):** deployment roll, loser picks a home edge (`config.HOME_EDGE_CHOICE`), winner opposite; mechs enter along it on turn 1. `config.DEPLOYMENT = "fixed_hexes"` keeps fixed starts. |
| Initiative | `orchestrator.roll_initiative()` | **REAL**, Daniel-confirmed 2026-08-31. |
| Movement | `orchestrator._phase_movement()` | **REAL:** damage- and heat-aware MP (TSM, MASC/supercharger), immobile (shut down / unconscious) skip, full Walk/Run/Jump envelope with expected dealt/received per spot (`INTEGRATION__ranged_combat.evaluate_going_second`), unconscious-skip, stand-up (`resolve_stand_up`) then move on with the remaining MP (p.51), movement PSR for Run 1+ hex / Jump (`check_movement_psr`; none for Walk, p.111), consciousness checks. The pick: `INTEGRATION__movement_selection.choose`. |
| Ranged Combat | `INTEGRATION__attack_resolution.py` | **REAL:** LOS, rear arc (only rear-mounted weapons fire into it), TN = gunnery + AMM + TMM(actual hexes moved; -4 if immobile) + LOS + range + heat + weapon / targeting computer / arm-crit / sensor / prone modifiers, shut-down mechs don't fire, heat- and ammo-constrained weapon selection, real to-hit rolls, attack direction from geometry, cluster table with Core groupings (Streak, MRM), hit location, damage, crits, explosions, floating TAC, head hits, aimed shots, ammo use, Attack Phase PSR, consciousness. Both sides declare before damage lands (simultaneous). **STUBS:** `unknown_damage_type`, `unconfirmed_weapon_data`, `ammo_data`. |
| Physical Combat | `INTEGRATION__physical.run_physical_phase()` | **REAL (Core pp.76-83):** all seven attack types - punches, kicks, physical weapons, clubs (`INTEGRATION__clubs`), pushes, charges and death from above (`INTEGRATION__charge` / `INTEGRATION__dfa`, declared in Movement via `INTEGRATION__movement_attacks`); bot picks the most expected damage, weighted by hit table. |
| Heat | `orchestrator._phase_heat()` → `INTEGRATION__heat.resolve_heat_phase()` | **REAL (2026-10-19, Core Rulebook pp.102-107):** heat carries over; += movement heat (Walk 1 / Run 2 / Jump, Improved JJ, XXL, super-cooled myomer) + weapon heat + engine-hit heat (5/10) + stealth heat − dissipation (+3 Partial Wing, radical heat sinks, coolant pods); then shutdown roll or restart, ammo and inferno explosion rolls (re-rolled after inferno heat), life-support pilot hits, and next turn's MP / to-hit / TSM effects. End Phase: heat sinks switched off to hold min_heat. **STUB:** `heat_explosion_bin` (bin tie-break needs shot counts). |
| End | `orchestrator._phase_end()` | **REAL:** wake-up rolls, crippled tracking, destruction check. |

Resolved 2026-10-18 (Daniel): TMM uses **actual hexes moved**
(`combat.fc_to_tmm`), not MECHSIM's max-available-MP `compute_tmm()`.

Open question, not decided: does "winner sees loser's result before their
own fire resolves" matter for a headless batch sim with no bot reading it
mid-phase? (Current build: no — both declare first, then both resolve.)

---

## 3. FOUR-PILE FRAMEWORK

1. **When in the turn** (turn-flow control)
2. **Who am I** (mech state)
3. **Where am I** (map/LOS/movement)
4. **What am I doing** (bot decisions — cross-cutting, not a module; see Section 6)

| Pile | Files |
|---|---|
| 1 | `INTEGRATION__orchestrator.py`, `INTEGRATION__results.py`, `INTEGRATION__stubs.py` (registry). Reference only, not imported: `PATHFINDER__combat_turn.py`, `MECHSIM__sim_runner.py` (see Section 5). |
| 2 | `INTEGRATION__heat.py`, `MECHSIM__mech_state.py`, `damage_resolution.py`, `armor_rules.py`, `piloting_rolls.py`, `hit_location.py`, `mtf_parser.py`, `equipment.py`/`.json`, `INTEGRATION__config.py`, `INTEGRATION__attack_resolution.py` (resolution half) |
| 3 | `PATHFINDER__hex_geometry.py`, `board_parser.py`, `terrain_rules.py`, `pathfinder.py`, `los.py`, `combat.py` (movement/rear-arc/TMM pieces) |
| 4 | Scattered — see Section 6, not a file |

---

## 4. OPEN ITEMS

**Movement-selection follow-ups (Daniel, 2026-10-19):**
- Terrain that forces a piloting roll on entry, and mine fields: add expected
  damage to the spot's cost (denominator), as the movement PSR already does.
- (Built 2026-10-19: internal-structure weighting, see Change Record.) Still
  open there: aimed shots at immobile targets, and using the same weighting in
  the real Ranged Combat weapon choice (movement scoring only for now).

**Stubs (all in `INTEGRATION__stubs.py`, knobs in `INTEGRATION__config.py` STUB SETTINGS).**
Each docstring carries a TODO naming what to check (MegaMek names in those
TODOs are from memory — grep before relying on them).

| Stub | What it does instead | Needs |
|---|---|---|
| `unknown_damage_type` | null damage_type → BALLISTIC | equipment.json curation (weapons not in the Core tables) |
| `unconfirmed_weapon_data` | Loud warning; weapon never fires | equipment.json curation - special-rules weapons (MG arrays, TAG, SRTs, HAG damage, MML modes, plasma, VSP damage...) |
| `ammo_data` | Unlimited ammo for a weapon with no shots_per_ton (HVAC, Improved AC - not in the Core tables) | shots_per_ton from Tactical Operations tables |
| `heat_explosion_bin` | Heat ammo explosion: bins still tied on damage value AND shots left picked at random; unknown-damage bins count as 0 | A controller policy (pile 4) |
| `munition_choice` | Which ammunition kind / guidance / Apollo mode fires: `STUB_MUNITION_POLICY` "greedy" (most expected damage this shot; ties keep standard) / "standard" / "random" | Research (Daniel 2026-10-20) |
| `rate_of_fire` | Ultra / Rotary AC shots: `STUB_RATE_OF_FIRE` "max" / "single" / "greedy" (jam risk not priced) | Research |
| `unjam` | Try to unjam a jammed Rotary AC (stand still / walk only): `STUB_UNJAM` True unless prone | Research |
| `escalating_use` | MASC / supercharger / radical heat sinks used this turn: `STUB_ESCALATING_USE` "cycle" (Daniel's 1-on / 1-off) / "always" / "never" | Research |

Replaced by Core Rulebook rules 2026-10-19 (Change Record): `attack_direction`
(p.73), `cluster_grouping` (pp.87, 181), `post_standup_movement` (p.51),
`walk_movement_psr` (p.111), `to_hit_modifiers_not_applied` (pp.66-67, 97-98,
184-200), `rear_mounted_weapons` (p.60), `ammo` / `one_shot` (pp.72-73, 95,
180-182), `deployment` (p.37), `physical_combat` (pp.76-83, partly).

**Rules gaps with no runtime flag** (also printed in every summary):
shoulder / head turrets (not Core) and the twist / flip a TAG designation
uses up (TAG doesn't fire yet) - Section 4a; LB-X/Ultra/Rotary multi-shot math;
Artemis/HAG/ammo variants; heat sources with no terrain model yet (water,
snow, fire, extreme temperatures) and inferno missiles (bins aren't fired
from); heat decisions (cooldown, voluntary shutdown); stealth armor /
Void-Signature hostile-ECM side effects; torso-mounted cockpit PSR/sensor
rules; domino effects (no third mech); jumping onto the board at deployment;
tripod leg sub-roll uses Python `random` (seeded from SEED, not the
BattleRNG stream).

**Core Rulebook vs existing MECHSIM rules - Daniel to decide** (found
2026-10-19 while replacing stubs; MECHSIM left unchanged because these are
confirmed project rules, not stubs):
- (Decided 2026-10-20, see Section 5: multiple PSRs one per trigger, the
  seatbelt check, fall side, Floating Criticals and fight-to-the-death are
  settled.)
- Standing up (p.51, PSR table p.111): each attempt is a PSR at -1;
  `resolve_stand_up` uses no -1.
- Tripod with no leg destroyed: -1 to PSRs (p.111); MECHSIM uses -2.
- Preexisting leg destroyed: +4 (p.111, "jumped with leg destroyed +4");
  MECHSIM uses +5.
- Quads only need a PSR to stand if a leg is destroyed (p.231).
- Rear arc: Daniel's 2026-07-20 rule was one hexside (60 degrees); the p.60
  Firing Arcs Diagram (screenshot, 2026-10-19) shows 120 degrees, and
  `INTEGRATION__arcs.py` now follows the diagram (agrees at range 1).
  PATHFINDER's `combat.in_rear_arc` (not wired) still has the old rule.

**AMS readings - Daniel may overrule (Claude, 2026-10-20, `INTEGRATION__ams`):**
- p.206 says an AMS covers "the attack direction covered by the firing arc of
  the location in which the AMS is mounted". Read as: the attacker stands
  inside the AMS's firing arc, worked out like a weapon in that location
  (torso twist, flipped arms, rear-mounted "(R)" AMS). So a left-arm AMS
  covers the forward and left side arcs, a rear-mounted one only the rear.
- "Cannot be engaged if the MechWarrior controlling it is unconscious": read
  as the whole crew (a tripod's gunner can still engage with the pilot out).
  A shut-down mech can't engage either (p.104: activated equipment doesn't
  work, no actions).

**Artemis / Narc / ECM readings - Daniel may overrule (Claude, 2026-10-20, `INTEGRATION__electronics`):**
- A Narc homing pod's worth (Daniel: "the expected increase in damage from its
  opponents missile systems if it lands"): taken as ONE turn's gain, at this
  turn's range and to-hit numbers, heat ignored. The pod lasts the battle, so
  this undervalues it - a natural job for the future-capability Memo.
- Stealth armor / Void-Signature "suffers effects as if in the radius of a
  hostile ECM suite" (pp.202, 209): read as jamming the mech's OWN Artemis
  (an attacker inside hostile ECM), not attacks on it nor pods on it - that
  imaginary field is hostile to the stealthed mech, not to its enemy. And its
  real ECM is off, so attacks on it keep their Artemis / Narc bonuses.
- 31 units carry an Artemis FCS but only standard ammo (e.g. Longbow LGB-0W,
  Hunchback HBK-5SS) - probably sloppy MegaMek files. Rules as written
  (p.197): no bonus without Artemis-equipped missiles, so they get none.
- MegaMek says which launcher an FCS belongs to only by putting it in the
  same location; linked in slot order there (a leftover FCS goes to a
  launcher with none).

**Movement objective vs lethal spots (Claude, 2026-10-20 - RESOLVED
2026-10-21: Daniel's "lifetime" objective with the history blend is the
default; edge deaths 45 -> ~13 per 100. Its side effect, mirror-match stalls,
is Pick up here 0):** Daniel asked why the Hammerhead stands on
the board edge so much (37 of its 57 losses in a 100-battle batch were pushes
or displacement off the board). Traced on seed 2167380083587462785, turn 4:
the push IS priced (the Kontio's modeled reply pushes for 146 = the
Hammerhead's whole remaining armor + structure), but the fast Kontio's
modeled reply from 453 of the Hammerhead's 482 spots is a free shot from
outside its arcs, so those spots score dealt 0 / received (0.4 to 23) = 0,
while the 29 edge spots score 27.8 / 146 = 0.19 and win. dealt / received
can't tell "take 0.4" from "die" once dealt is 0. Options for Daniel:
(a) a lethal guard - a spot whose expected received reaches the mech's
remaining HP (or a push off the board) ranks below every other spot;
(b) a smoothed ratio (dealt + k) / (received + k), so received still counts
when dealt is 0; (c) a difference, dealt - received. Replay of that battle:
https://claude.ai/artifact/NJUknRiK1fcZzUv4A1fndX

**Known issues to fix later (Daniel, 2026-10-20):**
- **Scatter vs the firing arc.** Arrow IV (p.182) and artillery cannon
  (p.183) misses "cannot scatter outside the launcher's firing arc: ... lands
  in the last hex along its scatter path before it would". The code
  (`attack_resolution._resolve_area_miss`) ignores the arc - Daniel: "Firing
  arc is an issue."
- **Machine gun array ammo.** Daniel: the array "should still track ammo for
  each MG in the array being fired". The code takes one round from each gun's
  bins (`declare_attacks`, `ammo.take` per gun in `weapon_profiles.mga_guns`)
  - confirm it with a test (shared bins, a gun with no ammo left drops out of
  the column) and fix anything that falls short.

**Map terrain waiting on rules (Daniel is hunting them, 2026-10-21):** these
stop a map loading (`terrain_rules.UNSUPPORTED_FEATURES`); counts are of the
192 16x17 maps in `data/maps.zip` (`python tests/survey_maps.py`):
- Bridges - 11 maps. In the Core Rulebook (pp.53, 131: paved bridges are
  roads, otherwise buildings; under-bridge movement; capacity, collapse), but
  they lean on the full building rules.
- Fuel tanks - 6; hazardous liquid - 3; ultra-heavy woods (density 3) - 3;
  fortified hexes - 2; planted fields - 2; elevators - 1; impassable - 1;
  magma - 1 (the Core Rulebook only mentions it in passing and points to
  *MapPack: Volcanic*). None of
  these are in the rules library.
- Solaris arena maps (e.g. Hartford Gardens, Scrapyard) are walled: their
  east / west edges are all building, so a home-edge deployment there means
  neither mech can enter (both destroyed, p.37). Arenas need a deployment
  zone inside - Daniel's call.
- Not blocking, ignored: MegaMek "arms" / "legs" terrain (severed limbs lying
  in a hex, 4 maps) - pick-up isn't on (clubs, p.79).

**Weapon-use readings (Claude, 2026-10-20, `INTEGRATION__fire_modes`):**
- DECIDED (Daniel): an attack on a hex (Apollo saturation, Arrow IV) takes no
  target modifiers - no TMM, not even the immobile -4 - "so its usually gunnery
  + range + LOS blockers". MML LRM rounds group by 5 (the p.250 C7/C9 is a
  typo), SRM by 2. ATM ER / HE use the launcher's shots per ton.
- DECIDED (Daniel: "Arrow IV to hit sounds correct"): the attacker's own
  modifiers (movement, heat, sensors) and LOS apply; range, target movement,
  immobile, prone-target and target stealth don't (hex attack). Area-effect
  damage on a 'Mech: 5-point groupings (pp.87, 182). Scatter / firing arc:
  see "Known issues" above.
- Machine gun arrays: one round from each gun fired (see "Known issues").
- Heat on the target (flamers, plasma) is priced at `TARGET_HEAT_WORTH` (0.5
  damage a point) - a placeholder for Daniel; without it a plasma cannon (no
  damage) would never fire.
- Unjam attempts are declared at the start of the Movement Phase for both
  mechs (the rule only says "during the Movement Phase").
- The Core Ultra AC has no jam rule (only the Rotary jams) - followed as written.

**TODO noted in code:** a failed movement PSR drops the mech in its END hex;
in tabletop play it falls where the check was failed
(`orchestrator._phase_movement`).

**Other open items:**
- `config.PROMPT_FOR_MAP` picker not built — always loads `DEFAULT_BOARD_PATH`.
- `STITCH_MAPS` raises NotImplementedError (stitch_boards itself is ready).
- ~~Full `MECHSIM__equipment.json` not available (only the 14-entry
  mini)~~ RESOLVED 2026-10-19: the full DB is now `mechsim/equipment.json`
  (689 entries, 166 verified; 279 weapons, 144 with damage stats). Improved
  Jump Jets and Endo Steel are recognized; jump-jet crits now reduce jump MP.
  Its `_meta.entry_count` says 1086 - stale, the file holds 689.
- 2026-10-19 rulebook fill pass (see Change Record): 176/279 weapons now have
  damage + heat + range (was 144). ISLBXAC10 fires (as a flat slug - LB-X
  cluster mode still not modeled). Still unfilled, by design: special-rules
  weapons (ATM/iATM, HAG, MML, VSP, Heavy Gauss, Snub-Nose PPC, artillery,
  Narc, mortars, plasma, TSEMP, AMS, pods, MG arrays, Silver Bullet Gauss),
  footnoted damage cells (flamers, Nail/Rivet Gun), one-shot launchers
  (stats copied from base launchers 2026-10-19 - see Change Record),
  and items with no table row. `shots_per_ton` filled 2026-10-19 (107 weapons; ammo is tracked).
- ~~Minimum range not applied~~ RESOLVED 2026-10-19: penalty applied in
  `weapon_selection._weapon_range_mod` (+1 per hex inside minimum; missing
  `range.min` = 0). One-shot launchers carry their base launcher's stats;
  the fire-once limit is enforced since 2026-10-19 (`INTEGRATION__ammo`).
- Pile 1 reconciliation: `sim_runner._resolve_hit`/`resolve_weapon_attack`
  are absorbed (`INTEGRATION__attack_resolution`). `combat_turn`'s two-ply
  search and closing-fallback are NOT — don't delete `combat_turn.py` until
  movement selection replaces them or Daniel decides they're not wanted.

**Weapon data model gaps:** LB-X/Ultra/Rotary cluster math,
HAG range damage, Artemis, ammo variants (inferno effect on targets). The
one-shot fire-once limit is enforced since 2026-10-19.

**Cross-cutting hazard — RESOLVED 2026-10-18:** the
load-MECHSIM-then-purge-then-load-PATHFINDER workaround in
`INTEGRATION__weapon_selection.py` deleted `INTEGRATION__config`'s own
`config` registration and made the next `import config` fail (confirmed by
a live import test). Removed. Both directories now go on `sys.path` once.
No PATHFINDER module used by the battle loop imports `config`.

**Deferred by explicit scope call, not gaps:**
- End Phase beyond unconscious-pilot recovery (heat restarts happen in the
  Heat Phase, p.105; voluntary End Phase shutdown is a bot decision, not built).

**Source-project backlog** (not integration-blocking, real but unwired):
- MECHSIM: Clan free CASE auto-injection at parse time; Reactive Armor's
  full secondary crit roll (only flat halving is wired); Modular Armor;
  Shields (no spec); Superheavy/Compact engine 2-hit exception; LAM/exotic
  Config types; `equipment.json` curation (166/689 entries verified,
  rest generic padding); PSR special cases (quad-all-legs, AES-in-legs,
  Tripod, small/torso cockpit) specified but not implemented, cockpit-type/AES
  not parsed.
- PATHFINDER: impassable-hex detection (`.board` always reports `False`,
  no confirmed rule); bridges (refused at map load since 2026-10-21 - see
  "Map terrain waiting on rules"); ~~elevation cap on single-step movement~~
  (built 2026-10-21, pp.46-47); LOS rule-6 tie-break is a placeholder pending a real
  evaluation function; closing-turn reweighting formula undesigned;
  persistent cross-call LOS/damage-EV cache (currently rebuilt per
  candidate); JSON export of search-state (deferred).

**Known Issues (unresolved):**
1. `equipment.json`'s `category` field only has `weapon`/`ammo`/`misc` —
   heat sinks are `misc`; finding them needs a name match, not a category
   filter.
2. Pathfinder's LOS tie-break is an explicit placeholder until a real
   move/attack evaluation function exists.
3. ~~MECHSIM's PSR system has only ever been smoke-tested against the
   hardcoded fixture mech~~ — 2026-10-18: now exercised against real parsed
   .mtf units (Attack Phase 20+ damage, leg actuator, hip-triggered movement
   PSR, falls, failed stand-up, consciousness) in live battles.
4. MegaMek export quirk: a location's armor-type crit slots can appear
   in a *different* location's crit list — always read armor type from
   the location's own header line, never infer from crit contents.

---

## 4a. TORSO TWISTING (and firing arcs)

*Everything about torso twists and arc changes in one place. Code:
`INTEGRATION__arcs.py` (its docstring is the rule summary with page cites);
rules text: `rules/Battletech_Rule_Reference_Index.zip`, combat-part1 entries
CR-CMB1-FIRING-ARCS, ARCS-TORSO-TWIST, TORSO-TWIST, REVERSING ARMS; appendices-a-c
(tripods, quads). Tests: `tests/test_arcs.py` (10 checks) plus the arc checks in
`tests/test_movement_selection.py`.*

**Firing arcs (p.60, Daniel's diagram):**
- The angle of the centre-to-centre line from the attacker's facing.
  Forward within 60 deg (120 wide), left/right side 60-120 deg (60 wide each),
  rear beyond 120 deg (120 wide). A hex on a boundary goes to the forward arc
  (vs a side arc) or the side arc (vs the rear arc). All 15 labelled hexes on
  the diagram are reproduced by `tests/test_movement_selection.py`.
- Weapons by arc: forward = everything but rear-mounted; left/right side =
  that side's arm weapons (a weapon split torso/arm is forward-only); rear =
  rear-mounted only. Prone doesn't change arcs.
- Leg weapons use the legs' forward arc (the facing). Tripods (p.236): the
  left / right leg arcs start two hexsides left / right of the front, the
  centre leg's at the front.

**Arc actions - what a mech declares at the start of attack declaration,
Ranged or Physical phase (p.61):** `arcs.ArcAction(twist, flip, turret)`.
- **Torso twist (p.62):** one hexside left or right; a **tripod any hexside**
  (p.236). Shifts head, torso and arm weapons, punches, clubs and physical
  weapons; never leg weapons, kicks, the facing, or how the mech is hit (p.73).
  Prone mechs and quads can't twist.
- **Reversing (flipping) arms (p.62):** only a design with neither hand nor
  lower arm actuators in BOTH arms and no torso/arm split weapon (all or
  nothing, FAQ p.243; losing actuators to damage doesn't qualify; losing an arm
  doesn't disqualify the other). Arm weapons then fire only into the rear arc;
  no punches or arm physical weapons. Not while prone.
- **Quad Turret (pp.61, 205):** weapons marked "(T)" on the crit line (now kept
  by `mtf_parser` as `Equipment.turret_mounted`) fire into the turret's forward
  arc, turned any number of hexsides at each declaration; this is separate from
  the once-a-turn twist/flip. A crit on the turret slot locks it at the
  direction it last had (`turret_last_offset`).
- **Once a turn:** a twist OR a flip, not both; once declared it stands for the
  rest of the turn (`arc_action_locked`). A mech that declared neither in the
  Ranged phase may twist in the Physical phase (p.76). End Phase: torso
  forward, arms back (`arcs.end_turn`, called from `orchestrator._phase_end`).

**Physical Attack Phase (`INTEGRATION__physical.py`, pp.76-83, 237):** arcs come
from `arcs.arcs_between` (the old nearest-hexside code is gone). Punches and arm
physical weapons use the twisted torso's forward / that arm's side arc; kicks the
legs' forward arc. Tripods attack physically only into the twisted torso's
forward arc, kicks included, never into a side arc.

**Who picks (bot choices, pile 4):**
- Ranged: `attack_resolution.declare_attacks` tries every legal action and keeps
  the one with the most expected damage; no change wins ties; if nothing fires,
  nothing is declared (so the Physical phase may still twist). Next to the
  target (2026-10-19) it scores each action together with each physical plan
  that can follow: ranged fire without the weapons in the punching / kicking
  limbs + the plan's expected damage, since the twist stands for both phases
  and a limb that attacks physically can't have fired (pp.62, 76, 82). The log
  says when weapons are held back for a punch.
- Physical: `physical.choose_attack` re-picks with what actually happened (fired
  weapons, falls): every twist still allowed x attack type, most expected damage.
- Movement scoring (`ranged_combat.MoveEvaluator`) takes each side's best
  action per spot, physical plans included for spots next to the enemy (both
  ways). That is the real rule: twists are declared at attack declaration,
  after movement (p.61). `physical.Planner` caches the options per reach case
  (cost: about 2.5 s a turn on the default battle, was ~1.9).

**Not modeled / not reachable:**
- TAG designation (p.53) uses up the turn's twist/flip, but TAG never fires
  yet (`stubs.unconfirmed_weapon_data`); `arcs.declare` is the hook if it does.
- Shoulder / head turrets are Tactical Operations equipment, not Core: their
  "(T)" weapons are treated as fixed forward.
- Primary target in the forward arc (p.64) and hidden-unit point-blank shots
  (p.230) need more than one enemy / hidden units - the sim has neither.
- Push (p.83) ignores twists - pushes aren't built.

**Claude's calls (not settled by the rules - Daniel may overrule):**
- A rear-mounted weapon in a flipped arm still fires only to the rear.
- The Physical phase never chooses to flip (it only takes punches away).
- Turrets: the locked direction is the last one declared before the crit.

**Gotchas:**
- The rear arc is now 120 deg. Daniel's 2026-07-20 one-hexside (60 deg) rule
  is superseded by the p.60 diagram (identical at range 1); PATHFINDER's
  `combat.in_rear_arc` (not wired) still has the old rule. Listed for Daniel
  under Section 4 "Core Rulebook vs existing MECHSIM rules".
- Attack DIRECTION (front/left/right/rear hit tables, p.73) is a different
  thing from firing arcs and is unaffected by twists.
- History: Change Record, 2026-10-19 entries "Firing arcs and torso twists"
  and "Arc actions".

---

## 5. DECISIONS LOG (Daniel's calls — implementation may not override)

- **Deployment and movement calls (Daniel, 2026-10-21):**
  - "A mech's level before it enters is undefined. So it can enter on top of
    those level 5 walls. But it could also get stuck up there which is bad.
    (I think defining stuck as no path to the other side of the map is
    possible for this unit.)"
  - "Add a deployment option. Default is 0 with a 'I can't enter/stuck
    terrain' override. Its value is the number of hexes in from the edge that
    a mech can start its movement. The override sets it at 3."
  - "Expanding the simplifications is the next task. Which might require a
    new subphase. There is a difference between planning where you want to
    go which the picker does. And actually getting there, which is needed
    when piloting skill rolls are required for entering terrain. A failure
    and subsequent results would cause that mech to recalculate its movement
    starting from its current state."
  - (Later, 2026-10-21) "Think buildings are deferred for another session
    later. Add them to the list." - Pick up here item 7.
  - Breached slots / ammo and halved physical damage in movement scoring:
    "wiring and logic jobs that don't need calls, just the effort to fix
    them."

- **Map calls (Daniel, 2026-10-21, after the survey of MegaMek's 192 16x17
  maps):**
  - Easy map fixes approved: MegaMek "option" lines, depth-0 water, stacked
    terrain costs, jungle, the 2-level climbing limit.
  - Water rules (partial cover, running PSR, heat sinks, underwater combat):
    "Also Yes as the next task."
  - Buildings: "set an option (Set to on) to treat buildings as passive
    terrain. Blocks LOS. Can't be entered. Can be jumped onto (But not
    climbed onto IIRC)" - built as `config.PASSIVE_BUILDINGS` (default True).
    The full Core building rules come next, "probably a discussion first".
  - The rest (bridges, ultra-heavy woods, MegaMek-only terrain): "We're
    after full functionality in the end. So you'll have to let me know what
    is still causing problems so I can go hunt down rules. I know ultra heavy
    is easy enough to add. Bridges are probably a pain."

- **Session 3 calls (Daniel, 2026-10-20):**
  - Build order: AMS, then "Artemis and Narc. Since they both affect Missiles
    and are affected by ECM in similar ways." A Narc pod's "damage value" (to
    an AMS, and so to the bot) is the expected increase in damage from its
    owner's missiles if it lands; none once one has landed.
  - "Work on including the functionality of choice, but use a stub for the
    actual decision": rate of fire, MASC use and which ammo (Apollo mode
    included) are research - the stubs stay until the research is done.
  - An attack on a hex takes no target modifiers (no TMM, not even immobile):
    "usually gunnery + range + LOS blockers". Arrow IV to-hit as built is
    correct.
  - MML LRM mode groups by 5, SRM by 2 (table C7 / C9 is a typo); ATM ER / HE
    use the launcher's shots per ton.
  - Heavy Gauss 25 / 20 / 10; VSP damage S / M / L 5/4/3, 9/7/5, 11/9/7; HAG a
    5-point cluster weapon, +2 Cluster roll at short, -2 at long.
  - "All cluster damage of a specific size is added up and then applied" -
    built as optional rule `POOL_CLUSTER_DAMAGE`, default True.
  - "Fixing non functional weapons just became top priority" (done); specialty
    ammo deferred.
  - Later ideas: a best-solution lookup table per weapon by range and starting
    TN; cluster weapons' value raised by their crit odds against the target's
    armor (Section 0, "Pick up here" item 1).

- **Rules review calls (Daniel, 2026-10-20):** "We've entered the realm of
  optional rules" - each becomes a config switch. Floating Criticals: a
  true/false switch, default true (`FLOATING_CRITICALS`). Gyro destroyed and
  both legs destroyed: "Fight to the death" - True follows the rules as
  written; False (default) follows Daniel's rules and "declare[s] a fight
  done when one mech is rendered immobile" (`FIGHT_TO_THE_DEATH`; Claude's
  reading: immobile for good - destroyed gyro, both legs - not a shutdown or
  an unconscious pilot, which can recover). "Related to this concept is
  forced withdrawal and crippled. But that's both an option and adding a bot
  movement picker override" - later. Multiple PSRs and the seatbelt check:
  "Follow the rules as written." Fall side (1D6, 1 = rear): "Add that
  functionality."

- **Gunnery/piloting skill:** config-level input, not derived from `.mtf`.
- **HP scalar for scoring:** total remaining armor + structure. Adjustable later.
- **Weapon data model:** `equipment.json` is the single source once a
  mech's crit layout exists; no separate Pathfinder weapon dict.
  `Equipment` carries weapon/heat-sink stats extracted once at parse time
  (compute-once — see Section 7 performance rule), not re-queried per read.
- **Outer batch-loop / turn-flow controller:** new orchestrator files, not
  either existing driver. Old files stay as reference only, removed once
  new files are assembled.
- **Pile 1 reconciliation (2026-08-30):** `PATHFINDER__combat_turn.py` and
  `MECHSIM__sim_runner.py` are cannibalized into the integration then
  deleted from this project. Both remain intact in their own source projects.
- **Pile-4 extraction:** no dedicated bot module — logic lives in whichever
  file makes that decision; Section 6 is the tracking index.
- **RNG:** single `INTEGRATION__rng.BattleRNG` (NumPy `Generator`-backed,
  optional seed), owned by whatever drives a battle. Wired 2026-08-30;
  every dice roll in the battle loop now draws from it (except the tripod
  leg sub-roll, see Section 4). Same seed → byte-identical log (verified
  2026-10-18).
- **Heat-constrained weapon selection:** expected damage = P(hit) ×
  E[damage|hit]. `min_heat` = active goal, `max_heat` = hard ceiling.
  Two-phase selector. Built and tested; wired into Ranged Combat 2026-10-18.
- **Heat budget (2026-10-18):** "Max heat is dissipation + the set value" —
  weapon heat budget = max_heat + dissipation − current heat − movement
  heat, i.e. max_heat caps the end-of-turn heat level. Heat is saved state,
  carried turn to turn. Movement heat: Walk 1, Run 2, Jump
  max(3, Improved JJ ? ceil(hexes jumped/2) : hexes jumped).
- **Cooldown (2026-10-18):** when to hold fire and cool back to zero is bot
  logic — later. Currently a mech at max_heat stays there.
- **TMM source (2026-10-18):** actual hexes moved this turn
  (`combat.fc_to_tmm`, +1 if jumped). MECHSIM `compute_tmm()` not used.
- **Minimum range (2026-10-19):** +1 to-hit per hex inside minimum range,
  i.e. (min - range) + 1; a weapon with no listed minimum has minimum 0.
- **One-shot launchers (2026-10-19):** same range and damage stats as their
  primary launcher; they may only fire once (not enforced yet).
- **Engine-hit heat (2026-10-19, confirmed):** a hit taken this turn adds
  its heat in that turn's Heat Phase; after that the 5 (or 10) comes out of
  the weapon heat budget every turn.
- **Heat equipment defaults (2026-10-19):** player choices are "default on"
  for now - stealth systems always active, coolant pods used (Claude's
  reading of "on": when heat would stay above min_heat). Radical heat sinks,
  MASC and superchargers run a 1-turn-on / 1-turn-off cycle
  (`config.ESCALATING_CYCLE_ON_ODD_TURNS`). TSM is controlled by min_heat =
  9 (`config.TSM_MIN_HEAT`; Claude also raises max_heat to at least
  min_heat). Heat sinks are switched off in the End Phase from the mech's
  most possible heat (weapons + movement + damage) so min_heat can be
  reached.
- **min_heat (2026-10-19):** the floor on end-of-Heat-Phase heat (the mech
  "wants to sit at a minimum of" it), mirror of max_heat. Was: minimum
  weapon heat generated per turn.
- **Stub conventions (2026-10-18):** every placeholder is its own function in
  `INTEGRATION__stubs.py`, warns loudly every run, is counted into the
  results, keeps its knobs in config. (The movement stub is gone since
  2026-10-19.) Hit table default `mechsim_random`.
- **Movement objective default (Daniel, 2026-10-21):** "lifetime" with the
  history blend K = 3 is the default ("Switch this system to the new
  default"); "ratio" stays available. No destruction filter ("Works for
  pushes. Doesn't work elsewhere"); a desperate mech may take chances late.
- **Movement objective option (Daniel, 2026-10-20):** after the board-edge
  finding (Section 4), Daniel's design, built as an option to test against the
  ratio ("Go for it as an option. Then we test a few batches of battles and see
  if the results change dramatically"): score = damage now + (turns I survive)
  x (my future damage per turn); turns I survive = HP left after this turn /
  the enemy's future damage per turn; future damage per turn = .5 (odds of
  winning initiative) x perfect expected damage, "Gunnery+Best enemy TMM as the
  target number vs the optimum damage potential of the attacking mech". Claude's
  readings agreed before building: heat-limited (sustainable, at the present
  heat), the attacker assumed to walk (+1), kicks / punches at range 1, the same
  structure-weighted units as dealt / received. `config.MOVEMENT_OBJECTIVE`.
- **Movement selection (Daniel, 2026-10-19):** objective = damage dealt /
  (damage received + .001). Two-ply so both sides move intelligently. The old
  `combat_turn` closing fallback ported as-is ("working system first, improve
  later"). Armor-exposure weighting by the real hit direction (thin armor on
  a side makes shots on it count more, both ways). Partial cover is already in
  to-hit. Cooldown relies on max_heat. Expected damage from falling is added to
  the denominator, ONLY for Movement-Phase PSRs (not PSRs caused by damage);
  mines / lava / terrain PSRs are a future addition. Dropping `compute_score()`'s
  HP-awareness is fine for now. Internal-structure damage counts k = 2x
  armor damage, per weapon x hit-location table, no chaining
  (`MOVEMENT_STRUCTURE_WEIGHT`). A Void-Signature mech's low-movement spots
  get its TN bonus (it keeps every movement variant). Claude's choices inside
  that: the opponent's modeled reply uses the same rule (greedy, not
  searched); the PSR cost is P(fail) x ceil(mass/10) for Run (1+ hex) / Jump
  when a trigger exists; exposure factors clamp to [0.5, 3.0].
- **Movement attacks are anticipated (Daniel, 2026-10-20):** "First mover
  needs to anticipate being charged, or any other incorporated attacks."
  The two-ply modeled reply runs the same charge / DFA decision the real
  second mover does (gate, score, beat its best ordinary reply) against each
  first-mover spot; ranged fire and every physical attack (pushes included)
  were already in the reply's numbers.
- **Pushes (Daniel, 2026-10-20):** "It does no damage on its own, but can be
  used to push a mech off a cliff causing falling damage, or push a mech off
  the map, which should probably be evaluated as taking 100% damage. Its a
  case of the threat of it affects choices, and it will almost never be
  used." Implemented: value = P(hit) x (the target's remaining armor +
  structure off the board; the fall's worth 2+ levels down; else 0), a
  physical plan using both arms. The same displacement worth is added to
  charges and DFAs that hit.
- **Clubs (Claude's call, 2026-10-20):** picked up only on a turn the mech
  fires nothing anyway (it costs the whole Ranged phase); limb / girder before
  tree. Not planned for in movement (a mech doesn't walk into woods to fetch
  one).
- **Death from above (Claude's calls, 2026-10-20):** the jump must clear the
  target's LOS level (hex + 2 standing / 1 prone) within the jump MP; a
  DFA'er that fell in the Ranged phase lands without a second fall (the rule
  says resolve a failed DFA instead of the fall); on a miss the target steps
  to the open hex with the smallest drop.
- **Charges (Daniel, 2026-10-20):** "gate that decision tree to ask if a
  charge at this movement mode does more damage than normal attacks and
  physicals before thinking about it." Implemented: per movement mode, a charge
  is only scored if its expected worth beats the best ordinary (ranged +
  physical) dealt any spot in that mode offers; survivors are scored by the
  usual objective with the charger's return fire, the target's physical attacks
  and its own expected self-damage as received, and taken only if they beat
  the normal pick. Claude's calls: the attacker's self-damage lands on its
  front; the bot always aborts a TN 13+ charge; the charge PSRs (+2 both) and
  displacement aren't in the score. Note: the ratio objective punishes a
  charge's guaranteed self-damage, so a charge wins mostly when every ordinary
  spot takes return fire too (weak-gunned heavy chargers vs big targets).
- **Physical attacks weighted by hit table (Daniel, 2026-10-20):** punches and
  kicks "use different hit tables so would have different scoring modifiers".
  `physical.Worth`: the table's own armor exposure and structure bonus, in
  movement scoring and the Physical-phase choice; the Ranged-phase fire-or-punch
  choice stays raw like its gun side. Not moved into the weapon list: profiling
  showed no speed gain (Daniel's condition was "if it would speed up").
- **Firing arcs and torso twists (Daniel's p.60 diagram, 2026-10-19):** see
  `INTEGRATION__arcs.py`'s docstring - 120-degree forward and rear arcs,
  60-degree sides, boundary hexes to the non-rear arc; this supersedes the
  2026-07-20 one-hexside rear arc. Each side takes its best twist. Details
  and to-do: Section 4a.

---

## 6. PILE 4 — DECISION-MAKING INDEX (cross-cutting, not a module)

| Decision point | Lives in | Decides |
|---|---|---|
| Movement selection | `INTEGRATION__movement_selection.choose` | Spot (hex + facing + mode) maximizing the objective - DEFAULT "lifetime" + history blend (row below), or "ratio": dealt×exposure / (received×exposure + movement-PSR cost + .001); first mover scores each spot by the second mover's modeled reply (two-ply, at its MASC / supercharger speed). Knobs: config MOVEMENT SETTINGS. |
| Movement objective option (+ history blend, `MOVEMENT_LIFETIME_HISTORY_K`) | `movement_selection._Ratio` / `_Lifetime` (`config.MOVEMENT_OBJECTIVE`) | "ratio" (default, above) or "lifetime": dealt + (effective HP left / enemy future damage) x own future damage (`INTEGRATION__future_damage`: 0.5 x best heat-limited expected damage at gunnery + walking +1 + the target's best TMM, kicks / punches at range 1). Each side scores its own spots with it, the modeled reply too |
| LOS exactly between two hexes (p.56) | `pathfinder/los._evaluate` (`worse_key`) | The target's controller picks the hex; the bot always takes the MORE obstructive one (blocking first, then woods). The pick is the same from either end (checked on all 12,060 such pairs of the 16x17 board), so p.56's "used for all attacks between those two 'Mechs ... for the rest of that turn" holds without storing it. Not modeled: a target choosing the clearer hex to shoot back better; p.56's random pick for a non-player target (a hex attack takes the more obstructive one too). Partial / off-board hexes are never picked (p.56: "LOS cannot be shifted so that it passes through a partial hex") |
| Movement-PSR cost | `movement_selection.psr_costs` | P(fail) × fall damage, only for Run / Jump with a Movement-Phase PSR trigger; damage-caused PSRs ignored (Daniel) |
| Armor-exposure weighting | `movement_selection.exposure_factors` | Per-side vulnerability from current armor + structure (front = 1.0, clamped) |
| No-LOS / out-of-range movement fallback | `movement_selection.closing_fallback` | Ported as-is from `combat_turn._closing_fallback` (cases A/B1/B2); nearest-to-enemy otherwise |
| Heat-constrained weapon selection | `INTEGRATION__weapon_selection.py` | Which weapons fire this turn, built and wired |
| Heat ammo explosion bin (controller's choice) | `INTEGRATION__stubs.stub_heat_explosion_bin` | **STUB.** Which of several equally destructive, equally full bins explodes (random). |
| AMS engagements | `INTEGRATION__ams.engage` | Which missile hits each AMS takes (the ones it cuts most first; a Narc pod counts half its worth - 1D6 4+ - and nothing once a pod is on), cheapest-heat AMS first; skips an engagement that would end the turn above max(max_heat, `config.AMS_HEAT_LIMIT` = 13). Expected damage (weapon choice, movement) scales each missile weapon toward its engaged value by min(1, engagements / missile weapons) |
| Ammunition kind / guidance / Apollo mode per shot | `fire_modes.Planner` -> **STUB** `stubs.stub_munition_choice` | LB-X slug / cluster, ATM standard / ER / HE, MML LRM / SRM, Artemis / Narc-equipped / standard missiles, Narc homing / explosive pods, Apollo standard / saturation, bombast 8 / 12 / 16. Research (Daniel 2026-10-20); default "greedy" |
| Rate of fire (Ultra / Rotary AC) | `fire_modes.Planner` -> **STUB** `stubs.stub_rate_of_fire` | Research; default "max" |
| Unjam a Rotary AC | `fire_modes.declare_unjams` -> **STUB** `stubs.stub_unjam` | Research; default: always try unless prone |
| Narc beacon worth | `electronics.pod_value`, priced by `fire_modes.Planner` | A homing pod is worth one turn of the owner's extra Narc-missile damage (Daniel) - 0 once a pod is on or the target has ECM; explosive pods their damage. Not in movement scoring |
| Worth of heat put on the enemy | `config.TARGET_HEAT_WORTH`, `fire_modes.Planner.value` | 0.5 damage per heat point - placeholder until Daniel sets it |
| Ammo bin to draw from | `INTEGRATION__ammo.spend` | The bin with the fewest shots left (empties bins sooner) |
| Prop arm when firing prone | `INTEGRATION__attack_resolution.prone_fire` | The arm whose weapons matter least |
| Physical attack type | `INTEGRATION__physical.choose_attack` | Twist (if still allowed) + attack type (punch / kick / physical weapon / club / push) with the most expected worth, weighted by hit table (`physical.Worth`) |
| Ranged fire vs the physical attack that follows | `attack_resolution.declare_attacks` (`_physical_planner`) | Next to the target: best (arc action, physical plan) by ranged expected damage without the attacking limbs' weapons + the plan's expected damage (raw on both sides) |
| Torso twist / arm flip / turret | `declare_attacks`, `physical.choose_attack`, `ranged_combat.MoveEvaluator` | Most expected damage; no change wins ties (Section 4a) |
| Charge / death from above | `movement_selection._movement_attack_pick`, `_modeled_reply`; `INTEGRATION__movement_attacks` | Gate per movement mode (beat the best ordinary attack), then the objective must beat the ordinary pick; both movers (two-ply) |
| Push value | `physical.push_option`, `movement_attacks.displacement_worth` | P(hit) x (target HP off the board / fall worth 2+ levels down / else 0) |
| Turning while down | `orchestrator._turn_while_down` | A prone mech that can't stand (fight to the death): fewest hexside turns that put the enemy in its forward arc, else a side arc; none if nothing improves (1 per turn with a destroyed gyro, p.98). The two-ply reply model doesn't anticipate it |
| Club pick-up | `INTEGRATION__clubs.maybe_pick_up` | OFF (`config.CLUB_PICKUP`); waits for the Memo below |
| DFA miss: where the target steps | `INTEGRATION__dfa.resolve` | The open hex with the smallest drop |
| Home edge | `config.HOME_EDGE_CHOICE` | Which edge the deployment-roll loser picks (default random) |
| Escalating Failure use (radical heat sinks, MASC, supercharger) | `equipment_systems.use_escalating` -> **STUB** `stubs.stub_escalating_use` | Research (Daniel 2026-10-20); default "cycle" = Daniel's 1-turn-on / 1-turn-off |
| Coolant pod trigger | `INTEGRATION__heat._extra_cooling` | One pod when heat would stay above min_heat, not on a radical turn |
| Heat-sink switching | `INTEGRATION__heat.choose_heat_sink_deactivation` | End Phase: how many sinks stay on so min_heat can be reached |
| Aimed shot location | `config.AIMED_SHOT_LOCATION` | Where shots at immobile targets aim (default Center Torso) |
| Candidate reduction | `movement_selection.reduced_options` | Max FC (min MP) per (hex, facing, mode, fc>0); Void-Signature exempt |
| Best-reply selection | `movement_selection._modeled_reply` | Wired (two-ply) |
| `compute_score()` | `PATHFINDER__combat.py` | Not wired (reference; built on flat HP/weapon dicts) |
| LOS rule-6 tie-break | `PATHFINDER__los.py` | Placeholder, see Known Issues #2 |
| Closing-turn detection | `movement_selection.closing_fallback` | Wired (ported) |

### Memo: the bot must weigh how an action changes its FUTURE capabilities (Daniel, 2026-10-20)

Every decision so far is greedy for the current turn. Several need the bot to
ask what an action does to what it can do on later turns:
- **Clubs.** Picking up a tree costs the Ranged phase and (Daniel, "IIRC")
  the arm and front-torso weapons while it's held; "the question is if the
  utility of having a club is greater than the weapons you're armed with. The
  answer is almost always no - I've never seen anyone use a tree as a club."
  Pick-up is OFF (`config.CLUB_PICKUP`) until this exists.
- **MASC / superchargers.** Each use raises the failure target number and a
  failure wrecks the legs / engine; using them is a trade between this turn's
  MP and next turns' risk. Today: a stub (`STUB_ESCALATING_USE`), default
  Daniel's 1-on / 1-off cycle.
- **Rotary autocannons** (and Ultras): more shots now vs jams that take the
  weapon away later. The rules are built (2026-10-20); the rate is a stub
  (`STUB_RATE_OF_FIRE`), as are the ammunition kind and unjamming.
- Likely the same shape: radical heat sinks, coolant pods, ammo spending
  ("they'll need their own logic suite on if it's worth using up limited
  ammo"), heat build-up vs a shutdown later, and possibly the hanging-back
  movement problem (Section 0, "Pick up here" item 2).
Not designed yet - Daniel: "when we get to figuring out how the bot should
think." A natural shape is a value for the mech's state at the end of the
turn (weapons usable, heat, jam / failure risk, a club in hand) added to the
turn's score, so a decision sees what it gives up.

---

## 7. STANDING PROMPTS

- (Daniel, 2026-10-19: "nuke those standing instructions - Claude Code did
  good work with little to go on." The old "don't run code until told
  'compile'" and "one test pass" gates are retired: build, test and run freely;
  ask only when a real rules/scope call is Daniel's.)
- Never hardcode a BT numeric rule from memory — check the rules library
  (below) and cite the page; if the library doesn't settle it, ask Daniel.
- The rules library is `rules/Battletech_Rule_Reference_Index.zip` (Core
  Rulebook base layer in `base/core-rules/*.md`). Unzip it outside the repo
  and check rules against it; cite the page in the code.
- Keep source-project file prefixes; never let one overwrite the other.
- Name which pile new code belongs to; if it doesn't fit, say so.
- New pile-4 decision points get a Section 6 row.
- Section 4/5 items aren't Claude's to resolve by inference — stop and ask.
- Daniel owns BT rules/scope; Claude owns implementation (structure,
  naming, data shape, algorithm choice) — don't reflect ordinary
  implementation calls back as questions.
- Monte Carlo batches multiply per-call cost — default to compute-once/
  cache over recompute-on-every-read; name which shape a choice takes.
- Daniel reads code, doesn't write it — clean, explicit, commented over
  dense/clever. Don't "fix" a Known Issue without checking it's actually
  a bug first. Sign work in the Change Record below.
- Placeholders go in `INTEGRATION__stubs.py` as loud, counted stubs with
  config knobs — never as silent defaults.
- (Daniel, 2026-10-20) **Claude runs the GitHub logistics**: develop on the
  session branch, commit with clear messages, push, open a PR to `main` and
  merge it once every test passes - Daniel doesn't use GitHub. Tell him in
  plain words what changed; don't make him handle branches or PRs.
- (Daniel, 2026-10-20) A decision with a cheap test that rules most cases
  out goes FIRST in the decision tree ("gate that decision tree ... before
  thinking about it") - e.g. charges / DFAs only get scored if they beat the
  best ordinary attack in that movement mode.
- (Daniel, 2026-10-20) Don't pause at natural checkpoints waiting for a
  "continue" - keep working through the agreed list; stop only for his calls.
- (Daniel, 2026-10-20) "We've entered the realm of optional rules. Which
  means more things to set up when configuring a run." Optional rules and
  Daniel-vs-Core differences become switches in `INTEGRATION__config.py`'s
  OPTIONAL RULES section (his default first, the rules as written available).
- (Daniel, 2026-10-20: "probably need to establish a briefer way to get a
  clean baseline") The baseline is one command, `python tests/run_checks.py`;
  a new test file or reference battle joins it automatically - keep new
  checks quick.
- (Daniel, 2026-10-21) Test battles stop at 50 turns: "No real fight should
  last that long. If it does it deserves to be noted as a possible flaw." A
  reference battle that hits the cap prints a NOTE; batch summaries flag
  battles that hit config.MAX_TURNS.
- (Daniel, 2026-10-21) Another instance may be working in parallel (maps):
  merge `origin/main` before merging, regenerate reference logs rather than
  hand-merging them.
- Measure speed on the fixed benchmark (`tests/benchmark_turns.py`) before and
  after; a change only for speed must leave every result identical.
- Reference logs: regenerate (`--update`) only for changes meant to alter
  results, and say so in the Change Record.
- (Daniel, 2026-10-20) A bot decision that is still research (rate of fire,
  MASC, ammo kind...) is built as OPTIONS (the rules) plus a loud stub that
  picks - don't invent a "real" policy for it without him.
- (Daniel, 2026-10-20) Known issues he names go in Section 4's "Known issues
  to fix later" list, not fixed on the spot unless he says so.
- New weapons / equipment: check the item's equipment.json row against the
  Core tables (pp.248-254) - slots, damage, range, heat, shots per ton - and
  its ammo-bin names against `ammo.parse_bin`; the data had many gaps.

---

## 8. CHANGE RECORD

*(Starts fresh 2026-08-28 — prior history archived/removed, not carried forward.)*

- **2026-10-21 (Claude):** The movement subphase (Daniel's design, Section 5;
  RULES_REVIEW F32; G11, G19 done).
  - `terrain_rules`: `step_psrs` / `turn_psrs` / `step_psr_causes`
    (rubble, sand with a level change, water when running, mud facing
    changes when running, backward level changes), `PSR_MODIFIER`,
    `has_psr_terrain` (cached on the board); backward level changes of one
    level allowed in `step_cost` (not with a destroyed hip, not on a roof).
  - `pathfinder`: `_build_terrain_psr` -> `PathTable` (PSR counts per entry,
    `path()` with `keep_parents`), used only on boards with PSR terrain or
    any level change - the flat boards keep `_build_terrain_aware` (results
    identical there).
  - `ranged_combat.movement_options` records `mover.path_psrs` (cleared per
    pick in `movement_selection.reduced_options`, which keeps a fewer-PSR
    variant unless dominated); `path_to()` rebuilds the path for a pick.
  - `movement_selection._Side.psr_cost` / `psr_for`: terrain PSRs priced as
    P(fall) x fall damage (`terrain_psr_odds`); jumps landing in water or
    rubble. Replaces the end-hex water pricing.
  - `orchestrator._walk_path` (roll each PSR in its hex; fall there) and
    `_after_fall_midmove` (stand with the MP left - `piloting_rolls.
    resolve_stand_up(mp_available=)` - and re-pick, repeatedly; hexes and MP
    add up, mode kept); `_landing_psr` (jumps: water, rubble) replaces
    `_water_psr`; a prone mech skips the end-of-move damage PSR.
  - Tests: `test_water.py` 16 (the subphase, terrain PSRs, backward level
    changes). Reference logs: Military Base 1 (backward level changes) and
    Large Lakes 1 (PSRs per water hex, two falls) regenerated; the others
    changed only in KNOWN_MISSING_RULES. Hill boards ~5-10% slower.

- **2026-10-21 (Claude):** Deployment depth and stuck terrain; water
  leftovers (Daniel's calls, Section 5; RULES_REVIEW F31, G20).
  - New `INTEGRATION__deployment.py`: `start_hexes(mech, board, edge)` -
    hexes 0..`config.DEPLOYMENT_DEPTH` (default 0) in from the home edge
    that the mech can enter (roofs too: `terrain_rules.step_cost(None, roof)`
    now allowed - "a mech's level before it enters is undefined") and from
    which it is not stuck (walking / jumping can reach a hex within 3 of the
    far edge); none -> `config.DEPLOYMENT_STUCK_DEPTH` (3). The deployment
    log line is unchanged for a plain edge. `mech.home_edge_row` keeps the
    edge for "head for the enemy's edge".
  - Hull breaches (`damage_resolution.mark_location_nonfunctional`, shared
    `_slot_loss_effects`): slots stay, still soak crits (effects not counted
    twice), breached ammo still explodes, breached gear that explodes only
    when working doesn't (p.127).
  - Scoring: `water.physical_value_factor` - physical damage to underwater
    locations counted at half in movement scoring (`physical.Planner`
    t_water), the Physical phase's pick and charge / DFA values (p.77).
  - Tests: `test_terrain.py` 11 (deployment, no start hex), `test_water.py`
    14. All reference logs unchanged. Benchmark 501 / 495 (17.2-17.6 s vs
    17.9-18.3 s for the pre-water code on the same machine).

- **2026-10-21 (Claude):** MAPS, part 3 - water rules, part 2 (RULES_REVIEW
  F30; `INTEGRATION__water`).
  - Physical attacks in water (p.77): `water.physical_allowed` filters the
    attack kinds in `physical.attack_options`, the Ranged phase's look-ahead
    (`attack_resolution._physical_planner`), movement scoring
    (`physical.Planner` / `ranged_combat._with_physical` take `allowed`) and
    charge / DFA planning (`movement_attacks`). `water.physical_damage`
    halves damage to underwater locations (punches, kicks, clubs, charges,
    DFAs).
  - Hull breaches (p.127): `damage_resolution.apply_damage` calls
    `water.check_breach` for each underwater location a grouping damages (2-4
    breaches); `orchestrator._after_phase` breaches armorless locations under
    water (`water.auto_breaches`); `water.breach` marks the slots destroyed,
    a leg as destroyed, a side torso's arm with it.
  - Drowning (p.117): `orchestrator._phase_end` - life support crit + fully
    submerged = 1 MechWarrior hit.
  - `tests/test_water.py` 9 -> 12 checks. The Large Lakes reference battle
    regenerated (breach rolls change its dice); every other reference log
    changed only in KNOWN_MISSING_RULES' water line. Benchmark 501 / 495.
    Sweep: 64 water maps x 2 seeds, 128 battles, no errors.

- **2026-10-21 (Claude):** MAPS, part 2 - water rules, part 1 (Daniel: water
  "Also Yes as the next task"). New `INTEGRATION__water.py` (page cites in
  each function); RULES_REVIEW F29, G6 is now part 2.
  - `terrain_rules.prepare_board`: a depth 1+ water hex's `level` becomes
    its floor (surface - depth, p.57), with `depth` and `surface_level` kept
    - so moving in / out is a level change (p.51; a depth-3 lake can't be
    walked into from its shore), jumps start / land at the floor (p.50), a
    'Mech in water stands on the bottom for LOS, and falls into water add
    the depth (p.115).
  - `los.py`: partial cover for a target standing in depth 1 (p.66), not
    against a fully submerged attacker; a water hex is never the "hill" that
    gives cover.
  - `attack_resolution.declare_attacks`: no attack across the water line
    (p.62); weapons the water stops (Underwater Attacks Table, pp.67, 127);
    underwater range +1 bracket, no long range (p.127, via the TN adjuster);
    submerged heat sinks in the heat budget.
  - Heat (`heat.py`, `ams.py`): submerged sinks dissipate double, at most +6
    (p.103); the Heat log shows "- water N".
  - Jumping MP in water (p.50): `water.jump_mp` (movement options, charges,
    the budget line).
  - PSRs: `orchestrator._water_psr` - running (Run, 1+ hex) or jumping into
    depth 1+ water, a failed jump falls the depth (pp.48, 50); END hex only
    (no paths kept). `piloting_rolls.resolve_fall` halves damage in water
    (p.115).
  - Movement scoring (`ranged_combat.MoveEvaluator`, `movement_selection`):
    each spot's water case (weapons stopped, range shift, heat sink bonus,
    the water line) and the water PSR's expected fall damage. Boards with no
    water take exactly the old path - every older reference log and the
    benchmark (501 / 495) are unchanged apart from the summary's
    KNOWN_MISSING_RULES text (water part 2 listed; all logs regenerated for
    that line only).
  - Replay viewer shows a water hex's surface level. `tests/test_water.py`
    (9 checks); reference battle Black Hawk F vs Cataphract CTF-3D on
    `data/16x17_Large_Lakes_1.board` (seed 1: jumps and runs into water, a
    halved fall, fire held across the water line, submerged sinks).

- **2026-10-21 (Claude):** MAPS, part 1 (Daniel, after the survey of
  MegaMek's 192 16x17 maps: "1. Yes ... 3. set an option (Set to on) to
  treat buildings as passive terrain"). Before: 31 maps played correctly, 29
  crashed (depth-0 water, bridges, ultra-heavy woods, stacked costs), 20
  didn't load (MegaMek "option" lines), and on the rest buildings, cliffs
  and most water rules were silently ignored. Now 165 play.
  - `pathfinder/board_parser.py`: skips "option" lines; knows MegaMek's
    terrain names (no warnings for building / pavement / fluff codes).
  - `pathfinder/terrain_rules.py` rewritten around `step_cost(from, to,
    level_limit, backward)` (MP or None = not allowed): Movement Costs Table
    p.48 with jungle / rubble / swamp / sand / mud / depth-0 water; stacked
    terrain adds up (p.47); road travel only road to road (p.53 - a road hex
    entered off the road now pays its terrain, CHANGED from always +0); the
    2-level limit, 1 with a destroyed hip (pp.46-47); passive buildings
    (pp.46, 134). `prepare_board()` runs when a map loads: refuses terrain not
    built yet with a list (bridges, ultra-heavy woods, MegaMek-only terrain)
    and turns building hexes into roofs (level = hex level + height, p.130).
    `transition_cost` kept for simple callers / old tests.
  - `pathfinder/pathfinder.py` (`level_limit`), `ranged_combat.movement_options`
    (hip limit; board entry can't land on a roof), `pathfinder/combat.py`
    (jump landing height, p.50), `movement_attacks` (charge's last step uses
    step_cost; a push from the ground into a building is blocked).
  - Option `config.PASSIVE_BUILDINGS` (default True; False refuses maps with
    buildings until the full rules are built).
  - Bug fix (`orchestrator.run_battle`): a mech that can't enter the
    battlefield (destroyed, p.37) left the battle running into the Ranged
    phase with no hex and crashed; the battle now ends there. Found on the
    Solaris arenas (Hartford Gardens, Scrapyard), whose east / west edges are
    solid walls.
  - Replay viewer draws buildings (B3 = roof level 3), roads / pavement,
    rough / rubble, water depth.
  - `data/maps.zip` (Daniel's map pack), `tests/survey_maps.py` (which maps
    play), `tests/test_terrain.py` (10 checks), new reference battle Black
    Hawk F vs Cataphract CTF-3D on `data/16x17_Military_Base_1.board` (seed 1,
    3 roof landings). The other reference logs are unchanged (flat board).
    Published replay: https://claude.ai/artifact/HcWk2ESA5zT4YKGc8MGfem
  - RULES_REVIEW F24-F28 (G2, G3 done), G6 now the water rules, new G19
    (terrain PSRs mid-move). Section 4: "Map terrain waiting on rules".

- **2026-10-21 (Claude):** Session 4 wrap-up (Daniel: "Cap the test battles
  length to 50 ... Anti-stall rule for the bot is added to the future tasks
  list ... the work space is set for the next instance"). Reference battles
  run with `config.MAX_TURNS = 50` (`check_reference_logs.TEST_BATTLE_MAX_TURNS`);
  one that reaches it prints "NOTE: reached the 50-turn cap ... a possible
  flaw" (also in `run_checks.py`), and every batch summary flags battles that
  hit their turn cap (`BattleResult.turn_cap`, summary "turn_cap_reached").
  Only the Asymptote mirror hits it (the stall); its log regenerated (the
  others end before turn 50 and are unchanged). run_checks ~12 min -> ~3 min.
  New `tests/ab_batches.py` (the A/B harness used this session: same seeds,
  several settings side by side). Section 0 rewritten for the next instance;
  RULES_REVIEW F21-F23 (AES, LOS on the border of two hexes, hardened armor);
  Section 7 notes (50-turn cap; a parallel instance). Benchmark 501 / 495.

- **2026-10-21 (Claude):** New default movement objective: "lifetime" with
  the history blend, K = 3 (Daniel: "Switch this system to the new default").
  `tests/test_movement_selection.py`'s brute-force helpers now score with the
  configured objective (they used the ratio formula directly). All reference
  logs regenerated (intended). Benchmark 477 / 468 -> 501 / 495 (15.3 s).
  FINDING for Daniel: mirror matches stall. The Asymptote mirror reference
  battle went from ~100 turns to 488 (cap 500): shots fired in only 55 of 488
  turns, up to 33 turns in a row with none; it ended on a head hit. Equal
  future damage on both sides means each fights only when this turn's trade
  beats 1:1, so neither commits. That one battle makes run_checks.py take
  ~12 min (was ~1.5). Options for Daniel: an anti-stall rule, or a turn cap
  for that reference battle.

- **2026-10-21 (Claude):** Time tracker (Daniel: "put a tracker on them to see
  where they're spending their time. We still need more speed"). New
  `INTEGRATION__timing.py`: `timing.section(name)` timers that nest (movement >
  picking a spot > two-ply look-ahead > reply scoring ...), each battle's
  totals carried back on `BattleResult.timing` (parallel workers included),
  and a "WHERE THE TIME WENT" table after every batch and in
  `tests/benchmark_turns.py`. `config.TIMING` (default True),
  `config.PROFILE_FUNCTIONS` = N lists the top N functions by own time
  (cProfile, ~2x slower; `BattleResult.profile`). Sections in the orchestrator
  (movement, ranged, physical, heat, end), movement_selection (reachable
  spots, scoring vs the enemy where it stands, future damage, two-ply, reply
  scoring, reply charges / DFA, charges / DFA) and attack_resolution
  (choosing weapons, resolving hits). The reference battles and the tests
  that compare printed output switch TIMING off. No result changes
  (benchmark 477 / 468). First reading (benchmark, ratio objective): the
  two-ply look-ahead is ~97% of the time - reply scoring ~74%, the per-reply
  candidate loop ~18%, reply charges / DFA ~5%; ranged, physical, heat and End
  Phase together under 0.2%.

- **2026-10-21 (Claude):** A/B batches for the history blend (same seeds as
  the ratio / lifetime batches below). Kontio vs Hammerhead, 100: lifetime +
  history K=3 Kontio 58 / Hammerhead 41 / draw 1 (ratio 59 / 39 / 2, plain
  lifetime 68 / 32 / 0), 19.3 turns (12.8 / 23.9), 13 off-board deaths
  (45 / 12); K=1: 55 / 45 / 0, 20.4 turns, 15 off-board - K 1 vs 3 is within
  the dice noise. Atlas AS7-K vs Archer ARC-2R, 40: 37 / 3 / 0, 15.8 turns
  (ratio 11.1, lifetime 21.7), same winner as ratio on 37 of 40. Cataphract
  CTF-3D vs Emperor EMP-6D: 3 / 37, 19.0 turns (12.4 / 24.6), same winner 34
  of 40. Replays, seed 766213648170853994 (pushed off turn 8 under ratio, wins
  turn 16 with history): https://claude.ai/artifact/C1ZBQWqzZmAnkp3tJfun5w
  (ratio), https://claude.ai/artifact/44yfKRLbr1XDTatWiBDCX9 (history K=3).
  Waiting on Daniel: make lifetime + history K=3 the default?

- **2026-10-21 (Claude):** History blend for the lifetime objective (Daniel:
  "We can't predict the future. But we can record the past"; "go with History
  blended K for now"; no destruction filter - "Works for pushes. Doesn't work
  elsewhere"; "I'm willing for a desperate mech to take chances later in the
  match"). `config.MOVEMENT_LIFETIME_HISTORY_K` (None = off): each future
  damage per turn = (K x estimate + damage really done) / (K + turns fought).
  The orchestrator records each mech's effective HP at deployment and every
  End Phase (`movement_selection.record_hp`, `mech.hp_log`); damage done =
  the other mech's real HP loss (falls and explosions included); turns fought
  start at the first turn either mech lost HP (`battle_record`). New check
  `history_blend_math`. Default unchanged (ratio; K None): reference logs
  match, benchmark 477 / 468.

- **2026-10-21 (Claude):** A/B batches, MOVEMENT_OBJECTIVE "ratio" vs
  "lifetime", same seeds (12345 batches), after the LOS and booster fixes. No
  code change. Kontio vs Hammerhead, 100 each: ratio Kontio 59 / Hammerhead
  39 / draw 2, 12.8 turns, 45 off-board deaths; lifetime 68 / 32 / 0, 23.9
  turns, 12 off-board deaths; same winner on 56 of 100. The Hammerhead's
  hits per turn halve (0.51 -> 0.26): its fight-or-not bar (my future / the
  enemy's future, ~0.6 against the faster, stealthier Kontio) is rarely met,
  so it backs off - but the Kontio reaches it anyway and shoots its back.
  Atlas AS7-K vs Archer ARC-2R, 40 each: 38 / 1 / 1 vs 37 / 3 / 0, 11.1 ->
  21.7 turns, same winner 35 of 40. Cataphract CTF-3D vs Emperor EMP-6D: 3 /
  37 both, 12.4 -> 24.6 turns, same winner 34 of 40. Replays of seed
  6507740548082236446 (Hammerhead wins turn 19 under ratio, dies turn 4
  under lifetime): https://claude.ai/artifact/7bjL7ePCNvjvWtF7dHb2M9 (ratio),
  https://claude.ai/artifact/5aWrPwb9mXCLkznRnpZaHV (lifetime). Waiting on
  Daniel: keep / adjust / drop the lifetime option.

- **2026-10-20 (Claude):** The two-ply look-ahead models MASC / supercharger
  speed. The modeled second mover's moves were built before its booster roll
  (Running MP x1.5), so a supercharged Kontio was predicted to run 9 and
  really ran 12 to push the Hammerhead off the board (A/B seed
  3486141480966086336, turn 3). New `equipment_systems.boost_multiplier`
  (the bot's own use decision without the stub warning, the 3+ roll counted
  as a success) and `modeled_boost`; `movement_selection._opponent_options`
  builds the reply's moves at that speed (the rule Daniel set: the reply is
  chosen "by the same rule the real second mover uses"), and
  `future_damage.best_tmm` counts a working booster (BEST TMM). Affects both
  objectives. Reference log `Asymptote_vs_HeatGear_seed5` regenerated (its
  test mech has MASC + a supercharger); benchmark unchanged (477 / 468).

- **2026-10-20 (Claude):** LOS between two hexes (Core p.56: "If LOS falls
  exactly on the line between two hexes, the target 'Mech's controller
  chooses which hex LOS passes through"). Two bugs in `pathfinder/los.py`,
  found when an A/B batch crashed (Atlas AS7-K vs Archer ARC-2R: "Intervening
  LOS hex (5, 1) is not on the loaded board"): (1) the edge test rounded both
  tied cube coordinates with Python's round-half-to-even, which often sent
  both to the SAME hex, so the second hex of a hexside line was missed - its
  woods / blocking terrain ignored (`_cube_round_candidates` now rounds the
  point nudged a hair to each side); (2) along the board edge one of the two
  hexes is off the board - the line now passes through the on-board one
  (Claude's reading of p.56: there is no off-board hex to choose) instead of
  raising. Every one of the 73,712 hex pairs on the 16x17 board now traces
  (24,120 have a two-hex step). Before, movement scoring silently skipped the
  spots that raised; a battle that reached one in the Ranged phase crashed.
  Reference logs regenerated (intended: fewer "spots with LOS" where the
  missed hex had woods); benchmark 458 / 466 -> 477 / 468.

- **2026-10-20 (Claude):** Movement objective option "lifetime" (Daniel's
  design, Section 5 "Movement objective option"). New
  `INTEGRATION__future_damage.py` (future damage per turn; `best_tmm` reads
  Running / Jumping MP without compute_tmm's side effect);
  `movement_selection._Ratio` / `_Lifetime` objects, one per side per pick
  (`_link`), used by the static scores, the two-ply and its modeled reply, and
  the charge / DFA scoring; `effective_hp` = armor + rear + k x structure.
  Config `MOVEMENT_OBJECTIVE` ("ratio" default), `MOVEMENT_LIFETIME_INITIATIVE`,
  `MOVEMENT_LIFETIME_ATTACKER_MODE`, `MOVEMENT_LIFETIME_FUTURE_FLOOR`. Three new
  checks in `tests/test_movement_selection.py`. Default unchanged: reference
  logs match, benchmark 458 / 466.

- **2026-10-20 (Claude):** Battle replays (Daniel: "build outputs both text
  and visual you can share from battles you run so I can see whats going on
  without me having to download the current version and run it myself").
  New `INTEGRATION__replay.py` (recorder + page writer) and
  `INTEGRATION__replay_viewer.html` (the page: hex map, record sheets, step
  log; no libraries). `config.REPLAY_BATTLES` / `REPLAY_DIR`;
  `config.set_log_sink` lets the recorder copy every log line, VERBOSE or
  not; `orchestrator.run_battle` marks the steps; `BattleResult.replay` carries
  the data back from parallel workers and `run_batch` writes the pages.
  Seeds are stored as text (they pass JavaScript's exact-integer limit). New
  `tests/test_replay.py` (recording changes nothing; step structure; page
  data round-trips). Default off: no result changes, benchmark 458 / 466.
  Also logged the movement-objective finding (Section 4, Pick up here 0).

- **2026-10-20 (Claude):** Actuator Enhancement System, Core p.206 (Daniel:
  "if AES is the only thing not built in this test, lets get that fixed").
  `mech_state.arm_aes_working` / `leg_aes_working` (cached per mech, refreshed
  on a crit): leg AES -2 in `piloting_rolls.special_case_modifier`, -1 to
  kicks (`physical._kick_options`) and charges (`charge.to_hit`, shown in the
  charge log line); arm AES -1 to that arm's ranged weapons
  (`attack_resolution.arm_aes_modifier`, in `tn_adjuster`, so movement
  scoring sees it too; split arm / torso weapons excluded) and its punches,
  claws and physical weapons; clubs and pushes -1 only with AES in both arms.
  Crits: any leg AES slot hit ends the leg effects; an arm only its own.
  DFA isn't named by p.206, so no change there. Tests: two new checks in
  `tests/test_equipment.py` (Hammerhead legs; Vindicator VND-3LD (Dao) arms).
  Reference logs regenerated: only the known-missing-rules AES line goes
  (the default battle ends on turn 1, before any PSR). Benchmark unchanged
  (458 / 466). Hardened armor checked against p.202 at the same time - all
  four effects were already built (2 points per pip, -2 TAC while armor
  remains, +1 PSR, -1 Running MP).

- **2026-10-20 (Claude):** New default matchup (Daniel: "Asymptote is an
  uninteresting match"; "kontio vs hammerhead ... Because its the example in
  the game's starter set"). `data/Kontio.mtf` and `data/Hammerhead.mtf`
  (from `meks.zip`, RG21 / RG05 - the only version of each) are
  `MECH_RED_MTF` / `MECH_BLUE_MTF`. Every gear item fires or applies except
  the Hammerhead's leg AES (not built - Section 4, and a new line in the
  report's known-missing rules). New reference battle
  `Kontio_vs_Hammerhead_seed12345` (the Kontio runs behind the Hammerhead on
  turn 1 and burns through its 5-point rear CT). The Asymptote reference
  battles and the benchmark now name the Asymptote explicitly (four
  scenarios had left Red to the default). Reference logs regenerated: the
  only change to the old ones is the AES line. Benchmark unchanged (458 / 466).

- **2026-10-20 (Claude):** One-command baseline (Daniel: "probably need to
  establish a briefer way to get a clean baseline. I sense that test bloat
  has taken hold."). New `tests/run_checks.py`: every test file and every
  reference battle run side by side (one per CPU core), one line each, a
  one-line verdict, `--bench` adds the benchmark. `check_reference_logs.py`
  runs its battles side by side too (its `compare` is shared). Cloud
  container: ~5 min one at a time -> ~1.6 min. No checks removed, no result
  changes (logs regenerate byte-identical; benchmark 458 / 466).

- **2026-10-20 (Claude):** Session 3 wrap-up (Daniel: "Good pass. Clean
  up."). Section 0 rewritten for the next instance; Section 4 "Known issues to
  fix later" (scatter vs firing arc; MG array ammo check); Section 5 session-3
  decisions; Section 7 three standing notes. Dead code removed
  (`fire_modes.mml_size`, `weapon_rules.is_laser_ams`). No result changes.

- **2026-10-20 (Claude):** Non-functional weapons (Daniel: "Fixing non
  functional weapons just became top priority"; review F18-F20). New
  `INTEGRATION__weapon_profiles.py`, read by `fire_modes`: variable damage by
  bracket (heavy Gauss 25/20/10, Snub-Nose PPC 10/8/5, VSP 5/4/3, 9/7/5,
  11/9/7 - Daniel), HAG (C5 on the 20/30/40 column, +2 short / -2 long),
  M-pods (15/10/5 column, C1), machine gun arrays (p.185: +2, the guns'
  column, one location; guns linked per location), bombast lasers (8/12/16
  at +0/+1/+2, heat 6/9/12 - a munition-stub choice), rifles (-3 vs 'Mechs),
  flamer / plasma heat on the target (`heat.resolve_heat_phase` outside
  heat, cap 15, p.102), Arrow IV (hex attack 7-17 hexes, Gunnery + 4, 20 AE,
  scatter MOF/2, 10 next door) and artillery cannons (AE, no immobile -4,
  scatter, Long Tom splash 10). Apollo saturation mode (Daniel's hex-attack
  ruling: `Planner(hex_offset=)` drops the target's TMM / immobile / prone /
  Void modifiers). MML LRM grouping 5 (Daniel: table typo). New optional
  rule `POOL_CLUSTER_DAMAGE` (default True, Daniel): an attacker's cluster
  damage of one grouping size (and damage type) is summed per phase, then
  grouped. New knob `TARGET_HEAT_WORTH` (placeholder 0.5). equipment.json:
  Clan flamers, plasma rifle / cannon, M-pod, B-pod, Snub-Nose PPC type,
  heavy MGA rows filled; IS MGA, three rifles, rifle ammo, bombast laser,
  Clan Arrow IV (12 slots; IS 15) added; artillery cannon damage / slots;
  chemical laser shots per ton (ammo now used). Ammo: Arrow IV standard bins
  feed; glued "...Ammo" names. 617 units had a Core weapon that couldn't
  fire; now only non-Core weapons are left (TSEMP, iATM, mortars,
  full-size artillery, fluid gun...). New `tests/test_weapons.py` (12
  checks); new reference battles `Bombardier_BMB-14K_vs_Black_Hawk_F_seed4`,
  `Bombardier_BMB-05A_vs_Cataphract_CTF-3LL_seed4`. Reference logs
  regenerated (pooled cluster damage changes missile battles; banner text).
  Benchmark unchanged (458 / 466).

- **2026-10-20 (Claude):** Weapon-use options with stub decisions (Daniel:
  "Work on including the functionality of choice, but use a stub for the
  actual decision"; review F14-F15). New `INTEGRATION__fire_modes.py`:
  Ultra (1-2) / Rotary (1-6) AC rapid fire (pp.182-183: heat and ammo per
  shot, one attack roll, Cluster Hits on the shots column, each shot its own
  location; no aimed rapid fire); Rotary jams (2-3 shots on 2, 4-5 on 3-, 6
  on 4-) and unjamming (declared in the Movement Phase - stand still / walk
  only - Gunnery + 3 at the end of the Ranged phase); LB-X cluster rounds
  (p.192: -1, rating column, 1-point pellets, no TC); ATM ER / HE and MML
  LRM / SRM ammunition (pp.186, 250, 252: damage, ranges, groupings, MML
  shots per ton); Apollo standard-fire mode (p.197, linked like Artemis:
  no MRM -1). `ShotPlan` per shot (`DeclaredAttack.fire`) wraps the
  electronics guidance; `Planner` prices special weapons for the knapsack
  (`weapon_selection` `planner=`, replacing the AMS / fire-control value
  factors and `bonus_per_hit`) and movement scoring, and makes the decision
  at declaration. New stubs (all loud at the decision): `munition_choice`,
  `rate_of_fire`, `unjam`, `escalating_use` (MASC / supercharger / radical,
  `equipment_systems.use_escalating`; default = Daniel's cycle, results
  unchanged). Ammo: `parse_bin` returns (weapon, munition, kind); LB-X
  cluster / ATM ER-HE / MML bins now feed their weapons; " - Half" bins hold
  half; `take` draws a chosen kind. Data: IS machine gun (p.248) and IS MG
  ammo rows added - IS machine guns never fired; "(Split)" crit lines are
  read. `heat.max_weapon_heat` counts full rapid fire. Tests:
  `tests/test_fire_modes.py` (10 checks), `test_ams` / `test_electronics`
  moved to the Planner API. New reference battles
  `Cataphract_CTF-3D_vs_Emperor_EMP-6D_seed1.txt`,
  `Akuma_AKU-2XK_vs_Highlander_IIC_2_seed1.txt` (units copied into `data/`).
  Reference logs regenerated: outcomes unchanged except where these rules
  act; the rest only log text (stub lines, the summary banner, split heavy
  Gauss now one weapon that can't fire yet). Benchmark unchanged (458 / 466).

- **2026-10-20 (Claude):** Weapon slot counts (review F16). equipment.json
  listed many multi-slot weapons with too few slots (every Ultra / Rotary /
  LB-X AC, ATM, MRM, MML, Streak LRM, heavy / VSP / X-pulse lasers, HAG,
  heavy Gauss...) and some Clan ones with the IS count (Clan ER large laser,
  ER PPC, LRMs, SRM 6). The parser groups crit lines by that count, so a
  5-slot Ultra AC/5 became five Ultra AC/5s and two adjacent Clan ER large
  lasers one. 103 rows fixed from the Core tables (pp.248-254, cited per
  row), 11 non-Core rows from the MegaMek files' crit-line runs; 1,893 of
  4,162 units had a wrong weapon count. `mtf_parser._join_split_items`: a
  weapon split between two locations is one item.

- **2026-10-20 (Claude):** Artemis, Narc and ECM (Daniel: "Artemis and Narc.
  Since they both affect Missiles and are affected by ECM in similar ways";
  review F11-F13). New `INTEGRATION__electronics.py`: Artemis IV / V FCS
  linked to launchers (p.197: +2 Cluster; V -1 to hit, +3; needs the
  matching Artemis-equipped missiles; ATM built-in +2, p.186); Narc / iNarc
  beacons (pp.188, 193: homing pods by location roll, working from the next
  phase, -1 / +2 for Narc-capable missiles, lost with the location;
  explosive pods 4 / 6); ECM (p.200: an enemy's working Guardian / Clan /
  Angel / Watchdog blocks Artemis and the pods; Angel unlocks Streaks;
  off when shut down or with a stealth system other than the LPS, p.209;
  stealth armor / Void-Signature jam their own mech's Artemis, pp.202, 209).
  `FireControl` per shot (`DeclaredAttack.fire`) carries the munition and
  bonuses into to-hit (`tn_adjuster`), resolution, the AMS (`ams.
  expected_damage_engaged` / `damage_factors` take it) and movement scoring
  (`MoveEvaluator` - same factors). Pod value per Daniel (Section 6, readings
  in Section 4); AMS engages pods for half of it. **Ammo-bin fix** (F10):
  `ammo.parse_bin` reads the munition off the bin name and finds the weapon
  via the bin's equipment.json ammo row - 1,541 units had bins that fed
  nothing (Gauss, AC/x, Artemis- / Narc-capable, Narc pods), so those
  weapons never fired; half-ton "(100)" bins hold their own count;
  `ammo.take` draws a chosen munition. `weapon_selection` gains
  `bonus_per_hit` (the beacon's worth). Data fixes (equipment.json):
  Narc / iNarc beacons damage 0 (was null, so they never fired), IS Narc 2
  slots, iNarc 3, Artemis V 2, Guardian / Angel / Watchdog 2 (p.250-254;
  each 2-slot item had parsed as two). `tests/test_equipment.py` updated
  (one Guardian instance, not two). New `tests/test_electronics.py` (10
  checks); new reference battles `Kintaro_KTO-19_vs_Atlas_AS7-K_seed2.txt`
  and `Atlas_AS7-S2_vs_Kintaro_KTO-19_seed1.txt` (units copied into
  `data/`). Reference logs regenerated: the Atlas AS7-K battle changed for
  real (its Gauss rifle fires now and it wins); the Asymptote logs only by
  the summary banner's known-missing-rules text. Benchmark unchanged
  (458 / 466).

- **2026-10-20 (Claude):** Anti-Missile Systems (Core p.206; review G13 ->
  F9), Daniel: "AMS functionality will be implemented". New
  `INTEGRATION__ams.py`: once both sides have declared, each defender's live
  AMS engage the missile (Type M) hits on it from inside their location's
  firing arc (INTEGRATION__arcs, with the declared twist / flip), at most 2
  per AMS per turn, one AMS per attack; 1 ammo + 1 heat each (laser AMS: no
  ammo, 7 heat IS / 5 Clan), the heat added to the defender's weapon heat;
  not while shut down (p.104) or with the whole crew unconscious.
  Resolution (`attack_resolution._resolve_one_attack`, `DeclaredAttack.ams`):
  the Cluster roll takes -4 on top of the weapon's own modifier and a
  result below 2 destroys every missile; an engaged Streak counts as a 7; a
  single missile (Thunderbolt) is destroyed on 1D6 4+. An AMS no longer
  fires as a 2-damage, range-1 weapon (`weapon_selection` leaves it off the
  table; the closing fallback and the prone prop-arm choice ignore it).
  Expected damage: `ams.damage_factors` (value_scale) in the Ranged-phase
  weapon choice and in `ranged_combat.MoveEvaluator` (scorers and best-twist
  memos keyed by the engagements the other side's AMS can make from that
  spot - `ams.Coverage`). Bot choices in Section 6; readings for Daniel in
  Section 4 ("AMS readings"); new knob `config.AMS_HEAT_LIMIT` (13). Data
  fix: equipment.json IS laser AMS takes 2 critical slots (p.250), not 1 -
  units with one had two separate laser AMS. New `tests/test_ams.py` (10
  checks); new reference battle `Atlas_AS7-K_vs_Archer_ARC-2R_seed2.txt`
  (both units copied from `data/meks.zip` into `data/`). The other reference
  logs and the benchmark (458 / 466) are unchanged - none of those mechs
  carries an AMS.

- **2026-10-20 (Claude):** Rules review, first pass complete
  (`INTEGRATION__RULES_REVIEW.md`: Playing the Game, the rest of Combat,
  Weapons and Equipment, The Battlefield). Fixed: an autocannon's first
  critical hit no longer destroys it (Core p.183; `damage_resolution.
  is_autocannon` / `_autocannon_shrugs_off` - the slot is used up, a second
  crit to another slot destroys it); internal explosions (p.96) - ammo bins
  now carry the UNCAPPED base damage (`INTEGRATION__ammo._update_explosion`,
  shots x Damage Value), and `apply_explosion` applies the 20 cap, strips the
  armor (torso: rear) of the location that took the 20th point when the base
  was over 20, vents CASE / CASE II excess into the (rear) armor up to 10, and
  gives CASE II's explosion crit checks -1. New gaps listed: AMS (G13),
  armored components (G14), ECM (G15). Tests: `test_rules.py`
  (autocannon_first_critical, explosions_and_case; ammunition updated).
  Reference logs regenerated (explosion log wording and the uncapped base
  damage in the log line; no battle outcome changed).

- **2026-10-20 (Claude):** Daniel's calls on rules review D1-D7 (Section 5).
  New OPTIONAL RULES section in `INTEGRATION__config.py`:
  `FLOATING_CRITICALS` (default True; False = the standard Through-Armor
  Critical, Core p.91: damage stays on the torso the 2 hit, plus one crit
  check there, following the damage transfer if that torso is gone) and
  `FIGHT_TO_THE_DEATH` (default False = Daniel's rule, a mech rendered
  immobile for good - destroyed gyro, both legs - is destroyed; True = rules
  as written: a destroyed gyro falls and can't stand (p.98), both legs gone
  is immobile (pp.49, 90; `mech_state.is_immobile` now includes it), and an
  immobile mech with no ranged weapons is destroyed (p.99); a prone mech that
  can't stand turns toward the enemy - `orchestrator._turn_while_down`, one
  hexside a turn with a destroyed gyro). Rules as written now
  (`mechsim/piloting_rolls.py`): one PSR per trigger at the sum of all the
  phase's modifiers, stopping at the first failure, one per leg (p.110;
  `roll_psrs`, `movement_psr_count` - movement scoring prices 1 - P^rolls);
  seatbelt check at Piloting + levels fallen only, automatic hit when
  immobile or over 12 (p.117); falls roll 1D6 for the side, 1 = rear (p.115).
  `resolve_fall` lost its `seatbelt_modifier` argument; `can_stand` (pp.51,
  98). Tests in `tests/test_rules.py` (5 checks). RESULT CHANGE: two
  reference logs regenerated (falls).

- **2026-10-20 (Claude):** Backward walking (Core pp.45-46, TMM p.63;
  rules review G1). `pathfinder.build_movement_table(backward_mp=...)`: a
  walking mech may step into the hex directly behind it, facing unchanged,
  same entry cost; a path that has moved backward never spends more than
  Walking MP (only walking mechs move backward); the forward count (TMM)
  restarts at 1 when the mech reverses direction. The search state carries
  (last direction, moved backward yet); without backward_mp the table is
  exactly as before. `ranged_combat.movement_options(backward=True)` passes
  Walking MP (not after standing up, not when entering the board); the charge
  index uses forward-only states. Same-level backward steps only - a backward
  level change needs a mid-move PSR the scoring can't price yet (review G11).
  The battle log marks moves that need a backward step (VERBOSE only). Test 9
  in `tests/test_pathfinder.py`. RESULT CHANGE: reference logs regenerated.
  Benchmark 17.1 s (the Asymptote gains ~30 end states at Walking MP 3).

- **2026-10-20 (Claude):** Rules review, first pass - new
  `INTEGRATION__RULES_REVIEW.md` (Core Rulebook vs code: fixed items, gaps,
  and Core-vs-project-rule questions for Daniel, all page-cited). Fixed: the
  target-in-woods to-hit modifier (+1 light / +2 heavy, Core p.66 / pp.68-69)
  was missing - added to the LOS result in `pathfinder/los.py`, so every attack
  and the movement scoring see it (DFA ignores terrain as before); partial
  cover was stored one step before the trace's last step that aimed shots and
  charges read (always 0); partial cover could come from the attacker's own
  hex at range 1 (p.57); an ordinary leg hit on a target in partial cover now
  strikes the cover (pp.66, 73); a floating-critical re-roll onto the Head now
  costs the pilot a hit (p.117). Tests in `tests/test_rules.py`. RESULT
  CHANGE: all five reference logs regenerated - the woods modifier changes
  where mechs stand (the default board has 30 woods hexes). Benchmark battle
  changed too (HP 458 / 466).

- **2026-10-20 (Claude):** Speed pass 2 (Pile 1 batch loop + Pile 4 movement
  scoring; no rules touched). (1) **Parallel batches**: `run_batch` runs
  `config.WORKERS` battles at once (0 = one per CPU core, the default; 1 = one
  after another; MANUAL_ROLLS always 1). Each battle now has its OWN seed
  (`orchestrator.battle_seed`: battle 1 = SEED, later battles a SeedSequence
  mix of (SEED, battle number)) instead of one dice stream shared by the
  whole batch, so a battle's dice don't depend on which battles ran before
  it. Workers capture their logs and the parent prints them in battle order,
  so the output is byte-identical for any worker count
  (`tests/test_parallel_batch.py`). `BattleResult.seed` records each
  battle's seed (SEED = it, NUM_SIMULATIONS = 1 replays that battle).
  RESULT CHANGE, batches only: battles 2+ of a batch differ from before
  (different dice, same statistics); one-battle runs and every reference log
  are unchanged. 4 cores here: an 8-battle batch went 78 s → 26 s.
  (2) **Memo sharing in `ranged_combat.MoveEvaluator`**: the best-twist memo is
  keyed on the set of arc keys a spot sees (`_ArcClasses`) instead of the
  exact geometry, and heat-limited scorers are shared by every (arc key,
  held weapons) that blocks the same weapons. The knapsack runs went
  246k → 32k on the benchmark. `MovementCandidate` uses slots; the spot-free
  parts of each pre_tn are added once per call. Results identical (reference
  logs match, benchmark HP 460 / 450); benchmark 21.5 s → 16.3 s in this
  container. Also measured: the LOS traces (~15% of a cold benchmark) are
  cached per board for the life of a worker, so they amortize in a batch.
  Language switch deferred (Daniel agreed: get it right in Python first).

- **2026-10-20 (Claude):** Club pick-up switched OFF (`config.CLUB_PICKUP =
  False`, Daniel) - the rules stay; the decision waits for the
  future-capability Memo (Section 6). Section 0 rewritten as a hand-off for a
  new instance; `CLAUDE.md` added (points here); `tests/benchmark_turns.py`
  added (the fixed 10-turn speed benchmark). Two reference logs regenerated
  (Asymptote vs HeatGear seeds 2 and 5: the Asymptote had picked up a tree,
  and holding it changed its later movement scores; it never clubbed).

- **2026-10-20 (Claude):** The remaining physical attacks and anticipation.
  New `INTEGRATION__movement_attacks.py` (target poses, a once-per-decision
  index of the mover's reachable states, charge / DFA options and values incl.
  displacement worth, the gate and scoring - used by the second mover's pick
  AND the first mover's two-ply reply), `INTEGRATION__dfa.py` (pp.79-80:
  Punch-table hit, Kick-table self-damage, landing, p.80 displacement order,
  a miss = 2-level rear fall), pushes in `INTEGRATION__physical.py` (p.83,
  valued by displacement; mutual pushes; prohibited hexes),
  `INTEGRATION__clubs.py` (p.79: trees in woods / jungle, girders in rubble,
  severed limbs left in their hex - `damage_resolution` records
  `severed_limbs`; holding needs both hands / shoulders; club attacks in
  `physical._club_options`, a PSR for the target, a tree breaks after one
  hit, dropped on hand / shoulder damage). `piloting_rolls.resolve_fall`
  takes `side`. `MoveEvaluator.evaluate(physical_reply=False)` for a mech in
  the air. `config.DFA` switches DFAs off. `tests/test_charge.py` became
  `tests/test_special_attacks.py` (20 checks). Default battle ~1.45 s a turn.
  Reference logs regenerated (pushes' threat moves mechs off board edges).

- **2026-10-20 (Claude):** Charge attacks (Core p.78; displacement pp.113-114;
  falls p.115). New `INTEGRATION__charge.py`: who can be charged (standing,
  finished moving or immobile - the second mover's option), the charge states
  (adjacent, facing, MP left to enter; TMM counts the target's hex), the gate
  and score in `movement_selection._charge_pick`, no ranged fire for the
  charger, resolution in the Physical phase (comparative Piloting, partial
  cover ignored, ceil(tons/5 x (TMM+1)) / ceil(target tons/10) in 5-point
  groups, displacement - off board destroyed, 3+ up prohibited, 2+ down an
  automatic fall - then +2 PSRs; cancelled if the target fell / was destroyed
  or TN 13+, a miss if the charger fell). `piloting_rolls.resolve_fall` takes
  `levels` (x(levels+1) damage). `config.CHARGES` switches it off. New
  `tests/test_special_attacks.py` (10 checks; a Charger CGR-1A1 vs Atlas AS7-D battle
  charges). Not modeled: charge PSRs / displacement in the score, the first
  mover anticipating a charge, domino effects, buildings, water, lance /
  spikes / shields.
- **2026-10-20 (Claude):** Physical attacks weighted by their hit table
  (`physical.Worth`, `structure_weight.hit_spread(rolls=)`, `vulnerability`,
  `spread_worth`): a kick at stripped legs or a punch at a thin upper body /
  head counts for more, in movement scoring and the Physical phase.
- **2026-10-20 (Claude):** Speed: 31.7 s -> 11.8 s for the default battle's
  first 10 turns (seed 12345), identical results - the heat-limited scorer
  passes its weapon list / damage table to select_weapons_to_fire, the
  evaluator memoizes the best-twist ranged value, physical scoring collapses
  identical arc actions and stops at the first plan that can't win.
  Physical attacks were NOT folded into the weapon list: profiling showed the
  physical layer at ~20% before / ~4% after these changes, and a combined
  list would need a second to-hit axis (Piloting) in the weapon tables.
- **2026-10-20 (Claude):** `data/meks.zip`: 4,227 MegaMek `.mtf` units (Daniel's
  upload); 4,162 parse (ultralights < 20 t, superheavies, LAMs don't).

- **2026-10-19 (Claude):** Physical attacks in the movement picker and the
  Ranged-phase twist (Daniel: "add physical attacks to the location picker,
  which may affect the ranged phase twist"). Spots next to the enemy now
  score the best arc action x physical plan (punch with one / both arms,
  kick, physical weapon) as ranged fire without that limb's weapons + the
  plan's expected damage, for both the mover and the enemy's reply
  (`ranged_combat._with_physical`, `physical.Planner`). The Ranged phase makes
  the same joint choice, so it twists for a punch and holds back an arm
  weapon worth less than that arm's punch; the Physical phase re-picks after.
  `physical.options_at` / `base_tn` / `plans` take explicit positions.
  Not counted: structure weighting of physical damage, kick PSR falls,
  charges / DFA / pushes / clubs (not built). Reference logs regenerated.

- **2026-10-19 (Claude):** Reference logs regenerated (`--update`, Daniel's
  go-ahead) - they now reflect movement selection, firing arcs and arc actions.

- **2026-10-19 (Claude):** Arc actions - the rest of the torso-twist rules
  (Core pp.61-62, 76, 205, 236-238). `INTEGRATION__arcs.ArcAction(twist, flip,
  turret)` replaces the bare twist: tripods twist to any hexside and their leg
  weapons use the p.236 leg arcs; arms reverse for designs with no hand / lower
  arm actuators in both arms and no split arm weapon; Quad Turret "(T)" weapons
  turn freely, a turret crit locks it; one twist OR flip a turn, kept for the
  rest of the turn and reset in the End Phase. The Physical Attack Phase now
  uses `arcs.arcs_between` with the twist (punches / arm weapons follow it,
  kicks don't, tripods only attack into the torso's forward arc, reversed arms
  can't punch) and may twist there if the Ranged phase didn't.
  `arc_unavailable(attacker, key)` now takes an `arcs.ArcKey`;
  `arc_keys(arcs, facing, actions, legs)` returns (key, action) pairs.
  New `tests/test_arcs.py` (10 checks). Reference logs differ again (the
  default tripods now twist further).

- **2026-10-19 (Claude):** Firing arcs and torso twists (Core pp.60-62), from
  Daniel's Firing Arcs Diagram screenshot. New `INTEGRATION__arcs.py`: the arc
  a target is in = angle of the centre-to-centre line from the attacker's
  facing (forward within 60 deg, side 60-120, rear beyond 120; boundary hexes
  go to the non-rear arc - all 15 hexes labelled on the diagram reproduce).
  **The rear arc is now 120 deg, replacing the 60-deg single-hexside rule of
  2026-07-20** (identical at range 1). Weapons by arc: forward = all but
  rear-mounted; side = that side's arm weapons (split torso/arm weapons are
  forward-only); rear = rear-mounted only. Torso twist (one hexside, none for
  prone/quad): shifts head/torso/arm weapon arcs, not legs, facing or how the
  mech is hit; the attack phase picks the twist with the most expected damage
  (`attacker.torso_twist`), and movement scoring takes each side's best twist.
  `los_cache` now caches the 6-facing arcs tuple (was a direction facing);
  `arc_unavailable(attacker, torso_arc, legs_forward)` replaces the rear-arc
  boolean. Not modeled: reversing arms, tripod leg arcs and any-hexside tripod
  twists, turrets, twist -> Physical Attack Phase. Reference logs differ again.
  Cost: roughly 1.5-2x per turn (~1.1 s) from scoring up to 3 twists per side.
- **2026-10-19 (Claude):** Structure-damage weighting for movement scoring
  (Daniel's design: per weapon x hit-location table, no chaining). New
  `INTEGRATION__structure_weight.py`: for each weapon (cluster weapons per
  grouping), each hit-table roll on the attack side counts the part of a hit
  that gets past armor into structure at `config.MOVEMENT_STRUCTURE_WEIGHT`
  (default 2.0; 1.0 = off, identical to before) and anything transferred past
  a destroyed location at 1.0. `weapon_selection.select_weapons_to_fire` takes
  an optional `value_scale` (used by movement scoring only; the attack phase is
  untouched); `MoveEvaluator` builds per-side multipliers for both mechs, so
  `dealt`/`received` are now WORTH. `_vulnerability` (exposure) shares the
  table walk (`hit_spread`). Exposure and structure weighting overlap a
  little (thin armor raises both); both stay on. 16 tests; ~16 s per battle.
- **2026-10-19 (Claude):** Void-Signature fix to movement selection: its TN
  bonus falls as hexes moved rise (+3 / +2 / +1 / 0), so the Section 5c
  reduction (keep max hexes moved) is unsafe for it. `reduced_options` now
  keeps every (forward count, MP) variant for a mech with a live Void-
  Signature System (Daniel's call); new test. Logged as open (Daniel, not yet
  built): (1) terrain that forces a PSR on entry and mine fields should add
  expected damage to the movement cost like the movement PSR does; (2)
  internal-structure damage should count for more than armor damage in the
  objective (Daniel suggested ~2x, value to be picked).
- **2026-10-19 (Claude):** Movement selection built (replaces
  `stub_select_movement`). New `INTEGRATION__movement_selection.py` and
  `INTEGRATION__los_cache.py` (compute-once LOS / entry-direction / distance
  cache); `ranged_combat` gained `MoveEvaluator` (pinned-position scoring that
  reuses weapon scorers; `evaluate_going_second` is now a wrapper, output
  byte-identical on 5 reference logs before wiring); `piloting_rolls` gained
  `movement_psr_trigger`, `movement_psr_target_number`, `fall_damage`.
  Daniel's decisions: objective = dealt / (received + .001); two-ply so both
  sides move intelligently; closing fallback ported as-is; armor-exposure
  weighting by actual hit direction; movement-phase PSR expected damage added
  to the denominator (damage-caused PSRs ignored); dropping `compute_score`'s
  HP-awareness is fine for now. Known limits: ratio ignores damage state
  (epsilon dominance by tiny-damage/no-return-fire spots), seatbelt/prone PSR
  aftermath unscored, tripod exposure uses the raw hit table, prone/immobile
  enemy modeled as staying put, modeled replies greedy not adversarial.
  New tests in `tests/test_movement_selection.py` (14 checks). ~15 s per
  40-turn battle. Reference logs differ by design - NOT updated.
- **2026-08-28 (Claude):** Consolidated `INTEGRATION__PROJECT_MAP.md` +
  both source projects' project maps/design notes/call graphs/change-record
  archives into this single doc. No code touched.
- **2026-08-30 (Daniel):** Resolved Pile 1 reconciliation — `combat_turn.py`
  / `sim_runner.py` cannibalized into the orchestrator then deleted from
  this project (source projects unaffected).
- **2026-08-30 (Claude):** Built `INTEGRATION__orchestrator.py` skeleton —
  map loading, RNG wiring, config attachment, initiative, Section-2 turn
  loop with Movement/Ranged as stubs, End Phase wired, `run_batch()`.
- **2026-08-31 (Daniel):** Confirmed initiative procedure — both sides
  roll 2d6, both reroll on ties, high roll wins and moves second.
- **2026-08-31 (Claude):** Wired confirmed initiative; wired damage-aware
  MP into `_phase_movement()` via `_compute_available_mp()`.
- **2026-09-02 / 09-05 (Claude):** Movement envelope
  (`_build_movement_envelope`); `INTEGRATION__ranged_combat.evaluate_going_second()`
  (unreduced, unranked candidate list with real weapon tables).
- **2026-10-18 (Daniel):** TMM from actual hexes moved; stub defaults
  approved; loud warnings fine; "hammer out something with the semblance
  of working."
- **2026-10-18 (Claude): first end-to-end run.**
  - Fixed: `INTEGRATION__weapon_selection.py` purge workaround removed (it
    deleted the `config` registration — live-confirmed ImportError).
  - Fixed: `piloting_rolls.py` reads a global `config.PILOTING` that didn't
    exist — `INTEGRATION__config.PILOTING` added; every call wrapped by
    `_with_piloting(mech, fn)` so each mech uses its own skill.
  - Fixed: `INTEGRATION__main.py` imported a non-existent bare `config` —
    now calls `orchestrator.run_batch()`.
  - Fixed: `INTEGRATION__config.py` imported bare `file_picker` — now
    `INTEGRATION__file_picker`.
  - Added headless mech paths (`MECH_RED_MTF`/`MECH_BLUE_MTF`), `SEED`,
    `DATA_DIR` path resolution, STUB SETTINGS block.
  - Added `INTEGRATION__stubs.py` (13 stubs + registry),
    `INTEGRATION__attack_resolution.py` (Ranged Combat with real dice;
    absorbs `sim_runner._resolve_hit`/`resolve_weapon_attack`),
    `INTEGRATION__results.py` (BattleResult moved here + batch summary +
    stub banner), `INTEGRATION__make_run_dir.py` (prefixed files → run layout).
  - Orchestrator: movement phase wired (envelope → stub pick → apply →
    movement PSR → consciousness), Ranged/Physical/Heat/End wired, per-battle
    stub reset and weapon-table cache reset (id(mech) reuse hazard),
    `random.seed(SEED)` for the tripod sub-roll.
  - Tested: Asymptote vs Asymptote (93 turns, Blue engine destroyed),
    Asymptote vs synthetic missile/AC/LB-X/rear-mount test loadout (8 turns,
    and a quiet 5-battle batch). Same seed → byte-identical stdout and
    stderr. Builder round-trip → identical output. Tests ran against
    test copies of the MECHSIM/PATHFINDER files transcribed from this
    Project (logic verbatim, docstrings trimmed) and a test equipment.json
    with the mini DB's stats.
- **2026-10-18 (Daniel):** Heat rules — max_heat is dissipation + the set
  value; movement heat Walk 1 / Run 2 / Jump max(3, hexes, or ceil(hexes/2)
  with Improved JJ); heat is saved state across turns; cooldown logic later.
- **2026-10-18 (Claude):** Wired the heat rules. `weapon_selection.select_weapons_to_fire`
  takes `dissipation`/`movement_heat`, budget = max_heat + dissipation −
  current − movement. `orchestrator`: `movement_heat()`, Improved-JJ
  detection (also matches unparsed crit strings, for the mini DB), real
  `_phase_heat()` accumulation. `stub_heat_phase` + `STUB_HEAT_MODE` replaced
  by `stub_heat_effects` (Heat Scale / engine-hit heat still missing).
  Tested: Asymptote mirror 22 turns (5-laser alphas, heat stays 0 vs 22
  sinks); synthetic mech climbs 0→7→8 and holds at max_heat 8; movement
  heat formula unit-checked; same seed → identical log.
- **2026-10-18 (Daniel):** Movement scoring should be heat-aware.
- **2026-10-18 (Claude):** `INTEGRATION__ranged_combat.evaluate_going_second`
  now scores each spot's dealt/received with `select_weapons_to_fire` (the
  same heat-limited pick Ranged Combat uses), with the spot's own movement
  heat in the mover's budget and the defender's movement heat in its
  return-fire budget; memoized per call. Was: sum over all in-range weapons
  (alpha assumption). New `INTEGRATION__heat.py` holds movement heat,
  Improved-JJ detection and the budget formula (moved out of the
  orchestrator to avoid a circular import). Tested: for every second mover
  (opponent's position final) the pick's expected damage equals what the
  combat phase then fires — 22/22 turns mirror, 7/7 synthetic; a 3-heat
  jump under a 19-heat budget scores 4 lasers (14.00) instead of 5 (17.50).
- **2026-10-19 (Daniel):** Moved the project to GitHub
  (`Logajam/battletech-monte-carlo-sim`). Retire the prefixed
  PATHFINDER/MECHSIM source files except ones that still hold context for
  useful features.
- **2026-10-19 (Claude):** Repo laid out as the run folder (the one
  `make_run_dir.py` used to build). `INTEGRATION__make_run_dir.py` removed:
  nothing left to convert. Prefixed `MECHSIM__*`/`PATHFINDER__*` copies
  retired; the live modules are `mechsim/` and `pathfinder/`. Reference
  files stay in the claude.ai Project, not the repo (Daniel):
  `PATHFINDER__combat_turn.py` (two-ply look-ahead, closing fallback),
  `PATHFINDER__report.py` / `terrain_colors.py` / `MECHSIM__sim_runner.py`'s
  record-sheet printing (output/visual helpers, for a future GUI shell),
  `PATHFINDER__validation.py` (test suite for the pathfinder modules;
  imports an absent `simulate`). Verified: a run from the repo
  matches `reference_logs/Asymptote_vs_Asymptote_seed12345.txt`
  except for file paths, stdout and stderr both.
- **2026-10-19 (Claude):** From Daniel's `battletech-monte-carlo.zip`
  (a parallel repo package, all code identical to this repo): added
  `data/BigBlank.board` (50x50, parses), `requirements.txt`, its
  `.gitignore`, and its sample logs, which use repo-relative paths and name
  the settings (`Asymptote_vs_Synthetic_maxheat8_seed777.txt` = Asymptote vs
  TEST_Synthetic_Loadout, max_heat 8, seed 777). Its README, docs and
  `make_run_dir.py` not taken.
- **2026-10-19 (Claude):** `PATHFINDER__validation.py` rebuilt as
  `tests/test_pathfinder.py` (Daniel asked). Same tests and expected
  values; paths point at `pathfinder/` and `data/`; old test 5 removed (it
  needed the absent `simulate.py`, whose import blocked every test); runs
  all tests and exits non-zero on any failure. Result: 8/8 pass. Sanity
  check: setting heavy-woods cost to 3 in a scratch copy fails test 7.
- **2026-10-19 (Daniel):** Full equipment DB goes in the repo, replacing the
  14-entry mini.
- **2026-10-19 (Claude):** `mechsim/equipment.json` replaced with the full DB.
  The mini's 14 entries have identical stats in it (only alias lists grew).
  Effect on the reference battles: Asymptote mirror now records jump-jet
  crits as "jump MP reduced (now 4)" and Endo Steel crit slots as real
  components - still 22 turns, Red wins; Synthetic battle unchanged except
  the "unrecognized component" notes are gone. Both reference logs
  regenerated. Added `tests/check_reference_logs.py` (re-runs both
  reference battles and compares; `--update` rewrites them) so the check
  works on Windows without diff tools.
- **2026-10-19 (Daniel):** Fill the equipment DB's missing weapon stats from
  his rulebook table rips (Total Warfare, Tactical Operations: AUE,
  Interstellar Operations).
- **2026-10-19 (Claude):** Rulebook fill pass on `mechsim/equipment.json`.
  Parsed all three tables; matched entries by canonical name/aliases + tech
  base; validated against already-filled entries first (368/372 values
  agree). Filled only null fields: 210 fields across 103 weapons
  (damage_type 95, damage 38, range 38, heat 36, rack_size 7); every
  changed entry's `notes` names the table row. One correction: Extended LRM
  5/10/15/20 range 7/14/21 -> 12/22/38 (the old value was inherited from the
  LRM base class and marked "Not confirmed"; TO:AUE says 12/22/38). Clan
  Heavy MG range set 1/2/2, following the IS Heavy MG entry's existing
  long = medium convention for "no long range". `verified` flags unchanged.
  Effect: Asymptote mirror unchanged; Synthetic battle now fires its LB
  10-X AC and ends turn 4 (was 8); its reference log regenerated.
- **2026-10-19 (Daniel):** One-shot launchers: thought removed from the JSON
  (they aren't - 41 OS/IOS entries are present); add their stats someday.
  Missing minimum range is a problem that needs to be corrected.
- **2026-10-19 (Claude):** Added `range.min` to 170 weapon entries from the
  rulebook tables: 161 by name match whose short/medium/long equal the
  table row exactly, 7 more by word-order match under the same equal-range
  check, plus both Heavy MGs (row has no long range; min cell 0). A dash in
  the min cell (7 rows) is stored as 0. No other field changed; battles are
  unchanged because nothing reads `range.min` yet.
- **2026-10-19 (Daniel):** Confirmed the minimum-range rule ((min - range) + 1
  per hex inside), missing minimum = 0, and OS launchers = base launcher's
  range/damage stats with a fire-once limit.
- **2026-10-19 (Claude):** Minimum-range penalty wired into
  `weapon_selection._weapon_range_mod` (so both weapon selection's
  expected-damage table and the to-hit roll use it). New
  `tests/test_weapon_range.py` (15 cases). 45 OS/I-OS entries given their
  base launcher's damage_type/damage/heat/range/rack_size where null
  (150+ fields; no existing OS value disagreed with its base); 204/279
  weapons can now fire. New `stub_one_shot` (replaces the ammo stub for
  one-shots) warns each time one fires. Summary banner: min-range line
  removed, LB-X line updated. Effect: Asymptote mirror unchanged except the
  banner; Synthetic battle now ends turn 7 (its LRM 15 takes +1 at range 6
  and is dropped for a laser at range 1; UAC/5 and AC/5 take +2/+3 at range
  1). Both reference logs regenerated.
- **2026-10-19 (Daniel):** "Get heat fully wired in", from his rules index
  (`Battletech Rule Reference Index`, Core Rulebook Heat chapter pp.102-107;
  errata v0.1 has no heat entries).
- **2026-10-19 (Claude):** Heat Scale wired; `stub_heat_effects` removed.
  - `INTEGRATION__heat.py`: Heat Data Table (p.103), engine-hit heat
    (+5 / +10 total, none while shut down), XXL and super-cooled-myomer
    movement heat (p.102), and `resolve_heat_phase()` in the book's order:
    adjust scale (Overflow kept) → shutdown roll (14: 4+ … 26: 10+,
    automatic at 30, no override with an unconscious MechWarrior) or, for a
    mech already shut down, restart (automatic below 14, roll otherwise,
    never at 30+) → ammo-explosion roll at 19/23/28 (4+/6+/8+; bin with the
    highest damage value per turn of shots explodes, Gauss/one-shots never)
    → life-support MechWarrior hits (1 at 10-19, 2 at 20+) → next turn's
    MP penalty (5/10/15/20/25) and ranged to-hit modifier (8/13/17/24).
  - Shut-down mechs: skip movement, don't fire, give attackers the -4
    immobile modifier, auto-fail standing PSRs (`piloting_rolls`), no engine
    or weapon heat; sinks keep working.
  - MECHSIM edits: `mech_state` gains `shutdown`/`heat_mp_penalty`/
    `heat_fire_modifier`/`myomer` and `is_immobile()`; `compute_walk_mp`
    subtracts the heat penalty after the damage floor (may reach 0, p.104);
    Hardened running floor skipped at 0 MP; `compute_heat_dissipation` adds
    +3 for a working Partial Wing (p.103). `mtf_parser` reads `Myomer:`.
  - **Claude's reading, for Daniel to confirm:** engine-hit heat comes out
    of the weapon heat budget (`select_weapons_to_fire(engine_heat=...)`),
    so max_heat still caps the end-of-turn level. Shutdown override /
    restart use the "pilot" crew role's consciousness (multi-crew mechs).
  - Side effect of the immobile rule: movement scoring
    (`ranged_combat.evaluate_going_second`) now scores an unconscious
    defender at the -4 immobile TMM, matching the combat phase (it used
    actual hexes moved before).
  - New `stub_heat_explosion_bin` (shots-left tie-break needs shot counts;
    controller's choice is random). New `tests/test_heat.py` (14 checks,
    scripted dice; fails when a threshold or the shut-down engine-heat rule
    is broken). New reference battle
    `Asymptote_vs_Synthetic_maxheat30_seed2.txt` (shutdown, heat ammo
    explosion, auto-failed PSR while shut down, automatic restart).
  - Effect: Asymptote mirror diverges at turn 8, right after Blue's first
    engine hit (+5 heat a turn, later +10, cutting its fire and giving it
    -1 MP / +1 to-hit at times); now 18 turns (was 22), Red still wins.
    Synthetic (max_heat 8) diverges at turn 2 (heat 5 after turn 1 -> -1
    Walking MP; at 8 it fires at +1); now ends turn 8 (was 7). Both
    regenerated. 300 quiet battles at max_heat 30: no crashes.
- **2026-10-19 (Daniel):** Engine-hit heat confirmed (charged in the Heat
  Phase of the turn the hit lands, then budgeted). Heat work goes straight
  to `main` - QC later, once he starts playing with it. Add stealth, coolant
  pods, radical heat sinks, inferno extra rolls, TSM, torso-mounted cockpit
  life support, aimed shots at shut-down mechs, MASC, superchargers, and
  End Phase heat-sink switching; player choices default on (radical/MASC/
  supercharger: 1 turn on, 1 off); TSM via min_heat 9.
- **2026-10-19 (Claude):** Heat equipment wired.
  - New `INTEGRATION__equipment_systems.py`: equipment detection by crit
    name, Escalating Failure (p.180, consecutive-turn count steps back on an
    unused turn), the on/off cycle, stealth systems (heat, +1/+2 medium/long,
    Void-Signature by hexes moved and +1 to its own attacks, ECM needed for
    stealth armor and Void), coolant pods (used pods stop being explosive),
    radical heat sink state, MASC/supercharger (Running MP x2 / x2.5,
    failure crits after moving: MASC to one random leg via the Kick table,
    never transferring; supercharger to the top centre-torso Engine slots,
    and destroyed), TSM activation.
  - `INTEGRATION__heat.py`: stealth heat; extra cooling at the start of the
    Heat Phase (radical on cycle turns, else a coolant pod); destroyed
    radical +1 movement / +1 firing heat; inferno bins roll the p.192 table
    separately and an inferno explosion's +30 heat re-triggers any newly
    crossed shutdown / ammo / inferno rolls; torso-cockpit life support
    (1-14: 1 hit, 15+: 2); TSM effect; `choose_heat_sink_deactivation`
    (End Phase, also at deployment). Weapon budget uses `other_heat` =
    engine + stealth + radical surcharge - planned radical cooling.
  - `weapon_selection`: `other_heat` replaces `engine_heat`; per-weapon
    `tn_adjust` (stealth range bonus, aimed shots); `range_bracket()`;
    min_heat is now the end-of-turn floor (no padding when it's 0).
  - `attack_resolution`: stealth TN terms, aimed shots (p.70: no cluster
    weapons; head +7 vs the -4; partial cover not applied and legs behind it
    rerolled; 1D6 4+), radical weapon surcharge. `ranged_combat` scores
    moves with the same terms.
  - MECHSIM: `mech_state` gains `tsm_active`, `deactivated_heat_sinks`,
    `run_mp_multiplier`, `heat_sink_rate()`/`working_heat_sinks()`/
    `active_heat_sinks()`; `mtf_parser` keeps the Cockpit:/Armor: header
    text and maps "Stealth" armor to Standard (no damage-math change).
  - `equipment.json`: `coolantpod` was category "ammo" (so it would have
    been a heat-explosion candidate with the 20-point ammo default) - now
    misc, 2-point explosion (p.208).
  - **Claude's readings, for Daniel to confirm:** the p.192 inferno text says
    rolls "at 19, 23, and 28" but its table starts at 10 - the table is
    used. Inferno heat is always the 30 cap (bins are never empty).
    Coolant pods / radical heat sinks don't work while shut down (p.104's
    "activated equipment" rule). Radical cooling on an on-turn is counted
    in the weapon budget; coolant pods aren't (used only when needed).
    ECM suites, like MASC, are one system however many slots they parse to.
  - New `data/TEST_Heat_Gear.mtf` (every new system on one mech), new
    `tests/test_equipment.py` (12 checks, scripted dice; catches broken
    escalating / TSM / inferno / Void / MASC values), two new reference
    battles (`Asymptote_vs_HeatGear_seed5`, `..._maxheat30_seed2`). The three
    older reference battles: log wording changed ("other" heat), and the
    maxheat30 battle now has aimed shots at the shut-down synthetic mech
    (ends turn 7, was 8). 300 quiet gear-mech battles: no crashes; failed
    escalating rolls ~1 in 36 as the 3+ table predicts.
- **2026-10-19 (Daniel):** Engine-hit heat confirmed. "Search for stubs
  that have answers in the rules and correct them." Keep files up to date
  (commit to main as I go).
- **2026-10-19 (Claude):** Every stub with a rules answer replaced, from
  the Core Rulebook (one commit per batch on main):
  - Attack direction (p.73): hexside the LOS enters, read against the
    target's facing (`attack_resolution.attack_side`).
  - Cluster groupings (pp.87, 181): SRM 2, LRM/MRM 5, ATM 6, default 5;
    Streaks hit with every missile, no heat or ammo on a miss (p.187); MRM
    cluster rolls -1 (p.186). New `INTEGRATION__weapon_rules.py`.
  - Standing up (p.51): free facing, remaining MP spent normally (Run).
  - Walking never forces a PSR; running only after 1+ hex (p.111).
  - To-hit (pp.66-67, 97-98, 184-200): per-weapon modifiers (pulse -2,
    ER pulse -1, X-pulse -2, VSP, heavy +1, re-engineered -1, silver bullet
    -1, RL +1, M-pod -1), targeting computer -1, shoulder +4 / upper arm +1,
    sensors (+2 / no fire; torso cockpit +2/+4/none), prone target -2/+1,
    prone attacker +2 with a prop arm (tripod/quad p.231).
  - Rear-mounted weapons (p.60): parser keeps "(R)"; only they fire into
    the rear arc, and only there. Side arcs and torso twists: see Change Record
    2026-10-19 (`INTEGRATION__arcs.py`).
  - Ammunition (pp.72-73, 95-96, 180-182): shots_per_ton from the Core
    tables (107 weapons; 125 heat values cross-checked, all agree), bins
    linked by exact ammo type, one shot per firing, fewest-shots bin first,
    empty bins don't fire or explode, explosion = shots x damage capped 20,
    one-shots and rocket launchers fire once, heat-explosion tie-break on
    shots left, real inferno heat. Inferno bins aren't fired from. New
    `INTEGRATION__ammo.py`.
  - Weapon data (pp.248-254): 62 null fields filled (types, ATM stats,
    heat/range); 209/279 weapons can fire (was 204).
  - Deployment (p.37): deployment roll, home edges, entry on turn 1.
  - Physical attacks (pp.76-83): punches, kicks, physical weapons, TSM and
    talons; kick PSRs via `resolve_attack_phase_psr(forced_triggers=...)`.
    New `INTEGRATION__physical.py`.
  - New `tests/test_rules.py` (11 checks). All five reference battles
    regenerated after each batch (results change: real attack direction,
    pulse -2, ammo limits, home-edge starts, punches).
  - Effects worth knowing: the synthetic test mech carries no LB-X or Ultra
    AC ammo, so those never fire now; the IS Machine Gun has no
    equipment.json entry at all (only Light/Heavy/Clan MGs).
  - Open for Daniel: Core-vs-MECHSIM PSR differences and the firing-arc
    diagram (Section 4).
- **2026-10-19 (Claude):** Added the rules library zip to the repo as
  `rules/Battletech_Rule_Reference_Index.zip` so later sessions can read it.
