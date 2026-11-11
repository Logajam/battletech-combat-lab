# Mech-vs-Mech Integration — Project Map

Single source of truth for the project's state, Daniel's decisions and the standing instructions.
Section 0 = where we are and the open work (read first). Sections 1-3 = scope, turn structure, the four
piles. Section 4 / 4a = open items and readings by topic, arcs. Section 5 = Daniel's decisions
(implementation may not override). Section 6 = every bot decision point, the Princess clone, the Memo.
Section 7 = standing instructions. The Change Record is `INTEGRATION__CHANGE_RECORD.md`; the session
history is `INTEGRATION__HISTORY.md`; task write-ups are `INTEGRATION__TASK_SPECS.md`; the Rust translation plan
is `INTEGRATION__RUST_PORT.md`; what a battle's state is: `INTEGRATION__STATE.md`.

**Naming:** `mechsim/` and `pathfinder/` hold the two source projects' modules; `INTEGRATION__*` = this
project's files. Never let one source project's file overwrite the other's same-named file.

---


## 0. WHERE WE ARE (2026-11-11, session 25) — read this first

This section is the current state and the open work, nothing else. The story of how it got here is in
`INTEGRATION__HISTORY.md` (the old Section 0, word for word, with Daniel's quotes and every number) and
`INTEGRATION__CHANGE_RECORD.md` (every change, newest first). Keep this section short: when something is done,
move its line to the Change Record instead of adding a paragraph here.

**What it is.** `.mtf` units in, turn-by-turn battles on a real hex board under the Core Rulebook, a batch summary
and statistics page out. Any number of units on any number of teams (`config.FORCES`), each driven by one of two
bots: Gladiator (this project's) or Princess (a MegaMek clone); a third, Hydra, exists in the Rust engine only. Daniel owns rules and scope; Claude owns the code
and the GitHub logistics (Section 7).

### Session setup and the checks

- **Rust engine (`engine/`, sessions 22-24):** `cd engine && cargo build --release -p btsim`; batches with
  `engine/target/release/btsim SCENARIO_DIR --battles N` (scenarios from `tools/port_scenario.py`; the Hydra mirror set
  from `tools/hydra_scenarios.py`, into the git-ignored `engine/fixtures/`). Checks: `RUST_PORT.md` "Session 24".
- `pip install -r requirements.txt`. Unzip `rules/Battletech_Rule_Reference_Index.zip` OUTSIDE the repo (Core
  Rulebook in `base/core-rules/*.md`, a `[p.N]` marker comes before page N's text; `summary/core-rules/*.yaml`
  is the fast read). Unzip `data/meks.zip` / `data/maps.zip` outside the repo when needed.
- The Rust module is optional (same results without it): `pip install maturin && cd fastcore && maturin build
  --release && pip install --force-reinstall target/wheels/*.whl`.
- MegaMek's source, when a rule or the Princess clone needs it: `git clone --depth 1 --filter=blob:none --sparse
  https://github.com/MegaMek/megamek.git` works through the proxy (Section 6, "Princess clone").
- Run: `python INTEGRATION__main.py`; every setting is in `INTEGRATION__config.py`.
- **After any change:** `python tests/run_checks.py` - 57 checks today (41 test files + 15 reference battles + the
  Rust reference set as one line), 1-2 minutes, all must pass. The Rust set (session 25): `python tests/check_rust_reference.py`
  plays 79 battles with `btsim` (inputs frozen in `engine/reference/scenarios.zip`, logs in `engine/reference/logs/`;
  `--update` for a Rust change meant to alter results) - the Rust's own answer key, no Python needed. The Asymptote mirror prints a NOTE at the 50-turn cap (the stall, backlog A1).
  `--bench` for anything on the hot path: a speed-only change must keep the benchmark's HP totals (501 / 495) and
  every reference log. A change MEANT to alter results: `python tests/check_reference_logs.py --update`, and say
  so in the Change Record. Art-only work runs only the three token tests (Section 7).
- Bot changes: `python tests/ab_batches.py` (duels) or the battery: `python tests/baseline_battery.py pg 20
  --legate --turns 100 --seed N --stats --first A --last B` (resumable; one core's share - start four side by
  side; `--no-triage` = the old baseline), table by `python tests/battery_summary.py`. Launching a background
  command is not the battery finishing: read each output file, then report.
- Show Daniel battles as replays: `config.REPLAY_BATTLES`, publish the page from `replays/` with the Artifact
  tool, give him the link.

### What is built (details: README, CALL_GRAPH, RULES_REVIEW, BOTS)

| Area | State | Where |
|---|---|---|
| Rules engine | Core Rulebook 'Mech combat: movement and terrain (water, hazards, passive buildings), LOS, ranged, all seven physical attacks, heat, damage / crits / PSRs, every Core weapon and most equipment; TO:AUE / TO:AR terrain and gear; IntOps weapons; ultralights and superheavies. 4,204 of 4,227 MegaMek units load (not the 23 LAMs); 174 of 192 16x17 maps play | `INTEGRATION__*`, `mechsim/`, `pathfinder/`; `INTEGRATION__RULES_REVIEW.md` (fixed F1-F71, open G rows) |
| Multi-unit battles | Teams, Initiative for any number of sides, stacking, domino effect, stitched boards | `INTEGRATION__forces`, `_domino`, `orchestrator.run_skirmish` |
| Gladiator | "Lifetime" move score, Short Grid search, two-ply first mover; in team battles Legate (enemy estimate, fire split), triage tiers, tiered movement order option, fire director option | `_movement_selection`, `_legate`, `_triage`, `_tiers`, `_kill_curve`, `_peril`, `_vision` |
| Princess | Modern (default) and v0.50.07 clones; group behaviours; Battle Value | `_princess*`, `_battle_value` |
| Choices still stubs | Rate of fire, ammo kind, MASC / supercharger, unjam, capacitors, shields, TAG... (loud, counted) | `INTEGRATION__stubs.py`, Section 6 |
| Output | Batch summary, timing table, replays, battle statistics page (stages 1-3 of 5), saved states (end of a turn) | `_results`, `_timing`, `_replay`, `_stats*`, `_saved_state` |
| Rust engine | The whole engine and both default bots, exact against the Python on 63 fixtures and ~830 random battles; `btsim` batches about 10x the Python's speed a core. Not translated: the switches that are off by default | `engine/`, `INTEGRATION__RUST_PORT.md`, `engine/REVIEW_BRIEF.md` |
| Hydra | Third bot, Rust only: one planner a team, damage priced by a forecast of the battle's end. Ahead of Gladiator at 4 v 4 / 8 v 8, behind in brawler duels | `engine/core/src/hydra.rs`, `INTEGRATION__HYDRA.md` |
| Speed (old) | Rust copies of the weapon table, movement search, LOS, hex distance for the Python; to be retired | `fastcore/`, `config.USE_FASTCORE` |
| Combat Lab art | Skeleton-and-shell faceted models, block library, workbench | `_tokens`, `_shell*`, `tools/token_*`, `INTEGRATION__COMBAT_LAB*.md` |

**Defaults that matter for the bots:** Legate on; fire split "proportional", this turn too; triage on (since
2026-11-08); Gladiator's target = Princess's choice borrowed (`STUB_GLADIATOR_TARGET = "princess_plan"`; the fire
director "kill_curve" is level with it, not better); big guns fire first; move order = Princess's index. OFF
because they did not win more: Peril in the move score, stacked coverage, herding, cohesion, team value, exchange.

**Yardstick** (Princess Red v Gladiator Blue, 12 v 12, 32 x 17 field, 100 battles, 100-turn cap): with triage
Gladiator 51 / Princess 47 / 2 draws, 'Mechs left 2.32 / 2.39; without, 42 / 56 / 2 (`INTEGRATION__BOTS.md`).
A 20-battle set swings several wins either way - compare against the 100-battle row.

### Open work (the backlog)

In brackets: the item's old "Pick up here" label, under which `INTEGRATION__HISTORY.md` has the full text. Task
write-ups a smaller model can act on are in `INTEGRATION__TASK_SPECS.md` (T numbers).

**A. Gladiator - the bot**
- **A1. The move score does not see a win, a clock or the walk back** (review 2026-11-10; [000000 (a)], [0]
  anti-stall). One cause behind the end-game stand-off, the mirror stall and the cap draws: the score has no
  enemy HP in it (a kill earns only its damage points), waiting costs nothing, and a spot far out of range keeps
  the full future term. To build as a switch and A/B (spec T1). Daniel's ruling stands: no special last-enemy mode.
- A2. Triage knobs: the 25% share, the weights (hot x2, cool x1.5), peak v mean [000000 (b)] - after A1 (T7).
- A3. Physical attack value in the move score looks about 2x high [000000 (j)] - probe first (T4).
- A4. Cohesion groups the force but does not win [00000]; team value / exchange re-tested, no gain. Re-test after A1.
- A5. Peril leftovers [000000 (c)-(i)]: arcs for units that stand still; smoke rebuild of the visibility table
  (`vision.invalidate` exists, nothing calls it); the ~2x turn cost; Legate reading terrain; holding back until
  the force can engage together; tiered movement order refinements.
- A6. Team awareness topics [0000] (Daniel's designs, to talk through): drawing fire for a weak unit, movement
  order, active choices priced in one currency, indirect fire and spotting (also settles `STUB_MISSION_KILL`).
- A7. Research decisions [3, 4, 8]: rate of fire, MASC, ammo kind, ammo conservation, PPC capacitors, the
  future-capability Memo (Section 6); placeholders `TARGET_HEAT_WORTH`, `TASER_` / `TSEMP_` / `IMP_EFFECT_WORTH`.
- A8. Not priced in movement scoring [6, 7]: attack-caused PSRs, mud's -1, hull-breach risk (G21: DON'T BUILD
  YET, Daniel), being pushed off the board edge.
- A9. Measurement (review 2026-11-10): judge A/Bs by a per-battle margin, not win counts (T2); a small scenario
  suite so the bot is not tuned to one roster and field (T3).

**B. Princess clone** [00] - still to clone when the project has the rules: forced withdrawal, artillery / TAG
standoff, sprinting, multi-target fire, unit orders. Open call (Daniel): Short-Short as the default search.

**C. Rules and units**
- C1. Crippled / forced withdrawal [5] - not started; an option plus a picker override.
- C2. Full building rules, bridges, fuel tanks [7, G22] - Daniel: "probably a discussion first".
- C3. Spotting / indirect fire, C3, special munitions (G16), G18 choices, G12; fire, snow / ice, temperatures;
  LAMs; TO:AR optional weather [11].
- C4. Deferred by Daniel [10]: 'Mech UMUs, the chain whip grapple, industrial tools.
- C5. Rules library: refresh the zip with TO:AUE / TO:AR; Interstellar Operations is not indexed yet (T9).
- C6. Other unit types; scenario features (objectives, fog of war).

**D. Engine, speed, state**
- D1. THE RUST TRANSLATION - DONE and reviewed (sessions 22-24; Change Record "RUST ENGINE REVIEWED"). Daniel, 2026-11-11:
  "Python will be effectively retired from here on out"; new bot work is Rust only (Hydra). Left, finishing work for a
  smaller model: a `config.ENGINE` switch in `INTEGRATION__main.py`; retiring `fastcore/`; then the Python fixes in
  Section 4 ("Known issues found by the Rust review" - Daniel: after the port is otherwise complete); the switches
  that are off by default stay untranslated until needed; speed leads in `engine/REVIEW_BRIEF.md`. Check any Rust
  change with `BOTS=rust cargo test --release --test stage6_battles` and `python tools/port_fuzz.py exact ...`.
- D2. One battle-state object and stable unit numbers in place of memory-address keys (about 300 `id()` uses; two
  real bugs came from them). Design DONE: `INTEGRATION__STATE.md`. The Rust translation builds it directly; the
  Python is changed (T6) only if the translation is dropped.
- D3. Saved states [16]: saves inside a turn; a replay from a loaded state; a readable state; `--round-trip` in
  run_checks.
- D4. Tidy the switches (148 settings): move the experiments that lost out of the scoring path - Daniel's call
  first, they are his designs (T8).
- D5. Automatic checks on GitHub for every push (T10).

**E. Output, GUI, art**
- E1. Battle statistics: stages 4-5 (Change Record "BATTLE STATISTICS", Section 5).
- E2. Combat Lab GUI [12, 14]: HTML front end behind an `.exe` (Daniel); setup shell first; MegaMek save import
  to test later. `INTEGRATION__COMBAT_LAB.md`.
  BUILD ORDER as spec sheets CL1-CL9 (session 24, on the Rust engine): `INTEGRATION__COMBAT_LAB_SPECS.md`.
- E3a. Art direction (session 24): why the models read as stacked blocks, and jobs A1-A8 in order -
  `INTEGRATION__COMBAT_LAB_ART_SPECS.md` (nothing built).
- E3. 3D art [15] (paused): next the weapon-block stockpile, then bird-body torso / head blocks, the 47 chart
  chassis, directional hardpoints.

**Daniel's own list of next topics (2026-11-06):** individual bot logic; group bot logic; more speed; GUI; Combat
Lab functionality; 3D art.

### REVIEW QUEUE (Daniel's standing order, 2026-10-28; Section 7)

Work waiting for a higher-level model's review. Items (a)-(l) were cleared 2026-11-06. When a review is done,
remove the line and note it in the Change Record.
- **(w) RUST REFERENCE BATTLES** (session 25): `tests/check_rust_reference.py`, the frozen inputs, the hook in `run_checks.py`.
- **(v) SESSION 25 TIDY-UP** (2026-11-11; Change Record "SESSION 25"): the lookahead-dice fix in both engines
  (`structure_weight.hit_spread`, `structure_weight.rs`), the six-crew-hits rule (`piloting_rolls.rs`), the warning clean-up.
- **(u) HYDRA, THE THIRD BOT** (session 24, Rust only) - plan `INTEGRATION__HYDRA.md`, code `engine/core/src/hydra.rs`. Second pass 2026-11-11 (exposure, lone unit may hide, reply 64; full table re-run in session 25: 285 - 245 head to head, HYDRA.md Section 5). First version built and
  measured (Change Record "HYDRA"); NEXT WORK is the movement play-out, plan Section 6 (S5a), then Section 7. To review: the Forecast and Prices,
  the Mover's score, the Fire Plan's overkill rule.
- **(t) RUST PORT STAGES 1-9** - REVIEWED in session 24 (Change Record "RUST ENGINE REVIEWED"): two engine bugs fixed, 3-5x faster, random-battle
  check added. What is left of it for a later look: the five Python findings below it in Section 4 (Daniel's call), and the session-24 changes
  themselves (the caches `los_memo` / `table_memo` / `Equipment::memo` and when `Battle::board_changed` empties them; `pyfmt::py_sum`).
- **(s) RUST PORT STAGE 0** (session 22; Change Record "RUST PORT STAGE 0 DONE"). Review: the decision seam changes nothing in
  normal play (`INTEGRATION__decisions.decide` calls `compute()`; the `choose_declaration` move in `attack_resolution._declare`
  is the same code); the recorder's hooks only read; the replay's completeness argument (an exact replay with the bots off proves
  the decision list holds everything the engine needs from them); the coverage list `engine/COVERAGE_GAPS.md`.
- **(m) BATTLE STATISTICS** (session 20). Review: the three engine hooks only read (`attack_resolution.
  run_ranged_phase`, `physical.run_physical_units`, the orchestrator's turn loop); per-attack damage is a total-HP
  difference around each attack (a hit that sets off an ammo explosion counts the explosion); kill credit = the
  first attack that leaves the target destroyed; the analysis in `INTEGRATION__stats_report.py` (Wilson interval,
  percentiles, the "held at its final state" curves); the page (`INTEGRATION__stats_viewer.html`).
- **(n) RUST SPEED WORK** (session 20; Change Records "RUST PORT STEP 1" to "STEP 6", "RUST EVALUATE LOOP: TRIED,
  MEASURED, NOT KEPT", "DECISION"). Review: each Rust copy is the Python's step for step - `fastcore.FastTable`
  (`weapon_selection.FireTable.choose`; `fire_modes.Planner.price_spec`), `PathBoard`
  (`pathfinder._build_terrain_psr`, `ranged_combat._movement_options`, incl. the entry-order quirk where the
  picker reads a state's FIRST PSR count), `LosBoard` (`los._evaluate`), `hex_distance` (round half to even); the
  Python caches (`damage_resolution.get_weapons` / `derived`, `structure_weight.multipliers`, `_ScorerContext`,
  `fire_state`'s `_damage_state`) invalidate on the right events (slot loss, turn start, battle start; smoke for
  the LOS snapshot); the new tests (`test_fastcore.py`, `test_fire_tables.py` with `FIRE_TABLE_VERIFY` and
  `WEAPONS_CACHE_VERIFY`) really exercise the Rust (they fail on a silent fall back, except as noted in the
  movement-search entry).
- **(o) TIERED MOVEMENT ORDER** (2026-11-07). Review: `INTEGRATION__tiers` (the four tiers from the footprints;
  `pick`; `flankers_of`), the hooks in `forces.movement_order`, `orchestrator` and `legate.foe_for`,
  `tests/test_tiers.py`; the two placeholders (union footprint, any-neighbour flank).
- **(p) THE PERIL LINE** (2026-11-07 / 08: `INTEGRATION__vision`, `_peril`, `_stack`, `_triage`; triage on by
  default). Its Change Record entries are marked REVIEW PENDING; it had no queue line until this clean-up.
- (q) THE MAP CLEAN-UP itself (2026-11-10): documents only, no code; check nothing was lost in the move.
- (r) THE PLANS written 2026-11-10: `INTEGRATION__RUST_PORT.md`, `INTEGRATION__STATE.md`, spec T1's formula
  (`INTEGRATION__TASK_SPECS.md`). Worth a second look before a long build starts on them.

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

**Rules gaps with no runtime flag** (the current list is printed in every
summary - `INTEGRATION__results.KNOWN_MISSING_RULES`; refreshed 2026-10-28,
the older items here had been built): the twist / flip a TAG designation
uses up; special munitions (G16, deferred); bombast charging, HAG flak,
distant Arrow IV (G18); full buildings / bridges (G22, deferred); fire,
snow / ice, extreme temperatures; heat decisions (cooldown, voluntary
shutdown); domino effects (no third mech). Units that don't load: LAMs
(ultralights and superheavies load since 2026-10-28).

**Core Rulebook vs existing MECHSIM rules - Daniel to decide** (found
2026-10-19 while replacing stubs; MECHSIM left unchanged because these are
confirmed project rules, not stubs):
- (Decided 2026-10-20, see Section 5: multiple PSRs one per trigger, the
  seatbelt check, fall side, Floating Criticals and fight-to-the-death are
  settled.)
- RESOLVED 2026-10-21 (Daniel: "Stand up, tripod, jumping, 4 legged mechs
  should all have answers in the rules. Clear them please." - rules as
  written, RULES_REVIEW F42): standing up -1 per attempt (p.51); tripod -1
  with no leg destroyed plus its dedicated pilot -1 / +2 disabled (pp.236-
  237); leg destroyed +4 (p.111); quads -2 only with all four legs, +1 per
  lost leg for the first two, no PSR to stand with all four legs, one lost
  leg forces no run / jump PSR (pp.238-239).
- RESOLVED 2026-10-21 (Daniel: "Follow the rules, not my calls" - built,
  RULES_REVIEW F43): his 2026-07-12 quad leg rules
  (`mech_state._damage_walk_mp`, `legs_gone`: a quad's lost legs count one
  fewer, so 2 lost legs = Walking MP 1 and 3 = destroyed) differ from the
  appendix (p.238): 1 lost leg -1 Walking MP, 2 lost legs -2 (the effects
  of a hip hit), 3 = a biped with one leg lost (still moves), 4 = both legs
  lost. Now the book's.
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

**Crew at 6 hits with the unit still standing (found by Hydra's trials, 2026-11-11).** A unit with several crew can reach 6 crew hits and not be
destroyed; the consciousness check then had no table entry and crashed. Placeholder (stub `crew_six_hits`, `piloting_rolls.rs`): that crew member is
out for the battle, no roll. RESOLVED session 25 from the book: six hits = dead (Core p.117, the Consciousness table's 6 column reads
"Dead"), so no roll; the console's secondary warrior takes over (p.203). Stub removed.

**Known issues found by the Rust review (session 24, 2026-11-11; the Python is frozen during the port, so none is changed).**
**DANIEL, 2026-11-11: fix these in the Python AFTER the port is otherwise complete ("We'll leave correcting the python code for future you"); the
lookahead dice are not a worry as long as both engines are wired the same way (they are: the Rust copies the quirk and draws from the battle's dice
too - only the number of draws differs, which shows in an exact replay and not in batch statistics). The switches that are off by default stay
untranslated "until they're actually needed". What is left of the port is finishing work for smaller models.**
- FIXED session 25 in both engines (Daniel: "a free floating dice outside of the seed"): the lookahead now takes the re-roll's
  exact average (Head rows dropped, the rest scaled by 1 / (1 - P(head))), draws no dice and prints nothing. Was: a bot's lookahead rolls REAL dice: `structure_weight.hit_spread` calls `hit_location.resolve_hit_location`, which re-rolls a head result on a unit
  whose head is destroyed and whose cockpit is in the torso (Core p.203) with `config.roll_2d6` and logs each re-roll. So a bot that is only thinking
  uses up battle dice and prints dozens of "Head already destroyed ... re-rolled" lines (fixture `fza_240`: 47 in one move). Suggested fix: in the
  lookahead, spread a head result over the other rolls instead of rolling.
- Crash: `weapon_selection._finish_choice` compares `w.heat <= remaining_budget` for a weapon whose heat is None (a profile weapon priced by the
  Planner, in the min-heat padding). Met with Parash 2 (Princess) v Uraeus UAE-7R (Gladiator), `tools/port_fuzz.py exact 182 1`.
- Crash: `capacitor.set_charged` adds to `ppc.base_damage` when it is None (Phoenix Hawk PXH-7KJ "Jasmine"), `tools/port_fuzz.py exact 242 1`.
- Crash (read from the code; the Rust had the same and is fixed): `ranged_combat.path_to` with `entry_edge` builds a table from an edge hex an
  enemy stands on - "Start hex ... is not on the loaded board".
- `smoke._changed` empties only the standing / standing LOS cache (`geo_cache.board(_BOARD)`): lines cached for a prone attacker or target keep
  their pre-smoke answer.

**Known issues to fix later (found session 13, Claude):**
- ~~FLAKY CHECK~~ FIXED 2026-10-29 (Claude): it was `test_superheavy.py`
  `superheavy_slots` - the ammo blast rolled its critical-hit checks with live
  dice, and about 1 run in 20 a critical set off another bin (one pilot hit
  more than the check expected). The check now pins those rolls to a miss
  (old version: 3 failures in 60 runs; new: 0 in 30). Earlier notes:
  One `tests/run_checks.py` run once reported "40 of 41 checks passed, 1
  FAILED" and the failing line was not captured; the next ~10 runs were all
  green. A flaky check somewhere (a shared cache or file written by two checks
  running side by side is the first suspect). If it shows again, keep the
  output. Seen once more 2026-10-29 ("41 of 42 ... 1 FAILED", output cut by a
  `tail -1`; the next 3 runs green).
- (found session 14, Claude) `mech_state.is_crippled` (logged as "now
  CRIPPLED" in the End Phase, nothing else reads it) uses the BattleMech
  Manual list Daniel quoted; the Core Rulebook's Crippling Damage ('Mechs,
  p.228) is a different, shorter list (two engine hits; two destroyed limbs
  with a leg among them; a destroyed torso, which a standard or compact fusion
  engine may ignore on a Piloting Skill Roll). Only matters once forced
  withdrawal is built (Daniel, 2026-10-29: crippled means "that pilot should
  run" - not a mission kill).

**Known issues to fix later (Daniel, 2026-10-20):**
- **Split items in a shared location (cleanup sweep; Daniel, 2026-10-21).**
  `mtf_parser._join_split_items` joins the parts of an item split across 2
  or 3 locations by name and slot count. Two of the same item that both put
  slots in one location (two Thumpers sharing the centre torso, possible on a
  superheavy) run together there into one part, so neither adds up and both
  stay short (a WARNING, not a silent mix-up). The Uni ATAE-70 ArtilleryMech
  (its Thumper 1 + 7 + 7 across three torsos) is an illegal design, not
  labeled as one (Daniel). Let the code sit until the cleanup sweep.
- ~~**Scatter vs the firing arc.**~~ FIXED 2026-10-21 (Claude): a missed
  Arrow IV / artillery cannon walks its scatter path a hex at a time and
  lands in the last hex still inside the launcher's firing arc (pp.182-183,
  `attack_resolution._resolve_area_miss` / `_in_firing_arc`: the mech's
  facing and this turn's twist / flip / turret). Held back all the way, it
  lands in the target's hex and deals the full area-effect damage.
  `tests/test_weapons.py` arrow_iv_scatter_held_by_firing_arc.
- ~~**Machine gun array ammo.**~~ FIXED 2026-10-21 (Claude): each gun still
  takes its own round, but guns sharing a bin used to each count the whole
  bin, so a bin with 1 round left fired every gun in the array. Now the
  rounds are counted once for all the guns (`fire_modes.mga_firing_guns`,
  `take_array_rounds`). Tested: shared bin, 1 / 2 / 0 rounds left, a
  destroyed gun drops out (`tests/test_weapons.py` machine_gun_array_ammo).

**Map terrain waiting on rules (Daniel is hunting them, 2026-10-21; updated
2026-10-27 - magma, hazardous liquid, ultra-heavy woods, fortified, planted
fields and impassable hexes now play from TO:AR, RULES_REVIEW F57-F59):** these
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
  damage on a 'Mech: 5-point groupings (pp.87, 182). Scatter stays inside
  the firing arc (fixed 2026-10-21, see "Known issues" above).
- Machine gun arrays: one round from each gun fired, shared bins counted
  once (fixed 2026-10-21, see "Known issues").
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
- `config.PROMPT_FOR_MAP` works (2026-10-28, `INTEGRATION__map_picker`): a console menu; the GUI will call the same library.
- `STITCH_MAPS` works (2026-10-28): `STITCH_BOARDS` names the boards, row-major.
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
2. ~~Pathfinder's LOS tie-break is an explicit placeholder~~ - 2026-10-21:
   the target picks one side of a border line for the whole line (p.56),
   the side worse for the attacker (RULES_REVIEW F41).
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

- **Battle statistics (Daniel, 2026-11-06):** the report is an HTML page (like the replays), one per batch.
  Teams get a limited set (win / loss, units standing and force remaining over time, survivors at the end, first
  kill timing, focus fire), the per-unit detail stays per unit. "Technically stats are useful even in a single
  game just to get a summary of events", so it is on for every battle by default (`config.STATS`), and it is
  switched off for the reference-battle checks and the speed benchmark. Dropped from the lists the other AIs
  gave: damage per ton and the other generic efficiency numbers ("an artifact of the other AI's generalizing");
  BV-based efficiency stays only in team / matchup views.

- **Map seams (Daniel, 2026-11-06):** "It should follow Megamek's
  conventions." Stitched boards abut (MegaMek BoardUtilities.combine); only an
  odd-width board gets one blank column after it. Replaces the 2026-07-20 rule
  (a blank row / column at every seam).

- **Multi-unit battles (Daniel, 2026-10-28):** "Multiple units that can be
  assigned to multiple teams. The ideal ranges would probably be a 4 unit
  lance and a 12 unit company vs like forces. But a 20 unit free for all or a
  3 way battle between different lances are also possibilities that need to be
  covered by the general solution. For the moment we're just getting to the
  point where we can unleash a group of bots to operate independently. (Or as
  a group if Princess already has that wired in waiting to go.)" - built as
  `config.FORCES`; Princess has no group mode wired in here (its mutual
  support, fire distribution and formations are the unbuilt Pick up here 00
  items), so the bots run independently. "If you encounter a question that
  can't be answered in the rules, consult how megamek does it, then me if its
  still a question" (Section 7).
- **IF/THEN's purpose (Daniel, 2026-10-28):** "this will not be a default
  search patern for an individual mech. In multi-unit games it is used to get
  a general idea of threat vector of farther away units while stronger
  searches deal with more immediate threats to avoid full N! computation
  explosions." It stays an option (`MOVEMENT_SEARCH = "if_then"`). Studies of
  it: "only run the more interesting test series. We're after general feel,
  not full stats" (`tests/pick_quality.py --pickers`, a few battles).
- **Multi-unit aware bot - Daniel's groundwork (2026-10-28):** two layers.
  (1) A PRE-MOVE phase, not the real movement: IF/THEN run for all units at
  once ("One side can move all of their units at once, Then the other starts
  a counter move"), up to ~12 rounds; a unit whose answer stops changing
  locks and costs nothing more. It "mimics a humans estimate of potential and
  threat zones"; no unlocking ("This is not their actual move phase").
  (2) The real movement adds "What is tactically important right now": units
  in that "right now" group get the strong search (Short Grid style) against
  the few enemies that matter; every other unit "can skip their entire short
  list value and just plug in either their final movement location or their
  IF/THEN location as the likely threat vector". Purpose: avoid the joint-
  position explosion (every unit's spot x every enemy's reply). Open design
  points for when it is built (Claude): what puts a unit in "right now"
  (range, line of sight, threat, ...); a target model for who shoots whom
  (focus fire), so a unit doesn't assume the whole enemy force fires at it.
- **Equipment wiring (Daniel, 2026-10-21):** "Wire in equipment that requires
  choice (Like capacitors) but defer the actual bot decision making for
  later." - each choice is options + a stub (Section 6 row). "Active probes
  and TAG could have a use in a 1 on 1 fight when smoke and homing ammo is
  included." "Thumper And Sniper Artillery use the same rules as Arrow IV.
  Thumper uses a 15/5 damage profile as a difference. Their homing ammo does
  10 (Sniper) and 5 (Thumper) on a hit. Plus 5 AE damage to all units in the
  target hex. Thats enough for basic wiring, we'll post the full rules
  later."
- **Clubs (Daniel, 2026-10-21):** "Clubs do not block weapons fire. Though
  Firing weapons in either arm does preclude the club attack that turn. May
  as well have mechs pick them up if they have nothing better to do." -
  `CLUB_PICKUP` on. PPC capacitor charging: "a bot logic question that
  requires its own session" (Pick up here 8).
- **Rules over house rules (Daniel, 2026-10-21):** "Follow the rules, not my
  calls." - quads' leg damage now follows pp.238-239 (F43);
  `POOL_CLUSTER_DAMAGE` defaults to False (rules as written). Kept on
  purpose: `FIGHT_TO_THE_DEATH` off - "it saves time when the situation is
  hopeless". (Section 7 standing prompt.)
- **PSR special cases (Daniel, 2026-10-21):** "Stand up, tripod, jumping, 4
  legged mechs should all have answers in the rules. Clear them please." -
  rules as written (RULES_REVIEW F42). This replaces his 2026-07-16 tripod
  -2 and 2026-07-17 pilot-unconscious +3 for tripods (+2, p.236; a QuadVee
  keeps +3 - not a Core unit).
- **Line of sight (Daniel, 2026-10-21):** "Go ahead and make sure the LOS
  rules match those in the rules and fix prone mechs." - the Core Rulebook's
  LOS (pp.56-58, 66) replaces his simplified 2026-07-19 rules (RULES_REVIEW
  D8 decided, F41).
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
  - Breach-risk pricing (G21): "Your plan is close to what I'm thinking.
    Save the notes but don't implement it yet" - tied to his idea for
    costing cluster weapons and risky equipment, another session (Section 6
    Memo).
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
    built as optional rule `POOL_CLUSTER_DAMAGE`, default True (False since
    2026-10-21: "Follow the rules, not my calls").
  - "Fixing non functional weapons just became top priority" (done); specialty
    ammo deferred.
  - Later ideas: a best-solution lookup table per weapon by range and starting
    TN; cluster weapons' value raised by their crit odds against the target's
    armor (`INTEGRATION__HISTORY.md`, "Pick up here" item 1).

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
| Multi-unit: activation order within a side | `forces.move_index` / `forces.movement_order` | Princess's move index (MegaMek `calculateMoveIndex`: distance to the nearest enemy over the fastest move; far, slow units first) for every bot; a unit still off the board goes first. Ranged declaration: Gladiator's FIRING ORDER, `bots.fire_pick`, `config.GLADIATOR_FIRE_ORDER` (2026-10-29, Daniel: "Big guns first followed by smaller guns. Its the same rule used on a mech, just applied to the entire formation.") - "big_guns_first" (default): within each of its side's selections, the Gladiator with the most expected damage at any enemy now (`kill_curve.firepower`, the dry run of its weapon choice) declares first, so smaller guns see the big guns' fire in the damage map; ranked after TAG designation; only when a side has 2+ Gladiators. "roster": list order. Princess units and the physical phase: roster order. TIERED ORDER (`config.MOVE_ORDER = "tiered"`, `INTEGRATION__tiers`, Daniel 2026-11-07, default "index"): for a side's Gladiator units - tier 0 stand-still (Legate's estimate of the unit's own end spot is its hex), farthest from its enemy first; tier 1 safe (its movement footprint, every hex it could end on, is completely outside the union of the enemy's); tier 2 may be flanked (overlap); tier 3 trapped (all inside); slower first inside tiers 1-3; fixed at the start of the Movement Phase; also when entering the battlefield (entry hexes as the footprint; no "off the board first"). Tiers 2 and 3 plan their two-ply against the highest-threat enemy that could flank them (`legate.foe_for` pool = the enemies whose footprint reaches a hex next to one the unit could end on). Placeholders: the enemy footprint is the whole side's union; a "flank" is any reach to a neighbouring hex, not to the side / rear arc. |
| Multi-unit: Initiative and Unequal Numbers with 3+ sides | `forces.initiative_order`, `forces.activation_sequence` | The book (pp.39-41) covers two sides. Here: every side rolls 2D6, the LOWEST acts first, only tied sides re-roll; each side takes ceil(its eligible units / the smallest other side's) selections at a time, tallied at the start of each round - exactly the book's table for two sides, and MegaMek's `TurnOrdered.generateTurnOrder` (ceil(turns / min)). Shut-down / unconscious (and, moving, immobile) units are left out of the tally and go ahead of their side's first selection. |
| Multi-unit: whom a bot plans movement against (its "foe") | `bots.choose_foe` -> `forces.choose_foe`, `config.FOE_CHOICE` | "nearest": the nearest standing enemy on the board (ties by roster order), else one not yet on the board. Gladiator's movement scoring sees that ONE enemy (independent bots) unless Legate is on (next row). Princess takes it as the start of a `princess_group.Group`: every enemy on the board is weighed (below). |
| Legate: Gladiator against the whole enemy force | `INTEGRATION__legate` (`config.LEGATE`, `LEGATE_ITERATIONS`), `movement_selection._legate_extras` | Daniel's design, 2026-10-28. At the start of the Movement Phase, for each side with a Gladiator and 2+ enemies on the board: IF/THEN for all units at once - round 0 everyone holds still, each round the enemy units answer, then the asking side's own units; a unit scores each spot (the grid search) with the picker score ("lifetime") against the WHOLE opposing force at its estimated spots: damage taken = the SUM over opposing units, damage dealt = the MAX, future damage rates likewise (`MultiLifetime`). Two units wanting a hex: the higher score keeps it, the other takes its next best, which can displace a third (cascade, `resolve`), settled before the next round; a unit that picks a hex it already tried is locked at its best attempt (closed to the others too). 12 rounds at most (`LEGATE_ITERATIONS`); the enemy units' best attempts are the estimate. Each Gladiator then plans against the enemy that would score highest against it (each at its estimated spot, its real spot once moved) among those yet to move (all moved: the most threatening), runs its normal search against that foe, and every spot is also scored against the other enemies at their estimated / real spots (taken adds up, dealt is the best). Fire at the weapons phase is unchanged (it already looks at every enemy). Off, or a duel: byte-identical. FIRE SPLIT (`config.LEGATE_FIRE_SPLIT`, 2026-10-29): in the life-left estimate each enemy's future rate on me counts times `legate.fire_share` - "proportional": my slice of what that enemy could deal across my standing team (those it can matter to) - or "none" (all of it, the first version). THIS TURN (`config.LEGATE_SPLIT_THIS_TURN`, `legate.now_share`, 2026-10-30): the same share on each enemy's damage this turn, in the move score and the estimate; default with "proportional" since the 2026-10-30 A/B. HERDING (`config.LEGATE_HERDING`, `legate._Herd`, Daniel's shape 2026-10-29): a spot that an enemy (at its estimated spot) can reach costs `LEGATE_HERD_WEIGHT` damage a hex beyond the support of every teammate that can see one of those enemies (LOS from the teammate's estimated / real end spot); support = the end of its medium bracket, long if it stands still; no teammate sees one: `LEGATE_HERD_UNSEEN_GAP` hexes; added to the damage taken. COHESION (`config.LEGATE_COHESION`, `legate._Cohesion`, Daniel 2026-10-30: "Reward staying within a range braket of its allies, stronger at short, much weaker at long. And how many allies are in mutual support range"): for each teammate (its estimated / real end spot) a spot inside the teammate's short / medium / long bracket (best weapon for each, `legate.brackets`) earns `LEGATE_COHESION_REWARD` 2 / 1 / 0.25 damage points, and inside mutual support (within both units' `support_range`: medium, long when standing still at the spot) `LEGATE_COHESION_MUTUAL` 1 more; summed over the teammates, times `LEGATE_COHESION_SCALE`, taken off the damage taken; no LOS test. Options: `LEGATE_COHESION_MAX_ALLIES` (only the best N teammates count), `LEGATE_COHESION_THREATENED_ONLY` (a spot no enemy can reach counts as fully supported), `LEGATE_COHESION_PAIRING` "either" (Daniel's fire-support point: judged by whichever unit covers the other, support inside either support range) v "ally". Off by default (A/B 2026-10-30). TEAM VALUE (`config.LEGATE_TEAM_VALUE`, off by default until A/B'd; `legate._TeamFire`, Daniel 2026-10-29): with the mover at the spot being scored, each enemy (estimated spot) shoots the unit it hurts most (movement evaluator, per pair) among those not already doomed by the fire assigned before it (`LEGATE_TEAM_FIRE_MODEL` "greedy", enemies in order of their biggest damage); the score becomes dealt + the team's future damage TV, "sum" = sum over the team of (1 - kill-curve chance at the damage drawn) x (effective HP - damage drawn) / theirs x mine, "product" = Daniel's SUM(future damage) x SUM(future vulnerability) / team size; carried into the objective as a cost in the mover's HP (`Extras.team_cost`, added to the PSR cost); the mover's damage taken is what it draws under that distribution. |
| Multi-unit: whom a unit shoots / fights | `bots.choose_target` -> `forces.choose_target` (Gladiator) / `princess_group.choose_target` (Princess) / `kill_curve.choose_target` (Gladiator's fire director) | One target a turn. Gladiator with 2+ enemies on the board: `config.STUB_GLADIATOR_TARGET` (2026-10-29). "kill_curve" is Gladiator's own FIRE DIRECTOR (2026-10-29, Daniel: "splitting fire to wreck 2 units is better then hard killing 1 and grazing the other"): each enemy scores worth x [f(declared + mine) - f(declared)], f = its kill curve (`INTEGRATION__kill_curve`: chance of a mission kill from N more damage, 5-point groups, on the side this unit hits), declared = the team's damage map, worth = the enemy's damage a turn (`KILL_CURVE_WEIGHT`), plus a tiny kill-progress tie-break; its declaration is counted for the teammates after it. What counts as a mission kill: **STUB** `stubs.stub_mission_kill`, `config.STUB_MISSION_KILL` ("destroyed" default / "no_ranged_weapons"; spotting has no worth yet). The stub choices (**STUB** `stubs.stub_gladiator_target`, Daniel: "a good test to stub in until we teach gladiator how to focus fire and account for target saturation"): "princess_plan" (default) borrows Princess's choice below, scored through Princess's fire control (`bots.princess_eyes`), and Gladiator's own declaration goes into the team's damage map (`bots.records_declared_damage`); it still picks its own weapons. "nearest" is the old pick: an enemy in sight beats one not, then one a weapon can bear on (arcs and torso twist, `attack_resolution.weapons_can_bear`), then the nearest. Princess: the enemy whose firing plan has the highest utility (a dry run of the real weapon choice, `declare_attacks(dry=True)`), the damage friends already declared counted (next row). Physical attacks: the declared charge / DFA target, else an adjacent enemy. No secondary targets (p.64): a plan has one target, as in MegaMek's ordinary Princess. |
| Princess: fire distribution | `princess_fire.overkill_fraction`, `princess_fire.assign_damage`, `princess_group.choose_target` | `FireControl.calcDamageAllocationUtility`: an enemy the team's earlier declarations are expected to destroy (damage >= its total HP) scores 100 x -30 (the unit fires at another, or nothing); below half its HP nothing is charged; between, the fraction of its HP x -30. The damage map is per team, filled as each unit declares in order (`Princess.damageMap`), emptied at the start of every Ranged Attack Phase, and ignored in a movement guess. |
| Princess: movement in a battle | `princess_group.Group`, `princess_modern._rank` / `princess._rank` | rankPath over ALL enemies: my firing and physical damage the best of any one, damage taken summed; distance / aggression / facing against the closest enemy by adjusted distance (an enemy yet to move counts farther by its walking MP); facing the closest enemy if beside the spot, else the median of the 4 closest (Weiszfeld, `facing_enemies`); an enemy too far for either side to reach adds nothing (`can_matter`, speed only). Posture is the FORCE's (`force_posture`: once a round, the enemy's mean distance to the centre of the team, kept in `princess_memory`). |
| Princess: mutual support, crowding | `princess_group.Group.support_mod` / `crowding_mod`, `princess_memory` | Mutual support (v0.50.07 "herd mentality"): distance from the end spot to the force's HOT SPOT (heat map: each Princess move credits its end hex with BV - 100 x max(jump, walk) MP; fades each turn - halves where none of the force stands, -200 where one does; the nearest of the top-rated hexes) else the friends' average position; x `mutual_support` (index 0-10 -> 0.1..2.0, default 5 = 1.0). Crowding (`anti_crowding`, default 0 = off, MegaMek's default): 10 / (11 - slider) per unit within ceil(1.3 x slider) hexes (friends, the mover itself at its start included) or within 60% of its range (enemies). `config.PRINCESS_GROUP = False` turns both off. |
| Battle Value | `INTEGRATION__battle_value.battle_value` | BV 2.0 from MegaMek's `BVCalculator` / `MekBVCalculator` / `HeatTrackingBVCalculator`; item values from MegaMek's classes (`tools/build_equipment_bv.py` -> `mechsim/equipment_bv.json`). Exact on the Atlas AS7-D 1,897, Locust LCT-1V 432, Commando COM-2D 541 and Jenner JR7-D 875; as built (`current=False`) or as it stands (`current=True`), with or without the pilot skill. Not modeled: armored components, C3 / TAG bonuses, Blue Shield, LAMs. |
| Multi-unit: home edges for 3+ teams | `orchestrator._edges_for_teams` | Two teams: p.37 (loser picks, winner gets the opposite). More: lowest deployment roll picks, then the opposite edge, then the two edges across (clockwise of the pick), round again past four teams (a free for all shares edges). Book silent. |
| Multi-unit: stepping out of a domino effect | `config.DOMINO_DODGE` (off) | A 'Mech that passes the domino PSR MAY step one hex forward / back (p.114). MegaMek's bots never do (`BotClient` answers "no action", TODO there), so neither does this one; True makes it step aside whenever a legal hex is free (forward first). |
| Movement selection | `INTEGRATION__movement_selection.choose` | Spot (hex + facing + mode) maximizing the objective - DEFAULT "lifetime" + history blend (row below), or "ratio": dealt×exposure / (received×exposure + movement-PSR cost + .001); first mover scores each spot by the second mover's modeled reply (two-ply, at its MASC / supercharger speed). Which spots are scored: `MOVEMENT_SEARCH` (a mech's own pick) and `MOVEMENT_ASSUMED_ENEMY_SEARCH` (the first mover's modeled reply), per side in `MECH_*_CONFIG` "search" / "assumes_enemy_search" - "grid" (DEFAULT since 2026-10-21, Daniel's guess and follow: a 1-in-7 hex net from the mover's own hex, `MOVEMENT_GRID_SPIN`, then uphill from the best `MOVEMENT_SEARCH_STARTS` net hexes; a second mover always also looks at the 6 hexes around the enemy - `_grid_search`) or "exhaustive" (every spot, "perfect"); for a first mover's own pick also "if_then" (Daniel's IF/THEN, 2026-10-28 - `_if_then_search`: hold still first ("If I hold still then..."), then best spot against that spot's modeled reply, back and forth while the two-ply score rises; keeps the last attempt that rose; also stops on a repeated spot; `MOVEMENT_IF_THEN_STEPS` = fixed steps instead; then `MOVEMENT_IF_THEN_NEIGHBOUR_CLIMB` climbs to better neighbouring hexes; a second mover scores every spot. Daniel: meant for multi-unit threat vectors of farther units, not a single 'Mech's default); for the modeled reply also "short_list" (DEFAULT since 2026-10-24, Daniel's simple short list: hexes next to the first mover, the replier's own, and at the ranges where either side's damage drops most - `short_list_distances`, `MOVEMENT_SHORT_LIST_DROPS` - each mode once at its best TMM, facing the first mover). Knobs: config MOVEMENT SETTINGS. |
| Movement objective option (+ history blend, `MOVEMENT_LIFETIME_HISTORY_K`) | `movement_selection._Ratio` / `_Lifetime` (`config.MOVEMENT_OBJECTIVE`) | "ratio" (default, above) or "lifetime": dealt + (effective HP left / enemy future damage) x own future damage (`INTEGRATION__future_damage`: 0.5 x best heat-limited expected damage at gunnery + walking +1 + the target's best TMM, kicks / punches at range 1). Each side scores its own spots with it, the modeled reply too |
| LOS exactly between two hexes (p.56) | `pathfinder/los._evaluate` (`worse_key`) | The target's controller picks the hex; the bot always takes the MORE obstructive one (blocking first, then woods). The pick is the same from either end (checked on all 12,060 such pairs of the 16x17 board), so p.56's "used for all attacks between those two 'Mechs ... for the rest of that turn" holds without storing it. Not modeled: a target choosing the clearer hex to shoot back better; p.56's random pick for a non-player target (a hex attack takes the more obstructive one too). Partial / off-board hexes are never picked (p.56: "LOS cannot be shifted so that it passes through a partial hex") |
| Movement-PSR cost | `movement_selection.psr_costs` | P(fail) × fall damage, only for Run / Jump with a Movement-Phase PSR trigger; damage-caused PSRs ignored (Daniel) |
| Armor-exposure weighting | `movement_selection.exposure_factors` | Per-side vulnerability from current armor + structure (front = 1.0, clamped) |
| No-LOS / out-of-range movement fallback | `movement_selection.closing_fallback` | Ported as-is from `combat_turn._closing_fallback` (cases A/B1/B2); nearest-to-enemy otherwise |
| Heat-constrained weapon selection | `INTEGRATION__weapon_selection.py` | Which weapons fire this turn, built and wired |
| Heat ammo explosion bin (controller's choice) | `INTEGRATION__stubs.stub_heat_explosion_bin` | **STUB.** Which of several equally destructive, equally full bins explodes (random). |
| AMS engagements | `INTEGRATION__ams.engage` | Which missile hits each AMS takes (the ones it cuts most first; a Narc pod counts half its worth - 1D6 4+ - and nothing once a pod is on), cheapest-heat AMS first; skips an engagement that would end the turn above max(max_heat, `config.AMS_HEAT_LIMIT` = 13). Expected damage (weapon choice, movement) scales each missile weapon toward its engaged value by min(1, engagements / missile weapons) |
| Ammunition kind / guidance / Apollo mode per shot | `fire_modes.Planner` -> **STUB** `stubs.stub_munition_choice` | LB-X slug / cluster, ATM standard / ER / HE (iATM also IMP / IIW), inferno / standard missiles, MML LRM / SRM, Artemis / Narc-equipped / standard missiles, Narc homing / explosive pods, Apollo standard / saturation, bombast 8 / 12 / 16. Research (Daniel 2026-10-20); default "greedy" |
| Rate of fire (Ultra / Rotary AC) | `fire_modes.Planner` -> **STUB** `stubs.stub_rate_of_fire` | Research; default "max" |
| Unjam a Rotary AC | `fire_modes.declare_unjams` -> **STUB** `stubs.stub_unjam` | Research; default: always try unless prone |
| Narc beacon worth | `electronics.pod_value`, priced by `fire_modes.Planner` | A homing pod is worth one turn of the owner's extra Narc-missile damage (Daniel) - 0 once a pod is on or the target has ECM; explosive pods their damage. Not in movement scoring |
| Worth of heat put on the enemy | `config.TARGET_HEAT_WORTH`, `fire_modes.Planner.value` | 0.5 damage per heat point - placeholder until Daniel sets it |
| Worth of a Taser hit's effect (TO:AUE p.158) | `config.TASER_EFFECT_WORTH`, `fire_modes.Planner.value` | 5 damage - placeholder until Daniel sets it (2026-10-27) |
| Worth of a TSEMP hit's effect / of IMP missile effects (Interstellar Operations) | `config.TSEMP_EFFECT_WORTH`, `config.IMP_EFFECT_WORTH`, `fire_modes.Planner._advanced_worth` | 5 damage a TSEMP hit; 2 a level of IMP effect - placeholders (2026-10-28). The firer's own TSEMP interference isn't priced |
| Worth of a nail / rivet gun hit | `advanced_weapons.nail_worth` | 3.5 x the chance the hit lands on a location with no front armor left (2026-10-28) |
| Closing in on a hazardous board | `movement_selection._safest` (closing fallback, nearest spot) | only the spots with the least hazard damage (2026-10-27) |
| Ammo bin to draw from | `INTEGRATION__ammo.spend` | The bin with the fewest shots left (empties bins sooner) |
| Prop arm when firing prone | `INTEGRATION__attack_resolution.prone_fire` | The arm whose weapons matter least |
| Physical attack type | `INTEGRATION__physical.choose_attack` | Twist (if still allowed) + attack type (punch / kick / physical weapon / club / push) with the most expected worth, weighted by hit table (`physical.Worth`) |
| Ranged fire vs the physical attack that follows | `attack_resolution.declare_attacks` (`_physical_planner`) | Next to the target: best (arc action, physical plan) by ranged expected damage without the attacking limbs' weapons + the plan's expected damage (raw on both sides) |
| Torso twist / arm flip / turret | `declare_attacks`, `physical.choose_attack`, `ranged_combat.MoveEvaluator` | Most expected damage; no change wins ties (Section 4a) |
| Charge / death from above | `movement_selection._movement_attack_pick`, `_modeled_reply`; `INTEGRATION__movement_attacks` | Gate per movement mode (beat the best ordinary attack), then the objective must beat the ordinary pick; both movers (two-ply) |
| Push value | `physical.push_option`, `movement_attacks.displacement_worth` | P(hit) x (target HP off the board / fall worth 2+ levels down / else 0) |
| Turning while down | `orchestrator._turn_while_down` | A prone mech that can't stand (fight to the death): fewest hexside turns that put the enemy in its forward arc, else a side arc; none if nothing improves (1 per turn with a destroyed gyro, p.98). The two-ply reply model doesn't anticipate it |
| Charge with spikes | `stubs.stub_charge_spikes` | STUB (`STUB_CHARGE_SPIKES`, default always): declare torso spikes for a charge (p.196) - +2 damage a cluster vs losing clusters |
| Raise a shield | `stubs.stub_raise_shield` | STUB (`STUB_RAISE_SHIELD`, default never): raise at the start of an attack phase (p.195) - more cover vs nothing behind it attacks |
| Activate a vibroblade | `stubs.stub_vibroblade` | STUB (`STUB_VIBROBLADE`, default on): fixed damage + heat vs tonnage damage (p.196) |
| Command console swap | `stubs.stub_console_swap` | STUB (`STUB_CONSOLE_SWAP`, default when the pilot is out or more hurt): End Phase seat swap (p.203) |
| Blue Shield on / off | `stubs.stub_blue_shield` | STUB (`STUB_BLUE_SHIELD`, default "on"): switched at the start and each End Phase (p.207); Memo: only against PPCs, and weigh the stealth it negates |
| PPC capacitor at the start | `stubs.stub_capacitor_start` | STUB (`STUB_CAPACITOR_START`, default "empty"): start the battle charged (p.188); Memo: the PPC-charging bot session |
| Charge a PPC capacitor | `stubs.stub_capacitor_charge` | STUB (`STUB_CAPACITOR_CHARGE`, default "never"; "when_idle" = whenever the PPC isn't fired): charge instead of firing (p.188); Memo: weigh 5 heat now and each turn held against +5 damage, and let weapon choice see the holding heat |
| Fire TAG | `stubs.stub_fire_tag` | STUB (`STUB_FIRE_TAG`, default "when_useful": the 'Mech has homing artillery rounds): designate the enemy before the Ranged Attack Phase (p.200); Memo: the twist / flip TAG may use first, semi-guided rounds |
| TAG aim | `stubs.stub_tag_aim` | STUB (`STUB_TAG_AIM`, default "mech"; "hex" / "easier"): designate the enemy or the ground it stands on (Daniel 2026-10-21: ground is easier, homing then does 5 AE to the 'Mech - "a bot logic question") |
| Club pick-up | `INTEGRATION__clubs.maybe_pick_up` | ON (`config.CLUB_PICKUP`, Daniel 2026-10-21): picks one up on a turn it fires nothing; smarter use waits for the Memo below |
| DFA miss: where the target steps | `INTEGRATION__dfa.resolve` | The open hex with the smallest drop |
| Home edge | `config.HOME_EDGE_CHOICE` | Which edge the deployment-roll loser picks (default random) |
| Escalating Failure use (radical heat sinks, MASC, supercharger) | `equipment_systems.use_escalating` -> **STUB** `stubs.stub_escalating_use` | Research (Daniel 2026-10-20); default "cycle" = Daniel's 1-turn-on / 1-turn-off |
| Coolant pod trigger | `INTEGRATION__heat._extra_cooling` | One pod when heat would stay above min_heat, not on a radical turn |
| Heat-sink switching | `INTEGRATION__heat.choose_heat_sink_deactivation` | End Phase: how many sinks stay on so min_heat can be reached |
| Aimed shot location | `config.AIMED_SHOT_LOCATION` | Where shots at immobile targets aim (default Center Torso) |
| Candidate reduction | `movement_selection.reduced_options` | Max FC (min MP) per (hex, facing, mode, fc>0); Void-Signature exempt |
| Best-reply selection | `movement_selection._modeled_reply` | Wired (two-ply) |
| `compute_score()` | `PATHFINDER__combat.py` | Not wired (reference; built on flat HP/weapon dicts) |
| LOS border-line side | `pathfinder/los.py` | The target picks the side worse for the attacker, whole line (p.56; F41) |
| Closing-turn detection | `movement_selection.closing_fallback` | Wired (ported) |

| Which bot decides for a unit | `INTEGRATION__bots.bot_for` (`config.BOT`, `MECH_*_CONFIG["bot"]`) | "gladiator" (DEFAULT - every row above) or "princess" (the clone below). Routed through `bots`: the Movement Phase pick (`choose_movement`), the weapon choice (`fire_control` around `attack_resolution.declare_attacks`' arc loop) and the physical attack (`choose_physical`). Every other row (ammunition kind, rate of fire, MASC, AMS, heat sinks, clubs, aimed shots...) is shared |
| Princess: movement | `INTEGRATION__princess_modern.choose` ("modern", DEFAULT) / `INTEGRATION__princess.choose` ("0.50.07") - `config.PRINCESS_VERSION` | BasicPathRanker.rankPath (below) |
| Princess: posture | `INTEGRATION__princess_modern.posture` | ATTACK, or DEFEND while the enemy closes 0.5+ hexes a round (3-round window); once a round, kept on `mech.princess_memory` |
| Princess: weapons and twist | `INTEGRATION__princess_fire.FireControl` via `weapon_selection.fire_control` | FireControl's plan utility and heat plans (below); the twist / flip with the best utility |
| Princess: physical attack | `INTEGRATION__princess_fire.choose_physical` | PhysicalCalculator.getBestPhysicalAttack (below); no new twist |

### Princess clone (Daniel, 2026-10-27) - as built

**Two versions, `config.PRINCESS_VERSION`** (Daniel, 2026-10-27: "Clone the
entire modern suit for Princess"): **"modern"** (DEFAULT) = MegaMek main at
commit `fd2edfb` (2026-10-26), cloned with `git clone --depth 1 --filter=
blob:none --sparse https://github.com/MegaMek/megamek.git` (git works through
the proxy; `megamek/src/megamek/client/bot` is 55k lines, mostly aerospace,
infantry, artillery, formations, convoys - not used by a 'Mech duel). A 'Mech
still gets `BasicPathRanker` (Princess.getPathRanker), the same validation,
FireControl and PhysicalCalculator; what changed is in
`INTEGRATION__princess_modern` (ranker: posture, close-range incentive,
squaring up, position hold + water sustain boost, movement / cover discounts,
physical threat weights, water hazard) and `INTEGRATION__princess_fire`
(tolerance with movement heat and the TSM ceiling, the TSM heat incentive,
crits / kills by damage on a hit). Module docstrings have the formulas.
**"0.50.07"** = the classic ranker below, kept (it reproduces the earlier
recorded runs exactly). Not ported from modern, beyond the v0.50.07 list
below: standoff for artillery / TAG 'Mechs, sprinting, unit orders, mutual
support / crowding / formations (no friends in a duel), forced withdrawal,
the enemy / friendly memory (FightMemory, EnemyTracker - multi-unit).
[Session 13: mutual support, crowding, the friendly heat map and the damage map
ARE ported now - `INTEGRATION__princess_group`; formations are CASPAR's.]

Reference: MegaMek **v0.50.07** `megamek/src/megamek/client/bot/princess/`
(+ `client/bot/PhysicalCalculator.java`, `princess/geometry/`). Fetch with
curl from `raw.githubusercontent.com/MegaMek/megamek/v0.50.07/...` (github.com
itself is blocked, raw is not). Chosen over `main` / v0.51: the classic ranker
(2,074-line `BasicPathRanker`), before the postures, doctrine and standoff
layers. Behavior: `config.PRINCESS_BEHAVIOR`, sliders 0-10, default 5 =
MegaMek's "DEFAULT" (fall shame 500, bravery 1.5, hyper-aggression 2.5,
self-preservation 15). The RULES stay the project's (to-hit, LOS, arcs,
cluster hits, ammunition kinds, AMS, water) - Princess's own parts are the
CHOICES. The module docstrings have the formulas; in short:
- **Movement** (`INTEGRATION__princess`): utility = -P(fall) x fall shame +
  [P(success) x (my fire + my physical) x bravery - damage taken] -
  hexes to the enemy x hyper-aggression - 50 x hexsides off the ideal facing
  beyond 1 (the ideal turns toward the better-armored side). Enemy already
  moved: both sides' guessed firing-plan utility from the real positions
  (Princess's FireControl in guess mode inside a `MoveEvaluator`, so the
  project's to-hit and twists) + kicks that hit more often than not. Enemy
  still to move: summed weapon damage at the range of the closest hex of its
  reachable area (MegaMek's `ConvexBoardArea` / `HexLine`, ported) x 0.25,
  + a flank kick; mine only if its whole area is inside my firing wedge.
  Spots out of range (or farther, if not in range now) and spots under the
  fall tolerance (0.75) are dropped first. One ply - no look-ahead.
- **Fire control** (`INTEGRATION__princess_fire.FireControl`): plan utility =
  (expected damage + 10 x expected criticals + 50 x kill chance) x
  log10(2 x target's range-1 damage + 10) - 30 x damage / target HP (when
  0.5+) - 5 x heat over (sinks - heat - stealth heat + 5). Heat plans built
  level by level; best utility, nothing if no plan beats 0. Princess ignores
  `max_heat` / `min_heat` (they are Gladiator's).
- **Physical** (`choose_physical`): punch (each arm / both), kick, club /
  physical weapon, push, each P(hit) x damage x punch-through bonus; kicks
  + the target's fall - its own from a miss; a push = the target's fall (its
  armor off the board). Best above 0.
- **Not ported** (each a candidate follow-up): charges and DFA (v0.50.07
  Princess never declares them); forced withdrawal / self-preservation (no
  crippled rules yet, Pick up here 5); herding, crowding, favor-higher-TMM
  (0 in a duel at the default sliders); hazards on the path's middle hexes
  (end hex only: water, rubble, mud); MASC odds in P(success); RAC unjamming
  and spin-up; ammo conservation; the "move to contact" re-rank; Princess's
  centre-of-board aim before the enemy enters (it heads for the enemy's home
  edge, as Gladiator does); damage already assigned by friends (a duel).
- **Known difference from MegaMek**: ties keep the first spot in the
  project's order (MegaMek's TreeSet keeps the first path it ranked).

### Memo: the bot must weigh how an action changes its FUTURE capabilities (Daniel, 2026-10-20)

Every decision so far is greedy for the current turn. Several need the bot to
ask what an action does to what it can do on later turns:
- **Clubs.** Picking up a tree costs the Ranged phase and (Daniel, "IIRC")
  the arm and front-torso weapons while it's held; "the question is if the
  utility of having a club is greater than the weapons you're armed with. The
  answer is almost always no - I've never seen anyone use a tree as a club."
  Pick-up is ON since 2026-10-21 (only on turns with nothing better to do) until this exists.
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
  movement problem (`INTEGRATION__HISTORY.md`, "Pick up here" item 2).
- **Breach risk in water (2026-10-21, G21 - notes only, Daniel: "Save the
  notes but don't implement it yet. Its related to an Idea I have for how to
  cost cluster weapons and the use of risky equipment. That is also for
  another session").** Today a spot in water is scored for its benefits
  (submerged heat sinks, partial cover, the water line) and its falls
  (halved), but not for hull breaches (p.127). Claude's plan, which Daniel
  called "close to what I'm thinking": for each underwater location that
  would take damage at a spot, add P(breach) = 1/6 (2-4 on 2D6) x that
  location's breach cost; price a breach as losing everything in the
  location (as the bot already values a destroyed location - a breached leg
  counts as destroyed, a torso's engine / gyro slots); a location with no
  armor left breaches for certain the moment it goes under. Wait for
  Daniel's cluster-weapon / risky-equipment costing idea - the same shape
  (expected value of a chance of a big loss) should serve all three.
Not designed yet - Daniel: "when we get to figuring out how the bot should
think." A natural shape is a value for the mech's state at the end of the
turn (weapons usable, heat, jam / failure risk, a club in hand) added to the
turn's score, so a decision sees what it gives up.

---

## 7. STANDING PROMPTS

- (Daniel, 2026-11-04) **Art changes run only the art checks.** "I'd also stop with the 50 checks. We're not messing with the
  core code, we're messing with visual assets that would plug into the program, but are otherwise separate. Run only checks
  that are related to that." For Combat Lab visuals (INTEGRATION__tokens / token_mesh / shell / shell_items / shell_facet,
  tools/token_*, data/token_*): tests/test_token_shell.py, test_token_joined.py, test_token_volume.py. Engine changes still run
  tests/run_checks.py.

- (Daniel, 2026-10-28) **Label every session's work for review.** "Label the
  work you did today with a note to have a higher level model review it when
  there are spare cycles, make that a standard order going forward." At the
  end of each session, add what was built to Section 0's REVIEW QUEUE, and mark
  its Change Record entries "REVIEW PENDING (higher-level model)". A reviewer
  clears the line when done.
- (Daniel, 2026-10-28) **A question the rules can't answer: MegaMek first, then
  Daniel.** "If you encounter a question that can't be answered in the rules,
  consult how megamek does it, then me if its still a question." (MegaMek's
  source: `add_repo` / clone `MegaMek/megamek` - Section 0's setup.) Used so
  far: the Unequal Numbers split for more than two sides (`TurnOrdered`:
  each side takes ceil(its turns / the smallest side's)), and the domino-effect
  dodge (MegaMek's bots never step aside - `BotClient`).
- (Daniel, 2026-10-21) **"Follow the rules, not my calls."** Where the Core
  Rulebook answers a question and an earlier call of Daniel's differs, the
  rulebook wins - change the code (or the switch's default) and say so. The
  exception is a switch he keeps for SPEED, not as a rules opinion:
  `FIGHT_TO_THE_DEATH` stays off ("it saves time when the situation is
  hopeless"), with the rules-as-written version one switch away.
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
  a bug first. Sign work in the Change Record (`INTEGRATION__CHANGE_RECORD.md`).
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
- (Daniel, 2026-10-21) A/B batch size: "We really need to do smaller test
  batches. like 20 runs is probably enough to show a major change ... Can do
  longer tests if something looks very off, or if we're establishing a longer
  baseline during down time." Default `tests/ab_batches.py 20 ...`; battle n of
  a batch always gets the same seed, so 20 battles repeat the first 20 of an
  older batch (compare against its saved rows in `run_stats/ab/`). Judge
  totals (wins, damage, HP, turns), not "same winner": one different move
  re-rolls the rest of a battle.
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
  Multi-slot items whose row says 1 slot get read as one weapon per slot
  (HVACs, mortars, TSEMPs, Improved ACs / missiles all did) - check the
  parsed weapon count against the unit's Weapons list.
- (Daniel, 2026-10-28) "Build what could be used. Custom units are and will
  be a thing" - build every option of a rule a unit could carry (all ammo
  kinds, effects for every unit column a 'Mech can be), not only what
  `data/meks.zip` carries today.
- (Daniel, 2026-10-28) Bot studies: "only run the more interesting test
  series. We're after general feel, not full stats" - name only the pickers
  / settings that matter and use few battles; a full battery only when he
  asks for one.
- (Daniel, 2026-10-28) Stats a rulebook paste or table doesn't give (slots,
  shots per ton, a weapon's range / heat): "megamek's values to use" -
  borrow from MegaMek's source (main branch) and cite it in the
  equipment.json note / the code. Rules text Daniel pastes counts as the
  library (cite the book and page he gives).

---

## 8. CHANGE RECORD

Moved to `INTEGRATION__CHANGE_RECORD.md` (2026-11-10), word for word. New entries go at the top of that
file. "Change Record" anywhere in the code or the documents means that file.
