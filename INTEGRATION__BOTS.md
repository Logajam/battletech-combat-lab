# How the two bots work (2026-10-29, end of session 14)

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
spots against the WHOLE enemy force at those estimated spots: damage taken is
the sum over enemies, damage dealt the best single target.

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

## Next steps (Daniel's list, PROJECT_MAP "Pick up here" 0000)

- How much fire one unit really takes (Legate's own to-do): share the enemy's
  future fire over the units it could shoot, instead of all of it on me.
  Quick to build and A/B; expected to stop the light dive.
- Then team awareness: price a move by the team's expected firepower lost,
  using the kill curve for our own units too ("move somewhere more exposed to
  draw fire from a vulnerable unit").
- Movement order hierarchy; active choices in one currency; indirect fire and
  spotting (which also settles STUB_MISSION_KILL); ammo conservation.
