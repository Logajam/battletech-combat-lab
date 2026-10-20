# Call Graph

Structural doc, separate from `INTEGRATION__PROJECT_MAP.md`. Tracks what
imports what, at module granularity. Update when wiring changes (new
import/call added, a file gets absorbed/retired). Not updated for
read-only investigation, and not a place for narrative or dated entries
— that stays in the Change Record.

Regenerated 2026-10-18 by grepping every `import`/`from ... import` line
in the INTEGRATION files after the first end-to-end wiring pass. MECHSIM/
PATHFINDER edges unchanged from the 2026-08-28 grep (those files weren't
edited).

---

## 1. EDGES

**Pile 1 / integration (`INTEGRATION__*`)**
- `main.py` → `orchestrator`
- `orchestrator.py` → `config` (imported first; self-registers as bare
  `config`), MECHSIM `mech_state` (is_destroyed, is_crippled, clone_mech,
  compute_*_mp, all_crew_unconscious, is_immobile),
  `piloting_rolls`; PATHFINDER `board_parser`, `hex_geometry`,
  `pathfinder.build_movement_table`, `combat` (build_jump_states,
  classify_movement_mode); INTEGRATION `rng`, `weapon_selection`, `heat`,
  `ranged_combat`, `movement_selection`, `stubs`, `attack_resolution`, `results`, `equipment_systems`,
  `ammo` (attach_ammo), `physical` (run_physical_phase) (2026-10-19), `electronics` (attach, 2026-10-20); stdlib
  `multiprocessing` / `concurrent.futures` + numpy `SeedSequence` for parallel
  batches (`battle_seed`, `worker_count`, `_worker_battle`) (2026-10-20)
- `attack_resolution.py` (NEW) → `config`, `stubs`, `weapon_selection`, `heat`, `equipment_systems`,
  `weapon_rules`, `ammo` (2026-10-19), `ams`, `electronics` (2026-10-20);
  MECHSIM `mech_state`, `armor_rules`, `hit_location`, `damage_resolution`
  (apply_damage, check_critical, cluster_hits_count, get_weapons),
  `piloting_rolls`; PATHFINDER `hex_geometry`, `combat` (fc_to_tmm,
  MODE_TO_AMM, in_rear_arc), `los` (has_los, hex_distance, trace_los_path)
- `weapon_rules.py` (NEW 2026-10-19) → MECHSIM `equipment.lookup_equipment`
  (local import). Otherwise a leaf: cluster/Streak/MRM/grouping and per-weapon
  to-hit modifiers.
- `ammo.py` (NEW 2026-10-19) → `config`, `stubs`, `weapon_rules`; MECHSIM
  `equipment` (Equipment, lookup_equipment), `damage_resolution.get_weapons`
- `weapon_profiles.py` (NEW 2026-10-20) → `weapon_rules` (lazy); MECHSIM `equipment`, `damage_resolution` (lazy).
  Used by `fire_modes`, `attack_resolution`, `ranged_combat`, `heat`.
- `fire_modes.py` (NEW 2026-10-20) → `config`, `stubs`, `weapon_rules`, `expected_damage`, `electronics`, `ammo`, `weapon_profiles`,
  `ams` / `weapon_selection` (lazy); MECHSIM `equipment`, `damage_resolution.get_weapons`; PATHFINDER
  `combat.hit_probability` (lazy). Used by `attack_resolution`, `weapon_selection`, `ranged_combat`, `orchestrator`,
  `electronics` / `ammo` / `heat` / `stubs` (lazy).
- `electronics.py` (NEW 2026-10-20) → `config`, `weapon_rules`, `expected_damage`, `equipment_systems`,
  `ammo`, `weapon_selection` (lazy); MECHSIM `equipment`, `damage_resolution.get_weapons`; PATHFINDER
  `combat.hit_probability` (lazy). Used by `attack_resolution`, `ams`, `ranged_combat`, `orchestrator` (attach).
- `ams.py` (NEW 2026-10-20) → `config`, `weapon_rules`, `expected_damage`, `arcs`, `ammo`, `heat`, `electronics`,
  `attack_resolution` (weapon_locations, lazy); MECHSIM `damage_resolution.get_weapons`,
  `mech_state` (all_crew_unconscious, compute_heat_dissipation); PATHFINDER `hex_geometry`.
  Used by `attack_resolution` (engage, weapon-choice factors) and `ranged_combat` (Coverage).
- `movement_attacks.py` (NEW 2026-10-20) → `config`, `attack_resolution`, `physical`, `ranged_combat` (lazy), `charge` / `dfa` (lazy); MECHSIM `mech_state`; PATHFINDER `hex_geometry`, `combat`, `terrain_rules`, `los`. Used by `movement_selection` (charge / DFA decisions, both movers' two-ply), `charge`, `dfa`, `physical` (displacement for pushes, lazy).
- `charge.py` (NEW 2026-10-20) → `config`, `attack_resolution`, `movement_attacks`; MECHSIM `mech_state`, `damage_resolution`, `hit_location`, `piloting_rolls`; PATHFINDER `hex_geometry`, `combat`. Used by `physical` (resolution, lazy import).
- `dfa.py` (NEW 2026-10-20) → `config`, `movement_attacks`, `attack_resolution` (lazy); MECHSIM `mech_state`, `piloting_rolls`; PATHFINDER `hex_geometry`, `combat`. Used by `physical` (lazy).
- `future_damage.py` (NEW 2026-10-20) → `config`, `arcs`, `ammo`, `fire_modes`, `heat`, `physical`, `structure_weight`, `weapon_profiles`, `weapon_selection`, `attack_resolution`, `ranged_combat` (`_make_heat_limited_scorer`, `_with_physical`), `equipment_systems`; MECHSIM `damage_resolution`, `mech_state`; PATHFINDER `combat`. Used by `movement_selection` (lifetime objective).
- `replay.py` (NEW 2026-10-20) → `config`, `arcs`, `attack_resolution` (total_hp); MECHSIM `mech_state`. Reads `replay_viewer.html`. Used by `orchestrator` (marks steps, writes pages).
- `clubs.py` (NEW 2026-10-20) → `config` only. Used by `attack_resolution` (pick-up), `physical` (club attacks), `orchestrator` (battle reset, end-of-phase drops).
- `physical.py` (NEW 2026-10-19) → `config`, `attack_resolution`, `arcs`, `structure_weight`, `charge` / `dfa` / `clubs` / `movement_attacks` (lazy); MECHSIM
  `mech_state`, `equipment`, `damage_resolution.apply_damage`,
  `hit_location.resolve_hit_location`, `piloting_rolls`; PATHFINDER
  `hex_geometry`, `combat`, `los` (has_los, hex_distance)
- `stubs.py` (NEW) → `config`; MECHSIM `mech_state`, `hit_location`
  (FACING_CHOICES); PATHFINDER `hex_geometry`, `los` (local imports inside
  stub_select_movement - removed 2026-10-19)
- `results.py` (NEW) → stdlib only. Leaf.
- `movement_selection.py` (NEW 2026-10-19) → `config`, `weapon_rules` (2026-10-20, is_ams), `ranged_combat`
  (MoveEvaluator, prepare_options), `los_cache`; MECHSIM `mech_state`,
  `damage_resolution`, `hit_location`, `piloting_rolls`; PATHFINDER
  `hex_geometry`, `combat`, `los`
- `arcs.py` (NEW 2026-10-19) → stdlib only (functools, math, typing). Used by `los_cache`, `attack_resolution`, `ranged_combat`, `physical`, `orchestrator` (End Phase reset).
- `structure_weight.py` (NEW 2026-10-19) → `config`, `expected_damage`, `weapon_rules`; MECHSIM `damage_resolution` (TRANSFER_MAP), `hit_location`. Used by `ranged_combat` and `movement_selection`.
- `los_cache.py` (NEW 2026-10-19) → `arcs`; PATHFINDER `combat`, `los`.
- `ranged_combat.py` → `los_cache` (2026-10-19), `config` (registration only), MECHSIM `mech_state`
  (compute_*_mp, compute_heat_dissipation, is_immobile); PATHFINDER `hex_geometry`,
  `pathfinder`, `los`, `combat`; `weapon_selection` (select_weapons_to_fire),
  `heat`, `equipment_systems`, `ammo`, `ams`, `electronics` (2026-10-20), `terrain_rules`, `attack_resolution` (tn_adjuster,
  aimed_shot_location, firing_conditions, ...). (No longer imports `damage_resolution` directly.)
- `equipment_systems.py` (NEW 2026-10-19) → `config`; MECHSIM `equipment`
  (Equipment, is_crit_target), `damage_resolution.resolve_slot_hit`
- `heat.py` (NEW 2026-10-18) → `config`, `stubs`, `equipment_systems`, `ammo` (2026-10-19); MECHSIM `mech_state`
  (compute_heat_dissipation, is_destroyed, pilot_unconscious,
  mark_consciousness_check_pending), `equipment` (Equipment,
  lookup_equipment), `damage_resolution` (apply_explosion, get_weapons), `piloting_rolls`
  (2026-10-19, Heat Phase)
- `weapon_selection.py` → `config` (registration only), `expected_damage`, `weapon_rules` (2026-10-20, is_ams),
  MECHSIM `damage_resolution.get_weapons`, PATHFINDER `combat.hit_probability`.
  **Purge/reload dance removed 2026-10-18** — plain imports now.
- `expected_damage.py` → bare `config` (= INTEGRATION__config via its
  self-registration), `weapon_rules` (2026-10-19)
- `config.py` → `file_picker` (INTEGRATION__file_picker), MECHSIM `mtf_parser`
- `rng.py` → `numpy` only
- `file_picker.py` → stdlib/`tkinter` only. Leaf. Only used when
  `MECH_*_MTF` is None.

**Pile 2 / mech state (`MECHSIM__*`)** — unchanged
- `armor_rules.py` → `mech_state`
- `damage_resolution.py` → `config`, `armor_rules`, `equipment`, `mech_state`
- `equipment.py` → stdlib only. Leaf (data loader; reads `equipment.json` next to itself).
- `hit_location.py` → `config` (also uses stdlib `random` directly for the tripod sub-roll)
- `mech_state.py` → `equipment`
- `mtf_parser.py` → `config`, `equipment`, `mech_state`, `damage_resolution`
- `piloting_rolls.py` → `config` (reads `config.PILOTING`), `hit_location`, `mech_state`, `damage_resolution`
- `sim_runner.py` → (reference only, NOT imported) `config`, `armor_rules`,
  `run_statistics` (absent), `piloting_rolls`, `equipment`, `hit_location`,
  `damage_resolution`, `mech_state`, `mtf_parser`

**Pile 3 / map (`PATHFINDER__*`)** — unchanged
- `board_parser.py` → stdlib only. Leaf.
- `combat.py` → `hex_geometry`, `pathfinder`, `los`
- `combat_turn.py` → (reference only, NOT imported) `hex_geometry`, `pathfinder`, `los`, `combat`
- `hex_geometry.py` → stdlib only. Leaf.
- `los.py` → `hex_geometry`
- `pathfinder.py` → `hex_geometry`, `terrain_rules`
- `report.py` → (not imported) `hex_geometry`, `pathfinder`, `combat`, `combat_turn`, `los`
- `terrain_colors.py` → stdlib only. Leaf, not imported.
- `terrain_rules.py` → stdlib only. Leaf.
- `validation.py` → (not imported) `hex_geometry`, `pathfinder`, `simulate` (absent), `board_parser`, `terrain_rules`

---

## 2. REACHABLE FROM THE ENTRY POINT (`INTEGRATION__main.py`)

```
main.py
└─ orchestrator.py
   ├─ config.py ── file_picker.py, mtf_parser ── equipment, mech_state, damage_resolution ── armor_rules
   ├─ mech_state, piloting_rolls ── hit_location, damage_resolution
   ├─ board_parser, hex_geometry, pathfinder ── terrain_rules, combat ── los
   ├─ rng.py
   ├─ weapon_selection.py ── expected_damage.py ── weapon_rules.py
   ├─ ammo.py ── weapon_rules.py, stubs.py
   ├─ heat.py ── stubs.py, equipment_systems.py, ammo.py, damage_resolution, piloting_rolls
   ├─ equipment_systems.py ── damage_resolution
   ├─ los_cache.py
   ├─ ranged_combat.py ── heat.py, los_cache.py
   ├─ movement_selection.py ── ranged_combat.py, los_cache.py, piloting_rolls, hit_location, damage_resolution
   ├─ stubs.py
   ├─ attack_resolution.py ── heat.py, weapon_rules.py, ammo.py, ams.py ── arcs.py, expected_damage.py, electronics.py, fire_modes.py
   ├─ physical.py ── attack_resolution.py, arcs.py, charge.py, dfa.py, clubs.py, hit_location, piloting_rolls
   └─ results.py
```

**Reachable:** every INTEGRATION file; MECHSIM
`config`(=INTEGRATION), `equipment`, `mech_state`, `damage_resolution`,
`armor_rules`, `hit_location`, `piloting_rolls`, `mtf_parser`; PATHFINDER
`board_parser`, `hex_geometry`, `terrain_rules`, `pathfinder`, `los`, `combat`.

**Not reachable (reference only, kept in the claude.ai Project, not in
the repo):** `MECHSIM__sim_runner.py`, `PATHFINDER__combat_turn.py`,
`report.py`, `validation.py`, `terrain_colors.py`.

---

## 3. KNOWN GAPS IN THIS GRAPH

- **MECHSIM's and PATHFINDER's own `config.py` are retired.** Every bare
  `import config` resolves to `INTEGRATION__config` via its
  self-registration — so `INTEGRATION__config` must be imported before
  any MECHSIM module. The orchestrator and `weapon_selection` both do this.
- **Two dangling imports** (only matter if run standalone, not reachable
  from main): `sim_runner.py` → `run_statistics`; `validation.py` →
  `simulate`. Neither file is in the Project.
- **Viz files** (`heatmap.py`, `combat_viz.py`, `los_viz.py`,
  `turn_viz.py`) and `compare_runs.py`/`build_equipment_db.py` absent;
  nothing imports them.

---

## 4. MAINTENANCE RULE

Update this doc when an actual import/call edge changes — new wiring,
a file absorbed or retired. Don't update it for files being temporarily
out of view; that's a session-level choice, not a structural fact.
