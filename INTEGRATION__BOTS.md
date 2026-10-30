# How the two bots work (2026-10-30, end of session 15)

Written for Daniel and the next session: what Gladiator (this project's bot)
does now, and what Princess (the MegaMek clone) does differently. The details
and every setting are in PROJECT_MAP Section 6; the history is in the Change
Record (Section 8). Where the numbers below come from: the 20-battle 12 v 12
battery (Princess Red v Gladiator Blue, stitched 2 x 1 field, seed 12345, cap 50
turns).

## A turn, and who decides what

The rules engine runs the turn (Core Rulebook order). At each decision it asks
the unit's bot (`INTEGRATION__bots`):

| Decision | Gladiator | Princess |
|---|---|---|
| Which unit of a side moves next | Princess's move index (far, slow units first; fast units near the enemy last) | same |
| Where to move | Its own search and score (below) | MegaMek's path ranker (below) |
| Whom to shoot | Fire director (`kill_curve`) or a stand-in (below) | Best firing plan, team damage map counted |
| Which weapons | Heat-limited choice of the most expected damage | MegaMek's firing-plan utility |
| Which unit declares fire first | Big guns first | Roster order |
| Physical attack | Most expected worth (punch / kick / club / push...) | MegaMek's PhysicalCalculator |
| Rate of fire, ammo kind, MASC, shields... | Shared stubs (placeholders) | same stubs |

## Gladiator

**Movement: one score for every spot it could end in.** The "lifetime"
objective (Daniel, 2026-10-20):

    score = damage dealt now
          + (my HP left after this turn / the damage the enemy deals me a turn)
            x the damage I deal a turn

That is "damage I deal now plus damage I'll deal in the rest of my life". HP
counts structure double (`MOVEMENT_STRUCTURE_WEIGHT`), damage on a side is
weighted by how thin the armor there is (exposure), and a run or jump that
forces a piloting roll pays its expected fall damage. The rates come from
`future_damage` (heat-limited expected damage, target at its best TMM) blended
with what has actually happened so far in the battle.

Which spots get scored: the Short Grid search (a 1-in-7 net of hexes, then
uphill from the best). The unit that moves first scores each spot by the reply
the enemy would actually make to it (two-ply).

**Legate (on by default in team battles).** At the start of each Movement
Phase it runs an IF/THEN estimate of where every unit on both sides will move
(each side answers the other, a few rounds). Then each Gladiator scores its
spots against the WHOLE enemy force at those estimated spots: damage dealt is
the best single target; damage taken adds up over the enemies, each enemy's
damage times the share of its fire this unit can expect to draw (its slice of
what that enemy could deal across the team - the fire split, default since
session 15, for this turn and the "damage the enemy deals me a turn" above
alike). Off by default: herding, cohesion, team value, exchange (below).

**Whom to shoot: the fire director** (`STUB_GLADIATOR_TARGET = "kill_curve"`,
built 2026-10-29). Each enemy has a kill curve: the chance it is
mission-killed by N more points of damage, from its current state and on the
side being hit. The curve is worked out with 100 quick trials of 5-point
groups through the engine's own damage code, so criticals, ammo explosions and
head hits are all in it. A Gladiator then scores each enemy as

    its damage a turn x ( kill chance added by my expected damage on top of
                          what my teammates already declared at it
                        + the share of a kill my useful damage pays )

Two 60% kills beat one sure kill and a graze, and softening a fresh enemy still
counts. Overkill earns nothing. Expected damage uses the real to-hit numbers.
"Mission kill" is a stub (`STUB_MISSION_KILL`): today "destroyed" (a gunless
'Mech that can still move or spot is still in the fight; spotting has no worth
yet).

**Firing order: big guns first** (`GLADIATOR_FIRE_ORDER`, Daniel's rule): in
each of its side's turns to declare, the Gladiator with the most expected
damage goes first, and smaller guns fill in around it.

**Weapons:** the most expected damage the heat budget allows (`max_heat` over
what the sinks shed), with torso twist / arm flips, and the punch or kick that
can follow at range 1.

The default target choice is still the stub that borrows Princess's choice
(`"princess_plan"`); the fire director is an option until it beats the stub.

## Princess (MegaMek clone)

Cloned from MegaMek's source (modern = main at fd2edfb; v0.50.07 kept as an
option), with this project's rules engine underneath.

**Movement: MegaMek's BasicPathRanker.** Every legal path is scored by
expected damage dealt minus expected damage taken (weighted by "bravery"), a
pull toward the enemy ("aggression"), facing toward the enemies, fall risk
("fall shame") and hazards. In a team battle it also has:

- **Mutual support ("herd mentality")**: a pull toward the force's hot spot
  (a heat map of where the force has been, weighted by Battle Value) or the
  friends' average position. This keeps Princess's units together.
- **The force's posture**: ATTACK, or DEFEND while the enemy keeps closing.
- Damage taken counted from every enemy, but only at its present spot (no
  IF/THEN estimate of where they will go).

**Whom to shoot:** each unit, in turn, takes the enemy its best firing plan
rates highest, with the damage its teammates already declared counted (an
enemy they are expected to destroy scores badly). The firing-plan utility is
expected damage + critical chance + kill chance - overheating.

## What actually differs, and what the battles show

Same 20 seeds, Gladiator with Legate (session 14):

| Gladiator's target choice | Princess wins / draws / Gladiator wins | 'Mechs left, Princess / Gladiator |
|---|---|---|
| "Shoot the nearest" (before session 14) | 15 / 5 / 0 | 5.6 / 0.35 |
| Princess's choice borrowed (stub, default) | 7 / 9 / 4 | 3.2 / 1.8 |
| Fire director, list-order firing | 15 / 5 / 0 | 4.6 / 0.7 |
| Fire director + big guns first | 9 / 8 / 3 | 4.3 / 1.3 |

Big guns first is what made the fire director work at all; with it, the fire
director is about level with the borrowed choice (20 battles can't separate
them). Target choice is not what is losing the battles:

1. **Gladiator's light 'Mechs dive in alone on turn 2 and die.** In the fire
   director + big guns run Gladiator lost 53 units in turns 1-6 across the 20
   battles, Princess 29. 46 of Gladiator's 53 were its lights (Jenner,
   Commando, Hunchback, Kintaro, Locust); 46 were closer to the enemy than
   most of their team, and 44 had at most one friend within 4 hexes.
   On turn 1 they behave (they stay back with the group); the dive is on turn
   2, with every enemy in view.
2. **Why the movement score allows it:** under Legate a Gladiator's "life
   left" is its HP divided by ALL enemies' damage a turn - as if every enemy
   shot only it, every turn. Against 12 enemies that is about 3 turns, so its
   HP is worth little and trading 50 points taken for 10 dealt scores well
   (example: Blue Jenner, battle 18, turn 3). In fact the enemy's fire is
   shared over 12 targets - until one unit runs ahead alone, and then it gets
   all of it. Defeated in detail, one light at a time.
3. **No "stay together" pull.** Princess's mutual support keeps its force
   together; Gladiator has none. Its heavies, which move first on turn 1 when
   only about 2 enemies are on the board, end 6.4 hexes from their nearest
   friend (Princess's 4.2), and further back from the enemy (17.8 v 15.4).
   Over turns 1-20 Gladiator's units are always a little more spread out.
4. Fewer Gladiators fire after the first turns (4.8 a turn in turns 11-20 v
   Princess's 5.6), following the losses.

## Team awareness (built later on 2026-10-29, all options, off by default)

Daniel's designs, in Legate, each a switch in `INTEGRATION__config.py`:

- **Fire split** (`LEGATE_FIRE_SPLIT`): a unit's life-left estimate shares each
  enemy's future fire over the team it can reach, instead of "every enemy
  shoots only me".
- **Herding** (`LEGATE_HERDING`): a spot an enemy can reach costs extra for each
  hex it lies beyond every teammate's support (a teammate's medium range, long
  if it stands still, and only if it can see one of those enemies).
- **Team value** (`LEGATE_TEAM_VALUE`): the enemy's fire this turn is
  distributed over the whole team (each enemy at the unit it hurts most, not
  already doomed) with the mover at the spot being scored, and the move is worth
  the team's future damage (each unit's life-left term times its kill-curve
  chance of surviving the turn; or Daniel's product form).
- **Exchange** (`LEGATE_TEAM_EXCHANGE`, with a team value): our fire is
  distributed over the enemy the same way, and the enemy's future damage it
  removes counts too ("some of us may die, but that's a sacrifice I'm willing to
  make").

Results, same 20 seeds (Princess wins / draws / Gladiator wins):

| Setting | Result | 'Mechs left, Princess / Gladiator |
|---|---|---|
| Baseline (target stub + big guns first) | 8 / 8 / 4 | 3.3 / 1.9 |
| Fire split | 4 / 16 / 0 | 5.55 / 3.35 |
| Herding | 8 / 8 / 4 | 3.25 / 2.0 |
| Split + herding | 1 / 19 / 0 | 5.3 / 3.25 |
| + team value "sum" | 12 / 4 / 4 | 4.45 / 1.5 |
| + team value "product" | 17 / 3 / 0 | 5.75 / 0.45 |
| + "sum" + exchange | 18 / 1 / 1 | 5.4 / 0.25 |

The fire split stops the light 'Mechs' suicide dives, but then both sides
stall. The team value and the exchange make Gladiator aggressive again, and it
over-commits: each unit plans as if its teammates stand where Legate estimated
and draw the fire (or finish its kills), and all of them do that at once. That
coordination problem is the next thing to look at.

## Diagnosis (session 15, 2026-10-30): Daniel's five suspects, measured

`tests/legate_probe.py` (report: `tests/legate_probe_report.py`) runs the battery with probes. It
re-scores every Gladiator move with the enemies where they REALLY ended, so an estimate error is
priced in damage and in score points, not just hexes. On the baseline:

| Suspect | Finding |
|---|---|
| IF/THEN estimate leads units astray | Off 2.7 hexes (worse than "everyone stands still", 2.0) but closer in damage (4.5 v 5.4 points a move); picks within 2.5% of the best in hindsight. Replacing it with "stands still": 11 / 5 / 4, no better. **Not the cause.** |
| Moving off the wrong unit | The primary foe fires at the mover 45% of the time, ~1/3 of the predicted damage. **Small.** |
| Weights | Not swept. |
| Systemic error | **Found.** Every enemy in reach counted as shooting the mover this turn: 4.8 a move, 1.1 really did. The fire split shared only future fire, so HP grew dearer while this turn stayed ~4x too high - the stall. Also: Gladiator's own damage is rated ~25% high (incoming is right). |
| Cohesion | **Confirmed.** Units with no friend within 4 hexes: 19 / 26 / 47% (turns 1-3 / 4-10 / 11+) v Princess 9 / 12 / 22%. Herding barely moves it. |

| Setting (20 battles) | Princess wins / draws / Gladiator wins | 'Mechs left, P / G |
|---|---|---|
| Old baseline | 8 / 8 / 4 | 3.3 / 1.9 |
| Estimate replaced by "stands still" | 11 / 5 / 4 | 3.9 / 1.3 |
| **Fire split, this turn too (now default)** | **8 / 4 / 8** | **2.65 / 2.1** |
| + herding | 9 / 4 / 7 | 3.1 / 2.25 |

## Cohesion reward (session 15 cont., off by default)

`LEGATE_COHESION` (Daniel's design): each ally whose short / medium / long bracket covers a spot makes
it worth 2 / 1 / 0.25 damage points, mutual support 1 more. Options: count only the best 3 allies;
no support needed where no enemy reaches; "either" pairing (whichever of the two covers the other, so a
fire-support unit behind a brawler is in position too). Same 20 seeds:

| Setting | Princess / draws / Gladiator | 'Mechs left P / G | Gladiator alone, turns 11+ |
|---|---|---|---|
| No cohesion (default) | 8 / 4 / 8 | 2.65 / 2.1 | 45% |
| "ally" x0.5 / x1 / x2 | 9/6/5, 11/4/5, 12/5/3 | 3.65/2.15, 4.2/1.5, 3.65/1.4 | 10%, 6%, 4% |
| "either", 3 allies, threatened only, x0.5 | 8 / 6 / 6 | 2.8 / 1.95 | 20% (Princess 21%) |
| same, x1 | 13 / 4 / 3 | 4.35 / 1.4 | 16% |

It groups the force as intended, but no setting beats none.

## Next steps (PROJECT_MAP "Pick up here" 00000 and 0000)

- Why grouping doesn't win: the cohesion reward matches Princess's spread but
  not her results - check with `tests/legate_probe.py` whether moves spent on
  cohesion cost firing spots (damage dealt, regret).
- Gladiator rates its own damage ~25% high (incoming is right): find where the
  movement model and the fire phase's dry run part.
- Re-test team value / exchange on the new fire-split default (they were built
  on the old over-count).
- Movement order hierarchy; active choices in one currency; indirect fire and
  spotting (which also settles STUB_MISSION_KILL); ammo conservation.
