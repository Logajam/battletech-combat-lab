# MegaMek bridge - spec (task T14)

Written 2026-11-12 (session 25, after Hydra was finished) from a read of MegaMek's source at commit `c743b3f`
(main, 2026-11-12). Daniel's idea: "Bridge that allows our bots to connect to a live Megamek game". Daniel, same
day: read the source and write the specs first; the basic build goes to Sonnet once the spec is written.

**What it is for.**
1. Daniel plays against Hydra (or Gladiator) in MegaMek's own game screen.
2. Our bots fight MegaMek's real Princess and CASPAR, not our clone of Princess.
3. An outside check on our engine: a big gap between results in MegaMek and results in our Monte Carlo means our
   rules or our Princess clone are off somewhere.

**What it is not for.** Big trial sets. MegaMek is far slower than our engine (Daniel: "400 games on megamek would
be... grinding"). A few games to see it works and that the numbers look about right; the Monte Carlo does the
large sets.

**MegaMek is never forked or edited** (Daniel, 2026-11-12: "It sounds like you want to make a pure Megamek branch
and then start editing it" - no). The bridge lives in this repo and uses an unchanged MegaMek (a released jar, or
one built from the unchanged source) as a library. A bot is just another player joining over the network, so
MegaMek never has to know our bots exist.

---

## 1. What MegaMek's source says (checked, with file paths)

Paths are under `megamek/src/megamek/` in the MegaMek repo.

- **A bot is a network client like a human player.** `client/bot/BotClient.java` is the abstract base. The calls a
  bot fills in: `calculateMoveTurn()` returns one `MovePath`; `calculateFiringTurn()` sends that unit's attacks
  itself (`sendAttackData(entityId, Vector<EntityAction>)`); `calculatePhysicalTurn()` returns a
  `PhysicalOption`; `calculateDeployment()`; plus `initialize`, `initMovement`, `initFiring`, chat, morale.
- **CASPAR is "Princess with parts swapped".** `client/bot/caspar/Caspar.java` (2026) is `class Caspar extends
  Princess` and overrides only a few "wiring seams" (`initializePathRankers()`, `initializeFireControls()`, the
  move order). Its own header lists its changes: Mutual Support movement and deployment, aerospace doctrine,
  aerospace move order. **The bridge copies this pattern**: `class HydraBridge extends Princess`, overriding
  only movement, firing and physical attacks, so Princess still does everything we don't (deployment, morale,
  aerospace, infantry, unjamming...).
- **Which unit moves is the bot's choice.** `Princess.getEntityToMove()` picks, among the units allowed this
  turn, the one with the highest "move index" (`Princess.java` ~line 3150). This is where Hydra's move order
  (S3) plugs in.
- **Bot types are an enum and a factory.** `client/bot/AIType.java` (`PRINCESS`, `CASPAR`) and
  `client/bot/BotFactory.createBot(...)`. Our bots are NOT added here (that would mean editing MegaMek); they join as players (B5).
- **MegaMek has its own headless bot-vs-bot runner.** `utilities/AIMatchRunner.java <scenarioFile>
  [repetitions] [roundsLimit] [timeoutMinutes]`, built on `utilities/ScenarioGameRunner.java`. The scenario file
  (`.mms`) names each bot player's AI with an `ai:` key (e.g. `ai: CASPAR`; examples in
  `testresources/data/scenarios/test_setups/MixedBattleCapstone.mms`). It writes a per-game CSV (winner, rounds,
  survivors, BV left). Our launcher (B5) reuses how it starts a game; the runner itself only knows MegaMek's own bots.
- **Orders.** A move is a `MovePath` of steps (`common/moves/`: `ForwardStep`, `BackwardStep`, `GetUpStep`,
  `ChargeStep`, ... and turn steps). A shot is `new WeaponAttackAction(attackerId, targetType, targetId,
  weaponId)`, where `weaponId` is MegaMek's equipment number (`Entity.getEquipmentNum(mounted)`). A torso twist
  is `new TorsoTwistAction(entityId, facing)` in the same attack vector. Physical attacks are `PhysicalOption`
  (`client/bot/PhysicalOption.java`: `PUNCH_LEFT`, `PUNCH_RIGHT`, kicks, push, club...).
- **Same file formats as ours.** MegaMek reads `.mtf` units and `.board` maps; so do we (`data/*.board`).
- **Same facing numbers.** Both use 0 = North, clockwise (`engine/core/src/hex_geometry.rs`; MegaMek
  `Coords.java`). Positions differ: we use doubled coordinates, MegaMek 0-based (x, y). **Use the hex label
  ("0905") as the common currency** on the wire; both sides already convert labels (`hex_geometry::hex_label`,
  `Coords.parseHexNumber`).
- **License: GPL v3** (`LICENSE.code`). Anyone may use, sell or change it; whoever hands out a program built on
  it must hand out the source too, under GPL. The bridge's Java code is built on MegaMek, so it is GPL. Private
  use is unaffected. Daniel, 2026-11-12: GPL is likely the license for this project anyway "if/when it goes live".
- **Running MegaMek here:** works (Section 1b), with Daniel's OK (2026-11-12, "Go ahead"). Java 21 is installed.

## 1b. B0 results (2026-11-12, MegaMek 0.51.01.7 release, run in this session)

- **Getting it:** the release tarball from GitHub's release download (`MegaMek-0.51.01.7.tar.gz`, about 580 MB packed,
  730 MB unpacked; the proxy allows it). Built 2026-11-12, it already holds `Caspar`, `AIMatchRunner` and
  `ScenarioGameRunner`, so no build from source is needed. Run from the unpacked folder:
  `java -Djava.awt.headless=true -cp 'MegaMek.jar:lib/*' megamek.utilities.AIMatchRunner FILE.mms N ROUNDS TIMEOUT_MIN`.
  Results: `logs/ai_match_results_*.csv`; game logs `logs/gamelog_*.html`.
- **Same board:** MegaMek's `Map Set 2/16x17 Scattered Woods.board` is our `data/16x17_Scattered_Woods.board`, hex
  for hex (only line endings differ).
- **Five games, Hunchback HBK-4G v Hunchback HBK-4G, Princess v CASPAR** (one `.mms`, below): 2 played out (28 rounds
  each; one won by each bot, about 20 s a game); **2 stalled at the start** (the CASPAR player disconnected in
  round 0 after errors inside MegaMek: `Princess.updateEntityState` "Entity.getOwner() is null", `PathRanker`
  "Entity invalid"; the runner waited out its timeout and wrote the game as unfinished); **1 misread** (the Princess
  'Mech FLED the board, MegaMek's default behaviour, and the runner wrote rounds -1 and 0 BV for both sides). The
  stalls happened both on the second game of a run and on a run's only game: restarting MegaMek per game is not
  enough on its own. The autosave also fails (no `savegames/` folder; harmless).
- **What this means for the build:**
  1. Our launcher (B5) plays one game per MegaMek process, with a timeout, and **retries a game that stalls in
     round 0** (counted in the records, never silent).
  2. It **checks each result** (rounds > 0, a winner or the cap) and records a bad one as such.
  3. **Bot behaviour must match ours:** MegaMek's Princess and CASPAR withdraw / flee by default; our games fight
     to the end. Their behaviour settings (forced withdrawal, flee board) are set off in bridge games (Section 7).
  4. The two MegaMek bugs (start-of-game stall, the fled-unit misread) are worth telling the MegaMek team about.

The B0 scenario file (`at:` is the board column and row):

```yaml
MMSVersion: 2
name: B0 Hunchback duel
map:
  boards:
    - file: Map Set 2/16x17 Scattered Woods.board
options:
  off: [check_victory, simultaneous_targeting, simultaneous_firing, simultaneous_physical, simultaneous_deployment]
factions:
  - name: Observer
  - name: Red
    bot: {ai: PRINCESS}
    units:
      - {fullname: Hunchback HBK-4G, at: [8, 2], facing: 3, crew: {name: Red Pilot, gunnery: 4, piloting: 5}}
  - name: Blue
    bot: {ai: CASPAR}
    units:
      - {fullname: Hunchback HBK-4G, at: [8, 15], facing: 0, crew: {name: Blue Pilot, gunnery: 4, piloting: 5}}
```

## 2. What our engine already has

- **A 'Mech's full state to JSON and back, exactly**: `engine/core/src/mech_json.rs` (`to_json` / `from_json`,
  checked by `engine/core/tests/mech_roundtrip.rs`). The board: `Board::from_json` (`board_parser.rs`).
- **A move's step-by-step route**: `ranged_combat.rs` `path_to(...)` (used by `orchestrator.rs` `walk_path`) rebuilds the steps (forward, turn, ...) from
  the path table's parents (`pathfinder.rs`, `keep_parents`). Our bots choose an END state (hex, facing, mode,
  MP spent: `move_options::Opt` / `Pick`); `path_to` turns that into steps.
- **The bot entry points**: `BotSet` in `orchestrator.rs` (`move_pick` = who moves next, the movement pick, the
  fire pick, the physical pick), with Gladiator, Princess and Hydra behind it (`gladiator_bots.rs`, `hydra.rs`).
- **What a battle's state is**: `INTEGRATION__STATE.md` (true state vs phase scratch vs caches). The bridge sends
  only true state.

## 3. The design

```
MegaMek server  <--network-->  HydraBridge (Java, extends Princess)  <--stdin/stdout, JSON lines-->  btsim decide (Rust)
```

- **Java side: `HydraBridge extends Princess`**, in this repo under `megamek_bridge/` (its own Gradle build that
  compiles against a MegaMek jar; not inside the MegaMek source tree). It overrides `getEntityToMove()`,
  `calculateMoveTurn()`, `calculateFiringTurn()`, `calculatePhysicalTurn()`. Each one: build a snapshot of the
  game (Section 4), send a request to the Rust process, read the answer, turn it into MegaMek orders (Section 5).
  On anything it can't handle it calls `super.` (Princess decides) and counts a FALLBACK (Section 6).
- **Rust side: `btsim decide`**, a new mode of the existing binary. It starts once per game and stays alive (so
  the bots' memories, e.g. Hydra's waits and its ledger, carry from turn to turn). It reads one JSON request a
  line, builds a `Battle` from the snapshot, asks the team's bot through the normal `BotSet` calls, and writes
  one JSON answer a line. No engine rules run on the snapshot except what the bot itself runs to plan (Hydra's
  play-outs).
- **Why a subprocess and not MegaMek's network protocol from Rust:** MegaMek's protocol carries Java objects;
  speaking it from Rust would be large and break with every MegaMek release. A subprocess with JSON lines is
  easy to test from either side alone.
- **Rules inside MegaMek are MegaMek's.** Our bot plans with our engine's rules; MegaMek resolves with its own.
  Where the two differ, the bot plans for a slightly different game. That is expected, and finding those places
  is goal 3. The MegaMek game options for bridge games are set to match ours as far as possible (Section 7).
- **Decision dice.** Hydra's play-outs roll dice while planning. In the parity check the state carries our dice's
  place in their stream, so the process rolls what the battle rolled. A MegaMek game sends no dice state: the process
  then rolls its own dice, seeded by the start line's `seed`, so a recorded game's decisions can be replayed.

## 3b. B1 as built (2026-11-12): the decision process and its check

**Code:** `engine/core/src/bridge.rs`; `btsim decide` and `btsim SCENARIO --bridge-parity [--bridge-dump FILE]`
(`engine/btsim/src/main.rs`); check `tests/check_bridge_parity.py` (`--quick` runs inside `tests/run_checks.py`).

**The process is fed SIGNALS as well as decisions.** Rather than turning every bot memory (Legate's plans, Princess's
heat map, Hydra's waits and fire plan) into JSON, `btsim decide` keeps its own `Battle` for the whole game and is sent
one line for every `BotSet` call the engine makes: the signals (`start_movement`, `unit_moved`, `end_movement`,
`end_of_turn`, `reset_assigned`, `assign_damage`) and the decisions (`move_pick`, `choose_movement`, `choose_foe`,
`choose_target`, `fire_pick_active`, `fire_pick`, `choose_declaration`, `choose_physical`). The bots' memories then build
up exactly as in one of our battles. **So the Java side must send the signals too**, at the matching moments of a
MegaMek game (B2/B4): when a Movement Phase starts and ends, after each unit moves (with the hex it left), at the end of
the turn, and the damage a friend declared at a target.

**The wire, as built:**
- First line, the start: `{"config": {...}, "board": {...}, "units": {name: dump}, "hydra_teams": [...], "seed": N}` -
  a scenario's own `config.json` / `board.json` / `units.json` (`Scenario::bridge_start`). Reply `{"started": true}`.
- Every later line: `{"method": "...", "args": {...}, "state": {...}}`. Reply `{"answer": ...}` (null for a signal), or
  `{"error": message}` when the call could not be made (the Java side then lets Princess decide: a FALLBACK).
- `state` (`bridge::state_json`): every unit's full dump (`Mech::to_json`), the turn, the board's changes (smoke,
  broken magma crust, severed limbs), the move order still to come, the dice's place in their stream, and the board
  itself when it changed.
- Answers: a move is the END state `{"pick": {"hex", "facing", "mode", "fc", "mp_spent", "charge", "dfa"}, "note",
  "gate"}` (the steps come from `ranged_combat::path_to`, B4); a weapon declaration names weapons by ADDRESS,
  `"LOC#first slot"` (e.g. `"RT#3"`): fixed at the battle's start and the same in every dump (a unit rebuilt from its
  dump may renumber its equipment list, which the first parity run caught), and what the Java side looks up in MegaMek.
  The physical attack's answer is still this check's own form (B4 gives it the wire form).

**The check, as built.** An ordinary battle is played with a `Recorder` around its bots; a fresh decision process runs
alongside and is handed each call's line as it is made, and must give the same answer. Checking as the battle goes
keeps nothing in memory (keeping a 12 v 12 battle's lines ran the machine out of memory). Results (seed 1, all 86
reference battles, Gladiator, Princess and Hydra, every bot call): **every answer the same**; the 12 v 12 with Hydra
alone is about 24,000 decisions over four battles. Recording does not change a battle (same winners and turns with and
without it). The wire test pipes a whole recorded 4 v 4 battle through a real `btsim decide`, line by line.

**What this means for B3.** The state the process reads is our own unit dump, which holds far more than a MegaMek game
shows (every equipment object's fields). The Java side should NOT write those dumps. B3 instead: the Java side sends a
COMPACT state per unit (Section 4: the `.mtf` name, position, facing, heat, armor and structure per location,
destroyed slots, ammo per bin, pilot state, what it did this turn), and a new Rust step builds the full dump from it:
load the unit from its `.mtf` (as the scenario builder does), then apply the damage and state. B3's check: the compact
state of each unit in our own battles, rebuilt, gives the same dump (or at least the same answer to every decision).

**Using this to check our Princess against MegaMek's** (Daniel, 2026-11-12: could a Princess v Princess match be
replicated in the Monte Carlo, if the RNG seed matched?). A whole-game replay can't be made to match: MegaMek rolls
with an unseeded Java generator by default (it can be given a seeded one, `Compute.setRNG`, from our own launcher), but
even with the same dice the two engines must roll for the same things in the same order, and the first roll one makes
and the other doesn't shifts every roll after it. The comparison that works is DECISION BY DECISION: MegaMek plays the
game; at each of its Princess's decisions, the same position goes to our Princess clone through this process, and we
count how often they agree (as `tests/bot_agreement.py` does between bots). It never drifts, since every decision starts
from MegaMek's own position. MegaMek's roll log (game option `rng_log`) and our dice tape (`TapeDice`) also allow one
attack's rolls to be replayed in our engine, to check that the rules give the same damage. Both are later stages.

## 3c. B2 and the Rust half of B3, as built (2026-11-12)

**B2, the Java side (`megamek_bridge/`, README there).** `HydraBridge extends Princess` starts `btsim decide` as a child
process (`DecisionProcess`) and pings it; every movement, firing and physical decision is still a counted FALLBACK to
Princess (reason "game state not translated yet"). `BridgeLauncher` plays ONE game of an `.mms` with our bot on the
named players and MegaMek's own bots (the scenario's `ai:`) on the rest, all of them fighting to the end (forced
withdrawal and auto-flee off), and appends one JSON record line: who drove whom, finished, rounds, the winning team,
each team's fielded / survivors / destroyed / fled / BV, and our bot's decisions and fallbacks by reason. Built by
`build.sh` against the unchanged release (javac 21); MegaMek is used as a library only.
- Found while building: a Princess (and so our bot) must have `startPrecognition()` called after it is made, as
  MegaMek's `BotFactory` does, or it waits forever on its first move.
- Check (B2's "done when"): three Hunchback duels, our bot (all FALLBACK) v CASPAR, all finished (about 70 s each),
  `pong` from the engine, 50-199 decisions a game, all counted. One record has the misread B0 saw (rounds -1, a unit
  neither destroyed nor fled): to look at with the records work in B4.

**B3, Rust half: the COMPACT unit state.** `bridge.rs` `UNIT_FIELDS` (78 fields) and `ITEM_FIELDS` (19 per equipment
object, by address), `compact_unit` / `apply_compact`: a unit is its start-of-battle record (built from the `.mtf`)
plus only what a battle changes - those fields, the critical slots that differ from the start, and the equipment
fields that differ. About 18 KB a unit becomes a few hundred bytes. The lists were MEASURED (every reference battle,
every field compared with its start value), then three were added when the compact-mode check found them
(`home_edge` / `home_edge_row`, set at deployment; `stuck`, first seen in the 8 v 8s). The check now holds every
reference battle to: every unit rebuilt from its compact state equals its real record at every call, field for field
("rebuild gaps", reported by name), and every answer the same. **This list is what the Java side must send per unit,
and what a Combat Lab save of a unit needs.**

**B3, Java half (next).** For each MegaMek unit, write those fields from MegaMek's `Entity` (position, facing, heat,
armor per location, destroyed slots, ammo by bin, jams...). The START line is ready: `{"settings": {...}, "hydra_teams",
"seed"}` builds the game in Rust from settings (Combat Lab CL1, `Scenario::from_settings`): FORCES with each unit's `.mtf`,
team, hex, facing, skills; the board; `DEPLOYMENT: "fixed_hexes"`. The Java side writes that from the MegaMek game. Many of the 78 are our engine's own bookkeeping (snapshots
taken at phase starts, this turn's movement, `hp_log`): the decision process can keep those itself from the signals
rather than read them from MegaMek. Sorting the 78 into "MegaMek says" and "we keep" is B3's first job.

## 3d. B3 (Java half) and B4, as built (2026-11-12): our engine plays in MegaMek

**The start.** `GameView.start` writes the game as SETTINGS (Combat Lab CL1): every MegaMek unit, in entity-id order,
as a FORCES entry (`"name": "U<id>"`, `"team": "T<team>"`, its `.mtf` - "Chassis Model.mtf" in our data folder -,
hex, facing, gunnery, piloting), `DEPLOYMENT: fixed_hexes`, and `DEFAULT_BOARD_PATH` = the scenario's board file in
MegaMek's data/boards (the same format as ours; the launcher reads it from the `.mms`). Our engine builds the game from
that (`Session::start` with "settings"). A unit with no `.mtf` in our data folder turns the bridge off for the game
(every decision a FALLBACK, the reason recorded).

**Before every question: MegaMek's view of each unit** (`GameView.state` -> `bridge::apply_megamek_view`): hex,
facing, prone, shutdown, heat, destroyed, armor / rear / structure / destroyed per location, destroyed critical slots
(through the engine's own slot loss, `damage_resolution::destroy_slot_quietly`: engine, gyro, heat sink, jump jet
counters follow; no explosion, MegaMek resolved it), ammo by address, jammed weapons, pilot hits and consciousness,
this turn's movement (mode, MP) and torso twist. A new round runs the engine's start-of-turn bookkeeping (each unit's
turn number - Hydra's Waiting counts turns with it -, the damage snapshot for piloting rolls). Not sent (our engine's
own bookkeeping keeps its start-of-game value or what the signals build): phase snapshots, `hp_log`, smoke and other
board changes (no such terrain in the first games).

**Signals** (`HydraBridge`): `start_movement` at our first movement decision of a round (after `end_of_turn` for the
last one), `unit_moved` for every unit seen done since (with the hex it started the round in), `end_movement` and
`reset_assigned` at our first firing decision of a round. Not sent yet: `assign_damage` (friends' declared damage, which
our Princess clone's target choice uses).

**Orders.**
- MOVE: `move_pick` among our units MegaMek allows to move (else the first), `choose_foe`, `choose_movement` (a prone
  unit plans with its running MP - 2, the stand's cost, Core p.98; the route starts with GET_UP and MegaMek rolls the
  stand), `path_steps` (new: the pick's route as MegaMek steps - forward, backward, turn_left / turn_right, get_up -
  from `ranged_combat::path_to`). The steps become a `MovePath`; if MegaMek finds it illegal or it ends elsewhere, its
  own path finder (`MovePath.findPathTo`) is tried to the same hex and facing; then a FALLBACK. Jumps go straight to
  the path finder (START_JUMP first). Charges and death from above: FALLBACK (not wired).
- FIRE: `choose_target`, then `choose_declaration`; weapons by address -> MegaMek's mounted item (location name and
  first slot) -> `WeaponAttackAction`; a torso twist first (`TorsoTwistAction`, same convention as ours: torso facing
  = facing + twist). A weapon MegaMek rules impossible is left out and counted. Arm flips: FALLBACK.
- PHYSICAL: `choose_target` (adjacent only), `choose_physical` (its answer now carries the attacks' `names`): one
  punch, both punches, or one kick become MegaMek's `PhysicalOption`; clubs, pushes, anything with a twist: FALLBACK.
- Every refused or unwired case is counted by reason in the game's record ("ours" by kind, "fallbacks" by reason), and
  the bridge logs each decision (`[bridge]` lines in MegaMek's `logs/unified_log.log`), with MegaMek's own to-hit for
  every weapon whenever our engine declines to fire (the two engines' line of sight and range, side by side).

## 4. The request (Java -> Rust), one JSON object a line

(The first draft, from before B1. The wire as built is Section 3b; this section's per-unit fields are the COMPACT state
B3 sends.)

```json
{"kind": "move_order" | "move" | "fire" | "physical" | "game_start" | "game_end",
 "game": {"seed": 123, "round": 4, "phase": "movement", "board": "16x17_Hilltops_1.board",
          "board_changes": [], "my_team": 1, "bot": "hydra", "settings": {}},
 "unit": 7,                              // the unit to decide for (absent for move_order: the bot picks)
 "eligible": [7, 9],                     // move_order only: units MegaMek allows to move now
 "units": [ {
     "id": 7, "team": 1, "mtf": "Hunchback HBK-4G", "pilot": [4, 5],
     "hex": "0905", "facing": 2, "twist": 0, "prone": false, "shutdown": false, "heat": 6,
     "armor": {"LA": 10, "LT": 12, "LTR": 4, ...}, "internal": {...},
     "destroyed_slots": [["RT", 3], ...], "ammo": [["RT", 4, 12], ...],
     "pilot_hits": 1, "conscious": true,
     "done": false, "moved_this_turn": {"mode": "Run", "hexes": 6, "jumped": false}
 } ]}
```

- `mtf`: the unit's chassis and model as MegaMek names it. Rust finds the `.mtf` in our `data/` by that name;
  a unit with no matching file is refused (FALLBACK, logged with its name) in the first version.
- Damage, slots and ammo use our location names (`LA`, `LT`, `LTR`...); the Java side maps MegaMek's location
  numbers to them (`Mek.LOC_*`).
- `board_changes`: fires, smoke, rubble, broken crust. **First version: refuse a board with changes** (FALLBACK
  for every decision once the board has changed). Later: map them onto `Board`.
- `game_start` carries every unit and the scenario once; `game_end` lets Rust write its record (Section 6).

## 5. The answer (Rust -> Java)

```json
{"move_order": 9}
{"move": {"unit": 7, "mode": "Run", "end": {"hex": "0807", "facing": 3},
          "steps": ["turn_left", "forward", "forward", "turn_right", "forward"]}}
{"fire": {"unit": 7, "twist": -1, "shots": [{"weapon": ["RT", 2], "target": 12}, ...]}}
{"physical": {"unit": 7, "kind": "kick", "target": 12}}       // or {"physical": null}
{"fallback": "reason"}                                          // Rust can't decide: Java lets Princess do it
```

- **Moves.** Steps come from `path_to`. Jumps: `start_jump` then hexes and the final facing (our jump search
  gives an end state; build the straight-line hexes). Java builds the `MovePath` from the steps and checks it
  (`MovePath` legality / its end hex and facing). If MegaMek refuses it, Java asks MegaMek's own path finder for
  the same end hex, facing and move mode; only if that fails too, FALLBACK. Charges and DFAs: the same, ending in
  the `ChargeStep` / DFA step.
- **Weapons** are named by (location, slot) as in the `.mtf`; Java maps that to MegaMek's equipment number
  (find the mounted whose location and first critical slot match, then `getEquipmentNum`). Ammo choice: MegaMek's
  default bin unless our engine chose one.
- **Twist** goes first in the attack vector as a `TorsoTwistAction`.

## 6. Records and fallbacks (Daniel's standing order: records are always kept)

- **Every FALLBACK is loud and counted**, like a stub (`INTEGRATION__stubs.py` rule): reason, unit, round,
  phase. A game with many fallbacks is reported as one where our bot did not really play.
- **One JSON line per game** in `trial_records/megamek/` (`tools/trial_records.py` style): scenario, bots,
  seed, winner, rounds, BV left (from MegaMek's own CSV), decisions made, fallbacks by reason, any refused
  orders. Written when the game ends, so a stopped set keeps its finished games.
- **Every refused order** (MegaMek said no to a move or shot we sent) is logged with the full request and
  answer: each one is a place where our rules and MegaMek's differ, or a bridge bug.

## 7. MegaMek game options for bridge games

Match our engine (`engine/core/src/config.rs`, `INTEGRATION__config.py` OPTIONAL RULES): Total Warfare rules,
TacOps options off unless our config turns the same rule on, no double-blind, no fog of war, no
forced withdrawal unless our battle has it, the MegaMek bots' own withdraw / flee-board behaviour off (B0: a
Princess 'Mech fled the board by default), same turn cap (ours is 100; MegaMek's runner takes `roundsLimit`).
The list is filled in during B4 by reading MegaMek's game options file (`common/options/`), one line per option
with our setting beside it. **Any option where the two can't match is a question for Daniel.**

## 8. Build order (each stage has a check a script can run)

| Stage | What | Model | Done when |
|---|---|---|---|
| **B0** DONE (Section 1b) | Get an unchanged MegaMek (a released jar, or built from the unchanged source) and run `AIMatchRunner` on a small `.mms` (Princess v CASPAR, 2 games). Needs Daniel's OK to run MegaMek's downloaded code here (or he runs it on his computer). | Sonnet | Two games finish and the CSV is written |
| **B1** DONE (Section 3b) | `btsim decide`: snapshot -> `Battle` -> `BotSet` call -> answer. Snapshot writer on the Rust side too (`--snapshot` on an ordinary battle). | Opus (the snapshot -> `Battle` step needs judgement; `INTEGRATION__STATE.md` lists every field) | **Parity check** (`tests/check_bridge_parity.py`): in ordinary battles, snapshot at every decision, feed it to `btsim decide`, the answer must equal what the battle chose. Every bot, the reference scenarios. |
| **B2** DONE (Section 3c) | `megamek_bridge/`: `HydraBridge extends Princess`, the subprocess, request/answer JSON, FALLBACK on everything (Rust answers `fallback` to all) | Sonnet | A bridge game finishes with every decision a FALLBACK and the same result as plain Princess on the same seed |
| **B3** Rust half DONE (Section 3c) | Compact state (Section 3b, "What this means for B3"): the Java side writes each unit's compact state (Section 4); a Rust step rebuilds the full dump from the `.mtf` plus that state | Opus for the Rust step, Sonnet for the Java | In our own battles, every unit's compact state rebuilt gives the same answer to every decision (the parity check run through the compact form); Java's compact state of a game's start equals Rust's of the same scenario |
| **B4** | Orders: moves, shots, twist, physical (Section 5); fallbacks and records (Section 6); game options (Section 7) | Sonnet; Opus for the path-refusal cases | A 1 v 1 'Mech duel, Hydra v Princess, plays with no FALLBACK and no refused order |
| **B5** | Our own launcher (`megamek_bridge/`): starts a game from an `.mms` file the way `ScenarioGameRunner` does and connects `HydraBridge` as a player, using MegaMek as a library. NOT a patched `AIType` / `BotFactory`: MegaMek is never edited. | Sonnet | The launcher plays Hydra v CASPAR from an `.mms` file and writes the records |
| **B6** | Check against our numbers: a few games each of Hydra v Princess and Hydra v CASPAR on our standard duels; compare with the Monte Carlo's | the top model to read the result | Numbers written up for Daniel; every big gap listed as a rules difference to look at |
| **B7** | Daniel plays Hydra from his own computer (MegaMek lobby, join a game with the bridge bot) | Sonnet writes the how-to | Daniel has played a game |

**First version's limits** (each one a FALLBACK, never a crash): 'Mechs only; no board changes; no units
without a `.mtf` in our `data/`; no equipment our engine doesn't model.

## 9. Open questions

- **For Daniel:** where the Java code lives (proposed: `megamek_bridge/` in this repo, GPL); the game options
  that can't match (after B4); whether to tell the MegaMek team (their Discord) - they may already have a way for
  an outside bot to connect, which would replace B5.
- **To check in B2/B5:** which `ScenarioGameRunner` pieces are public enough for our launcher to reuse; where
  they aren't, the launcher repeats them in our own code (still no edit to MegaMek).
