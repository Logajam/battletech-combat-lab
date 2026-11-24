//! EVENT RECORDS (INTEGRATION__EVENTS.md): what happened in a battle, as DATA the engine writes where it happens - never parsed
//! back out of the log text, so a change of log wording cannot break a search (Daniel, 2026-11-24).
//!
//! RECORDING CHANGES NOTHING: an event is written beside the log line it matches, from numbers the code already has. Nothing
//! here rolls dice, asks a bot or touches a unit. Events are off unless a caller turns them on (`Battle::events_on`), and a
//! dry run (log `quiet`) never records one, exactly as it never writes a log line.
//!
//! One event = {k kind, t turn, p phase, u unit, o other, tn, r roll, ok, d dmg, l loc, s sub, w what, n}; unset fields are
//! left out of the JSON. `unit` is who it happened to or who did it, `other` the second party (target, attacker). Field
//! meanings per kind are in `KINDS` (and INTEGRATION__EVENTS.md): a test compares the two, so they cannot drift.
use serde_json::{json, Map, Value};

use crate::battle::{Battle, UnitId};

/// The event list's version. Bump it when a kind is added, removed or changes meaning; stored records carry it.
pub const EVENT_VERSION: i64 = 1;

/// Every event kind: (name, what its fields mean). `tools/search_events.py` and the coverage check read this list through
/// `btsim --events-list`.
pub const KINDS: &[(&str, &str)] = &[
    // initiative
    ("INITIATIVE_ROLL", "one team's Initiative throw: sub = team, roll = the 2D6, n = round (1 = first throw, 2+ = a tie re-roll among the tied teams)"),
    // movement
    ("MOVE", "a unit's move: sub = mode (walk, run, jump, ...), n = MP used, what = destination hex"),
    ("STAND_ATTEMPT", "a prone unit tries to stand: tn, roll, ok = it stood"),
    ("FALL", "a unit falls: sub = cause (movement, hit, pilot, ...), n = fall damage"),
    ("WATER_ENTER", "a unit's move ends in water after starting out of it: n = depth, what = hex (only the move's two ends are compared)"),
    ("BUILDING_ENTER", "a unit's move ends in a building hex after starting outside one: what = hex"),
    ("BUILDING_LEAVE", "a unit's move ends outside a building after starting in one: what = the hex it left"),
    ("HAZARD", "a hazard taken: sub = magma, magma_crust (the crust breaks), hazardous_liquid or bog (stuck)"),
    // physical attacks
    ("PHYS_CHARGE", "charge: unit attacks other, tn, roll, ok, dmg = damage to the target"),
    ("PHYS_DFA", "death from above: as PHYS_CHARGE"),
    ("PHYS_PUSH", "push: as PHYS_CHARGE"),
    ("PHYS_KICK", "kick: as PHYS_CHARGE"),
    ("PHYS_PUNCH", "punch: as PHYS_CHARGE, loc = arm"),
    ("PHYS_CLUB", "club, hatchet and other melee gear: as PHYS_CHARGE, what = the weapon"),
    // ranged attacks
    ("ATTACK", "one weapon's attack roll: unit fires at other, sub = weapon family (energy, ballistic, missile, area_effect), what = weapon, tn, roll, ok = hit, n = shots"),
    ("HIT", "damage landing on a unit: unit = the one hit, other = who hit it, loc = location, roll = location roll, dmg = damage applied, sub = ranged, physical or other, what = weapon"),
    // TAG and indirect fire
    ("TAG_DESIGNATE", "a TAG shot: unit tags other (or a hex), tn, roll, ok, sub = mech or hex"),
    ("SPOT", "a unit spots for indirect fire: unit spots other"),
    ("INDIRECT_FIRE", "an attack with no line of sight, fired on a spot: unit fires at other, what = weapon"),
    ("HOMING_HIT", "a homing missile strikes a TAG-designated target (sub = mech or hex): unit fires at other, dmg"),
    // damage
    ("CRIT", "a critical hit: unit = the one hit, loc, sub = slot type (Engine, Gyro, Cockpit, Sensors, Life Support, Actuator, Weapon, Ammo, Heat Sink, Other), what = the slot, n = that component's hits so far"),
    ("COMPONENT_DESTROYED", "a component is gone for good: sub = Engine, Gyro or Cockpit"),
    ("AMMO_EXPLOSION", "an ammo bin explodes: loc, sub = case or no_case (the location's CASE state), dmg = damage taken"),
    ("LOCATION_DESTROYED", "a location is destroyed: loc"),
    ("UNIT_DESTROYED", "a unit is destroyed: sub = cause"),
    // pilot and heat
    ("PILOT_HIT", "the pilot takes damage: n = hits so far, sub = cause"),
    ("CONSCIOUSNESS", "a consciousness roll: tn, roll, ok = stayed conscious, n = pilot hits"),
    ("SHUTDOWN", "a unit shuts down: sub = heat or other cause"),
    ("RESTART", "a restart attempt: tn, roll, ok"),
    ("HEAT_LEVEL", "heat at the end of the Heat Phase: n = heat now, sub = the highest heat-scale step at or below it (0, 5, 8, 10, 13, 14, 15, 17, 18, 19, 20, 22, 23, 24, 25, 26, 28, 30)"),
    // bot and player choices
    ("TARGET_CHOSEN", "a unit's declared target: unit picks other"),
    ("MOVE_CHOSEN", "the move a unit chose: sub = mode, what = destination hex, n = MP"),
    ("HOLD_FIRE", "a unit that could not or would not fire: what = the reason"),
];

/// The heat scale's steps (Core, the Heat Scale): a HEAT_LEVEL event's `sub` is the highest one at or below the unit's heat.
pub const HEAT_BRACKETS: [i64; 17] = [5, 8, 10, 13, 14, 15, 17, 18, 19, 20, 22, 23, 24, 25, 26, 28, 30];

/// The kinds, as a JSON list (btsim --events-list).
pub fn kinds_json() -> Value {
    json!({"version": EVENT_VERSION, "phases": PHASES, "kinds": KINDS.iter().map(|(k, d)| json!({"kind": k, "fields": d})).collect::<Vec<_>>()})
}

/// The phases an event can carry, in turn order.
pub const PHASES: &[&str] = &["deployment", "initiative", "movement", "ranged", "physical", "heat", "end"];

#[derive(Debug, Clone, Default)]
pub struct Event {
    pub kind: &'static str,
    pub turn: i64,
    pub phase: &'static str,
    pub unit: Option<UnitId>,
    pub other: Option<UnitId>,
    pub tn: Option<i64>,
    pub roll: Option<i64>,
    pub ok: Option<bool>,
    pub dmg: Option<f64>,
    pub loc: Option<String>,
    pub sub: Option<String>,
    pub what: Option<String>,
    pub n: Option<i64>,
}

/// A battle's events and the context they are written in. Cloning a battle (Hydra's playouts) gives an empty, OFF record: a
/// forecast never writes events.
#[derive(Debug, Default)]
pub struct EventLog {
    pub on: bool,
    pub list: Vec<Event>,
    pub turn: i64,
    pub phase: &'static str,
    /// units whose UNIT_DESTROYED has been written
    pub dead: Vec<bool>,
    /// who is attacking, and with what, while a ranged attack's damage lands (so a HIT names its attacker)
    pub actor: Option<(UnitId, String)>,
}

impl Clone for EventLog {
    fn clone(&self) -> EventLog {
        EventLog::default()
    }
}

/// An event being built (`Battle::ev`). Inert when events are off: the setters do nothing and `emit` writes nothing.
pub struct Ev {
    live: bool,
    e: Event,
}

impl Battle {
    /// Turns event recording on (before the battle starts).
    pub fn events_on(&mut self) {
        self.log.ev.on = true;
    }

    /// Starts an event of `kind` (a name in `KINDS`) at the current turn and phase.
    pub fn ev(&self, kind: &'static str) -> Ev {
        let live = self.log.ev.on && self.log.quiet == 0;
        debug_assert!(!live || KINDS.iter().any(|(k, _)| *k == kind), "unknown event kind {}", kind);
        Ev { live, e: Event { kind, turn: self.log.ev.turn, phase: self.log.ev.phase, ..Default::default() } }
    }

    /// The orchestrator's marker: events written from here on carry this turn and phase.
    pub fn event_phase(&mut self, turn: i64, phase: &'static str) {
        self.log.ev.turn = turn;
        self.log.ev.phase = phase;
    }

    /// A pilot hit just landed on `u` (its `pilot_hits` already counts it): the PILOT_HIT event.
    pub fn pilot_hit_ev(&mut self, u: UnitId, cause: &str) {
        let n = self.units[u].pilot_hits;
        self.ev("PILOT_HIT").unit(u).n(n).sub(cause).emit(self);
    }

    /// UNIT_DESTROYED, once per unit: called wherever a unit is seen to be destroyed (`Battle::is_destroyed`, the phase sweep).
    pub fn note_destroyed(&mut self, u: UnitId) {
        if self.log.ev.dead.len() <= u {
            self.log.ev.dead.resize(self.units.len().max(u + 1), false);
        }
        if self.log.ev.dead[u] || self.log.quiet > 0 {
            return;
        }
        self.log.ev.dead[u] = true;
        let cause = self.units[u].cause_of_death.clone().unwrap_or_else(|| "unknown".into());
        self.ev("UNIT_DESTROYED").unit(u).sub(&cause).emit(self);
    }

    /// The phase sweep: any unit now destroyed that no event has reported yet (displacement deaths set `destroyed` directly).
    pub fn sweep_destroyed(&mut self) {
        if self.log.ev.on {
            for u in 0..self.units.len() {
                if self.units[u].destroyed {
                    self.note_destroyed(u);
                }
            }
        }
    }

    /// Who is attacking while damage lands (None to clear).
    pub fn event_actor(&mut self, actor: Option<(UnitId, String)>) {
        if self.log.ev.on {
            self.log.ev.actor = actor;
        }
    }
}

impl Ev {
    pub fn unit(mut self, u: UnitId) -> Ev {
        self.e.unit = Some(u);
        self
    }
    pub fn other(mut self, u: UnitId) -> Ev {
        self.e.other = Some(u);
        self
    }
    pub fn tn(mut self, v: i64) -> Ev {
        self.e.tn = Some(v);
        self
    }
    pub fn roll(mut self, v: i64) -> Ev {
        self.e.roll = Some(v);
        self
    }
    pub fn ok(mut self, v: bool) -> Ev {
        self.e.ok = Some(v);
        self
    }
    pub fn dmg(mut self, v: f64) -> Ev {
        self.e.dmg = Some(v);
        self
    }
    pub fn n(mut self, v: i64) -> Ev {
        self.e.n = Some(v);
        self
    }
    pub fn loc(mut self, v: &str) -> Ev {
        if self.live {
            self.e.loc = Some(v.to_string());
        }
        self
    }
    pub fn sub(mut self, v: &str) -> Ev {
        if self.live {
            self.e.sub = Some(v.to_string());
        }
        self
    }
    pub fn what(mut self, v: &str) -> Ev {
        if self.live {
            self.e.what = Some(v.to_string());
        }
        self
    }
    /// Is this event being recorded? (Guard work that only an event needs.)
    pub fn live(&self) -> bool {
        self.live
    }
    pub fn emit(self, b: &mut Battle) {
        if self.live {
            b.log.ev.list.push(self.e);
        }
    }
}

/// A weapon's family for ATTACK events: its damage type (energy, ballistic, missile), or "homing" / "artillery" / "area_effect"
/// for those shot kinds. Reads only.
pub fn weapon_family(m: &crate::mech_state::Mech, w: usize, shot_kind: &str) -> &'static str {
    match shot_kind {
        "homing" => "homing",
        "artillery" | "distant" => "artillery",
        _ => match m.items[w].damage_type.as_deref() {
            Some("Energy") => "energy",
            Some("Ballistic") => "ballistic",
            Some("Missile") => "missile",
            Some("AreaEffect") => "area_effect",
            _ => "other",
        },
    }
}

/// One event as JSON: unset fields are left out; units go by their side name.
pub fn event_json(b: &Battle, e: &Event) -> Value {
    let name = |u: UnitId| b.units[u].side_name.clone().unwrap_or_default();
    let mut m = Map::new();
    m.insert("k".into(), json!(e.kind));
    m.insert("t".into(), json!(e.turn));
    m.insert("p".into(), json!(e.phase));
    if let Some(u) = e.unit {
        m.insert("u".into(), json!(name(u)));
    }
    if let Some(u) = e.other {
        m.insert("o".into(), json!(name(u)));
    }
    if let Some(v) = e.tn {
        m.insert("tn".into(), json!(v));
    }
    if let Some(v) = e.roll {
        m.insert("r".into(), json!(v));
    }
    if let Some(v) = e.ok {
        m.insert("ok".into(), json!(v));
    }
    if let Some(v) = e.dmg {
        m.insert("d".into(), json!(v));
    }
    if let Some(v) = &e.loc {
        m.insert("l".into(), json!(v));
    }
    if let Some(v) = &e.sub {
        m.insert("s".into(), json!(v));
    }
    if let Some(v) = &e.what {
        m.insert("w".into(), json!(v));
    }
    if let Some(v) = e.n {
        m.insert("n".into(), json!(v));
    }
    Value::Object(m)
}

/// Each unit's team, {side name: team}: events name units by side name, a search needs the teams.
pub fn teams_json(b: &Battle) -> Value {
    let mut m = Map::new();
    for u in b.units.iter() {
        let side = u.side_name.clone().unwrap_or_default();
        m.insert(side.clone(), json!(u.team.clone().unwrap_or(side)));
    }
    Value::Object(m)
}

/// A battle's whole event list as JSON (the order they happened in).
pub fn events_json(b: &Battle) -> Value {
    Value::Array(b.log.ev.list.iter().map(|e| event_json(b, e)).collect())
}
