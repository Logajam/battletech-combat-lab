//! The battle: everything that carries from one moment to the next (INTEGRATION__STATE.md). There are NO globals
//! (RUST_PORT trap 6): the units, the board, the dice, the settings, the log and every table the Python keeps in a
//! module live here, and the engine's functions take `&mut Battle` and a `UnitId`.

use crate::fasthash::{IndexMap, IndexSet};

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
    /// dice a bot drew while thinking, in a replay (its decision was recorded, so it does not think now)
    fn skip(&mut self, _count: usize) {
        panic!("this dice source cannot skip draws");
    }
    /// The dice's exact place in their stream, as JSON (MegaMek bridge, `bridge.rs`): None for a source that cannot
    /// be saved. `PcgDice::restore` puts it back.
    fn save(&self) -> Option<serde_json::Value> {
        None
    }
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
    fn skip(&mut self, count: usize) {
        self.pos += count;
    }
}

/// The battle log: what the Python prints (stdout, via config.log) and its stub warnings (stderr). `quiet` > 0 is a
/// dry run: log lines are dropped (config.quiet()).
#[derive(Default, Debug, Clone)]
pub struct Log {
    pub lines: Vec<String>,
    pub stderr: Vec<String>,
    pub quiet: i64,
    /// which of `lines` are bare prints (`Battle::print`): the Python printed them to the screen only, so its replay
    /// record (and the Rust history, history.rs) leaves them out
    pub printed: Vec<usize>,
}

impl Log {
    pub fn log(&mut self, msg: impl Into<String>) {
        if self.quiet > 0 {
            return;
        }
        self.lines.push(msg.into());
    }
}

/// Counters the Combat Lab reads at the end of a battle (never the rules): per unit, the weapons' shots, hits, damage and the
/// turns they fired in ([fired, hits, damage, turns_fired, last_turn_fired]), kills by weapon fire, and turns standing.
#[derive(Clone, Debug, Default)]
pub struct Tally {
    pub weapons: Vec<IndexMap<String, [f64; 5]>>,
    pub kills: Vec<i64>,
    pub alive: Vec<i64>,
    /// Movement and spacing, per unit (Daniel, 2026-11-20; statistics only, never read by the rules):
    /// [hexes moved, turns moved, distance to nearest enemy, turns sampled, distance to its target, turns it had a target,
    ///  mean distance to its allies, turns it had a living ally on the board]. Moved = the straight-line hexes between where the
    /// unit's Movement Phase began and ended; the other distances are taken when the Movement Phase is over.
    pub track: Vec<[f64; 8]>,
}

impl Tally {
    pub fn fit(&mut self, n: usize) {
        if self.kills.len() < n {
            self.weapons.resize_with(n, Default::default);
            self.kills.resize(n, 0);
            self.alive.resize(n, 0);
            self.track.resize(n, [0.0; 8]);
        }
    }
}

pub struct Battle {
    pub cfg: Config,
    pub tally: Tally,
    /// equipment.json: a read-only table, parsed once for the whole process and shared by every battle
    pub db: &'static EquipmentDb,
    pub log: Log,
    pub dice: std::cell::RefCell<Box<dyn Dice>>,
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
    /// the decision seam in replay mode (INTEGRATION__decisions): the recorded bot answers
    pub replay: Option<Replay>,
    /// legate.py's module state (plans, rates, shares, peril caches)
    pub legate: crate::legate::LegateState,
    /// weapon_selection._FIRE_CONTROL: another bot's fire control while it thinks
    pub fire_ctl: Option<crate::princess_fire::FireControl>,
    pub princess: crate::princess_fire::PrincessState,
    /// hydra.rs: the third bot's memory for this battle
    pub hydra: crate::hydra::HydraState,
    /// Movement Phase: the units still to move after the current mover, in the expected order (playout::move_queue;
    /// session 25, Hydra's S5a). Read only by bots; empty outside the Movement Phase.
    pub move_queue: Vec<UnitId>,
    /// Physical Attack Phase: the 'Mechs a push has been declared against this phase (p.83: a 'Mech is the target of
    /// only one charge, DFA or push a turn). Emptied at the start of each Physical Attack Phase.
    pub pushed_this_phase: Vec<UnitId>,
    /// spotting.rs: this turn's spots for indirect fire (TAG hits and declared spotters); remade each Ranged Attack Phase
    pub spots: Vec<crate::spotting::Spot>,
    /// spotting.rs: (attacker, target) pairs attacked INDIRECTLY this Ranged Attack Phase (no Artemis bonus, p.70)
    pub indirect_pairs: Vec<(UnitId, UnitId)>,
    /// artillery.rs: distant Arrow IV / Thumper / Sniper shots in flight (they land next turn, p.182)
    pub pending_artillery: Vec<crate::artillery::PendingStrike>,
    /// INTEGRATION__los_cache: lines of sight the bots asked about, (from, to, heights) -> answer (None = the line runs
    /// off the board). Speed only: emptied whenever the board changes (`board_changed`).
    /// finished movement tables (`movement_table`); speed only, emptied when the board changes
    pub table_memo: std::cell::RefCell<crate::fasthash::HashMap<TableKey, std::sync::Arc<crate::pathfinder::MovementTable>>>,
    pub los_memo: std::cell::RefCell<crate::fasthash::HashMap<((i64, i64), (i64, i64), crate::los::Height, crate::los::Height), Option<crate::move_eval::PairInfo>>>,
}

/// `Battle::table_memo`'s key: (x, y, facing, MP budget, backward MP, level limit, blocked hexes sorted).
pub type TableKey = (i64, i64, i64, i64, Option<i64>, crate::terrain_rules::GroundLimit, Vec<(i64, i64)>);
/// The most tables `Battle::table_memo` holds before it is emptied (it just refills).
pub const TABLE_MEMO_MAX: usize = 400;

/// decisions.json played back: each bot decision of the battle, in the order the engine asks for them.
pub struct Replay {
    pub records: Vec<serde_json::Value>,
    pub cursor: usize,
}

impl Battle {
    /// Call after any change to a hex of the board (smoke, magma crust): remembered lines of sight are dropped.
    pub fn board_changed(&mut self) {
        self.los_memo.borrow_mut().clear();
        self.table_memo.borrow_mut().clear();
        self.board.psr_terrain = Default::default();
        self.board.hazard_terrain = Default::default();
    }

    /// pathfinder.build_movement_table on this battle's board (no parent links), each distinct search done once and
    /// kept until the board changes - the Python's finished-table cache. The blocked hexes are part of the key.
    #[allow(clippy::too_many_arguments)]
    pub fn movement_table(&self, x: i64, y: i64, facing: i64, budget: i64, backward_mp: Option<i64>, level_limit: crate::terrain_rules::GroundLimit, blocked: &crate::fasthash::HashSet<(i64, i64)>) -> std::sync::Arc<crate::pathfinder::MovementTable> {
        let mut hexes: Vec<(i64, i64)> = blocked.iter().copied().collect();
        hexes.sort();
        let key = (x, y, facing, budget, backward_mp, level_limit, hexes);
        if let Some(t) = self.table_memo.borrow().get(&key) {
            return t.clone();
        }
        let table = std::sync::Arc::new(crate::pathfinder::build_movement_table(x, y, facing, budget, Some(&self.board), backward_mp, level_limit, false, blocked).unwrap());
        let mut memo = self.table_memo.borrow_mut();
        if memo.len() >= TABLE_MEMO_MAX {
            memo.clear();
        }
        memo.insert(key, table.clone());
        table
    }

    pub fn new(cfg: Config, board: Board, units: Vec<Mech>, dice: Box<dyn Dice>) -> Battle {
        let piloting = if cfg.has("PILOTING") { cfg.i("PILOTING") } else { 5 };
        Battle {
            cfg,
            tally: Tally::default(),
            db: EquipmentDb::shared(),
            log: Log::default(),
            dice: std::cell::RefCell::new(dice),
            units,
            board,
            stub_counts: IndexMap::default(),
            smoky: IndexSet::default(),
            broken_crust: Vec::new(),
            limbs_on_ground: IndexMap::default(),
            turn: 0,
            piloting,
            hazards_in_phase: false,
            replay: None,
            legate: Default::default(),
            fire_ctl: None,
            princess: Default::default(),
            hydra: Default::default(),
            move_queue: Vec::new(),
            pushed_this_phase: Vec::new(),
            spots: Vec::new(),
            indirect_pairs: Vec::new(),
            pending_artillery: Vec::new(),
            los_memo: Default::default(),
            table_memo: Default::default(),
        }
    }

    pub fn roll_2d6(&self) -> i64 {
        self.dice.borrow_mut().roll_2d6()
    }
    pub fn pick_number(&self, n: i64) -> i64 {
        self.dice.borrow_mut().pick_number(n)
    }
    pub fn log(&mut self, msg: impl Into<String>) {
        self.log.log(msg);
    }
    /// a bare `print` (not config.log): never dropped by a dry run's quiet
    pub fn dice_used(&self) -> usize {
        self.dice.borrow().used()
    }
    pub fn print(&mut self, msg: impl Into<String>) {
        self.log.printed.push(self.log.lines.len());
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
    /// `decisions.decide(kind, ctx, compute)` in REPLAY mode: the recorded answer for the next decision (checked against
    /// the kind and who it is about), after skipping the dice the bot drew and printing the log lines and stub warnings
    /// its thinking printed. Returns the recorded value (JSON, rt-encoded).
    pub fn decide(&mut self, kind: &str, who: &str) -> serde_json::Value {
        let rp = self.replay.as_mut().expect("no replay loaded");
        let n = rp.cursor;
        assert!(n < rp.records.len(), "decision {}: asked for {} {} but the record has ended", n + 1, kind, who);
        let rec = rp.records[n].clone();
        if rec["kind"].as_str().unwrap() != kind || rec["who"].as_str().unwrap() != who {
            panic!("decision {}: asked for {} {}, record has {} {} (phase {})", n + 1, kind, who, rec["kind"], rec["who"], rec["phase"]);
        }
        rp.cursor += 1;
        self.dice.borrow_mut().skip(rec["dice_drawn"].as_u64().unwrap() as usize);
        for line in rec["log"].as_array().unwrap() {
            self.log(line.as_str().unwrap());
        }
        for s in rec["stubs"].as_array().unwrap() {
            let (name, msg) = (s[0].as_str().unwrap().to_string(), s[1].as_str().unwrap().to_string());
            self.warn_stub(&name, &msg);
        }
        rec["value"].clone()
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
