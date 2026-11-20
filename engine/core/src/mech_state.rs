// Translated from mechsim/mech_state.py (session 22).
//! "What a mech IS": the state container and the pure state-query functions. Attributes the Python hangs on a mech
//! later (RUST_PORT trap 7) are fields here; those that exist only once a later module has set them are `Option`s.

use crate::fasthash::{IndexMap, IndexSet};
use serde_json::{json, Map, Value};

use crate::equipment::{is_crit_target, Equipment, ItemId, Slot};
use crate::pyfmt::Num;

/// How damage is classed for the armor-type dispatch (mech_state.DamageType).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum DamageType {
    Ballistic,
    Energy,
    Missile,
    AreaEffect,
    Physical,
    Reengineered,
}

impl DamageType {
    /// the Python enum member's `.name` (used in log lines)
    pub fn name(&self) -> &'static str {
        match self {
            DamageType::Ballistic => "BALLISTIC",
            DamageType::Energy => "ENERGY",
            DamageType::Missile => "MISSILE",
            DamageType::AreaEffect => "AREA_EFFECT",
            DamageType::Physical => "PHYSICAL",
            DamageType::Reengineered => "REENGINEERED",
        }
    }
    pub fn from_name(n: &str) -> DamageType {
        match n {
            "BALLISTIC" => DamageType::Ballistic,
            "ENERGY" => DamageType::Energy,
            "MISSILE" => DamageType::Missile,
            "AREA_EFFECT" => DamageType::AreaEffect,
            "PHYSICAL" => DamageType::Physical,
            "REENGINEERED" => DamageType::Reengineered,
            other => panic!("damage type {}", other),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum StructureType {
    Standard,
    Reinforced,
    Composite,
}

impl StructureType {
    pub fn name(&self) -> &'static str {
        &self.dump()[14..]
    }
    pub fn from_dump(s: &str) -> StructureType {
        crate::mech_json::structure_type_from(s)
    }
    pub fn dump(&self) -> &'static str {
        match self {
            StructureType::Standard => "StructureType.STANDARD",
            StructureType::Reinforced => "StructureType.REINFORCED",
            StructureType::Composite => "StructureType.COMPOSITE",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ArmorType {
    Standard,
    Reactive,
    Reflective,
    Hardened,
    FerroLamellor,
    ImpactResistant,
    AntiPenetrativeAblation,
    BallisticReinforced,
    HeatDissipating,
}

impl ArmorType {
    pub fn name(&self) -> &'static str {
        &self.dump()[10..]
    }
    pub fn from_dump(s: &str) -> ArmorType {
        crate::mech_json::armor_type_from(s)
    }
    pub fn dump(&self) -> &'static str {
        match self {
            ArmorType::Standard => "ArmorType.STANDARD",
            ArmorType::Reactive => "ArmorType.REACTIVE",
            ArmorType::Reflective => "ArmorType.REFLECTIVE",
            ArmorType::Hardened => "ArmorType.HARDENED",
            ArmorType::FerroLamellor => "ArmorType.FERRO_LAMELLOR",
            ArmorType::ImpactResistant => "ArmorType.IMPACT_RESISTANT",
            ArmorType::AntiPenetrativeAblation => "ArmorType.ANTI_PENETRATIVE_ABLATION",
            ArmorType::BallisticReinforced => "ArmorType.BALLISTIC_REINFORCED",
            ArmorType::HeatDissipating => "ArmorType.HEAT_DISSIPATING",
        }
    }
}

/// Standard internal structure by tonnage: (tons, CT, ST, Arm, Leg).
pub const STRUCTURE_TABLE: [(i64, i64, i64, i64, i64); 39] = [
    (10, 4, 3, 1, 2), (15, 5, 4, 2, 3), (20, 6, 5, 3, 4), (25, 8, 6, 4, 6), (30, 10, 7, 5, 7), (35, 11, 8, 6, 8),
    (40, 12, 10, 6, 10), (45, 14, 11, 7, 11), (50, 16, 12, 8, 12), (55, 18, 13, 9, 13), (60, 20, 14, 10, 14),
    (65, 21, 15, 10, 15), (70, 22, 15, 11, 15), (75, 23, 16, 12, 16), (80, 25, 17, 13, 17), (85, 27, 18, 14, 18),
    (90, 29, 19, 15, 19), (95, 30, 20, 16, 20), (100, 31, 21, 17, 21), (105, 32, 22, 17, 22), (110, 33, 23, 18, 23),
    (115, 35, 24, 19, 24), (120, 36, 25, 20, 25), (125, 38, 26, 21, 26), (130, 39, 27, 21, 27), (135, 41, 28, 22, 28),
    (140, 42, 29, 23, 29), (145, 44, 31, 24, 31), (150, 45, 32, 25, 32), (155, 47, 33, 26, 33), (160, 48, 34, 26, 34),
    (165, 50, 35, 27, 35), (170, 51, 36, 28, 36), (175, 53, 37, 29, 37), (180, 54, 38, 30, 38), (185, 56, 39, 31, 39),
    (190, 57, 40, 31, 40), (195, 59, 41, 32, 41), (200, 60, 42, 33, 42),
];
pub const SUPERHEAVY_MIN_TONS: i64 = 105;
pub const SUPERHEAVY_HEAD: i64 = 4;
pub const LARGE_TARGET_MODIFIER: i64 = -1;
pub const SUPERHEAVY_PHYSICAL_MODIFIER: i64 = 1;

pub fn is_superheavy(mech: &Mech) -> bool {
    mech.mass.unwrap_or(0) >= SUPERHEAVY_MIN_TONS
}

pub fn engine_hits_to_destroy(mech: &Mech) -> i64 {
    if is_superheavy(mech) && mech.engine_desc.as_deref().unwrap_or("").to_uppercase().contains("COMPACT") {
        2
    } else {
        3
    }
}

pub fn target_size_modifier(mech: &Mech) -> i64 {
    if is_superheavy(mech) {
        LARGE_TARGET_MODIFIER
    } else {
        0
    }
}

/// {location: structure points} for a tonnage. Err = Python's ValueError text.
pub fn structure_for_tonnage(mass: i64, mech_type: &str) -> Result<IndexMap<String, i64>, String> {
    let row = STRUCTURE_TABLE
        .iter()
        .find(|r| r.0 == mass)
        .ok_or_else(|| format!("No internal structure table entry for {} tons (10-200 in 5-ton steps are supported).", mass))?;
    let (_, ct, st, arm, leg) = *row;
    let mut out = IndexMap::default();
    out.insert("Head".to_string(), if mass >= SUPERHEAVY_MIN_TONS { SUPERHEAVY_HEAD } else { 3 });
    out.insert("Center Torso".to_string(), ct);
    out.insert("Left Torso".to_string(), st);
    out.insert("Right Torso".to_string(), st);
    out.insert("Left Leg".to_string(), leg);
    out.insert("Right Leg".to_string(), leg);
    out.insert("Center Leg".to_string(), leg);
    if mech_type == "quad" || mech_type == "quadvee" {
        for l in ["Front Left Leg", "Front Right Leg", "Rear Left Leg", "Rear Right Leg"] {
            out.insert(l.to_string(), leg);
        }
    } else {
        out.insert("Left Arm".to_string(), arm);
        out.insert("Right Arm".to_string(), arm);
    }
    Ok(out)
}

/// One location's damage state. armor / structure are `Num`: an int until a hardened or reinforced point makes one a
/// float (the Python mixes them, and prints them differently).
#[derive(Clone, Debug, PartialEq)]
pub struct Location {
    pub armor: Num,
    /// only torsos carry rear armor
    pub rear_armor: Option<Num>,
    pub structure: Num,
    pub destroyed: bool,
}

impl Location {
    fn new(armor: i64, rear: Option<i64>, structure: i64) -> Location {
        Location { armor: Num::I(armor), rear_armor: rear.map(Num::I), structure: Num::I(structure), destroyed: false }
    }
    pub fn to_json(&self) -> Value {
        let mut m = Map::new();
        m.insert("armor".into(), self.armor.to_json());
        if let Some(r) = self.rear_armor {
            m.insert("rear_armor".into(), r.to_json());
        }
        m.insert("structure".into(), self.structure.to_json());
        m.insert("destroyed".into(), json!(self.destroyed));
        Value::Object(m)
    }
    pub fn from_json(v: &Value) -> Location {
        Location {
            armor: Num::from_json(&v["armor"]),
            rear_armor: v.get("rear_armor").map(Num::from_json),
            structure: Num::from_json(&v["structure"]),
            destroyed: v["destroyed"].as_bool().unwrap(),
        }
    }
    /// `loc[field]` for field "armor" / "rear_armor" / "structure".
    pub fn field(&self, name: &str) -> Num {
        match name {
            "armor" => self.armor,
            "rear_armor" => self.rear_armor.expect("rear_armor"),
            "structure" => self.structure,
            other => panic!("KeyError: {}", other),
        }
    }
    pub fn set_field(&mut self, name: &str, v: Num) {
        match name {
            "armor" => self.armor = v,
            "rear_armor" => self.rear_armor = Some(v),
            "structure" => self.structure = v,
            other => panic!("KeyError: {}", other),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Crew {
    pub unconscious: bool,
    pub check_pending: bool,
    pub went_out_this_turn: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct SlotInfo {
    pub name: String,
    pub instance_id: Option<ItemId>,
}

/// The unit's slots as the Battle Value reads its file (`mtf_parser::parse_mtf_for_bv`): only `battle_value` looks at it. Kept apart
/// so the units the engine builds stay exactly the frozen Python's (fix of 2026-11-20).
#[derive(Clone, Debug)]
pub struct BvView {
    pub crits: IndexMap<String, Vec<Slot>>,
    pub items: Vec<Equipment>,
    pub armored_slots: IndexSet<(String, usize)>,
}

#[derive(Clone, Debug)]
pub struct Mech {
    pub mech_type: String,
    pub chassis: String,
    pub model: String,
    pub locations: IndexMap<String, Location>,
    pub crits: IndexMap<String, Vec<Slot>>,
    /// every Equipment object of this mech; slots hold indices into it
    pub items: Vec<Equipment>,
    pub leg_locations: Vec<String>,
    pub limb_locations: Vec<String>,
    pub side_torso_child: IndexMap<String, String>,
    pub max_armor: IndexMap<String, i64>,
    pub max_rear_armor: IndexMap<String, i64>,
    pub max_structure: IndexMap<String, i64>,
    pub armor_type: IndexMap<String, ArmorType>,
    pub structure_type: StructureType,
    pub base_walk_mp: i64,
    pub base_jump_mp: i64,
    pub destroyed_leg_actuators: IndexMap<String, i64>,
    pub destroyed_hip_locations: IndexSet<String>,
    pub destroyed_jump_jet_ids: IndexSet<ItemId>,
    pub base_heat_sinks: i64,
    pub heat_sink_type: String,
    pub current_heat: i64,
    pub heat_mp_penalty: i64,
    pub heat_fire_modifier: i64,
    pub shutdown: bool,
    pub tsm_active: bool,
    pub deactivated_heat_sinks: i64,
    pub run_mp_multiplier: f64,
    pub myomer: String,
    pub destroyed_heat_sinks: IndexMap<ItemId, i64>,
    pub destroyed_slot_info: IndexMap<(String, usize), SlotInfo>,
    pub armored_slots: IndexSet<(String, usize)>,
    pub base_mechanical_jump_booster_mp: i64,
    pub mechanical_jump_booster_disabled: bool,
    pub partial_wing_active: bool,
    pub pilot_hits: i64,
    pub crew: IndexMap<String, Crew>,
    pub engine_hits: i64,
    pub gyro_hits: i64,
    pub cockpit_hit: bool,
    pub explosions: i64,
    pub destroyed: bool,
    pub cause_of_death: Option<String>,
    pub crippled: bool,
    pub crippled_at: Option<Value>,
    pub prone: bool,
    pub preexisting_damage_snapshot: IndexMap<String, Value>,
    pub pre_attack_phase_snapshot: IndexMap<String, Value>,
    pub movement_mode_this_turn: String,
    pub round_capable: IndexMap<String, bool>,
    pub initial_sensor_slots: i64,
    // set by mtf_parser.parse_mtf
    pub mass: Option<i64>,
    pub engine_desc: Option<String>,
    pub cockpit_type: Option<String>,
    pub gyro_type: Option<String>,
    pub armor_desc: Option<String>,
    /// the header's "heat sink kit:RISC Heat Sink Override Kit" (BV x 1.01, MegaMek); not saved with a state
    pub risc_heat_sink_kit: bool,
    /// the slots as the Battle Value reads the file (set by parse_mtf; None for a unit read from a saved state or a units.json,
    /// whose BV then reads its ordinary slots, as before the BV work); not saved with a state
    pub bv_view: Option<std::sync::Arc<BvView>>,
    pub is_industrial: Option<bool>,
    pub structure_desc: Option<String>,
    pub tech_base: Option<String>,
    // attributes other modules add (read with getattr(.., default) in the Python)
    pub secondary_hits: Option<i64>,
    pub console_lost: Option<bool>,
    pub primary_dead: Option<bool>,
    pub imp_mp: Option<i64>,
    pub modular_armor: Vec<ItemId>,
    // ---- attached when a battle is set up (orchestrator._attach_mech_config, ammo, electronics, equipment_systems...) ----
    /// false for a freshly parsed mech: the attributes below do not exist yet
    pub attached: bool,
    pub side_name: Option<String>,
    pub team: Option<String>,
    pub moved_this_turn: bool,
    pub hex: Option<String>,
    pub facing: String,
    pub home_edge: Option<Vec<String>>,
    pub gunnery: i64,
    pub piloting: i64,
    pub min_heat: i64,
    pub max_heat: i64,
    pub move_search: Option<String>,
    pub assumes_enemy_search: Option<String>,
    pub bot: String,
    pub has_improved_jump_jets: bool,
    pub has_xxl_engine: bool,
    pub has_supercooled_myomer: bool,
    pub equipment_systems: IndexMap<String, Vec<ItemId>>,
    pub has_tsm: bool,
    pub has_stealth_armor: bool,
    pub torso_cockpit: bool,
    pub escalating_turns: IndexMap<String, i64>,
    pub systems_used_this_turn: Vec<String>,
    /// T16: the bot manages this unit's heat equipment (MegaMek BotHeatEquipmentManager; Princess / CASPAR only). While false
    /// every concealment system works whenever it can and the radical heat sink follows STUB_ESCALATING_USE, as before.
    pub heat_managed: bool,
    /// T16: concealment systems the bot has switched OFF ("stealth_armor", "chameleon", "null_signature", "void_signature").
    pub systems_off: Vec<String>,
    /// T16: the bot has the radical heat sink switched ON (read only while `heat_managed`).
    pub radical_on: bool,
    pub turn_number: i64,
    pub pfd_active: bool,
    pub pfd_turns_used: i64,
    pub pfd_failed: bool,
    pub narc_pods: Vec<NarcPod>,
    pub ecm_suites: Vec<ItemId>,
    pub unjamming: Vec<ItemId>,
    pub capacitors: Vec<ItemId>,
    pub capacitor_heat: i64,
    /// False (None), "mech" or "hex"
    pub tag_designated: Option<String>,
    pub move_mode: String,
    pub move_fc: i64,
    pub mp_spent: i64,
    pub movement_heat: i64,
    /// the unit it declared a charge / DFA against (index in the battle's roster)
    pub charging: Option<usize>,
    pub dfa: Option<usize>,
    pub deferred_end_of_move: Option<Value>,
    // ---- attributes that only appear during a battle (Option = the attribute does not exist yet) ----
    pub ams_used: Option<Value>,
    pub arc_action: Option<ArcAction>,
    pub arc_action_locked: Option<bool>,
    pub armor_at_turn_start: Option<IndexMap<String, Vec<Num>>>,
    pub arms_flipped: Option<bool>,
    pub blocked_hex: Option<Value>,
    pub breached_locations: Option<IndexSet<String>>,
    pub hp_log: Option<Vec<f64>>,
    pub jump_only: Option<bool>,
    pub magma_entered: Option<Vec<(String, String)>>,
    pub other_unit_hexes: Option<Value>,
    pub outside_heat: Option<i64>,
    pub shield_raised: Option<Value>,
    pub started_in_liquid: Option<bool>,
    pub torso_twist: Option<i64>,
    pub weapons_fired_this_turn: Option<IndexSet<ItemId>>,
    pub club: Option<Option<String>>,
    pub breached_slot_set: Option<IndexSet<(String, usize)>>,
    pub autocannon_crits: Option<IndexSet<ItemId>>,
    pub severed_limbs: Option<Vec<String>>,
    pub severed_seen: Option<Vec<String>>,
    pub bv_built: Option<i64>,
    pub turret_last_offset: Option<i64>,
    pub taser_interference_until: Option<Option<i64>>,
    pub taser_shutdown_until: Option<Option<i64>>,
    pub tsemp_hits: Option<Vec<i64>>,
    pub tsemp_interference_until: Option<Option<i64>>,
    pub mech_turret_dir: Option<IndexMap<String, i64>>,
    pub home_edge_row: Option<Vec<String>>,
    /// bogged down (TO:AR p.60): the attribute is absent until a 'Mech is first stuck; present-None after it frees itself
    pub stuck: Option<Option<Stuck>>,
    pub tsemp_shutdown_until: Option<Option<i64>>,
    pub imp_until: Option<Option<i64>>,
    pub imp_level: Option<i64>,
    pub imp_started: Option<Option<i64>>,
    pub imp_missiles: Option<(Option<i64>, i64)>,
}

/// mech.stuck = {"rolls", "prone_stage", "by_jump", and once freed from the prone stage "stand_only"}
#[derive(Clone, Debug, PartialEq)]
pub struct Stuck {
    pub rolls: i64,
    pub prone_stage: bool,
    pub by_jump: bool,
    pub stand_only: Option<bool>,
}

impl Stuck {
    pub fn to_json(&self) -> Value {
        let mut m = Map::new();
        m.insert("rolls".into(), json!(self.rolls));
        m.insert("prone_stage".into(), json!(self.prone_stage));
        m.insert("by_jump".into(), json!(self.by_jump));
        if let Some(s) = self.stand_only {
            m.insert("stand_only".into(), json!(s));
        }
        Value::Object(m)
    }
    pub fn from_json(v: &Value) -> Stuck {
        Stuck { rolls: v["rolls"].as_i64().unwrap(), prone_stage: v["prone_stage"].as_bool().unwrap(), by_jump: v["by_jump"].as_bool().unwrap(), stand_only: v.get("stand_only").and_then(|x| x.as_bool()) }
    }
}

/// A twist / arm-flip / turret action (arcs.ArcAction).
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct ArcAction {
    pub twist: i64,
    pub flip: bool,
    pub turret: Option<Turret>,
}

/// A turret's setting in an ArcAction: an offset (an int) or a name - the Python uses both.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum Turret {
    Offset(i64),
    Name(String),
}

impl Turret {
    pub fn to_json(&self) -> Value {
        match self {
            Turret::Offset(i) => json!(i),
            Turret::Name(s) => json!(s),
        }
    }
    pub fn from_json(v: &Value) -> Option<Turret> {
        if let Some(i) = v.as_i64() {
            Some(Turret::Offset(i))
        } else {
            v.as_str().map(|s| Turret::Name(s.to_string()))
        }
    }
}

/// An enemy Narc pod stuck to this 'Mech.
#[derive(Clone, Debug, PartialEq)]
pub struct NarcPod {
    pub effective: bool,
    pub location: String,
    pub owner: String,
}

pub const QUAD_TYPES: [&str; 2] = ["quad", "quadvee"];

fn loc(name: &str) -> String {
    name.to_string()
}

impl Mech {
    /// Is this unit driven by Princess or by CASPAR (the fourth bot, session 29)? CASPAR is "Princess with parts swapped"
    /// (MegaMek's `class Caspar extends Princess`): it shares Princess's target choice, fire control, physical attacks and
    /// memory, and differs only in its movement ranker and zone deployment (`caspar.rs`). Every place that asked
    /// "is this a Princess unit?" asks this instead; only the movement call and the deployment tell the two apart.
    pub fn is_princess_family(&self) -> bool {
        self.bot == "princess" || self.bot == "caspar"
    }

    /// `BattleMech(mech_type)`: the stress-test fixture mech (its crit lists and numbers are placeholders that
    /// parse_mtf overwrites).
    pub fn new(mech_type: &str) -> Mech {
        let quad = QUAD_TYPES.contains(&mech_type);
        let mut items: Vec<Equipment> = Vec::new();
        // equipment_slots(...): ONE Equipment shared by its slots
        let shared = |items: &mut Vec<Equipment>, name: &str, slots: i64, explosive: bool, dmg: Option<i64>| -> Vec<Slot> {
            items.push(Equipment::new(name, slots, explosive, dmg, true, None, false, None, None, None, None, None, None, None, None));
            let id = items.len() - 1;
            (0..slots).map(|_| Slot::Item(id)).collect()
        };
        let names = |v: &[&str]| -> Vec<Slot> { v.iter().map(|s| Slot::name(s)).collect() };

        let mut locations: IndexMap<String, Location> = IndexMap::default();
        locations.insert(loc("Head"), Location::new(9, None, 3));
        locations.insert(loc("Center Torso"), Location::new(30, Some(14), 31));
        locations.insert(loc("Left Torso"), Location::new(20, Some(10), 21));
        locations.insert(loc("Right Torso"), Location::new(20, Some(10), 21));

        let mut crits: IndexMap<String, Vec<Slot>> = IndexMap::default();
        crits.insert(loc("Head"), names(&["Cockpit", "Sensors", "Life Support", "Padding", "Padding"]));
        crits.insert(loc("Center Torso"), names(&["Engine", "Engine", "Engine", "Gyro", "Gyro", "Gyro", "Gyro", "Engine", "Engine", "Engine", "Padding", "Padding"]));
        let mut lt = names(&["Engine", "Engine", "Padding", "Padding", "Padding", "Padding", "Padding", "Padding"]);
        lt.extend(shared(&mut items, "LRM Ammo", 1, true, Some(20)));
        lt.extend(shared(&mut items, "LRM Ammo", 1, true, Some(20)));
        lt.extend(names(&["CASE", "Padding"]));
        crits.insert(loc("Left Torso"), lt);
        crits.insert(loc("Right Torso"), names(&["Engine", "Engine", "Padding", "Padding", "Padding", "Padding", "Padding", "Padding", "Padding", "Padding"]));

        let limb = |armor: i64, structure: i64| Location::new(armor, None, structure);
        if quad {
            for l in ["Front Left Leg", "Front Right Leg", "Rear Left Leg", "Rear Right Leg"] {
                locations.insert(loc(l), limb(41, 21));
            }
            let mut c = names(&["Hip", "Upper Leg", "Lower Leg", "Foot", "Padding", "Padding", "Padding", "Padding", "Padding"]);
            c.extend(shared(&mut items, "Ammo", 1, true, Some(20)));
            c.push(Slot::name("CASE"));
            crits.insert(loc("Front Left Leg"), c);
            let mut c = names(&["Hip", "Upper Leg", "Lower Leg", "Foot"]);
            c.extend(shared(&mut items, "Gauss Rifle", 7, true, None));
            crits.insert(loc("Front Right Leg"), c);
            crits.insert(loc("Rear Left Leg"), names(&["Hip", "Upper Leg", "Lower Leg", "Foot", "Padding", "Padding"]));
            crits.insert(loc("Rear Right Leg"), names(&["Hip", "Upper Leg", "Lower Leg", "Foot"]));
        } else {
            locations.insert(loc("Left Arm"), limb(34, 17));
            locations.insert(loc("Right Arm"), limb(34, 17));
            locations.insert(loc("Left Leg"), limb(41, 21));
            locations.insert(loc("Right Leg"), limb(41, 21));
            let mut c = names(&["Shoulder", "Upper Arm", "Lower Arm", "Hand", "Padding", "Padding", "Padding", "Padding", "Padding"]);
            c.extend(shared(&mut items, "Ammo", 1, true, Some(20)));
            c.push(Slot::name("CASE"));
            crits.insert(loc("Left Arm"), c);
            let mut c = names(&["Shoulder", "Upper Arm", "Lower Arm", "Hand"]);
            c.extend(shared(&mut items, "Gauss Rifle", 7, true, None));
            crits.insert(loc("Right Arm"), c);
            crits.insert(loc("Left Leg"), names(&["Hip", "Upper Leg", "Lower Leg", "Foot", "Padding", "Padding"]));
            crits.insert(loc("Right Leg"), names(&["Hip", "Upper Leg", "Lower Leg", "Foot"]));
        }
        if mech_type == "tripod" {
            locations.insert(loc("Center Leg"), limb(41, 21));
            crits.insert(loc("Center Leg"), names(&["Hip", "Upper Leg", "Lower Leg", "Foot", "Padding", "Padding"]));
        }

        let (leg_locations, limb_locations, side_torso_child): (Vec<String>, Vec<String>, IndexMap<String, String>) = if quad {
            let legs: Vec<String> = ["Front Left Leg", "Front Right Leg", "Rear Left Leg", "Rear Right Leg"].iter().map(|s| s.to_string()).collect();
            let mut st = IndexMap::default();
            st.insert(loc("Left Torso"), loc("Front Left Leg"));
            st.insert(loc("Right Torso"), loc("Front Right Leg"));
            (legs.clone(), legs, st)
        } else {
            let mut legs: Vec<String> = vec![loc("Left Leg"), loc("Right Leg")];
            if mech_type == "tripod" {
                legs.push(loc("Center Leg"));
            }
            let mut limbs = vec![loc("Left Arm"), loc("Right Arm")];
            limbs.extend(legs.iter().cloned());
            let mut st = IndexMap::default();
            st.insert(loc("Left Torso"), loc("Left Arm"));
            st.insert(loc("Right Torso"), loc("Right Arm"));
            (legs, limbs, st)
        };

        let max_armor = locations.iter().map(|(l, v)| (l.clone(), v.armor.as_int())).collect();
        let max_rear_armor = locations.iter().filter_map(|(l, v)| v.rear_armor.map(|r| (l.clone(), r.as_int()))).collect();
        let max_structure = locations.iter().map(|(l, v)| (l.clone(), v.structure.as_int())).collect();
        let armor_type = locations.keys().map(|l| (l.clone(), ArmorType::Standard)).collect();
        let destroyed_leg_actuators = leg_locations.iter().map(|l| (l.clone(), 0)).collect();
        let crew_roles: Vec<&str> = if mech_type == "tripod" || mech_type == "quadvee" { vec!["pilot", "gunner"] } else { vec!["pilot"] };
        let crew = crew_roles.iter().map(|r| (r.to_string(), Crew { unconscious: false, check_pending: false, went_out_this_turn: false })).collect();
        let initial_sensor_slots = crits.get("Head").map_or(0, |h| h.iter().filter(|s| s.is_name("Sensors")).count() as i64);

        let mut m = Mech {
            mech_type: mech_type.to_string(),
            chassis: String::new(),
            model: String::new(),
            locations,
            crits,
            items,
            leg_locations,
            limb_locations,
            side_torso_child,
            max_armor,
            max_rear_armor,
            max_structure,
            armor_type,
            structure_type: StructureType::Standard,
            base_walk_mp: 4,
            base_jump_mp: 0,
            destroyed_leg_actuators,
            destroyed_hip_locations: IndexSet::default(),
            destroyed_jump_jet_ids: IndexSet::default(),
            base_heat_sinks: 0,
            heat_sink_type: "Single".to_string(),
            current_heat: 0,
            heat_mp_penalty: 0,
            heat_fire_modifier: 0,
            shutdown: false,
            tsm_active: false,
            deactivated_heat_sinks: 0,
            run_mp_multiplier: 1.5,
            myomer: "Standard".to_string(),
            destroyed_heat_sinks: IndexMap::default(),
            destroyed_slot_info: IndexMap::default(),
            armored_slots: IndexSet::default(),
            base_mechanical_jump_booster_mp: 0,
            mechanical_jump_booster_disabled: false,
            partial_wing_active: false,
            pilot_hits: 0,
            crew,
            engine_hits: 0,
            gyro_hits: 0,
            cockpit_hit: false,
            explosions: 0,
            destroyed: false,
            cause_of_death: None,
            crippled: false,
            crippled_at: None,
            prone: false,
            preexisting_damage_snapshot: IndexMap::default(),
            pre_attack_phase_snapshot: IndexMap::default(),
            movement_mode_this_turn: "running".to_string(),
            round_capable: IndexMap::default(),
            initial_sensor_slots,
            mass: None,
            engine_desc: None,
            cockpit_type: None,
            gyro_type: None,
            armor_desc: None,
            risc_heat_sink_kit: false,
            bv_view: None,
            is_industrial: None,
            structure_desc: None,
            tech_base: None,
            secondary_hits: None,
            console_lost: None,
            primary_dead: None,
            imp_mp: None,
            modular_armor: Vec::new(),
            attached: false,
            side_name: None,
            team: None,
            moved_this_turn: false,
            hex: None,
            facing: "N".to_string(),
            home_edge: None,
            gunnery: 4,
            piloting: 5,
            min_heat: 0,
            max_heat: 4,
            move_search: None,
            assumes_enemy_search: None,
            bot: "gladiator".to_string(),
            has_improved_jump_jets: false,
            has_xxl_engine: false,
            has_supercooled_myomer: false,
            equipment_systems: IndexMap::default(),
            has_tsm: false,
            has_stealth_armor: false,
            torso_cockpit: false,
            escalating_turns: IndexMap::default(),
            systems_used_this_turn: Vec::new(),
            heat_managed: false,
            systems_off: Vec::new(),
            radical_on: false,
            turn_number: 0,
            pfd_active: false,
            pfd_turns_used: 0,
            pfd_failed: false,
            narc_pods: Vec::new(),
            ecm_suites: Vec::new(),
            unjamming: Vec::new(),
            capacitors: Vec::new(),
            capacitor_heat: 0,
            tag_designated: None,
            move_mode: "Stand Still".to_string(),
            move_fc: 0,
            mp_spent: 0,
            movement_heat: 0,
            charging: None,
            dfa: None,
            deferred_end_of_move: None,
            ams_used: None,
            arc_action: None,
            arc_action_locked: None,
            armor_at_turn_start: None,
            arms_flipped: None,
            blocked_hex: None,
            breached_locations: None,
            hp_log: None,
            jump_only: None,
            magma_entered: None,
            other_unit_hexes: None,
            outside_heat: None,
            shield_raised: None,
            started_in_liquid: None,
            torso_twist: None,
            weapons_fired_this_turn: None,
            club: None,
            breached_slot_set: None,
            autocannon_crits: None,
            severed_limbs: None,
            severed_seen: None,
            bv_built: None,
            turret_last_offset: None,
            taser_interference_until: None,
            taser_shutdown_until: None,
            tsemp_hits: None,
            tsemp_interference_until: None,
            mech_turret_dir: None,
            home_edge_row: None,
            stuck: None,
            tsemp_shutdown_until: None,
            imp_until: None,
            imp_level: None,
            imp_started: None,
            imp_missiles: None,
        };
        snapshot_round_capability(&mut m);
        m
    }
}

pub fn snapshot_round_capability(mech: &mut Mech) {
    let mut rc = IndexMap::default();
    for (l, slots) in &mech.crits {
        rc.insert(l.clone(), slots.iter().any(|s| is_crit_target(s, &mech.items)));
    }
    mech.round_capable = rc;
}

/// Consciousness Number table: target number to stay conscious after a pilot hit, or to wake up.
pub fn consciousness_target_number(pilot_hits: i64) -> Result<i64, String> {
    match pilot_hits {
        1 => Ok(3),
        2 => Ok(5),
        3 => Ok(7),
        4 => Ok(10),
        5 => Ok(11),
        _ => Err(format!(
            "No Consciousness Number table entry for {} pilot hits (table only covers 1-5; 6+ should be unreachable - is_destroyed() kills the mech at 6 pilot hits before a consciousness roll could see that count).",
            pilot_hits
        )),
    }
}

pub fn is_quad(mech: &Mech) -> bool {
    QUAD_TYPES.contains(&mech.mech_type.as_str())
}

/// Legs still on the 'Mech whose hip is destroyed.
pub fn live_hip_legs(mech: &Mech) -> Vec<String> {
    mech.destroyed_hip_locations.iter().filter(|l| !mech.leg_locations.iter().any(|d| &d == l && mech.locations[d.as_str()].destroyed)).cloned().collect()
}

pub fn destroyed_leg_count(mech: &Mech) -> i64 {
    mech.leg_locations.iter().filter(|l| mech.locations[l.as_str()].destroyed).count() as i64
}

/// How many hip hits have their standard effects.
pub fn hip_effects(mech: &Mech) -> i64 {
    let hips = live_hip_legs(mech).len() as i64;
    if !is_quad(mech) {
        return hips;
    }
    0.max(hips - 1) + if destroyed_leg_count(mech) == 2 { 1 } else { 0 }
}

/// One level per hex moved forward, none backward (pp.90, 99).
pub fn ground_level_limited(mech: &Mech) -> bool {
    if !is_quad(mech) {
        return !mech.destroyed_hip_locations.is_empty();
    }
    hip_effects(mech) > 0 || destroyed_leg_count(mech) >= 3
}

pub fn has_hd_gyro(mech: &Mech) -> bool {
    mech.gyro_type.as_deref().unwrap_or("").to_uppercase().contains("HEAVY")
}

pub fn gyro_destroyed(mech: &Mech) -> bool {
    mech.gyro_hits >= if has_hd_gyro(mech) { 4 } else { 2 }
}

/// Shield sizes: (name, Damage Absorbance, Damage Capacity, Walking MP penalty, no jumping).
pub const SHIELD_SIZES: [(&str, i64, i64, i64, bool); 3] = [("SMALL", 3, 11, 0, false), ("MEDIUM", 5, 18, 1, false), ("LARGE", 7, 25, 1, true)];

fn norm_name(name: &str) -> String {
    name.replace(' ', "").to_uppercase()
}

/// [(arm, shield item, size)] for the shields still on the 'Mech. (No `_no_shields` memo: speed only.)
pub fn mech_shields(mech: &Mech) -> Vec<(String, ItemId, &'static str)> {
    let mut out = Vec::new();
    let mut seen: Vec<ItemId> = Vec::new();
    for arm in ["Left Arm", "Right Arm"] {
        if !mech.locations.contains_key(arm) || mech.locations[arm].destroyed {
            continue;
        }
        if let Some(slots) = mech.crits.get(arm) {
            for s in slots {
                if let Slot::Item(id) = s {
                    // most slots are not shields: say so without building the upper-case name
                    if let Some((buf, len)) = norm_ascii(&mech.items[*id].name, false) {
                        if !has_bytes(&buf[..len], b"SHIELD") {
                            continue;
                        }
                    }
                    let n = norm_name(&mech.items[*id].name);
                    if n.contains("SHIELD") && !n.contains("BLUESHIELD") && !seen.contains(id) {
                        seen.push(*id);
                        let size = SHIELD_SIZES.iter().find(|(k, ..)| n.contains(k)).map_or("MEDIUM", |t| t.0);
                        out.push((arm.to_string(), *id, size));
                    }
                }
            }
        }
    }
    out
}

pub fn shield_row(size: &str) -> (&'static str, i64, i64, i64, bool) {
    *SHIELD_SIZES.iter().find(|r| r.0 == size).unwrap()
}

pub const TRIPOD_DEDICATED_PILOT_MODIFIER: i64 = -1;
pub const TRIPOD_CREW_DISABLED_MODIFIER: i64 = 2;

pub fn tripod_pilot_modifier(mech: &Mech) -> i64 {
    if mech.mech_type != "tripod" {
        return 0;
    }
    if mech.crew["pilot"].unconscious {
        TRIPOD_CREW_DISABLED_MODIFIER
    } else {
        TRIPOD_DEDICATED_PILOT_MODIFIER
    }
}

pub fn physical_attacker_modifier(mech: &Mech) -> i64 {
    tripod_pilot_modifier(mech) + if is_superheavy(mech) { SUPERHEAVY_PHYSICAL_MODIFIER } else { 0 }
}

pub fn tripod_gunner_modifier(mech: &Mech) -> i64 {
    if mech.mech_type != "tripod" || !mech.crew.contains_key("gunner") {
        return 0;
    }
    if mech.crew["gunner"].unconscious {
        TRIPOD_CREW_DISABLED_MODIFIER
    } else {
        0
    }
}

pub fn has_technical_officer(mech: &Mech) -> bool {
    mech.mech_type == "tripod" && is_superheavy(mech)
}

pub fn has_command_console(mech: &Mech) -> bool {
    mech.cockpit_type.as_deref().unwrap_or("").to_uppercase().contains("COMMAND") || has_technical_officer(mech)
}

pub const TECHNICAL_OFFICER_HEAT_BONUS: i64 = 2;

pub fn console_active(mech: &Mech) -> bool {
    has_command_console(mech) && !mech.console_lost.unwrap_or(false) && mech.secondary_hits.unwrap_or(0) < 6
}

pub fn technical_officer_bonus(mech: &Mech) -> i64 {
    if has_technical_officer(mech) && console_active(mech) {
        TECHNICAL_OFFICER_HEAT_BONUS
    } else {
        0
    }
}

pub fn mark_consciousness_check_pending(mech: &mut Mech) {
    for state in mech.crew.values_mut() {
        if !state.unconscious {
            state.check_pending = true;
        }
    }
}

/// The MechWarrior takes n hits (a consciousness check follows); head / heat hits reach the console's second warrior.
pub fn pilot_hit(mech: &mut Mech, n: i64, head: bool) {
    mech.pilot_hits += n;
    mark_consciousness_check_pending(mech);
    if head && console_active(mech) {
        mech.secondary_hits = Some(mech.secondary_hits.unwrap_or(0) + n);
    }
}

/// The secondary warrior becomes the pilot for good (p.203). Returns the log line.
pub fn console_takes_over(mech: &mut Mech, why: &str) -> String {
    mech.pilot_hits = mech.secondary_hits.unwrap_or(0);
    mech.console_lost = Some(true);
    mech.primary_dead = Some(false);
    for state in mech.crew.values_mut() {
        state.unconscious = false;
    }
    format!("  {}: the command console's MechWarrior takes over as pilot ({}, p.203).", mech.side_name.as_deref().unwrap_or(""), why)
}

/// End Phase seat swap (p.203).
pub fn swap_warriors(mech: &mut Mech) {
    let (a, b) = (mech.secondary_hits.unwrap_or(0), mech.pilot_hits);
    mech.pilot_hits = a;
    mech.secondary_hits = Some(b);
    let dead = mech.primary_dead.unwrap_or(false);
    mech.primary_dead = Some(false);
    if dead {
        mech.secondary_hits = Some(6);
    }
    for state in mech.crew.values_mut() {
        state.unconscious = false;
    }
}

pub fn has_torso_cockpit(mech: &Mech) -> bool {
    mech.cockpit_type.as_deref().unwrap_or("").to_uppercase().contains("TORSO")
}

pub fn has_small_cockpit(mech: &Mech) -> bool {
    mech.cockpit_type.as_deref().unwrap_or("").to_uppercase().contains("SMALL")
}

pub fn head_hit_hurts_pilot(mech: &Mech) -> bool {
    !has_torso_cockpit(mech)
}

pub fn torso_cockpit_sensor_penalty(mech: &Mech) -> i64 {
    if !has_torso_cockpit(mech) {
        return 0;
    }
    let hit: Vec<&String> = mech.destroyed_slot_info.iter().filter(|(_, info)| info.name == "Sensors").map(|((l, _), _)| l).collect();
    if hit.len() >= 3 || (hit.len() == 2 && hit.iter().all(|l| *l == "Head")) {
        4
    } else {
        0
    }
}

pub fn all_crew_unconscious(mech: &Mech) -> bool {
    mech.crew.values().all(|s| s.unconscious)
}

pub fn legs_gone(mech: &Mech) -> bool {
    let threshold = if is_quad(mech) { 4 } else { 2 };
    destroyed_leg_count(mech) >= threshold
}

pub fn is_immobile(mech: &Mech) -> bool {
    mech.shutdown || all_crew_unconscious(mech) || legs_gone(mech)
}

pub fn pilot_unconscious(mech: &Mech) -> bool {
    mech.crew["pilot"].unconscious
}

/// Is any weapon left (Core p.99's "ranged weapons")? `damage_resolution::get_weapons`.
fn has_ranged_weapon(mech: &Mech) -> bool {
    !crate::damage_resolution::get_weapons(mech).is_empty()
}

/// True if the 'Mech is destroyed (and records the cause the first time). Reads config.FIGHT_TO_THE_DEATH.
pub fn is_destroyed(mech: &mut Mech, to_the_death: bool) -> bool {
    if mech.destroyed {
        return true;
    }
    if mech.locations["Center Torso"].destroyed {
        mech.destroyed = true;
        mech.cause_of_death = Some("Center Torso Destroyed".into());
        return true;
    }
    if mech.locations["Head"].destroyed && !has_torso_cockpit(mech) {
        mech.destroyed = true;
        mech.cause_of_death = Some("Head Destroyed".into());
        return true;
    }
    if !to_the_death && legs_gone(mech) {
        mech.destroyed = true;
        mech.cause_of_death = Some("Legs Destroyed".into());
        return true;
    }
    if mech.cockpit_hit {
        mech.destroyed = true;
        mech.cause_of_death = Some("Cockpit Destroyed".into());
        return true;
    }
    if mech.pilot_hits >= 6 && console_active(mech) {
        if !mech.primary_dead.unwrap_or(false) {
            mech.primary_dead = Some(true);
            for state in mech.crew.values_mut() {
                state.unconscious = true;
            }
        }
    } else if mech.pilot_hits >= 6 {
        mech.destroyed = true;
        mech.cause_of_death = Some("6 Pilot Hits".into());
        return true;
    }
    if mech.engine_hits >= engine_hits_to_destroy(mech) {
        mech.destroyed = true;
        mech.cause_of_death = Some("Engine Destroyed".into());
        return true;
    }
    if gyro_destroyed(mech) && !to_the_death {
        mech.destroyed = true;
        mech.cause_of_death = Some("Gyro Destroyed".into());
        return true;
    }
    if to_the_death && is_immobile(mech) && legs_gone(mech) && !has_ranged_weapon(mech) {
        mech.destroyed = true;
        mech.cause_of_death = Some("Immobile, No Ranged Weapons".into());
        return true;
    }
    false
}

/// Crippling Damage (BattleMech Manual): see the Python's docstring.
pub fn is_crippled(mech: &Mech) -> bool {
    if mech.pilot_hits >= 4 {
        return true;
    }
    if mech.initial_sensor_slots > 0 {
        let current = mech.crits.get("Head").map_or(0, |h| h.iter().filter(|s| s.is_name("Sensors")).count());
        if current == 0 {
            return true;
        }
    }
    if mech.gyro_hits >= 1 && mech.engine_hits >= 1 {
        return true;
    }
    if mech.engine_hits >= 2 {
        return true;
    }
    if mech.locations["Left Torso"].destroyed || mech.locations["Right Torso"].destroyed {
        return true;
    }
    let mut damaged_limbs = 0;
    for limb in &mech.limb_locations {
        let v = &mech.locations[limb.as_str()];
        if v.destroyed || v.structure < Num::I(mech.max_structure[limb.as_str()]) {
            damaged_limbs += 1;
        }
    }
    if damaged_limbs >= 3 {
        return true;
    }
    let mut damaged_torsos = 0;
    for t in ["Left Torso", "Right Torso", "Center Torso"] {
        let v = &mech.locations[t];
        if v.armor <= Num::I(0) && v.structure < Num::I(mech.max_structure[t]) {
            damaged_torsos += 1;
        }
    }
    damaged_torsos >= 2
}

/// Current effective walking MP (leg damage, TSM, heat, IMP).
pub fn compute_walk_mp(mech: &Mech) -> i64 {
    0.max(damage_walk_mp(mech) + if mech.tsm_active { 2 } else { 0 } - mech.heat_mp_penalty - mech.imp_mp.unwrap_or(0))
}

fn has_modular_armor(mech: &Mech) -> bool {
    mech.modular_armor.iter().any(|id| mech.items[*id].modular_points.unwrap_or(0) > 0)
}

fn damage_walk_mp(mech: &Mech) -> i64 {
    let destroyed_legs: Vec<&String> = mech.leg_locations.iter().filter(|l| mech.locations[l.as_str()].destroyed).collect();
    let quad = is_quad(mech);
    if destroyed_legs.len() >= if quad { 3 } else { 1 } {
        return 1;
    }
    let mut penalty = destroyed_legs.len() as i64;
    for l in &mech.leg_locations {
        if !destroyed_legs.contains(&l) {
            penalty += mech.destroyed_leg_actuators.get(l).copied().unwrap_or(0);
        }
    }
    if quad && !live_hip_legs(mech).is_empty() {
        penalty -= 1;
    }
    penalty += mech_shields(mech).iter().map(|(_, _, size)| shield_row(size).3).sum::<i64>();
    if has_modular_armor(mech) {
        penalty += 1;
    }
    1.max(mech.base_walk_mp - penalty)
}

/// Current effective running MP: ceil(walk * multiplier), Hardened legs -1.
pub fn compute_running_mp(mech: &Mech) -> i64 {
    let mut running = (compute_walk_mp(mech) as f64 * mech.run_mp_multiplier).ceil() as i64;
    if running > 0 && mech.leg_locations.iter().any(|l| mech.armor_type.get(l) == Some(&ArmorType::Hardened)) {
        running = 1.max(running - 1);
    }
    running
}

fn is_aes(name: &str) -> bool {
    match norm_ascii(name, true) {
        Some((buf, n)) => {
            let t = &buf[..n];
            t.ends_with(b"AES") || has_bytes(t, b"ACTUATORENHANCEMENT")
        }
        None => {
            let n = name.replace(' ', "").replace('-', "").to_uppercase();
            n.ends_with("AES") || n.contains("ACTUATORENHANCEMENT")
        }
    }
}

/// `name` with spaces (and hyphens too, when `hyphens`) dropped and in upper case, written into a buffer on the stack:
/// (buffer, length). None for a name that is not plain ASCII or is too long - the caller then builds the String as
/// the Python does. Speed only: these name tests run millions of times a battle.
pub fn norm_ascii(name: &str, hyphens: bool) -> Option<([u8; 96], usize)> {
    if !name.is_ascii() {
        return None;
    }
    let mut buf = [0u8; 96];
    let mut n = 0;
    for c in name.bytes() {
        if c == b' ' || (hyphens && c == b'-') {
            continue;
        }
        if n == buf.len() {
            return None;
        }
        buf[n] = c.to_ascii_uppercase();
        n += 1;
    }
    Some((buf, n))
}

pub fn has_bytes(text: &[u8], needle: &[u8]) -> bool {
    text.windows(needle.len()).any(|w| w == needle)
}

fn slot_name<'a>(mech: &'a Mech, s: &'a Slot) -> &'a str {
    match s {
        Slot::Name(n) => n,
        Slot::Item(id) => &mech.items[*id].name,
    }
}

/// {location: true (working) / false (an AES slot there was hit)} for every location that mounts AES.
fn aes_by_location(mech: &Mech) -> IndexMap<String, bool> {
    let mut status = IndexMap::default();
    for (loc, slots) in &mech.crits {
        if slots.iter().any(|s| is_aes(slot_name(mech, s))) {
            status.insert(loc.clone(), true);
        }
    }
    for ((loc, _), info) in &mech.destroyed_slot_info {
        if is_aes(&info.name) {
            status.insert(loc.clone(), false);
        }
    }
    status
}

pub fn arm_aes_working(mech: &Mech, arm: &str) -> bool {
    // `aes_by_location(mech).get(arm) == Some(&true)`, looking at this one location only
    let mounted = mech.crits.get(arm).is_some_and(|slots| slots.iter().any(|s| is_aes(slot_name(mech, s))));
    mounted && !mech.destroyed_slot_info.iter().any(|((loc, _), info)| loc == arm && is_aes(&info.name))
}

pub fn leg_aes_working(mech: &Mech) -> bool {
    // `aes_by_location(mech).get(l) == Some(&true)` for every leg, one location at a time
    mech.leg_locations.iter().all(|l| arm_aes_working(mech, l))
}

/// Current effective jump MP.
pub fn compute_jump_mp(mech: &Mech) -> i64 {
    if mech_shields(mech).iter().any(|(_, _, size)| shield_row(size).4) {
        return 0;
    }
    let mut jet_mp = 0.max(mech.base_jump_mp - mech.destroyed_jump_jet_ids.len() as i64);
    if jet_mp != 0 && has_modular_armor(mech) {
        jet_mp -= 1;
    }
    jet_mp = 0.max(jet_mp - mech.imp_mp.unwrap_or(0));
    if jet_mp == 0 || !mech.partial_wing_active {
        return jet_mp;
    }
    jet_mp + if mech.mass.unwrap_or(0) >= 60 { 1 } else { 2 }
}

pub fn heat_sink_rate(mech: &Mech) -> i64 {
    let t = mech.heat_sink_type.replace(' ', "").to_uppercase();
    if t.contains("DOUBLE") || t.contains("LASER") {
        2
    } else {
        1
    }
}

pub fn working_heat_sinks(mech: &Mech) -> i64 {
    0.max(mech.base_heat_sinks - mech.destroyed_heat_sinks.values().sum::<i64>())
}

pub fn active_heat_sinks(mech: &Mech) -> i64 {
    0.max(working_heat_sinks(mech) - mech.deactivated_heat_sinks)
}

pub fn compute_heat_dissipation(mech: &Mech) -> i64 {
    active_heat_sinks(mech) * heat_sink_rate(mech) + if mech.partial_wing_active { 3 } else { 0 }
}

pub fn compute_mechanical_jump_booster_mp(mech: &Mech) -> i64 {
    if mech.mechanical_jump_booster_disabled {
        0
    } else {
        mech.base_mechanical_jump_booster_mp
    }
}

pub fn display_crits(mech: &Mech, location: &str) -> Vec<String> {
    mech.crits[location].iter().map(|s| slot_name(mech, s).to_string()).collect()
}
