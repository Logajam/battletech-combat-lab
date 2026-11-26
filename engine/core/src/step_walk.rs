//! STEP WALKER: a ground move one step at a time (forward, backward, turn left, turn right), each step checked by the same rules
//! the movement DP (`pathfinder.rs`) uses. New 2026-11-24 (session 36). It is the missing piece PROJECT_MAP Section 4 calls
//! `walk_path`: a route a person drew (waypoints that must be walked as drawn, a route that avoids a hazard or a hex), a bot that
//! builds its own path (the BTTT-style bot), and per-step move events all need "what does ONE step do from here?".
//!
//! ONE SET OF RULES: a step's cost, PSRs and hazard come from `terrain_rules::step_cost`, `step_psrs`, `turn_psrs` and `step_hazard`,
//! the same calls `pathfinder::build_terrain_psr` makes, and the MP budget and the forward-count bookkeeping mirror it. The DP is
//! the standard: `tests/step_walk.rs` replays every route the DP can rebuild and walks the whole step graph from several starts,
//! and the two must agree on every (hex, facing, MP) reachable, with the same PSR and hazard totals.
//!
//! NOT HERE: jumping (no route: a jump goes to its end hex), standing up, entering from off the board, charges. Those keep their
//! own code. Nothing here rolls dice, asks a bot or changes a unit: it reads the board and returns new values.
use crate::board_parser::Board;
use crate::fasthash::HashSet;
use crate::hex_geometry::FACING_DELTAS;
use crate::pathfinder::Hex;
use crate::terrain_rules::{self, GroundLimit};

/// One step of a ground move. A turn is one MP and one sixth of a circle; +1 facing is a turn to the right (the bridge's
/// "turn_right"), -1 to the left.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Step {
    Forward,
    Backward,
    TurnLeft,
    TurnRight,
    /// Lateral shifts (tripod Core p.236, quad p.238; MegaMek LATERAL_*): into the hex at the front-left / front-right hexside, or
    /// (the "back" ones, backward movement) the rear-left / rear-right one, +1 MP, the facing kept.
    LateralLeft,
    LateralRight,
    BackLateralLeft,
    BackLateralRight,
    /// A tripod turns any number of hexsides for the one MP (Core p.237): two left, two right, or right round.
    TurnLeft2,
    TurnRight2,
    TurnAbout,
}

impl Step {
    pub const ALL: [Step; 11] = [
        Step::Forward,
        Step::Backward,
        Step::TurnLeft,
        Step::TurnRight,
        Step::LateralLeft,
        Step::LateralRight,
        Step::BackLateralLeft,
        Step::BackLateralRight,
        Step::TurnLeft2,
        Step::TurnRight2,
        Step::TurnAbout,
    ];

    /// For a lateral shift: (hexside offset from the facing, is it backward movement).
    fn lateral(self) -> Option<(i64, bool)> {
        match self {
            Step::LateralLeft => Some((-1, false)),
            Step::LateralRight => Some((1, false)),
            Step::BackLateralLeft => Some((-2, true)),
            Step::BackLateralRight => Some((2, true)),
            _ => None,
        }
    }

    /// The names the MegaMek bridge uses.
    pub fn name(self) -> &'static str {
        match self {
            Step::Forward => "forward",
            Step::Backward => "backward",
            Step::TurnLeft => "turn_left",
            Step::TurnRight => "turn_right",
            Step::LateralLeft => "lateral_left",
            Step::LateralRight => "lateral_right",
            Step::BackLateralLeft => "lateral_left_backwards",
            Step::BackLateralRight => "lateral_right_backwards",
            Step::TurnLeft2 => "turn_left_2",
            Step::TurnRight2 => "turn_right_2",
            Step::TurnAbout => "turn_about",
        }
    }

    pub fn from_name(s: &str) -> Option<Step> {
        Step::ALL.into_iter().find(|st| st.name() == s)
    }
}

/// Why a step was refused.
#[derive(Clone, Debug, PartialEq)]
pub enum StepError {
    /// the hex is off the board or blocked (a mobile enemy stands there)
    Blocked,
    /// the terrain rules do not allow the step (impassable, too many levels, a roof, a backward level change, ...)
    NotAllowed,
    /// the step is allowed but costs more MP than are left
    OutOfMp { needed: i64, left: i64 },
    /// no backward movement budget was given for this unit
    NoBackward,
    /// this unit cannot make a lateral shift (only a tripod or quad with no leg destroyed can)
    NoLateral,
    /// this unit cannot turn several hexsides for one MP (only a tripod with no leg destroyed can)
    NoFreeFacing,
}

impl std::fmt::Display for StepError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            StepError::Blocked => write!(f, "that hex is off the board or blocked"),
            StepError::NotAllowed => write!(f, "the terrain does not allow that step"),
            StepError::OutOfMp { needed, left } => write!(f, "that step costs {} MP and only {} are left", needed, left),
            StepError::NoBackward => write!(f, "this unit cannot move backward"),
            StepError::NoLateral => write!(f, "this unit cannot shift sideways"),
            StepError::NoFreeFacing => write!(f, "this unit cannot turn more than one hexside for 1 MP"),
        }
    }
}

/// Where a move stands after some steps: the position and everything the DP counts along the way.
#[derive(Clone, Debug, PartialEq)]
pub struct WalkState {
    pub x: i64,
    pub y: i64,
    pub facing: i64,
    /// MP spent so far
    pub mp: i64,
    /// the last move's direction: 0 none yet, +1 forward, -1 backward (turns leave it alone)
    pub last: i64,
    /// has the move gone backward yet (after that the backward budget is the limit)
    pub used_back: bool,
    /// hexes moved in a straight run since the direction last changed (what TMM counts; the DP's "forward count")
    pub forward_count: i64,
    /// PSRs the route forces whatever the mode, and PSRs only a run forces
    pub always_psrs: i64,
    pub run_psrs: i64,
    /// expected damage of the hexes entered (magma, hazardous liquid)
    pub hazard: f64,
}

impl WalkState {
    pub fn state(&self) -> crate::hex_geometry::State {
        (self.x, self.y, self.facing)
    }

    /// The DP's search key (position, facing, last direction, gone backward): two walks that agree on it and on MP have the same
    /// possible futures.
    pub fn key(&self) -> (i64, i64, i64, i64, bool) {
        (self.x, self.y, self.facing, self.last, self.used_back)
    }
}

/// A unit's movement limits on one board: build one, then step with it.
pub struct Walker<'a> {
    pub board: &'a Board,
    /// hexes no ground step may enter (a mobile enemy's)
    pub blocked: &'a HashSet<Hex>,
    pub level_limit: GroundLimit,
    /// total MP of the move (walk, or run when the move may run)
    pub budget: i64,
    /// the MP a move that has gone backward may spend (walking only); None: no backward steps
    pub backward_mp: Option<i64>,
}

impl<'a> Walker<'a> {
    /// `pathfinder::hex_info`: None for a blocked hex or one off the board.
    fn open(&self, x: i64, y: i64) -> Option<&'a crate::board_parser::Hex> {
        if self.blocked.contains(&(x, y)) {
            return None;
        }
        self.board.info_xy(x, y)
    }

    /// The start of a move: standing at (x, y) facing `facing` (0-5) with nothing spent.
    pub fn start(&self, x: i64, y: i64, facing: i64) -> Result<WalkState, String> {
        if !(0..=5).contains(&facing) {
            return Err(format!("facing must be 0-5, got {}", facing));
        }
        if self.open(x, y).is_none() {
            return Err(format!("start hex ({}, {}) is not on the board", x, y));
        }
        Ok(WalkState { x, y, facing, mp: 0, last: 0, used_back: false, forward_count: 0, always_psrs: 0, run_psrs: 0, hazard: 0.0 })
    }

    /// One step from `st`: the new state, or why not.
    pub fn step(&self, st: &WalkState, step: Step) -> Result<WalkState, StepError> {
        // once a move has gone backward the backward budget is its limit (pathfinder: `budget`)
        let budget = if st.used_back { self.backward_mp.unwrap_or(self.budget) } else { self.budget };
        let (dx, dy) = FACING_DELTAS[st.facing as usize];
        match step {
            Step::Forward | Step::Backward | Step::LateralLeft | Step::LateralRight | Step::BackLateralLeft | Step::BackLateralRight => {
                let lateral = step.lateral();
                if lateral.is_some() && !self.level_limit.lateral {
                    return Err(StepError::NoLateral);
                }
                let backward = step == Step::Backward || lateral.is_some_and(|l| l.1);
                let limit = if backward {
                    // backward moves have their own, smaller budget; none given means none allowed
                    self.backward_mp.ok_or(StepError::NoBackward)?
                } else {
                    budget
                };
                let (tx, ty) = match lateral {
                    Some((k, _)) => {
                        let (lx, ly) = FACING_DELTAS[((st.facing + k).rem_euclid(6)) as usize];
                        (st.x + lx, st.y + ly)
                    }
                    None if backward => (st.x - dx, st.y - dy),
                    None => (st.x + dx, st.y + dy),
                };
                let there = self.open(tx, ty).ok_or(StepError::Blocked)?;
                let here = self.board.info_xy(st.x, st.y);
                let cost = terrain_rules::step_cost(here, there, self.level_limit, backward).ok_or(StepError::NotAllowed)? + if lateral.is_some() { crate::pathfinder::LATERAL_SHIFT_EXTRA_MP } else { 0 };
                if st.mp + cost > limit {
                    return Err(StepError::OutOfMp { needed: cost, left: (limit - st.mp).max(0) });
                }
                let (always, run_only) = terrain_rules::step_psrs(here, there, backward);
                let (dir, same_dir) = if backward { (-1, st.last <= 0) } else { (1, st.last >= 0) };
                Ok(WalkState {
                    x: tx,
                    y: ty,
                    facing: st.facing,
                    mp: st.mp + cost,
                    last: dir,
                    used_back: st.used_back || backward,
                    forward_count: if same_dir { st.forward_count + 1 } else { 1 },
                    always_psrs: st.always_psrs + always,
                    run_psrs: st.run_psrs + run_only,
                    hazard: st.hazard + terrain_rules::step_hazard(there, 2),
                })
            }
            Step::TurnLeft | Step::TurnRight | Step::TurnLeft2 | Step::TurnRight2 | Step::TurnAbout => {
                // turning more than one hexside for the 1 MP is a tripod's (Core p.237)
                let sides: i64 = match step {
                    Step::TurnLeft => -1,
                    Step::TurnRight => 1,
                    Step::TurnLeft2 => -2,
                    Step::TurnRight2 => 2,
                    _ => 3,
                };
                if sides.abs() > 1 && !self.level_limit.free_facing {
                    return Err(StepError::NoFreeFacing);
                }
                let cost = 1;
                if st.mp + cost > budget {
                    return Err(StepError::OutOfMp { needed: 1, left: (budget - st.mp).max(0) });
                }
                let (always, run_only) = terrain_rules::turn_psrs(self.board.info_xy(st.x, st.y).ok_or(StepError::Blocked)?);
                let facing = (st.facing + sides).rem_euclid(6);
                Ok(WalkState {
                    facing,
                    mp: st.mp + cost,
                    always_psrs: st.always_psrs + always,
                    run_psrs: st.run_psrs + run_only,
                    ..st.clone()
                })
            }
        }
    }

    /// Every step that is legal from `st`, with the state it leads to (what a screen highlights, what a bot chooses among).
    pub fn legal_steps(&self, st: &WalkState) -> Vec<(Step, WalkState)> {
        Step::ALL.into_iter().filter_map(|s| self.step(st, s).ok().map(|n| (s, n))).collect()
    }

    /// Walks `steps` from `st`. Ok: the state after every step (the first is the one after step 1). Err: the index of the first
    /// refused step and why, so a screen can colour the route up to there.
    pub fn walk(&self, st: &WalkState, steps: &[Step]) -> Result<Vec<WalkState>, (usize, StepError)> {
        let mut out = Vec::with_capacity(steps.len());
        let mut cur = st.clone();
        for (i, &s) in steps.iter().enumerate() {
            cur = self.step(&cur, s).map_err(|e| (i, e))?;
            out.push(cur.clone());
        }
        Ok(out)
    }
}

/// The steps of a route the DP rebuilt (`MovementTable::path`: (step name, state after, MP after)), as `Step`s from `start`:
/// the DP's "turn" has no direction, so it is read from the change of facing.
pub fn steps_of_path(start_facing: i64, path: &[(&'static str, crate::hex_geometry::State, i64)]) -> Vec<Step> {
    let mut facing = start_facing;
    let mut out = Vec::with_capacity(path.len());
    for &(name, (_, _, f), _) in path {
        match name {
            "forward" => out.push(Step::Forward),
            "backward" => out.push(Step::Backward),
            "lateral_left" => out.push(Step::LateralLeft),
            "lateral_right" => out.push(Step::LateralRight),
            "lateral_left_back" => out.push(Step::BackLateralLeft),
            "lateral_right_back" => out.push(Step::BackLateralRight),
            _ => {
                // a turn: the DP's "turn" has no direction, so it is read from the change of facing (a tripod's may be 2 or 3 hexsides)
                out.push(match (f - facing).rem_euclid(6) {
                    1 => Step::TurnRight,
                    2 => Step::TurnRight2,
                    3 => Step::TurnAbout,
                    4 => Step::TurnLeft2,
                    _ => Step::TurnLeft,
                });
            }
        }
        facing = f;
    }
    out
}

/// A route as text for the MOVE_PATH event: one entry per step, "HEX/S/MP" - the hex after the step, the step (F forward, B backward,
/// L / R a turn, E entering the board from its edge) and the MP spent so far - joined by spaces. `path` is what
/// `MovementTable::path` gives (`ranged_combat::path_to`); a turn's direction is read from the change of facing, starting
/// from `start_facing`.
pub fn route_text(path: &[(&'static str, crate::hex_geometry::State, i64)], start_facing: i64) -> String {
    let mut facing = start_facing;
    let mut out = Vec::with_capacity(path.len());
    for &(name, (x, y, f), mp) in path {
        let code = match name {
            "forward" => "F",
            "backward" => "B",
            "enter" => "E",
            // lateral shifts: SL / SR forward, SBL / SBR the backward ones
            "lateral_left" => "SL",
            "lateral_right" => "SR",
            "lateral_left_back" => "SBL",
            "lateral_right_back" => "SBR",
            // a turn; a tripod's several hexsides are one entry (R / L by the shorter way round)
            _ => {
                if (f - facing).rem_euclid(6) <= 3 {
                    "R"
                } else {
                    "L"
                }
            }
        };
        facing = f;
        out.push(format!("{}/{}/{}", crate::hex_geometry::hex_label(x, y).unwrap_or_default(), code, mp));
    }
    out.join(" ")
}
