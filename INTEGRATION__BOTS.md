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

[filled in from the battery below]
