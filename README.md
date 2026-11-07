# BattleTech Monte Carlo Simulator

Headless batch simulator: two mechs (`.mtf` files) fight on a hex board,
turn by turn, many times over, and the results are summarized. Any number of
mechs on any number of teams can fight too (a lance against a lance, a company,
a free for all, a three-way battle): set `FORCES` in `INTEGRATION__config.py`.

## Run it

```
python INTEGRATION__main.py
```

Needs Python 3 and NumPy (`pip install -r requirements.txt`). All settings (which mechs,
board, seed, number of battles, stub knobs) are in `INTEGRATION__config.py`.
A batch runs one battle per CPU core at once (`WORKERS`; set it to 1 to run them
one after another) - the output is the same either way.

## Layout

| Path | What's there |
|---|---|
| `INTEGRATION__*.py` | The simulator: turn flow, combat, movement picking (`movement_selection`), firing arcs and torso twists (`arcs`), heat, results, stubs; Tactical Operations / Interstellar Operations gear and terrain (`advanced_weapons`, `advanced_equipment`, `hazards`, `smoke`); which bot drives each unit (`bots`: "gladiator", this project's, or "princess", a clone of MegaMek's Princess - modern in `princess_modern`, v0.50.07 in `princess`, fire control in `princess_fire`; its team behaviors in `princess_group` and `princess_memory`); Battle Value (`battle_value`, items from `mechsim/equipment_bv.json`); Legate (`legate`, `config.LEGATE`: the layer that lets a Gladiator plan against the whole enemy force); the tiered movement order (`tiers`, `config.MOVE_ORDER = "tiered"`) |
| `mechsim/` | Mech state, damage, crits, piloting rolls, `.mtf` parser, `equipment.json` (full equipment database) |
| `pathfinder/` | Hex geometry, board parser, movement, LOS, to-hit pieces |
| `data/` | `.board` maps (16x17 Grassland, 50x50 BigBlank) and `.mtf` mechs (test mechs, plus real units from `meks.zip` for the AMS / Artemis / Narc / ECM / weapon-use reference battles) |
| `data/maps.zip` | Daniel's MegaMek map pack (346 `.board` maps, 192 of them 16x17). `python tests/survey_maps.py` lists which ones the simulator can play and what stops the rest |
| `data/meks.zip` | 4,227 MegaMek `.mtf` units by source book (4,204 load - ultralights and superheavies since 2026-10-28; the 23 LAMs don't). Unzip outside the repo and point `INTEGRATION__config.py` at a file to try a unit |
| `tests/` | `run_checks.py` (everything below in one command), `check_reference_logs.py` (same-seed battles vs saved logs), `test_pathfinder.py` (hex geometry, movement, board parsing, terrain costs), `test_terrain.py` (map terrain: costs, roads, level limits, jump height, passive buildings, deployment depth / stuck terrain), `test_water.py` (water: depth, cover, the water line, underwater weapons, torpedoes, heat sinks, jump jets, PSRs, falls), `test_los.py` (line of sight per the Core Rulebook: heights, intervening terrain, woods, partial cover, prone, border lines), `survey_maps.py` (which maps in `data/maps.zip` play - not in run_checks), `test_weapon_range.py` (range modifiers), `test_heat.py` (Heat Scale), `test_equipment.py` (heat equipment), `test_rules.py` (stub replacements), `test_movement_selection.py` (movement picker), `test_arcs.py` (twists, arm flips, turrets), `test_special_attacks.py` (charges, DFA, pushes, clubs), `test_ams.py` (anti-missile systems), `test_electronics.py` (Artemis, Narc, ECM, ammo-bin names), `test_fire_modes.py` (rapid fire, ammunition kinds, Apollo, the weapon-use stubs, slot counts), `test_weapons.py` (variable-damage, HAG, M-pod, MG array, bombast, rifles, heat-causing, Arrow IV / artillery, Apollo saturation, pooled cluster damage, PPC capacitors, Thumper / Sniper, TAG and homing artillery), `test_tiers.py` (the tiered movement order: tiers, order, flanker pool, entry), `test_peril.py` (the visibility table and the Peril field), `peril_picture.py` (the Peril heat map of a saved battle turn as a page - not in run_checks), `test_multi_unit.py` (teams, Initiative and Unequal Numbers for any number of sides, foe / target choice, stacking, the domino effect, 3-way / lance / free-for-all battles), `test_parallel_batch.py` (parallel batches), `test_replay.py` (battle replays), `test_stats.py` (battle statistics: the log, the analysis, the page), `test_saved_state.py` (saved states: team battles reloaded every turn, files, fresh dice, settings), `test_rng.py` (every roll of a battle from its one pool of dice), `test_fastcore.py` (the Rust module gives the Python's exact answers; skips when not built), `test_fire_tables.py` (the weapon choice's lookup tables give the fresh answer in team battles), `test_bots.py` (the bot switch and the Princess clone), `test_hazards.py` (TO:AR magma, hazardous pools, bogging down, hazards in path search and both bots), `test_advanced_gear.py` (TO:AUE HVAC, mortars, Taser, fluid guns / VGLs, turrets, modular armor, flail / chain whip, smoke and active probes, Gauss explosions), `test_intops.py` (Interstellar Operations TSEMP, iATM with IMP / IIW, inferno missiles, Improved weapons, nail / rivet gun), `test_superheavy.py` (ultralight and superheavy 'Mechs), `ab_batches.py` (the same seeds under several bot settings, side by side), `bot_agreement.py` (how often Princess's movement pick matches Gladiator's - not in run_checks), `turn_inspector.py` (pick battle N, turn T of the baseline battery and read back that turn's math: Legate's estimate v truth, each move's predicted v real score, each attack's model v dry run v what landed, every shot; replayable under a changed setting - not in run_checks), `probe_hooks.py` (the recorders, shared), `legate_probe.py` + `legate_probe_report.py` (a diagnostic battery: Legate's estimate v truth, predicted v actual damage, the regret of each pick, cohesion, calibration - not in run_checks), `pick_quality.py` (every bot's movement pick priced on Perfect Knowledge's scale over 8 scenarios; `--pickers` runs only some, `--perfect-cache` reuses Perfect's prices - not in run_checks) |
| `rules/` | `Battletech_Rule_Reference_Index.zip`: the rules library (Core Rulebook in `base/core-rules/*.md`) that page cites in the code refer to. Unzip somewhere outside the repo to read it |
| `stats/` | Battle statistics pages and their JSON (made at the end of every batch while `STATS` in `INTEGRATION__config.py` is on; open one in a browser). Not kept in git |
| `replays/` | Battle replay pages (made when `REPLAY_BATTLES` in `INTEGRATION__config.py` is above 0; open one in a browser). Not kept in git |
| `fastcore/` | Rust hot loops (2026-11-03 trial, since 2026-11-06 the weapon choice table, missile pricing, the movement search, line of sight and hex distance; optional - without it everything runs in Python with the same results): `pip install maturin && cd fastcore && maturin build --release && pip install --force-reinstall target/wheels/*.whl`. `config.USE_FASTCORE` switches it all off; `FASTCORE_PRICING`, `FASTCORE_MOVEMENT`, `FASTCORE_LOS` one part each |
| `saved_states/` | Saved states (made when `SAVE_STATE_TURNS` in `INTEGRATION__config.py` names turns): `python INTEGRATION__saved_state.py <file> [--turns N] [--fresh-dice SEED]` plays on from one. Not kept in git |
| `tools/` | Combat Lab art (output only; the simulator never imports it): `token_sheet.py` (2D token contact sheet), `token_3d.py` (the 3D model viewer page, `--glb` for glTF files), `token_audit.py` (measures every model: blocks floating free of the body, parts below the ground, mirror symmetry). Need `pip install scipy trimesh python-fcl`. Design and history: `INTEGRATION__COMBAT_LAB.md` |
| `reference_logs/` | Same-seed sample logs (matchup and settings in the file name), for checking that a change didn't alter results |

After a change, from the repo root:
- `python tests/ab_batches.py 20 "Red.mtf" "Blue.mtf" --set knowledge --turns 50`: A/B batches - one matchup, the same seeds, under several bot settings (`--set` picks a `VARIANT_SETS` entry at its top: `objective`, `search`, `knowledge`, `grid-spin`, `baseline`; `--board`, `--seed` too). 20 battles a setting by default (Daniel)
- `python tests/run_checks.py`: **the clean-baseline check** - runs every test below and every reference battle side by side, one line each (`--bench` adds the benchmark)
- `python tests/check_reference_logs.py`: re-runs the reference battles and checks the results are unchanged (`--round-trip`: each battle saved, reloaded and played on from the reload after every turn - must still match; not in run_checks)
- `python tests/test_multi_unit.py`: checks multi-unit battles (Core Rulebook pp.39-41, 113-116): Initiative and the Unequal Numbers tables, who a unit fights, stacking, domino effects and accidental falls from above, and whole 3-way / lance / free-for-all battles - uses units from `data/meks.zip`
- `python tests/test_map_picker.py`: checks the map picker (listing the loose boards and the map pack, finding a map, which maps fit a stitched grid, the console menu with scripted answers, remembering the last pick)
- `python tests/test_princess_group.py`: checks Princess's team behaviors (the target choice with the damage friends already declared, the heat map and its hot spot, mutual support, crowding, the force's posture, a move against several enemies)
- `python tests/test_legate.py`: checks Legate (the hex-conflict cascade, the estimate, the foe choice, the other enemies' damage in a Gladiator's move score; off and in a duel nothing changes)
- `python tests/test_battle_value.py`: checks Battle Value (the four published values, skill, damage, the equipment data, every unit in the pack priced)
- `python tests/baseline_battery.py pp|pg|gg [battles] [--legate] [--fire-split ...] [--split-now] [--herding] [--cohesion SCALE] [--team-value ...] [--first N --last M] [--move-order index|tiered|random|reverse] [--fresh] [--replay]`: the baseline battery - 12 v 12 mirrored forces on a 2 x 1 stitched field, Princess v Princess / Princess v Gladiator / Gladiator v Gladiator; prints winner, turns, units and HP left, seconds a battle (a yardstick: results recorded in PROJECT_MAP Section 8). RESUMABLE: each finished battle is saved under `run_stats/baseline/saved/`, so after a machine restart run the same command again and saved battles are skipped (`--fresh` ignores them); `python tests/battery_summary.py [name]` prints wins / 'Mechs left / damage per saved set; with `--stats` each battle's full event log is saved too, and `python tests/battery_stats.py <name>` writes the per-unit statistics page from them
- `python tests/test_pathfinder.py`: checks the movement/map code
- `python tests/test_weapon_range.py`: checks range brackets and the minimum-range penalty
- `python tests/test_heat.py`: checks the Heat Scale rules (Core Rulebook pp.102-107) with scripted dice
- `python tests/test_equipment.py`: checks the heat/movement equipment (stealth, coolant pods, radical heat sinks, inferno, TSM, MASC, supercharger, aimed shots)
- `python tests/test_movement_selection.py`: checks the movement picker against brute-force scoring (reduction, two-ply reply, PSR cost, exposure, structure weighting, Void Signature, closing fallback, firing arcs and torso twists, physical attacks next to the enemy, determinism, the IF/THEN picker)
- `python tests/test_arcs.py`: checks torso twists (both attack phases, tripods), tripod leg arcs, reversing arms, Quad Turrets and the End Phase reset
- `python tests/test_special_attacks.py`: checks charges and death from above (damage, reach, the decision gate, the first mover anticipating them, displacement, PSRs, cancellation), pushes (when possible, off the board / down a cliff, the threat in movement scoring), clubs (holding, picking up, attacking, dropping) and multi-level falls - uses units from `data/meks.zip`
- `python tests/test_ams.py`: checks Anti-Missile Systems (Core Rulebook p.206: the engaged Cluster roll, Streaks, single missiles, arcs, the 2-a-turn limit, ammo, heat, crew / shutdown, expected damage in weapon choice and movement) - uses units from `data/meks.zip`
- `python tests/test_electronics.py`: checks Artemis IV / V, Narc / iNarc pods, ECM (Angel vs Streaks, stealth armor), munition choice and the ammo-bin names (Core Rulebook pp.186-188, 192-193, 197, 200) - uses units from `data/meks.zip`
- `python tests/test_fire_modes.py`: checks rapid fire (Ultra / Rotary AC, jams, unjamming), LB-X cluster rounds, ATM / MML ammunition, the Apollo FCS, the weapon-use and MASC stubs, and the slot-count / machine-gun data fixes - uses units from `data/meks.zip`
- `python tests/test_weapons.py`: checks the weapons that couldn't fire before (variable damage, HAG, M-pods, machine gun arrays, bombast lasers, rifles, flamer / plasma heat, Arrow IV, artillery cannons), Apollo saturation, pooled cluster damage and PPC capacitors - uses units from `data/meks.zip`
- `python tests/test_hazards.py`, `test_advanced_gear.py`, `test_intops.py`, `test_superheavy.py`: check the Tactical Operations terrain and gear, the Interstellar Operations weapons, and ultralight / superheavy 'Mechs (2026-10-27/28) - use units from `data/meks.zip`
- `python tests/test_parallel_batch.py`: checks that a batch prints the same output whether its battles run one at a time or in parallel, and each battle's own seed
- `python tests/benchmark_turns.py`: times the first 10 turns of the default battle (seed 12345) - for speed changes
- `python tests/test_token_volume.py`, `test_token_joined.py`: check the Combat Lab 3D art (equal mass, equal volume; real-scale missile tubes; every block joined to the body). They skip, and pass, without the art libraries above
- `python tests/test_rules.py`: checks the rules that replaced stubs (attack direction, cluster groupings, to-hit modifiers, ammo, deployment, physical attacks)

Anything not yet a real rule is a loud **stub**: it prints `STUB: ...` to
stderr and appears in the summary banner.

New to the project (or a new Claude session)? Start with `CLAUDE.md`, then Section 0 of `INTEGRATION__PROJECT_MAP.md`.

Project status, open items and decisions: `INTEGRATION__PROJECT_MAP.md` (torso twists and firing arcs: its Section 4a).
Core Rulebook vs code (fixed, gaps, questions for Daniel): `INTEGRATION__RULES_REVIEW.md`.
Import structure: `INTEGRATION__CALL_GRAPH.md`.
