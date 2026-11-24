# Project history - the old PROJECT_MAP Section 0, kept word for word

Moved out of `INTEGRATION__PROJECT_MAP.md` on 2026-11-10 (Daniel: "clean up the project map"). Nothing was
rewritten: session summaries (newest first), then the old "Pick up here" list with Daniel's words and every
number. The CURRENT state and open work are in PROJECT_MAP Section 0; where they differ, Section 0 wins.
Code comments that say "Pick up here 000000 / 00000 / ... / 16" mean the items of the list below.

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
000000. **THE PERIL LINE - STATE AT THE PIVOT (2026-11-08).** BUILT, all committed: `INTEGRATION__vision` (per-board visibility / modifier / distance table), `INTEGRATION__peril` (per-unit and per-side damage fields over
   the board: peak and mean, from each unit's footprint, LOS and cover applied; `field_for` caches per phase), `INTEGRATION__stack` (stacked coverage up to an enemy's HP, `config.STACK`, off: no gain),
   `INTEGRATION__triage` (peril / toughness tiers, `config.TRIAGE`, **ON by default since 2026-11-08**: 51 v 42 wins over 100 battles at a 100-turn cap, 'Mechs left 2.32 v 1.62) and the mirror map (`triage.reach_on`);
   `config.PERIL` (field replaces the other enemies' damage in the move score, off: not better); `tests/peril_picture.py` (the heat map of a saved turn as a page); tests `test_peril`, `test_stack`, `test_triage`.
   DANIEL'S DESIGN (kept for reference): every unit's weapons-over-range table projected from it, covering its arcs (a mover picks its facing at the end, so arcs bind only a unit that stands still), smeared over its
   movement footprint, filtered by line of sight (no LOS: nothing; woods / partial cover: the to-hit modifier), one field a unit; a side's Peril is the sum; "super position of movement x damage x counter movement
   collapsing to the best spot". His refinements: smart LOS blocking (a hex that blocks a line blocks everything past it at the same level), partial LOS testing (corners / short list). Both speed the build or change
   accuracy only; the table is static, so they were not needed (2 s for the 544-hex field).
   OPEN, in the order I would take them: (a) THE PICKER does not see that it can win and close in (Daniel, 2026-11-08: the end-game stand-off, 1 v 2 left at 100 turns, is a picker problem, not a special mode);
   (b) TRIAGE KNOBS: the 25% share, the two weights (hot x2, cool x1.5), peak v mean in the ratio - each a 20-battle A/B at `--turns 100` against the five triage sets; (c) arcs for units that stand still;
   (d) the accuracy tests of the two shortcuts against the exact field (only worth it for a board too big to build exactly: 3 x 3 boards ~42 s); (e) disk cache of the visibility table and a rebuild on smoke
   (`vision.invalidate` exists; nothing calls it); (f) speed: the new terms cost about 2x a turn (1.5 to 3.4 s); (g) Legate reads the board for good terrain (cover that sees: only partial cover, elevation, arcs and
   range differences are asymmetric, since LOS itself is symmetric); (h) Legate holds back until most of its combat power can engage at once; (i) tiered movement order refinements (resting); (j) ordinary
   physical-attack value in the movement model looks about 2x high. A BATTERY: `python tests/baseline_battery.py pg 20 --legate --turns 100 --seed N [--stats] --first A --last B` (resumable; `--no-triage` = the old baseline).
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

## Session 26's pick-up note (moved from PROJECT_MAP Section 0 on 2026-11-24, session 35, word for word)

**Pick up here (Daniel, 2026-11-14, closing session 26):** "I'll start that list tomorrow" - he will play with Combat Lab
alpha-2 (`downloads` branch, `CombatLab-alpha-2.zip`) and bring a change list; then it goes to Opus for review before
anything goes to the public repo (E6). Session 26 built Daniel's round-2 list, all of it merged to `main` (pull requests 224,
225): CL11-CL17, CL19-CL21 (Princess) and the standard parts of CL18; every entry is in the Change Record and the REVIEW QUEUE
below. OPEN: (1) CL18's live user-built conditions, saved for Opus to design (the sheet in `INTEGRATION__COMBAT_LAB_V2_TASKS.md`);
(2) CL21's Gladiator and Hydra heat maps (need CL6 saved state / CL7 overlays); (3) the Windows `CombatLab.exe` of alpha-2 was not
run (no Wine here): if it misbehaves on Daniel's PC, start there.
