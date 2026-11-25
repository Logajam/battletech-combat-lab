# INTEGRATION__EVENTS.md - event records and search

**Event list version 2** (`btsim --events-list` prints it; the code is `engine/core/src/events.rs`).
Daniel, 2026-11-24: "I want a way to search sets of battles for events" - for example a turn where a 'Mech took four engine
hits in one phase, or a 1v1 where both 'Mechs destroyed each other's gyro on the same turn.

## The rules of the records

- **An event is DATA the engine writes where the thing happens**, from numbers the code already holds. It is never parsed back
  out of the log text, so a change of log wording cannot break a search.
- **Recording changes nothing.** An event is written beside the log line it matches; no dice are rolled and no decision is made
  by the code that records it. Events are off unless a caller turns them on (`Battle::events_on`), and a dry run (`quiet`, a
  bot's forecast, a Hydra playout) never records one. `tests/check_rust_reference.py` plays every reference battle with events ON
  and compares its log byte for byte with the saved one, so every run of it proves this.
- **The list is versioned.** `EVENT_VERSION` (events.rs) is bumped when a kind is added, removed or changes meaning; every stored
  event file carries the version it was written under. To add a kind: add it to `KINDS` in events.rs, write the hook, add its row
  here (`tests/check_events.py` compares this table with the engine's list), bump the version, re-save the reference events
  (`python tests/check_rust_reference.py --update`, a change of events only: every log must stay identical) and name it in the
  Change Record.

## What one event holds

`{k, t, p, u, o, tn, r, ok, d, l, s, w, n}` - unset fields are left out of the JSON.

| field | meaning |
|---|---|
| `k` | kind (below) |
| `t` | turn (0 = deployment) |
| `p` | phase: `deployment`, `initiative`, `movement`, `ranged` (TAG designation and indirect-fire spotting happen here), `physical`, `heat`, `end` |
| `u` | the unit it happened to or that did it (its side name, e.g. `Red 1`) |
| `o` | the second party: target, or the attacker in a HIT |
| `tn`, `r`, `ok` | the number needed, the 2D6 rolled, and whether it succeeded |
| `d`, `l` | damage, location |
| `s` | sub-kind: weapon family, move mode, slot type, cause... (see each kind) |
| `w` | what: weapon name, hex, reason... |
| `n` | a count: shots, MP, hits so far, heat... |

A battle's file also carries `teams` ({unit: team}) so a search can say "a Blue unit" (`u_team`, `o_team`).

## The kinds

| kind | fields |
|---|---|
| `INITIATIVE_ROLL` | one team's Initiative throw: sub = team, roll = the 2D6, n = round (1 = first throw, 2+ = a tie re-roll among the tied teams) |
| `MOVE` | a unit's move: sub = mode (walk, run, jump, ...), n = MP used, what = destination hex |
| `MOVE_PATH` | (version 2) the route of the MOVE just before it, for a ground move (not a jump or a charge): what = the steps as "HEX/S/MP" entries joined by spaces (the hex after the step, S = F forward, B backward, L or R a turn, E entering the board; MP spent so far), n = number of steps, sub = the mode. The engine's own best route to the destination (most hexes moved, so the best TMM): the rules check only the two ends of a move. Written only when events are on; found with the read-only `step_walk::route_text` before the unit moves |
| `STAND_ATTEMPT` | a prone unit tries to stand: tn, roll, ok = it stood |
| `FALL` | a unit falls: sub = cause (movement, hit, pilot, ...), n = fall damage |
| `WATER_ENTER` | a unit's move ends in water after starting out of it: n = depth, what = hex (only the move's two ends are compared) |
| `BUILDING_ENTER` | a unit's move ends in a building hex after starting outside one: what = hex |
| `BUILDING_LEAVE` | a unit's move ends outside a building after starting in one: what = the hex it left |
| `HAZARD` | a hazard taken: sub = magma, magma_crust (the crust breaks), hazardous_liquid or bog (stuck) |
| `PHYS_CHARGE` | charge: unit attacks other, tn, roll, ok, dmg = damage to the target |
| `PHYS_DFA` | death from above: as PHYS_CHARGE |
| `PHYS_PUSH` | push: as PHYS_CHARGE |
| `PHYS_KICK` | kick: as PHYS_CHARGE |
| `PHYS_PUNCH` | punch: as PHYS_CHARGE, loc = arm |
| `PHYS_CLUB` | club, hatchet and other melee gear: as PHYS_CHARGE, what = the weapon |
| `ATTACK` | one weapon's attack roll: unit fires at other, sub = weapon family (energy, ballistic, missile, area_effect), what = weapon, tn, roll, ok = hit, n = shots |
| `HIT` | damage landing on a unit: unit = the one hit, other = who hit it, loc = location, roll = location roll, dmg = damage applied, sub = ranged, physical or other, what = weapon |
| `TAG_DESIGNATE` | a TAG shot: unit tags other (or a hex), tn, roll, ok, sub = mech or hex |
| `SPOT` | a unit spots for indirect fire: unit spots other |
| `INDIRECT_FIRE` | an attack with no line of sight, fired on a spot: unit fires at other, what = weapon |
| `HOMING_HIT` | a homing missile strikes a TAG-designated target (sub = mech or hex): unit fires at other, dmg |
| `CRIT` | a critical hit: unit = the one hit, loc, sub = slot type (Engine, Gyro, Cockpit, Sensors, Life Support, Actuator, Weapon, Ammo, Heat Sink, Other), what = the slot, n = that component's hits so far |
| `COMPONENT_DESTROYED` | a component is gone for good: sub = Engine, Gyro or Cockpit |
| `AMMO_EXPLOSION` | an ammo bin explodes: loc, sub = case or no_case (the location's CASE state), dmg = damage taken |
| `LOCATION_DESTROYED` | a location is destroyed: loc |
| `UNIT_DESTROYED` | a unit is destroyed: sub = cause |
| `PILOT_HIT` | the pilot takes damage: n = hits so far, sub = cause |
| `CONSCIOUSNESS` | a consciousness roll: tn, roll, ok = stayed conscious, n = pilot hits |
| `SHUTDOWN` | a unit shuts down: sub = heat or other cause |
| `RESTART` | a restart attempt: tn, roll, ok |
| `HEAT_LEVEL` | heat at the end of the Heat Phase: n = heat now, sub = the highest heat-scale step at or below it (0, 5, 8, 10, 13, 14, 15, 17, 18, 19, 20, 22, 23, 24, 25, 26, 28, 30) |
| `TARGET_CHOSEN` | a unit's declared target: unit picks other |
| `MOVE_CHOSEN` | the move a unit chose: sub = mode, what = destination hex, n = MP |
| `HOLD_FIRE` | a unit that could not or would not fire: what = the reason |

### What is and is not recorded (known limits)

- **Skids are not recorded: the engine has no skid rule.** (Daniel's first list named them; there is nothing to hook.)
- **WATER_ENTER / BUILDING_ENTER / BUILDING_LEAVE** compare the hex a unit's move began in with the one it ended in. A hex only
  passed through is not seen, nor is a displacement by a push, charge or domino.
- **CRIT** is a critical hit rolled on the table. An engine or gyro slot lost because its whole location was destroyed counts
  toward the component but writes no CRIT; a `COMPONENT_DESTROYED` follows only from a CRIT.
- **HIT** is damage applied to a location: ranged and physical attacks carry their attacker (`o`) and weapon (`w`); falls,
  hazards and heat damage carry neither. `d` is the damage the location took after the rules that reduce it (a halved physical
  hit under water, Heat-dissipating armor...), before armor absorbs any of it.
- **SHUTDOWN** is written for every shutdown; its `s` is `heat` (the engine's only shutdown source in the Heat Phase).
- **HOLD_FIRE** names the reason a unit that was to fire could not (`w`).
- Battles a trial recorded before this list existed have no events and are skipped by a search.

## Where events are kept

| what | where |
|---|---|
| a trial's battles (`tools/hydra_trial.py`, `round_robin.py`: anything that calls `trial_records.stream_args`) | `trial_records/events/<records file name>/<batch>.events.jsonl.gz`: gzip, one JSON line a battle (`{sim, seed, events_version, teams, events}`), a header line first (the batch's settings and the exact `btsim` command). The records line names its file in `"events"`. A batch's progress file (git-ignored) holds the events as they happen, so a stopped set resumes with `btsim --stream`. |
| the reference battles | `engine/reference/events/<name>.events.jsonl.gz`: a header line `{events_version, teams}`, then one event a line. `check_rust_reference.py` compares them as it compares the logs. |
| a replay page | inside the page's JSON (`events`, `events_version`), whenever `btsim --history` or the Lab makes one |
| any run | `btsim ... --events --events-out FILE` writes `{sim, seed, events_version, teams, events}` a line as each battle ends |

**Size** (100 battles of a set, measured 2026-11-24, Hydra v house bot): duels 0.30 MB gzipped (4.5 MB raw, about 570 events a
battle), 2v2 0.35 MB, 4v4 0.77 MB, 8v8 1.6 MB (24 MB raw). Recording costs 2-7% of a battle's run time. A replay page grows by
about 20-40 KB. Events are stored compressed and stay queryable: the search reads them straight from the gzip.

## Searching

Two ways, one engine (`engine/lab/web/events_query.js`): `tools/search_events.py` runs that file under node, and the replay
page carries a copy of it (`tools/sync_events_query.py` keeps the copy current; `tests/check_events.py` fails when it is not), so
a query gives the same answer in both.

### On the command line

```
python tools/search_events.py [SOURCE ...] --example engine-hits-4
python tools/search_events.py trial_records/2026-11-24_hydra_trial_events_demo.jsonl --kind CRIT --where s=Engine --group u,t,p --count '>=4'
python tools/search_events.py --reference --query-file my_query.json --limit 50
python tools/search_events.py --list-examples      # the prepared searches
python tools/search_events.py --list-kinds         # this table
```

A SOURCE is a records file (its event files are followed), an event file, or a folder; none = every records file in
`trial_records/`; `--reference` = the reference battles. Each match prints the battle (set, number, seed), the turn, the phase, the
events found, and **the exact `btsim` command that replays that battle** (`--sims N --history N`; the page lands in `replays/`;
for a reference battle `python tests/check_rust_reference.py --only NAME --exact --history replays`). Then counts per battle and per
set. `--json` gives everything.

### In the replay tab

Every replay page has a **Search events** panel: pick a prepared search, or an event type and filters, or paste a query. A result
jumps the replay to its turn and phase (a movement event to its unit's move). A replay made before events existed says so.

### The query language

JSON, documented at the top of `events_query.js`:

```
{ "steps": [ {"as": "a", "kind": "STAND_ATTEMPT"}, {"as": "b", "kind": "PHYS_CHARGE", "where": {"o": "$a.u"}} ],
  "same": ["t"], "ordered": true }
```

- `steps` - events to find, in order (`"ordered": false` = any order). `kind` is a name or a list. `where` maps a field to a value or
  `{eq, ne, gt, gte, lt, lte, in, nin, re}`. A value `"$a.u"` is the field `u` of the event step `a` matched.
- `same` - fields every event of the match must share: `["t"]` the same turn, `["t","p"]` the same turn and phase.
- `group` + `count` (one step) - count the step's events per group of fields; each group that passes `count` is a match.
- derived fields `u_team`, `o_team`.

## The reference list and its coverage rule

`engine/reference/battles.txt` is the list of battles `tests/check_rust_reference.py` plays (the scenarios are in `engine/reference/scenarios.zip`, the saved
logs in `engine/reference/logs/`, the saved events in `engine/reference/events/`). It was chosen 2026-11-24 with these tools:

1. `python tests/check_rust_reference.py --all --out POOL` plays EVERY scenario and variant of the zip (nothing in engine/reference is touched).
2. `python tools/event_coverage.py --reference-dir POOL --answer-key --tsv table.tsv --times ...` tabulates, per battle, how often each event type
   (and each sub-case: `CRIT:Gyro`, `ATTACK:homing`, the weapons fired `WEAPON:...`, the gear fielded `GEAR:...`) happens.
3. `python tools/choose_reference_set.py table.tsv --n 3 --keep-file KEEP --write-list engine/reference/battles.txt` picks the cheapest set in which
   every event type happens in at least N=3 battles, and every sub-case, weapon and piece of gear at least once, after the battles in KEEP
   (the long full-length bot battles that guard against stalls and slow drift, and each Hydra / CASPAR switch variant).
4. A type nothing reaches gets a short purpose-built scenario (`tools/make_event_scenarios.py`, the `ev_*` battles).

**The rule the check enforces:** it prints each event type's battles and events across the list and **fails if any type has no event** (a rule or a
scenario stopped reaching it); fewer than 3 battles is a NOTE. Changing the list: re-run the steps and name every dropped battle in the Change Record
(PROJECT_MAP Section 7).

### Prepared searches (`engine/lab/web/events_examples.json`)

- `engine-hits-4` - a 'Mech takes 4 or more engine critical hits in one turn and phase.
- `mutual-gyro` - two different units each lose their gyro in the same turn (the 1v1 where both kill the other's gyro).
- `tag-then-homing` - a TAG designation that hit, then a homing missile hit on the same target in the same turn.
- `stand-then-charge` - a unit tries to stand, then is charged the same turn.
- `ammo-explosion-no-case`, `fall-then-pilot-hit`.
