# BattleTech Monte Carlo Simulator

Headless batch simulator: two mechs (`.mtf` files) fight on a hex board,
turn by turn, many times over, and the results are summarized.

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
| `INTEGRATION__*.py` | The simulator: turn flow, combat, movement picking (`movement_selection`), firing arcs and torso twists (`arcs`), heat, results, stubs |
| `mechsim/` | Mech state, damage, crits, piloting rolls, `.mtf` parser, `equipment.json` (full equipment database) |
| `pathfinder/` | Hex geometry, board parser, movement, LOS, to-hit pieces |
| `data/` | `.board` maps (16x17 Grassland, 50x50 BigBlank) and `.mtf` mechs (test mechs, plus the Atlas AS7-K / AS7-S2, Archer ARC-2R and Kintaro KTO-19 from `meks.zip` for the AMS / Artemis / Narc / ECM reference battles) |
| `data/meks.zip` | 4,227 MegaMek `.mtf` units by source book (4,162 parse; ultralights under 20 t, superheavies and LAMs don't). Unzip outside the repo and point `INTEGRATION__config.py` at a file to try a unit |
| `tests/` | `check_reference_logs.py` (same-seed battles vs saved logs), `test_pathfinder.py` (hex geometry, movement, board parsing, terrain costs), `test_weapon_range.py` (range modifiers), `test_heat.py` (Heat Scale), `test_equipment.py` (heat equipment), `test_rules.py` (stub replacements), `test_movement_selection.py` (movement picker), `test_arcs.py` (twists, arm flips, turrets), `test_special_attacks.py` (charges, DFA, pushes, clubs), `test_ams.py` (anti-missile systems), `test_electronics.py` (Artemis, Narc, ECM, ammo-bin names), `test_parallel_batch.py` (parallel batches) |
| `rules/` | `Battletech_Rule_Reference_Index.zip`: the rules library (Core Rulebook in `base/core-rules/*.md`) that page cites in the code refer to. Unzip somewhere outside the repo to read it |
| `reference_logs/` | Same-seed sample logs (matchup and settings in the file name), for checking that a change didn't alter results |

After a change, from the repo root:
- `python tests/check_reference_logs.py`: re-runs the reference battles and checks the results are unchanged
- `python tests/test_pathfinder.py`: checks the movement/map code
- `python tests/test_weapon_range.py`: checks range brackets and the minimum-range penalty
- `python tests/test_heat.py`: checks the Heat Scale rules (Core Rulebook pp.102-107) with scripted dice
- `python tests/test_equipment.py`: checks the heat/movement equipment (stealth, coolant pods, radical heat sinks, inferno, TSM, MASC, supercharger, aimed shots)
- `python tests/test_movement_selection.py`: checks the movement picker against brute-force scoring (reduction, two-ply reply, PSR cost, exposure, structure weighting, Void Signature, closing fallback, firing arcs and torso twists, physical attacks next to the enemy, determinism)
- `python tests/test_arcs.py`: checks torso twists (both attack phases, tripods), tripod leg arcs, reversing arms, Quad Turrets and the End Phase reset
- `python tests/test_special_attacks.py`: checks charges and death from above (damage, reach, the decision gate, the first mover anticipating them, displacement, PSRs, cancellation), pushes (when possible, off the board / down a cliff, the threat in movement scoring), clubs (holding, picking up, attacking, dropping) and multi-level falls - uses units from `data/meks.zip`
- `python tests/test_ams.py`: checks Anti-Missile Systems (Core Rulebook p.206: the engaged Cluster roll, Streaks, single missiles, arcs, the 2-a-turn limit, ammo, heat, crew / shutdown, expected damage in weapon choice and movement) - uses units from `data/meks.zip`
- `python tests/test_electronics.py`: checks Artemis IV / V, Narc / iNarc pods, ECM (Angel vs Streaks, stealth armor), munition choice and the ammo-bin names (Core Rulebook pp.186-188, 192-193, 197, 200) - uses units from `data/meks.zip`
- `python tests/test_parallel_batch.py`: checks that a batch prints the same output whether its battles run one at a time or in parallel, and each battle's own seed
- `python tests/benchmark_turns.py`: times the first 10 turns of the default battle (seed 12345) - for speed changes
- `python tests/test_rules.py`: checks the rules that replaced stubs (attack direction, cluster groupings, to-hit modifiers, ammo, deployment, physical attacks)

Anything not yet a real rule is a loud **stub**: it prints `STUB: ...` to
stderr and appears in the summary banner.

New to the project (or a new Claude session)? Start with `CLAUDE.md`, then Section 0 of `INTEGRATION__PROJECT_MAP.md`.

Project status, open items and decisions: `INTEGRATION__PROJECT_MAP.md` (torso twists and firing arcs: its Section 4a).
Core Rulebook vs code (fixed, gaps, questions for Daniel): `INTEGRATION__RULES_REVIEW.md`.
Import structure: `INTEGRATION__CALL_GRAPH.md`.
