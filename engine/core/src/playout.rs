// Hydra's play-out stage S5a, the groundwork (session 25; INTEGRATION__HYDRA.md Section 6). Not translated from the Python:
// Hydra is Rust only. Three blocks the play-out is built from; nothing here changes a battle that does not use them.
//
//   MOVE QUEUE - who moves after the current mover, in order: `Battle::move_queue`, set by the turn loop
//                (orchestrator, Movement Phase) before each unit is asked to move. See `move_queue` below.
//   POSE       - "assume unit U ends its move here": `Poses::pose` sets where a unit stands and how it moved, remembers
//                what was there, and `Poses::restore` puts every posed unit back exactly. No rolls, no heat, no log.
//   WITNESS    - "thinking left the battle as it found it": `Witness::take` before a decision, `Witness::check` after.
//                Compares every unit's full state, the dice drawn, the log and the stub counts. It costs a dump of every
//                unit, so it runs only when the environment variable HYDRA_CHECK is set (tests and trials).

use crate::battle::{Battle, UnitId};

// =============================================================================================================
// MOVE QUEUE
// =============================================================================================================
/// The units still to move this Movement Phase after the one now moving, in the order the turn loop expects to ask
/// them. Empty outside the Movement Phase. It is a FORECAST: the order is worked out from the activation state with
/// the same rule the loop uses (forces::move_index), on positions as they are now; a side's later picks can change
/// as units move. The units move in their sides' alternating turns, so friends and enemies are mixed.
pub fn move_queue(b: &Battle) -> &[UnitId] {
    &b.move_queue
}

// =============================================================================================================
// POSE
// =============================================================================================================
/// Where a unit stands and how it moved this turn: everything the Exchange Oracle (move_eval) reads about a unit's
/// move. Copied in and out whole.
#[derive(Clone, Debug, PartialEq)]
pub struct Pose {
    pub hex: Option<String>,
    pub facing: String,
    /// "Stand Still" / "Walk" / "Run" / "Jump" ...
    pub move_mode: String,
    /// hexes moved (the target movement modifier counts these)
    pub move_fc: i64,
    pub mp_spent: i64,
    pub movement_heat: i64,
    pub moved_this_turn: bool,
}

impl Pose {
    /// The unit's pose as it is now.
    pub fn of(b: &Battle, u: UnitId) -> Pose {
        let m = &b.units[u];
        Pose {
            hex: m.hex.clone(),
            facing: m.facing.clone(),
            move_mode: m.move_mode.clone(),
            move_fc: m.move_fc,
            mp_spent: m.mp_spent,
            movement_heat: m.movement_heat,
            moved_this_turn: m.moved_this_turn,
        }
    }

    fn put(&self, b: &mut Battle, u: UnitId) {
        let m = &mut b.units[u];
        m.hex = self.hex.clone();
        m.facing = self.facing.clone();
        m.move_mode = self.move_mode.clone();
        m.move_fc = self.move_fc;
        m.mp_spent = self.mp_spent;
        m.movement_heat = self.movement_heat;
        m.moved_this_turn = self.moved_this_turn;
    }
}

/// A stack of posed units. Pose any number, in any order; `restore` undoes them all, last first. Dropping a stack
/// that still holds poses is a bug (the battle would be left wrong) and panics.
#[derive(Default)]
pub struct Poses {
    saved: Vec<(UnitId, Pose)>,
}

impl Poses {
    pub fn new() -> Poses {
        Poses::default()
    }

    /// Assume `u` ends its move as `pose` says (a unit that has moved: `moved_this_turn` true). The board is not
    /// touched, so no cache needs emptying: line-of-sight and movement-table caches are keyed by position.
    pub fn pose(&mut self, b: &mut Battle, u: UnitId, pose: &Pose) {
        self.saved.push((u, Pose::of(b, u)));
        pose.put(b, u);
    }

    /// How many poses are in place.
    pub fn len(&self) -> usize {
        self.saved.len()
    }

    pub fn is_empty(&self) -> bool {
        self.saved.is_empty()
    }

    /// Is a hex already taken by a posed unit (two units may not end in the same hex)?
    pub fn holds_hex(&self, b: &Battle, hex: &str) -> bool {
        self.saved.iter().any(|(u, _)| b.units[*u].hex.as_deref() == Some(hex))
    }

    /// Puts every posed unit back as it was, last pose first.
    pub fn restore(&mut self, b: &mut Battle) {
        while let Some((u, was)) = self.saved.pop() {
            was.put(b, u);
        }
    }
}

impl Drop for Poses {
    fn drop(&mut self) {
        if !self.saved.is_empty() && !std::thread::panicking() {
            panic!("playout::Poses dropped with {} pose(s) still in place: call restore()", self.saved.len());
        }
    }
}

// =============================================================================================================
// WITNESS
// =============================================================================================================
/// Is the check switched on (environment variable HYDRA_CHECK set to anything but "0")? Read once per process.
pub fn checking() -> bool {
    static ON: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
    *ON.get_or_init(|| std::env::var("HYDRA_CHECK").map_or(false, |v| v != "0"))
}

/// A record of the battle's state before a bot thinks.
pub struct Witness {
    units: Vec<String>,
    dice: usize,
    log_lines: usize,
    stubs: i64,
}

impl Witness {
    /// None when checking is off (the usual case: costs nothing).
    pub fn take(b: &Battle) -> Option<Witness> {
        if !checking() {
            return None;
        }
        Some(Witness::now(b))
    }

    /// Always takes the record (tests).
    pub fn now(b: &Battle) -> Witness {
        Witness { units: unit_dumps(b), dice: b.dice_used(), log_lines: b.log.lines.len(), stubs: b.stub_counts.values().sum() }
    }

    /// Panics, naming the first difference, unless the battle is as it was. `what` names the decision.
    pub fn check(&self, b: &Battle, what: &str) {
        if let Some(why) = self.difference(b) {
            panic!("HYDRA_CHECK: {} changed the battle while only thinking: {}", what, why);
        }
    }

    /// The first difference from the record, or None.
    pub fn difference(&self, b: &Battle) -> Option<String> {
        if b.dice_used() != self.dice {
            return Some(format!("{} dice drawn", b.dice_used() as i64 - self.dice as i64));
        }
        if b.log.lines.len() != self.log_lines {
            return Some(format!("{} log line(s) written", b.log.lines.len() as i64 - self.log_lines as i64));
        }
        let stubs: i64 = b.stub_counts.values().sum();
        if stubs != self.stubs {
            return Some(format!("{} stub call(s) counted", stubs - self.stubs));
        }
        let now = unit_dumps(b);
        for (u, (was, is)) in self.units.iter().zip(now.iter()).enumerate() {
            if was != is {
                let name = b.units[u].side_name.clone().unwrap_or_default();
                return Some(format!("unit {} ({}) is not as it was", u, name));
            }
        }
        None
    }
}

fn unit_dumps(b: &Battle) -> Vec<String> {
    let name = |i: usize| b.units[i].side_name.clone().unwrap_or_default();
    b.units.iter().map(|m| m.to_json(&name).to_string()).collect()
}
