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
- **The score** of a spot = gain - resolve x (cost + risk). Prices already put both sides' damage on
  one scale, so at resolve 1 the score asks "does this trade move the forecast my way".
- **Resolve.** When the Forecast says my team is losing, resolve drops below 1 (down to 0.25): a
  losing side that waits only loses later, so it takes the trades that hurt the enemy most ("sell
  dearly") instead of stalling to the turn limit.
- Tried and dropped (2026-11-11, keep for the record): scoring by the rate dealt / received. It
  cured stalling but made Hydra too picky in an even fight; an agile mirror duel went 19 to 54
  against Gladiator. With the score above the same duel is 30 to 35.
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

## 5. Later stages (not started)

- **S2 Ghost that moves**: the Ghost pose learns where an unmoved enemy is likely to go (a few
  candidate positions weighted by the enemy's own best score) instead of "stays near".
- **S3 Move order**: Hydra chooses which of its units moves next (least to lose first, deciders
  last). Needs a new question on the `BotSet` socket.
- **S4 Charges and death from above** in the Mover (today Hydra never declares them).
- **S5 Play-outs**: for the top few positions of a deciding unit, copy the battle and play the turn
  forward in the real engine with Hydra itself as the fast pilot; pick by the average. Needs a way to
  copy a battle.
- **S6 Self-calibration**: fit the Forecast's few constants from thousands of finished battles, so its
  margin matches what really happens.

## 6. Status

| Block | State |
|---|---|
| Plan (this file) | written 2026-11-11 |
| Ledger, Forecast, Prices | see the Change Record |
| Mover | see the Change Record |
| Fire Plan | see the Change Record |
| Results v Gladiator / Princess | see the Change Record |
