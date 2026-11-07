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

## 0. WHERE WE ARE (2026-11-06, end of session 19) — read this first

**NEXT TOPICS (Daniel, 2026-11-06)** - his list: individual bot logic; group bot logic; more speed;
GUI; Combat Lab functionality; (speed: done for now - 12 v 12 about 3x faster, Daniel may go for a full Rust rebuild next week, see Change Record "DECISION"); 3D art for the Combat Lab (art paused: "We've spent most of the week on
3d"; its next step stays the weapon-block stockpile). Also raised by Claude and open: the unbuilt rules
(buildings / bridges, crippled + forced withdrawal, spotting / indirect fire, C3, special munitions),
refreshing the rules zip with TO:AUE / TO:AR, the anti-stall rule, other unit types, scenario features
(objectives, fog of war), the engine port. **OUTPUT** - STARTED 2026-11-06 (session 20): the battle statistics report is built, stages 1-3 of 5
(Change Record "BATTLE STATISTICS", Section 5 "Battle statistics"); what is left is listed there. Daniel was asked
what the Monte Carlo should report and sorted three AIs' lists with Claude.
Session 19 (2026-11-06) was review work by the higher-level model: the queue was empty then, the map
seams follow MegaMek, the baseline battery moved to the 32 x 17 field (INTEGRATION__BOTS.md).

**REVIEW QUEUE - needs a higher-level model's review when there are spare
cycles** (Daniel's standing order, 2026-10-28; Section 7). Items (a) to (l) were reviewed
2026-11-06 (Change Record "REVIEW: KILL CURVE, RUST, FIRE TABLES; MEGAMEK MAP SEAMS" and "REVIEW QUEUE
CLEARED"). New work goes into this queue:
  - **(m) BATTLE STATISTICS** (session 20, 2026-11-06; Change Record "BATTLE STATISTICS"). Review: the three
    engine hooks only read (`attack_resolution.run_ranged_phase`, `physical.run_physical_units`, the
    orchestrator's turn loop); the per-attack damage is a total-HP difference around each attack (so a hit that
    sets off an ammo explosion counts the explosion); kill credit = first attack that leaves the target
    destroyed; the analysis in `INTEGRATION__stats_report.py` (Wilson interval, percentiles, the "held at its
    final state" curves); and the page (`INTEGRATION__stats_viewer.html`).
  - **(o) TIERED MOVEMENT ORDER** (2026-11-07, Change Record "TIERED MOVEMENT ORDER"). Review: `INTEGRATION__tiers` (the four tiers from the footprints; `pick`; `flankers_of`), the hooks in `forces.movement_order`, `orchestrator` and `legate.foe_for`, `tests/test_tiers.py`; the two placeholders (union footprint, any-neighbour flank).
  - **(n) RUST SPEED WORK** (session 20, 2026-11-06; Change Records "RUST PORT STEP 1" to "STEP 6", "RUST EVALUATE
    LOOP: TRIED, MEASURED, NOT KEPT" and "DECISION"). Review: each Rust copy is the Python's step for step -
    `fastcore.FastTable` (`weapon_selection.FireTable.choose`; `fire_modes.Planner.price_spec`), `PathBoard`
    (`pathfinder._build_terrain_psr` and `ranged_combat._movement_options`, incl. the entry-order quirk where the picker
    reads a state's FIRST PSR count), `LosBoard` (`los._evaluate`) and `hex_distance` (round half to even); the
    Python caches (`damage_resolution.get_weapons` / `derived`, `structure_weight.multipliers`, `_ScorerContext`,
    `fire_state`'s `_damage_state`) invalidate on the right events (slot loss, turn start, battle start; smoke for the
    LOS snapshot); the new tests (`test_fastcore.py`, `test_fire_tables.py` with `FIRE_TABLE_VERIFY` and
    `WEAPONS_CACHE_VERIFY`) really exercise the Rust (they fail on a silent fall back, except as noted in the
    movement-search entry). Everything has the Python as fallback (`config.USE_FASTCORE`, `FASTCORE_PRICING` /
    `_MOVEMENT` / `_LOS`).
When a review is done, move its line out of this queue and note it in the
Change Record.

Latest art work: **Session 18 - SKELETON-AND-SHELL MODELS, THE FACETED LOOK, THE WORKBENCH** (2026-11-04 to 11-06, Change
Record; REVIEW QUEUE (l)). The 'Mech art is now built from the units' own data: each location's volume from its mass (bulk by
structure points, legs x1.6 for their myomer, actuators as art mass), a skeleton, myomer and internal equipment inside an armor
shell, every crit-holding item on a hardpoint. Daniel chose the FACETED look (one shaped solid per part, after a low-poly Mad Cat
print) over the plated one; it is built from a library of interchangeable blocks (13 slots: pose, torso, waist, head, gun
housing, missile mount, pauldron, arm, forearm, hand, leg, knee, foot; tags pick them, else a per-slot name hash) on the eight-
chassis test range (`tools/token_3d.py --range`, the published viewer). Each slot can be reviewed alone with its mounting brackets
(`tools/token_lineup.py`), and any combination can be set by hand in the WORKBENCH (`tools/token_workbench.py`; Daniel runs it on
his PC from the bundle `tools/make_workbench_bundle.py`; a setting comes back to Claude as a "CLW1." code: `--code`).
**NEXT on the 3D side (Daniel, 2026-11-06): a stockpile of WEAPON BLOCKS** - the weapon models are still the first-pass ones
(`INTEGRATION__shell.item_geometry`); build interchangeable weapon blocks per family (lasers, PPCs, autocannons, Gauss, missile
racks, machine guns, flamers, plasma...) in the same library style, reviewed by lineup and in the workbench. Then: torso / head
blocks for the bird body, the 47 chart chassis (phase 2, after the dictionary is built up), directional equipment hardpoints
(shields, electronics). Art checks only for this work (Section 7).

Latest engine work: **Session 17 - SAVED STATES** (Daniel, 2026-11-03: the board, the units and their state,
and the dice, so "the engine will just continue from there"; branches keep the same dice by default,
fresh dice a switch). Built: `INTEGRATION__saved_state.py` - a save at the end of any turn
(`config.SAVE_STATE_TURNS`), a file of JSON (a readable header + the exact state packed), play on with
`python INTEGRATION__saved_state.py <file> [--turns N] [--fresh-dice SEED]`. The check: every reference
battle saved, reloaded and played on from the reload after EVERY turn matches byte for byte
(`check_reference_logs.py --round-trip`), and so do team battles with Legate and Princess
(`tests/test_saved_state.py`). It found one real trap: destroyed equipment was recorded by memory
address, so a reload revived it - the save now re-points those records. Before it, the RNG clean-up:
one pool of dice per battle (`tests/test_rng.py`). Next: Pick up here 16.

Before that: **Sessions 14-15 - GLADIATOR IN TEAM BATTLES** (Change Record, newest first;
`INTEGRATION__BOTS.md` sums up how both bots decide and every battery since). Session 14: the kill
curve and fire director, big-guns-first firing order, Daniel's team-awareness options. Session 15:
Daniel's five suspects measured with `tests/legate_probe.py`; the fire split now covers this turn's
damage too and is the default (8 / 4 / 8 v Princess, from 8 / 8 / 4); the cohesion reward (off -
it groups the force but doesn't win more). Open work: Pick up here 00000.

Earlier: **Session 12 - MULTI-UNIT BATTLES** (Daniel, 2026-10-28: "Multiple units
that can be assigned to multiple teams. The ideal ranges would probably be a 4
unit lance and a 12 unit company vs like forces. But a 20 unit free for all or
a 3 way battle between different lances are also possibilities... For the
moment we're just getting to the point where we can unleash a group of bots to
operate independently."). A battle is now a LIST of units on any number of
teams: `config.FORCES = [{"team": "Red", "mtf": "Atlas AS7-D.mtf", "count": 4},
{"team": "Blue", ...}]` (None = the old Red vs Blue duel, byte-identical: all 15
reference logs match). New: `INTEGRATION__forces` (teams, Initiative for any
number of sides, the Unequal Numbers rule - Core p.41, who a bot plans against
and shoots at), `INTEGRATION__domino` (displacement into an occupied hex: the
domino effect and the accidental fall from above, pp.113-116),
`orchestrator.run_skirmish`, `results.summarize_teams`, a replay viewer for any
number of units and teams, `tests/test_multi_unit.py`. The bots are INDEPENDENT:
each unit's bot (Gladiator or Princess) plans its movement against its nearest
enemy (`forces.choose_foe`) and fires at the enemy it picks
(`forces.choose_target`: in sight, a weapon bears, nearest); it does not model
its other enemies or coordinate with its team - that is Pick up here 00
(Daniel's IF/THEN threat picture, mutual support, fire distribution). Speed: a
4v4 Kontio / Hammerhead battle takes ~40 s (13 turns); cost grows with the unit
count (~0.5 s a unit a turn) - run big battles with `config.WORKERS`.
Decisions the book doesn't make are in Section 6 ("Multi-unit").

**Session 13 - PRINCESS FOR TEAMS + BATTLE VALUE** (Daniel, 2026-10-28: "Are
there any Princess features that need to be updated now that multi-unit mode is
enabled?" ... "I think 1-5 are do able. 6 requires us to calculate BV, which is
also doable and needed for human integration. As usual use Megamek as source
material where needed."). Built from MegaMek main 7205e4d (v0.50.07 checked for
the same code where it exists): (a) FIRE DISTRIBUTION - a Princess unit picks its
target by the best firing plan against every enemy it can see (MegaMek
`getBestFiringPlan`), with the damage its friends already declared this phase
counted (`calcDamageAllocationUtility`: an enemy they are expected to kill scores
100 x -30, so the unit turns to another); (b) MOVEMENT against every enemy, not
just the nearest (rankPath: my best damage on any one, all their damage to me;
the closest enemy by walking-MP-adjusted distance; the median of the 4 closest
to face), the FORCE's posture (once a round, from the centre of the team),
MUTUAL SUPPORT (a pull toward the force's remembered hot spot or the friends'
centre, 1.0 a hex at the default) and ANTI-CROWDING (slider, default 0 = off, as
MegaMek's default); (c) the heat map behind the hot spot, weighted by BATTLE
VALUE; (d) `INTEGRATION__battle_value`: BV 2.0 for a 'Mech, exact on the four
published values and matching others (Warhammer, Griffin, Shadow Hawk, Awesome).
NOT built, and why: secondary targets - MegaMek's ordinary Princess fires every
weapon at ONE target (only multi-tasker / multi-trac crews use
`MultiTargetFireControl`), so the clone does too; the highest-BV cluster anchor
- MegaMek uses it only for standoff artillery and TAG spotters; formations -
`MutualSupportPathRanker` is the CASPAR doctrine, a different bot. Switches:
`config.PRINCESS_GROUP` (off = the old duel Princess), `PRINCESS_BEHAVIOR`
`mutual_support` / `anti_crowding` / `facing_enemies`. A duel is unchanged with
PRINCESS_GROUP off (hash-identical logs, both versions); ON, a lone Princess is
pulled toward its own earlier ground too (MegaMek does that: its heat map holds
its own moves) - Princess vs Gladiator won 7 -> 5 of 20 (noise), Princess vs
Princess 12 -> 12.

**Session 13, second half - LEGATE** (Daniel, 2026-10-28: "making gladiator
less myopic"). `INTEGRATION__legate` + `config.LEGATE` (OFF by default): at the
start of each Movement Phase an IF/THEN estimate for ALL units at once (12
rounds; two units wanting a hex - higher picker score wins, the loser takes its
next best, cascading; a unit that loops is locked) says where each side's
enemies will go; a Gladiator plans against the most threatening enemy yet to
move, with every other enemy's damage added to each spot's score (taken = sum,
dealt = max). Design: its docstring, Section 6 row "Legate", Change Record.
20-battle comparison, Princess (Red) v Gladiator (Blue), 12 v 12, same seeds:
with Legate Gladiator deals 24% more damage and Princess loses 1.4 more 'Mechs,
but neither wins more (Princess 15 v 14 wins, 5 v 6 cap draws, Gladiator 0) and
a battle takes 1.8x as long. ON BY DEFAULT since 2026-10-29 (Daniel), after the stub + Legate run (Change Record).
**Next (Daniel is starting a more dedicated session):** Legate speed pass; the
anti-stall item (the cap-draw stragglers, Pick up here 0); Legate's to-do list
(Pick up here 000: map reading, concentrated-fire estimate). Running a battery:
`python tests/baseline_battery.py pg 20 [--legate] --first 1 --last 5` is one
core's share - start four of them (1-5, 6-10, 11-15, 16-20; add `--replay` to
the one with battle 1 to get a page in `replays/`, then publish it with the
Artifact tool), read each output file, and only then report. Launching a
background command that waits is not the battery finishing.

Previous: **Session 11** (Daniel's IF/THEN movement picker, an option - PRs
#85-#90) and **Session 10** (Tactical Operations terrain and gear,
Interstellar Operations weapons, ultralight and superheavy 'Mechs - PRs
#79-#83) are summed up below, just above "Pick up here"; the open work is
that list. Daniel's multi-unit bot groundwork (IF/THEN as a pre-move threat
picture + a "right now" layer) is in Section 5.

**Session 7 in one paragraph - RULES AND EQUIPMENT (all merged to `main`,
PRs #44-#61):** Daniel: get the environment and physics right before the
bot, and "Follow the rules, not my calls" (except `FIGHT_TO_THE_DEATH`
off, for speed - now a CLAUDE.md working rule). Fixed the known issues
(scatter held in the firing arc, MG array ammo); charge / DFA end-of-move
PSRs and no moving through the enemy; water leftovers; armored components;
cockpits; filler slots can't take crits; LOS rewritten to the book with
heights and prone 'Mechs (`tests/test_los.py`); the PSR special cases;
quad leg damage; clubs (pick-up on). Then the equipment survey (RULES_REVIEW
G23-G34) built with every choice a loud stub, decisions deferred: HD gyro,
heat-dissipating armor, talons / spikes / lance / vibroblades / shields
(`INTEGRATION__physical_gear`), quad kicks, HarJel, command console, APDS,
Blue Shield, PPC capacitors (`INTEGRATION__capacitor`, off by default),
torpedoes, Thumper / Sniper as Arrow IV (Daniel's numbers), TAG and homing
artillery (`INTEGRATION__tag`, TAG may aim at the ground). Left: smoke and
active probes (G34, no smoke source yet); the split-item cleanup (Section
4). New stubs are in Section 6; details in the Change Record (Section 8).

**Session 6 - SPEED (all merged to `main`, PRs #38-#43):**
a speed-only pass (~25%: reply PSR costs once per pick, per-hex rows in
`MoveEvaluator.evaluate`, lazy charge-gate tables, LOS line shapes cached
per offset), then Daniel's "guess and follow" movement search, now the
DEFAULT for both movers (`config.MOVEMENT_SEARCH` /
`MOVEMENT_ASSUMED_ENEMY_SEARCH` = "grid"): a 1-in-7 hex net laid from the
mover's own hex, then climb to better neighbours; the second mover also
always looks at the 6 hexes around the enemy (without that, melee mechs
lost: Kontio 57 -> 38 of 100). Benchmark 14.5 s -> ~3.5 s; `run_checks.py`
~3 min -> ~1 min. Per side (`MECH_*_CONFIG` "search" /
"assumes_enemy_search") each mech can be "perfect" (exhaustive) or "fast".
A/B tooling (`tests/ab_batches.py --set ... --board --seed`); Daniel's rule:
20 battles a setting. Findings: fast is within dice noise of perfect for
both sides; one side searching perfectly helped the favourite (Atlas,
Black Hawk ~+5 of 20) but not the underdog; what a side assumes about the
enemy's search made no consistent difference; grid spin doesn't matter.
Bug fixed on the way: aimed shots with variable-damage weapons (Heavy
Gauss) crashed. Details: Change Record (Section 8).

**Session 5 - MAPS (PRs #32-#36), for reference:**
Daniel's MegaMek map pack is `data/maps.zip` (346 maps, 192 of them 16x17);
`python tests/survey_maps.py` says which play and what stops the rest - 165
of the 192 16x17 maps play (31 did before; the rest crashed, didn't load, or
had buildings / cliffs / water silently ignored). Built (RULES_REVIEW
F24-F32): terrain costs and stacking, road travel, the 2-level climbing
limit, jump landing height; PASSIVE buildings (`config.PASSIVE_BUILDINGS`,
Daniel's option); a load-time refusal of terrain not built yet; the water
rules (`INTEGRATION__water`: depth as level, partial cover, the water line,
underwater weapons and ranges, heat sinks, jump jets, physical attacks,
hull breaches, drowning, halved falls); deployment depth with the stuck-
terrain override (`INTEGRATION__deployment`, the Solaris arenas play); and
Daniel's MOVEMENT SUBPHASE - the picker plans, the mech walks the path
rolling each terrain PSR where it happens (water when running, rubble,
sand, mud, backward level changes) and re-plans after a fall. Reference
battles on Military Base 1 (buildings, cliffs) and Large Lakes 1 (water).
Daniel deferred the full building rules and the breach-risk pricing (with
his cluster-weapon / risky-equipment costing idea) to later sessions.
Details: Change Record (Section 8), Daniel's calls: Section 5.

**Session 4 (PRs #18-#31):** one-command checks; Kontio vs
Hammerhead default; AES; replays; LOS on hex borders; the "lifetime"
movement objective (default); the time tracker; 50-turn reference cap.

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
`python tests/run_checks.py --bench` (about 1 min).

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
`data/` the boards, test mechs and `meks.zip` (4,227 MegaMek units, 4,204
load - only the 23 LAMs don't); `rules/` the rules library zip; `reference_logs/` same-seed sample
battles; `replays/` and `run_stats/` (git-ignored) generated output.

**After any change, from the repo root:** `python tests/run_checks.py` -
one command, about 1 min: every `tests/test_*.py` (23 files, incl. `test_multi_unit.py`) and every
reference battle (15), side by side, one line each, all must pass. Reference
battles stop at 50 turns (`check_reference_logs.TEST_BATTLE_MAX_TURNS`,
Daniel); one that hits the cap prints a NOTE ("a possible flaw") - today
only the Asymptote mirror (the stall, Pick up here 0). A reference log may
differ only when the change is MEANT to alter results - then look at a fresh
battle, run `python tests/check_reference_logs.py --update`, and say so in
the Change Record (Daniel has OK'd regenerating them for intended changes).
For anything on the hot path add `--bench` (10 turns of the Asymptote mirror,
pinned so timings stay comparable - a pure speed change must keep its HP
totals, currently 501 / 495 since the 2026-10-24 short-list look-ahead
default (also 501 / 495 with the exhaustive search; 495 / 495 was the grid
look-ahead's); ~2-3 s in the cloud container (~14.5 s exhaustive); it prints
where the time went). Bot changes: compare with
`python tests/ab_batches.py` (same seeds, several settings side by side, 20
battles a setting - Daniel).

**What's built (all Core Rulebook, page-cited in the code):**
- Batches: `config.WORKERS` battles at once, one per CPU core (0 = all
  cores); each battle has its own seed (`orchestrator.battle_seed`, battle 1
  = SEED) and the output is identical for any worker count
  (`tests/test_parallel_batch.py`). `BattleResult.seed` replays a battle.
- Movement: `INTEGRATION__movement_selection.choose` scores reachable spots,
  exposure- and structure-weighted, TWO-PLY for the first mover (the
  modeled reply now moves at its MASC / supercharger speed). WHICH spots:
  DEFAULT since 2026-10-21 (Daniel) the "grid" search - Daniel's guess and
  follow: a 1-in-7 hex net laid from the mover's own hex, then climb to
  better neighbours; a second mover also always looks at the 6 hexes around
  the enemy - for its own pick and as the first mover's assumed reply
  (`config.MOVEMENT_SEARCH`, `MOVEMENT_ASSUMED_ENEMY_SEARCH`, per side in
  `MECH_*_CONFIG` "search" / "assumes_enemy_search"); "exhaustive" = every
  spot ("perfect", ~4x slower). DEFAULT objective
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
  pick-up ON since 2026-10-21, pushes, charges, DFA), each weighted by its own hit table.
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
  scatter). Optional rule `POOL_CLUSTER_DAMAGE` (Daniel's; default False since
  2026-10-21 - the rules as written):
  cluster damage of one grouping size is summed before grouping.
- Remaining loud stubs (`INTEGRATION__stubs.py`): weapon data gaps
  (`ammo_data`, `unconfirmed_weapon_data`, `unknown_damage_type`),
  `heat_explosion_bin` (a controller choice), and the weapon-use decisions
  (`munition_choice`, `rate_of_fire`, `unjam`, `escalating_use` - MASC /
  supercharger / radical heat sinks).

**Rules review:** `INTEGRATION__RULES_REVIEW.md` - the Core Rulebook vs the
code: what was fixed (F1-F56), the gap list (G rows; open: G16 special
munitions, G18 choices, G21 breach pricing, G22 buildings, G34 smoke /
probes), and the Core-vs-project questions (D1-D8 decided). Read it before
building rules.

**Session 8 (2026-10-24):** Daniel's two-ply research - the second
mover's reply comes from a short list of places (next to the first mover,
standing still, range-bracket ends), so the first mover's look-ahead now
checks only those (`MOVEMENT_ASSUMED_ENEMY_SEARCH = "short_list"`, the
default), each hex scored roughly (best TMM, facing the first mover). ~1.5x
faster a turn, results within noise of perfect knowledge. Details and
numbers: Change Record (Section 8).

**Session 9 (2026-10-27) - BOTS PER UNIT, PRINCESS, PICK QUALITY (all merged
to `main`, PRs #66-#77).** Daniel: "The ability to select what type of bot
each unit uses. The current system ... shall be called 'Gladiator'. I would
like to make a clone of Megamek's Princess bot to compare it against."
- `INTEGRATION__bots`: `config.BOT` / `MECH_*_CONFIG["bot"]` = "gladiator"
  (default) or "princess"; routes the move, the weapon choice and the
  physical attack. `weapon_selection.fire_control` lets a bot's own thinking
  use its own weapon choice (scoped - the other bot never sees it).
- Princess, two versions (`config.PRINCESS_VERSION`): "modern" (default,
  MegaMek main fd2edfb, `INTEGRATION__princess_modern`) and "0.50.07"
  (`INTEGRATION__princess`); fire control and physical choice in
  `INTEGRATION__princess_fire`; sliders `config.PRINCESS_BEHAVIOR`. Getting
  MegaMek's source: `git clone --depth 1 --filter=blob:none --sparse
  https://github.com/MegaMek/megamek.git` works through the proxy (Section 6,
  "Princess clone"). Not cloned yet: Pick up here 00.
- Gladiator search options: "Short-Short" (`MOVEMENT_SEARCH = "short_list"`,
  both movers pick from their own short list, best few states a hex) and its
  grid prune (`MOVEMENT_SHORT_LIST_GRID`); defaults unchanged ("Short Grid", the
  official name since Daniel, 2026-10-28).
- Studies (not in run_checks): `ab_batches.py --set bots / bots-classic /
  short-short`; `tests/bot_agreement.py` (pick agreement, time, operations);
  `tests/pick_quality.py` (every bot's pick priced on Perfect Knowledge's
  scale, 8 scenarios incl. kiters; `movement_selection.SCORE_SINK`). 4 boards
  and 8 'Mechs added to `data/` for them.
- Findings (Change Record): Gladiator beats Princess in every seat (modern
  Princess better than classic, most as a brawler); Princess is ~3x faster a
  decision than Short Grid, ~16x than Perfect; the short-list rules of thumb
  hold (Short Grid 94% of Perfect's score range, no closing bias; Short-
  Short 87%); Princess closes when it needn't (+2 to +2.6 hexes) and hides
  out of line of sight on bad trades (18% moving second); Gladiator breaks
  off on bad trades (27% moving first) but NOT more as it gets hurt.

**Session 10 (2026-10-27/28) - TACTICAL OPERATIONS EQUIPMENT AND TERRAIN,
INTERSTELLAR OPERATIONS WEAPONS, ULTRALIGHTS AND SUPERHEAVIES (all merged to
`main`, PRs #79-#83).**
Daniel: "The tactical operations books have been indexed ... wire in
functionality of missing weapons, equipment, and hex types already noted.
If there is anything beyond those categories needed to match megameks level
of base functionality ask before including them." Built from the TO:AUE /
TO:AR summaries in `logajam/battletech-rules-index` (RULES_REVIEW F57-F64):
- Hex types: magma (crust / liquid, bogging down) and hazardous liquid pools
  (new `INTEGRATION__hazards`), ultra-heavy woods / jungle, impassable,
  fortified and planted-field hexes. 174 of 192 16x17 maps play (was 165);
  bridges, fuel tanks and elevators still wait on the full building rules.
  Both bots price the hazards (Gladiator: path + end hex; Princess: end hex,
  ported from MegaMek's calcMagmaHazard / calcHazardousLiquidHazard).
- Weapons (new `INTEGRATION__advanced_weapons`): HVACs (ammo, misfeed,
  smoke), 'Mech mortars (AP shells, direct and indirect fire), the Taser,
  fluid guns / VGLs (no effect on 'Mechs), flail and chain whip.
- Equipment: shoulder / head turrets (`INTEGRATION__arcs`), modular armor
  (new `INTEGRATION__advanced_equipment`); smoke and active probes (G34, new
  `INTEGRATION__smoke`).
- Data fixes: HVAC, mortar, fluid gun, flail, chain whip slot counts (each
  slot had been read as its own weapon).
- Interstellar Operations (2026-10-28, Daniel pasted the rules; MegaMek's
  values for stats the pastes don't give - RULES_REVIEW F66-F69): TSEMP
  Cannon / One-Shot / Repeating, iATM (a Streak when fired directly) with
  ER / HE / IMP / IIW rounds, inferno missiles (Core p.192 - needed by IIW,
  any unit's inferno bins now fire), Improved weapons' slots and ammo, the
  nail / rivet gun (MegaMek's rule). Industrial tools deferred (Daniel).
- Ultralight and superheavy 'Mechs (2026-10-28, Daniel: "Go borrow from
  megamek to get superheavy and ultra light mechs working" - RULES_REVIEW
  F70-F71): MegaMek's structure table (10-15, 105-200 tons) and superheavy
  slots (two items a slot, half the slots each), the Core superheavy
  appendix (pp.236, 240-241). All 42 such units in data/meks.zip load; only
  the 23 LAMs still don't.
- Daniel's answers (2026-10-28): 'Mech UMUs and the chain whip grapple -
  DEFERRED (Pick up here 10); Princess now prices hazards on every hex of
  her path like MegaMek ("Need the change for an acurate replica");
  `TASER_EFFECT_WORTH` stays 5 and joins the research pile (item 3); every
  Gauss rifle now explodes when hit ("Fix it").

**Session 11 (2026-10-28) - IF/THEN PICKER (PRs #85-#90).** Daniel's IF/THEN first-mover
picker (`MOVEMENT_SEARCH = "if_then"`, an option, not the default): best
spot against the enemy where it stands, then best spot against that spot's
modeled reply, back and forth while the two-ply score rises. Measured with
`tests/pick_quality.py` (now 7 pickers) - first mover 85% of Perfect's score
range vs Short Grid's 96%, ~2 hexes closer to the enemy than Perfect, 102 ms
a pick vs 174 (Short Grid) and 1,218 (Perfect). Then (Daniel) the first
attempt became "If I hold still then...": on the two worst scenarios 81.5 ->
84.0% of range, lean in +3.3 -> +2.2 hexes, but it now holds still on 34% of
first-mover picks (Perfect 8%). Fixed steps (`MOVEMENT_IF_THEN_STEPS = 12`,
Daniel): 84.0 -> 88.9% of range for +50 ms a pick (198 ms; Short Grid 281,
Perfect 2,309). Then a closing climb to better neighbouring hexes
(`MOVEMENT_IF_THEN_NEIGHBOUR_CLIMB`, Daniel's "option 2"): 12 steps + climb
94.5% of range, about Short Grid's time. Daniel: IF/THEN is for multi-unit
threat vectors of farther units, not a single 'Mech's default (Section 5).
Full battery (8 scenarios x 20): first mover 94.5% of range (Short Grid 96.1,
Short-Short 91.0), same time as Short Grid - Daniel: "a fairly strong
prediction level". Settings to use it: `MOVEMENT_SEARCH = "if_then"`,
`MOVEMENT_IF_THEN_STEPS = 12`, `MOVEMENT_IF_THEN_NEIGHBOUR_CLIMB = True`
(the steps default is still 0, the climb). Study tools: `pick_quality.py
--pickers` (only the named pickers) and `--perfect-cache FILE` (Perfect's
prices reused; the file lives in `run_stats/`, lost with the session -
rebuild it with one full run). Numbers: Change Record.

**How the bots work now:** `INTEGRATION__BOTS.md` (2026-10-29) - Gladiator v
Princess, decision by decision, the latest battery and why Gladiator loses.

**Pick up here (open, roughly in priority order):**
000000. **THE PERIL HEAT MAP (the top-down approach; Daniel, 2026-11-07) - IN PROGRESS, start here. STAGES 1-4 DONE (2026-11-07): `INTEGRATION__vision` (the table, ordered pairs because the to-hit modifier is NOT symmetric: 14% of random pairs differ, LOS itself is; 2.1 s for the 544-hex field), `INTEGRATION__peril` (`unit_field` / `team_field`, peak and mean; 0.07 s for a 10-unit side), `tests/test_peril.py` (5 checks), `tests/peril_picture.py` (a page per saved turn). Next: 5 (shortcut accuracy tests), 6 (Legate's move score uses the field; switch; A/B). Not done yet: arcs for stand-still units, disk cache of the table, smoke refresh call (`vision.invalidate` exists, nothing calls it).** Where things stand
   (the pivot after the tiered order proved uninformative): Daniel's design - for every unit, its weapons' damage-over-range
   table is projected from it (the damage at each distance), the firing arcs are covered by rotating it (a unit that can move
   chooses its facing at the end, so for it the damage reaches every direction; arcs bind only a unit that cannot turn - start
   omnidirectional, add arcs for stand-still units), the table is SMEARED over the unit's movement footprint (the outer
   perimeter of each movement mode: peak damage it could bring to a hex from any spot it can reach, or the same weighted by how
   likely each spot is), and a LINE-OF-SIGHT map filters it (no LOS: nothing; woods / partial cover: the to-hit modifier
   scales the damage). One field a unit; a team's Peril is their sum; when a unit moves its own movement interacts with the
   field ("super position of movement x damage x counter movement collapsing to the best spot"). Daniel's refinements:
   SMART LOS BLOCKING (a hex that blocks a line blocks everything past it at the same or lower level) and PARTIAL LOS TESTING
   (test only the footprint's corners, or the short list). My reading, measured on 2026-11-07: the per-board visibility table
   is STATIC, so those two refinements speed the one-time build (2 s on the 544-hex field, ~42 s for 3 x 3 boards at
   7 us a pair under load) and the per-turn lookups, not a per-turn LOS cost; the corner-sampling shortcut changes ACCURACY,
   so build the exact version first and score each shortcut against it. Stages: (1) the visibility + modifier table per board
   (numpy; `los_cache.pair_info`; cache on disk; refresh when smoke changes); (2) per-unit damage-by-range profiles -
   `future_damage.range_profile(attacker, target, extra_tn)` is DONE (a refactor of `future_damage`, committed); (3) the exact peril field, `INTEGRATION__peril` (new): uses
   `tiers.footprint` for the spots; peak and expected versions; modifier classes 0-3 from the visibility table; one unit at a
   time so memory is one N x N table; (4) a picture: heat maps from a saved battle turn (`tests/turn_inspector.py`
   `make_state` gives the states) as an Artifact page; (5) the shortcut accuracy tests; (6) Legate's move score uses the
   fields (a switch), A/B on the 100-battle baseline (INTEGRATION__BOTS.md). Later (Daniel): Legate reads the board for good
   terrain (cover that sees: only partial cover, elevation, arcs and range differences are asymmetric, since LOS itself is
   symmetric); Legate holds back until most of its combat power can engage at once. Numbers: the cost per turn is about
   spots x targets in range lookups (~1 M a side on the current field), tens of ms with numpy, 1.5 s or more in plain Python;
   memory is one table at a time (24 MB at 2,448 hexes) - NOT the limit.
00000. **Cohesion and the open biases** (session 15 diagnosis, Change Record 2026-10-30): Gladiator's
   units end alone about twice as often as Princess's, worse late (47% v 22% with no friend within 4
   hexes). The cohesion reward (`LEGATE_COHESION`, Daniel's design, off) fixes the spread - "either"
   pairing at x0.5 matches Princess's cohesion - but no setting wins more battles than none: the
   spread may not be what loses them. Open: why (moves spent on cohesion instead of firing spots?
   check with the probe's regret / dealt figures). Gladiator
   rates its own damage ~25% high (incoming is right) - find where the movement model and the fire
   phase's dry run part. The team value / exchange options were built on the old, unshared damage
   count: worth re-running on top of the new default.
0000. **Team awareness and the topics after it** (Daniel, 2026-10-29, "thinking
   out loud" - topics to design, nothing built). The fire director
   (`INTEGRATION__kill_curve`, STUB_GLADIATOR_TARGET "kill_curve") is the first
   piece: it prices damage as kill chance x the enemy's output.
   - **Team awareness:** "Gladiator needs to have a sense of how its actions
     affect the enemies board state and its own teams board state. The example
     case is 'Move to a location that is more exposed, because it will draw
     fire away from a vulnerable unit, preserving future firepower.'" Claude's
     note: the kill curve works for our own units too, so a move could be
     scored by the enemy's likely fire allocation (their side's fire director)
     with this unit at that spot: the team's expected firepower lost, summed
     over its units (output x kill chance), not just this unit's.
   - **Team health value** (Daniel, 2026-10-29): "the shape of the team health
     value should be something like SUM(all future damage)*SUM(All future
     vulnerability). Where it goes into, or at what scale it goes into the
     picker I'm not really sure. Numerator side, might replace the units own
     future damage value (Since in a 1 on 1 it collapses into the same
     number.)" BUILT as an option to compare: `LEGATE_TEAM_VALUE = "product"`
     (divided by the team's size for scale) beside "sum" (each unit's own
     lifetime term summed); where it belongs is still Daniel's call.
   - **Incoming fire** (Daniel, 2026-10-29): "Gladiator should be aware of
     incoming fire, the likelyhood of its own destruction, and the likelyhood
     that fire will be split by its rules. So it can seek adverse exchange
     ratios with the enemy." BUILT: `LEGATE_FIRE_SPLIT` (the future share)
     and `LEGATE_TEAM_VALUE` (Daniel: "aware of the expected distribution of
     enemy fire at the start of its turn ... how that distribution changed
     across its entire force, and the expected loss of future damage") - this
     turn's fire distributed over the team, each unit's kill-curve chance of
     destruction, the team's future damage in the move score.
   - **Herding** (Daniel, 2026-10-29): "a penalty for being past medium range
     of any unit in the force ... IF a mech stands still its range of support
     should increase. Somehow LOS should be involved. You can't support a mech
     if you can't see its enemies." BUILT as `LEGATE_HERDING` (`legate._Herd`;
     weights are placeholders until A/B'd).
   - **Movement order hierarchy:** which of a team's units moves first. Today
     both bots use Princess's move index (`forces.move_index`: faster units
     closer to the enemy move later). Daniel, 2026-10-29: "We'll continue to
     use Princess's movement heirarcy for now."
   - **Firing order hierarchy:** which declares first. BUILT 2026-10-29 as
     Daniel's rule, "Big guns first followed by smaller guns. Its the same
     rule used on a mech, just applied to the entire formation."
     (`config.GLADIATOR_FIRE_ORDER`, Section 6 activation-order row).
   - **Active choice systems** (a whole host: rate of fire, ammunition kind,
     MASC, AMS, shields, capacitors, aimed shots... today mostly stubs) -
     ideally priced in one currency (the kill curve's).
   - **Indirect fire valuation** (spotting isn't built; its worth also decides
     STUB_MISSION_KILL: a gunless 'Mech that can spot).
000. **Legate** (Daniel, 2026-10-28: "making gladiator less myopic ... a multi-unit
   bot layer at the start of the movement phase ... in charge of keeping tabs on
   the battlefield") - BUILT as a first version (Change Record; `config.LEGATE`,
   off by default until Daniel has seen the numbers). TO DO, in Daniel's words
   or close to them:
   - **Read the maps and find tactically useful terrain** ("Eventually I will
     want Legate to read maps and determine tactically useful terrain
     features"); for now it only lets Gladiator keep track of the whole enemy
     force.
   - **How much fire one unit would really take** - the estimate's score sums
     every enemy's damage on a spot; "need to add an estimate of how much
     actual fire a single unit would take. Which is part of figuring out how
     concentrated fire should be calculated" (Daniel: "This will change later").
   - **Speed** - the estimate roughly triples a Gladiator battle's time at 12 v
     12 (Change Record); evaluators are cached per foe's estimated spot, the
     estimate is run per side with a Gladiator.
   - Open questions: on by default? The Princess clone could read the same
     estimate. Gladiator's second mover (the foe already moved) scores only
     spots in sight of that foe in `_static_scores`, as before.
00. **Princess clone - TODO as the scope grows** (Daniel, 2026-10-27: "All of
   those not cloned features will be needed in the future as the projects
   scope expands. But we can add them to the todo list"). The modern Princess
   (MegaMek main fd2edfb) is built and is an option, `config.PRINCESS_VERSION`
   = "modern" (default) / "0.50.07". Still to clone, each when the project
   has what it needs:
   - **Forced withdrawal** - crippled units retreat to their edge and flee,
     hold fire unless fired on (ForcedWithdrawalTracker, self-preservation
     mod, Princess.calculatePhysicalTurn); needs the crippled / withdrawal
     rules (Pick up here 5).
   - **Standoff for artillery and TAG 'Mechs** - Arrow IV / artillery units
     hold back past their minimum range, TAG spotters keep a designation band
     and a priority target (evaluateStandoff, desiredStandoffDistance,
     spotter priority, shoot-and-scoot); the project already has Arrow IV and
     TAG (F55-F56).
   - **Sprinting** (TacOps) - the sprint exposure penalty; needs the sprint
     movement rule.
   - **Multi-unit play - the GROUP behaviors** - BUILT in session 13 (Change
     Record): fire distribution, multi-enemy movement, the force's posture,
     mutual support, anti-crowding (slider), the BV-weighted heat map, BV.
     Daniel's IF/THEN pre-move threat picture + "right now" layer is built for
     GLADIATOR as Legate (Pick up here 000; the Princess clone doesn't use it).
     Still open: FightMemory / EnemyTracker (infantry in buildings / the
     experimental ranker - not used by a 'Mech); the enemy heat maps (fog of
     war - this project's bots see every unit); secondary targets and a
     MultiTargetFireControl for crews with multi-tasker / multi-trac (the rule
     itself, Core p.64, is not in the engine: a Daniel scope call); the
     highest-BV cluster anchor (artillery / TAG standoff only); formations
     (the CASPAR `MutualSupportPathRanker`, a separate bot).
   - **Unit orders, towns, convoys, deployment planning** - scenario features.
   - Other gaps listed under Section 6 "Princess clone" (hazards on a path's
     middle hexes, MASC odds, RAC unjam / spin-up, ammo conservation, the
     "move to contact" re-rank, aerospace, infantry).
   Open too: whether Short-Short (+ grid prune) should become the default (Daniel's
   call - 3 matchups A/B'd so far, Change Record); a self-preservation pull
   for a badly hurt Gladiator (it breaks off on bad trades, never because it
   is hurt - goes with item 5).
0. **Anti-stall rule for the bot** (Daniel, 2026-10-21: "Anti-stall rule for
   the bot is added to the future tasks list"). Under the lifetime default,
   mirror matches stall: the Asymptote mirror ran 488 turns (shots in only 55),
   because with equal future damage each side fights only when a trade beats
   1:1. Design it with Daniel (ideas so far: force an attack after N turns
   without firing); test with `tests/ab_batches.py` and replays. Reference
   battles are capped at 50 turns meanwhile, and every batch summary flags
   battles that hit the turn cap.
1. **Speed for multi-unit battles** (session 12): a 12v12 took ~9.5 s a turn;
   ~60% of it was `ranged_combat.movement_options` (each unit's reachable
   spots). DONE (2026-10-28): `pathfinder._BoardCache` - a lazy per-board
   cache of hex info and step cost / PSRs / hazard per (hex pair, level
   limit), so a search only computes its own footprint and overlapping
   footprints (other units, next turn) reuse it - plus finished tables
   shared between identical requests. Table-building time halved (profile
   12.3 -> 5.7 s); 4v4 -25%, 12v12 2 turns 26.5 -> 12.5 s; logs identical.
   What is left, in order: the reply scoring (`_modeled_reply` /
   `MoveEvaluator.evaluate`, ~8 s of the 18 s profile; top-few spots only
   would change results - A/B it), `_entry_options` on the entry turn
   (75k yields; fewer edge hexes), the search loop itself (~1.8 s), and the
   table reuse found few matches (24 of 439 builds - same-start requests are
   rare). A speed-only change must keep the benchmark (501 / 495) and every
   reference log. Sample replay (4v4 Kontio / Hammerhead, seed 21):
   https://claude.ai/artifact/FnXQK7huREYBfhGcM4cEMX
   Stitched boards for company-size fights: DONE 2026-10-28 (`STITCH_MAPS`).
1a. **Speed** (Daniel: "We still need more speed") - largely done in session
   6; next steps only if runs get slow again. Session 6: ~25% off the
   exhaustive search (Change Record), then the grid search as the default
   (~4x). With the EXHAUSTIVE search the two-ply look-ahead is ~95% of run
   time: every first-mover spot (300-630) x every reply spot (400-630). Reply scoring (`MoveEvaluator.evaluate` for each modeled reply)
   ~70%, the per-reply loop in `movement_selection._modeled_reply` ~20%,
   reply charges / DFA ~3%. Pure-Python tuning is near its floor (~3 memo
   lookups a pair); the next big steps are fewer pairs (e.g. two-ply only the
   best spots by the static score - changes the bot, Daniel's call, test with
   `ab_batches.py`) or the compiled hot path (item 9). A speed-only change
   must keep the benchmark's HP totals and every reference log.
   **Guess and follow** - the default since 2026-10-21 (A/B results in the
   Change Record): both movers with the second mover's always-checks = ~3.5-
   4.5x, results within noise (Kontio 57 -> 61 of 100). Watch: 5 of 100
   Kontio battles hit the turn cap (exhaustive 1).
   Open follow-ups (Daniel's to call, none started): (a) confirm with a
   longer down-time run that a perfect search really helps the favourite
   (Atlas vs Kintaro, Black Hawk vs Bombardier: +5 of 20 - the only
   knowledge results beyond noise); (b) the reply search could also climb
   from more than one start, or the first mover could get extra always-
   checks if a matchup shows the grid missing narrow peaks; (c) mechs
   pushed off the board edge aren't priced in movement scoring (item 6) -
   0 vs 4 of 60 in one grid A/B, small numbers.
   **Future (Daniel, 2026-10-24: "explore short list vs short list at some
   point in the future when there are more tokens available"):** a deeper
   run of the short-list look-ahead on BOTH sides (the default since
   2026-10-24) - more matchups and battles than the short 12-battle check in
   the Change Record. Watch Kontio vs Hammerhead: both short-grid went 9-2
   against 5-5 for both perfect (the isolation run put it on the grid
   search, not the short list). `python tests/ab_batches.py N red blue
   --set short-vs-perfect` (and `--set short-list`).
2. ~~**Known issues Daniel asked to fix later**~~ - both fixed 2026-10-21
   (scatter held inside the firing arc; machine gun array ammo). Section 4.
3. **Research: how the bot should decide** rate of fire, MASC use and which
   ammunition (Daniel, 2026-10-20) - today stubs (`STUB_MUNITION_POLICY`,
   `STUB_RATE_OF_FIRE`, `STUB_UNJAM`, `STUB_ESCALATING_USE`); goes with the
   future-capability Memo (item 4). Daniel's ideas: (a) a lookup table of
   known best solutions per weapon by range and starting to-hit number;
   (b) raise a cluster weapon's expected value by its odds of a critical hit
   given the target's armor. **Ammo conservation for Gladiator** (Daniel,
   2026-10-29: "Add conserving ammo to the to do list for gladiator"): in
   battle 10 of the 12 v 12 battery, Gladiator's Emperor fired its Rotary
   ACs at the "max" rate and was dry by turn 20 of 50, and by turns 30-40
   nearly every LRM, Gauss, Ultra and LB-X on both sides was empty (Change
   Record, session 14). Gladiator should weigh rounds left against the
   battle still ahead (rate of fire, and whether a long, low-odds shot is
   worth a round); Princess's own rationing is in MegaMek. Deferred: specialty ammo. Placeholders to set:
   `TARGET_HEAT_WORTH`, and `TASER_EFFECT_WORTH` (Daniel, 2026-10-28: "Good
   enough for now. Add it in the same pile as deriving the value of cluster
   weapons"); `TSEMP_EFFECT_WORTH`, `IMP_EFFECT_WORTH` (same pile,
   2026-10-28). Questions for Daniel: Section 4.
4. **The bot's future-capability planning** - Section 6 "Memo" (Daniel,
   2026-10-20). Needed for clubs, MASC, Rotary ACs (jam risk) and similar.
5. **Crippled / forced withdrawal** (Daniel, 2026-10-20): an option plus a
   bot movement-picker override - not started.
6. Attack-caused PSRs (kick, club, push, charge, DFA, 20+ damage) aren't
   priced in movement scoring - Daniel's rule so far is "only Movement-phase
   PSRs count". A bot target choosing the clearer hex on a two-hex LOS line
   (p.56) isn't modeled (Section 6).
7. **Maps - leftovers** (RULES_REVIEW G7, G20-G22): water done (F36); the movement subphase (mud's -1 isn't
   priced - bot); prone LOS height done (G7, F41); Section 4
   "Map terrain waiting on rules" (Daniel is hunting the rules);
   `PROMPT_FOR_MAP` and `STITCH_MAPS` both work (2026-10-28).
   - **Hull-breach risk in movement scoring (G21) - DON'T BUILD YET**
     (Daniel, 2026-10-21: "Your plan is close to what I'm thinking. Save the
     notes but don't implement it yet. Its related to an Idea I have for how
     to cost cluster weapons and the use of risky equipment"). The plan and
     the gap: Section 6 Memo, "Breach risk".
   - **Deferred to a later session (Daniel, 2026-10-21): the full building
     rules** (G22 - forced entry, inside, damage, collapse, support limits,
     bridges; pp.53, 130-136; "probably a discussion first"). Passive
     buildings stand in until then.
7a. **DONE (session 7, Daniel 2026-10-21: "Continue with the rulebook
   items. Wire in equipment that requires choice (Like capacitors) but defer
   the actual bot decision making for later.")** - RULES_REVIEW G23-G33 built
   (F43-F54), each choice a loud stub; Thumper / Sniper artillery (F55); TAG
   and homing artillery (F56). Smoke and active probes (G34) built in
   session 10 (F64 - the HVAC is the smoke source). Thumper / Sniper
   shots per ton and heat: answered (F55). Every new choice is a stub with
   a Section 6 row, waiting for the bot sessions.
8. **PPC capacitors** (Daniel, 2026-10-21: "PPC charging is a bot logic
   question that requires its own session"): the rules are BUILT (2026-10-21,
   `INTEGRATION__capacitor`, RULES_REVIEW F53); left for that session is the
   decision - the two stubs `STUB_CAPACITOR_START` / `STUB_CAPACITOR_CHARGE`
   (off by default), and weapon choice seeing the 5 holding heat. ~65 units
   in `data/meks.zip`.
9. Later (Daniel agreed 2026-10-20): a setup shell GUI (the replay viewer
   exists); a compiled hot path (Cython / Rust for `MoveEvaluator.evaluate`)
   once the rules settle - not a rewrite; evolutionary tuning of the bot's
   settings with batches (discussed 2026-10-20, not started).
10. **Deferred TO:AUE items (Daniel, 2026-10-28: "Defered")**: 'Mech UMUs
   (TO:AUE p.107 - submarine-style movement under water, 1 MP a UMU, +3 to
   its own attacks; needs underwater elevations in the movement search) and
   the chain whip's arm grapple (TO:AUE p.101 - needs TO:AR's grappling
   rules; the leg trip is built). Industrial tools - chainsaws, drills,
   hoists... (TechManual / Total Warfare; Daniel, 2026-10-28: "Defering
   industrial tools").
11. **Physics gaps left (survey 2026-10-28, for Daniel to pick from - none
   started):** LAMs (23 units - their own movement system, flight); fire,
   snow / ice and extreme temperatures (Core pp.120-123 - matter once a map
   or setting turns them on; inferno missiles setting hexes alight goes
   with fire); G18 choices (bombast laser charging; HAG flak and distant
   Arrow IV barely matter in a ground duel); G12 (charging after a backward
   step); the torso twist a TAG shot uses up; TO:AR optional rules (wind,
   smoke drift, magma eruptions). Every weapon on every unit that loads now
   fires with real ammo counts. The rest of the open work is bot decisions
   (items 3, 4, 8) and placeholder values.
12. **Combat Lab GUI (wish list + spec, Daniel via GPT, 2026-10-30 - none
   started):** `INTEGRATION__COMBAT_LAB.md` - Part A the idea pile (interactive
   replay, branches, bot comparison, heat maps, tokens, MegaMek import, bot
   plugin adapter), Part B the spec to build (tabbed Windows-3.x-style
   `CombatLab.exe`: Units / Map / Options / Results / Replay). Item 9's setup
   shell GUI is its first stage. Foundation both need: a full-state snapshot
   per phase (the replay is output only today). Open for Daniel: tkinter + `.exe`
   v. HTML front end (Daniel 2026-10-31: HTML, like MekBay - click the `.exe`, the
   browser shows it, works offline on his own PC); `.blk` later (orbital fire
   support, thousands of units), 'Mechs stay `.mtf`.
13. **(2026-11-06: PARTLY DONE - see Change Records "RUST PORT STEP 1-6"; the full rebuild is Daniel's maybe for the
   week after, "DECISION" entry.) NEXT WEEK (Daniel, 2026-10-31): condense the physics core into something
   faster.** The game physics are essentially complete (changes only for bugs);
   ongoing work is bot behaviour, which can stay in Python. Plan: survey the
   hot path first (`INTEGRATION__timing`; `MoveEvaluator.evaluate`, LOS,
   expected damage), pick Rust or Cython, port the physics behind a narrow
   API, keep the bots in Python calling it. Safety net: the reference logs and
   `tests/run_checks.py` must stay byte-identical (a speed-only change, CLAUDE.md).
   PyPy tried 2026-11-03 (Change Record): no gain - once warm it ties CPython 3.13.
   Rust tried 2026-11-03 (Change Record, `fastcore/`): exact and 3.4x per call on the weapon knapsack,
   but that is 5.7% of a battle (~1% gained); caching two weapon-kind checks in Python gained ~8%.
   Rust pays for a big piece done per call on flat data (the per-spot scoring), not small kernels.
   Weapon-choice lookup tables (Daniel's design, 2026-11-03): ~5% on a 12 v 12 - the rows asked are
   genuinely many (152k a 2-turn 12 v 12); building them (per-weapon pricing) is the next target.
   **BACK BURNER (Daniel, 2026-11-03: "We're hitting diminishing returns it feels like. There are
   more profitable tasks.")** When it comes back: (a) a cheaper `weapon_selection.fire_state` (~84 us,
   ~3% of a 12 v 12); (b) cache each weapon's price per (distance, pre-TN) across sides / twists /
   targets - the row-building cost; (c) then the full Rust port of that per-weapon pricing loop.
   Watch the boundary: bots call the evaluator thousands of times a move, so
   the API should score many spots per call, not one. Supersedes item 9's
   "once the rules settle" wording. The Combat Lab state snapshot and the
   engine API (COMBAT_LAB.md) should be designed with this boundary in mind.
15. **Combat Lab procedural tokens (Daniel, 2026-10-31 - in progress, saved
   2026-11-01):** `INTEGRATION__COMBAT_LAB.md` (design, reviews, decisions, "Where
   the tokens stand"), `INTEGRATION__tokens.py`, `INTEGRATION__token_mesh.py` (3D), `tools/token_sheet.py`,
   `tools/token_3d.py` (viewer), `tools/token_audit.py` (geometry audit, 2026-11-04), data in
   `data/token_*.json`. Output only; no engine code. Next steps are in the doc (the review pass's
   "what is left" list: skeleton-and-shell rebuild, bevels / smooth shading, decals, an overlap audit).
   **The skeleton-and-shell rebuild has a build spec (Daniel's answers, 2026-11-04):
   `INTEGRATION__COMBAT_LAB_SKELETON.md`** - replaces every block, no exposed internals, hardpoints from the
   critical slots, items sized by slots and mass per slot, volume a sanity band, tags kept, phased from a test range.
14. **MegaMek save import - test it (Daniel, 2026-10-31: "test it and see",
   later, spare cycles):** get sample MegaMek `.sav` files from Daniel, check what a
   save holds and how hard the mapping is (COMBAT_LAB.md, Part A). Last in the Combat Lab order.

16. **Saved states (Daniel, 2026-11-03) - BUILT at the end of a turn** (`INTEGRATION__saved_state`,
   Change Record). Next, in order: (a) saves INSIDE a turn - after each phase and after each unit's
   move (the "what if the Atlas moved here?" point; the turn body `orchestrator._play_turn` has to be
   cut into resumable steps, with the turn's Initiative order, who has moved and the attack reports
   saved too); (b) a replay that starts from a loaded state, and a branch's replay beside the
   original's; (c) a readable engine state (today the exact part is Python pickle) - designed with the
   engine interface for the faster-language port (item 13), since both need the same list of what a
   battle's state is; (d) `--round-trip` in `run_checks.py` if it stays cheap (~20 s today, run by
   hand). Design notes: the module docstring (what is saved, what is rebuilt, the id traps).
**Housekeeping:** reference logs match the code (last regenerated
2026-10-24, session 8: all 15 for the short-list look-ahead default; nothing
in session 9 changed Gladiator's results). Speed history
(10-turn benchmark, HP 501 / 495 with the exhaustive search): 31.7 s → 11.8 s → ~14.5 s (all physical
attacks) → ~25% less (memo sharing) → ~15 s; 16-18 s in session 5's
container, the same as the pre-map code on that machine - compare only like
with like. Hill / water / rubble boards use the path-aware movement search
(~5-10% slower than the plain one). Session 6 speed pass: ~17.9 s -> ~13.4 s;
then the grid-search default: ~3.5 s (HP 495 / 495); the short-list
look-ahead default (2026-10-24): ~2 s (HP 501 / 495). Scratch for map work: unzip
`data/maps.zip` outside the repo; `tests/survey_maps.py` reads the zip
directly.

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
  movement problem (Section 0, "Pick up here" item 2).
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

*(Starts fresh 2026-08-28 — prior history archived/removed, not carried forward.)*

- **2026-11-07 (Claude), PERIL HEAT MAP IN LEGATE'S MOVE SCORE: FIRST A/B (stage 6; `config.PERIL` off / peak / mean, `PERIL_BLEND`; default off). REVIEW PENDING (higher-level model).**
  The field replaces the damage taken from the OTHER enemies (not the foe) in `legate.Extras.adjust`; `peril.field_for` caches footprints and fields for the phase. Princess (Red) v Gladiator + Legate (Blue), the baseline's first 20 battles, seed 12345:
  baseline 8 / 11 / 1 draw (Blue wins / Red / draws), left 1.95 / 2.55, dealt 1345 / 1508; peak x1.0: 5 / 13 / 2, left 1.10 / 3.45; mean x1.0: 7 / 11 / 2, left 1.45 / 3.15;
  peak x0.5: 6 / 10 / 4, left 1.50 / 3.15. None beats the baseline (all a little worse, within the noise of 20 battles); peak is worst. Default stays off. Likely reasons to look at
  next: the field ignores which side of the unit is hit and each enemy's real chance of ending on a spot (peak assumes the worst spot, mean a flat spread); it replaces only the
  other enemies, so the foe term and the field disagree on scale. Not yet tried: weighting the spots (closer to Legate's estimate), arcs, a 40-battle run of the best arm.

- **2026-11-07 (Claude), PERIL HEAT MAP: STAGES 1-4 (visibility table, exact Peril field, tests, picture). REVIEW PENDING (higher-level model).**
  New `INTEGRATION__vision.py`: per-board N x N arrays (seen, to-hit modifier clipped 0..3, distance) from `los_cache.pair_info`, built once per board
  (ordered pairs: the modifier differs with direction on ~14% of pairs, line of sight does not). New `INTEGRATION__peril.py`: for each attacker, its
  `future_damage.range_profile` per modifier class laid over its `tiers.footprint` spots and filtered by the table; `peak` (worst case from any reachable
  spot) and `mean` per hex; `team_field` adds them. Arcs ignored (a mover chooses its facing). `tests/test_peril.py` (5 checks, in run_checks: 53 / 53 pass,
  reference logs unchanged: nothing in the battle uses it yet) and `tests/peril_picture.py` (the heat map of a saved battle turn as a page, pick the target
  and the attacker). Nothing is wired into Legate yet (stage 6).

- **2026-11-07 (Claude), PERIL HEAT MAP: DESIGN AND FIRST STEP (Pick up here 000000). REVIEW PENDING (higher-level model).** Daniel let
  the tiered order rest and chose the top-down peril heat map. First step done: `INTEGRATION__future_damage._ranged_for` and
  `range_profile(attacker, target, extra_tn)` (the damage at every distance, with a to-hit modifier option) split out of
  `future_damage` with no change in results (52 / 52 checks, reference logs identical). The rest of the plan, the reasoning on
  Daniel's two refinements, and the cost figures are in Pick up here 000000.

- **2026-11-07 (Claude), TIERED MOVEMENT ORDER. REVIEW PENDING (higher-level model).** Daniel's design (Ideas phase, same day):
  "units whose movement footprint is completely outside the enemies' ... move first; may intersect ... second; can not
  escape ... last"; slower first; units that will stand still first, farthest first; the tiers also on entering the
  battlefield; tiers 2 and 3 plan their two-ply against the highest-threat unit that could flank them; "not gaming
  winning on its own, but game losing if it is not there against a good opponent". `INTEGRATION__tiers` (module
  docstring has the full rule), `config.MOVE_ORDER = "tiered"` (default "index"), Gladiator units only (Princess keeps the
  move index), `baseline_battery.py --move-order tiered`, `tests/test_tiers.py` (8 checks; 52 of 52 pass, default and
  reference logs unchanged). Footprint = every hex `movement_options` gives; enemy footprint = the union over the enemy
  side; "could flank" = the enemy's footprint reaches a hex next to one the unit could end on. FIRST RESULT (40 battles,
  Princess v Gladiator, seeds 12345 and 2468, v the baseline on the same seeds; Princess / draws / Gladiator): 20 / 8 / 12
  against 20 / 5 / 15, 'Mechs left 3.48 / 1.52 against 2.70 / 1.75, Gladiator damage 1288 against 1349 (seed 12345 4 wins
  v 8, seed 2468 8 v 7): NOT BETTER, inside the noise. Gladiator units lost in turns 1-6 (seed 2468): 2.8 a battle v 2.2;
  units with no friend within 4 hexes about the same. WHY (one battle, Blue's tiers by turn): turn 1 25% safe / 75% may be
  flanked; turns 2-10 about 35% stand still, 50-56% may be flanked, 0-4% safe, 9-12% trapped - the union of twelve enemy
  footprints covers nearly the whole field, so the tiers barely separate units and the order falls back to slowest first.
  The two parts (order, flanker foe) were not tested apart. Next: refine the footprint rule (per enemy, or by how many
  enemies reach), then test order-only and foe-only. Future (Daniel): teach Legate to read the battlefield for good terrain; hold back until most of the
  combat power can engage at once.

- **2026-11-07 (Claude), TURN INSPECTOR; THE "25% HIGH" DAMAGE ESTIMATE SETTLED; MOVE ORDER AND TEAM VALUE RESULTS. REVIEW PENDING
  (higher-level model).** (1) `tests/turn_inspector.py <pp|pg|gg> <battle> <turn> [--unit NAME] [--set NAME=VALUE]
  [--json FILE]` (Daniel: "select a turn in a match, and get a read back of all the math ... a feature and for trouble
  shooting"): plays battle N of the baseline battery to the end of turn T-1 once and keeps the saved state
  (`run_stats/inspector/`), then loads it and plays only turn T with the recorders on - same dice, so the turn is exact
  (checked: battle 1 turn 12, all 24 units' HP and hexes and all 29 shots identical to the batch) and repeatable in
  seconds, or under a changed setting (a one-turn A/B). Prints Legate's estimate v where units ended, each move's
  predicted v real-spot score and regret, each attack's movement-model value v the fire phase's dry run v the ranged
  and physical damage that landed, every shot and physical attack, HP before / after. The recorders moved from
  `legate_probe.py` into `tests/probe_hooks.py` (same output: battle 6 compared turn by turn). (2) The "Gladiator
  rates its own damage ~25% high" item (Pick up here 0000): NOT an error in the damage math (see INTEGRATION__BOTS.md
  Next steps): the ~25% compared structure-weighted points with raw ones, and on 13 battles the model is within a few
  percent at range 2+; the gap is attacks from an adjacent hex (the physical attack that follows, ordinary value about
  2x the real 3 points, and pushes valued at the target's whole HP). Also found: the battle log's damage counters read
  0 for a push that removes the target off the board, and `damage_dealt` counts ranged fire only. (3) Movement order
  (20 battles, Princess v Gladiator): index 11 / 1 / 8, random 10 / 2 / 8, reverse 9 / 6 / 5 - order alone barely
  matters; Daniel wants the tiered order (stand-still first, then out-of-footprint, may-intersect, cannot-escape) built as
  a switch to guard against a strong opponent. (4) Team value re-test: none beats the baseline (BOTS.md). Also
  `baseline_battery.py --exchange / --stats`, `tests/battery_stats.py`.

- **2026-11-07 (Claude), RESUMABLE BATTERIES + MOVEMENT-ORDER SWITCH. REVIEW PENDING (higher-level model).** Daniel: "write the
  driver and make it standard equipment". The sandbox restarted twice during the first movement-order batteries and killed
  them mid-run. `tests/baseline_battery.py` now saves every finished battle at once (whole file, then rename, so never a
  half file) under `run_stats/baseline/saved/<setup, Legate, target, settings, seed, turn cap>/battle_NNN.json` and skips
  a saved battle when the same command is run again (a battle's seed depends only on its number, so saved and fresh are
  interchangeable; `--fresh` ignores them). `tests/battery_summary.py` prints one line a set (wins, draws, 'Mechs left,
  damage dealt, turns) and can read old console logs (`--log`). Also `config.MOVE_ORDER` ("index" default = Princess's
  move index; "random" = a deterministic shuffle seeded from the units' names and hexes, never the battle dice;
  "reverse" = lowest index first) and `baseline_battery.py --move-order`, to measure how much the order within a side
  matters (Daniel's tiered-order ideas, 2026-11-07, are Ideas phase). Default behaviour unchanged: all 51 checks pass. `--stats` (same day, Daniel: "record everything and generate end of game stats for every unit") saves each battle's INTEGRATION__stats event log in its saved file; `tests/battery_stats.py <name>` builds the per-unit statistics page from them (no measurable time cost: 4.85 v 4.88 s a turn on a 3-turn Gladiator v Gladiator test).

- **2026-11-06 (Claude, session 20), DECISION (Daniel): speed work stops here; "maybe go for the full rebuild next week".**
  His reading: the time now lost is translating between the two codes - which the measurements back (the Python /
  Rust boundary, MovementCandidate objects, per-option passes: see the entry below). If the full Rust rebuild is
  taken up, design it so that nothing crosses per option: units, options, hex rows, arc classes and the fire tables all
  live in Rust, and Python (the bots' decisions, config, reports) calls it once per question with whole batches.
  Where things stand: `fastcore/` holds the weapon choice table (+ missile pricing), the movement search, line of
  sight and hex distance, all with the Python as fallback and specification; 12 v 12, 5 turns: 59 s -> 19 s, same battle.

- **2026-11-06 (Claude, session 20), RUST EVALUATE LOOP: TRIED, MEASURED, NOT KEPT. REVIEW PENDING (higher-level model).**
  Daniel: "Go for it" (the `evaluate` rewrite). Built `fastcore.EvalCore`: the per-option arithmetic of
  `MoveEvaluator.evaluate` (to-hit numbers, the best-twist memo, the max over an arc class's FastTables) in Rust on a
  dry board with no AMS, Python keeping the hex rows, arc classes and results (two passes over the options). It gave the
  same battle (reference logs identical, 51 of 51) and NO speedup: 12 v 12, 5 turns, 19.2 s before and 20.0 s with it.
  Reverted (no code kept). Why, measured in real time (not cProfile) on 838,000 options in 4 turns of 12 v 12:
  `evaluate` is 8.7 s of an 18 s run, ~10 us an option, and the Rust-able part (memo + fire-table calls) is only ~1.7 s of
  it; the rest is Python that stays when only the arithmetic moves: building the 627,000 MovementCandidates
  (~0.8 s), 221,000 hex rows (1.3 s), registering ~18,000 scorer groups (1.85 s), the adjacent-hex physical attacks
  (0.9 s, 43,000 calls), and the two passes over the options themselves (~2.5 s). Also tried and dropped (no gain):
  one tuple of scorers per arc class; calling the Rust fire table straight from `score`. What would still help is
  not another kernel: keep each mover's options, hex rows and arc classes alive in Rust between calls (a persistent
  option set), so Python never touches an option per call - a redesign of `evaluate`, Legate's `rows` / `combine` and
  the consumers of MovementCandidate together (movement_selection, Legate, Princess, movement_attacks), estimated
  at <= 1.3x for several million tokens. Running more battles at once (cores / sessions) scales better.

- **2026-11-06 (Claude, session 20), RUST PORT STEP 6: SCORER CONTEXT, AND A CORRECTED CEILING. REVIEW PENDING (higher-level
  model).** Daniel: "Go for it" (the `evaluate` / Legate `combine` rewrite). Speed only: 51 of 51 checks, reference logs
  identical. `ranged_combat._ScorerContext`: the firer's dissipation, weapons, damage table, other heat and the two
  units' `fire_state`s are read once per (firer, target) pair instead of once per scorer (~20,000 scorers in a 4-turn
  12 v 12); `weapon_selection.shared_fire_table` takes the states. 12 v 12, 5 turns: 20.1 -> 19.2 s.
  CORRECTION to the estimate given when asking for the go-ahead ("a second 2.9x"): the region the rewrite would replace
  (`evaluate`, the scorer memo calls, `_hex_row`, Legate `rows` / `combine`) is ~44% of the profiled time (24 of 55 s);
  even a 10x faster Rust version of all of it leaves 33 s of 55: at most ~1.7x more, and only after moving the
  results (MovementCandidate objects, Legate's rows) into flat arrays too. What remains outside it is spread over
  ~40 functions of 1-4% each. So the rewrite is a large, risky change for <= 1.7x; not started - Daniel's call.

- **2026-11-06 (Claude, session 20), RUST PORT STEP 5: MORE CACHES, AND WHERE THE TIME IS NOW. REVIEW PENDING (higher-level
  model).** Speed only: 51 of 51 checks with and without the Rust built, every reference log identical, benchmark
  501 / 495.
  - `damage_resolution.derived` (the `get_weapons` cache's sibling: kept while a battle is played and no slot is lost)
    for `attack_resolution.weapon_locations` and `arcs.mech_turrets`; `future_damage` works out its arc key, blocked
    set and to-hit base once, not at each of ~30 distances; `weapon_selection.fire_state` uses its own cheaper copy of
    the damage signature (`_damage_state`; `kill_curve._signature` itself is untouched - its text seeds the kill
    curve's dice).
  - Honest total, 12 v 12 Gladiator v Gladiator (Legate on), same battle (HP identical), 5 turns, one core:
    59 s before this session's Rust work (main at the statistics PR) -> 20 s now = 2.9x. (Daniel's hope was ~30x: a
    full port; a handful of sections gives ~3x because the time is spread thin.)
  - Where the time is now (4-turn cProfile, 59 s profiled): `evaluate` + Legate `combine` ~49% (its own loop 5%, the
    scorer memo calls ~18%, `_with_physical` 6%, `_hex_row` 5%, the Rust fire table itself ~5%), `fire_state` keys ~5%,
    `future_damage` ~6%, `reduced_options` ~4%. Nothing above 10% is left that has a clean boundary: what is left is
    Python plumbing around many small calls, so the next gain is moving whole loops (the `evaluate` per-option loop with
    its memos, Legate's `combine`) with their data flat in Rust - a rewrite of those two, not another kernel.

- **2026-11-06 (Claude, session 20), RUST PORT STEP 4: LINE OF SIGHT, HEX DISTANCE, AND THREE PYTHON CACHES. REVIEW
  PENDING (higher-level model).** Speed only: 51 of 51 checks with and without the Rust built, every reference log
  identical, benchmark 501 / 495.
  - `fastcore.LosBoard` (Rust): a copy of `pathfinder/los._evaluate` (Core pp.56-58, 66, 124, 240; TO:AR pp.29, 36, 38)
    for `los_cache.pair_info` - the hex line (from (0, 0), the same float operations, Python's round half to even), both
    sides of a border line, woods / ultra-heavy / smoke / fields, partial cover, the target's woods. Python hands it a
    snapshot of the board (`los_cache._build_rust_los`); `INTEGRATION__smoke` drops it whenever the smoke changes (a
    trace reads the live board). `config.FASTCORE_LOS`. `los.hex_distance` is the Rust function when built.
  - `damage_resolution.get_weapons` keeps its answer while the mech's `destroyed_slot_info` keeps its length (every
    writer of `crits` / `destroyed_slot_info` adds an entry), only while a battle is played (`play_on` switches it on:
    tests that edit `mech.crits` by hand outside a battle see their edit). `config.WEAPONS_CACHE_VERIFY` compares every
    cached answer with a fresh scan (on in `tests/test_fire_tables.py`).
  - `structure_weight.multipliers` kept per (weapons and their damage, target's armor / structure, side, k), emptied each
    turn; `movement_selection.spot_hazard` / `_safest` return 0.0 at once on a board with no hazard hex
    (`terrain_rules.has_hazard_terrain`).
  - Checks: `tests/test_fastcore.py` compares Rust v Python line of sight on 7 boards x with / without smoke x 4 height
    codes (14,000 pairs: results, entry directions, distances, arcs, off-board errors) and `hex_distance` on 50,000 pairs.
  - Result, 12 v 12 Gladiator (Legate on), 5 turns: 62.2 s (no Rust, no caches) -> 36.5 s (steps 1-3) -> 23.3 s (now),
    the same battle: 63% less, 2.7x. Left, by the profile: the `evaluate` loop and Legate's `combine` (Python plumbing
    around the scorers, ~40%), `future_damage` (~9%), `arcs` (~4%).

- **2026-11-06 (Claude, session 20), RUST PORT STEP 3: THE REACHABLE-SPOT SEARCH (`fastcore.PathBoard`). REVIEW PENDING
  (higher-level model).** Daniel: "Go ahead and do all three" (evaluate loop, reachable spots / movement table, Legate
  future damage). This is the second. Speed only: 51 of 51 checks with and without the Rust built, every reference log
  identical, benchmark 501 / 495.
  - `fastcore.PathBoard` (Rust): a copy of `pathfinder._build_terrain_psr` (the Dial's-algorithm sweep: same buckets
    in the same insertion order, the same "strictly better (forward count, fewer PSRs) replaces" rule) plus the state
    lists `ranged_combat._movement_options` builds from it: `walk_states` (a mover walking from its own hex) and
    `entry_states` (turn 1, entering from the edge: every edge hex x 6 facings). Python gives it the board's step data
    once per board and level-limit class (`ranged_combat._rust_board`, kept on the board's cache so `forget_board` drops
    it); finished tables are cached in the Rust like `board.tables`. Boards with no PSR terrain use the same search (a
    backward step only onto the same level, no PSR counts, as `_build_terrain_aware`). Boards with live hazards (magma
    crust), `standup_mp` and `keep_parents` paths stay in Python. `config.FASTCORE_MOVEMENT` (on) switches it off.
  - A quirk the Rust copies on purpose: while a mech ENTERS the board `_note_psrs` runs as each state is yielded and the
    reduction (`movement_selection.reduced_options`) reads the PSR count then, so a state reached again by a way with
    fewer PSRs is read with its FIRST count and holds the fewest only afterwards. The first version returned the final
    counts and changed one reference battle (LargeLakes1: 92 v 93 spots); `entry_states` now returns both.
  - Checks: `tests/test_fastcore.py` `the_rust_movement_search_matches_the_python_on_real_boards` (6 boards, 5 'Mechs,
    random starts / facings / blocked hexes / destroyed hips: states, order, PSR counts, entry states, and the reduced
    states the picker reads, Rust v Python). It did not catch the entry-order quirk by itself (a mutation test
    passed); the LargeLakes1 reference battle does.
  - Result, 12 v 12 Gladiator (Legate on): 2 turns 21.1 -> 15.0 s (turn 1 is the entry search); 5 turns 62.2 s with no
    Rust at all -> 36.5 s with all three Rust steps (41% less), same battle. Next: the rest of `evaluate`, Legate.

- **2026-11-06 (Claude, session 20), RUST PORT STEP 2: MISSILE / SPECIAL WEAPON PRICING IN THE RUST TABLE. REVIEW
  PENDING (higher-level model).** Speed only: 51 of 51 checks with and without the Rust built, reference logs
  identical, benchmark 501 / 495. `fire_modes.Planner.price_spec` describes a special weapon in numbers when it has
  ONE shot plan (a single ammunition kind) and is an ordinary attack: the range modifier and bracket by distance,
  the TN change and the hit worth (`Planner._hit_worth`, split out of `value()` unchanged) by bracket, and the
  heat. `FastTable` kind 3 then prices the (distance, pre-TN) rows itself: hit_probability(TN) x worth, the same
  float operations as `value()`. An Ultra / Rotary AC is covered too when `STUB_RATE_OF_FIRE` is "max" (default) or
  "single" (the rate does not depend on the row); "greedy" asks the planner row by row. Still asked row by row
  (kind 2): LB-X with two ammunition kinds, Narc beacons, MML / ATM with several kinds, anything with more than one
  plan. `config.FASTCORE_PRICING` (on) switches the step off. Checks: `FIRE_TABLE_VERIFY` compares every Rust
  answer with Python's; `the_rust_fire_table_is_really_used_when_built` also fails if no weapon was priced in Rust.
  Result, 12 v 12 Gladiator, 2 turns: 24.0 s -> 21.1 s; with step 1, 29.3 s -> 21.1 s (28% less) in all. Planner
  callbacks 135k -> 36k. Next by the profile: the rest of `evaluate` (the per-spot loop and its memos, ~25% of a run),
  `reduced_options` and the movement table (~25%), Legate future damage (~9%).

- **2026-11-06 (Claude, session 20), RUST PORT STEP 1: THE WEAPON CHOICE TABLE (`fastcore.FastTable`). REVIEW PENDING
  (higher-level model).** Daniel: "Lets start with weapon pricing. See how much of an improvement we can get."
  Speed only: 51 of 51 checks with and without the Rust built, every reference log identical, benchmark 501 / 495.
  - `fastcore/src/lib.rs`: `FastTable`, a copy of `weapon_selection.FireTable.choose` - candidates in weapon order,
    value = table value x the side's structure-weight scale, the row cache, the knapsack levels solved again only at
    a larger budget, Phase 2 padding. Same sums in the same order, so the same answer to the last bit. Plain weapons
    are priced from flat grids (`build_expected_damage_table` now keeps one per weapon, `table["flat"]`); missiles
    and other special weapons call back into the Python planner (`fire_modes.Planner`) for their value and heat -
    that part is NOT ported yet.
  - `weapon_selection.FireTable.choose_value` (what the movement scorer reads - the value only) builds the
    FastTable on first use (`_build_fast`; falls back to Python when not built, `config.USE_FASTCORE` off, a
    non-integer heat, more than 64 weapons, or a planner heat the Rust can't take). `ranged_combat` `score()` calls it.
  - Checks: `config.FIRE_TABLE_VERIFY` now also compares the Rust answer (value, heat, chosen weapons) with
    Python's on every call (`tests/test_fire_tables.py`, all 3717 tables of a 12 v 12 matched);
    `the_rust_fire_table_is_really_used_when_built` fails if the tables silently fall back to Python.
  - Result, 12 v 12 Gladiator (Legate on), 2 turns: 29.3 s -> 24.0 s (18% less), same battle. What is left of weapon
    pricing in the profile: the planner callbacks (135k in those 2 turns, ~16% of a profiled run); to port them
    the planner's per-weapon constants (bracket TN offsets, expected hit worth per bracket) go over once per table
    and the Rust prices the (distance, pre-TN) grid and picks the munition / rate itself (stubs' policy: best
    value, ties to the plain kind; rate: STUB_RATE_OF_FIRE).
  - `tests/test_hazards.py` `magma_heat_is_uncapped` failed ~3 runs in 100 with no code change (a heat-phase
    ammo-explosion roll at 30+ heat was unseeded); it now scripts the dice.
  - Build: `cd fastcore && maturin build --release && pip install --force-reinstall target/wheels/*.whl`
    (needs `pip install maturin`; `tests/test_fastcore.py` skips when not built).

- **2026-11-06 (Claude, session 20), RUST PORT - PROFILE AND PLAN. REVIEW PENDING (higher-level model).** Daniel:
  20 battles an hour (the 12 v 12 baseline battery, ~3 min a battle on one core) is too slow to iterate on bot
  logic; "Go for stage 2 [the compiled scoring]. If nothing else, slowly port over to rust one section at a time."
  No code changed yet. Profile (cProfile, 12 v 12 Gladiator, Legate on, 3 turns, 176 s; real time is ~half):
  `evaluate` 50% cumulative (88 s) of which the weapon choice (`FireTable.choose` 46 s, `fire_candidates` 34 s,
  fire_modes planner 25 s, knapsack 6 s) is most; `reduced_options` / `_movement_options` 15% (27 s);
  `build_movement_table` + `_build_terrain_psr` 11% (19 s); LOS (`los.walk`, `hex_distance`) ~5%; Legate
  `future_damage` ~9%. The spread is FLAT: no section is over ~26%, so one section alone gains 1.1-1.4x (Amdahl);
  the 30x Daniel hopes for needs most of the engine in Rust. CORRECTION to the 2026-11-06 estimate "20 battles in
  well under 10 minutes from stage 2 alone": that held for the exhaustive search, not the grid default.
  Section order, easiest boundary first (each one keeps the reference logs byte-identical, Python stays the
  fallback and the spec, as `fastcore/` does): (1) pathfinder movement table (flat data: step costs per hex /
  direction in, table out; ~11%); (2) LOS and hex distance (~5%); (3) weapon pricing: per-weapon rows, fire table,
  knapsack (~26%; the fire_modes planner for missiles is the hard part); (4) reduced_options / spot hazards;
  (5) Legate future damage; then the movement score itself. Estimate: ~6-10M tokens for all of it.

- **2026-11-06 (Claude, session 20), BATTLE STATISTICS - REVIEW PENDING (higher-level model).** Daniel asked what
  the Monte Carlo should output; he and Claude sorted three AIs' lists (his answers: Section 5 "Battle statistics").
  Built (stages 1-3 of 5):
  - `INTEGRATION__stats.py`, the COLLECTOR: a per-battle event log (one row per ranged shot with range, TN, roll,
    hit and damage; one per physical attack, charge and DFA; every unit's state at each turn's end - HP, hex,
    heat, prone, shutdown, locations lost, engine / gyro / cockpit hits, explosions, pilot hits; the turn, phase
    and cause of each death; who landed each killing blow). It rides on `BattleResult.stats`. It only reads.
  - `INTEGRATION__stats_report.py`, the ANALYSIS: outcome (win / draw with a 95% Wilson interval, how draws
    ended, battle length, the running win rate, shortest / longest battles with seeds), per unit (survival,
    death turn / cause / phase, killer, damage dealt and taken as mean / median / p10 / p90, kills per game,
    damage by weapon and by physical attack, shots and hit % by range, locations lost, criticals, heat, prone and
    shutdown turns), per team (units standing and force remaining by turn with a p10-p90 band, survivors at the
    end, first / second kill turn, focus fire, spread, each unit's share of the team's damage), and curves by
    turn. `INTEGRATION__stats_viewer.html` draws it (inline SVG, no libraries, light / dark); the page and its
    JSON go to `stats/` (git-ignored) at the end of every batch (`config.STATS`, `STATS_DIR`).
  - Hooks: `attack_resolution.run_ranged_phase` (every shot, and pooled cluster lumps), `physical.run_physical_units`
    (every physical attack), the orchestrator (turn snapshots, deaths by phase, start / finish). 30 test files
    set `config.STATS = False` (they compare output or run batteries); `check_reference_logs.py` and
    `test_parallel_batch.py` add it to their scenario code. New: `tests/test_stats.py` (logging changes nothing;
    the log agrees with the result; a 2 v 2 batch analyzes; the page carries the analysis).
  - Checks: `python tests/run_checks.py --bench`: 51 of 51 pass, every reference log identical (no `--update`),
    the benchmark's "resolving hits and damage" unchanged at 0.0 s. A 30-battle Kontio v Hammerhead batch (6.5 s
    a battle, 8 workers) and a 16-battle 2 v 2 batch both write a page that loads with no errors and no sideways
    scroll at 400 px.
  - LEFT (stages 4-5): wasted damage / overkill and critical slots (need a hook inside `apply_damage`); PSR
    counts; BV-weighted force value by turn; paired comparisons with a confidence interval (`ab_batches.py`);
    initiative advantage; matchup and terrain tables; the bots' predicted v actual (calibration, regret) in the
    report (`legate_probe` has the data); outliers linked to replays. Pushes show in the turn totals, not as a
    damage row.

- **2026-11-06 (Claude), REVIEW QUEUE CLEARED: LEGATE, SAVED STATES, COMBAT LAB ART.** Review of queue items
  (d), (e), (f), (h), (g), (k), (l) by the higher-level model (Daniel: "clear the rest of the review board").
  - (d) / (f) Legate team options: `fire_share` / `now_share`, `MultiLifetime`, `_Herd`, `_Cohesion`,
    `brackets`, `_TeamFire` read through; the team-value arithmetic checked (the score comes out as dealt +
    the team's future damage, as documented; with the exchange, as documented). Two fixes:
    (1) `_FRIEND_DMG` (team fire, LEGATE_TEAM_VALUE - off by default) is now emptied every Movement Phase:
    keyed by positions only, a teammate standing where it stood on an earlier turn reused damage worked out
    before either unit was hurt. (2) BOT CHANGE: `Extras.adjust` left out the fire of an enemy whose
    ESTIMATED end hex is the spot being scored, so those spots looked safer than they are; that enemy now
    shoots from where it stands (it will end somewhere else). About 1% of Gladiator moves (2 of 198 in a
    probe battle). A/B, same 20 seeds, baseline battery (Princess wins / draws / Gladiator wins; 'Mechs left
    P / G; damage dealt P / G; turns; battles at the cap): without 11 / 1 / 8, 2.60 / 1.75, 1529 / 1378, 37.6,
    2; with 11 / 1 / 8, 2.55 / 1.95, 1508 / 1345, 36.5, 1 (7 battles identical) - level within the noise,
    kept as the correct score. These are also the first battery numbers on the MegaMek-seam field (32 x 17):
    the new BASELINE (the older ones, 8 / 4 / 8 and before, were on 33 x 17).
  - (e) The probe battery's monkeypatches (wrappers that record and pass the original answer through):
    battle 1 with `--calib` gives exactly the battery's battle 1 (Red after 40 turns, 4 left, 1750 / 1177
    dealt). One harmless quirk: `--calib`'s raw (k = 1.0) pass can reuse a physical-attack Worth built under
    the configured weight (`movement_attacks._WORTH` keys by unit and HP, not the weight) - the diagnostic's
    raw column only, never the battle.
  - (h) Saved states: the round-trip check passes (every reference battle saved, reloaded and played on
    after every turn, byte for byte); module caches not emptied on a load (`_WORTH`, the LOS / hex-property
    boards) key by an object they hold or compare, so a reused id can't hit them. Nothing to fix.
  - (g) / (k) / (l) Combat Lab art (art checks only, Section 7): the workbench is safe (codes are JSON, a
    unit name only matches a file in the library, the Windows starter binds 127.0.0.1); the argmin guard
    covers the reported crash; pyflakes clean; 300 random library units built in all three bodies with no
    failure. Fixed: `tokens.read_unit` skipped PATCHWORK armor lines ("LA armor:IS Reactive(Inner
    Sphere):8"), drawing those units (e.g. the Spindrift SDT-1) with no armor - the points are now read after
    the last colon. Found: `tests/test_token_shell.py` prints PASS but SKIPS its geometry checks when scipy /
    trimesh are missing - they were missing in this container; `requirements.txt` now lists them (art only).
  - Checks: 50 of 50, reference logs identical, the round trip identical.

- **2026-11-06 (Claude), REVIEW: KILL CURVE, RUST, FIRE TABLES; MEGAMEK MAP SEAMS.** Review of queue items
  (c), (i), (j) by the higher-level model, and Daniel's map-seam call. 50 of 50 checks, every reference log
  identical, benchmark 501 / 495 - with the Rust built and without.
  - MAP SEAMS (Daniel: "It should follow Megamek's conventions"; MegaMek BoardUtilities.combine, master):
    stitched boards now ABUT - no gap between rows, none after an even-width board (16-wide sheets keep
    their column parity and join up as drawn). Only after an odd-width board (the pack has 15- and 45-wide
    maps) one blank column, MegaMek's default padding, restores the parity. MegaMek fills that column with
    terrain blended from both sides (random woods / rough); ours stays blank. A 2 x 1 field is now 32 x 17
    (was 33 x 17: `tests/baseline_battery.py`'s field is one column narrower, so its battles change). Test:
    `test_terrain.stitched_map_loads_and_crosses_the_seam` checks every hex of the second and third boards
    sits exactly 16 columns / 17 rows on, and the odd-width padding.
  - (c) Sound: the kill curve's own dice (every roll in the damage path goes through config.roll_2d6 /
    pick_number, looked up at call time; mechsim's `config` is the same module), its trials write nothing
    outside their copy (quiet() also silences the replay's sink), the fire director's dry run changes
    nothing, `fire_pick`'s ranking, the advance-into-an-occupied-hex fix, and `princess.direction`'s 5 for
    the same hex (checked against MegaMek's Coords.radian: equal x and y give 1.5 pi, / (pi/3) = 4.5, Java
    rounds to 5). Fixed (no result change): the kill-curve cache outlives a battle and is keyed by
    `id(mech)`, which Python reuses; the state signature can't tell armor types apart (hardened armor has no
    slots), so a freed unit's id reused by another design could have found its curve - the armor and
    structure types are now in the key. Doc fix: the trials' seed has no design name in it (a 'Mech has no
    `name`), only the side and the damage state.
  - (i) Sound: the Rust knapsack is the Python's step for step (levels visited high to low, strictly better
    replaces, new levels at the end, first highest wins, the same float sums). Built here and compared on
    60,000 random knapsacks (heavy ties, zero-heat weapons, up to 64 candidates): the same winner, heat and
    weapons, and the same `knapsack_levels` in the same order. The one difference (a sorted list v a Python
    set of indices, which isn't always in ascending order) can't matter: every caller turns it into a set of
    weapons and walks the weapons in their own order. The `special` / `has_profile` caches read only the
    weapon's name and fixed data (missile, Ultra / Rotary, profiles, flamers / plasma by name), so a cached
    answer can't go stale. Fixed (latent crash, no result change): `knapsack_levels` sent a non-integer heat
    budget to the Rust, which raises TypeError there (`best_subset` catches it; this one didn't) - it now
    checks the budget first.
  - (j) Sound: solving once at the largest budget and filtering gives exactly a smaller budget's answer
    (levels at or below a budget are built only from lower ones, in the same insertion order, when no heat
    cost is negative - the table checks that) - also run against fresh solves at every budget in the
    60,000 cases above. The shared table's key covers what the first caller's tn_adjust / Planner / scale
    read: attacker and target state (`fire_state`, incl. active stealth, which ECM positions can change in
    mid-movement - it is in the key each time a scorer is made), aim, AMS count, water, unavailable weapons
    (ammo, jams, arcs, held limbs), the weighting switch, and the role; cleared every turn and on a load.
    Nothing missing found.

- **2026-11-06 (Claude), BV REVIEW ITEM (b) CLOSED** (Daniel: "the BV difference was a non issue. Calculated value matches Mordel"). Crusader CRD-3R stays at 1317; review item (b) removed from the queue. Docs only.

- **2026-11-05 (Claude), session 18 - WORKBENCH: SHAREABLE CODES; A CRASH GUARD** (Daniel: "error: attempt to get argmin of an
  empty sequence" - a Clan LB 20-X on an arm with no lower arm or hand actuator; "as a feature, a copyable code that I can paste so
  you can plug it back in and see what I'm doing"). REVIEW PENDING (higher-level model). Art only; the art checks pass.
  - Not reproduced here (360 combinations of tonnage, body, arm block, side and rail on that gun all built), so the cause is
    unconfirmed. Guarded: `Solid.hit` returns the start point when no face can be left through (a zero direction made the
    argmin empty); `_arm_grid` does not seat a block centred on the arm along a direction it does not have.
  - Codes: `token_workbench.encode` / `decode` (the page's whole setting, JSON, zlib, URL-safe base64, prefix "CLW1."). The page
    has "Copy code" and "Load pasted code"; a failed build puts its code in the box. `python -I tools/token_workbench.py --code
    <code>` rebuilds a pasted code here with the checks. The server prints the full error of a failed build.

- **2026-11-05 (Claude), session 18 - THE ARM HARDPOINT GRID; WEAPONS BLOCK WEAPONS** (Daniel, from a workbench test: an Atlas
  with 8 medium lasers pinned to one rail of its right arm showed "6 in line with each other, most of which shots would be blocked
  by the one in front of it and a 7th off on its own. No idea where laser 8 is." His fix: "a 6x6 grid laid over the end of the
  arm. The inner 4 squares tend to be reserved for the hand, the middle ring of 12 are the normal weapon slots and the outer ring
  of 18 are virtual slots that give space for bulky weapons to expand into. Groups of squares can be combined to use their average
  center of gravity as a hard point. (For example on a mech with no hands the 4 center squares would be merged into one bigger
  square to fit a single weapon.)"; also equipment hardpoints facing other directions - shields, electronics, turret pods such as
  the Catapult's box launchers on its shoulders). REVIEW PENDING (higher-level model). Art only; the art checks pass.
  - Cause: the clear-muzzle check only tested against the body, never against other weapons, and line rails queued weapons one
    behind another.
  - `INTEGRATION__shell_facet._arm_grid` / `_arm_grid_geom`: the grid over the end of each forearm, the four centre cells the
    forearm's own section (the hand, or with no hand one big port), the middle ring of 12 around the outside of the forearm, the
    outer ring of 18 for bulky weapons. Each weapon takes a block of cells sized to its cross-section, as near its preferred ring
    position as the free cells allow (bulky weapons first); its hardpoint is the block's centre. Ring weapons are pulled in along
    their own direction until they seat on the forearm; one wholly in the outer ring gets a mounting bracket. An arm now has 12
    "rails" (`shell_items.rail_count`): the ring positions, which the workbench's rail menu pins. Brackets show the 12 and the
    centre (H = hand, C = centre port).
  - Weapons count as obstacles in the clear-muzzle check (`Sink.items`); line rails place their items SIDE BY SIDE.
  - New missile mount "post" for the humanoid (launcher pods on top of the side torsos: the Catapult). Shields and electronics
    facing other directions are not built yet.
  - Daniel's test now: 8 medium lasers with a hand ring the wrist; without a hand they make a grid of ports over the arm's end;
    0 floating, 0 clipping, 0 blocked muzzles (also 3 large lasers, 2 PPCs, an AC/20).

- **2026-11-05 (Claude), session 18 - WORKBENCH BUNDLE FOR A WINDOWS DESKTOP** (Daniel: "So? no link to it?" - the cloud
  preview never reached him; "D:\Claude\Model viewer. You have permission to push the required files into that folder"). This
  cloud session cannot reach his computer (no folder shared), so the workbench ships as a zip he unzips there.
  REVIEW PENDING (higher-level model). Art only.
  - `tools/make_workbench_bundle.py <out.zip>`: the workbench, the ten modules it imports, the token data, equipment.json,
    meks.zip, and `tools/workbench_windows/` (start_workbench.bat: finds Python, installs numpy / scipy / trimesh / python-fcl,
    starts the server on 127.0.0.1:8765, opens the browser; README.txt). Tested unzipped on Linux; the .bat is untested.
  - `token_workbench.py --host` (127.0.0.1 on a desktop; 0.0.0.0 stays the default for the cloud preview).

- **2026-11-04 (Claude), session 18 - COMBAT LAB WORKBENCH** (Daniel: "a viewer that lets me manually set what blocks are being
  used. Sliders for tonnage and mobility, and drop down menus for weapon loadouts with the ability to control which mounts they
  use. Basically full control over any combination. Which will let me systematically do testing."). REVIEW PENDING
  (higher-level model). Art only; the shell test passes.
  - `tools/token_workbench.py` (a small web server, stdlib only) + `tools/token_workbench.html`: start with
    `python -I tools/token_workbench.py --port 8765 [--meks <unzipped meks folder>]`, open the port (in a cloud session the app's
    preview). Each change rebuilds the 'Mech with the real faceted builder. Controls: tonnage, walk and jump MP, armor level,
    engine and cockpit type, body (humanoid / bird), head mount, reference tags on / off, arm actuators; a menu per block slot
    (auto = tag or name hash; the page shows what each slot resolved to and why); a loadout table (any of 686 items, its
    location, its rail or auto); load any of 4,225 unit files and change it; layers, X-ray, edges, mounting brackets; "Run
    checks" (volume by location against its budget, floating, below ground, clipping, blocked muzzles). Not an Artifact on
    purpose: a published page cannot run the Python builder.
  - `INTEGRATION__shell_items.place_items` honours `unit["force_rails"]` ({zone: {item index: rail}}) for the workbench's rail
    pins; the shuffle is unchanged otherwise.

- **2026-11-04 (Claude), session 18 - TEST RANGE FACETED FROM THE NAME HASH; PER-SLOT HASH FIX** (Daniel: "go ahead and generate
  our smaller test batch's hash values as faceted"). REVIEW PENDING (higher-level model). Art only; the three art checks pass.
  - The viewer gets a fifth variant, "Faceted, name hash" (`tools/token_3d.py --range`, `facet_hash`): each range chassis built
    with no reference tags, as an untagged unit would be.
  - BUG found and fixed: `pick` read the slot's block from a byte of the 8-byte name hash, so every slot after the eighth always
    took its first block (every name-hash unit had prism legs, drum knees, heel-and-toe feet, a box head, box pauldrons, octagon
    forearms). Each slot now hashes the unit's name with the slot's name. Tagged slots are unchanged; untagged slots of tagged
    units change look too.
  - Heads are fitted to the Head budget as a whole (glass, canopy and ears included: the bubble head was 1.7x over); the bird
    body's nose cockpit may scale 0.6-1.6 (the Locust's was capped short).
  - Seen, not changed (for Daniel): the name-hash Archer has a missile rack standing at an odd angle off its round torso's top
    edge; the name-hash JagerMech (a bird body) shows an amber plate on its canopy.

- **2026-11-04 (Claude), session 18 - BLOCK VARIANTS FOR EVERY BODY PART** (Daniel: "systematically add variant blocks for each
  body part. Lets try to build up the dictionary before regenerating the full list of mechs. I will want to look at each set of
  parts as seperate pieces."). REVIEW PENDING (higher-level model). Art only; the three art checks pass.
  - New blocks: legs box / tapered; knees spike / twin; feet claw / pad; pauldrons fin / shell; forearms hex / tapered. New slots:
    hand (fist / block / claw / ball, sized within the forearm so arm guns fire past) and waist (drum / ring / column).
    `data/token_dictionary.json` `shell_mapping.facet_blocks` lists every block and the tag that forces it.
  - Lineups of all 13 slots (tools/token_lineup.py): every block passes joined / ground / clip / clear-muzzle. Fixed on the way:
    the claw foot's hub sat below the ground; a ball or block hand blocked guns lying along the forearm.
  - The 47 chart chassis are NOT regenerated yet (Daniel: build the dictionary first).

- **2026-11-04 (Claude), session 18 - BAY HOUSINGS, ATTACHED SHOULDERS, PART LINEUP TOOL** (Daniel: "Doors on the atlas are
  overshadowed by the missile launchers clipping. Archers arms are also not attatched and the missiles are still clipping";
  "I will want to look at each set of parts as seperate pieces. Parts that have mounting brackets should indicate where those
  are."). REVIEW PENDING (higher-level model). Art only; the three art checks pass.
  - Missile bays get a HOUSING: a flat-fronted box set into the side torso's upper front, aimed forward and about 20 degrees up,
    its volume booked to the side torso; the racks sit flush in its face, each door hinged at its top edge and raised (`_bay`).
    The racks no longer poke out of curved or sloped torsos.
  - Shoulders: the side torso's outer face is found AT shoulder height (a round body narrows up top), the arm hangs clear of the
    torso's widest point below it (bay housings included), and the shoulder drum reaches in to the face, so the arm is held.
  - New `tools/token_lineup.py` (replaces token_heads.py): every block of a slot on one 'Mech, the slot's locations drawn alone,
    with the MOUNTING BRACKETS marked (green: joint sockets; orange: hardpoint rails, numbered) and the checks per block.
    The brackets come from `_record_brackets` (model["_brackets"]).

- **2026-11-04 (Claude), session 18 - HEAD BLOCK LIBRARY** (Daniel: "Start a pass of designing a group of heads blocks. Think we'll
  tackle one location at a time and build a library of interchangeable blocks."). REVIEW PENDING (higher-level model). Art only;
  the three art checks pass.
  - `INTEGRATION__shell_facet.head_block`: box, skull, dome, wedge, bubble, visor, turret, hood (`BLOCKS["head"]`, sizes
    `HEAD_SIZE`, mount depth `HEAD_DROP`); tags pick them (head_mount built_in -> hood; head_shape -> its block), else the name
    hash. `pick` honours `model["force_blocks"]` for lineups and tests.
  - New `tools/token_heads.py`: every block of a slot on one 'Mech, 3/4 front and rear close-ups, with the joined / ground / clip /
    clear-muzzle checks per block (all eight heads pass on the Atlas). Its renderer sorts all faces in one collection (thin glass
    plates vanished under the head otherwise).
  - Seen on the way, not changed: the Atlas's left side torso missile-bay door stands up in front of its head.

- **2026-11-04 (Claude), session 18 - CT DEPTH RATIO, ROUND TORSO, CLEAR MUZZLES** (Daniel: keep the centre torso within a ratio
  of the side torsos' depth "otherwise we could see a distinct cross shape from overhead"; "Archer needs a geometry pass. Could put
  negative space in front of weapons to prevent them from being blocked by clipping ... Solution might be the Round blocks used on
  the 'Old blocks' variant of the urbanmech"). REVIEW PENDING (higher-level model). Art only; the three art checks pass.
  - `torso_pieces`: the centre torso's depth is at most `CT_RATIO` (1.25) x the shallower side torso's; when the shoulder rule
    thins a side torso, the centre gets shallower and wider to keep its volume (`_torso_parts`, up to 4 rounds).
  - Torso block `round` (a faceted ovoid, the old blocks' UrbanMech body) replaces `dome`; tags torso dome / ovoid, profile dome,
    kit round_blocks pick it.
  - Negative space in front of every weapon: `_muzzle_blocked` tests the bore line 1.2 m ahead against the body's solids
    (`Sink.body`); a blocked weapon slides forward (up to 0.7 of its length), then tries the location's other rails; one still
    blocked is drawn and counted (`model["blocked_muzzles"]`, which tests/test_token_shell.py requires to be 0). All eight range
    chassis: 0.

- **2026-11-04 (Claude), session 18 - SHOULDERS OUT, WAIST AND PELVIS, FORWARD MISSILE BAYS** (Daniel: "shoulder joints should
  generally be farther out then the hip joints ... inflating the torso to push the arms back out will have the added benefit of
  reducing the 'Sandwich mounted sideways on legs' look"; "missiles tend to point towards enemy in battletech. Sometimes they're
  angled upwards"; "the ability to torso twist has been visually lost. we're using twin hip blocks, and are missing the Hips to
  waist actuator system"; and: run only the art checks for art work, Section 7). REVIEW PENDING (higher-level model). Art only;
  the three art checks pass.
  - `INTEGRATION__shell_facet`: `_hips` builds a pelvis block between the hips (two halves meeting at the centre line, sized by
    the hip actuators) with a hip joint drum at each side; `_waist` adds a vertical drum on the pelvis (the torso-twist
    actuator, part of the centre torso) that the torso stands on; bird body too.
  - Shoulder rule in `torso_pieces(min_outer)`: each side torso reaches far enough that the shoulder joint sits at least 1.22
    times the hip's outer edge out (tiny arms excepted), and thins its depth to keep its volume. Shoulder joints now 1.7 to 2.8
    times the hip joints' distance from the centre line.
  - `_bay`: racks in the side torso's upper front, aimed forward and about 20 degrees up, each under a door hinged at the top of
    its opening and swung up.

- **2026-11-04 (Claude), session 18 - LEG MYOMER FACTOR** (Daniel: "Give them a factor. This is where paying attention to the
  myomers would matter. Legs would tend to have more of them to support the entire mass of the mech."). REVIEW PENDING
  (higher-level model). Art only, 50 of 50 checks, reference logs identical.
  - `bulk_rule.leg_factor` 1.6 (data/token_densities.json): each leg's structure points count 1.6 times in the bulk share, as the
    head's count 1.5. Calibrated on the MWO Atlas kit (each leg with half the pelvis about 22 m3, each arm about 10: ours 19.4
    and 9.9). Volume below half height v the Syllogy (MWO) kits: Hunchback 36 v 35 percent, JagerMech 38 v 45, Archer 38 v 43,
    UrbanMech 33 v 49, Locust 25 v 43 (the Locust's long legs are a bird-body shape question, not a budget one).
  - The myomer layer shows it: six thicker bundles round each leg segment, four on the arms (`build_layers`).
  - Fixes the factor exposed: racks in a missile bay sit inside the side torso, so their volume goes back to the torso block
    (it was taken out twice); the gun housing never takes more than 45 percent of its side torso.

- **2026-11-04 (Claude), session 18 - BULK BY STRUCTURE POINTS, THREE-PART TORSO** (Daniel: "sometimes the torso feels like its
  just the center torso. The torso of any mech should have 3 parts that fit together. The relative bulk, before considering
  weapons and equipment also in that location should be based on the number of structural points in that location (Head counts
  at 1.5 its structure). This will probably require more depth"; test candidates JagerMech, Atlas, Hunchback). REVIEW PENDING
  (higher-level model). Art only, 50 of 50 checks, reference logs identical.
  - `INTEGRATION__shell_items.budgets`: rule `structure_points` (data/token_densities.json `bulk_rule`, head factor 1.5; rule
    `parts` keeps the old per-part budgets). The 'Mech's base volume is kept and shared by structure points; each location's
    parts keep their proportions (the hip still builds the pelvis). Atlas: side torsos 12.2 / 8.7 -> 19.0 / 15.5 m3, legs 21.4
    -> 14.6, head 4.9 -> 3.6. Applies to both looks.
  - `INTEGRATION__shell_facet.torso_pieces`: three blocks per torso (`TORSO_PARTS`), the centre forward, the sides set back, cut
    edges so the seams show, each fitted to its own budget; depth 0.36 of the height. The dome stays one solid cut in three.
  - Measured against the Syllogy (MWO) kits: JagerMech depth 0.73 (kit 0.73), width 0.54 (0.73); Hunchback depth 0.44 (0.54),
    width 0.50 (0.85). Legs now hold less of the volume than the kits' (JagerMech 30 percent below half height v the kit's 45):
    the structure-point rule gives the legs a smaller share than the actuator calibration did.

- **2026-11-04 (Claude), session 18 - FACETED BLOCKS: POSE, TORSO, HOUSING, MISSILE BAY, STRAIGHT GUN ARM** (Daniel, after the
  Syllogy kit comparison - Syllogy's models are MWO's: "Archer does not have launchers above the head. Those are the protective
  doors for the launchers in the torso in a raised position"; "Jagermech: the guns simply line up with the upper arm coming
  straight from the shoulder"; yes to pose, deeper torsos, a torso slot; "Hunchback only gets a bigger hump if it becomes a
  standard block. I'd prefer to minimize one off custom solutions."). REVIEW PENDING (higher-level model). Art only, 50 of 50.
  - New slots in `INTEGRATION__shell_facet.BLOCKS`: pose (stride / ready / crouch; legs per side via `pose_joints`, the upper body
    leans about the hip line, `lean_pts`), torso (v_chest / box / slab / wedge / dome: ONE solid 0.30 of the height deep, cut into
    the three locations by `clip_x` / `split_x` so each piece holds its budget), housing (the hump as a standard block, sized by
    the side torso's heaviest gun), missiles (face / bay: racks in the torso top under raised doors, `_bay`), arm (pod /
    straight). The bird body uses the pose slot too. The old per-section chest and the one-off hump are gone.
  - All eight range chassis within the volume band, 0 floating, nothing below ground, clip 0. Against the Syllogy (MWO) kits:
    depth up (JagerMech 0.69 v the kit's 0.73, Hunchback 0.37 v 0.54), poses now bent and leaning. Still narrower and less bulky
    than the medium / heavy kits (Hunchback width 0.52 v 0.85, bulk 0.067 v 0.107); since the kits are MWO's and the MWO Atlas /
    Timber Wolf matched our budgets, the remaining gap is either our volume budgets or our height curve against MWO's heights:
    Daniel's call.

- **2026-11-04 (Claude), session 18 - FACETED BLOCK LIBRARY** (Daniel: "Go ahead" on giving the humanoids their own identities).
  REVIEW PENDING (higher-level model). Art only, 50 of 50 checks.
  - `INTEGRATION__shell_facet.py`: `BLOCKS` per slot (leg prism / slab / pillar / greave; knee drum / cap / guard; foot heel_toe /
    wedge / three_toe; pauldron box / slant / drum / collar; forearm octagon / square / round), `TAG_PICKS` (tags that force a
    block), `pick` (tag, else a byte of the name hash per slot; recorded in `model["blocks"]`, shown in the viewer's info panel).
    The mapping is in `data/token_dictionary.json` `shell_mapping.facet_blocks`. `build_model` records `hash_only`.
  - All eight range chassis still within the volume band, 0 floating, nothing below ground, clip 0 (tests/test_token_shell.py).
  - Next: blocks for the torso (the UrbanMech's dome reads as a box from the front), heads and the bird body; then the 47 chart
    chassis (phase 2).

- **2026-11-04 (Claude), session 18 - FACETED LOOK ON THE WHOLE TEST RANGE** (Daniel: "what about extending this style to the
  other models?"; on the Atlas chest width: "similar, not perfect"). REVIEW PENDING (higher-level model). Art only, 50 of 50 checks.
  - `INTEGRATION__shell_facet.py` now builds all eight range chassis (`FACET_RANGE` = `SHELL_RANGE`). New tag-driven blocks in
    the humanoid body: chest profile from `profile` (dome, bell, prow, ... else the V-chest), `tall_slab` / slab torsos taller,
    a HUMP block for `hunch` / `stepped` on the side torso with the heaviest guns (its face rail takes the heaviest gun, rail
    `prefer="heavy"`), launcher POSTS for `kit` tall_launchers / launchers, GUN-POD forearms for any arm without a hand
    actuator (length by contents; `long_barrel` x1.2), head position by `head_mount` (top, built_in, front, notch), antennas,
    rounder arms for `round_blocks`, squat legs under a dome torso. The bird body: `narrow` torsos, antennas.
  - The ribs are clamped inside the side torsos (`build_layers`; the faceted Atlas had them running into the arms).
  - `tests/test_token_shell.py` now checks the faceted builds too (32 models: volume band, height, plate minimum, and the joined /
    ground / clip audit for the faceted ones). The viewer has a "Faceted (experiment)" variant on every range chassis.
  - Known: the humanoids still share one leg, foot and pauldron set (the block library would give them choices).

- **2026-11-04 (Claude), session 18 - FACETED LOOK: ATLAS, HARDPOINT RAILS** (Daniel: "Core shape is good, the length of those
  arms could easily be made a variable based on how much stuff is in them ... where all the hard point spots on that model would
  be located to deal with other configurations. And certainly go ahead with the Atlas."). REVIEW PENDING (higher-level model).
  Art only, 50 of 50 checks.
  - `INTEGRATION__shell_facet.py` restructured: a body per archetype (`body_bird` for the Mad Cat, new `body_humanoid` for the
    Atlas), each declaring its HARDPOINT RAILS (`FRail`: face, line or post; the same rail counts per location as the plated
    builder, so the shuffled `place_items` plan drives any loadout), one placement step (`mount_rails`): a face rail lays its guns
    out as a grid centred on the face, a line rail as a run centred along the part, a post rail puts every missile rack in one
    launcher on a post (a chassis with posts always uses them). Vents, nozzles and domes keep the plated builder's spots.
  - Mad Cat gun-pod length follows the arm's fullest rail (0.17 of the height + 0.4 m a slot, at most 0.40).
  - Atlas: straight legs on big knee drums, heel-and-toe feet, a V-shaped chest whose side torsos stand taller than the centre
    (the head's notch), a skull with two eye slots and a jaw, box pauldrons over the shoulders, forearms with fists, guns under
    the forearms. Every location within 10 percent of its budget (name hash within 10 of 0.90), 0 floating, nothing below
    ground, clip 0. Still narrower in the chest than the kit (convex sections at the budget's volume).
  - `build_layers`: torso myomer sized from each section's own box (it floated out of the Mad Cat's small side blocks).

- **2026-11-04 (Claude), session 18 - FACETED-LOOK EXPERIMENT, MAD CAT** (Daniel: "Lets experiment with the madcat. See if its
  worth pursuing", after a low-poly Mad Cat print). REVIEW PENDING (higher-level model). Art only, 50 of 50 checks.
  - New `INTEGRATION__shell_facet.py`, used only for the Mad Cat / Timber Wolf and only when `build_model(..., style="facet")`:
    one faceted solid per part (octagonal prisms with chamfered ends, drums across the knee, hock, hip, shoulder and elbow, a
    teardrop canopy torso with the cockpit nose as the Head location, side blocks, gun-pod forearms aimed forward, claw feet),
    launchers on posts over the side torsos, a forward-pitched body and wide stance. 35 body solids against about 140 in the
    plated builder. Shares the budgets, hardpoints, layers and rules height; every location within 10 percent of its budget, 0
    floating, nothing below ground, clip 0 (tagged and name-hash builds). Viewer: a "Faceted (experiment)" variant on the
    Timber Wolf, edges drawn by default.
  - Fix found on the way: Clan weapons whose canonical name keeps the tech prefix (`CLMG`) were classed "misc", not weapons
    (`shell_items._classify` now reads the family from the cleaned name).
  - Not covered by tests yet (the experiment is not in `tests/test_token_shell.py`); Daniel decides whether it replaces the plated look.

- **2026-11-04 (Claude), session 18 - SHELL BUILDER: KIT CALIBRATION, NO STEPPED PLATES** (Daniel sent the MWO Atlas and
  Timber Wolf kit models: "skinny legs that are almost all bone, with mini ziggurats built up on their faces ... looks like it was
  built in minecraft"). REVIEW PENDING (higher-level model). Art only, 50 of 50 checks, reference logs identical.
  - Measured both kits at scale (STL volumes): our torsos and arms matched, legs were half the kits', the pelvis a fifth. Cause:
    actuators had no mass in the budgets. Now `data/token_densities.json` `actuator_tons` (art mass per actuator, calibrated on
    the two kits; the hip's volume builds the pelvis). Atlas now 112 m3 v the kit's 112, Timber Wolf 90 v 80.
  - One plate per face (`n_layers` = 1); thick armor shows as a thicker plate. Legs deeper than wide (both kits), lower legs nearly
    as big as thighs, legs 0.52 / 0.53 of the height, feet a heel block with two toes, a pelvis block per hip, faceted box
    pauldrons in place of the domes, torso section widths balanced against their own budgets.
  - Daniel then sent a low-poly Mad Cat print that reads better than this: the next step is his call (see the reply that day).

- **2026-11-04 (Claude), session 18 - SKELETON-AND-SHELL BUILDER, PHASE 1 (TEST RANGE)** (spec:
  `INTEGRATION__COMBAT_LAB_SKELETON.md`). REVIEW PENDING (higher-level model). Art only: no engine code, every reference
  log identical, 50 of 50 checks. STOPPED for Daniel's verdict on the look before phase 2.
  - **Built:** `INTEGRATION__shell_items.py` (the data half: every crit line becomes an item with kind, slots, tons from
    `mechsim/equipment.json` with a flagged fallback, volume = tons / density; hardpoint capacity read from `unit["slots"]`;
    the name-hash shuffle onto rails; location volume budgets from items, structure, armor, engine, gyro, cockpit),
    `INTEGRATION__shell.py` (skeleton joints from the rules height, location envelopes sized from the budgets, bevelled armor
    plates of real thickness layered by armor ratio, joint covers that overlap so no gap shows, shoulder sockets, visible
    mounts: weapons on rails, heat-sink vents, jump-jet nozzles, sensor domes, real-scale missile tubes),
    `data/token_densities.json` (art densities with a reason each, slot length 0.4 m, 5 cm plate minimum),
    `tests/test_token_shell.py`, a clip measure in `tools/token_audit.py`, the dictionary mapping
    (`data/token_dictionary.json` `shell_mapping`: every tag term expressed, approximated or FLAGGED), a third "Old blocks"
    variant in the viewer.
  - **Layers (Daniel's follow-up, same day):** every part carries a layer (`shell.LAYER_OF`): armor (core, plates, covers),
    equipment (visible mounts plus the unseen engine, gyro, cockpit, ammo and other items drawn INSIDE the shell), myomer
    (spindle bundles round each bone and the torso) and skeleton (bones and ball joints). The viewer has a switch per layer,
    presets (all / armor / equipment / myomer / skeleton only) and an X-ray armor option; the default view (armor + equipment)
    is unchanged, so no internals are exposed. `unit_mesh` parts carry `ly`. Skeleton and myomer are placement geometry:
    their volume is not part of any location's budget (the spine, hip, shoulder and rib bars count to no location).
  - **Range (phase 1):** Atlas, Mad Cat / Timber Wolf, Locust, Hunchback, Archer, JagerMech, UrbanMech, and Wendigo (a
    torso-mounted cockpit, weapon and ammo in the head; name hash only). `tokens.build_model(..., shell=True)` routes them to the
    shell builder; every other unit still uses the old block builder `_build` until phase 2, which is why `_build` and
    `calibrate` are not yet deleted (the spec's "retire" lands with the last phase).
  - **Checks:** hardpoints over all 4,227 unit files (115,951 items placed once each, none over capacity, shuffle stable);
    location volume within a band of its budget (spec 25 percent; tuned to **30 percent**: the pelvis plates and clamped
    narrow side torsos need it); height on the rules curve (3 percent); no plate under 5 cm; 0 floating blocks, nothing below
    the ground, arm / torso and leg / leg clip 0 on 16 models. `test_token_volume.py` skips the old density law for shell models.
  - **2D from 3D:** for shell models the 2D tokens already project the very convex solids the mesh hulls, so they cannot
    disagree; the old 2D path stays for old-builder units until phase 2.
  - **Not done / for Daniel's eye:** the look. Known weak points (FLAGGED in the dictionary mapping): no Hunchback hump, no
    Archer tall launcher boxes, no Atlas notch, no Mad Cat wing bays, plates read stepped on steep limbs, physical weapons,
    martian / quad / tripod skeletons (phase 3). Weapon masses with no table value use the fallback list
    (`INTEGRATION__shell_items.FALLBACKS`: mostly ammo and heat sinks).

- **2026-11-04 (Claude), session 18 - COMBAT LAB 3D - REVIEW PASS (Daniel: "a higher tier pass at the combat lab 3d
  assets; see what problems you can find and fix").** REVIEW PENDING (higher-level model). Art only: no engine code, every
  reference log identical, 49 of 49 checks.
  - **Measured, not eyeballed:** new `tools/token_audit.py` builds every chart unit and measures the meshes the viewer
    shows: exact distances between the convex blocks (python-fcl), so a block that touches nothing joined to the body is
    FLOATING, named by the builder line that made it; parts below the ground; mirror symmetry. Before: 368 floating parts
    over the 48 reference-tag models, 351 more on the name-hash models (the look every untagged unit in the library gets).
    After: 0 and 0. New `tests/test_token_joined.py` (12 models that each had a different fault; it fails on the old code).
  - **Bugs found and fixed** (`INTEGRATION__tokens.py`): (1) clamped arm guns hung 2-3 cm clear of the forearm (166
    parts): each gun is now built on the forearm's axis and slid out until it seats on the forearm (or on the gun before
    it), with a clamp block; side-by-side guns touch instead of sitting 8 px apart whatever their size. (2) Wing-bay tube
    mouths (Mad Cat, Stalker) were laid on a vertical plane in front of the bay's slanted face (92 parts): they follow the
    face and start inside it. (3) Things on the back (fins, brackets, jump jets) used the centre torso's depth, but the side
    torsos are 0.96 deep. (4) A "stepped" panel set builds the centre torso 0.03 taller, but every lookup of the front face
    used the shorter height: chest vents, plates and guns stood off sloped chests (`pv`, and `side=True` for side-torso
    mounts). (5) Gauss rifles: `B3.prism` never applied the width fit to x / y, so every Gauss barrel stood off its mount.
    (6) Box / wedge / visor heads ignored their mount depth (`extrude` had no `cy`): every "front" or "boom" head was built
    at the torso centre, sunk in it, with its glass floating out front (the Locust's wedge head now stands out front, as
    tagged). (7) ARM PLACEMENT: the old formula scaled the whole torso half-width by the top taper, but each section
    tapers about its own centre: arms beside top-wide torsos (narrow, winged) hung in the air, beside top-narrow ones
    (ovoid) clipped in - likely the root of the JagerMech clipping. Now the side torso's real outer face, and a shoulder gap
    that grows with the arm's girth (a fixed 5.8 cm put every heavy upper arm inside the torso): arm-into-torso
    penetration 6 of 94 models (up to 3.5 cm) to 0. (8) Shoulders, heads, antennas, cockpit blisters, turrets, ECM / probe /
    C3, fins and shoulder-barrel cradles were placed at `ztop` even where the top leans or curves: they now sit on the real
    top (`top_at`, `sit`; ellipsoid surfaces for dome / canopy torsos). (9) Martian, quad and tripod legs ended 6 mm above
    the foot. (10) Smaller: chest bolts off wedge-plan faces, a hatchet spike and sword tip off their shafts, ear pods
    beside top-narrow torsos.
  - **Viewer (semi-realistic look):** sRGB output with a filmic (ACES) tone map (light paint schemes such as arctic no
    longer blow out to white), an image-based studio environment so metal reflects, a warm key / cool fill / rim light
    set, 2048 shadows, materials by class (satin painted plate, darker reflective frame and weapon metal, glass cockpit,
    matte panel lines), the black outline on every block off by default (an "Edges" button turns it back on: it made the
    models read as toys), and a `<meta charset>` (the badge showed "Â·").
  - **Visible changes:** arms move a little in or out on most units, the shoulders of leaning torsos are lower, heads on
    front / boom mounts move forward, arm guns sit against the forearm. Volume calibration still within 8 percent.
  - **Still open (not done here):** the skeleton-and-shell rebuild of torsos and limbs (still boxes) remains the biggest
    step toward "military hardware"; surfaces are flat-shaded convex hulls with no bevels or decals; the audit counts
    floating, not ugly overlaps between non-arm blocks.

- **2026-11-03 (Claude), session 17 - WEAPON-CHOICE LOOKUP TABLES (Daniel's design).** REVIEW PENDING
  (higher-level model). Daniel: "Choice should be: 'For that target, what is the base TN, and what is
  the range' After that it should just be a look up table to find the precomputed best mix of weapons
  for that situation. And that Cache is only refreshed if the mech takes battle damage that changes its
  options." Speed only: 47 of 47 checks, every reference log identical (also --round-trip), the 12 v 12
  log hash unchanged, benchmark 501 / 495.
  - `weapon_selection.FireTable`: per (distance, pre-TN, side) the candidates and the knapsack's levels;
    a query's movement heat only filters them (`knapsack_levels` + `best_within` - the same answer and
    tie-break as solving at that budget, `tests/test_fire_tables.py`). `select_weapons_to_fire` split into
    `heat_limits` / `fire_candidates` / `_finish_choice` (unchanged behaviour). Rust `knapsack_levels`
    in `fastcore` (default on, Daniel).
  - Shared across scorers: `shared_fire_table`, keyed by both units' `fire_state` (damage incl. every
    slot and bin, heat, prone / shutdown, TAG, Narc pods, stealth, TSEMP / IMP, sinks switched off) plus
    the weapons that can't fire, dissipation, other heat and the scorer's role (aimed / unaimed / future
    damage, AMS, water). Emptied every turn and on a saved-state load. `config.FIRE_TABLE_VERIFY` (test
    switch) recomputes every answer fresh and keeps the tables across turns - leaving the target's state
    out of the key fails it (tried); leaving the unit's own state out does not (the other parts changed
    with it in those battles) - kept in anyway.
  - Measured (12 v 12 Gladiator + Legate, 2 turns, CPU seconds, a noisy shared machine): weapon choice
    in movement scoring ~11.5 s (28%) -> ~9 s (24%); the battle ~41 -> ~39 s (~5%). Why not more: of
    565,648 scoring queries, 283,101 miss the scorers' own memos and need 152,829 different
    (distance, pre-TN, side) rows - the situations really are that many (range 1-30, pre-TN, 4 sides
    with structure weighting on, the arcs' weapon sets). Tried and dropped: solving each row at the
    largest budget up front (bigger knapsacks cost more); tables per scorer without sharing are SLOWER
    than before (13.5 s) - the sharing is what pays. `fire_state` costs ~84 us (1.4 s a 12 v 12 2-turn
    run): a cheaper signature is the next small win.
  - Lesson for the Rust port: the cost is in building ~150k candidate rows (planner, to-hit, tables per
    weapon), i.e. the per-weapon pricing - that is the loop to move as a whole, over flat per-weapon data.

- **2026-11-03 (Claude), session 17 - RUST TRIAL + WEAPON-KIND CACHES.** REVIEW PENDING (higher-level
  model). Daniel: "Move on to testing if rust will give us any extra speed" (long run: Rust or C; keep
  Python's modularity for now). Speed only: 46 of 46 checks, every reference log identical, benchmark
  501 / 495.
  - Profile, 12 v 12 Gladiator v Gladiator (Legate on), 4 turns under cProfile (~2x slower than real):
    Legate estimate 51%, movement 43% (two-ply 27%, reachable spots 8%); by function, the weapon choice
    `select_weapons_to_fire` 43% cumulative (618k calls; the bots dry-run what they would fire from each
    spot). Inside it the arithmetic is small; the time is plumbing: `canonical_name` 31M calls,
    `fire_modes.special` 1.3M calls (47 s cumulative), `get_weapons` rebuilt 351k times, the Planner.
  - Rust: `fastcore/` (PyO3 + maturin crate) with `best_subset`, the weapon choice's 0/1 knapsack, now
    pulled out of `select_weapons_to_fire` as `weapon_selection._best_subset_python` (the spec; ties and
    sum order copied exactly). Same answer on all 124,680 knapsacks of a 4 v 4 and on 20,000 random ones
    (`tests/test_fastcore.py`; skips when not built). Per call 0.85 us v 2.89 us (3.4x; most of the 0.85
    is turning Python lists into Rust ones). But the knapsack is 5.7% of a battle, so a 4 v 4 gained ~1%
    (inside the run-to-run noise). `config.USE_FASTCORE` (on; not built = Python).
  - Python: `fire_modes.special` / `has_profile` cached on the weapon (they depend only on its kind, as
    `canonical_name` already was): 4 v 4 3 turns ~22 -> ~20 s, 12 v 12 2 turns 45.5 -> 41.9 s (~8%),
    logs identical.
  - Lesson (Pick up here 13): Rust pays only for a big piece of work done in one call on flat data -
    a kernel this small saves less than its boundary costs matter. Next candidates, in order: more
    weapon-kind caching and per-turn flat weapon descriptors in Python (cheap, ~same results check),
    then the per-spot scoring (to-hit + weapon choice for plain weapons) in Rust over those descriptors.

- **2026-11-03 (Claude), session 17 - PYPY TRIED: NO GAIN (no code changed).** Daniel: "Test PyPy" (long
  run: Rust or C, keeping Python's modularity for now). PyPy 7.3.20 (Python 3.11) + numpy 2.4.6, in the
  scratchpad only. The dice are identical (same stream hash as CPython). Speed: the 10-turn benchmark
  8.0-8.4 s v 2.5-3.1 s under CPython 3.13 (same result, 501 / 495); the reference battles 51 s v 20 s;
  a 50-turn Asymptote mirror in one process, seconds per 10 turns PyPy 7.4 / 4.3 / 3.7 / 2.8 / 3.0 v
  CPython 2.5 / 3.3 / 2.8 / 2.3 / 3.0 - once warm it only ties. Its JIT log: 30% of the run compiling,
  255 loops + 733 bridges (very branchy code, few tight loops), 6 traces too long. Results: 12 of 15
  reference logs identical; 3 differ only in a printed rounding (7.375 -> "7.37" v "7.38": a last-bit
  float difference, same moves and scores). Verdict: not worth it. The lesson for the compiled path:
  the time is spread over branchy object code, so a port pays only where a loop is reshaped into
  flat-data work (Pick up here 13).

- **2026-11-03 (Claude), session 17 - SAVED STATES (end of turn).** REVIEW PENDING (higher-level
  model). Daniel: "load the board, units, their states and positions, and probably a count of how many
  rnd numbers have been used, and from there the engine will just continue"; a branch keeps the same
  dice by default, with a switch for fresh dice. Built:
  - `orchestrator`: `run_skirmish` split into `Battle` (units, board, dice, result, stats, turns done),
    `_start_battle`, `play_on` (turns from `battle.turn + 1`), `_play_turn` (the old turn body,
    unchanged) and `_finish`; `after_turn(battle)` hook (may hand back a reloaded copy to play on).
  - `INTEGRATION__saved_state.py`: `capture` / `restore`, `save` / `load`, `play_on_from`, a command
    line. Saves the battle (units with all their state, the board as it stands, the dice - the numpy
    generator's own state and the place in its block of rolls, not a roll count), the bots' memories
    (Princess's team heat maps / posture, Legate's plans and team-fire cache, severed limbs, stub
    counts) and every setting. Memories keyed by id(unit) are stored by unit name; caches are emptied
    on load and rebuild themselves. Found by the round-trip check: `destroyed_slot_info`'s
    `instance_id` is id(component), so a reload revived destroyed ECM / Artemis / ammo bins; the save
    keeps each named component beside its record and re-points it on load.
  - `config.SAVE_STATE_TURNS` / `SAVE_STATE_BATTLES` / `SAVE_STATE_DIR` / `SAVE_STATE_ROUND_TRIP`
    (test switch); `saved_states/` git-ignored.
  - Checks: `check_reference_logs.py --round-trip` (all 15 reference battles saved and reloaded after
    every turn: byte-identical); `tests/test_saved_state.py` (a 2 v 2 Gladiator + Legate v Princess
    team reloaded every turn, again with Legate's team-fire / herding / cohesion options on; a file
    played on; same dice repeat, fresh dice branch; settings restored; bad files refused). Leaving out
    Princess's memory or the component re-pointing makes them fail (tried); leaving out Legate's
    team-fire cache does not (it recomputes the same values - saved anyway).
  - Size / speed: a 12 v 12 save is 57 KB and takes under 10 ms to write or read.
  Engine results unchanged: 45 of 45 checks, every reference log identical, benchmark 501 / 495.

- **2026-11-03 (Claude), session 17 - RNG CLEAN-UP: ONE POOL OF DICE.** REVIEW PENDING (higher-level
  model). Daniel: "Do a clean up pass" (first step of the saved states). Every roll of a battle already
  came from its `BattleRNG`; the leftovers are gone: the orchestrator's `random.seed` (nothing drew from
  it since the tripod fix of 2026-10-21; its comment was stale), config's fallbacks to Python's `random` /
  numpy's global generator (now `config.active_rng()`: the battle's pool, or a private unseeded
  `BattleRNG` for rolls outside a battle), and Pathfinder's dead `resolve_combat_roll` /
  `_roll_weapon_damage` (their caller, combat_turn.py, was deleted long ago) with `BattleRNG.random()`.
  New `tests/test_rng.py`: real battles (a duel; a 2v2 with Gladiator + Legate + kill curve v Princess,
  tripods) with Python's `random` and numpy's global generator booby-trapped (shown to catch a planted
  draw). Speed-only change: 44 of 44 checks, every reference log identical, benchmark 501 / 495.

- **2026-11-03 (Claude), session 17 - ARCHER BV CONFIRMED.** Daniel pasted a BV breakdown for the
  Archer ARC-2R: 1,477 (defensive 786.6, offensive 689.92), the same as `INTEGRATION__battle_value`.
  The 2026-10-29 review's recalled 1,415 was wrong; review item (b) now holds only the Crusader
  CRD-3R. New check in `tests/test_battle_value.py`. No engine change.

- **2026-11-03 (Claude), session 16 (cont.) - FASTCORE GUARD FIX; REFERENCE TAGS FROM 3D STUDIES.** REVIEW PENDING
  (higher-level model). In a fresh checkout without the Rust wheel, `import fastcore` found the repo's own
  `fastcore/` crate folder and imported it as an empty package, so the "not built = Python" fallback never
  ran and every battle crashed (`AttributeError: ... knapsack_levels`; 37 of 47 checks failed). Both the guard
  in `INTEGRATION__weapon_selection.py` and `tests/test_fastcore.py` now treat a `fastcore` without the Rust
  functions as not built. Python path unchanged, results identical; 47 of 47 pass. Also: Combat Lab reference
  tags for eight chassis from whole-model / part-kit studies (`INTEGRATION__COMBAT_LAB.md` round 3).

- **2026-11-03 (Claude), session 16 (later) - FLAKY TEST NOTED.** REVIEW PENDING (higher-level model).
  `tests/test_hazards.py` `magma_heat_is_uncapped` failed in 2 of 4 consecutive `run_checks.py` runs on the same
  code (art-only commits, nothing in the engine changed) and passed the rest. Not diagnosed: the assertion
  compares `current_heat` with `15 + 5 + 10 - sinks + heat.engine_heat(m)`, so something in the heat or
  placement setup is not deterministic. Worth a look before anyone trusts a red or green on it.

- **2026-11-03 (Claude), session 16 - COMBAT LAB TOKENS v4 + BLOCK LIBRARY.** REVIEW PENDING
  (higher-level model). Tokens (output only, no engine change; `python tests/run_checks.py` 43 of 43):
  `plan` / `profile` / `hips` features (so top and side differ), armor thinning per location (thinner
  when under-armored, never thicker; Daniel 2026-11-01), the `read_unit` armor-parser fix (it never
  matched, so armor bulk had been constant), mounts for shoulder racks, then a block library from a
  study of a fan-made MWO Timber Wolf parts kit Daniel uploaded (files kept out of the repo, only
  descriptions and original shapes committed): chamfered boxes, `canopy` torso with wing bays, lozenge
  pod arm, knee disc covers, weapon sections by kind. Notes: `INTEGRATION__COMBAT_LAB.md`; vocabulary:
  `data/token_blocks.json`; sheet republished (claude.ai artifact CS8cdEG8rBR2jU5o3t1Y8a).

- **2026-10-31 (Claude) - DOCS: COMBAT LAB FRONT END = HTML; COMPILED PHYSICS CORE QUEUED.** REVIEW PENDING
  (higher-level model). Daniel chose the HTML front end (local `.exe` + browser, offline) and asked that
  condensing the physics core into a faster language go on next week's list, bots staying in Python
  (pick-up items 12-13). No code changed.

- **2026-10-30 (Claude), session 15 (cont.) - COMBAT LAB GUI WISH LIST FILED (docs only).** REVIEW PENDING
  (higher-level model). Daniel's notes (as summarized by GPT) split into
  `INTEGRATION__COMBAT_LAB.md`: Part A future ideas, Part B functional spec, each with Claude's notes
  (state snapshot is the foundation; tkinter v. HTML and `.blk` v. `.mtf` questions for Daniel).
  Pick-up item 12 added. No code changed.

- **2026-10-30 (Claude), session 15 (cont.) - COHESION REWARD BUILT (OFF): IT GROUPS THE FORCE BUT
  DOESN'T WIN BATTLES.** REVIEW PENDING (higher-level model). Daniel: "Reward staying within a range
  braket of its allies, stronger at short, much weaker at long. And how many allies are in mutual
  support range." `legate._Cohesion` (`config.LEGATE_COHESION`, off): per teammate (at its estimated /
  real end spot) a spot in its short / medium / long bracket earns `LEGATE_COHESION_REWARD` 2 / 1 /
  0.25 damage points, mutual support `LEGATE_COHESION_MUTUAL` 1 more, times `LEGATE_COHESION_SCALE`,
  taken off the damage taken. Refinements: `LEGATE_COHESION_MAX_ALLIES` (best N teammates count);
  `LEGATE_COHESION_THREATENED_ONLY` (a spot no enemy can reach needs no support - counts as fully
  supported; the first build gave it ZERO, which pulled units into the enemy's reach: 15 / 2 / 3, a
  bug, fixed); `LEGATE_COHESION_PAIRING` "either" (Daniel: "A fire support unit in the back will feel
  like its out of position because its not in cohesion with a short ranged back stabber up front. The
  back stabber however will feel fine since it has covering fire" - the pair is judged by whichever
  unit covers the other; support inside either support range). `baseline_battery.py --cohesion
  SCALE`. Battery, same 20 seeds, on the current default (Princess wins / draws / Gladiator wins;
  'Mechs left P / G; Gladiator units with no friend within 4 hexes, turns 11+): no cohesion 8 / 4 / 8
  (2.65 / 2.1; 45%); "ally" pairing x0.5 9 / 6 / 5 (3.65 / 2.15; 10%), x1 11 / 4 / 5 (4.2 / 1.5; 6%),
  x2 12 / 5 / 3 (3.65 / 1.4; 4%) - the force balls up; "either" + 3 allies + threatened only x0.5
  8 / 6 / 6 (2.8 / 1.95; 20%, Princess 21%), x1 13 / 4 / 3 (4.35 / 1.4; 16%). Best is "either" x0.5,
  level with no cohesion within 20 battles' noise; stronger is worse. Default stays off. Replay of an
  "ally" x0.5 battle published for Daniel. Reference logs unchanged; 43/43 checks.
- **2026-10-30 (Claude), session 15 - LEGATE DIAGNOSIS: DANIEL'S FIVE SUSPECTS MEASURED; THE
  FIRE SPLIT NOW COVERS THIS TURN TOO, AND IS THE DEFAULT.** REVIEW PENDING (higher-level model).
  Daniel's suspects: the IF/THEN estimate leads units astray; units model their move off the wrong
  unit; weights; a systemic error; poor cohesion - and "measure not just how wrong the prediction
  was, but to the degree it was wrong". New probe battery `tests/legate_probe.py` (report:
  `tests/legate_probe_report.py`; same results as the battery, so the probes don't perturb): it
  re-scores every Gladiator move at the end of the Movement Phase with the enemies at their TRUE end
  spots (the damage the estimate missed, and the regret of the pick), and with `--calib` checks the
  movement model's expected damage pair by pair with everyone at their real spots. Findings (20
  battles, baseline):
  (1) Estimate: off by 2.7 hexes a unit (within 2 hexes about half the time) - WORSE in hexes than
  "everyone stands still" (2.0), but closer in damage terms (4.5 points off a move v 5.4), and the
  pick it led to was within 2.5% of the best in hindsight (half the picks were the best). Swapping
  it for "stands still" (`--estimate hold`): 11 / 5 / 4 (3.9 / 1.3 left) - no better. Not the cause.
  (2) Wrong unit: the primary foe (the two-ply one) fired at the mover 45% of the time and is ~1/3
  of the predicted damage; small.
  (4) SYSTEMIC ERROR, FOUND: a move score counts every enemy that can reach the spot as shooting it
  THIS turn - 4.8 enemies a move, 1.1 really fired; predicted damage taken 2.3x the actual. The fire
  split (2026-10-29) shared only the FUTURE fire, so it made HP worth more while this turn's damage
  stayed ~4x too high: the stall. Fixed by `config.LEGATE_SPLIT_THIS_TURN` (`legate.now_share`: the
  same share on this turn's damage, in the move score and the estimate). Calibration (3 battles, raw
  points, the pairs that fired, everyone at their real spots): incoming fire is right (model 6.9 a
  Princess attack, actual 7.0); Gladiator's own is ~25% high (5.8 v 4.6; the fire phase's own dry
  run says 5.0) - a smaller bias, open (Section 0 Pick up here 0000).
  (3) Weights: not swept; (5) Cohesion, CONFIRMED: Gladiator units with no friend within 4 hexes,
  turns 1-3 / 4-10 / 11+: 19% / 26% / 47% (Princess 9% / 12% / 22%); alone AND ahead of their team
  21% late (Princess 9%). Herding at its placeholder weight barely moves it (42%).
  Battery, same 20 seeds (Princess wins / draws / Gladiator wins; 'Mechs left P / G): baseline
  8 / 8 / 4 (3.3 / 1.9); estimate replaced by "stands still" 11 / 5 / 4 (3.9 / 1.3); fire split with
  this turn too 8 / 4 / 8 (2.65 / 2.1) - the best yet; + herding 9 / 4 / 7 (3.1 / 2.25). DEFAULTS NOW
  `LEGATE_FIRE_SPLIT = "proportional"` and `LEGATE_SPLIT_THIS_TURN = True` (Daniel's rule: defaults
  match the best measured). Reference logs unchanged (duels; Legate needs 2+ enemies). 43/43 checks.
- **2026-10-29 (Claude), session 14 (cont.) - TEAM AWARENESS: FIRE SPLIT, HERDING,
  TEAM VALUE, EXCHANGE - BUILT AS OPTIONS, NONE BEATS THE BASELINE YET.** REVIEW
  PENDING (higher-level model). Daniel's designs (Pick up here 0000), all in
  `INTEGRATION__legate`, all off by default: `LEGATE_FIRE_SPLIT` (fire_share),
  `LEGATE_HERDING` (_Herd), `LEGATE_TEAM_VALUE` "sum" / "product" (_TeamFire: the
  enemy's fire this turn distributed over the team, greedy "most hurt, not
  already doomed"; the team's future damage with kill curves), and
  `LEGATE_TEAM_EXCHANGE` (our fire on the enemy by the same rule; the enemy's
  future damage removed counts too). Battery, same 20 seeds, Legate, target stub,
  big guns first (Princess wins / draws / Gladiator wins; 'Mechs left P / G):
  baseline 8 / 8 / 4 (3.3 / 1.9); fire split 4 / 16 / 0 (5.55 / 3.35 - stops the
  light dive, then both sides go passive); herding 8 / 8 / 4 (3.25 / 2.0 - half
  the battles end differently, the totals don't move); split + herding 1 / 19 / 0
  (5.3 / 3.25); + team value "sum" 12 / 4 / 4 (4.45 / 1.5); + "product" 17 / 3 / 0
  (5.75 / 0.45); + "sum" + exchange 18 / 1 / 1 (5.4 / 0.25). Reading (not yet
  checked in replays): each mover scores its spot with its teammates at their
  ESTIMATED spots and the enemy shooting whoever it hurts most, so it can count on
  a teammate to draw the fire (and, with the exchange, to finish its kills) - and
  every teammate reasons the same way at once: the force over-commits. Next:
  check that in replays; then let a mover count the teammates yet to move at
  their own best spots / their own risk (a coordination step), before tuning
  weights. Also fixed: the long-flaky check (`test_superheavy` superheavy_slots,
  live dice in an ammo blast's critical rolls, ~1 run in 20). Battery flags:
  `--fire-split`, `--herding`, `--team-value`, `--fire-order`.
- **2026-10-29 (Claude), session 14 - KILL CURVE, FIRE DIRECTOR, BIG GUNS FIRST;
  TWO CRASH FIXES; WHY GLADIATOR LOSES.** REVIEW PENDING (higher-level model).
  Summary for Daniel and the next session: `INTEGRATION__BOTS.md`.
  - `INTEGRATION__kill_curve` (Daniel: "a function that takes incoming damage and
    converts it into a % chance of mission kill ... rule of thumb ... 5 point
    clusters"): 100 trials of 5-point groups through `attack_resolution.
    _resolve_hit` on a pickled copy, own dice (config's roll functions swapped),
    cached per unit / side / damage state; ~0.05-0.1 s a curve. Mission kill:
    STUB_MISSION_KILL ("destroyed" default; "no_ranged_weapons"), after Daniel
    ruled out the book's Crippled ("that pilot should run") and noted spotting
    has no worth yet.
  - Fire director (STUB_GLADIATOR_TARGET "kill_curve", not the default): worth x
    (kill chance added on top of friends' declared fire + KILL_CURVE_PROGRESS_WEIGHT
    x useful damage / damage still needed). The softening term came from Daniel:
    "are units taking long shots to marginally increase a kill vs a hurt unit
    instead of applying stronger damage vs a unit that needs to be softened
    first?" - they were (a 1% gain beat a full volley 100 to 1).
  - Big guns first (GLADIATOR_FIRE_ORDER, default; Daniel's rule).
  - Speed only: `mech_state.mech_shields` remembers a 'Mech with no shield.
  - Crash fixes (both reproduced, tests added): a charger / pusher / DFA
    attacker advancing into its target's old hex goes through the domino code
    when a fall from above (p.116) put another 'Mech there (MegaMek's
    doEntityDisplacement; two enemies had ended up stacked); Princess's facing
    to a point in its own hex is MegaMek's Coords.direction, 5.
  - Battery, same 20 seeds, + Legate: stub 7 / 9 / 4 (Princess / draw /
    Gladiator); fire director with list-order firing 15 / 5 / 0; fire director +
    big guns first 9 / 8 / 3, 'Mechs left 4.3 / 1.3 (replays of all 20, run on
    the fixed code). Analysis (scratch scripts over the replays): Gladiator lost
    53 units in turns 1-6 v Princess's 29; 46 of the 53 were lights that dived
    ahead alone on turn 2. Cause: Legate's MultiLifetime divides HP by ALL
    enemies' damage a turn, so a unit's life looks ~3 turns long and bad trades
    score well (Pick up here 000 "how much fire a single unit would take").
    Also: no cohesion pull (heavies' nearest friend 6.4 hexes v Princess's 4.2
    on entry). Daniel's question "is it starting positions?": the first movers
    see ~2 enemies on turn 1 but end further back than Princess's, not worse.
  - Daniel's next topics are Pick up here 0000; ammo conservation is item 3.
- **2026-10-29 (Claude), session 14 - BATTERY RE-RUN WITH THE PRINCESS FIX; KILL-
  CURVE IDEA.** Daniel: "Rerun the 20 battle set with the corrected princess.
  Mostly for curiosity." Same 20 seeds, stub + Legate (both defaults), after the
  `max_damage_at_range` fix below: Princess 7 wins / 9 draws / Gladiator 4 wins
  (unchanged from before the fix); damage dealt Gladiator 1274 / Princess 1601
  a battle (was 1235 / 1543); 'Mechs left Princess 3.2 / Gladiator 1.8 (was
  3.65 / 2.10); 249 s a battle. Rows in `run_stats/baseline/pg_legate_princess_plan_
  seed12345_*`. Ammo conservation for Gladiator added to Pick up here 3.
  Daniel's next idea (discussion, nothing built): a 'Mech's "vulnerability" as
  the curve f(N) = P(destroyed after N more damage) from its current state, by
  damage grouping; target value = expected output / vulnerability; a hit's
  worth = how much it shortens the damage still needed. A scratch prototype
  (`_resolve_hit` in fixed-size groups, front table, no damage PSRs) gave an
  Atlas AS7-D an expected 170 / 254 / 223 damage to destroy in 1- / 5- / 20-point
  groups (1-point: 83% die of 6 pilot hits, p.117; 20-point: 33% head kills), and
  a Commando 45 / 51 / 38. From fresh (255 left, 5-point groups) 10 into the left
  arm was worth ~0, 10 into the centre torso 13, 10 into the head 116.

- **2026-10-29 (Claude), session 14 - AMMO RUNS OUT; PRINCESS'S QUICK ESTIMATE FIX.**
  Daniel: "did that emperor in battle 10 still have ammo by that point, and if it
  didnt, was it still acting like it did?" Battle 10 re-run (same seed) with
  every bin read at each end phase. Gladiator's Emperor fired its two Rotary
  AC/5s at `STUB_RATE_OF_FIRE = "max"` (6 shots each a turn): 120 rounds, 36 left
  at turn 10, dry by turn 20; from then on it fired its ER large lasers only, and
  its movement scoring knew (ranged_combat / future_damage drop empty weapons).
  Princess's Emperor still had 54-78 rounds (MegaMek's own fire control). And by
  turns 30-40 nearly every ammo weapon on the field was empty on both sides
  (every LRM 20 / 15, both Gauss Rifles, Ultra and LB-X ACs): the LRM carriers
  are left with medium lasers - another stall cause (they hang back at LRM range
  with nothing that reaches). BUG FIXED (MegaMek parity):
  `princess_fire.max_damage_at_range` (FireControl.getMaxDamageAtRange) counted
  weapons that are out of ammo, jammed or a spent one-shot; MegaMek skips them
  (`weapon.isCrippled()`). It feeds Princess's close-range pull (modern), the
  v0.50.07 estimate against an enemy yet to move, and the target-threat term of
  the firing-plan utility - so Princess planned with empty guns and read an
  enemy's empty guns as a threat. Now skipped; `close_range_incentive` memoizes
  it per ranking (45 us a call). No reference log changed (no Princess battle
  in them runs dry). OPEN, Daniel's (a research stub): Gladiator's
  rate-of-fire policy ("max" empties an Emperor in ~10 turns of fire).

- **2026-10-29 (Claude), session 14 - WHY 12 v 12 BATTLES STALL (diagnosis, no code).**
  Daniel: "Based on the game records can you get a feel for why the games are
  stalling out?" Four of the 9 cap draws of the stub + Legate run (battles 2, 9,
  10, 18) re-run with replays and read turn by turn. Three causes:
  (1) THE CAP IS TIGHT FOR 24 UNITS: battles 2 and 18 were mop-ups (Gladiator's
  last 1-2 'Mechs at 138-165 HP, 2-4 more turns at the late damage rate);
  battle 9 a slugfest still trading (~20 more turns). Decisive battles end at
  turns 16-49. (2) BOTH BOTS PARK: about half of all moves are Stand Still, in
  every stage of the battle, both bots; the nearest enemy sits ~10 hexes off
  and the late damage rate is 10-60 HP a turn a side against 1000-1800 HP left.
  Battle 10 is a standoff: Princess's Atlas and Emperor at full HP stood still
  all of turns 35-50 at 18-20 hexes, firing nothing worth it most turns;
  Gladiator's Emperor stood still 16 of 16 turns. Suspects: Princess modern's
  position-hold credit (and its DEFEND posture, which is not logged), and
  Gladiator's lifetime objective, which prices a long-range trade as good
  enough. (3) NOBODY HUNTS A STRAGGLER: battle 2, six Princess 'Mechs took 11
  turns over one Gladiator Cataphract; one Princess Awesome sat 22-24 hexes off
  with no line of sight for 11 of 12 turns. Analysis scripts were in the session
  scratchpad (per-turn and per-unit tables from replay JSON).

- **2026-10-29 (Claude), session 14 - LEGATE ON BY DEFAULT.** Daniel: "Legate on
  by default in multi unit games." `config.LEGATE = True` (it only acts with 2+
  enemies on the board, so duels and every reference log are unchanged);
  `baseline_battery.py` follows the config (`--no-legate` for the old Gladiator).

- **2026-10-29 (Claude), session 14 - GLADIATOR TARGET CHOICE STUB.** Daniel:
  "a good test to stub in until we teach gladiator how to focus fire and account
  for target saturation." `config.STUB_GLADIATOR_TARGET` (default
  "princess_plan", "nearest" = the old pick), `stubs.stub_gladiator_target`: a
  Gladiator unit with 2+ enemies on the board takes Princess's target choice
  (`princess_group.choose_target`, scored through Princess's fire control while
  `bots.princess_eyes` is on - so friends' declared damage counts and an enemy
  they are expected to kill scores low), then picks its own weapons as before;
  its declaration goes into the team's damage map (`bots.records_declared_damage`)
  for the teammates after it. Duels unchanged (all reference logs match).
  `baseline_battery.py --target`. Test: `test_princess_group.py`
  `gladiator_borrows_princess_target_choice_and_spreads_its_fire`.
  RESULT, Princess (Red) v Gladiator (Blue), 12 v 12, the same 20 seeds, no
  Legate (stub / the recorded "nearest" run): Princess won 14 / 14, draws 6 / 6,
  Gladiator 0 / 0, Gladiator wiped out in 14 / 14; turns 37.2 / 36.7; Princess
  'Mechs left 6.1 / 7.0, HP left 2156 / 2295; damage Gladiator dealt 898 / 772
  (+16%); damage Princess dealt 1691 / 1674; Gladiator 'Mechs left 0.70 / 0.75;
  133 / 143 s a battle. Reading: better targeting buys about two-thirds of
  Legate's damage gain (+24%) at no time cost, but wins nothing and Princess's
  damage to Gladiator is unchanged - Gladiator still takes about twice what it
  deals. Target choice is part of the gap, not most of it: the rest is where
  Gladiator stands (movement) and how much fire it soaks.
  STUB + LEGATE (Daniel: "Stub plus legate. Go."), same 20 seeds (stub+Legate /
  Legate alone, recorded 2026-10-28): Princess won 7 / 15, draws 9 / 5,
  GLADIATOR WON 4 / 0 (battles 1, 13, 15, 20 - its first wins in a 12 v 12);
  Gladiator wiped out in 7 / 15; turns 42.8 / 39.6; Princess 'Mechs left 3.65 /
  5.6, HP left 1776 / 2068; damage Gladiator dealt 1235 / 959 (+29%); damage
  Princess dealt 1543 / 1721; Gladiator 'Mechs left 2.10 / 0.35; 260 / 259 s a
  battle. Reading: the two together are far more than either alone (stub alone
  +16% damage, Legate alone +24%, both +60% over the plain bot, 772 -> 1235) -
  Legate's positioning puts several Gladiators in range of the same enemies,
  and the shared target choice turns that into kills. The damage ratio went
  from about 1 : 2.2 to 1 : 1.25. 9 cap draws now: the anti-stall item matters
  more.

- **2026-10-29 (Claude), session 14 - REVIEW OF SESSIONS 12-13 (Sonnet's work).**
  Daniel: "quickly review the work done by Sonnet models. If they're kosher we
  can clear their 'review this' flags." Read against the Core Rulebook and
  MegaMek's source (main 4f22bf6): (1) multi-unit battles - Unequal Numbers
  reproduces both p.41 tables (18 v 10, 14 v 5); the domino effect and the
  accidental fall from above follow pp.113-116, and the fall damage's
  "target's height" matches MegaMek's Core rules (a standing 'Mech 1, prone 0):
  OK. (2) Map picker: OK (minor: a pack map extracted to the temp folder is never
  refreshed if the pack changes). Map stitching: the seam-parity question is
  Daniel's (Section 0 REVIEW QUEUE (a)). (3) Movement cache: BUG FIXED - a magma
  crust that breaks becomes liquid (+1 MP, TO:AR p.30), but `_BoardCache` kept
  the crust's step cost for the rest of the battle; `test_hazards.py`'s cache
  check only passed because it read the stale 1 MP entry. Now
  `INTEGRATION__hazards` drops the board's cache (`pathfinder.forget_board`)
  when a crust breaks or is mended, and the check breaks a crust for real and
  wants the 2 MP entry (it fails on the old code). No reference log changed.
  (4) Princess group: mutual support, the ally centre and the posture's closing
  test and hysteresis match MegaMek's Java. Battle Value: REVIEW QUEUE (b).
  (5) Legate: the cascade / lock rules do what the docstring says; minor: in
  `Extras.adjust` a spot where another enemy is estimated to stand skips that
  enemy (a slight pull toward its hex - harmless while it is only an estimate).
  42 of 42 checks pass.

- **2026-10-28 (Claude), session 13 - LEGATE (first version).** **REVIEWED 2026-10-29 (higher-level model; see the review entry).** Daniel: "making gladiator less myopic ... a multi-unit
  bot layer at the start of the movement phase ... I call this layer Legate; it's
  in charge of keeping tabs on the battlefield", then his answers: the IF/THEN
  runs 12 rounds; ties in a round go by picker score and can cascade; a unit
  locks only when its own choices loop; the score is Gladiator's picker score
  with damage taken the sum over all enemies and damage dealt the max; the foe
  is the most threatening enemy yet to move; fire at the weapons phase goes to
  the enemy it can hurt most once positions are final. New `INTEGRATION__legate`
  (design in its docstring and the Section 6 row), `config.LEGATE` (OFF by
  default) / `LEGATE_ITERATIONS` 12, `bots.choose_foe`, `Extras` hook in
  `movement_selection._choose_normal` / `_static_scores`, `legate.plan_turn` /
  `end_phase` / `reset` in the orchestrator, `tests/test_legate.py` (12 checks),
  `baseline_battery.py --legate`. With it off, or in a duel, nothing changes: 42
  of 42 checks pass, reference logs untouched. Fire choice needed no change
  (`forces.choose_target` already picks among all enemies once positions are
  final). RESULTS (12 v 12 battery, seed 12345, 1 core each, 3 battles, Legate on
  for every Gladiator): Gladiator v Gladiator: Draw (cap), Draw (cap), Red; 50/50/44
  turns; 241/292/206 s (4.7-5.8 s a turn, was 2.2-2.9: about 2x; the estimate is
  ~45% of it). Princess (Red) v Gladiator: Princess won 2 and drew 1 (was 3
  wins); Gladiator had 0/3/0 'Mechs left (was 0/0/0); 34/50/39 turns; 233/289/276
  s (was 123-152). Three battles say little about strength; Legate costs about 2x
  at this size. To do (Pick up here 000): map reading, concentrated-fire estimate,
  speed, on-by-default decision.
  20-BATTLE RUN (Daniel: "a battery of 20 tests"), Princess (Red) v Legate
  Gladiator (Blue), seed 12345, 4 cores x 5 battles, about 25 minutes: Red
  (Princess) won 15, 5 draws at the 50-turn cap, Gladiator won none; Gladiator
  was wiped out in 15 of them and kept 1-3 'Mechs in the draws; 23-50 turns;
  168-351 s a battle. (The earlier 3-battle no-Legate Princess v Gladiator run
  was 3 Princess wins; a matching 20-battle no-Legate run was not made.)
  `baseline_battery.py` gained `--first/--last` (split over cores) and `--replay`.
  MATCHING 20 WITHOUT LEGATE (same seeds): Princess won 14, 6 draws, Gladiator
  none; Gladiator wiped out in 14. Averages over 20 (Legate / no Legate):
  turns 39.6 / 36.7; Princess 'Mechs left 5.6 / 7.0; Princess HP left 2068 /
  2295; damage Princess dealt 1721 / 1674; damage Gladiator dealt 959 / 772
  (+24%); Gladiator 'Mechs left 0.35 / 0.75; seconds a battle 259 / 143 (1.8x).
  Reading: Legate makes Gladiator hurt Princess more (about 10% more of
  Princess's HP lost, 1.4 more 'Mechs lost, 24% more damage dealt) but not win
  more: no Gladiator wins either way, and the draws are stragglers at the cap
  (5 v 6), the anti-stall item. Princess still wins every decisive battle.

- **2026-10-28 (Claude), session 13 - BASELINE TEST BATTERY.** **REVIEWED 2026-10-29 (higher-level model; see the review entry).** Daniel: "4 maps stitched together, 12 mechs vs 12
  mechs, mixed but mirrored (3 assault, 3 heavy, 3 medium, 3 light); Princess vs
  Princess, Princess vs Gladiator, Gladiator vs Gladiator. Mostly seeing if it
  works and how long it takes. Results will be recorded as a yard stick." Then,
  after the first try (2 x 2 boards, 404 s, 50 turns, a draw): "drop down to a
  2x1 map size." `tests/baseline_battery.py pp|pg|gg N` (field: Grassland 1 +
  Desert Hills stitched 2 x 1, 33 x 17; each side Atlas AS7-K, Emperor EMP-6D,
  Awesome AWS-8Q, Archer ARC-2R, Cataphract CTF-3D, Catapult CPLT-C1, Kintaro
  KTO-19, Griffin GRF-1N, Hunchback HBK-4G, Jenner JR7-D, Commando COM-2D, Locust
  LCT-1V; gunnery 4 / piloting 5; 50-turn cap; seed 12345, battle n uses
  battle_seed). YARDSTICK, each battle on ONE core (the three batteries ran at
  once on a 4-core box - Daniel: that is the 1-core baseline and keeps the
  yardstick the same size every time), code at the group-behaviors merge (PR #98):
  | setup | results (3 battles) | turns | seconds a battle (a turn) |
  |---|---|---|---|
  | Gladiator v Gladiator | Red, draw (cap), Red | 44 / 50 / 30 | 96 / 143 / 75 (2.2-2.9) |
  | Princess (Red) v Gladiator | Red x3 (Gladiator 0 left each time) | 24 / 45 / 34 | 123 / 152 / 147 (3.4-5.1) |
  | Princess v Princess | Blue, draw (cap), Blue | 35 / 50 / 27 | 243 / 417 / 257 (6.9-9.5) |
  The 2 x 2 first try (Princess v Princess, 1 battle): draw at the cap, 404 s
  (8.1 s a turn). FINDING: a Princess battle costs 2-3x a Gladiator one at 12 v
  12 (movement is 98% of the time; "Princess path ranking" ~110 s of 243 s) -
  the multi-enemy movement (every enemy evaluated per move) outweighs Gladiator's
  one-foe two-ply search; a speed pass on it is the obvious next step. 3 battles
  a setup is a yardstick, not statistics.

- **2026-10-28 (Claude), session 13 - PRINCESS FOR TEAMS + BATTLE VALUE.**
  **REVIEWED 2026-10-29 (higher-level model; see the review entry).** Daniel: "I think 1-5 are do able. 6
  requires us to calculate BV ... As usual use Megamek as source material where
  needed." Source: MegaMek main 7205e4d (a newer commit than the fd2edfb the
  modern clone was made from; the group code is the same in v0.50.07 where it
  exists - `BasicPathRanker`, `PathRanker`, `HeatMap`, `FireControl`,
  `PostureResolver`, `Coords.median`). Built: (1) `princess_fire`: the damage
  map and the overkill term (a team stops piling on an enemy it expects to
  kill); (2) `attack_resolution.declare_attacks(dry=True)` + `config.quiet()` -
  a dry run of the real weapon choice for each enemy, so Princess's target is
  the best firing plan (`princess_group.choose_target`, `bots.choose_target`);
  `run_ranged_phase` picks each unit's target when its turn comes (Gladiator's
  pick is pure, so nothing changes for it); (3) `princess_group.Group` and
  `princess_memory`: movement against every enemy, the closest enemy by
  adjusted distance, the median of the 4 closest to face, the force's posture,
  mutual support with the BV-weighted heat map, anti-crowding (default off);
  wired for both Princess versions; the orchestrator credits moves
  (`princess_memory.unit_moved`), fades the map each turn (`end_of_turn`) and
  resets it with the battle; (4) `INTEGRATION__battle_value` (BV 2.0) with
  `tools/build_equipment_bv.py` reading MegaMek's equipment classes into
  `mechsim/equipment_bv.json` (640 of the 699 items; every weapon and ammo bin
  of all 4,204 playable units in the pack is priced); `mtf_parser` now keeps
  `structure_desc` and `tech_base`. Checked: BV exact on the four published values
  and 1 off a fifth (Mad Cat Prime 2,737 vs the TRO's 2,738); a Warhammer
  1,299, Griffin 1,272, Shadow Hawk 1,064 and Awesome 1,605 land on the
  readouts too. `tests/test_princess_group.py` (17) and `tests/test_battle_value.py`
  (7). A duel with `PRINCESS_GROUP` off is hash-identical to before, both
  versions; the reference logs (no Princess) are unchanged. Duel A/B (20
  battles, Kontio v Hammerhead, `ab_batches.py --set princess-group`): Princess
  vs Gladiator, group off Red 7 / Blue 10 / Draw 3 -> on 5 / 13 / 2; Princess vs
  Princess 12 / 7 / 1 both ways. Left out on purpose: secondary targets (MegaMek's
  ordinary Princess fires at one target), the highest-BV cluster anchor
  (artillery / TAG standoff only), formations (CASPAR's ranker). OPEN FOR THE
  REVIEWER: the 7205e4d Java was read, not run (building MegaMek was not
  allowed here), so BV was checked against published values rather than against
  MegaMek's own output.

- **2026-10-28 (Claude), session 12 - MAP PICKER.** **REVIEWED 2026-10-29 (higher-level model; see the review entry).** Daniel: "Wire in the map picker. Will need it for the
  next trick, making the program easily accessible by a person, which is GUI
  work." `INTEGRATION__map_picker` in two layers so the GUI can reuse the
  first: the library (`list_maps` - the loose boards in data/ plus the
  356-board `maps.zip` pack, by name, pack folder and size; `resolve_board`;
  `playable` - what `prepare_board` refuses, e.g. bridges; `compatible_maps` -
  the stitch size rule per grid slot; `MapChoice` / `apply_choice` /
  `remember_choice`) and the console menu `choose_map(ask, say)` (last time's
  pick offered first; one board or a columns x rows grid up to 12; numbered
  list with a text filter; an unplayable map is refused with the reason).
  `config.PROMPT_FOR_MAP = True` makes `orchestrator._load_map` ask once per
  run and write the answer into config; with no keyboard it keeps the
  configured map. Config may now name a pack map directly
  ("AGoAC Maps/16x17 Desert 2.board") - `_load_map` resolves every name
  through the picker. Tests: `tests/test_map_picker.py` (8 checks, scripted
  answers). 39 of 39 checks pass, reference logs unchanged. GUI notes: call
  `list_maps()` for the list, `playable()` on demand (about 0.1 s a map, so not
  for all 356 at once), `compatible_maps()` per slot, `apply_choice()` to set.
- **2026-10-28 (Claude), session 12 - MAP STITCHING + OFFICIAL NAME.**
  **REVIEWED 2026-10-29 (higher-level model; see the review entry).** Daniel: "Short Grid is the official
  name now. Map stitching up and running." The name is recorded (the
  "placeholder" notes are gone). `config.STITCH_MAPS` works: `STITCH_BOARDS`
  (board files, row-major), `STITCH_GRID_COLS` x `STITCH_GRID_ROWS`;
  `orchestrator._load_map` calls the existing `board_parser.stitch_boards`
  (blank hex row / column at each seam, Daniel 2026-07-20; same-size rule), then
  `prepare_board` as for one board; a list that doesn't fill the grid is
  refused. Home edges, deployment, LOS, the movement cache and the replay
  viewer need nothing special (a 6v6 on two stitched 16x17 maps, 33x17, ran 14
  turns and replayed without console errors). Test:
  `test_terrain.stitched_map_loads_and_crosses_the_seam`. Not built: a map
  picker (built the same day, next entry); Section 6 gap: on a stitched board the home
  edges are the outer edges of the whole field, so long fields mean long
  approach marches. 38 of 38 checks pass, reference logs unchanged.
- **2026-10-28 (Claude), session 12 - MOVEMENT TABLE CACHE (speed only).**
  **REVIEWED 2026-10-29 (higher-level model; see the review entry).**
  Daniel's idea: compute only the hexes inside a unit's movement footprint
  and share them between units and turns. `pathfinder._BoardCache` (one per
  loaded board, filled on demand): hex info by (x, y); step cost, terrain
  PSRs and hazard per (from, to, backward, level limit incl. superheavy);
  facing-change PSRs; and finished movement tables keyed by (start, facing,
  MP, backward MP, level limit, blocked hexes within reach). Callers must treat
  a returned table as read-only. A loaded map must not be edited in place
  (test_pathfinder test 9 now edits a copy). A/B against the previous code,
  same seed, battle logs byte-identical: 4v4 grass 18.6 -> 13.9 s, 4v4
  scattered woods 16.0 -> 15.2, 4v4 hazardous badlands 8.9 -> 8.0, 12v12 grass
  (2 turns) 26.5 -> 12.5; 1v1 benchmark 2.6 s both (HP 501 / 495). Gains
  are biggest on the entry turn and big forces; battles that end early or on
  PSR boards gain little. 38 of 38 checks pass, reference logs unchanged.
  Caught in review before it shipped further: magma crust breaks mid-battle,
  so hazards are read live and a board with a hazard feature shares no
  finished tables (`_BoardCache.hazardous`; test
  `movement_cache_sees_a_broken_crust`, which fails without it). Smoke also
  lives on hex infos but nothing the search reads.
- **2026-10-28 (Claude), session 12 - MULTI-UNIT BATTLES.**
  **REVIEWED 2026-10-29 (higher-level model; see the review entry).** Daniel: units on
  teams, a lance / company against like forces, a free for all, a 3-way battle
  - "unleash a group of bots to operate independently". The two-'Mech battle
  is the same code with two units: every battle in the 15 reference logs
  plays out identically (benchmark HP 501 / 495); the logs were regenerated
  (`--update`) only because the results banner no longer lists "domino effects
  (no third mech)" as missing - 30 banner lines, nothing else. Built:
  - `config.FORCES` (list of `{team, mtf, count, name, gunnery, ...}`; None =
    Red vs Blue as before), `config.load_roster`, `FORCE_DEFAULTS`,
    `FOE_CHOICE`, `DOMINO_DODGE`. Labels: a team's only unit is called by the
    team ("Red"), else "Red 1", "Red 2"; a free for all = one team per unit.
  - `INTEGRATION__forces`: teams / enemies / stacking sets; `initiative_order`
    (any number of sides, ties re-roll among the tied); `activation_sequence`
    = Core p.41 Unequal Numbers (reproduces the book's 18 v 10 and 14 v 5
    tables - `tests/test_multi_unit.py`) generalized to 3+ sides like MegaMek's
    `TurnOrdered`; `move_index` (Princess's, for both bots); `choose_foe`,
    `choose_target` (Section 6 rows).
  - `orchestrator.run_skirmish` (and `run_battle` as its two-'Mech form):
    per-unit movement against the unit's foe with every mobile enemy's hex
    closed (`mover.blocked_hex` is now a set; `pathfinder._blocked_set`) and
    no ending in any other unit's hex (`reduced_options` takes a set; both
    Princess rankers too), TAG / ranged / physical phases over the whole force
    (`tag.designation_units`, `attack_resolution.run_ranged_phase`,
    `physical.run_physical_units`; the two-'Mech functions wrap them), AMS
    engagements shared by every attacker on a target (p.206, `_ams_used`),
    home edges for any number of teams, the battle ends when one team or none
    is left (p.41: last 'Mechs destroyed together = draw).
  - `INTEGRATION__domino`: a charge, push or DFA displacing a 'Mech into an
    occupied hex - domino effect (PSR, forced on a hex, fall on a failure,
    chains, destroyed with nowhere to go) and the accidental fall from above
    (TN 7 attack, damage, random neighbour) per pp.113-116; the old "domino
    effects (no third mech)" gap is closed. Not modeled: a submerged target's
    halved damage.
  - Results: `BattleResult.teams` / `.units`, `summarize_teams`; `.red` /
    `.blue` keep working for the teams of those names. Replay: any number of
    units and teams (colour per team, numbered markers, record sheets fold up
    past four units, click a marker for its sheet).
  - Not built (loud, Pick up here 00): any group behavior (mutual support,
    fire distribution, secondary targets p.64, a threat picture), Gladiator's movement
    scoring seeing more than one enemy. Timing: a 4v4 Kontio / Hammerhead
    battle ~40 s for 13 turns, ~0.5 s a unit a turn, the entry turn the
    slowest (`DEPLOYMENT_DEPTH` > 0 multiplies the entry search).
  Tests: `tests/test_multi_unit.py` (20 checks).
- **2026-10-28 (Claude):** Full pick-quality battery for the latest IF/THEN
  (hold still first + neighbour climb), against the recorded 2026-10-27/28
  runs: 8 scenarios x 20 battles, same seeds (Short Grid reproduced its
  recorded numbers exactly). `tests/pick_quality.py --perfect-cache FILE`
  (Daniel: "since Perfect is slow to generate, but once generated..."):
  Perfect's prices are saved per decision and reused while the battle
  follows the recorded path - scenarios 1-6 ran ~2x faster from the cache
  (`run_stats/`, git-ignored, lost with the session). FIRST MOVER (2,716
  decisions; % of range / got best / rank pct / hexes off / closer / ms):
    Perfect               100.0 / 100% / 100% / 0.00 / +0.00 / 1269
    Short Grid             96.1 /  49% /  95% / 2.47 / -0.11 /  196
    IF/THEN + climb        93.7 /  36% /  92% / 3.25 / +0.88 /  177
    IF/THEN 12 + climb     94.5 /  39% /  93% / 3.21 / +0.87 /  198
    (recorded) Short-Short 91.0 /  26% /  88% / 3.39 / +0.87 /   93
    (recorded) IF/THEN first version 85.1 / 18% / 73% / 3.94 / +1.98 / 102
    (recorded) Princess modern 75.7 / 9% / 61% / 4.31 / +2.82 / 45
  Per scenario, IF/THEN 12 + climb 91.2-95.7% (Short Grid 92.9-98.5); it
  beats Short Grid only on Atlas vs Archer (95.2 vs 94.2). Holds still on 20%
  of first-mover picks (Short Grid 18%, Perfect 11%). Moving second it is
  Perfect (every spot). One 'Mech against one, it costs about Short Grid's
  time - its saving is meant for multi-unit play (Section 5).
- **2026-10-28 (Claude):** IF/THEN neighbour climb (Daniel: "I like option
  2"), `config.MOVEMENT_IF_THEN_NEIGHBOUR_CLIMB` (on): after the back and
  forth, from the best attempt's hex score every state of that hex and its 6
  neighbours by the two-ply score, move to the best neighbour while it
  beats the current hex (`movement_selection._neighbour_climb`); test
  `if_then_neighbour_climb_ends_on_a_local_best`. `tests/pick_quality.py
  --pickers` (only the named pickers; Perfect always runs). Quick read
  (Daniel: "general feel, not full stats"): Catapult vs Jenner and Kontio vs
  Hammerhead, 8 battles each, FIRST MOVER (% of range / got best / rank pct /
  hexes off / closer / ms - ms run beside the test suite, so high):
    Perfect             100.0 / 100% / 100% / 0.00 / +0.00 / 2678
    Short Grid           97.3 /  45% /  96% / 3.16 / -0.45 /  321
    IF/THEN 12 steps     88.5 /  18% /  76% / 4.32 / +1.84 /  222
    IF/THEN + climb      93.3 /  29% /  89% / 4.29 / +1.59 /  293
    IF/THEN 12 + climb   94.5 /  34% /  91% / 4.20 / +1.48 /  325
  The climb is worth ~5-6 points of range for ~100 ms; the lean in shrinks
  but stays (+1.5 hexes).
- **2026-10-28 (Claude):** IF/THEN fixed steps, `config.MOVEMENT_IF_THEN_STEPS`
  (Daniel: "run like 10 to 15 steps, with an early stop if it lands on the
  same hex again. Then pick the best"): 0 = the climb (default), N = up to N
  attempts whatever they score, early stop on a hex already tried, the
  best-scoring attempt is the pick. Pick-quality picker "IF/THEN 12 steps";
  test `if_then_fixed_steps_keep_the_best`. Two worst scenarios, 20 battles
  each, same seeds, FIRST MOVER (% of range / got best / rank pct / hexes off
  / closer / holds still / ms):
    Perfect           100.0 / 100% / 100% / 0.00 / +0.00 /  8% / 2309
    Short Grid         97.1 /  42% /  96% / 3.19 / -0.40 / 12% /  281
    Short-Short        91.9 /  20% /  88% / 4.14 / +1.12 / 21% /  139
    IF/THEN (climb)    84.0 /  14% /  67% / 4.43 / +2.17 / 34% /  150
    IF/THEN 12 steps   88.9 /  19% /  78% / 4.36 / +1.87 / 29% /  198
  Catapult vs Jenner 86.6 -> 91.2, Kontio vs Hammerhead 80.2 -> 85.6.
  Traced (12 battles, 198 picks): it lands on a hex already tried after
  ~4-5 attempts (12 attempts in 4% of picks); the best attempt is #1 in 31%,
  #2 28%, #3 15%, #4+ 26%.
- **2026-10-28 (Claude):** IF/THEN's first attempt is now holding still
  (Daniel: "Its first step is 'If I hold still then...'" - to remove the lean
  from a high score against a stationary target, and to lock in quickly when
  holding still is best); without a Stand Still state (standing up, entering)
  it starts from the best spot against the enemy where it stands, as before.
  Rerun of the two worst scenarios (20 battles each, same seeds), FIRST MOVER,
  old -> new (% of range / got best / hexes off Perfect / closer / ms):
    Catapult vs Jenner   82.6 -> 86.6 / 18 -> 20% / 3.94 -> 3.64 / +2.29 -> +1.66 / 137 -> 147
    Kontio vs Hammerhead 80.0 -> 80.2 /  6 ->  5% / 6.59 -> 5.57 / +4.67 -> +2.92 / 150 -> 149
    both                 81.5 -> 84.0 / 13 -> 14% / 5.02 -> 4.43 / +3.26 -> +2.17
  (Short Grid 97.1 / 42% / 3.19 / -0.40 / 277 ms on the same picks.) The lean
  in shrinks by a third but a new lean appears: it holds still on 34% of
  first-mover picks (old 14%, Perfect 8%, Short Grid 12%). Traced (12
  battles, 192 picks): hold still kept 44%, 2 attempts 39%, 3+ 17%; stops on a
  lower score 168, repeat / no answer 24. The answer step still assumes the
  enemy stands frozen at its reply, so the answer's honest score usually comes
  in lower than the attempt before and the climb stops there.
- **2026-10-28 (Claude):** Daniel's IF/THEN first-mover picker ("IF I don't
  move, where will the enemy end up ... If the Second mover would move there,
  where should I go ... until the first mover generates a lower score than its
  previous attempt ... or until it picks the same location twice").
  `config.MOVEMENT_SEARCH` / `MECH_*_CONFIG["search"]` = "if_then" - an
  option, the default is unchanged (all reference logs identical).
  `movement_selection._if_then_search`: attempt 1 = the best spot (every
  reachable spot) against the enemy where it stands (Daniel: "Project its
  own move vs the 2nd movers static position first"); each attempt is scored
  by its modeled reply (`MOVEMENT_ASSUMED_ENEMY_SEARCH`, short list by
  default), the next attempt is the best spot against that reply; stops when
  an attempt doesn't score higher (keeps the one before), repeats a spot, or
  has no reply. Daniel declined hedging against several replies and extra
  seeds ("measure the best it can do"). A second mover with "if_then" scores
  every spot (it already knows where the enemy stands). Also
  `tests/pick_quality.py` pickers "IF/THEN" and "IF/THEN perfect" (exhaustive
  reply model), `tests/ab_batches.py --set if-then`, test
  `if_then_climbs_by_its_rule`. Pick quality, same 8 scenarios x 20 battles
  and seeds as 2026-10-27 (the old pickers' numbers reproduce exactly), FIRST
  MOVER (2,716 decisions; % of range / got best / rank pct / hexes off /
  closer / ms):
    Perfect          100.0 / 100% / 100% / 0.00 / +0.00 / 1218 ms
    Short Grid        96.1 /  49% /  95% / 2.47 / -0.11 /  174 ms
    Short-Short       91.0 /  26% /  88% / 3.39 / +0.87 /   93 ms
    IF/THEN           85.1 /  18% /  73% / 3.94 / +1.98 /  102 ms
    IF/THEN perfect   84.6 /  17% /  73% / 3.95 / +2.12 /  128 ms
    Princess modern   75.7 /   9% /  61% / 4.31 / +2.82 /   45 ms
  Moving second IF/THEN = Perfect (every spot). Per scenario (first mover):
  best on Atlas vs Archer (95.6-97.0% of range, beats Short Grid), worst on
  Catapult vs Jenner (88%) and Kontio vs Hammerhead (90%, +1.8 to +2.9 hexes
  closer). Why (24 battles traced, 397 first-mover picks): the climb is
  short - 1 attempt kept in 52%, 2 in 32%, 3+ in 12%; it stopped on a lower
  score 303 times, a repeated spot 90, no reply 4. The best spot against a
  fixed enemy hex is usually close in (the enemy "holds still"), and the
  honest score of the next answer is usually lower, so it mostly keeps the
  static best's answer - a lean in. A perfect reply model doesn't help.
- **2026-10-28 (Claude):** Ultralight and superheavy 'Mechs (Daniel: "Go
  borrow from megamek to get superheavy and ultra light mechs working").
  RULES_REVIEW F70-F71. From MegaMek: the structure table for 10-15 and
  105-200 tons (a superheavy head 4), superheavy slots - an item takes half
  its slots, rounded up, and one slot may hold two ammo bins / heat sinks
  ("A|B": the second is appended after the 12 slots as `partner_of_slot`,
  never itself a critical hit target; `clone_mech` re-points the pairs).
  From the Core appendix (pp.236, 240-241): Large target -1
  (`_target_tmm`, movement scoring), +1 to its own physical attacks
  (`physical_attacker_modifier`), 1 MP less into rough / rubble / woods /
  jungle (`terrain_rules.GroundLimit` carries the flag through the path
  search), 3 levels tall / 2 prone (`los.Height` - partial cover next to a
  hex 2 levels up or in depth 2; none prone), water one level deeper and
  the depth-1 `water.WADING` state, its own Different Levels table
  (`physical._superheavy_options`, kicks two levels down), a slot's two
  ammo bins explode together for one MechWarrior hit, a compact engine
  dies at 2 hits, a superheavy tripod's technical officer (command console
  benefits, +2 to avoid heat shutdown / ammo explosions). Also fixed: a
  quad's cached reach lost its mule kick (`physical._FixedReach.mule_ok`) -
  a crash when a quad was scored next to an enemy. Not built: buildings
  (deferred), foliage (no such terrain), friendly-unit hex rules (no
  allies). Reference logs: only the summary's gap-list text changed;
  benchmark unchanged (HP 501 / 495). New tests/test_superheavy.py (9
  checks).
- **2026-10-28 (Claude):** Industrial tools deferred (Daniel: "Defering
  industrial tools") - Pick up here 10, the summary's gap list. Section 4's
  stale "rules gaps" paragraph refreshed. Reference logs regenerated (gap
  text only).
- **2026-10-28 (Claude):** Interstellar Operations weapons from Daniel's
  pasted rules (TSEMP pp.88-91, iATM, IMP and IIW rounds) and MegaMek's
  values for what the pastes don't give (Daniel: "There should either be a
  weapons table to look up, or megamek's values to use. Borrow from megamek
  for the nail gun too"; "Build what could be used. Custom units are and
  will be a thing"). RULES_REVIEW F66-F69. `INTEGRATION__advanced_weapons`:
  TSEMP effects / interference / shutdown / recharge / Repeating misfeed,
  IMP effects, inferno heat (Core p.192), nail gun; hooks in
  attack_resolution, fire_modes (IMP / IIW kinds, inferno munition,
  pricing), ammo (inferno bins fire; Improved and iATM IMP / IIW bins link;
  a recharging TSEMP is unavailable), electronics (as if jammed), mech_state
  (IMP -MP), equipment_systems / physical / charge / dfa (to-hit),
  weapon_rules (an iATM is a Streak), mtf_parser (`is_industrial` - also
  fixes the Taser's IndustrialMech column, which was never used).
  equipment.json "intops_pass": TSEMP rows (slots 5 / 3 / 7 - each slot
  had been read as its own TSEMP), iATM rows, Improved weapons' slots
  (Improved AC/5, SRM 6, LRM 15 / 20 had been doubled or quadrupled) and
  shots, Improved Gauss explosive (Daniel), nail gun range / heat / shots,
  nail ammo not explosive. Placeholders `TSEMP_EFFECT_WORTH` 5,
  `IMP_EFFECT_WORTH` 2 (Pick up here 3). Reference logs regenerated: only
  the summary's gap-list text and new munition-choice stub lines (the
  HeatGear test 'Mech's SRM inferno bins are now an option - the greedy
  stub keeps firing standard); no battle result moved. Benchmark unchanged
  (HP 501 / 495). New tests/test_intops.py (8 checks).
- **2026-10-28 (Claude):** Daniel's answers to the TO questions. (1) Princess
  prices hazards like MegaMek's checkPathForHazards: every hex her ground
  path stands in (`ranged_combat.PathBook` - the path the project's search
  found, the searches shared per pick), each once, the last as the end
  hex; a jump its landing hex; standing still nothing (modern: the water it
  stands in); a stand-up's GET_UP step in its own hex. Checking MegaMek's
  Terrains.HAZARDS (v0.50.07 and main alike) showed swamp is a hazard
  (calcSwampHazard - now ported) and rubble is not (its calcRubbleHazard is
  never reached) - the clone had priced rubble and missed swamp. Princess
  no longer walks through lava (Caustic Valley battles, both versions).
  Speed: a board with no hazard terrain skips it (`_hazard_board`). (2)
  Every Gauss rifle explodes when hit (Core p.184): Light, Heavy, Improved
  Heavy, Silver Bullet, AP Gauss and the HAGs were marked non-explosive.
  (3) `TASER_EFFECT_WORTH` joins the research pile (Pick up here 3); UMUs
  and the chain whip grapple deferred (Pick up here 10). Reference logs
  unchanged except the summary's gap-list text. Tests: tests/test_hazards.py
  princess_prices_the_whole_path, tests/test_advanced_gear.py
  every_gauss_rifle_explodes.
- **2026-10-28 (Claude):** Tactical Operations weapons, equipment and hex
  types (Daniel: "wire in functionality of missing weapons, equipment, and
  hex types already noted"; rules from the TO:AUE / TO:AR summary layers of
  `logajam/battletech-rules-index`, page-cited in the code). RULES_REVIEW
  F57-F64. New modules `INTEGRATION__hazards`, `INTEGRATION__smoke`,
  `INTEGRATION__advanced_weapons`, `INTEGRATION__advanced_equipment`; new
  tests `tests/test_hazards.py`, `tests/test_advanced_gear.py`; maps
  `data/32x17_Caustic_Valley_Lava.board`,
  `data/16x17_Badlands_2_Hazardous_Liquid.board`. equipment.json
  "to_aue_pass" (shots, damage types, slot counts; Mek Taser and fluid gun
  ammo rows). Path search: the least hazard damage wins first, then hexes
  moved (unchanged when a board has no hazards). Reference logs regenerated: only the summary's gap-list text changed
  (no battle result moved - none of their 'Mechs or boards carry the new items). Found, not fixed
  (Core data, out of scope): Light / Heavy / Improved Heavy Gauss rows are
  not marked explosive, though Core p.184's Gauss rule covers every Gauss
  rifle. Not built, for Daniel: 'Mech UMUs, the chain whip's grapple,
  Princess checking every path hex for hazards (MegaMek does; the clone
  prices the end hex - on lava maps she can walk through lava).
- **2026-10-27 (Claude):** Two questions from the pick-quality battery (Daniel:
  "why was princess hiding? Also it seems gladiator is blood thirsty. I
  wonder if there is a case where it will break off an attack to preserve
  itself"). Scratch study (not in the repo): the 8 pick-quality scenarios x
  20 battles, Gladiator driving both sides; at every second-mover decision
  modern Princess's ranker was asked too, with each spot's score parts.
  PRINCESS HIDES on 487 of 2,739 second-mover decisions (18%; 10% Large
  Lakes - 28% Scattered Woods) - by her own rules, not a bug: an enemy that
  has moved can't shoot a spot it can't see, so hiding scores 0 on the trade,
  and her trade is 1.5 x my damage - its damage (both as firing-plan
  utility, its punches / kicks at their threat weights). Her best spot WITH
  line of sight averaged 3.6 dealt vs 8.6 taken; in 60% of the hidden picks
  that spot traded below zero (1.5 x 3.6 < 8.6). The term that tipped it:
  the trade 53%, aggression 28% (the hidden spot is NEARER - 7.1 vs 7.8
  hexes: round a corner, behind woods), facing 10% (the line-of-sight spot
  faced badly), the close-range pull 8%. Gladiator can't do it when moving
  second: it only takes a spot with line of sight while one deals damage.
  GLADIATOR BREAKS OFF, but not to save itself: moving first it chose a
  spot with no exchange (its modeled reply can't shoot and nor can it) on
  27% of 2,729 decisions and opened the range on 51%; moving second it chose
  a line-of-sight spot that deals nothing on 14.5% and opened the range on
  16%. The rates DON'T rise as it gets hurt (moving first: 27.6% above 80%
  HP, 27.2% at 50-80%, 25.9% below 50%) - the lifetime objective compares
  dealt with received x (my future damage / its future damage), and HP left
  scales both options alike, so being damaged doesn't make it more careful.
  It disengages when the exchange is bad, not when it is in danger. A
  self-preservation pull when crippled would be new bot logic - it goes
  with forced withdrawal (Pick up here 5, and Princess's own withdrawal,
  item 00) - Daniel's call.
- **2026-10-27 (Claude):** Do the short list's rules of thumb hold up? (Daniel:
  "Set up a battery of tests using a diversified set of combatants across a
  range of maps. At least one set should be a faster unit with longer range
  that wants to kite ... For each turn's board state take a measurement of"
  Perfect, Short-Grid, Short-Short-Grid, Princess classic / modern "... what
  average percentage of score is earned compared to perfect knowledge ...
  And How many hexes away on average the pick is"). New
  `tests/pick_quality.py` and `movement_selection.SCORE_SINK` (studies only,
  off by default: Perfect's run prices every reachable spot and charge / DFA
  with the objective). 8 scenarios x 20 battles, Gladiator (Short Grid)
  driving both sides, 30-turn cap, scenarios one after another, battles in
  parallel: Dervish vs Hunchback (Grassland, kite), Griffin vs Hunchback
  (Scattered Woods, kite), Catapult vs Jenner (Rolling Hills, LRM vs fast
  brawler), Kontio vs Hammerhead (Grassland), Atlas vs Archer (Hilltops),
  Awesome vs Griffin (Military Base, Griffin kites), Locust vs Commando
  (Desert Hills), Black Hawk vs Cataphract (Large Lakes). Added to data/: 4
  boards (Rolling Hills 1, Scattered Woods, Hilltops 1, Desert Hills) and 8
  'Mechs (Dervish DV-6M, Hunchback HBK-4G, Griffin GRF-1N, Catapult CPLT-C1,
  Jenner JR7-D, Awesome AWS-8Q, Locust LCT-1V, Commando COM-2D).
  Scale: best / worst / rank over the spots Perfect chooses among (moving
  second: only spots with line of sight; a no-LOS pick is priced at most at
  the best); decisions where nothing deals damage (Perfect's closing
  fallback) left out. "% of best" reads 95-100% for everyone (the lifetime
  objective is mostly HP left); "% of range" = (pick - worst) / (best -
  worst) is the sharper one. 5,116 decisions; % of best / % of range / got
  the best spot / hexes from Perfect's pick / closer to the enemy than
  Perfect / ms a decision:
    Perfect          100.0 / 100.0 / 100% / 0.00 / +0.00 / 680 ms
    Short Grid        99.6 /  94.2 /  57% / 2.23 / -0.13 / 116 ms
    Short-Short       98.8 /  86.7 /  30% / 3.01 / +0.44 /  70 ms
    Princess 0.50.07  95.9 /  77.5 /  22% / 3.71 / +2.61 /  40 ms
    Princess modern   96.6 /  79.7 /  20% / 3.50 / +2.12 /  52 ms
  First mover: Short Grid 96.1% of range, Short-Short 91.0, Princess 70-76
  (+2.8 to +3.4 hexes closer). Second mover: Short Grid 91.9, Short-Short
  81.8, Princess 84-86 (+1.3 to +1.7 closer; 15-17% of its picks hide out of
  line of sight). Kiters only (1,634 decisions): Short Grid 94.4% of range,
  +0.05 hexes closer - no closing bias; Short-Short 88.2, +0.56; Princess
  75-78, +2.5 to +2.8 - Princess closes when it doesn't have to. Per scenario
  Short Grid stays 92.5-96.1% of range everywhere (worst Military Base),
  Short-Short 82.9-91.8 (worst Military Base, best Hilltops). Verdict: the
  rules of thumb hold up - the short-list look-ahead (in Short Grid, the
  default) loses ~6% of the score range and has no closing bias; picking
  your own spot from the short list too (Short-Short) costs another ~7%
  and adds a slight lean in (strongest moving first, +0.9 hexes) for ~40%
  less time.
- **2026-10-27 (Claude):** The MODERN Princess (Daniel: "Clone the entire
  modern suit for Princess. Do a sanity check vs the results of one of the
  previous runs thats already recorded, see if she improves"). MegaMek main
  at fd2edfb (2026-10-26): new `INTEGRATION__princess_modern.py` (posture,
  close-range incentive, squaring up, position hold with the water sustain
  boost, attacker-movement and cover discounts, physical threat weights, the
  modern water hazard) and modern FireControl in `INTEGRATION__princess_fire`
  (movement heat and the TSM ceiling in the tolerance, the TSM heat
  incentive, crits / kills by damage on a hit). `config.PRINCESS_VERSION`
  ("modern" DEFAULT, "0.50.07"); orchestrator sets `mover.turn_number`;
  `ab_batches.py --set bots-classic`; `tests/test_bots.py` checks the modern
  fire control, the posture and both versions' battles. The classic version
  reproduces its recorded 20-battle Kontio-Hammerhead run exactly (5-15-0 /
  17-2-1 / 7-13-0); Gladiator unchanged (all reference logs identical).
  Sanity check against the recorded 100-battle runs (same seeds; wins of the
  side Princess plays, classic -> modern, with both-Gladiator for scale):
  Kontio-Hammerhead - Princess Red 14 -> 40 (Gladiator 63), off-board deaths
  48 -> 25; Princess Blue 14 -> 11 (Gladiator 31); both Princess Red 44 -> 68.
  Atlas-Archer - Princess Red 73 -> 81 (Gladiator 92); Princess Blue 0 -> 2
  (Gladiator 7); both Princess 94-6 -> 97-2. Battles last longer (Kontio
  6-7 -> 7-8 turns, Atlas 9-11 -> 10-14). Modern Princess is better, most
  of all as the faster brawler (the close-range pull, squaring up); it still
  trails Gladiator in every seat, and is still pushed off the board often.
- **2026-10-27 (Claude):** Short-Short, best few states + grid prune (Daniel:
  "Keep only the best few states. Also wonder if short list hexes tend to be
  continuous. If so then a grid search prune on them would reduce the total
  that need to be checked"). `movement_selection.own_short_list`: per
  short-list hex and movement mode, one state - most hexes moved (least MP
  on a tie), then the facing nearest the enemy - always a reachable state.
  New `config.MOVEMENT_SHORT_LIST_GRID` (default False): the grid search
  ("guess and follow") over those hexes instead of all of them.
  Contiguity (Short-Short, 10 battles each, Kontio-Hammerhead, Atlas-Archer,
  Cataphract-Emperor; 740 decisions): reachable 412 states / 60 hexes ->
  short list 25 hexes, 48 states kept; 1.9 connected groups a decision, the
  largest holding 85% of the hexes, 0.3 lone hexes - mostly continuous.
  A/B, 20 battles, wins Red-Blue-draw, ms a turn (Short Grid -> Short-Short
  -> + grid prune): Kontio-Hammerhead 13-5-2 / 14-6-0 / 12-8-0, 127 / 125 /
  104 ms; Atlas-Archer 19-1-0 / 20-0-0 / 20-0-0, 36 / 29 / 28 ms;
  Cataphract-Emperor 2-17-1 / 1-19-0 / 1-19-0, 98 / 105 / 73 ms. Results
  within noise; Short-Short battles end sooner (9-10 turns vs 16-18 on two
  matchups). Default unchanged; all checks pass.
- **2026-10-27 (Claude):** "Short-Short" for Gladiator, BEGUN (Daniel: "second
  mover only tests its short list vs the opponent's short list to pick a
  movement option"; Daniel near his usage limit). `MOVEMENT_SEARCH` /
  `"search"` = "short_list": the second mover scores only the reachable
  states in its own hex and at the short-list distances from the enemy
  (`short_list_distances`); CORRECTED the same day (Daniel: "I want the
  First mover to only evaluate against its own short list vs the 2nd movers
  short list. Basically both sides are only picking from their own short
  lists"): the first mover too scores only its own hex and the hexes at the
  short-list distances from the enemy's current hex, each against the second
  mover's short list (the look-ahead). Kontio-Hammerhead, 20 battles: Short
  Grid 13-5-2 (17.6 turns), Short-Short 14-6-0 (10.4 turns, same winner
  15/20); 53 s vs 47 s - every state in the short-list hexes gets the full
  look-ahead, where the grid search checks only part of the board. With the
  default look-ahead ("short_list") that is Short-Short. `ab_batches.py
  --set short-short`. First check, Kontio-Hammerhead, 20 battles: Short Grid
  13-5-2, Short-Short 13-7-0 (34 s vs 40 s, same winner 10/20). Default
  unchanged. Open: wider A/B, a speed and agreement row (bot_agreement),
  Daniel's confirmation that this is the reading he meant.
- **2026-10-27 (Claude):** Princess vs Gladiator SPEED (Daniel: "how fast is
  princess compared to gladiator? Either in terms of operations to reach a
  decision, or just measure how long its turns take"). `tests/bot_agreement.py`
  now times each picker on the same positions and counts its operations -
  the (my spot, enemy spot) pairs it scores. 8 matchups x 20 battles, 2,272
  movement decisions, 4 workers, mean / median ms a decision, mean pairs:
  Princess 36 / 25 ms, 385 pairs; Short Grid 115 / 80 ms, 2,039 pairs (3.2x
  Princess); Perfect 556 / 102 ms (max 7.8 s), 89,153 pairs (15.6x). Moving
  first: Princess 23 ms, Short Grid 177 ms (7.8x), Perfect 1,046 ms (46x) -
  the look-ahead is Gladiator's cost (Princess has none). Moving second, all
  three are about the same (49 / 54 / 62 ms; Short Grid scores fewer pairs,
  110 vs 388). Whole turns, 10 battles, both sides the same bot, 1 worker
  (s a turn, Gladiator -> Princess): Kontio-Hammerhead 0.388 -> 0.275,
  Atlas-Archer 0.118 -> 0.041, Cataphract-Emperor 0.186 -> 0.081. Movement
  is 90-98% of a turn for both; the weapon choice is ~1.5-3.3 ms and the
  physical choice ~0.3-0.5 ms a call for either bot. (Princess's Kontio
  turns stay slow: a fast 'Mech has ~1,500 spots, all ranked with its fire
  control's heat plans.)
- **2026-10-27 (Claude):** Princess vs Gladiator, longer and wider (Daniel:
  "Longer and wider comparison runs. Also get a sense for how often princes's
  top pick matches the 'Perfect Knowledge' and the current default setting
  (Needs a nick name.) if it were gladiator"). Nickname used for now: the
  default Gladiator = **"Short Grid"** (grid search + short-list look-ahead,
  after Daniel's "Simple Short Grid") - made the official name 2026-10-28;
  "Perfect" = exhaustive own search and look-ahead.
  A/B, `ab_batches.py 100 ... --set bots --turns 50`, 100 battles a setting,
  wins of the side Princess takes over (baseline both Gladiator -> that side
  Princess): Kontio-Hammerhead Red 63->14, Blue 31->14; Atlas-Archer Red
  92->73, Blue 7->0; Kintaro-Atlas Red 11->4, Blue 87->58; Cataphract-Emperor
  Red 6->5, Blue 92->83; Akuma-Highlander IIC Red 11->15, Blue 88->64;
  Bombardier 14K-Black Hawk F Red 21->19, Blue 76->27; Black Hawk-Cataphract
  Military Base Red 81->48, Blue 17->15; same on Large Lakes Red 75->53, Blue
  25->10. Overall Princess won 502 of 1,600 battles in the seat where
  Gladiator won 783 - Gladiator is worse in only one case (Akuma Red, +4,
  noise). Pushed off the board: up to 48 of 100 with Princess on a side (it
  ignores edges). Princess battles last 6-10 turns against Gladiator's 12-19.
  Agreement, new `tests/bot_agreement.py` (20 battles per matchup, the 8
  above, Princess vs Gladiator alternating sides; at every movement decision
  Princess, Short Grid and Perfect each pick from the same position, only the
  'Mech's own bot's pick is played - checked: the battle is unchanged):
  2,272 decisions - same spot (hex, facing, mode) / same hex / avg hexes
  apart: Princess vs Perfect 14% / 23% / 2.7; Princess vs Short Grid 13% /
  22% / 2.7; Short Grid vs Perfect 53% / 55% / 1.6. Moving first (enemy still
  to move): Princess vs Perfect 4% / 9% / 3.6, Short Grid vs Perfect 39%;
  moving second: 24% / 37% / 1.8, Short Grid vs Perfect 68%. Least agreement
  on the terrain boards (7-9% same spot), most Akuma-Highlander (~20%).
- **2026-10-27 (Claude):** The Princess clone (Daniel: "I would like to
  make a clone of Megamek's Princess bot to compare it against"; "work until
  the task is complete"). New `INTEGRATION__princess.py` (BasicPathRanker:
  the path utility, both enemy estimates, ConvexBoardArea / HexLine ported
  with Java integer maths, fall tolerance and range filters, end-hex hazards)
  and `INTEGRATION__princess_fire.py` (FireControl's plan utility and heat
  plans; PhysicalCalculator's attack choice). Hooks: `weapon_selection.
  fire_control` (a context: inside it, `select_weapons_to_fire` hands its
  candidates - now with each one's to-hit number - to another bot's chooser;
  `side` passed through from `MoveEvaluator`'s scorers), `bots.fire_control`
  around `declare_attacks`' arc loop (Princess plans no physical with its
  fire), `bots.choose_physical` in `run_physical_phase`. `config.
  PRINCESS_BEHAVIOR`; `ab_batches.py --set bots`; `tests/test_bots.py` now
  checks the geometry port, the plan utility, that the fire-control hook
  stays scoped, and a repeatable Princess battle. Gladiator unchanged: every
  reference log identical, all checks pass.
  A/B, 20 battles a setting, same seeds, 50-turn cap (wins Red-Blue-draw):
  Kontio vs Hammerhead - Gladiator both 13-5-2; Princess Red 5-15-0 (8
  off-board deaths); Princess Blue 17-2-1; Princess both 7-13-0. Atlas AS7-K
  vs Archer ARC-2R - Gladiator both 19-1-0; Princess Red 12-7-1 (7 off-board:
  the Atlas stands on its edge row and the Archer pushes it off); Princess
  Blue 20-0-0; Princess both 18-2-0. Princess battles are shorter (6-9 turns
  against 14-18) and its turns are a little faster (no look-ahead).
  Replays now record each side's bot (`"bot"` in the mech header) and show it
  in the title ("Kontio (Princess) vs Hammerhead (Gladiator)").
- **2026-10-27 (Claude):** Bots per unit, stage 1 (Daniel: "The ability to
  select what type of bot each unit uses. The current system ... shall be
  called 'Gladiator'"). New `INTEGRATION__bots.py`: `config.BOT` (default
  "gladiator") and an optional `"bot"` key in each `MECH_*_CONFIG`; the
  orchestrator attaches `mech.bot` and asks `bots.choose_movement` for the
  Movement Phase pick. "princess" is registered but refused at load time
  until built (Section 6, "Princess clone", has the port plan from MegaMek
  v0.50.07). New `tests/test_bots.py`. Results unchanged: every reference
  log identical, 33 of 33 checks pass.

- **2026-10-24 (Claude):** Daniel's "simple short list" two-ply look-ahead,
  the DEFAULT (`MOVEMENT_ASSUMED_ENEMY_SEARCH = "short_list"`; Daniel: "we
  push 'Simple Short list' for the first movers evaluation"; both movers keep
  the grid search for their own spots). Research first (Daniel's theory: "the
  move second side ... will consistently tend to pick a spot from a more
  limited selection of locations"): 30 full-fidelity battles (both sides
  exhaustive; 5 matchups, 3 boards, ~156k modeled replies). In one decision
  the reply lands on 5-63 distinct hexes for 125-800 first-mover spots; 89%
  hit the first mover's side or rear, 31% stand next to it (Kontio 86%,
  mostly behind); stand-off replies sit at range-bracket ends (Atlas 44% at
  7, Cataphract at 6, Black Hawk one past the Cataphract's brackets). The
  rule of thumb (`movement_selection.short_list_distances`): next to the
  first mover, the replier's own hex, the replier's `MOVEMENT_SHORT_LIST_DROPS`
  = 2 biggest damage drops and one past the first mover's (rough damage by
  range at pre-TN 6); ~80% of exact replies. Each listed hex is scored once
  per movement mode at its best TMM, facing the first mover (Daniel:
  "Location, best tmm of any move to that hex per movement type. Expected
  incoming damage as if its facing you"; the facing isn't checked as
  reachable, and the first mover's return fire counts as front hits - "The
  first mover can never control its targets facing anyways unless its
  immobile"; an immobile or prone replier keeps the full model). Same-state
  A/B over 191 decisions: same pick 46%, score lost 0.20% on average (worst
  3.5%) vs 0.45% (worst 6.6%) for the grid reply - picks change but among
  near-ties. Per turn (ab_batches `--set short-list`, 8 battles, 15 turns):
  ~1.5x faster than the grid reply (Kontio 244 -> 168 ms, Atlas 54 -> 43,
  Black Hawk 111 -> 69). Short-grid vs perfect knowledge, one per side
  (`--set short-vs-perfect`, 12 battles, 25 turns): Atlas / Archer and Black
  Hawk / Cataphract within noise; Kontio / Hammerhead both perfect 5-5,
  Hammerhead short-grid vs Kontio perfect 2-8, both short-grid 9-2 - an
  isolation run (20 battles, both grid for own spots) gave grid reply 12-5,
  short-list 13-3, so the lean is the grid search's (already the default),
  not the short list's. Benchmark ~3.5 s -> 2.1 s (HP 501 / 495). New:
  `ranged_combat.turned_option`; tests short_list_reply_follows_its_rule,
  damage_drops_sit_on_bracket_ends; test_replay reads the outcome from the
  result instead of pinning it. Reference logs updated (all 15 - intended).
- **2026-10-21 (Claude):** Daniel's answers: Thumper 20 shots a ton / 5
  heat, Sniper 10 / 10 (equipment.json; no more unlimited-ammo stub); homing
  rounds' 5 AE hits every other unit in the hex; TAG can designate the
  ground (`STUB_TAG_AIM`, Section 6; homing then 5 AE to the 'Mech there).
  The Uni ATAE-70 is an illegal design; the split-item join in a shared
  location is a Section 4 cleanup-sweep item (code left as is).
  test_weapons updated. Reference logs unchanged.
- **2026-10-21 (Claude):** TAG and homing artillery (RULES_REVIEW F56, pp.53,
  190, 200), new `INTEGRATION__tag`: a designation step before the Ranged
  Attack Phase (`STUB_FIRE_TAG`, Section 6); Arrow IV / Thumper / Sniper
  homing rounds parsed and fired at a designated target (2D6 4+: 20 / 10 / 5
  direct-fire, else 5 AE). Smoke and active probes left as G34 (no smoke
  source yet). test_weapons tag_and_homing_artillery. Reference logs
  updated: the Asymptote mounts TAG, so the new stub's lines and the
  known-missing wording - battle results unchanged.
- **2026-10-21 (Claude):** Thumper / Sniper artillery as Arrow IV (Daniel's
  wiring; RULES_REVIEW F55): their own damage (15/5, 20/10), slots fixed
  (15, 20), the parser joins a three-location split; homing damage recorded
  for TAG. Open for Daniel: shots per ton (unlimited, loud stub) and heat.
  test_weapons thumper_and_sniper_artillery. Reference logs updated: the
  known-missing note's wording only.
- **2026-10-21 (Claude):** Torpedo launchers (RULES_REVIEW F54, pp.127,
  187): all torpedo names parse (as their LRM / SRM launcher), fire only
  underwater along an all-water line, and use only torpedo rounds. Before,
  "LRT 5"-style names fired on land as LRMs and "CLLRT15" didn't parse (26
  units). test_water torpedoes. Reference logs unchanged; the benchmark too.
- **2026-10-21 (Claude):** PPC capacitors (RULES_REVIEW F53, p.188), new
  `INTEGRATION__capacitor`: links, charging / holding heat, +5 damage and heat
  when fired charged, the explosion on a crit. Both choices are stubs, off by
  default (`STUB_CAPACITOR_START` / `STUB_CAPACITOR_CHARGE`, Section 6).
  `weapon_selection`'s table cache key now includes the charges.
  test_weapons ppc_capacitor. Reference logs updated: only the known-missing
  note's wording (capacitor charging is now a stub, off by default).
- **2026-10-21 (Claude):** Blue Shield particle field damper (RULES_REVIEW
  F52, pp.180, 207); on / off is a stub (`STUB_BLUE_SHIELD`, Section 6).
  test_equipment blue_shield. Reference logs unchanged.
- **2026-10-21 (Claude):** APDS (RULES_REVIEW F51, p.206) - Core after all;
  engages like an AMS and stacks with one. test_ams apds. Reference logs
  unchanged.
- **2026-10-21 (Claude):** Cockpit command console (RULES_REVIEW F50, p.203);
  the End Phase seat swap is a stub (`STUB_CONSOLE_SWAP`, Section 6).
  test_rules command_console. Reference logs unchanged.
- **2026-10-21 (Claude):** HarJel I / II / III (RULES_REVIEW F49, p.208).
  test_water harjel. Reference logs unchanged.
- **2026-10-21 (Claude):** Quad kicks - front kick and mule kick (RULES_REVIEW
  F48, p.238). test_special_attacks quad_kicks. Reference logs unchanged.
- **2026-10-21 (Claude):** Shields and vibroblades (RULES_REVIEW F47); raising a
  shield and activating a vibroblade are stubs (`STUB_RAISE_SHIELD` never,
  `STUB_VIBROBLADE` on - Section 6). test_special_attacks shields,
  vibroblades. Reference logs and benchmark unchanged.
- **2026-10-21 (Claude):** Talons on DFA, spikes, lance armor-piercing checks
  (RULES_REVIEW F46, new `INTEGRATION__physical_gear`), the charge-spikes
  declaration as a stub (`STUB_CHARGE_SPIKES`, Section 6). Bug fixed: a
  multi-slot physical weapon was one item per slot (one crit didn't wreck
  it). test_special_attacks talons_spikes_and_lances. Reference logs
  unchanged.
- **2026-10-21 (Claude):** Heat-dissipating armor (RULES_REVIEW F45, p.202):
  flamer / plasma damage to it halved, no outside heat. test_weapons
  heat_dissipating_armor. Reference logs unchanged.
- **2026-10-21 (Claude):** Heavy-duty gyro (RULES_REVIEW F44, p.204): 4 hits to
  destroy, +1 a hit, no PSR from its hits or from running, +2 to jump with
  hits; the .mtf gyro type is now read. Chemical laser ammo checked - already
  right (G31). test_rules heavy_duty_gyro. Reference logs unchanged.
- **2026-10-21 (Claude):** To-do list refilled (Daniel: "Are there any weapons
  or equipment that don't have rules implemented yet"): a survey of every
  unit in `data/meks.zip` against the Core Rulebook's Weapons & Equipment
  chapter - RULES_REVIEW G23-G33 (Pick up here 7a), plus the list of items
  with no effect in a duel and non-Core items.
- **2026-10-21 (Claude):** Clubs (Daniel): holding one never blocks fire
  (the code already let it fire), firing an arm weapon rules out the club
  attack that turn (already so, p.79); `CLUB_PICKUP` now on - a mech that
  fires nothing picks up a club in its hex. PPC capacitors noted for their
  own session (Pick up here 8). Reference logs regenerated where clubs got
  picked up.
- **2026-10-21 (Claude):** "Follow the rules, not my calls" (Daniel). Quads'
  leg damage by the book (RULES_REVIEW F43, pp.238-239): lost legs -1
  Walking MP / +1 PSR each for the first two, three = a biped with one leg
  lost (still mobile), four = immobile (was: destroyed at three, Walking MP
  1 at two); the first hip hit has no MP / PSR / running-PSR / level-limit
  effect, later ones do; two lost legs bring a hip hit's effects.
  `mech_state.hip_effects` / `ground_level_limited` (the level limit now
  goes through it everywhere). `POOL_CLUSTER_DAMAGE` default False. Sweep
  of other "Daniel's rule" spots: the 2-per-slot component explosion is the
  book's (p.96) - comment fixed; `FIGHT_TO_THE_DEATH` briefly flipped on,
  then back off at Daniel's word (speed). Reference logs regenerated: 12
  changed by the pooling default; one winner flipped (Bombardier 14K vs
  Black Hawk: Blue -> Red). test_rules quad_leg_damage_by_the_book.
- **2026-10-21 (Claude):** PSR special cases cleared from the rules
  (RULES_REVIEW F42): stand-up -1, leg destroyed +4 (was +5), tripod -1 with
  no leg lost (was -2) plus the dedicated pilot -1 / +2 disabled (PSRs and
  physical attacks) and the gunnery officer's +2 to ranged attacks when
  disabled, quad -2 only with all legs, +1 per lost leg (first two), no PSR
  to stand, one lost leg forces no run / jump PSR. test_rules
  psr_modifiers_by_the_book. Reference logs regenerated (13 changed in the
  detail, 3 in the result, same winners). Found on the way: Daniel's quad
  leg-loss MP / destruction house rule differs from p.238 - left, asked
  (Section 4).
- **2026-10-21 (Claude):** Line of sight rebuilt to the Core Rulebook (Daniel:
  "make sure the LOS rules match those in the rules and fix prone mechs";
  RULES_REVIEW F41, D8 decided, G7 built). `pathfinder/los.py`: LOS levels
  with heights (standing 2, prone 1), the p.57 intervening test, hills /
  buildings block, woods and jungle points (3 block), partial cover with the
  height and prone conditions, border lines on one side for the whole line
  (the target's pick). Heights passed from `declare_attacks` / `attack_side`
  and the movement-scoring cache (`los_cache.board(map, a_height,
  t_height)`). New `tests/test_los.py` (the rulebook's examples).
  Reference logs regenerated: 8 changed; Large Lakes 1 now draws at the cap
  - the Cataphract sits fully under water where nobody can fire (p.62), a
  bot stall (Pick up here 0), not an LOS fault; the others keep their
  winners. Benchmark 495 / 495, ~4 s.
- **2026-10-21 (Claude):** BUG FIXED (RULES_REVIEW F40, p.94): Inner Sphere
  endo-steel / ferro-fibrous / stealth / reactive / reflective / ballistic-
  reinforced slots are written as plain names that don't match
  equipment.json, and any plain name counted as a crit target - on ~1,090
  units those 7-28 filler slots soaked critical hits meant for real
  components. Now inapplicable (`equipment.is_structure_or_armor_slot`).
  Found by a parse survey of all 4,227 units for unrecognized components
  (the rest are non-Core gear: cargo, backhoes, torpedoes...). 3 reference
  battles changed, same winners. test_rules
  structure_and_armor_slots_take_no_crits.
- **2026-10-21 (Claude):** Cockpits (RULES_REVIEW F39, p.203): small and
  torso-mounted cockpits +1 to every PSR (205 + 34 units in meks.zip);
  torso-mounted - no pilot hit from head hits, the head's loss isn't fatal
  (later head hits re-rolled), sensor hits +4 to physical attacks and PSRs
  (both head sensors, or 3+). The tripod leg sub-roll now draws from the
  battle's dice (was Python's random - a seed didn't replay it): the 5
  Asymptote reference battles changed, same winners. test_rules
  cockpit_types.
- **2026-10-21 (Claude):** Movement options (RULES_REVIEW G5, G8 -> F38):
  jumping into the mech's own hex for 1 MP (p.50 - any facing, +1 TMM, 3
  heat) and Minimum Movement (p.49 - run one hex straight ahead without the
  MP it costs, as the whole move). Reference logs regenerated: 10 changed
  (jump-capable mechs), same winners; the Asymptote mirror still hits the
  cap but trades more (6 / 6 damage -> 15 / 27). Benchmark 495 / 495. Not
  built: G12 (a charge after a backward step - the charge planner's paths
  are forward-only; a bot option). G7 (prone LOS height) waits for Daniel
  with D8 - `pathfinder/los.py` is his ruleset ("don't change without
  asking").
- **2026-10-21 (Claude):** Armored components (RULES_REVIEW G14 -> F37),
  and a parser bug found on the way: MegaMek's "(armored)" tag wasn't
  stripped, so on the 37 units carrying it an armored engine / gyro /
  cockpit / actuator was inert padding (crits did nothing) and an armored
  weapon never fired. Now parsed (`mech.armored_slots`); each armored slot
  absorbs one attack crit (p.207), not MASC / supercharger ones; an armored
  hip / shoulder stops a limb blown off once. test_rules armored_components.
  Reference logs unchanged (no armored unit in them).
- **2026-10-21 (Claude):** Water leftovers (RULES_REVIEW G6 -> F36): hits on
  a 'Mech standing in depth 1 from a leg weapon in depth 1, or any weapon of
  a fully submerged 'Mech, use the Kick Location Table (legs only, no
  partial cover, pp.67, 127); an energy weapon firing from under water uses
  the next bracket for its damage too (p.127, Snub-Nose PPC / VSP). New
  checks in test_water (18). Reference logs regenerated for the known-
  missing-rules text only (no battle changed).
- **2026-10-21 (Claude):** Rules gaps, physics first (Daniel: "I'm basically
  after getting the environment and physics of the game correct before
  worrying too much about the bots behavior"). (1) G20 "damage PSRs fall in
  the END hex" is the RULE (p.113: movement-mode PSRs are made at the end of
  movement) - TODO removed. But a charger's / DFA's movement only ends in the
  Physical phase (pp.78, 80): its end-of-movement PSRs now wait until then,
  joined by a PSR for the hex a successful charger advances into (rubble,
  sand, water when running) or a DFA lands in (water, rubble)
  (`movement_attacks.end_of_movement_triggers`); a DFA mech no longer rolls a
  landing PSR for the hex it hangs over (RULES_REVIEW F34). (2) G4: a mech
  can't pass through a mobile enemy's hex on the ground (p.48, F35;
  `pathfinder.build_movement_table(blocked=...)`). Reference logs
  regenerated: all 15 (the known-missing-rules text), 4 with different
  moves - Atlas S2 vs Kintaro, Kintaro vs Atlas, Bombardier 05A vs
  Cataphract, Black Hawk vs Cataphract (Military Base) - same winners.
  Benchmark unchanged (495 / 495). New checks: test_special_attacks
  charge_end_of_movement_psrs, test_pathfinder 9b.
- **2026-10-21 (Claude):** Daniel's two known issues fixed (Daniel: "Start
  with known issues"). (1) Scatter vs the firing arc (pp.182-183): a missed
  Arrow IV / artillery cannon now walks its scatter path hex by hex and
  stops at the last hex its launcher's firing arc still covers
  (`attack_resolution._in_firing_arc`: facing + declared twist / flip /
  turret); held all the way back it lands on the target's hex for the full
  area-effect damage. Artillery cannons without splash now roll the
  direction too (needed to know whether the arc holds the shell on the
  target). (2) Machine gun array ammo: guns sharing a bin each counted the
  whole bin, so 1 round left fired all 3 guns; the rounds are now counted
  once (`fire_modes.mga_firing_guns`, `take_array_rounds`). New checks in
  `tests/test_weapons.py` (14 now). `run_checks.py`: 31 of 31, every
  reference log unchanged (neither case arose in them).
- **2026-10-21 (Claude):** Session 6 wrap-up (Daniel: "Good session. Wrap it
  up. make sure everything is updated and ready to go for the next
  session."). Section 0 rewritten for session 6 (summary, the speed item's
  status and open follow-ups); Section 6's movement row names the new
  search settings; README's A/B line updated. Clean baseline at hand-off:
  `run_checks.py --bench` 31 of 31 in 60 s, benchmark 495 / 495 in 3.5 s.
- **2026-10-21 (Claude):** Knowledge A/B (Daniel: "If Red moves perfectly,
  and thinks Blue will move perfectly But blue moves using the fast method
  ... See how much of an advantage perfect knowledge is vs close enough").
  `tests/ab_batches.py --set knowledge`, 20 battles a setting, same seeds,
  50-turn cap. "Perfect" = exhaustive search; "expects" = the search it
  assumes for the enemy's reply. Wins of the side named (all fast = 0):
  Kontio (R) 11 vs Hammerhead (B) 8: R perfect +1 / +3 (expecting perfect /
  fast), B perfect 0 / -2; a fast side expecting perfect: R -2, B -2.
  Kintaro (R) 6 vs Atlas (B) 13: R perfect 0 / +1, B perfect +5 / +6;
  expecting perfect: R -1, B +1. Bombardier (R) 6 vs Black Hawk (B) 13: R
  perfect -2 / 0, B perfect +6 / +4; expecting perfect: R -5, B +3.
  Cataphract (R) 1 vs Emperor (B) 19: R perfect +2 / -1, B perfect 0 / -1
  (at the ceiling); expecting perfect: R -1, B +1. Dice noise at 20 battles
  is about +-2 wins. Reading: searching perfectly helped the side already
  winning (Atlas, Black Hawk ~ +5, Kontio +1 to +3) and not the underdog;
  what a side assumes about the enemy's search made no consistent
  difference. A perfect side runs 0.3-0.6x the default's speed. Output:
  `run_stats/ab_knowledge_2026-10-21.txt`.
- **2026-10-21 (Claude):** The grid search is the DEFAULT (Daniel: "I think it
  should become the default"), and each side can have its own search
  (Daniel: "See how much of an advantage perfect knowledge is vs close
  enough"). `config.MOVEMENT_SEARCH` (how a mech picks its own spot - the
  first mover's two-ply candidates, the second mover's real pick) and
  `MOVEMENT_ASSUMED_ENEMY_SEARCH` (how a first mover assumes the reply
  picks) replace MOVEMENT_TWO_PLY_SEARCH / MOVEMENT_REPLY_SEARCH; both
  "grid". Per side: `MECH_RED_CONFIG` / `MECH_BLUE_CONFIG` "search",
  "assumes_enemy_search" (`orchestrator._attach_mech_config`,
  `movement_selection.own_search` / `assumed_enemy_search`). The movement
  note says "N of M spots (grid search) x K replies (grid search)". All 15
  reference logs regenerated (intended); the Asymptote mirror still hits
  the 50-turn cap. Benchmark 501 / 495 (14.5 s) -> 495 / 495 (~3.5 s); both
  "exhaustive" settings, globally or per side, still give 501 / 495.
  `run_checks.py` 186 s -> ~60 s. Two movement checks that prove the
  perfect search finds the best spot now pin "exhaustive"; new check
  per_side_search_settings. `tests/ab_batches.py`: settings "DICT.key" set
  one key of a config dict; sets "search" (all fast vs all perfect) and
  "knowledge" (one side perfect, expecting perfect or fast...).
  **Bug fix found by the new battles:** an aimed shot (p.70) applied
  `weapon.damage_per_shot` instead of the shot's damage
  (`fire_modes.damage_per`), so an aimed Heavy Gauss Rifle shot (variable
  damage, no listed figure) crashed the Atlas AS7-S2 vs Kintaro battle;
  `_resolve_aimed_hit` now takes the damage (`tests/test_equipment.py`).
- **2026-10-21 (Claude):** Grid spin A/B (Daniel: "clockwise vs counter
  clockwise grid spin ... no more then a single set of 20 sims").
  `config.MOVEMENT_GRID_SPIN`: the two mirror-image 1-in-7 nets, cube
  (q + 3r) or (q + 5r) mod 7 - range-3 net hexes "2 out, then 1 turning
  clockwise / counter-clockwise"; default "clockwise" (the net so far).
  Kontio vs Hammerhead, 20 battles, both movers on the grid
  (`--set grid-spin`): clockwise 11 / 8 / 1 draw, 14.7 turns, dealt 42.0 /
  44.0; counter-clockwise 12 / 7 / 1, 18.2 turns, 47.4 / 48.0 - no
  difference beyond dice noise; kept clockwise. Defaults unchanged.
- **2026-10-21 (Claude):** Always-checks for the grid search (Daniel: "add a
  short list of always checks. Your starting position for standing still,
  the targets position for charging. And the 6 hexes around it for melee";
  then "Always checks wouldn't help the first mover"). `_grid_search` always
  looks at the mover's own hex and, for the SECOND mover only (the modeled
  reply and its real pick), the 6 hexes around the enemy; the first mover's
  enemy moves after it. Charging into the target's hex needed nothing new:
  charges / DFAs are scored apart, over every charge state, in any search
  mode. Defaults unchanged (reference logs, benchmark 501 / 495). A/B, 20
  battles x 6 matchups (`--set search-always`): first mover only - the same
  numbers as before (own hex was already a net hex); both movers - all six
  within noise of the exhaustive baseline. Kontio vs Hammerhead, 100 battles
  (the case that looked off): Kontio 61 / Hammerhead 34 / 5 draws (baseline
  57 / 41 / 2; without the always-checks 38 / 61 / 1), 3.5x faster than the
  baseline batch; 5 battles hit the 50-turn cap (baseline 1) - watch.
  Benchmark with both grids on: 3.4 s (exhaustive ~14 s).
- **2026-10-21 (Claude):** Guess-and-follow two-ply search (Daniel: "check a
  sample of all the places you could end up, pick the best ranking one and
  then check the hexes around it. If a better choice exists follow it"), as
  switches, default OFF - every reference log and the benchmark (501 / 495)
  unchanged. `config.MOVEMENT_TWO_PLY_SEARCH` = "grid": the first mover looks
  at a 1-in-7 net of its reachable hexes (cube (q + 3r) mod 7 - the hex
  grid's own spacing: every hex is a net hex or next to exactly one), then
  climbs from the best `MOVEMENT_SEARCH_STARTS` net hexes to better
  neighbours (`movement_selection._grid_search`; a hex looked at scores all
  its facings / modes). `config.MOVEMENT_REPLY_SEARCH` = "grid" does the
  same for the second mover, in the modeled reply and in its real pick
  (Daniel: "what happens if second mover uses the same picker formula").
  Offline first (230 recorded two-ply decisions, 14 matchups): ~5 local
  peaks among ~58 hexes a decision; grid 1/7 + climb = 28% of the work,
  exact best 52%, within 2 points 78%; sparser nets lose accuracy but save
  little more (the climb dominates). A/B (`tests/ab_batches.py --set search`,
  same seeds, 50-turn cap; 100 battles Kontio vs Hammerhead, 60 the rest):
  first mover on the grid - winners within dice noise in all 6 matchups
  (Kontio 57 -> 63 / 54 with best 3; Bombardier vs Black Hawk 6 -> 11 / 11
  of 60, borderline), battles a little shorter with slightly more hits a
  turn, batches 1.4x (Atlas, slow) to 3.3x faster. A yardstick run on other
  seeds (`--set baseline --seed 777`) moved hits a turn by up to 0.09 by dice
  alone. Both movers on the grid (`--set search-both`): 20 battles each,
  close in five matchups, but Kontio vs Hammerhead 6 / 20 (baseline 11 / 20);
  100 battles confirmed it - Kontio 38 wins (baseline 57), the Hammerhead's
  CT / engine deaths 35 -> 16. Likely: the Kontio's best spots are narrow
  (the right adjacent hex and facing for its claws), the hardest kind of
  peak for a sparse net to find. Benchmark with both on: ~14 s -> 3.0 s.
  Also: `ab_batches.py` gained --set / --turns / --board / --seed, damage /
  HP / identical-battle / speed columns; Daniel's 20-battle rule (Section 7);
  `tests/test_movement_selection.py` grid_search_net_and_follow. Output:
  `run_stats/ab_search_2026-10-21.txt`, `ab_noise_...`, `ab_both_...`.
- **2026-10-21 (Claude):** Speed pass (session 6; Daniel: "Back to trying to
  speed up a simulation run"). Speed only - every reference log and the
  benchmark's 501 / 495 are unchanged. Benchmark ~17.9 s -> ~13.4 s (about
  25% less, averaged over 3 runs each in this container). (1)
  `movement_selection._modeled_reply`: the reply spots' PSR costs don't
  depend on the first mover's spot, so `_psr_by_state` works them out once
  per pick instead of ~2 million times. (2) `MoveEvaluator.evaluate`: what
  depends only on the mover's hex (LOS rows, side hit, the defender's arc
  class, the to-hit bases, water) is worked out once per hex per call
  (`_hex_row`), the facing-dependent parts once per (hex, facing); candidates
  are built positionally. (3) `movement_attacks.scored_options` accepts a
  function for `best_by_mode`, so the reply's per-mode table is built only
  when a charge / DFA state exists. (4) `pathfinder/los.hex_line` works each
  line's shape out once per hex offset and shifts it (a 16x17 board has
  ~74k hex pairs but ~1,000 offsets) - checked equal to the direct line for
  every pair on 16x17 and 50x50 boards; `tests/test_pathfinder.py`
  test_10 keeps the 16x17 check. What's left (profile): the two-ply is
  still ~95% of a turn because it is exhaustive - every first-mover spot
  (313-629 in the benchmark) x every reply spot (396-634), up to ~400k
  pairs a pick, at about 3 memo lookups each; the one-time LOS fill is
  ~25% of a cold 10-turn benchmark but is paid once per worker in a batch.
  Further big gains need fewer pairs (a bot change - Daniel's call) or a
  compiled hot path (Pick up here 1).
- **2026-10-21 (Claude):** Session 5 wrap-up (Daniel: "Go ahead and wrap
  this one up. All files up to date. List of future problems to solve
  updated. Workspace cleaned up for the next session."). Section 0 rewritten
  for session 5; Pick up here item 7 reorganized (map leftovers; breach-risk
  pricing G21 noted but NOT to be built yet; full building rules G22
  deferred); the breach plan saved in the Section 6 Memo; Section 5 records
  Daniel's calls. No code change.

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
