//! WHAT A PERSON HAS CHOSEN (BattleROM, INTEGRATION__PLAYER_DECISIONS.md Sections 12-16). Not translated from the Python.
//!
//! The engine's stubs and defaults decide a number of things a player decides: which kind of ammunition a weapon fires, how
//! many shots an Ultra / Rotary AC fires, which ammunition bin is drawn from, whether to try to clear a jam, charge a PPC
//! capacitor, use MASC / a supercharger / radical heat sinks / a coolant pod, how many heat sinks stay on, Blue Shield. A
//! unit a person controls has an entry in `PlayerChoices::units` (made by `play_session`); the stubs and defaults look
//! there FIRST and fall back to their own rule when the person has said nothing. A battle with no entry (every simulated
//! battle) is exactly as before.
//!
//! Choices persist until changed: "Once the option is chosen it stays chosen" (Daniel, 2026-11-21). Keys are the unit's side
//! name and the weapon's item id (or name where the stub only has the name).
use crate::equipment::ItemId;
use crate::fasthash::{HashMap, HashSet};

#[derive(Clone, Debug, Default)]
pub struct UnitChoices {
    /// weapon -> the label of the shot option (munition / guidance / kind) to fire, as `ShotPlan::label` says it
    pub munition: HashMap<ItemId, String>,
    /// weapon -> shots of an Ultra / Rotary AC
    pub shots: HashMap<ItemId, i64>,
    /// weapon -> the ammunition bin it draws from (otherwise the automatic order, `ammo::auto_bin`)
    pub bin: HashMap<ItemId, ItemId>,
    /// jammed weapons to try to clear next turn (by name)
    pub unjam: HashSet<String>,
    /// PPCs whose capacitor is charged instead of firing (by name)
    pub charge: HashSet<String>,
    /// labelled systems ("MASC / supercharger", "radical heat sink system") the person switched on (true) or off (false)
    pub escalating: HashMap<String, bool>,
    /// coolant pods: Some(false) = never, Some(true) = as soon as heat is expected, None = the engine's automatic rule
    pub coolant: Option<bool>,
    /// how many heat sinks to leave switched off, when the person set it
    pub sinks_off: Option<i64>,
    pub blue_shield: Option<bool>,
    /// VOLUNTARY SHUTDOWN (Core p.105; engine pass 2026-11-24): this Heat Phase's request, Some(true) = shut down, Some(false) =
    /// restart (used once, then cleared)
    pub power_request: Option<bool>,
    /// shut down by choice: no restart is tried until the person asks for one (then the usual heat checks, p.105)
    pub held_off: bool,
}

#[derive(Clone, Debug, Default)]
pub struct PlayerChoices {
    pub units: HashMap<String, UnitChoices>,
}

impl PlayerChoices {
    pub fn is_player(&self, unit: &str) -> bool {
        self.units.contains_key(unit)
    }
    pub fn unit(&self, unit: &str) -> Option<&UnitChoices> {
        self.units.get(unit)
    }
    pub fn unit_mut(&mut self, unit: &str) -> &mut UnitChoices {
        self.units.entry(unit.to_string()).or_default()
    }
}
