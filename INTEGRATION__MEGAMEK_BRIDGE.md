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
  `client/bot/BotFactory.createBot(...)`. Adding `HYDRA` (and `GLADIATOR`) is one enum value and one `case` each.
- **MegaMek has its own headless bot-vs-bot runner.** `utilities/AIMatchRunner.java <scenarioFile>
  [repetitions] [roundsLimit] [timeoutMinutes]`, built on `utilities/ScenarioGameRunner.java`. The scenario file
  (`.mms`) names each bot player's AI with an `ai:` key (e.g. `ai: CASPAR`; examples in
  `testresources/data/scenarios/test_setups/MixedBattleCapstone.mms`). It writes a per-game CSV (winner, rounds,
  survivors, BV left). **We don't need to build a game runner**: add our type to the enum and use this one.
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
- **Not checked yet:** building and running MegaMek here. A Gradle build of MegaMek in this session was refused
  by the session's safety check (running downloaded build code needs Daniel's OK). Java 21 is installed.

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
- **Decision dice.** Hydra's play-outs roll dice while planning. In `btsim decide` they are seeded from (game
  seed, round, unit id) so a decision can be replayed.

## 4. The request (Java -> Rust), one JSON object a line

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
forced withdrawal unless our battle has it, same turn cap (ours is 100; MegaMek's runner takes `roundsLimit`).
The list is filled in during B4 by reading MegaMek's game options file (`common/options/`), one line per option
with our setting beside it. **Any option where the two can't match is a question for Daniel.**

## 8. Build order (each stage has a check a script can run)

| Stage | What | Model | Done when |
|---|---|---|---|
| **B0** | Build MegaMek here and run `AIMatchRunner` on a small `.mms` (Princess v CASPAR, 2 games). Needs Daniel's OK to run MegaMek's downloaded build (or he runs it on his computer). | Sonnet | Two games finish and the CSV is written |
| **B1** | `btsim decide`: snapshot -> `Battle` -> `BotSet` call -> answer. Snapshot writer on the Rust side too (`--snapshot` on an ordinary battle). | Opus (the snapshot -> `Battle` step needs judgement; `INTEGRATION__STATE.md` lists every field) | **Parity check** (`tests/check_bridge_parity.py`): in ordinary battles, snapshot at every decision, feed it to `btsim decide`, the answer must equal what the battle chose. Every bot, the reference scenarios. |
| **B2** | `megamek_bridge/`: `HydraBridge extends Princess`, the subprocess, request/answer JSON, FALLBACK on everything (Rust answers `fallback` to all) | Sonnet | A bridge game finishes with every decision a FALLBACK and the same result as plain Princess on the same seed |
| **B3** | Java snapshot writer (Section 4) | Sonnet | Java's snapshot of a game's start equals Rust's snapshot of the same scenario (a test compares the two) |
| **B4** | Orders: moves, shots, twist, physical (Section 5); fallbacks and records (Section 6); game options (Section 7) | Sonnet; Opus for the path-refusal cases | A 1 v 1 'Mech duel, Hydra v Princess, plays with no FALLBACK and no refused order |
| **B5** | `AIType.HYDRA` / `GLADIATOR` in a patched `BotFactory`, or a launcher that adds the bot to a game (whichever MegaMek allows without changing its source; the read so far says the enum has to be patched) | Sonnet | `AIMatchRunner` plays Hydra v CASPAR from an `.mms` file |
| **B6** | Check against our numbers: a few games each of Hydra v Princess and Hydra v CASPAR on our standard duels; compare with the Monte Carlo's | the top model to read the result | Numbers written up for Daniel; every big gap listed as a rules difference to look at |
| **B7** | Daniel plays Hydra from his own computer (MegaMek lobby, join a game with the bridge bot) | Sonnet writes the how-to | Daniel has played a game |

**First version's limits** (each one a FALLBACK, never a crash): 'Mechs only; no board changes; no units
without a `.mtf` in our `data/`; no equipment our engine doesn't model.

## 9. Open questions

- **For Daniel:** where the Java code lives (proposed: `megamek_bridge/` in this repo, GPL); the game options
  that can't match (after B4); whether to tell the MegaMek team (their Discord) - they may already have a way for
  an outside bot to connect, which would replace B5.
- **To check in B0/B2:** whether MegaMek can load a bot class from outside its own jar, or only through
  `AIType` (decides B5).
