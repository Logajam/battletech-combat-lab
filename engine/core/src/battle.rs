//! The battle: everything that carries from one moment to the next (INTEGRATION__STATE.md). There are NO globals
//! (RUST_PORT trap 6): the units, the board, the dice, the settings, the log and every table the Python keeps in a
//! module live here, and the engine's functions take `&mut Battle` and a `UnitId`.

use indexmap::{IndexMap, IndexSet};

use crate::board_parser::Board;
use crate::config::Config;
use crate::equipment::EquipmentDb;
use crate::mech_state::Mech;

/// A unit = its index in `Battle::units`, fixed for the battle (destroyed units keep their number).
pub type UnitId = usize;

/// The two draws the engine makes (INTEGRATION__rng.BattleRNG).
pub trait Dice {
    /// 2d6, 2-12
    fn roll_2d6(&mut self) -> i64;
    /// 1..=n
    fn pick_number(&mut self, n: i64) -> i64;
    /// how many draws so far (the trace's `dice_used`)
    fn used(&self) -> usize;
}

/// Plays a recorded dice tape back (`["r", 0, sum]` / `["p", n, k]`); asking for a different kind of draw or a
/// different n than the tape holds panics with the call number - the first-difference detector for dice.
pub struct TapeDice {
    pub calls: Vec<(char, i64, i64)>,
    pub pos: usize,
}

impl TapeDice {
    pub fn new(calls: Vec<(char, i64, i64)>) -> TapeDice {
        TapeDice { calls, pos: 0 }
    }
    pub fn from_json(v: &serde_json::Value) -> TapeDice {
        TapeDice::new(v.as_array().unwrap().iter().map(|c| (c[0].as_str().unwrap().chars().next().unwrap(), c[1].as_i64().unwrap(), c[2].as_i64().unwrap())).collect())
    }
    fn next(&mut self, kind: char, n: i64) -> i64 {
        let c = *self.calls.get(self.pos).unwrap_or_else(|| panic!("dice call {}: asked for ({}, {}) but the tape has ended", self.pos + 1, kind, n));
        if c.0 != kind || c.1 != n {
            panic!("dice call {}: asked for ({}, {}), tape has ({}, {})", self.pos + 1, kind, n, c.0, c.1);
        }
        self.pos += 1;
        c.2
    }
    /// Dice a bot drew while thinking (its decision was recorded, so it does not think now).
    pub fn skip(&mut self, count: usize) {
        self.pos += count;
    }
}

impl Dice for TapeDice {
    fn roll_2d6(&mut self) -> i64 {
        self.next('r', 0)
    }
    fn pick_number(&mut self, n: i64) -> i64 {
        self.next('p', n)
    }
    fn used(&self) -> usize {
        self.pos
    }
}

/// The battle log: what the Python prints (stdout, via config.log) and its stub warnings (stderr). `quiet` > 0 is a
/// dry run: log lines are dropped (config.quiet()).
#[derive(Default, Debug, Clone)]
pub struct Log {
    pub lines: Vec<String>,
    pub stderr: Vec<String>,
    pub quiet: i64,
}

impl Log {
    pub fn log(&mut self, msg: impl Into<String>) {
        if self.quiet > 0 {
            return;
        }
        self.lines.push(msg.into());
    }
}

pub struct Battle {
    pub cfg: Config,
    pub db: EquipmentDb,
    pub log: Log,
    pub dice: Box<dyn Dice>,
    pub units: Vec<Mech>,
    pub board: Board,
    /// stubs.py: how many times each stub ran this battle
    pub stub_counts: IndexMap<String, i64>,
    /// smoke.py: labels with smoke now
    pub smoky: IndexSet<String>,
    /// hazards.py: labels whose magma crust broke this battle (put back at the next battle start)
    pub broken_crust: Vec<String>,
    /// clubs.py: hex label -> severed limbs lying there
    pub limbs_on_ground: IndexMap<String, i64>,
    pub turn: i64,
    /// config.PILOTING as piloting_rolls reads it: the Python sets the one global to a mech's own skill around each call
    /// (attack_resolution._with_piloting)
    pub piloting: i64,
    /// hazards._IN_PHASE
    pub hazards_in_phase: bool,
}

impl Battle {
    pub fn new(cfg: Config, board: Board, units: Vec<Mech>, dice: Box<dyn Dice>) -> Battle {
        let piloting = if cfg.has("PILOTING") { cfg.i("PILOTING") } else { 5 };
        Battle {
            cfg,
            db: EquipmentDb::load(),
            log: Log::default(),
            dice,
            units,
            board,
            stub_counts: IndexMap::new(),
            smoky: IndexSet::new(),
            broken_crust: Vec::new(),
            limbs_on_ground: IndexMap::new(),
            turn: 0,
            piloting,
            hazards_in_phase: false,
        }
    }

    pub fn roll_2d6(&mut self) -> i64 {
        self.dice.roll_2d6()
    }
    pub fn pick_number(&mut self, n: i64) -> i64 {
        self.dice.pick_number(n)
    }
    pub fn log(&mut self, msg: impl Into<String>) {
        self.log.log(msg);
    }
    /// a bare `print` (not config.log): never dropped by a dry run's quiet
    pub fn print(&mut self, msg: impl Into<String>) {
        self.log.lines.push(msg.into());
    }
    /// `stubs._warn`: counts the stub and prints its warning to stderr.
    pub fn warn_stub(&mut self, name: &str, msg: &str) {
        *self.stub_counts.entry(name.to_string()).or_insert(0) += 1;
        self.log.stderr.push(format!("STUB: {} - {}", name, msg));
    }
    /// `mech_state.is_destroyed(mech)` (reads config.FIGHT_TO_THE_DEATH).
    pub fn is_destroyed(&mut self, u: UnitId) -> bool {
        let ttd = self.cfg.has("FIGHT_TO_THE_DEATH") && self.cfg.b("FIGHT_TO_THE_DEATH");
        crate::mech_state::is_destroyed(&mut self.units[u], ttd)
    }
    pub fn unit_index(&self, side_name: &str) -> UnitId {
        self.units.iter().position(|u| u.side_name.as_deref() == Some(side_name)).unwrap_or_else(|| panic!("no unit {}", side_name))
    }
}

impl Battle {
    /// `_with_piloting(mech, fn)`: piloting_rolls reads one global PILOTING; set it to this mech's own skill for the call.
    pub fn with_piloting<R>(&mut self, u: UnitId, f: impl FnOnce(&mut Battle) -> R) -> R {
        let saved = self.piloting;
        self.piloting = self.units[u].piloting;
        let r = f(self);
        self.piloting = saved;
        r
    }
}
