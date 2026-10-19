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

## 0. WHERE WE ARE (2026-10-19) — read this first

**It runs end to end.** `.mtf` in → turn-by-turn battle on a real board →
batch summary out. Every phase does something. Everything that isn't a real
rule yet is a **loud, counted stub** (`INTEGRATION__stubs.py`): it prints
`STUB: <name> - ...` to stderr every time it runs, and the batch summary
opens and closes with a banner listing which stubs ran and how often.

**How to run** (the GitHub repo is already laid out as a run folder,
since 2026-10-19):
```
git clone https://github.com/Logajam/battletech-monte-carlo-sim
cd battletech-monte-carlo-sim
python INTEGRATION__main.py
```
Needs Python 3 and NumPy (`pip install -r requirements.txt`). Layout: `INTEGRATION__*.py` at the top,
`mechsim/` and `pathfinder/` hold the source-project modules the battle
loop imports (un-prefixed names), `data/` holds `.board` and `.mtf` files,
`reference_logs/` holds same-seed sample logs to diff against (the
file name gives the matchup and settings).
Settings (mech files, board, seed, batch size, every stub knob) are all in
`INTEGRATION__config.py`. Default: Asymptote II vs Asymptote II on
16x17 Grassland, seed 12345, 1 battle, verbose, home-edge deployment.

**What a battle looks like right now:** both mechs enter from opposite
home edges and pick each turn's spot with `INTEGRATION__movement_selection`
(2026-10-19: damage dealt / damage received, two-ply - see Section 5);
adjacent mechs punch or kick in the Physical Attack Phase.

**Heat is fully wired (2026-10-19)** from the Core Rulebook Heat chapter
(pp.102-107): engine-hit heat, Heat Scale MP and to-hit penalties,
shutdown/restart, heat ammo explosions, life-support pilot hits. See
`INTEGRATION__heat.py`'s docstring for the rule list with page cites.
**Heat equipment too (2026-10-19):** stealth systems, coolant pods, radical
heat sinks, inferno ammo rolls, TSM, torso-mounted cockpit life support,
MASC, superchargers, End Phase heat-sink switching and aimed shots at
immobile targets - `INTEGRATION__equipment_systems.py`, with Daniel's
default player choices (Section 5).

**Stubs with rule answers were replaced 2026-10-19** (attack direction,
cluster groupings, post-stand-up movement, walking PSRs, to-hit modifiers,
rear-mounted weapons, ammunition and one-shots, deployment, punches/kicks/
physical weapons). What's left is bot decisions and data gaps:
1. `ammo_data` / `unconfirmed_weapon_data` / `unknown_damage_type` — weapons
   whose stats aren't in the Core tables.
2. `heat_explosion_bin` — the controller's choice among tied bins.
(`movement_selection` stopped being a stub 2026-10-19.)

**Picking up from here (2026-10-19):** movement selection is wired and
passes `tests/test_movement_selection.py`. The reference logs now DIFFER from
`main` on purpose (movement changed every battle) - Daniel reviews fresh
logs, then `check_reference_logs.py --update`. Waiting on Daniel: the
Core-vs-MECHSIM PSR questions and the firing-arc diagram (Section 4). Rules are checked
against `rules/Battletech_Rule_Reference_Index.zip` (Section 7). Most
recent work and its page cites: Change Record, last entries.

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
| Physical Combat | `INTEGRATION__physical.run_physical_phase()` | **REAL (Core pp.76-83):** punches, kicks, physical weapons; bot picks the most expected damage. Charges, DFA, pushes, clubs not built. |
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

**Stubs (all in `INTEGRATION__stubs.py`, knobs in `INTEGRATION__config.py` STUB SETTINGS).**
Each docstring carries a TODO naming what to check (MegaMek names in those
TODOs are from memory — grep before relying on them).

| Stub | What it does instead | Needs |
|---|---|---|
| `unknown_damage_type` | null damage_type → BALLISTIC | equipment.json curation (weapons not in the Core tables) |
| `unconfirmed_weapon_data` | Loud warning; weapon never fires | equipment.json curation - special-rules weapons (MG arrays, TAG, AMS, SRTs, HAG damage, MML modes, plasma, VSP damage...) |
| `ammo_data` | Unlimited ammo for a weapon with no shots_per_ton (HVAC, Improved AC - not in the Core tables) | shots_per_ton from Tactical Operations tables |
| `heat_explosion_bin` | Heat ammo explosion: bins still tied on damage value AND shots left picked at random; unknown-damage bins count as 0 | A controller policy (pile 4) |

Replaced by Core Rulebook rules 2026-10-19 (Change Record): `attack_direction`
(p.73), `cluster_grouping` (pp.87, 181), `post_standup_movement` (p.51),
`walk_movement_psr` (p.111), `to_hit_modifiers_not_applied` (pp.66-67, 97-98,
184-200), `rear_mounted_weapons` (p.60), `ammo` / `one_shot` (pp.72-73, 95,
180-182), `deployment` (p.37), `physical_combat` (pp.76-83, partly).

**Rules gaps with no runtime flag** (also printed in every summary):
side firing arcs for torso weapons and torso twists (needs the p.60 Firing
Arcs Diagram - not in the rules rip); LB-X/Ultra/Rotary multi-shot math;
Artemis/HAG/ammo variants; heat sources with no terrain model yet (water,
snow, fire, extreme temperatures) and inferno missiles (bins aren't fired
from); heat decisions (cooldown, voluntary shutdown); stealth armor /
Void-Signature hostile-ECM side effects; torso-mounted cockpit PSR/sensor
rules; charges, DFA, pushes, clubs; jumping onto the board at deployment;
tripod leg sub-roll uses Python `random` (seeded from SEED, not the
BattleRNG stream).

**Core Rulebook vs existing MECHSIM rules - Daniel to decide** (found
2026-10-19 while replacing stubs; MECHSIM left unchanged because these are
confirmed project rules, not stubs):
- Standing up (p.51, PSR table p.111): each attempt is a PSR at -1;
  `resolve_stand_up` uses no -1.
- Tripod with no leg destroyed: -1 to PSRs (p.111); MECHSIM uses -2.
- Preexisting leg destroyed: +4 (p.111, "jumped with leg destroyed +4");
  MECHSIM uses +5.
- Quads only need a PSR to stand if a leg is destroyed (p.231).
- Rear arc: the project's confirmed rule is one hexside (60 degrees); the
  Core diagram's wedge sizes can't be read from the rip, so not checked.

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
- Physical attacks beyond punches/kicks/physical weapons: charges, DFA,
  pushes, clubs (built 2026-10-19: `INTEGRATION__physical.py`).
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
  no confirmed rule); bridge cost/elevation rules (`ValueError` on any
  bridge feature, unconfirmed); elevation cap on single-step movement
  (unenforced); LOS rule-6 tie-break is a placeholder pending a real
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

## 5. DECISIONS LOG (Daniel's calls — implementation may not override)

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
  results, keeps its knobs in config. Defaults: movement `max_dealt`, hit
  table `mechsim_random`.

---

## 6. PILE 4 — DECISION-MAKING INDEX (cross-cutting, not a module)

| Decision point | Lives in | Decides |
|---|---|---|
| Movement selection | `INTEGRATION__movement_selection.choose` | Spot (hex + facing + mode) maximizing dealt×exposure / (received×exposure + movement-PSR cost + .001); first mover scores each spot by the second mover's modeled reply (two-ply). Knobs: config MOVEMENT SETTINGS. |
| Movement-PSR cost | `movement_selection.psr_costs` | P(fail) × fall damage, only for Run / Jump with a Movement-Phase PSR trigger; damage-caused PSRs ignored (Daniel) |
| Armor-exposure weighting | `movement_selection.exposure_factors` | Per-side vulnerability from current armor + structure (front = 1.0, clamped) |
| No-LOS / out-of-range movement fallback | `movement_selection.closing_fallback` | Ported as-is from `combat_turn._closing_fallback` (cases A/B1/B2); nearest-to-enemy otherwise |
| Heat-constrained weapon selection | `INTEGRATION__weapon_selection.py` | Which weapons fire this turn, built and wired |
| Heat ammo explosion bin (controller's choice) | `INTEGRATION__stubs.stub_heat_explosion_bin` | **STUB.** Which of several equally destructive, equally full bins explodes (random). |
| Ammo bin to draw from | `INTEGRATION__ammo.spend` | The bin with the fewest shots left (empties bins sooner) |
| Prop arm when firing prone | `INTEGRATION__attack_resolution.prone_fire` | The arm whose weapons matter least |
| Physical attack type | `INTEGRATION__physical.choose_attack` | Punch / kick / physical weapon with the most expected damage |
| Home edge | `config.HOME_EDGE_CHOICE` | Which edge the deployment-roll loser picks (default random) |
| Escalating Failure use (radical heat sinks, MASC, supercharger) | `INTEGRATION__equipment_systems.cycle_on` | 1-turn-on / 1-turn-off cycle (Daniel's default) |
| Coolant pod trigger | `INTEGRATION__heat._extra_cooling` | One pod when heat would stay above min_heat, not on a radical turn |
| Heat-sink switching | `INTEGRATION__heat.choose_heat_sink_deactivation` | End Phase: how many sinks stay on so min_heat can be reached |
| Aimed shot location | `config.AIMED_SHOT_LOCATION` | Where shots at immobile targets aim (default Center Torso) |
| Candidate reduction | `movement_selection.reduced_options` | Max FC (min MP) per (hex, facing, mode, fc>0); Void-Signature exempt |
| Best-reply selection | `movement_selection._modeled_reply` | Wired (two-ply) |
| `compute_score()` | `PATHFINDER__combat.py` | Not wired (reference; built on flat HP/weapon dicts) |
| LOS rule-6 tie-break | `PATHFINDER__los.py` | Placeholder, see Known Issues #2 |
| Closing-turn detection | `movement_selection.closing_fallback` | Wired (ported) |

---

## 7. STANDING PROMPTS

- Don't write/run code without explicit instruction. "Compile" (or a
  clear equivalent — "go ahead," "do it") triggers execution; ask only
  on genuine scope ambiguity.
- State test scope up front; one pass; don't iterate unless asked.
- Never hardcode a BT numeric rule from memory — confirm with Daniel first.
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

---

## 8. CHANGE RECORD

*(Starts fresh 2026-08-28 — prior history archived/removed, not carried forward.)*

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
    the rear arc, and only there. Side arcs NOT applied (diagram needed).
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
