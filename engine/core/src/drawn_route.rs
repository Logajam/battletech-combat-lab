//! DRAWN ROUTES (Daniel, 2026-11-24: "Follow the route as drawn. I suspect the engine might not be avoiding hazards, simply accepting
//! their cost to get to desired hexes instead of looking for a way around the hazard. Follow as drawn lets the humans avoid hazards at
//! least."). This replaces the 2026-11-22 ruling that the unit takes the engine's own best route to the last waypoint.
//!
//! A person draws a ground move through numbered waypoints on the play page. The route is: from the unit's start, the cheapest way
//! (the movement DP, `pathfinder.rs`) to waypoint 1, then from there to waypoint 2, and so on, then the turns that finish it facing
//! the chosen way. The page draws that route, `way_query` (play_session.rs) shows what it costs and where it can go on from its end,
//! and when the move is committed THIS SAME route becomes the pick's `route`: the unit walks exactly those steps
//! (`orchestrator::walk_path`), rolling every terrain PSR and hazard where the route puts it. Mode, hexes moved (so TMM), movement
//! heat, PSRs and hazard are those of the route walked, not of some other route to the same hex.
//!
//! ONE CODE PATH: the route drawn, the numbers shown and the route walked all come from `chain`, `reach` and `finish` here, and every
//! number is read off a replay of the steps through `step_walk::Walker` (the DP's own rules, `tests/step_walk.rs`), so what the page
//! shows cannot differ from what the engine does. Nothing here rolls dice or changes a unit.
//!
//! Ground moves only: no jumps, stand-ups, entries from the edge or charges. Backward steps are not drawn (the DP table is built
//! without them, as before).
use std::collections::BTreeMap;

use crate::battle::{Battle, UnitId};
use crate::fasthash::HashSet;
use crate::hex_geometry::{self, State};
use crate::mech_state::{compute_running_mp, compute_walk_mp, ground_level_limited, is_superheavy};
use crate::pathfinder::{build_movement_table, Hex, MovementTable};
use crate::ranged_combat::{blocked_set, Pick};
use crate::step_walk::{steps_of_path, Step, WalkState, Walker};
use crate::terrain_rules::{max_level_change, GroundLimit};

/// A route as the DP gives it: (step name, state after, MP spent so far).
pub type Path = Vec<(&'static str, State, i64)>;

/// What a unit's ground move may do on this board, gathered once: its walls (a mobile enemy's hex), level limit and MP.
pub struct UnitWalk {
    pub blocked: HashSet<Hex>,
    pub level_limit: GroundLimit,
    pub walk: i64,
    pub run: i64,
    /// where the unit stands now: (x, y, facing)
    pub start: State,
}

impl UnitWalk {
    /// None: the unit is not on the map.
    pub fn of(b: &Battle, u: UnitId) -> Option<UnitWalk> {
        let m = &b.units[u];
        let start = hex_geometry::state_from_label(m.hex.as_deref()?, &m.facing).ok()?;
        Some(UnitWalk {
            blocked: blocked_set(&m.blocked_hex),
            level_limit: crate::mech_state::ground_limit(m),
            walk: compute_walk_mp(m),
            run: compute_running_mp(m),
            start,
        })
    }

    /// The walker for this unit's move (the same limits `ranged_combat::path_to` searches with).
    pub fn walker<'a>(&'a self, b: &'a Battle) -> Walker<'a> {
        Walker { board: &b.board, blocked: &self.blocked, level_limit: self.level_limit, budget: self.run, backward_mp: if self.walk > 0 { Some(self.walk) } else { None } }
    }

    fn table(&self, b: &Battle, x: i64, y: i64, facing: i64, budget: i64) -> Option<MovementTable> {
        self.table_back(b, x, y, facing, budget, 0)
    }

    /// The table for a leg that may back up (Core p.51: backward steps use walking points only, so the leg's backward steps stop at the
    /// walk points still unspent, `walk_left`; 0 = no backing up, the way every leg was drawn before the Back up button).
    fn table_back(&self, b: &Battle, x: i64, y: i64, facing: i64, budget: i64, walk_left: i64) -> Option<MovementTable> {
        build_movement_table(x, y, facing, budget, Some(&b.board), if walk_left > 0 { Some(walk_left) } else { None }, self.level_limit, true, &self.blocked).ok()
    }
}

/// Walks `path` from the unit's start through the step walker: the state at its end (hexes moved, MP, PSRs, hazard) and the steps.
/// None if the walker refuses a step (it never does for a route the DP built: `tests/step_walk.rs`).
pub fn replay(b: &Battle, uw: &UnitWalk, path: &Path) -> Option<(WalkState, Vec<Step>)> {
    let steps = steps_of_path(uw.start.2, path);
    let w = uw.walker(b);
    let start = w.start(uw.start.0, uw.start.1, uw.start.2).ok()?;
    let states = w.walk(&start, &steps).ok()?;
    Some((states.last().cloned().unwrap_or(start), steps))
}

/// The DP's name for a step (`MovementTable::path`): "turn" has no direction, the lateral shifts name their side.
fn step_name(s: Step) -> &'static str {
    match s {
        Step::Forward => "forward",
        Step::Backward => "backward",
        Step::LateralLeft => "lateral_left",
        Step::LateralRight => "lateral_right",
        Step::BackLateralLeft => "lateral_left_back",
        Step::BackLateralRight => "lateral_right_back",
        Step::TurnLeft | Step::TurnRight | Step::TurnLeft2 | Step::TurnRight2 | Step::TurnAbout => "turn",
    }
}

/// A route given as steps, back in the DP's shape ((name, state after, MP so far)): what `walk_path` walks. None if a step is refused.
pub fn path_of_steps(b: &Battle, uw: &UnitWalk, steps: &[Step]) -> Option<Path> {
    let w = uw.walker(b);
    let start = w.start(uw.start.0, uw.start.1, uw.start.2).ok()?;
    let states = w.walk(&start, steps).ok()?;
    Some(steps.iter().zip(states.iter()).map(|(s, st)| (step_name(*s), st.state(), st.mp)).collect())
}

/// The route through the waypoints: where it ends, how it faces, what it has cost and every step.
pub struct Chain {
    pub at: (i64, i64),
    pub facing: i64,
    pub spent: i64,
    pub path: Path,
}

/// The cheapest route from the unit's start through every waypoint in turn (any facing at each; the cheapest total wins, the lowest facing
/// on a tie). Err: why not, in words for the page.
pub fn chain(b: &Battle, uw: &UnitWalk, waypoints: &[(i64, i64)]) -> Result<Chain, String> {
    if waypoints.is_empty() {
        return Err("which waypoints?".to_string());
    }
    chain_back(b, uw, waypoints, &[])
}

/// `chain`, where leg i (the way to waypoint i) may back up if `backs[i]` (the Back up button was on when it was drawn). No waypoints is
/// allowed: the chain is then the unit's own start (the page asks for the places it can back up to from where it stands).
pub fn chain_back(b: &Battle, uw: &UnitWalk, waypoints: &[(i64, i64)], backs: &[bool]) -> Result<Chain, String> {
    // where we stand at each stage: facing -> (MP spent, the route so far)
    let mut at = (uw.start.0, uw.start.1);
    let mut cur: BTreeMap<i64, (i64, Path)> = BTreeMap::new();
    cur.insert(uw.start.2, (0, vec![]));
    for (i, &(wx, wy)) in waypoints.iter().enumerate() {
        let back = backs.get(i).copied().unwrap_or(false);
        let mut next: BTreeMap<i64, (i64, Path)> = BTreeMap::new();
        for (f, (spent, route)) in &cur {
            let Some(t) = uw.table_back(b, at.0, at.1, *f, uw.run - spent, if back { uw.walk - spent } else { 0 }) else { continue };
            for f2 in 0..6 {
                let state = (wx, wy, f2);
                let Some(col) = t.entries.get(&state) else { continue };
                let Some(&mp) = col.keys().min() else { continue };
                if next.get(&f2).is_some_and(|(have, _)| *have <= spent + mp) {
                    continue;
                }
                let mut r = route.clone();
                r.extend(t.path(state, mp).into_iter().map(|(name, st, mm)| (name, st, spent + mm)));
                next.insert(f2, (spent + mp, r));
            }
        }
        if next.is_empty() {
            return Err("that hex cannot be reached through the waypoints with the points you have".to_string());
        }
        cur = next;
        at = (wx, wy);
    }
    let (facing, (spent, path)) = cur.into_iter().min_by_key(|(_, (spent, _))| *spent).expect("a route");
    Ok(Chain { at, facing, spent, path })
}

/// The numbers of one way to end the move.
pub struct End {
    pub state: State,
    pub hex: String,
    pub facing: &'static str,
    pub mode: &'static str,
    pub mp: i64,
    /// the whole route: the chain, then the way on from its end
    pub path: Path,
    pub walked: WalkState,
    pub steps: Vec<Step>,
}

/// Every (hex, facing, mode) the move can end in from the end of the chain with the points left, the cheapest of each, with the whole
/// route (the chain, then the way on) and its numbers read off a replay.
pub fn reach(b: &Battle, uw: &UnitWalk, chain: &Chain) -> Vec<End> {
    reach_back(b, uw, chain, false)
}

/// `reach`, with the way on from the chain's end allowed to back up (`back`).
pub fn reach_back(b: &Battle, uw: &UnitWalk, chain: &Chain, back: bool) -> Vec<End> {
    let Some(t) = uw.table_back(b, chain.at.0, chain.at.1, chain.facing, uw.run - chain.spent, if back { uw.walk - chain.spent } else { 0 }) else { return vec![] };
    let mut best: BTreeMap<(i64, i64, i64, &'static str), (i64, State, i64)> = BTreeMap::new();
    for (&(x, y, f2), col) in &t.entries {
        for &mp in col.keys() {
            let total = chain.spent + mp;
            let mode = crate::combat::classify_movement_mode(total, uw.walk);
            let e = best.entry((x, y, f2, mode)).or_insert((i64::MAX, (x, y, f2), mp));
            if total < e.0 {
                *e = (total, (x, y, f2), mp);
            }
        }
    }
    let mut out = Vec::with_capacity(best.len());
    for (&(x, y, f2, mode), &(total, state, leg_mp)) in &best {
        let mut path = chain.path.clone();
        path.extend(t.path(state, leg_mp).into_iter().map(|(name, st, mm)| (name, st, chain.spent + mm)));
        let Some((walked, steps)) = replay(b, uw, &path) else { continue };
        let (Ok(hex), Ok(facing)) = (hex_geometry::hex_label(x, y), hex_geometry::facing_to_compass(f2)) else { continue };
        out.push(End { state, hex, facing, mode, mp: total, path, walked, steps });
    }
    out
}

/// What the page committed: the pick (with its route) and the PSRs and hazard of that route (what `PathGate` carries).
pub struct Drawn {
    pub pick: Pick,
    pub psrs: i64,
    pub hazard: f64,
}

/// The route through `waypoints` finished facing `facing` (0-5) in `mode` ("Walk" or "Run"), as the pick the unit will walk. Err: in words
/// for the page.
pub fn finish(b: &Battle, mover: UnitId, waypoints: &[(i64, i64)], facing: i64, mode: &str) -> Result<Drawn, String> {
    finish_back(b, mover, waypoints, &[], false, facing, mode)
}

/// `finish` for a route drawn with the Back up button: `backs` per leg, `back_reach` for the way on from the last waypoint. No waypoints is
/// allowed when `back_reach` is on (a move that only backs up from where the unit stands).
pub fn finish_back(b: &Battle, mover: UnitId, waypoints: &[(i64, i64)], backs: &[bool], back_reach: bool, facing: i64, mode: &str) -> Result<Drawn, String> {
    let uw = UnitWalk::of(b, mover).ok_or("the unit is not on the map")?;
    let ch = chain_back(b, &uw, waypoints, backs)?;
    let t = uw.table_back(b, ch.at.0, ch.at.1, ch.facing, uw.run - ch.spent, if back_reach { uw.walk - ch.spent } else { 0 }).ok_or("no way on from the last waypoint")?;
    let state = (ch.at.0, ch.at.1, facing);
    // the cheapest way to end here facing that way whose total puts the move in the mode asked for (a longer one spins on the spot)
    let mp = t
        .entries
        .get(&state)
        .and_then(|col| col.keys().copied().filter(|mp| crate::combat::classify_movement_mode(ch.spent + mp, uw.walk) == mode).min())
        .ok_or_else(|| format!("that facing in {} mode is not possible on this route", mode))?;
    let mut path = ch.path.clone();
    path.extend(t.path(state, mp).into_iter().map(|(name, st, mm)| (name, st, ch.spent + mm)));
    let (walked, steps) = replay(b, &uw, &path).ok_or("the route is not walkable")?;
    let mode_name = crate::combat::classify_movement_mode(walked.mp, uw.walk);
    let run = mode_name == "Run";
    Ok(Drawn {
        pick: Pick {
            hex: hex_geometry::hex_label(ch.at.0, ch.at.1)?,
            facing: hex_geometry::facing_to_compass(facing)?.to_string(),
            mode: mode_name.to_string(),
            fc: walked.forward_count,
            mp_spent: walked.mp,
            charge: false,
            dfa: false,
            route: Some(steps),
        },
        psrs: walked.always_psrs + if run { walked.run_psrs } else { 0 },
        hazard: walked.hazard,
    })
}

/// The PSRs and hazard of the route a pick carries (None: it carries none), what `orchestrator::walk_path` is to roll: the route's own, not
/// the search's cheapest to the same end.
pub fn route_gate(b: &Battle, mover: UnitId, pick: &Pick) -> Option<(i64, f64)> {
    let steps = pick.route.as_ref()?;
    let uw = UnitWalk::of(b, mover)?;
    let path = path_of_steps(b, &uw, steps)?;
    let (walked, _) = replay(b, &uw, &path)?;
    Some((walked.always_psrs + if pick.mode == "Run" { walked.run_psrs } else { 0 }, walked.hazard))
}
