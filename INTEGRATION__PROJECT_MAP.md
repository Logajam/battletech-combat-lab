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

## 0. WHERE WE ARE (2026-10-18) — read this first

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
Needs Python 3 and NumPy. Layout: `INTEGRATION__*.py` at the top,
`mechsim/` and `pathfinder/` hold the source-project modules the battle
loop imports (un-prefixed names), `data/` holds `.board` and `.mtf` files,
`reference_logs/` holds same-seed sample logs to diff against.
Settings (mech files, board, seed, batch size, every stub knob) are all in
`INTEGRATION__config.py`. Default: Asymptote II vs Asymptote II on
16x17 Grassland, seed 12345, 1 battle, verbose.

**What a battle looks like right now:** both mechs close, then mostly stand
still and trade fire (the movement stub maximizes expected damage dealt,
and standing still has the best AMM). Asymptote vs Asymptote now runs ~22
turns: with 22 points of dissipation the Asymptote can alpha all five
Medium Pulse Lasers every turn under the 2026-10-18 heat budget.

**The biggest stubs to replace, in rough order of impact on results:**
1. `movement_selection` — which spot to move to (scoring formula is Daniel's call).
2. `attack_direction` — which hit table a shot uses (needs attacker-vs-target-facing geometry).
3. `heat_effects` — heat accumulates for real but does nothing (no Heat Scale).
4. `cluster_grouping` — missile damage grouping sizes.
5. `ammo` — unlimited ammo.

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
6. **Heat** — heat effects applied. *(deferred — see Section 4)*
7. **End Phase** — cleanup. *(scoped to unconscious-pilot recovery roll only
   — see Section 4)*

| Phase | Where | Status (2026-10-18) |
|---|---|---|
| Deployment | `stubs.stub_deployment()` | **STUB** — fixed CONFIG hexes; edge entry not built. |
| Initiative | `orchestrator.roll_initiative()` | **REAL**, Daniel-confirmed 2026-08-31. |
| Movement | `orchestrator._phase_movement()` | **REAL:** damage-aware MP, full Walk/Run/Jump envelope with expected dealt/received per spot (`INTEGRATION__ranged_combat.evaluate_going_second`), unconscious-skip, stand-up (`resolve_stand_up`), movement PSR for Run/Jump (`check_movement_psr`), consciousness checks. **STUBS:** `movement_selection` (the pick), `walk_movement_psr`, `post_standup_movement`. |
| Ranged Combat | `INTEGRATION__attack_resolution.py` | **REAL:** LOS, rear-arc firing block, TN = gunnery + AMM + TMM(actual hexes moved) + LOS + range, heat-constrained weapon selection, real to-hit rolls, cluster table, hit location, damage, crits, explosions, floating TAC, head hits, Attack Phase PSR, consciousness. Both sides declare before damage lands (simultaneous). **STUBS:** `attack_direction`, `cluster_grouping`, `unknown_damage_type`, `unconfirmed_weapon_data`, `ammo`, `to_hit_modifiers_not_applied`. |
| Physical Combat | `stubs.stub_physical_combat()` | **STUB** (deferred by scope call). |
| Heat | `orchestrator._phase_heat()` | **REAL (2026-10-18):** heat carries over; += movement heat (Walk 1 / Run 2 / Jump max(3, hexes) or max(3, ceil(hexes/2)) with Improved JJ) + weapon heat − dissipation. **STUB:** `heat_effects` (no Heat Scale, no engine-hit heat). |
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
| `deployment` | Fixed start hexes | Daniel's edge-entry procedure |
| `movement_selection` | `max_dealt` (ties → closest to enemy → least received → seeded random); no-LOS → closest reachable spot to enemy | Real scoring formula (Daniel); two-ply look-ahead from `combat_turn.py` not ported |
| `walk_movement_psr` | No PSR for Walk/Stand Still (or check as running) | Rule: does walking with gyro/hip/leg damage need a PSR? |
| `post_standup_movement` | Stays in hex, Stand Still AMM/TMM | Rule: movement after standing |
| `attack_direction` | MECHSIM 3:1:1:1 random front/left/right/rear | Attacker-position-vs-target-facing side table |
| `cluster_grouping` | All connected damage as one group (or per missile) | Group size per weapon family (Daniel), then into equipment.json |
| `unknown_damage_type` | null damage_type → BALLISTIC | equipment.json curation |
| `unconfirmed_weapon_data` | Loud warning; weapon never fires | equipment.json curation (e.g. ISLBXAC10) |
| `ammo` | Unlimited ammo (bins still explode on crits) | shots_per_ton data + bin linkage |
| `rear_mounted_weapons` | "(R)" stripped by parser → fire forward | Parser change (MECHSIM, Daniel's call) or INTEGRATION mount table |
| `to_hit_modifiers_not_applied` | Warns: prone target/attacker, sensor hits, arm actuators, heat | The modifiers themselves |
| `physical_combat` | Skipped | Whole phase |
| `heat_effects` | Heat accumulates but has no effect; engine hits add no heat | Heat Scale (Daniel); engine-hit heat rule |

**Rules gaps with no runtime flag** (also printed in every summary):
minimum range (no data); per-mount firing arcs; LB-X/Ultra/Rotary multi-shot
math; Artemis/HAG/ammo variants; Heat Scale effects; cooldown decisions; physical
combat; tripod leg sub-roll uses Python `random` (seeded from SEED, not the
BattleRNG stream).

**TODO noted in code:** a failed movement PSR drops the mech in its END hex;
in tabletop play it falls where the check was failed
(`orchestrator._phase_movement`).

**Other open items:**
- `config.PROMPT_FOR_MAP` picker not built — always loads `DEFAULT_BOARD_PATH`.
- `STITCH_MAPS` raises NotImplementedError (stitch_boards itself is ready).
- Full `MECHSIM__equipment.json` is not in this Project (only the 14-entry
  mini). With the mini DB, the Asymptote's Improved Jump Jets and Endo
  Steel parse as inert padding (jump MP still comes from the header line,
  but jump-jet crits don't reduce it).
- Pile 1 reconciliation: `sim_runner._resolve_hit`/`resolve_weapon_attack`
  are absorbed (`INTEGRATION__attack_resolution`). `combat_turn`'s two-ply
  search and closing-fallback are NOT — don't delete `combat_turn.py` until
  movement selection replaces them or Daniel decides they're not wanted.

**Weapon data model gaps** (unchanged): LB-X/Ultra/Rotary cluster math,
HAG range damage, Artemis, ammo variants, minimum range.

**Cross-cutting hazard — RESOLVED 2026-10-18:** the
load-MECHSIM-then-purge-then-load-PATHFINDER workaround in
`INTEGRATION__weapon_selection.py` deleted `INTEGRATION__config`'s own
`config` registration and made the next `import config` fail (confirmed by
a live import test). Removed. Both directories now go on `sys.path` once.
No PATHFINDER module used by the battle loop imports `config`.

**Deferred by explicit scope call, not gaps:**
- Physical Combat phase, Heat phase (stubbed, see above).
- Radical Heat Sink Systems (activatable, risk-bearing — not passive; not wired).
- End Phase beyond unconscious-pilot recovery (shutdown-mech restart tied to Heat).

**Source-project backlog** (not integration-blocking, real but unwired):
- MECHSIM: Clan free CASE auto-injection at parse time; Reactive Armor's
  full secondary crit roll (only flat halving is wired); Modular Armor;
  Shields (no spec); Superheavy/Compact engine 2-hit exception; LAM/exotic
  Config types; `equipment.json` curation (~80/3758 entries verified,
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
- **Stub conventions (2026-10-18):** every placeholder is its own function in
  `INTEGRATION__stubs.py`, warns loudly every run, is counted into the
  results, keeps its knobs in config. Defaults: movement `max_dealt`, hit
  table `mechsim_random`.

---

## 6. PILE 4 — DECISION-MAKING INDEX (cross-cutting, not a module)

| Decision point | Lives in | Decides |
|---|---|---|
| Movement selection | `INTEGRATION__stubs.stub_select_movement` | **STUB.** Which reachable spot to end movement in. Its inputs (expected dealt/received per spot) are heat-aware since 2026-10-18. |
| No-LOS movement fallback | `INTEGRATION__stubs.stub_select_movement` | **STUB.** Where to go when nothing has LOS. |
| Heat-constrained weapon selection | `INTEGRATION__weapon_selection.py` | Which weapons fire this turn, built and wired |
| Candidate reduction | `PATHFINDER__combat_turn.py` (reference) / `orchestrator._reachable_states` | Max-FC per (hex, facing, mode) — used for the no-LOS fallback pool |
| Best-reply selection | `PATHFINDER__combat_turn.py` | Not wired (reference) |
| `compute_score()` | `PATHFINDER__combat.py` | Not wired (reference; built on flat HP/weapon dicts) |
| LOS rule-6 tie-break | `PATHFINDER__los.py` | Placeholder, see Known Issues #2 |
| Closing-turn detection | `PATHFINDER__combat_turn.py` | Not wired |

---

## 7. STANDING PROMPTS

- Don't write/run code without explicit instruction. "Compile" (or a
  clear equivalent — "go ahead," "do it") triggers execution; ask only
  on genuine scope ambiguity.
- State test scope up front; one pass; don't iterate unless asked.
- Never hardcode a BT numeric rule from memory — confirm with Daniel first.
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
  retired; the live modules are `mechsim/` and `pathfinder/`. Not carried
  over: `MECHSIM__sim_runner.py` (its hit/attack resolution already absorbed
  into `INTEGRATION__attack_resolution`), `PATHFINDER__report.py`,
  `validation.py`, `terrain_colors.py`. Still wanted as reference, not yet
  in the repo: `PATHFINDER__combat_turn.py` (two-ply look-ahead and
  closing fallback, not yet absorbed). Verified: a run from the repo
  matches `reference_logs/sample_battle_log_Asymptote_vs_Asymptote.txt`
  except for file paths, stdout and stderr both.
