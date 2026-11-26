// Translated from INTEGRATION__ranged_combat.py (movement_options, _entry_options, prepare_options, turned_option) and
// INTEGRATION__movement_selection.py (reduced_options, occupied_hexes): the end states a mover can reach this turn,
// the Section 5c reduction, and what each state carries that does not depend on where the enemy is.
use crate::fasthash::{HashMap, HashSet};

use crate::fasthash::IndexMap;

use crate::battle::{Battle, UnitId};
use crate::combat::{classify_movement_mode, fc_to_tmm, mode_to_amm};
use crate::hex_geometry::{self, State};
use crate::mech_state::*;
use crate::pathfinder::Hex;
use crate::terrain_rules;

/// (x, y, facing, fc, mode, mp_spent)
pub type StateKey = (i64, i64, i64, i64, &'static str, i64);

/// The `mover.path_psrs` / `mover.path_hazard` tables of the Python: what the search noted for each state it yielded.
#[derive(Default, Clone)]
pub struct PathNotes {
    pub psrs: HashMap<StateKey, i64>,
    pub hazard: HashMap<StateKey, f64>,
}

impl PathNotes {
    /// _note_psrs: the fewest terrain PSRs (run-only ones count for a Run) and the least hazard damage per state.
    pub fn note(&mut self, key: StateKey, psrs: (i64, i64), hazard: f64) {
        let n = psrs.0 + if key.4 == "Run" { psrs.1 } else { 0 };
        match self.psrs.get(&key) {
            Some(old) if *old <= n => {}
            _ => {
                self.psrs.insert(key, n);
            }
        }
        if hazard != 0.0 {
            match self.hazard.get(&key) {
                Some(old) if *old <= hazard => {}
                _ => {
                    self.hazard.insert(key, hazard);
                }
            }
        } else if self.hazard.contains_key(&key) {
            self.hazard.insert(key, 0.0);
        }
    }
}

pub fn mode_str(m: &str) -> &'static str {
    match m {
        "Stand Still" => "Stand Still",
        "Walk" => "Walk",
        "Run" => "Run",
        "Jump" => "Jump",
        other => panic!("mode {}", other),
    }
}

/// One mover end state with everything about it that does not depend on where the defender is (`_Option`).
#[derive(Clone, Debug)]
pub struct Opt {
    pub x: i64,
    pub y: i64,
    pub facing: i64,
    pub label: String,
    pub facing_compass: &'static str,
    pub fc: i64,
    pub mode: &'static str,
    pub mp_spent: i64,
    pub amm: i64,
    pub move_heat: i64,
    pub tmm: i64,
    pub void_mod: i64,
}

impl Opt {
    pub fn hex_xy(&self) -> (i64, i64) {
        (self.x, self.y)
    }
    pub fn key(&self) -> StateKey {
        (self.x, self.y, self.facing, self.fc, self.mode, self.mp_spent)
    }
    /// The pick dict {hex, facing, mode, fc, mp_spent}.
    pub fn pick(&self) -> crate::ranged_combat::Pick {
        crate::ranged_combat::Pick { hex: self.label.clone(), facing: self.facing_compass.to_string(), mode: self.mode.to_string(), fc: self.fc, mp_spent: self.mp_spent, charge: false, dfa: false, route: None }
    }
}

/// prepare_options: _Option objects for (x, y, facing, fc, mode, mp_spent) tuples; states with no labeled hex are dropped.
pub fn prepare_options(b: &Battle, u: UnitId, options: &[StateKey]) -> Vec<Opt> {
    let m = &b.units[u];
    let mut out = Vec::with_capacity(options.len());
    for &(x, y, facing, fc, mode, mp_spent) in options {
        let Ok(label) = hex_geometry::hex_label(x, y) else { continue };
        out.push(Opt {
            x,
            y,
            facing,
            label,
            facing_compass: hex_geometry::facing_to_compass(facing).unwrap(),
            fc,
            mode,
            mp_spent,
            amm: mode_to_amm(mode),
            move_heat: crate::heat::movement_heat(m, mode, fc),
            tmm: fc_to_tmm(fc, mode == "Jump").unwrap() + target_size_modifier(m),
            void_mod: crate::equipment_systems::void_signature_modifier(m, Some(fc), Some(mp_spent)),
        });
    }
    out
}

/// turned_option: a copy of state `o` facing `facing` instead.
pub fn turned_option(o: &Opt, facing: i64) -> Opt {
    let mut t = o.clone();
    t.facing = facing;
    t.facing_compass = hex_geometry::facing_to_compass(facing).unwrap();
    t
}

fn blocked_hexes(b: &Battle, u: UnitId) -> HashSet<Hex> {
    crate::ranged_combat::blocked_set(&b.units[u].blocked_hex)
}

/// movement_options: every end state the mover can reach this turn, in the Python's order, noting each state's terrain
/// PSRs and hazard damage in `notes` (not cleared here, like the Python's mover.path_psrs).
pub fn movement_options(b: &Battle, u: UnitId, standup_mp: Option<i64>, entry_edge: Option<&[String]>, backward: bool, notes: &mut PathNotes) -> Vec<StateKey> {
    movement_options_snap(b, u, standup_mp, entry_edge, backward, notes).into_iter().map(|y| y.0).collect()
}

/// A yielded state with the PSR count and hazard the notes held at the moment it was yielded (reduced_options reads them
/// then: a state reached again later by a way with fewer PSRs holds the fewest only afterwards).
pub type Yielded = (StateKey, i64, f64);

pub fn movement_options_snap(b: &Battle, u: UnitId, standup_mp: Option<i64>, entry_edge: Option<&[String]>, backward: bool, notes: &mut PathNotes) -> Vec<Yielded> {
    let states = movement_options_all(b, u, standup_mp, entry_edge, backward, notes);
    if crate::fire_modes::walk_only_for_unjam(&b.units[u]) {
        return states.into_iter().filter(|st| st.0 .4 == "Stand Still" || st.0 .4 == "Walk").collect();
    }
    states
}

fn movement_options_all(b: &Battle, u: UnitId, standup_mp: Option<i64>, entry_edge: Option<&[String]>, backward: bool, notes: &mut PathNotes) -> Vec<Yielded> {
    let m = &b.units[u];
    if let Some(edge) = entry_edge {
        return entry_options(b, u, edge, notes);
    }
    let mut out: Vec<Yielded> = Vec::new();
    let (sx, sy, start_facing) = hex_geometry::state_from_label(m.hex.as_deref().unwrap(), &m.facing).unwrap();
    let mut standup = standup_mp;
    let (mut starts, run_budget, jump_mp, walk, backward_mp): (Vec<i64>, i64, i64, i64, Option<i64>);
    if standup_mp.is_none() {
        let w = compute_walk_mp(m);
        walk = w;
        starts = vec![start_facing];
        run_budget = compute_running_mp(m);
        jump_mp = crate::water::jump_mp(b, u);
        backward_mp = if backward && w > 0 { Some(w) } else { None };
    } else {
        walk = 0;
        starts = (0..6).collect();
        run_budget = standup_mp.unwrap();
        jump_mp = 0;
        backward_mp = None;
    }
    let mode_for = |spent: i64, standup: bool| -> &'static str {
        if standup { "Run" } else { classify_movement_mode(spent, walk) }
    };
    let standup_flag = standup_mp.is_some();
    let level_limit = crate::mech_state::ground_limit(m);
    let mut seen: HashSet<StateKey> = HashSet::default();
    let blocked = blocked_hexes(b, u);
    let mut mode_standup_flag = standup_flag;
    if m.jump_only == Some(true) {
        // Bogged down after ground movement (TO:AR p.60): stay, or jump out.
        starts = vec![];
        standup = Some(0);
        // mode_for was bound with standup_mp None: classify as for a ground move
        mode_standup_flag = false;
        out.push(((sx, sy, start_facing, 0, mode_for(0, false), 0), 0, 0.0));
    }
    for f0 in &starts {
        let table = b.movement_table(sx, sy, *f0, run_budget, backward_mp, level_limit, &blocked);
        for ((x, y, facing), col) in &table.entries {
            let psrs = table.psrs.as_ref().and_then(|p| p.get(&(*x, *y, *facing)));
            let hz = table.hazards.get(&(*x, *y, *facing));
            for (mp_spent, fc) in col {
                let key: StateKey = (*x, *y, *facing, *fc, mode_for(*mp_spent, mode_standup_flag), *mp_spent);
                if let Some(p) = psrs {
                    notes.note(key, p[mp_spent], hz.and_then(|h| h.get(mp_spent)).copied().unwrap_or(0.0));
                }
                if seen.insert(key) {
                    out.push((key, notes.psrs.get(&key).copied().unwrap_or(0), notes.hazard.get(&key).copied().unwrap_or(0.0)));
                }
            }
        }
    }
    if standup.is_none() {
        let seen_s: HashSet<(i64, i64, i64, i64, String, i64)> = seen.iter().map(|k| (k.0, k.1, k.2, k.3, k.4.to_string(), k.5)).collect();
        if let Some(got) = crate::ranged_combat::minimum_move(b, u, sx, sy, start_facing, run_budget, &seen_s, level_limit) {
            let key: StateKey = (got.0, got.1, got.2, got.3, mode_str(&got.4), got.5);
            // _minimum_move notes its PSRs itself (only on a board that has PSR terrain)
            if terrain_rules::has_psr_terrain(&b.board) {
                let here = &b.board.hexes[m.hex.as_deref().unwrap()];
                let label = hex_geometry::hex_label(key.0, key.1).unwrap();
                let info = &b.board.hexes[&label];
                notes.note(key, terrain_rules::step_psrs(Some(here), info, false), terrain_rules::step_hazard(info, 2));
            }
            out.push((key, notes.psrs.get(&key).copied().unwrap_or(0), notes.hazard.get(&key).copied().unwrap_or(0.0)));
        }
    }
    // on mechanical jump boosters the unit cannot steer in flight: it lands facing the way it took off (TO:AUE p.105)
    let boosters = m.jump_boosters_on;
    if jump_mp > 0 {
        for ((x, y, facing), fc) in crate::combat::build_jump_states(&b.board, sx, sy, jump_mp).unwrap() {
            if boosters && facing != start_facing {
                continue;
            }
            let k = (x, y, facing, fc, "Jump", jump_mp);
            out.push((k, notes.psrs.get(&k).copied().unwrap_or(0), notes.hazard.get(&k).copied().unwrap_or(0.0)));
        }
        for facing in (0..6).filter(|f| !boosters || *f == start_facing) {
            let k = (sx, sy, facing, 0, "Jump", 1);
            out.push((k, notes.psrs.get(&k).copied().unwrap_or(0), notes.hazard.get(&k).copied().unwrap_or(0.0)));
        }
    }
    out
}

fn entry_options(b: &Battle, u: UnitId, edge: &[String], notes: &mut PathNotes) -> Vec<Yielded> {
    let m = &b.units[u];
    let (walk, run) = (compute_walk_mp(m), compute_running_mp(m));
    let mut seen: HashSet<StateKey> = HashSet::default();
    let mut out = Vec::new();
    let blocked = blocked_hexes(b, u);
    let level_limit = crate::mech_state::ground_limit(m);
    for label in edge {
        let Some(info) = b.board.hexes.get(label) else { continue };
        let (ex, ey) = hex_geometry::parse_hex_label(label).unwrap();
        if blocked.contains(&(ex, ey)) {
            continue;
        }
        let Some(cost) = terrain_rules::step_cost(None, info, terrain_rules::max_level_change(false, false), false).filter(|c| *c <= run) else { continue };
        let (ea, er) = terrain_rules::step_psrs(None, info, false);
        let eh = terrain_rules::step_hazard(info, 2);
        for f0 in 0..6 {
            let table = b.movement_table(ex, ey, f0, run - cost, None, level_limit, &blocked);
            for ((x, y, facing), col) in &table.entries {
                let psrs = table.psrs.as_ref().and_then(|p| p.get(&(*x, *y, *facing)));
                let hz = table.hazards.get(&(*x, *y, *facing));
                for (spent, fc) in col {
                    let total = spent + cost;
                    let key: StateKey = (*x, *y, *facing, fc + 1, classify_movement_mode(total, walk), total);
                    if let Some(p) = psrs {
                        let (a, r) = p[spent];
                        notes.note(key, (a + ea, r + er), hz.and_then(|h| h.get(spent)).copied().unwrap_or(0.0) + eh);
                    }
                    if seen.insert(key) {
                        out.push((key, notes.psrs.get(&key).copied().unwrap_or(0), notes.hazard.get(&key).copied().unwrap_or(0.0)));
                    }
                }
            }
        }
    }
    out
}

/// reduced_options: the reachable end states after the Section 5c reduction, in a stable order. `exclude`: the hexes
/// occupied by other units (cannot be ended in). Returns the states and the PSR / hazard notes of this search.
pub fn reduced_options(b: &Battle, u: UnitId, exclude: &HashSet<(i64, i64)>, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> (Vec<StateKey>, PathNotes) {
    let void = crate::equipment_systems::active_stealth(&b.units[u]).contains(&"void_signature");
    let mut notes = PathNotes::default();
    // best: IndexMap keyed (x, y, facing, mode, fc>0 | (fc, mp), hazard, psrs)
    type K = (i64, i64, i64, &'static str, i64, i64, u64, i64);
    let mut best: IndexMap<K, StateKey> = IndexMap::default();
    let all = movement_options_snap(b, u, standup_mp, entry_edge, true, &mut notes);
    // the notes as they stand when each state is read (see Yielded), kept for the dominance step below
    let mut snap: HashMap<StateKey, (i64, f64)> = HashMap::default();
    for (st, n, h) in all {
        snap.insert(st, (n, h));
        let (x, y, facing, fc, mode, mp_spent) = st;
        if exclude.contains(&(x, y)) {
            continue;
        }
        let (k4, k5) = if void { (fc, mp_spent) } else { ((fc > 0) as i64, 0) };
        let (n, h) = (n, h);
        let key: K = (x, y, facing, mode, k4, k5, if h == 0.0 { 0 } else { h.to_bits() }, n);
        match best.get(&key) {
            Some(cur) if !(fc > cur.3 || (fc == cur.3 && mp_spent < cur.5)) => {}
            _ => {
                best.insert(key, st);
            }
        }
    }
    if notes.psrs.is_empty() && notes.hazard.is_empty() {
        return (best.into_values().collect(), notes);
    }
    // by base (everything but hazard and PSR count): a path with fewer PSRs and no more hazard is no worse
    let mut by_base: IndexMap<(i64, i64, i64, &'static str, i64, i64), Vec<((f64, i64), StateKey)>> = IndexMap::default();
    for (key, st) in &best {
        let h = snap[st].1;
        by_base.entry((key.0, key.1, key.2, key.3, key.4, key.5)).or_default().push(((h, key.7), *st));
    }
    let mut kept = Vec::new();
    for variants in by_base.values() {
        for ((h, n), st) in variants {
            let dominated = variants.iter().any(|((g, m), o)| (*m, *g) != (*n, *h) && *m <= *n && *g <= *h && o.3 >= st.3 && o.5 <= st.5);
            if dominated {
                continue;
            }
            kept.push(*st);
        }
    }
    (kept, notes)
}

/// The hexes a mover may not end in (occupied_hexes): other_unit_hexes when set, else just the other unit's hex.
pub fn occupied_hexes(b: &Battle, mover: UnitId, other: UnitId) -> HashSet<(i64, i64)> {
    let labels: Vec<String> = match &b.units[mover].other_unit_hexes {
        Some(serde_json::Value::Array(a)) => a.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect(),
        Some(serde_json::Value::String(s)) => vec![s.clone()],
        _ => b.units[other].hex.iter().cloned().collect(),
    };
    labels.iter().filter(|l| !l.is_empty()).map(|l| hex_geometry::parse_hex_label(l).unwrap()).collect()
}

pub type StateXY = State;
