# Hydra: the third bot (design plan)

Daniel, 2026-11-11: "start from first principles on your own bot - entirely envisioned and designed by
you ... it needs to be effective from 1 on 1 to large force engagements 12 on 12 or possibly higher."
Rust only (the Python is retired; there is no Python answer key for this bot).

This file is the plan: WHAT each block is supposed to do and how the blocks connect. How a block does
its sums may change; its job and its connections should not change without a note here. A model picking
this work up should read Sections 1-4, then the status table in Section 6.

## 1. The idea in four sentences

1. **One mind, many bodies.** Hydra is not twelve pilots. It is one planner per team; the units are
   its limbs. Every decision of every unit is scored by what it does for the whole team.
2. **One currency.** Every point of damage, dealt or taken, is priced by how much it changes the
   predicted END of the battle (who is left standing, and how much of them). There are no hand-set
   weights such as "aggression" or "caution".
3. **Prices come from a forecast.** A small, fast model plays the rest of the battle forward as a
   battle of attrition ("the Forecast"). Damage on a unit is worth what the Forecast says it is worth.
4. **Uncertainty is stated, not ignored.** An enemy that has not moved yet is treated as an enemy that
   WILL turn to face you, not as a statue.

What falls out of this without being written as a rule: focus fire (the Forecast prices the damage
that kills soonest highest), protecting a hurt but valuable friend (its damage price is high),
boldness when winning and care when losing, and ignoring an enemy that will not matter.

## 2. The blocks

```
            +-----------+     +------------+     +-----------+
 battle --> |  LEDGER   | --> |  FORECAST  | --> |  PRICES   |
 state      +-----------+     +------------+     +-----------+
                                                   |   |   |
              +------------------------------------+   |   +---------------------+
              v                                        v                         v
        +-----------+   exchange    +-------------------------+        +----------------+
        |  MOVER    | <------------ |  EXCHANGE ORACLE        | -----> |  FIRE PLAN     |
        | (one unit |    table      | (engine: expected damage|        | (whole team,   |
        |  at a time)|              |  both ways, two poses)  |        |  once a phase) |
        +-----------+               +-------------------------+        +----------------+
              |                                                                 |
              v                                                                 v
        movement pick                                         target per unit, then weapons, physical
```

### LEDGER - "what is every unit worth right now"
- In: the battle state. Out: for every unit on both sides, two numbers.
  - `life`: how much damage it can still absorb before it stops fighting.
  - `guns`: how much damage a turn it can put out when it has a shot.
- Rebuilt at the start of every Movement Phase and every Weapon Attack Phase.
- Must be cheap and must not depend on where units stand (position is the Mover's business).

### FORECAST - "how does this battle end from here"
- In: the Ledger. Out: one number, the **margin**: (what my team has left) minus (what theirs has
  left) when the fight is played out as pure attrition, both sides concentrating fire sensibly.
- It is a model, not the engine: no dice, no board, a handful of steps. It must run thousands of
  times a second, because Prices calls it once per unit.
- It must work the same for 1 v 1 and 12 v 12 (cost grows with the number of units, no worse).

### PRICES - "what is one point of damage on unit X worth"
- In: Ledger + Forecast. Out: one price per unit.
- Method: take a little life off unit X in the Ledger, run the Forecast again, see how far the margin
  moved. That is X's price. Enemy prices say what hitting them is worth; friend prices say what
  being hit costs.
- This is the ONLY place values come from. Every other block multiplies damage by a price.

### EXCHANGE ORACLE - "if A stands here and B stands there, what damage flows each way"
- This is the engine's own expected-damage calculation (range, arcs, cover, movement modifiers, heat,
  physical attacks). Hydra does not re-derive rules; it asks the engine.
- Two poses for the other unit:
  - **Fixed**: it has already moved this turn; use where it actually is.
  - **Ghost**: it has not moved yet; assume it stays near, has moved a typical amount, and
    turns to face whoever it is being compared with.

### MOVER - "where does this unit go"
- Called by the engine for one unit at a time, in initiative order.
- For every legal end position of the unit:
  - **gain** = the best (price of enemy x damage I would deal to it) over the enemies;
  - **cost** = my own price x the damage each enemy would deal me, each enemy counted by the share
    of its attention I would get (an enemy has one target; friends near me share the load);
  - **risk** = my own price x expected damage from falls and hazards on the way.
- **The score** of a spot = what it does to my team's rate of exchange over a typical turn:
  (d0 + gain) / (r0 + cost + risk), where d0 / r0 = what my whole team, this unit included, deals /
  takes in a typical turn (from the Ledger, priced). In a big force one unit's trade is small next to
  d0 and r0, so the score asks "is this trade better than the team's average?". In a duel d0 and r0
  are the unit's own typical turn, which stops it chasing a tiny free shot over a solid trade.
  A unit that waits scores d0 / r0, so stalling never beats a fair trade.
- Tried and dropped (2026-11-11, mirror match-ups v Gladiator, Hydra wins - Gladiator wins):
  - pure rate, gain / cost: agile duel 19-54 (too picky), heavy 4 v 4 55-17;
  - gain - cost, cost discounted when losing: agile duel 30-35, heavy 4 v 4 40-28, 12 v 12 11-16;
  - the rule above (kept): agile duel 33-34, heavy 4 v 4 51-24, 8 v 8 15-7.
- **The reply.** An enemy that has not moved will answer. The best few spots (one per hex) are scored
  again against the best answer of the unmoved enemy that weighs most on them (the rival). The number
  of spots re-scored shrinks as more enemies are weighed, so the cost stays level in a big battle.
- **Never refuses battle.** If any spot deals damage, a spot that deals damage is chosen. (Purpose:
  the simulator exists to resolve the fight. A later stage may let a unit wait for its friends.)
- No position deals damage: close on the highest-priced enemy among the nearest, by the safest route.
- Only enemies that can matter this turn are asked about (reach + weapon range), so a 12 v 12 does
  not cost 12 times a duel for every unit.

### FIRE PLAN - "who shoots whom"
- Run once per team at the start of the Weapon Attack Phase, for all its units together.
- In: Prices, and from the engine each unit's expected damage on each enemy it can hit.
- Out: one target per unit. The plan maximizes the sum of (price x damage), where damage beyond what
  is needed to finish a target counts for nothing (no overkill), so spare guns go to the next target.
- Weapons and heat for the chosen target, and the physical attack: the engine's existing
  expected-damage optimizers. They are sums, not judgment; Hydra does not replace them.

## 3. How it plugs into the engine

**What Hydra borrows from Gladiator (Daniel, 2026-11-12: "Did Fable copy my homework?" - yes, the measuring tools):** a unit's
LIFE is Daniel's rule (armor + MOVEMENT_STRUCTURE_WEIGHT x structure, `orchestrator::effective_hp`; Hydra's own weight
setting exists since S6's second pass, kept at 2); its GUNS are Gladiator's damage a turn (`move_select::future_damage`);
the EXCHANGE ORACLE is Gladiator's move evaluator (`MoveEvaluator`) with its exposure weighting and fall-risk costs; the
reply's options and the charge / DFA stops are Gladiator's lists. And life x guns as a unit's worth is close to Daniel's
"lifetime" (turns survived x damage a turn). Hydra's own: one planner a team, damage priced by the Forecast's ending, the
rate score, the team fire plan, the play-out.

- A unit's bot name is `"hydra"`. The engine asks its bots through one socket, `BotSet`
  (`engine/core/src/orchestrator.rs`); `engine/core/src/gladiator_bots.rs` routes each question by the
  unit's bot name, and sends a Hydra unit's to `engine/core/src/hydra.rs`.
- Hydra's memory for a battle (ledger, prices, the phase's fire plan) lives in `Battle::hydra`.
- Run: `btsim SCENARIO_DIR --hydra TEAM` makes every unit of that team a Hydra (the scenario files
  still come from the old tools).
- Trials: `python tools/hydra_scenarios.py` builds the mirror match-ups (same 'Mechs both sides) into
  `engine/fixtures/hy_*`; `python tools/hydra_trial.py engine/fixtures/hy_* --battles 40` plays each
  three ways (nobody Hydra, first team Hydra, second team Hydra) and prints the comparison.

## 4. How it is judged

No exact-match test exists for this bot. It is judged by results, on the same seeds:
1. **Does not break the engine**: with no Hydra unit, every existing test still passes unchanged.
2. **Beats the house bots**: Hydra v Gladiator and Hydra v Princess, sides swapped so the 'Mechs and
   the starting edge cancel out, at duel, 4 v 4 and 12 v 12. Report wins and surviving strength.
3. **Speed**: seconds per battle next to Gladiator on the same match-up.
4. **Repeatable**: same seed, same result.

## 5. Results so far (2026-11-11, first day)

Mirror match-ups (same 'Mechs both sides, `tools/hydra_scenarios.py`), Hydra v Gladiator, both seatings,
40 battles a seating (16 for 8 v 8). Hydra wins - Gladiator wins - no winner:

| Match-up | Result | Read |
|---|---|---|
| duel, Griffin, open ground | 33 - 34 - 13 | level |
| duel, Hunchback, woods | 23 - 47 - 10 | **loses: the known weak spot** |
| duel, Awesome, hills | 47 - 33 - 0 | wins |
| 2 v 2, open ground | 32 - 45 - 3 | loses |
| 4 v 4 lance, open ground | 41 - 29 - 10 | wins |
| 4 v 4 lance, woods | 41 - 28 - 11 | wins |
| 4 v 4 heavies, hills | 51 - 24 - 5 | wins clearly |
| 8 v 8 | 15 - 7 - 10 | wins |
| 12 v 12 | 14 - 15 - 3 | level |

Speed: Hydra's battles take about half the time of Gladiator's at 4 v 4 and above.
Not yet tried: Hydra v Princess (`python tools/hydra_scenarios.py --house princess`).

**Hydra v Princess (session 25, 2026-11-12)**, same mirror set (`tools/hydra_scenarios.py --house princess`), 40 battles a
seating (16 for 8 v 8 and 12 v 12). Hydra - Princess - none:

| Match-up | Result |
|---|---|
| duel, Griffin | 71 - 7 - 2 |
| duel, Hunchback, woods | 51 - 25 - 4 |
| duel, Awesome, hills | 46 - 32 - 2 |
| 2 v 2 | 52 - 28 - 0 |
| 4 v 4 lance, open ground | 56 - 24 - 0 |
| 4 v 4 lance, woods | 49 - 30 - 1 |
| 4 v 4 heavies | 56 - 24 - 0 |
| 8 v 8 | 15 - 13 - 4 |
| 12 v 12 | 20 - 11 - 1 |

All nine: 416 - 194. Ahead everywhere, the brawler duel included (Princess is weaker there than Gladiator). One caution: at
8 v 8 and 12 v 12 Hydra wins more but its strength-left margin is slightly negative (-0.04, -0.03): it wins by finishing
units, not by trading cheaply - few battles there, worth a longer look.

**Round robin (session 25, 2026-11-12)**, `tools/round_robin.py`: every bot against every bot, itself included, on the
nine mirror match-ups, both seatings, 40 battles a seating (16 for 8 v 8 / 12 v 12), seed 1. Wins - wins - no winner:

| Pairing | Result | Share of decided battles |
|---|---|---|
| Hydra v Princess | 416 - 194 - 14 | Hydra 68% |
| Hydra v Gladiator | 285 - 245 - 94 | Hydra 54% |
| Gladiator v Princess | 331 - 240 - 53 | Gladiator 58% |
| Gladiator v itself (Red - Blue) | 118 - 126 - 68 | |
| Hydra v itself | 145 - 148 - 19 | |
| Princess v itself | 168 - 125 - 19 | Red's edge is worth something to Princess, not to the others |

So the order is Hydra, Gladiator, Princess. Gladiator v itself has the most draws (68 of 312): the stand-off of backlog A1.
Gladiator v Princess per match-up: Princess wins only at 8 v 8 / 12 v 12 (20 - 24).

**Time a battle takes (session 25, one core, nothing else running; each bot playing itself, so both sides' thinking):**

| Match-up | Gladiator | Princess | Hydra | Hydra + S5a |
|---|---|---|---|---|
| duel, Griffin | 25 ms a turn (0.95 s a battle) | 7 (0.14) | 38 (1.58) | 39 (1.52) |
| 4 v 4 lance | 164 (4.2) | 49 (1.2) | 79 (1.6) | 182 (3.3) |
| 12 v 12 | 335 (14.6) | 237 (11.9) | 231 (4.9) | 472 (10.4) |

The engine's own rules work is in every figure. Hydra's battles are also shorter (it trades), which is part of its speed per
battle. S5a costs about 2.1 - 2.3 times plain Hydra per turn from 4 v 4 up (the plan's target: 2 times).

What the weak spots have in common: few units, short range, and Hydra moving FIRST. Then everything
rests on guessing the enemy's answer, and Hydra's guess (one rival, scored on Hydra's own terms) is
poor: in the brawler duel it predicted "I deal 2.9, take 8.0" and still had to go. Stage S5a below is
aimed at exactly this.

### Second pass (2026-11-11, later the same day): three changes kept, four tried and dropped

Kept (all in the Mover; each judged on the same seeds, 40 battles a seating):
- **Where damage lands.** Every damage figure in an exchange is multiplied by the engine's exposure factor of the
  side it arrives on (front / left / right / rear, from the armor and structure left there).
  2 v 2 + 4 v 4 woods: 69 - 64 with it, 59 - 70 without.
- **A unit alone may hide.** When Hydra must move first and no friend is in any weighed enemy's reach, the
  spots sent to the reply include those that deal nothing. A unit with friends may NOT: hiding leaves them
  the fire (tried for everyone: 4 v 4 woods fell from winning to 28 - 36).
- **Reply budget 64** (was 32). 128 and 256 gave nothing more.

| Match-up | Before | After |
|---|---|---|
| duel, Griffin | 33 - 34 - 13 | 38 - 26 - 16 |
| duel, Hunchback, woods | 23 - 47 - 10 | 29 - 38 - 13 (still the weak spot) |
| 2 v 2 | 32 - 45 - 3 | 34 - 34 - 12 |
| 4 v 4 lance, woods | 41 - 28 - 11 | 35 - 30 - 15 (within the noise of 80 battles) |

Whole table re-run in session 25 (same build; the four rows above reproduced exactly), Hydra - Gladiator - none,
40 battles a seating (16 for 8 v 8 and 12 v 12): Awesome duel 42 - 36 - 2 (was 47 - 33 - 0); 4 v 4 grass 36 - 33 - 11
(was 41 - 29 - 10); 4 v 4 heavies 42 - 25 - 13 (was 51 - 24 - 5); 8 v 8 16 - 11 - 5 (was 15 - 7 - 10); 12 v 12 13 - 12 - 7
(was 14 - 15 - 3). All nine: 285 - 245. Seconds a battle (wall, 4 threads), Gladiator mirror v with Hydra on one side:
4 v 4 0.70-1.00 v 0.46-0.60; 8 v 8 2.13 v 1.37; 12 v 12 4.53 v 2.86. Still ahead from 4 v 4 up and faster; the brawler
duel and 2 v 2 are the gaps, as before.

Tried and dropped (no gain, so the code does not carry them):
- pressing harder when ahead (judging trades as if level; discounting damage taken by the lead): flat;
- more or less weight on the team's typical turn in the score (x 0.3, x 3): flat;
- counting the fire a friend takes when I hide as my cost: much worse (74 - 130 over three match-ups);
- a deeper reply alone (128 spots, dealing spots only): flat.

What was learned: a split trial (Hydra only when moving first / only when moving second, the house pilot
otherwise) put the gap in MOVING FIRST: 23 - 42 with Hydra's first move, 30 - 38 with Gladiator's. Hydra's
duels ended in 17 turns against 28 for Gladiator v Gladiator: it walked into trades. S5a is still the cure.
One battle in ten or so is about 80 battles' noise here (+/- 6 wins): judge on 3 or more match-ups together.

## 6. Stage S5: play-outs (the plan; nothing built)

Purpose: replace the Mover's weakest guess - "what happens after I move" - with a measurement.

It comes in two parts. **S5a is the one to build first**: it needs no dice, no copy of the battle
and only one small change to the engine. S5b is the heavy version and should wait until S5a's
numbers are in.

### Why two parts
What a unit cannot know when it moves is (i) where everyone who moves after it will go, and (ii) the
dice. For (ii) the Exchange Oracle already gives the exact average, so rolling dice inside a play-out
adds noise and no knowledge (except for kills, falls and critical hits). Nearly all the missing
knowledge is (i). So S5a plays out only the REST OF THE MOVEMENT PHASE and judges the final
positions by expected damage. No dice are drawn, so one play-out per candidate spot is enough.

### S5a: the movement play-out

```
 MOVE QUEUE ---> for each candidate spot of the mover:
 (who moves        POSE the mover there
  after me,        each RESPONDER in queue order picks its answer, POSED in turn
  in order)        POSITION JUDGE prices the final picture
                 -> the spot with the best judged picture wins; POSES are removed
```

- **MOVE QUEUE** - "who moves after me, in what order". In: the turn loop's activation state.
  Out: the units still to move, in the order they will move. This is the one engine change: the turn
  loop publishes the queue (a copy of its activation list) before it asks a unit to move.
  Today that list is a local variable of the turn loop (`forces::Activation` in `play_turn`).
- **POSE** - "assume unit U ends its move here". Sets a unit's position, facing and how it moved,
  remembers what was there, and puts it back afterwards. Nothing else about the unit changes: no
  rolls, no heat, no log lines. Every play-out must leave the battle exactly as it found it; a check
  at the end of each decision (state before = state after, dice drawn = 0) is part of the block.
- **RESPONDER** - the fast pilot for one unit that has not moved. It picks the best of its own short
  list (its top spots from the plain Mover table, made once per decision) against the poses assumed
  so far. It never runs a play-out itself (no recursion). Enemy responders use the same rule from
  their own side: an enemy is assumed to think like Hydra.
- **POSITION JUDGE** - "what is this final picture worth". For the units involved it asks the Oracle
  for expected damage both ways at the final poses, lets each side's Fire Plan choose targets, and
  returns the team's gain and cost. These go into the Mover's existing score. So a play-out changes
  what goes INTO the score, not the score.
- **Budget** - the play-out involves only the mover's neighbourhood: responders that can matter to
  the mover this turn, nearest first, at most N of them (start with N = 3); everyone else stays as
  the Mover treats them today. Candidates: the top K spots, one per hex (start with K = 8, fewer as
  N grows). Target: a 12 v 12 battle no more than twice as slow as today's Hydra.
- This block replaces "the reply" in the Mover (the reply is the special case N = 1, enemy only).
  Friends who move after me are responders too: the unit learns that support will arrive.

Traps to design for (each has bitten the house bots):
- two units may not end in the same hex: a responder's short list must drop hexes already posed;
- a prone unit, a unit entering the board, an immobile unit: fixed, never a responder;
- the pose must carry how the unit moved (walk / run / jump, hexes moved): the Oracle needs it for
  both the to-hit numbers and the heat;
- do not call Legate's or Princess's hooks from inside a play-out (their memories would be changed);
- thinking must never draw from the battle's dice (PROJECT_MAP Section 4, the lookahead-dice issue).

Done when: (1) with no Hydra unit, all 63 fixtures still match exactly; (2) same seed, same result;
(3) the "state before = state after, no dice drawn" check never fires over the whole mirror set;
(4) the mirror table above improves, the brawler duel and the 2 v 2 first; (5) the speed target holds.

### S5b: the dice play-out (later)

For decisions where averages mislead (a charge or death from above, pulling back a crippled unit,
a kill that changes everything) and for looking more than one turn ahead.

- **SNAPSHOT** - a separate copy of the battle that can be played without touching the real one:
  units and everything that changes (smoke, broken crust, limbs), its OWN dice (seeded from the
  decision, never the battle's), log switched off, stubs not counted. The board is shared, not
  copied, until something changes a hex. Today units, board and settings can be copied; the dice
  and the three bots' memories cannot yet.
- **TURN CURSOR** - "where in the turn are we". Today a turn is one long function with its place
  kept in local variables, so it cannot be started in the middle. The cursor holds the turn number,
  the initiative order, who has moved and the phase, and one function advances a battle from a
  cursor to a stopping point. The real battle must run through the same function (one path, so the
  play-out cannot drift from the real rules). Acceptance: the 63 fixtures match exactly.
- **FAST PILOT** - drives every unit inside a snapshot: the plain Mover (no reply, no play-out) and
  the Fire Plan.
- **JUDGE** - the Forecast's margin on the snapshot's Ledger when the play-out stops, minus the
  margin now. One currency again.
- **Same dice for every candidate** - each candidate spot is played with the same set of dice
  seeds, so the spots differ by position and not by luck; far fewer play-outs are needed.
- By-product: every play-out is a finished piece of battle with a known outcome - the data S6
  (self-calibration of the Forecast) needs.

### S5a groundwork (session 25): BUILT; the play-out itself is not

`engine/core/src/playout.rs`, tests `engine/core/tests/playout.rs`:
- **MOVE QUEUE** - `Battle::move_queue` (read with `playout::move_queue`): the turn loop works out, before each unit
  moves, who moves after it and in what order, from a copy of its activation state and the same pick rule (`forces::
  move_index`). A forecast: later picks can change as units move. Its accuracy is not measured yet. Empty outside the
  Movement Phase. Changes nothing: all 79 Rust reference battles and the 63 Python-matched fixtures are as before.
- **POSE** - `playout::Pose` (hex, facing, move mode, hexes moved, MP spent, movement heat, moved flag) and `Poses`, a
  stack: `pose` puts a unit there and remembers what was, `restore` undoes all, last first; `holds_hex` for the
  "two units may not end in one hex" trap; dropping a stack with poses still in place panics. The board is not
  touched, so no cache needs emptying (they are keyed by position).
- **WITNESS** - `playout::Witness`: a record of every unit's state, the dice drawn, the log length and the stub
  counts; `check` panics naming the first difference. On when `HYDRA_CHECK` is set; `tests/check_rust_reference.py`
  always sets it, so every Hydra decision in the reference battles is checked. It now wraps Hydra's move choice
  (`hydra::choose_movement`), except before any enemy is on the board, where Hydra hands the move to Gladiator's
  march and that march's tie-break is a real, seeded random choice. First run: it found exactly that draw; Hydra's own
  thinking is clean in all 7 Hydra reference battles.

S5a ITSELF: BUILT (session 25), as a switch: `HYDRA_PLAYOUT` = "reply" (default, the old reply step) or "s5a"
(`btsim --set HYDRA_PLAYOUT=s5a`; `hydra::playout`). For the mover's top spots (one per hex), the RESPONDERS - units still
to move (the move queue) that can matter, friends and enemies, nearest first, at most 3 - each pick their best answer in
the order they move, from their own reachable spots against their counterpart (an enemy answers the mover; a friend the
weighed enemy nearest it), skipping hexes already taken, and are POSED there. The POSITION JUDGE then reads the picture:
an enemy responder's exchange with the mover from where it ended, and every weighed enemy's "what else it could shoot at"
from the final positions (so a friend arriving near draws fire). Every pose is undone; the witness checks it. Spots:
PLAYOUT_BUDGET 64 shared by the responders (64 in a duel, 21 with three). First cut used 8 spots flat: it won team
battles and lost the Griffin duel (28 - 33, where the reply's 64 spots win 38 - 26); v2 shares the budget.

S5a v2 against the reply (same seeds; Hydra - house bot):

| Match-up | v Gladiator, reply | v Gladiator, S5a | v Princess, reply | v Princess, S5a |
|---|---|---|---|---|
| duel, Griffin | 38 - 26 | 39 - 24 | 71 - 7 | 74 - 4 |
| duel, Hunchback, woods | 29 - 38 | 28 - 37 | 51 - 25 | 54 - 22 |
| duel, Awesome | 42 - 36 | 44 - 35 | 46 - 32 | 49 - 31 |
| 2 v 2 | 34 - 34 | 34 - 36 | 52 - 28 | 51 - 28 |
| 4 v 4 grass | 36 - 33 | 44 - 21 | 56 - 24 | 55 - 25 |
| 4 v 4 woods | 35 - 30 | 37 - 29 | 49 - 30 | 42 - 38 |
| 4 v 4 heavies | 42 - 25 | 50 - 17 | 56 - 24 | 45 - 33 |
| 8 v 8 | 16 - 11 | 14 - 12 | 15 - 13 | 16 - 8 |
| 12 v 12 | 13 - 12 | 19 - 7 | 20 - 11 | 12 - 14 |
| **All nine** | **285 - 245** | **309 - 218** | **416 - 194** | **398 - 203** |

Read: better against Gladiator (most in 4 v 4 and 12 v 12), a little worse against Princess (4 v 4 woods / heavies, 12 v 12);
together 707 - 421 against 701 - 439 for the reply - within the noise. The brawler duel did not move. So the default stays
"reply". Ideas for the next S5a pass: a responder answers only one counterpart (a friend answers one enemy, an enemy only
the mover), so a friend never weighs its own exposure to the other enemies; enemies that cannot reach the mover are not
responders even when they would shift fire onto a friend; the 3-responder cap; and the duel gap is NOT about the reply's
width (S5a with 64 spots is the reply there) - look at charges / DFA (S4) and moving first for the brawler duel.

Earlier plan text, for reference - to build S5a itself: the RESPONDER (each unit in the queue near the mover picks from its own short list
against the poses so far), the POSITION JUDGE (Oracle both ways at the final poses, priced), and the budget N = 3
responders, K = 8 candidate spots; replace the reply step with it; judge on both mirror tables.

## 7. Other later stages (not started)

- **S2 Ghost that moves**: superseded by S5a.
- **S3 Move order**: BUILT session 25 as a switch, `HYDRA_MOVE_ORDER = "stake"` (default off: the engine's index), measured
  level against Gladiator and worse against Princess - see below.

### S3: move order (session 25, 2026-11-12): built, measured, OFF by default

`hydra::move_pick`, asked through a new question on the socket, `BotSet::move_pick` (None = the engine's rule, Princess's
move index). The turn loop asks it for every pick of a side whose candidates are all Hydra's, so the S5a move queue follows
the same order. The rule, LEAST TO LOSE FIRST, DECIDERS LAST: a unit's STAKE is the priced damage that can flow through it
this turn, the sum over enemies on the board of `range_factor`(distance left after its best run or jump) x (enemy guns x
my price + my guns x enemy price); the smallest stake moves first. Guns and prices are worked out once per team per Movement
Phase (`HydraState::order`), from a read-only ledger (`ledger_as`, which does not raise the best guns seen). Same seeds and
battles as S6 (40 a seating, 16 for 8 v 8 / 12 v 12); Hydra - house bot:

| | engine's index | stake |
|---|---|---|
| v Gladiator, nine match-ups | 333 - 203 | 331 - 204 |
| v Princess, nine match-ups | 434 - 174 | 410 - 195 |
| of which v Princess 4 v 4 woods + heavies | 119 - 40 | 100 - 54 |

Duels are identical (one unit a side: no choice). Speed is the same. Why it does not help, as far as the numbers say: the
engine's index already sends the far, slow units first and the close ones last (distance / speed), which is most of the
stake rule; what the stake adds is that Hydra's most valuable units in contact wait longest, and against Princess, which
moves her close units last too, that seems to leave Hydra's best guns reacting to a line she has already set rather than
setting it. Ideas if taken up again: the opposite end (deciders first, to take the good ground), or a pick that asks the
Oracle how much a unit's best spot changes when the enemies still to move have moved (the true worth of waiting).
- **S4 Charges and death from above**: BUILT session 25 as a switch, `HYDRA_MOVEMENT_ATTACKS` (default off), measured
  level - see below.

### S4: charges and death from above (session 25, 2026-11-12): built, measured level, OFF by default

`hydra::movement_attack`. Against every weighed enemy that has finished moving (or cannot move; Core pp.78-79 - so only
when Hydra moves after it), every charge and DFA stop (`move_attacks::MoverIndex`, Gladiator's list) is priced as a spot:
the target's line is the attack's expected damage both ways (`move_attacks::values`: hit chance, damage, self-damage, a
missed DFA's fall, displacement) plus the ranged exchange from the attack hex; every other weighed enemy's line is the
Oracle's at the attack hex; risk is the move's PSR cost. It is taken when its rate beats the best ordinary spot. A stop on a
hex another unit stands in is skipped (the first trial crashed on one: Gladiator's stop list does not look at other units).
Results (same seeds, 40 battles a seating, 16 for 8 v 8 / 12 v 12; Hydra - house bot):

| | without | with S4 |
|---|---|---|
| v Gladiator, nine match-ups | 285 - 245 | 291 - 244 |
| v Princess, nine match-ups | 416 - 194 | 407 - 202 |
| of which v Princess 8 v 8 + 12 v 12 | 35 - 24 | 28 - 30 |

The three duels v Gladiator came out identical: Hydra found no attack worth it there (the Hunchback cannot jump; a charge
at 58% for 10 damage loses to standing and shooting), so the brawler-duel gap is not about charges. In team battles it
charges (the lance, the 4 v 4s), with no gain, and the big battles v Princess got worse. Likely why: an attack is scored
against the enemies as they stand (ghosts), never against the reply / play-out, so walking into contact in a crowd is
under-priced. If S4 is taken up again: score the attack spot through the same reply or play-out as the other spots.
- **S6 Self-calibration**: DONE session 25 (first pass) - see below. The Forecast now assumes spread fire (FOCUS 0).

### S6: calibrating the Forecast (session 25, 2026-11-12): DONE, first pass; FOCUS 0 is now the default

Tools: `btsim --ledger FILE` (`scenario::run_recorded`: every unit's raw life and guns at the end of every turn and at the
end; recording only reads - five batches identical with and without it) and `tools/hydra_calibrate.py` (`collect`: the nine
mirror match-ups x Hydra v Gladiator / v Princess both seats, Hydra v Hydra, Gladiator v Gladiator, Princess v Princess,
20 battles a seating, 8 for the big two, seed 11 - 1,092 battles; `fit`: the Forecast re-written in Python with three
settings, scored against how each battle really ended). The OUTCOME is measured with the snapshot's guns held fixed,
(Red's life at the end x guns - Blue's) / (the same with life at the snapshot), so it does not depend on what is fitted.
The settings (`hydra::Shape`, `HYDRA_FORECAST_FOCUS` / `_FADE` / `_STEP`): FOCUS = share of fire poured in kill order, the
rest spread in proportion to life; FADE = guns shrink with life; STEP = fire per step.

What the data says (8,334 snapshots, every 3rd turn):
- The first version is already sound: correlation 0.81 with the real margin, scale right (real = 0.98 x predicted), and
  the predicted leader wins 93% of battles when it predicts a margin over 0.35, 78% at 0.2 - 0.35.
- Over all sizes the shape hardly matters (error 0.0798 - 0.0808 for every FOCUS / STEP); FADE only made it worse.
- By size it does: in DUELS it under-predicts swings (x 1.15; focus cannot matter, one target); with 9+ UNITS ALIVE it is
  over-confident (real = 0.74 x predicted; right about the winner 66%) and SPREAD FIRE fits 20% better (error 0.040 v 0.050
  for perfect focus).
- In battle (same seeds as the earlier tables, NOT the fitting seeds), FOCUS 0 v the first version's FOCUS 1:

| Match-up | v Gladiator | v Princess |
|---|---|---|
| 2 v 2 | 34 - 34 -> 38 - 26 | 52 - 28 -> 61 - 19 |
| 4 v 4 grass | 36 - 33 -> 43 - 27 | 56 - 24 -> 51 - 29 |
| 4 v 4 woods | 35 - 30 -> 38 - 24 | 49 - 30 -> 52 - 27 |
| 4 v 4 heavies | 42 - 25 -> 69 - 7 | 56 - 24 -> 67 - 13 |
| 8 v 8 | 16 - 11 -> 18 - 10 | 15 - 13 -> 20 - 10 |
| 12 v 12 | 13 - 12 -> 18 - 9 | 20 - 11 -> 15 - 12 |
| all six | 176 - 145 -> 224 - 103 | 248 - 130 -> 266 - 110 |

  The three duels are identical either way (checked on both house bots). So FOCUS 0 is the default (`Shape::CALIBRATED`).
  Why it plays better, a guess to check: with perfect focus the prices pile onto the one enemy next in kill order, so
  Hydra over-commits to a single kill; spread fire prices the whole enemy line more evenly and Hydra trades better.
- Left for a second pass: the duel's under-prediction (x 1.15), a size-dependent shape, the inputs themselves (`guns` =
  `future_damage`, `life` = armor + weighted structure), and re-fitting on battles played by the calibrated Hydra.

### S6 second pass (session 25, 2026-11-12): no change to the defaults

Re-collected 1,092 battles with the CALIBRATED Hydra (seed 12; the ledger now also records each unit's raw armor and
structure) and fitted with `tools/hydra_calibrate.py fit2`, scored by log-loss on who really won (a measure that does not
depend on the structure weight being fitted; the margin measure does).
- SPREAD FIRE CONFIRMED on the fresh data, most in big battles (9+ alive: MSE 0.038 spread v 0.044 focused).
- FIRE SPREAD BY SIZE (a separate FOCUS for 8 units or fewer and for more): no gain over FOCUS 0 everywhere.
- STRUCTURE WEIGHT in life (`HYDRA_LIFE_STRUCTURE_WEIGHT`, new, Hydra only; without it Gladiator's
  `MOVEMENT_STRUCTURE_WEIGHT` 2 as before): 1 predicts a little better than 2 in both size groups (log-loss 0.4778 v 0.4802
  overall). In battle (seed 1, all nine match-ups): v Gladiator 333 - 203 (weight 2) v 330 - 216 (weight 1), v Princess
  434 - 174 v 442 - 165: flat. Default stays 2 (Daniel's weight); the setting stays for later.
- THE DUEL GAP needs no fix: in a duel Hydra compares two prices scaled to a mean of 1, so scaling the forecast up or
  down cannot change a choice.
- So the Forecast's FORM is now as good as this family of models gets: what is left is noise from the dice and from
  what the ledger cannot see (position, heat, ammo). A better Forecast would need new inputs (e.g. guns by range, or
  ammo left), not new constants.
- **Waiting**: BUILT session 25 as a switch, `HYDRA_WAITING` (default off), measured level - see below.
- **Attention share**: BUILT session 25 as a switch, `HYDRA_ATTENTION = "oracle"` (default off: the range rule), level
  overall, better in the two big battles - see below.

### Waiting and Attention share (session 25, 2026-11-12): built, measured, both OFF by default

WAITING (`HYDRA_WAITING`, in `choose_movement_inner` after the reply): when the best trade's rate is below the team's
typical turn (d0 / r0) and a friend is still COMING, the unit may take a spot that deals nothing, scored like any other
spot, (d0 + 0) / (r0 + cost + risk); it wins only where no weighed enemy can punish much. Ties: nearest a coming friend.
At most `MAX_WAITS` = 2 turns in a row (`HydraState::waited`), so the battle is still fought. COMING (`coming_friends`): not
on the board yet, or able to move and at least `BEHIND` = 3 hexes further from its nearest enemy than the mover is - the
mover is out ahead of its line. The first definition (a friend out of every enemy's reach) never held in the mirror
match-ups, where both forces enter together. It fires a few times a battle in a 4 v 4, a dozen or more in 8 v 8.

ATTENTION SHARE (`HYDRA_ATTENTION = "oracle"`, `elsewhere_of` / `attention_damage`): "what else could this enemy shoot
at" is the Oracle's expected damage of the enemy on each friend as both stand (enemy as a ghost if unmoved), x the friend's
price, the most over friends; in place of guns x `range_factor`. Used by the Mover's cost and by the S5a position judge.

Same seeds and battles as S3 (40 a seating, 16 for 8 v 8 / 12 v 12); Hydra - house bot:

| | first version | Waiting | Attention (Oracle) |
|---|---|---|---|
| v Gladiator, nine match-ups | 333 - 203 | 335 - 195 | 329 - 213 |
| v Princess, nine match-ups | 434 - 174 | 426 - 179 | 441 - 165 |
| of which 8 v 8 + 12 v 12, both opponents | 71 - 41 | 65 - 44 | 80 - 31 |
| of which 2 v 2 + 4 v 4, both opponents | 419 - 172 | 422 - 166 | 413 - 187 |

Duels identical (no friend: neither can act). Waiting is noise everywhere. Attention is level overall but splits by size:
better in both big battles against both bots, worse in the 4 v 4s against Gladiator (heavies 69 - 7 -> 56 - 14). The big
battles are 64 battles a cell, so the gain is a hint, not a result; a confirming run of the big two on fresh seeds would
settle whether to turn it on for big battles only. Cost: about 10-20% more time a battle in 8 v 8 / 12 v 12.

### All five together (session 25, 2026-11-12): ON BY DEFAULT

Daniel: "turn on all the features Fable wanted at once ... I suspect that individually they're suffering diminishing
returns. Their value would be in edge cases." With all five on (S5a play-out, S4 charges / DFA, S3 move order, Waiting,
Oracle attention) at the old 50-turn cap, Hydra lost less but many battles stalled (8 v 8 / 12 v 12 about 40% no winner,
41 turns on average against 33). Played on to 150 turns (Daniel: "take the draws and play them out"), same seeds, 40
battles a seating, 16 for 8 v 8 / 12 v 12; Hydra - house bot - no winner:

| | first version | all five on |
|---|---|---|
| v Gladiator, nine match-ups | 369 - 243 - 12 | 397 - 219 - 8 |
| v Princess, nine match-ups | 438 - 176 - 10 | 447 - 161 - 16 |
| of which 8 v 8 + 12 v 12, both opponents | 75 - 47 | 86 - 30 |
| of which 4 v 4 lance woods v Gladiator | 46 - 30 | 61 - 19 |
| of which 4 v 4 heavies v Princess | 67 - 13 | 59 - 21 (worse in every test of these switches) |

About three standard deviations better against Gladiator, one against Princess; duels level (the Hunchback duel v
Gladiator is still lost, 33 - 47). So the stalls at 50 turns were mostly Hydra wins still being ground out. Daniel:
"cheap runs against inferior opponents means you learn nothing. Leave them all on. Set the standard game cap to 100
rounds." DEFAULTS now: all five on (each turned off by its OFF value, listed at the top of `hydra.rs`), and the Rust
engine's turn cap is 100 (`scenario::STANDARD_MAX_TURNS`). Cost: a big battle takes about 2.5 times the computer time
(12 v 12 about 17-19 s a battle on 2 threads, against 7) and runs longer (45 - 75 turns on average). Records:
`trial_records/2026-11-12_hydra_trial_*cap150_big.jsonl` (the small match-ups were run before records existed).

### The two weak spots, 400 battles each (session 25, 2026-11-12): flukes

Daniel: "Cast a wider net for both the hunchback and the heavies. Maybe 400 games each. Lets rule out fluke." Fresh seeds
(101), 200 a seating, Hydra - house bot - no winner:

| | first version (all five off) | all five on |
|---|---|---|
| Hunchback duel in woods v Gladiator | 182 - 195 - 23 | 190 - 187 - 23 |
| 4 v 4 heavies on hills v Princess | 279 - 118 - 3 | 282 - 116 - 2 |

The Hunchback duel is even (the 80-battle 29 - 38 and 33 - 47 were the seeds), and the switches did not hurt the heavies
(67 - 13 -> 59 - 21 was the seeds). The first run of the first version crashed on battle 8: a rule gap in the engine, not
Hydra (RULES_REVIEW F-list: a walking fall in a hex holding an immobile 'Mech). Records:
`trial_records/2026-11-12_hydra_trial_wide_*.jsonl`.

### The map edge (session 28, 2026-11-17): built, ALWAYS ON (no switch; Daniel the same day: "mandatory ... with no way to turn it off")

Reopened by Daniel ("you are allowed to fix your bot and update Hydra") after the WHM-6R v JVN-10F study: a third of the Hydra
Warhammer's losses were a Javelin CHARGING it off the map (a 'Mech displaced off the battlefield is destroyed, Core p.113). The
Mover priced an adjacent enemy's push (through Gladiator's evaluator) but not an enemy that has still to move charging or
jumping on it. `hydra::edge_risk`: for each spot, the best hit chance of any unmoved enemy that can reach (in hexes, terrain
ignored) a neighbour from which the charge / DFA push leads off the board (piloting + 2 running, + 3 jumping, + the spot's
TMM); that chance times the unit's whole remaining armor + structure, priced, is added to the spot's risk. WHM v JVN, 100
battles a seating, same seeds: Hydra Warhammer v Gladiator Javelin 73 -> 82 wins, off-the-map losses 9 -> 0; v Hydra
Javelin 68 -> 70, 10 -> 0; the other seatings within noise. Team battles: see the Change Record entry of 2026-11-17.

### The new rules (2026-11-21): C3, spotting, distant artillery
Daniel: "Update Hydra to incorporate the new rules." What the rules added on 2026-11-20 (backlog N1-N10) meant for Hydra:
- **Already seen, nothing to do:** the FIRE PLAN prices shots with the engine's own dry declaration, so C3's shorter range,
  the special rounds (armor-piercing, precision, caseless, semi-guided) and the Narc homing ammo are in it. The partial
  cover leg discount (N8) is in the shared evaluator for Gladiator and Hydra. Per-team settings (N5) carry Hydra's switches.
- **C3 in the MOVER (built):** the evaluator read the range from the unit's own hex only, so a C3 unit's spots were priced
  as if it had no network. `MoveEvaluator::with_c3` (Hydra's evaluators only) takes each side's network partners
  (`c3::Partners`, where they stand now) and, per hex, the closest partner that would see the target: the mover's shots
  use it against the defender, and the defender's shots use its partners' distance to each hex the mover might take.
  The Adjuster applies the rule as for a real attack (only a better bracket counts; +1 a bracket in hostile ECM).
- **SPOTTING (built, Hydra's own):** one plan a team a phase, like the fire plan (`plan_spots`). A spot is worth the
  spotter's best priced shot with the +1 (nothing if it holds fire) less its shot now, plus, for each Hydra friend with
  no line of sight, how much better its indirect shot on the spotted enemy is than its best shot now. The best spot is
  taken, the shots updated, and the next sought while one gains over 1% of the spotter's shot. A first version decided
  unit by unit and had one unit hold its fire to spot a target a second then spotted better; the team plan fixes that.
- **DISTANT ARTILLERY (borrowed):** Hydra uses Princess's aim (MegaMek's ArtilleryTargetingControl, `princess_artillery`):
  it reads no Princess setting, and Hydra borrows tools as it borrows Gladiator's. Before, Hydra never fired a distant shot.
- **Left as they are:** AMS stays on (the rulebook's default; MegaMek's on / off switch is a Princess habit, and only a
  laser AMS's heat costs anything); no ammunition conservation (the fire plan prices each shot now; Princess's rule is
  MegaMek's taste). The MOVER still does not plan for indirect fire or for spotting positions (the `indirect_unplanned`
  stub counts each indirect shot).
- **Results** (20 battles a setting, same seeds, Red = Hydra v Gladiator; old = main before this): C3 lance (Cyclops C3
  Master, Hatamoto-Chi, Centurion CN9-D5, Clint 5U v Atlas AS7-K, Awesome, Archer, Cataphract; Hilltops) old 13-7, new
  12-8; LRM lance (Archer, Catapult, Bombardier, Jenner v Awesome, Cataphract, Griffin, Dervish; Scattered Woods) old
  6-14, new 5-15; Arrow IV lance (Patriot, Legionnaire, Hermes II v Hunchback, Griffin, Jenner; Caustic Valley) seeds 1-20
  old 17-1 (2 draws), new 14-3 (3); seeds 21-60 old 24-11 (5), new 31-7 (2). All within noise; speed unchanged.

### The new rules, second pass (2026-11-21, same day): from the desired outcome, measured by behaviour
Daniel on the first pass: "you got hydra working, but you didn't really think about how you would solve the 'how would i
program the desired outcome'... Hydra is yours. Its performance reflects on you." He was right: the first pass plugged each
rule into the nearest hook and called "within noise" fine, when noise meant the features did nothing. The second pass
started from what a good commander does with each rule, and measured whether Hydra now does it.
- **C3: measure first.** Priced with and without the network, Hydra's own C3 lance's planned shots gained only +3% / +6% /
  +3% / +0% (1,143 shots): Hydra fights close, so a partner rarely improves the bracket. So the network goes into the
  LEDGER as a measured bonus (`c3_gain`: each networked unit's own running tally, with a 4% prior worth 50 points of
  damage; the prior also stands for enemy networks), kept apart in `Entry.net` so the FORECAST can take it away: a Slave
  keeps its bonus in proportion to its Master's life left against the Master's full life (`net_loss`; the calibrated
  Forecast spreads fire by life, so every unit of a side falls in the same step and a hard "Master destroyed" would never
  single the Master out), and loses it all with no partner left. Unit test: a Master is priced above its Slaves in both
  Forecast shapes. In play the effect is small, as the measurement says it should be (Hydra's fire on an enemy C3 Master
  15% -> 14%; wins within noise over 120 battles). C3's real value would come from standing off while a partner holds
  line of sight; on 16x17 boards Hydra seldom gets there.
- **Indirect fire in the MOVER (`indirect_exchange`).** The evaluator priced direct fire only: a hex with no line of
  sight to an enemy read 0 dealt, 0 received, so a hidden LRM boat did nothing and hiding was perfectly safe. Now a hidden
  hex deals the mover's indirect weapons if a friend sees the enemy (that friend's spotting modifiers), receives the
  enemy's indirect weapons if one of its friends sees the hex, and a hex that sees an enemy no friend sees gains the
  indirect damage its line would open for the hidden friends (a friend that sees no enemy). The damage is
  `move_select::IndirectProfile` with the move's own movement modifiers (a first try used the lifetime figures - the
  attacker running, the target's best TMM - and on top of the indirect modifiers that left about a tenth of the damage).
- **Two bugs the behaviour trials found.** (1) Arrow IV has no range brackets in the equipment table, so the spotting
  check never counted an Arrow IV carrier as a friend to spot for: Hydra hid its Arrow IV units for spots that never came
  (0 spots, 0 indirect shots; damage ratio 1.59 -> 1.28). `spotting::reaches_indirectly` gives artillery its reach with a
  spotter (under 18 hexes). (2) The closing move read range from every weapon, empty launchers included: an Archer with
  its LRMs spent "was in range" at 15 hexes and never closed to its lasers (two weaponless survivors, 50 turns). Fixed for
  every bot at Daniel's word ("If gladiator is pricing weapons that cant actually fire, please fix that too"):
  `move_select::weapon_ranges` / `max_range` count only weapons that can fire; Princess keeps MegaMek's own reading
  (`max_range_megamek`: jammed out, empty launchers in, as MegaMek's `isReady`).
- **Artillery aim: tried, measured, not kept.** Hydra's own aim (MegaMek's candidate hexes, each unit at Hydra's price,
  fire whenever positive) fired five times as often, hit less and did worse (80 battles: damage ratio 1.28 / 1.57 v
  1.87 / 1.82 with MegaMek's aim). MegaMek's "two enemies together" rule keeps rounds for better shots; Hydra has no value
  for a round of ammunition. Hydra keeps MegaMek's aim. NEXT: a value for a round (its expected use later), which the
  same evidence says Hydra's indirect LRM plinking needs too.
- **Results (behaviour, then wins; Red = Hydra v Gladiator, same seeds, first pass v second):**
  - LRM lance (Archer, Catapult, Bombardier, Jenner), 20 battles a board: indirect share of Red's attacks 2% -> 5% /
    3% -> 3% / 2% -> 7% (Desert Hills / Hilltops / Scattered Woods); wins 6-14 -> 6-14, 1-18 -> 6-14, 5-15 -> 3-15;
    damage ratio 0.84 -> 0.89, 0.69 -> 0.92, 0.93 -> 0.84. In one battle the Archer did as intended for its first turns:
    out of every enemy's sight, fired its LRMs indirectly at TN 7-8 through a friend's spot, taking no fire.
  - Arrow IV lance (Patriot, Legionnaire, Hermes II v Hunchback, Griffin, Jenner), 40 battles: spots 0 -> 104, indirect
    shots 0 -> 115; wins 28-8 -> 29-5; damage ratio 1.59 -> 1.87.
  - The standard match-ups, 40 new seeds each (lance woods, heavy hills, 8v8 valley, 2v2 grass): 98-49 (13 draws) ->
    104-47 (9); 8v8 valley the one that slipped (21-11 -> 19-17).
  - Left open: units hidden for a spot that does not come (the Arrow IV lance held fire hidden 796 times in 40
    battles); a lone corner Archer and two Blue 'Mechs trading lasers at 9 hexes until the cap (both bots holding back).

## 8. Status

**COMPLETE (Daniel, 2026-11-12: "I think this concludes building Hydra").** Defaults: all five switches on (Section 7,
"All five together"); turn cap 100. What a later look could still take up: new Forecast inputs (guns by range, ammo
left), S4 scored through the play-out, the move order's opposite end; none is planned.

**STILL TO IMPROVE (2026-11-21, after the new rules' second pass; the same list is PROJECT_MAP Section 0 "H"):** H1 a value
for a round of ammunition (first); H2 hiding for a spot that never comes; H3 C3 standoff (long guns back, a partner forward);
H4 stalemates at the turn cap when outnumbered; H5 the 8v8 valley slip; H6 small things (coarse Forecast step, unmoved
enemy at a walk, a second spotter worth nothing). H7 RAC unjamming (today the shared stub always tries, and the walk-only limit
is set before Hydra plans; to be priced against the move it costs).

| Block | State |
|---|---|
| Plan (this file) | written 2026-11-11 |
| Ledger, Forecast, Prices | built, first version (`engine/core/src/hydra.rs`) |
| Mover (score, reply) | built; the reply is to be replaced by S5a |
| Fire Plan | built |
| Trial tools | `tools/hydra_scenarios.py`, `tools/hydra_trial.py` |
| S5a groundwork: move queue, pose, witness | built, session 25 (`playout.rs`) |
| S5a movement play-out (responder, judge) | built, switch `HYDRA_PLAYOUT`, ON by default since 2026-11-12 (off: "reply") |
| S4 charges / DFA | built, switch `HYDRA_MOVEMENT_ATTACKS`, ON by default since 2026-11-12 |
| S3 move order, Waiting, Attention share | built, switches `HYDRA_MOVE_ORDER` / `HYDRA_WAITING` / `HYDRA_ATTENTION`, ON by default since 2026-11-12 |
| S6 calibration | done, two passes: `btsim --ledger`, `tools/hydra_calibrate.py` (fit, fit2); FOCUS 0 by default; structure weight tested, kept at 2 |
| Section 7 (Fable's list) | all built; the two weak spots were flukes (400-battle check below) |
| Map edge (Section 7, 2026-11-17) | built, always on (the `HYDRA_EDGE_RISK` switch was removed the same day, Daniel) |
