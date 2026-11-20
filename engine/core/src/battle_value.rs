// Translated from INTEGRATION__battle_value.py: Battle Value (BV 2.0) of a 'Mech as built, from MegaMek's BV calculators
// (item BVs from mechsim/equipment_bv.json). Princess's heat map weighs her units by it. Only the as-built number with the
// pilot's skill is translated (current=False, skill=True): the report lines and the "as it stands now" form are not.
use crate::fasthash::{HashMap, HashSet};
use std::sync::OnceLock;

use crate::fasthash::IndexMap;
use serde_json::Value;

use crate::battle::{Battle, UnitId};
use crate::equipment::Slot;
use crate::mech_state::*;

const BV_JSON: &str = include_str!("../../../mechsim/equipment_bv.json");

fn items_db() -> &'static HashMap<String, Value> {
    static DB: OnceLock<HashMap<String, Value>> = OnceLock::new();
    DB.get_or_init(|| {
        let v: Value = serde_json::from_str(BV_JSON).expect("equipment_bv.json");
        v["items"].as_object().unwrap().iter().map(|(k, e)| (k.clone(), e.clone())).collect()
    })
}

/// The skill multipliers, [gunnery][piloting] from 0 to 8 (4 / 5 = 1.00). Public for Combat Lab, whose page works a
/// unit's BV out for any pilot from its 4 / 5 value: BV = floor(BV(4/5) x SKILL_TABLE[g][p] + 0.5), as `battle_value`.
pub const SKILL_TABLE: [[f64; 9]; 9] = [
    [2.42, 2.31, 2.21, 2.10, 1.93, 1.75, 1.68, 1.59, 1.50],
    [2.21, 2.11, 2.02, 1.92, 1.76, 1.60, 1.54, 1.46, 1.38],
    [1.93, 1.85, 1.76, 1.68, 1.54, 1.40, 1.35, 1.28, 1.21],
    [1.66, 1.58, 1.51, 1.44, 1.32, 1.20, 1.16, 1.10, 1.04],
    [1.38, 1.32, 1.26, 1.20, 1.10, 1.00, 0.95, 0.90, 0.85],
    [1.31, 1.19, 1.13, 1.08, 0.99, 0.90, 0.86, 0.81, 0.77],
    [1.24, 1.12, 1.07, 1.02, 0.94, 0.85, 0.81, 0.77, 0.72],
    [1.17, 1.06, 1.01, 0.96, 0.88, 0.80, 0.76, 0.72, 0.68],
    [1.10, 0.99, 0.95, 0.90, 0.83, 0.75, 0.71, 0.68, 0.64],
];
const ARMOR_FACTOR: f64 = 2.5;

/// BV_TRACE=1 prints each unit's run / jump MP, defensive and offensive values and heat efficiency to stderr (BV_TRACE=2 also every
/// weapon's BV and heat): how the comparison with MegaMek's report (tests/check_bv_megamek.py) was diagnosed. Read once.
fn trace_level() -> u8 {
    static LEVEL: OnceLock<u8> = OnceLock::new();
    *LEVEL.get_or_init(|| std::env::var("BV_TRACE").ok().and_then(|v| v.parse().ok()).unwrap_or(0))
}
const ARMS: [&str; 2] = ["Left Arm", "Right Arm"];
const SIDE_TORSOS: [&str; 2] = ["Left Torso", "Right Torso"];
const LIGHT_EXPLOSIVES: [&str; 8] = ["F_GAUSS", "F_HVAC", "F_HYPER", "F_TSEMP", "F_TASER", "F_B_POD", "F_M_POD", "F_PPC"];
const NON_EXPLOSIVE_WEAPON_AMMO: [&str; 6] = ["AC_ROTARY", "AC", "AC_IMP", "AC_PRIMITIVE", "PAC", "LAC"];

fn armor_type_multiplier(t: Option<&ArmorType>) -> f64 {
    match t {
        Some(ArmorType::Hardened) => 2.0,
        Some(ArmorType::Reactive) | Some(ArmorType::Reflective) | Some(ArmorType::BallisticReinforced) => 1.5,
        Some(ArmorType::FerroLamellor) | Some(ArmorType::AntiPenetrativeAblation) => 1.2,
        Some(ArmorType::HeatDissipating) => 1.1,
        _ => 1.0,
    }
}

/// Java's Math.round: halves round up.
fn jround(x: f64) -> i64 {
    (x + 0.5).floor() as i64
}

fn tmm(mp: i64, jumped: bool) -> i64 {
    if mp == 0 && !jumped {
        return 0;
    }
    let mut base = 0;
    for (low, value) in [(25, 6), (18, 5), (10, 4), (7, 3), (5, 2), (3, 1)] {
        if mp >= low {
            base = value;
            break;
        }
    }
    base + if jumped { 1 } else { 0 }
}

fn skill_factor(gunnery: i64, piloting: i64) -> f64 {
    SKILL_TABLE[gunnery.clamp(0, 8) as usize][piloting.clamp(0, 8) as usize]
}

struct Item {
    canonical: String,
    location: String,
    slots_by_location: IndexMap<String, i64>,
    flags: HashSet<String>,
    kind: Option<String>,
    bv: f64,
    ammo_type: Option<String>,
    rack_size: i64,
    heat: f64,
    heat_adjust: f64,
    internal: String,
    has_bv: bool,
    link: Option<usize>,
    rear: bool,
    turret: bool,
    explosive: bool,
    name: String,
    equip_name: String,
    /// a slot of it is tagged "(armored)" in the unit file (Armored Components, Core p.207)
    armored: bool,
}

impl Item {
    fn slots(&self) -> i64 {
        self.slots_by_location.values().sum()
    }
    fn has(&self, f: &str) -> bool {
        self.flags.contains(f)
    }
    fn any(&self, fs: &[&str]) -> bool {
        fs.iter().any(|f| self.flags.contains(*f))
    }
}

/// Where MegaMek's `isExplosive` differs from the equipment table (checked against every MegaMek equipment type, 2026-11-20): the BV
/// goes by MegaMek. (The table's flag also drives critical-hit explosions in play: those twelve are on the rules-review list.)
const EXPLOSIVE_PER_MEGAMEK: [(&str, bool); 12] = [("climprovedheavylargelaser", true), ("climprovedmediumheavylaser", true), ("climprovedsmallheavylaser", true),
    ("israilgun", true), ("isrischyperlaser", true), ("ismagshotgrammo", false), ("isc3sensors", false), ("clfluidgunammo", true), ("extendedfueltank", true),
    ("isprototypeimprovedjumpjet", true), ("lamfueltank", true), ("isriscemergencycoolantsystem", true)];

/// Prototype and primitive weapons: the equipment table maps them onto the ordinary weapon, but MegaMek prices them apart. (canonical
/// key, BV, heat) for a raw name that says "prototype" (all but the "primitive" rows), taken from MegaMek's equipment types by
/// comparing every one with equipment_bv.json (2026-11-20). `f64::NAN` leaves the table's own value.
const PROTOTYPE_BV: [(&str, f64, f64); 17] = [("islargepulselaser", 108.0, f64::NAN), ("iserlargelaser", 136.0, f64::NAN), ("ismediumpulselaser", 43.0, f64::NAN),
    ("issmallpulselaser", 11.0, f64::NAN), ("clermediumlaser", 62.0, f64::NAN), ("clersmalllaser", 17.0, f64::NAN), ("clultraac2", 56.0, f64::NAN),
    ("clultraac10", f64::NAN, 4.0), ("clultraac20", 281.0, 8.0), ("cllbxac2", 42.0, f64::NAN), ("cllbxac5", 83.0, f64::NAN), ("clstreaksrm4", 59.0, f64::NAN),
    ("clstreaksrm6", 89.0, f64::NAN), ("rl10", 15.0, f64::NAN), ("rl15", 18.0, f64::NAN), ("rl20", 19.0, f64::NAN), ("isnarcbeacon", 15.0, f64::NAN)];
/// The same for "primitive prototype" weapons (heat only: their BV matches).
const PRIMITIVE_HEAT: [(&str, f64); 4] = [("mediumlaser", 5.0), ("largelaser", 12.0), ("smalllaser", 2.0), ("ppc", 15.0)];

fn equipment_items(b: &Battle, u: UnitId) -> Vec<Item> {
    let m = &b.units[u];
    let mut seen: HashMap<usize, usize> = HashMap::default();
    let mut items: Vec<Item> = Vec::new();
    for (location, slots) in &m.crits {
        for (slot_idx, slot) in slots.iter().enumerate() {
            let Slot::Item(id) = slot else { continue };
            let armored = m.armored_slots.contains(&(location.clone(), slot_idx));
            if let Some(&ix) = seen.get(id) {
                *items[ix].slots_by_location.entry(location.clone()).or_insert(0) += 1;
                items[ix].armored |= armored;
                continue;
            }
            let eq = &m.items[*id];
            let entry = b.db.lookup_equipment(&eq.name);
            let record = entry.and_then(|e| items_db().get(&e.canonical_name().replace(' ', "").to_lowercase()));
            let canonical = entry.map(|e| e.canonical_name().to_lowercase()).unwrap_or_default();
            let flags: HashSet<String> = record.and_then(|r| r["flags"].as_array()).map(|a| a.iter().filter_map(|x| x.as_str().map(|s| s.to_string())).collect()).unwrap_or_default();
            let raw_up = eq.name.to_uppercase();
            let canon_key = canonical.replace(' ', "");
            let (mut over_bv, mut over_heat) = (f64::NAN, f64::NAN);
            if raw_up.contains("PRIMITIVE") || raw_up == "PPCP" {
                if let Some((_, h)) = PRIMITIVE_HEAT.iter().find(|(n, _)| *n == canon_key) { over_heat = *h; }
            } else if raw_up.contains("PROTOTYPE") || raw_up.contains("(CP)") {
                if let Some((_, v, h)) = PROTOTYPE_BV.iter().find(|(n, _, _)| *n == canon_key) { over_bv = *v; over_heat = *h; }
            }
            let g = |k: &str| record.and_then(|r| r.get(k));
            let mut sbl = IndexMap::default();
            sbl.insert(location.clone(), 1);
            seen.insert(*id, items.len());
            let explosive_key = canonical.replace(' ', "");
            items.push(Item {
                canonical,
                location: location.clone(),
                slots_by_location: sbl,
                flags,
                kind: g("kind").and_then(|v| v.as_str()).map(|s| s.to_string()),
                bv: if over_bv.is_nan() { g("bv").and_then(|v| v.as_f64()).unwrap_or(0.0) } else { over_bv },
                ammo_type: g("ammo_type").and_then(|v| v.as_str()).map(|s| s.to_string()),
                rack_size: g("rack_size").and_then(|v| v.as_f64()).map_or(0, |f| f as i64),
                heat: if over_heat.is_nan() { g("heat").and_then(|v| v.as_f64()).unwrap_or(0.0) } else { over_heat },
                heat_adjust: g("heat_adjust").and_then(|v| v.as_f64()).unwrap_or(0.0),
                internal: g("internal").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                has_bv: g("bv").map_or(false, |v| !v.is_null()),
                link: None,
                rear: eq.rear_mounted,
                turret: eq.turret_mounted,
                explosive: EXPLOSIVE_PER_MEGAMEK.iter().find(|(n, _)| *n == explosive_key).map_or(eq.is_explosive, |(_, v)| *v),
                name: g("name").and_then(|v| v.as_str()).map(|s| s.to_string()).unwrap_or_else(|| eq.name.clone()),
                equip_name: eq.name.clone(),
                armored,
            });
        }
    }
    items
}

struct Calc<'a> {
    m: &'a Mech,
    items: Vec<Item>,
    engine_sides: i64,
    fusion: bool,
    quad: bool,
    clan_mech: bool,
    clan_structure: bool,
    defensive: f64,
    offensive: f64,
    walk: i64,
    run: i64,
    jump: i64,
    umu: i64,
    improved_jets: bool,
    has_tc: bool,
}

fn up(s: &Option<String>) -> String {
    s.as_deref().unwrap_or("").to_uppercase()
}

fn engine_of(m: &Mech) -> (i64, bool, bool) {
    let desc = up(&m.engine_desc);
    let tech = up(&m.tech_base);
    let clan_chassis = tech.starts_with("CLAN") || tech.contains("MIXED (CLAN");
    let clan = if desc.contains("(CLAN)") { true } else if desc.contains("(IS)") || desc.contains("(INNER SPHERE)") { false } else { clan_chassis };
    let superheavy = m.mass.unwrap_or(0) > 100;
    let sides = if desc.contains("XXL") {
        if superheavy { 2 } else if clan { 4 } else { 6 }
    } else if desc.contains("XL") {
        if superheavy { if clan { 1 } else { 2 } } else if clan { 2 } else { 3 }
    } else if desc.contains("LIGHT") {
        if superheavy { 1 } else { 2 }
    } else {
        0
    };
    let fusion = !["ICE", "I.C.E", "FUEL", "FISSION"].iter().any(|w| desc.contains(w));
    (sides, fusion, clan)
}

fn engine_multiplier(sides: i64) -> f64 {
    if sides >= 6 { 0.25 } else if sides >= 3 { 0.5 } else if sides == 2 { 0.75 } else if sides == 1 { 0.825 } else { 1.0 }
}

impl<'a> Calc<'a> {
    fn new(b: &'a Battle, u: UnitId) -> Calc<'a> {
        let m = &b.units[u];
        let mut items = equipment_items(b, u);
        let (engine_sides, fusion, _clan_engine) = engine_of(m);
        let tech = up(&m.tech_base);
        let clan_mech = tech.starts_with("CLAN") || tech.contains("MIXED (CLAN");
        let structure = up(&m.structure_desc);
        let clan_structure = clan_mech && !structure.starts_with("IS ");
        // _link_equipment: Artemis, Apollo and PPC capacitors work with a weapon in their own location
        for li in 0..items.len() {
            if items[li].kind.as_deref() != Some("misc") {
                continue;
            }
            let l = &items[li];
            let wants: Option<Box<dyn Fn(&Item) -> bool>> = if l.any(&["F_ARTEMIS", "F_ARTEMIS_PROTO", "F_ARTEMIS_V"]) {
                Some(Box::new(|w: &Item| w.has("F_ARTEMIS_COMPATIBLE")))
            } else if l.has("F_APOLLO") {
                Some(Box::new(|w: &Item| w.ammo_type.as_deref() == Some("MRM")))
            } else if l.has("F_PPC_CAPACITOR") {
                Some(Box::new(|w: &Item| w.has("F_PPC")))
            } else if l.any(&["F_RISC_LASER_PULSE_MODULE", "F_LASER_INSULATOR"]) {
                // a laser pulse module / insulator works with a laser in its own location (it was never linked: no RISC bonus)
                Some(Box::new(|w: &Item| w.has("F_LASER")))
            } else {
                None
            };
            let Some(wants) = wants else { continue };
            let loc = l.location.clone();
            let mut target = None;
            for (wi, w) in items.iter().enumerate() {
                if w.kind.as_deref() == Some("weapon") && w.link.is_none() && w.slots_by_location.contains_key(&loc) && wants(w) {
                    target = Some(wi);
                    break;
                }
            }
            if let Some(wi) = target {
                items[wi].link = Some(li);
            }
        }
        // Shields (BipedMek.getWalkMP, Mek.getJumpMP): each large or medium shield takes a walking MP; a large shield also takes all the
        // jump (and UMU) MP, a medium one a jump MP each
        let large_shields = items.iter().filter(|i| i.has("S_SHIELD_LARGE")).count() as i64;
        let medium_shields = items.iter().filter(|i| i.has("S_SHIELD_MEDIUM")).count() as i64;
        let mut walk = m.base_walk_mp - large_shields - medium_shields;
        if items.iter().any(|i| i.has("F_TSM")) {
            walk += 1;
        }
        // MegaMek's BV_CALCULATION counts an armed MASC or supercharger in the run MP (MPBoosters.calculateRunMP): either one doubles
        // the walk, both give x2.5, neither x1.5
        let masc = items.iter().any(|i| i.has("F_MASC") && !i.has("S_SUPERCHARGER") && !i.has("S_JET_BOOSTER"));
        let charger = items.iter().any(|i| i.has("F_MASC") && i.has("S_SUPERCHARGER"));
        let mut run = if masc && charger { (walk as f64 * 2.5).ceil() as i64 } else if masc || charger { walk * 2 } else { (walk as f64 * 1.5).ceil() as i64 };
        if m.armor_type.values().any(|t| *t == ArmorType::Hardened) {
            run = (run - 1).max(0);
        }
        let mut jump = m.base_jump_mp;
        if jump != 0 && m.partial_wing_active {
            jump += if m.mass.unwrap_or(0) >= 60 { 1 } else { 2 };
        }
        jump = (jump - medium_shields).max(0);
        jump = jump.max((m.base_mechanical_jump_booster_mp - medium_shields).max(0));
        if large_shields > 0 { jump = 0; }
        let umu = if large_shields > 0 { 0 } else { items.iter().filter(|i| i.has("F_UMU")).count() as i64 };
        let improved_jets = items.iter().any(|i| i.canonical.replace(' ', "").contains("improvedjumpjet"));
        Calc { m, items, engine_sides, fusion, quad: m.mech_type == "quad" || m.mech_type == "quadvee", clan_mech, clan_structure, defensive: 0.0, offensive: 0.0, walk, run, jump, umu, improved_jets, has_tc: false }
    }

    fn flag_at(&self, flag: &str, loc: &str) -> bool {
        self.items.iter().any(|i| i.has(flag) && i.slots_by_location.contains_key(loc))
    }
    fn has(&self, flag: &str) -> bool {
        self.items.iter().any(|i| i.has(flag))
    }

    fn armor(&mut self) {
        let m = self.m;
        let mut total = 0.0;
        for (loc, e) in &m.locations {
            let front = (m.max_armor.get(loc).copied().unwrap_or(e.armor.f() as i64)).max(0);
            let mut rear = 0;
            if e.rear_armor.is_some() {
                rear = m.max_rear_armor.get(loc).copied().unwrap_or(e.rear_armor.unwrap().f() as i64).max(0);
            }
            // Modular armor adds its 10 points a slot to the location, then goes through the same multipliers (MegaMek)
            let modular = 10 * self.items.iter().filter(|i| i.has("F_MODULAR_ARMOR") && i.slots_by_location.contains_key(loc)).count() as i64;
            let mut points = front + rear + modular;
            if loc == "Center Torso" && up(&m.cockpit_type).contains("TORSO-MOUNTED") {
                points += front + rear;
            }
            let mut mult = armor_type_multiplier(m.armor_type.get(loc));
            if self.has("F_BLUE_SHIELD") { mult += 0.2; }
            if self.flag_at("F_HARJEL_II", loc) { mult *= 1.1; }
            if self.flag_at("F_HARJEL_III", loc) { mult *= 1.2; }
            // Commercial armor is BAR 5: MegaMek halves its BV
            let bar = if up(&m.armor_desc).contains("COMMERCIAL") { 0.5 } else { 1.0 };
            total += points as f64 * mult * bar;
        }
        self.defensive += total * ARMOR_FACTOR;
    }

    fn structure(&mut self) {
        let m = self.m;
        let internal: i64 = m.locations.iter().map(|(loc, e)| m.max_structure.get(loc).copied().unwrap_or(e.structure.f() as i64).max(0)).sum();
        let st = up(&m.structure_desc);
        // "Endo-Composite" is its own structure type with no BV change; only Composite and Industrial halve it
        let composite = st.contains("COMPOSITE") && !st.contains("ENDO");
        let mut multiplier = if st.contains("INDUSTRIAL") || composite { 0.5 } else if st.contains("REINFORCED") { 2.0 } else { 1.0 };
        if self.has("F_BLUE_SHIELD") { multiplier += 0.2; }
        let engine = engine_multiplier(self.engine_sides);
        self.defensive += internal as f64 * 1.5 * multiplier * engine;
        let gyro = up(&m.gyro_type);
        let gyro_mult = if (gyro.contains("HEAVY") && !gyro.contains("SUPERHEAVY")) { 1.0 } else if gyro == "NONE" && !up(&m.cockpit_type).contains("INTERFACE") { 0.0 } else { 0.5 };
        self.defensive += m.mass.unwrap_or(0) as f64 * gyro_mult;
    }

    /// Armored Components (MegaMek Mek.getArmoredComponentBV): each armored piece of equipment adds 5% of its BV per slot (a flat 5 a
    /// slot when it has no BV); an armored gyro slot adds 5% of weight x gyro multiplier; any other armored system slot adds 5.
    fn armored_components(&mut self) {
        let m = self.m;
        let mut bv = 0.0;
        for i in &self.items {
            if !i.armored {
                continue;
            }
            bv += if i.bv > 0.0 { i.bv * 0.05 * i.slots() as f64 } else { 5.0 * i.slots() as f64 };
        }
        let gyro = up(&m.gyro_type);
        let gyro_mult = if (gyro.contains("HEAVY") && !gyro.contains("SUPERHEAVY")) { 1.0 } else if gyro == "NONE" && !up(&m.cockpit_type).contains("INTERFACE") { 0.0 } else { 0.5 };
        for (loc, slots) in &m.crits {
            for (idx, slot) in slots.iter().enumerate() {
                if !m.armored_slots.contains(&(loc.clone(), idx)) {
                    continue;
                }
                if let Slot::Name(n) = slot {
                    if n == "Gyro" { bv += m.mass.unwrap_or(0) as f64 * gyro_mult * 0.05; } else if n != "-Empty-" { bv += 5.0; }
                }
            }
        }
        self.defensive += bv;
    }

    fn defensive_equipment(&mut self) {
        let (mut ams_bv, mut ams_ammo_bv) = (0.0, 0.0);
        for i in &self.items {
            if i.kind.as_deref() == Some("ammo") && matches!(i.ammo_type.as_deref(), Some("AMS") | Some("APDS")) {
                ams_ammo_bv += i.bv;
            }
        }
        const DEF: [&str; 16] = ["F_ECM", "F_BAP", "F_VIRAL_JAMMER_DECOY", "F_VIRAL_JAMMER_HOMING", "F_AP_POD", "F_MASS", "F_HEAVY_BRIDGE_LAYER", "F_MEDIUM_BRIDGE_LAYER", "F_LIGHT_BRIDGE_LAYER", "F_BULLDOZER", "F_CHAFF_POD", "F_HARJEL_II", "F_HARJEL_III", "F_SPIKES", "F_MINESWEEPER", "F_SHIELD"];
        for i in &self.items {
            let counts = match i.kind.as_deref() {
                Some("weapon") => i.any(&["F_AMS", "F_M_POD", "F_B_POD"]),
                Some("misc") => i.any(&DEF),
                _ => false,
            };
            if !counts {
                continue;
            }
            self.defensive += i.bv;
            if i.kind.as_deref() == Some("weapon") && i.has("F_AMS") {
                ams_bv += i.bv;
            }
        }
        if ams_ammo_bv > 0.0 {
            self.defensive += ams_bv.min(ams_ammo_bv);
        }
    }

    fn location_case(&self, loc: &str) -> bool {
        // MegaMek (Mek.addClanCase, v0.51): a Clan 'Mech gets CASE in every location that holds explosive equipment, whatever its
        // structure (the old test also asked for Clan structure: an IS-structure Clan 'Mech like the Archer C 2 lost its CASE)
        self.flag_at("F_CASE", loc) || self.flag_at("F_CASEP", loc) || self.clan_mech
    }

    fn explosion_penalty_applies(&self, loc: &str) -> bool {
        if self.flag_at("F_CASEII", loc) {
            return false;
        }
        if ARMS.contains(&loc) && !self.quad {
            return match crate::damage_resolution::transfer_map(loc) {
                Some(side) => !self.location_case(loc) && self.explosion_penalty_applies(side),
                None => !self.location_case(loc) && self.explosion_penalty_applies_none(),
            };
        }
        if SIDE_TORSOS.contains(&loc) {
            return !self.location_case(loc) || self.engine_sides >= 3;
        }
        true
    }

    // TRANSFER_MAP.get(loc) is None only for a location with no transfer: the Python then calls it with None, which is
    // not in any set: no flag, not an arm, not a side torso -> True
    fn explosion_penalty_applies_none(&self) -> bool {
        true
    }

    fn explosive_equipment(&mut self) {
        let mut sub = 0.0;
        // Blue Shield (MekBVCalculator.processExplosiveEquipment): 1 off for every body location (not the head) a hit there could
        // set off the field damper's explosion in: all but a CASE II location; a Clan 'Mech only the centre torso, legs and an
        // XL-or-larger side torso; an IS 'Mech with a light-engine-or-smaller side torso count of slots, CASE in the torso / arm spares it
        if self.has("F_BLUE_SHIELD") {
            let side_slots_small = self.engine_sides <= 2;
            let mut unprotected = 0;
            for loc in ["Center Torso", "Right Torso", "Left Torso", "Right Arm", "Left Arm", "Right Leg", "Left Leg"] {
                if self.flag_at("F_CASEII", loc) {
                    continue;
                }
                if self.clan_mech {
                    let torso = loc == "Right Torso" || loc == "Left Torso";
                    if loc != "Center Torso" && loc != "Right Leg" && loc != "Left Leg" && !(torso && self.engine_sides > 2) {
                        continue;
                    }
                } else if side_slots_small {
                    let torso_case = |t: &str| self.location_case(t);
                    if (loc == "Right Torso" || loc == "Left Torso") && self.location_case(loc) { continue; }
                    if loc == "Left Arm" && (self.location_case(loc) || torso_case("Left Torso")) { continue; }
                    if loc == "Right Arm" && (self.location_case(loc) || torso_case("Right Torso")) { continue; }
                }
                unprotected += 1;
            }
            sub += unprotected as f64;
        }
        for item in &self.items {
            // a PPC with a capacitor linked, and the capacitor itself, are explosive for BV (MegaMek's isExplosive): the table says no
            let capacitor_pair = item.has("F_PPC_CAPACITOR") || (item.kind.as_deref() == Some("weapon") && item.has("F_PPC") && item.link.is_some_and(|l| self.items[l].has("F_PPC_CAPACITOR")));
            if !item.explosive && !capacitor_pair {
                continue;
            }
            if item.kind.as_deref() == Some("weapon") {
                if let Some(at) = item.ammo_type.as_deref() {
                    if NON_EXPLOSIVE_WEAPON_AMMO.contains(&at) {
                        continue;
                    }
                }
                if item.has("F_PPC") && item.link.is_none() {
                    continue;
                }
            }
            if !self.explosion_penalty_applies(&item.location) {
                continue;
            }
            let mut subtract = 15.0;
            if item.kind.as_deref() == Some("weapon") && (item.any(&LIGHT_EXPLOSIVES) || (item.has("F_LASER") && item.has("S_IMPROVED"))) {
                subtract = 1.0;
            }
            if item.kind.as_deref() == Some("misc") && item.any(&["F_PPC_CAPACITOR", "F_RISC_LASER_PULSE_MODULE", "F_EMERGENCY_COOLANT_SYSTEM", "F_JUMP_JET"]) {
                subtract = 1.0;
            }
            if item.kind.as_deref() == Some("ammo") && item.ammo_type.as_deref() == Some("COOLANT_POD") {
                subtract = 1.0;
            }
            let slots = if item.has("F_HVAC") { 1 } else { item.slots() };
            sub += subtract * slots as f64;
            // (the Python subtracts as it goes; the running total is only read at the end)
        }
        self.defensive -= sub;
        if self.defensive < 1.0 {
            self.defensive = 1.0;
        }
    }

    fn defensive_factor(&mut self) {
        let m = self.m;
        let mut best = tmm(self.run, false).max(if self.jump != 0 { tmm(self.jump, true) } else { 0 }).max(if self.umu != 0 { tmm(self.umu, false) } else { 0 });
        let desc = up(&m.armor_desc);
        if desc.contains("STEALTH") || self.items.iter().any(|i| i.equip_name.to_uppercase().contains("STEALTH")) {
            best += 2;
        }
        if self.items.iter().any(|i| i.canonical.replace(' ', "").contains("nullsignature")) {
            best += 2;
        }
        if self.items.iter().any(|i| i.canonical.replace(' ', "").contains("chameleon")) {
            best += 2;
        }
        if self.items.iter().any(|i| i.canonical.replace(' ', "").contains("voidsignature")) {
            if best < 3 {
                best = 3;
            } else if best == 3 {
                best += 1;
            }
        }
        self.defensive *= 1.0 + best as f64 / 10.0;
    }

    /// A vibroblade is priced with the weapons (MegaMek HeatTrackingBVCalculator: one per arm, heat 7 / 5 / 3 for large / medium / small)
    fn is_vibroblade(i: &Item) -> bool {
        i.kind.as_deref() == Some("misc") && i.has("F_CLUB") && i.any(&["S_VIBRO_LARGE", "S_VIBRO_MEDIUM", "S_VIBRO_SMALL"])
    }

    fn offensive_weapon(&self, i: &Item) -> bool {
        if i.kind.as_deref() != Some("weapon") {
            return false;
        }
        if i.any(&["F_AMS", "F_B_POD", "F_M_POD"]) {
            return false;
        }
        i.bv > 0.0 || i.has("F_MGA")
    }

    fn is_arm(&self, i: &Item) -> bool {
        ARMS.contains(&i.location.as_str()) && !self.quad
    }

    fn arm_aes(&self, loc: &str) -> bool {
        self.items.iter().any(|i| i.has("F_ACTUATOR_ENHANCEMENT_SYSTEM") && i.slots_by_location.contains_key(loc))
    }

    fn capacitor_bv(w: &Item) -> f64 {
        let internal = w.internal.to_uppercase().replace(' ', "");
        match internal.as_str() {
            // the table's internal names are "Light PPC", "PPC", "Heavy PPC", "ISSNPPC" (MiscType.getBV goes by the weapon's class)
            "ISLIGHTPPC" | "LIGHTPPC" => 44.0,
            "ISPPC" | "PPC" => 88.0,
            "ISHEAVYPPC" | "HEAVYPPC" => 53.0,
            "ISSNUBNOSEPPC" | "ISSNPPC" => 87.0,
            "ISERPPC" => 114.0,
            "CLERPPC" => 136.0,
            _ => 0.0,
        }
    }

    fn weapon_bv(&self, wi: usize, rear_set: Option<&HashSet<usize>>) -> f64 {
        let item = &self.items[wi];
        let mut bv = if Self::is_vibroblade(item) { self.misc_bv(item) } else { item.bv };
        if item.has("F_MGA") {
            let mut s = 0.0;
            for i in &self.items {
                if i.kind.as_deref() == Some("weapon") && i.location == item.location && !i.has("F_MGA") && i.ammo_type == item.ammo_type {
                    s += i.bv;
                }
            }
            bv = s * 0.67;
        }
        if self.arm_aes(&item.location) && ARMS.contains(&item.location.as_str()) {
            bv *= 1.25;
        }
        if let Some(rs) = rear_set {
            if rs.contains(&wi) {
                bv /= 2.0;
            }
        }
        // MegaMek processWeapon: a drone's weapons count for 80% (before the capacitor / Artemis additions)
        if self.has("F_DRONE_OPERATING_SYSTEM") {
            bv *= 0.8;
        }
        if let Some(li) = item.link {
            let link = &self.items[li];
            if link.has("F_PPC_CAPACITOR") {
                bv += if link.bv != 0.0 { link.bv } else { Self::capacitor_bv(item) };
            } else if link.has("F_ARTEMIS") {
                bv *= 1.2;
            } else if link.has("F_ARTEMIS_PROTO") {
                bv *= 1.1;
            } else if link.has("F_ARTEMIS_V") {
                bv *= 1.3;
            } else if link.has("F_RISC_LASER_PULSE_MODULE") || link.has("F_APOLLO") {
                bv *= 1.15;
            }
        }
        if item.has("F_DIRECT_FIRE") && self.has_tc {
            bv *= 1.25;
        }
        bv
    }

    fn weapon_heat(&self, item: &Item) -> f64 {
        if Self::is_vibroblade(item) {
            return if item.has("S_VIBRO_LARGE") { 7.0 } else if item.has("S_VIBRO_MEDIUM") { 5.0 } else { 3.0 };
        }
        let mut heat = item.heat;
        if item.has("F_ONE_SHOT") {
            heat /= 4.0;
        }
        let at = item.ammo_type.as_deref();
        if matches!(at, Some("AC_ULTRA") | Some("AC_ULTRA_THB")) {
            heat *= 2.0;
        } else if at == Some("AC_ROTARY") {
            heat *= 6.0;
        }
        heat += item.heat_adjust;
        if item.has("F_LASER") {
            if let Some(li) = item.link {
                let l = &self.items[li];
                if l.has("F_RISC_LASER_PULSE_MODULE") {
                    heat += 2.0;
                } else if l.has("F_LASER_INSULATOR") {
                    heat = (heat - 1.0).max(1.0);
                }
            }
        }
        if matches!(at, Some("SRM_STREAK") | Some("LRM_STREAK") | Some("IATM")) {
            heat *= 0.5;
        }
        if item.has("F_PPC") && item.link.is_some() {
            heat += 5.0;
        }
        heat
    }

    fn built_dissipation(&self) -> i64 {
        let m = self.m;
        let t = m.heat_sink_type.replace(' ', "").to_uppercase();
        let rate = if t.contains("DOUBLE") || t.contains("LASER") { 2 } else { 1 };
        m.base_heat_sinks * rate + if m.partial_wing_active { 3 } else { 0 }
    }

    fn heat_efficiency(&self) -> f64 {
        let m = self.m;
        let mut efficiency = 6 + self.built_dissipation();
        let pods = self.items.iter().filter(|i| i.kind.as_deref() == Some("ammo") && i.ammo_type.as_deref() == Some("COOLANT_POD")).count() as i64;
        if pods > 0 {
            efficiency += (m.base_heat_sinks as f64 * pods as f64 / 5.0).ceil() as i64;
        }
        if self.has("F_EMERGENCY_COOLANT_SYSTEM") {
            efficiency += 4;
        }
        // Mek.getHeatCapacity: a radical heat sink system adds 40% (rounded up) of the working sinks
        if self.has("F_RADICAL_HEATSINK") {
            efficiency += (m.base_heat_sinks as f64 * 0.4).ceil() as i64;
        }
        let xxl = up(&m.engine_desc).contains("XXL");
        let mut run_heat = if xxl && self.fusion { 6 } else { 2 };
        if m.is_industrial.unwrap_or(false) || up(&m.cockpit_type).contains("INDUSTRIAL") {
            run_heat = 0;
        }
        if self.items.iter().any(|i| i.canonical.contains("supercooledmyomer")) {
            run_heat = 0;
        }
        let mut move_heat = run_heat;
        if self.jump > 0 {
            let mut jump_mp = self.jump;
            // MegaMek (Mek.getJumpHeat) does not count the Partial Wing's bonus MP in the jump heat
            if m.partial_wing_active && m.base_jump_mp != 0 {
                jump_mp -= if m.mass.unwrap_or(0) >= 60 { 1 } else { 2 };
            }
            if self.improved_jets {
                jump_mp = jump_mp / 2 + jump_mp % 2;
            }
            let jump_heat = if xxl { 6.max(jump_mp * 2) } else { 3.max(jump_mp) };
            if jump_heat > run_heat {
                move_heat = jump_heat;
            }
        }
        efficiency -= move_heat;
        if up(&m.armor_desc).contains("STEALTH") {
            efficiency -= 10;
        }
        if self.items.iter().any(|i| i.canonical.replace(' ', "").contains("chameleon")) {
            efficiency -= 6;
        }
        if self.items.iter().any(|i| i.canonical.replace(' ', "").contains("nullsignature")) {
            efficiency -= 10;
        }
        if self.items.iter().any(|i| i.canonical.replace(' ', "").contains("voidsignature")) {
            efficiency -= 10;
        }
        efficiency as f64
    }

    fn weapons(&mut self) {
        self.has_tc = self.has("F_TARGETING_COMPUTER") || self.items.iter().any(|i| i.canonical.replace(' ', "").contains("targetingcomputer"));
        let mut weapons: Vec<usize> = (0..self.items.len()).filter(|i| self.offensive_weapon(&self.items[*i])).collect();
        for arm in ARMS {
            if let Some(vi) = (0..self.items.len()).find(|i| Self::is_vibroblade(&self.items[*i]) && self.items[*i].location == arm) {
                weapons.push(vi);
            }
        }
        let front: Vec<usize> = weapons.iter().copied().filter(|w| !self.is_arm(&self.items[*w]) && !self.items[*w].turret && !self.items[*w].rear).collect();
        let rear: Vec<usize> = weapons.iter().copied().filter(|w| !self.is_arm(&self.items[*w]) && !self.items[*w].turret && self.items[*w].rear).collect();
        // Python: sum(...) of floats
        let mut terms = Vec::new();
        for w in &front {
            terms.push(self.weapon_bv(*w, None));
        }
        let front_bv = crate::pyfmt::py_sum(terms);
        let mut terms = Vec::new();
        for w in &rear {
            terms.push(self.weapon_bv(*w, None));
        }
        let rear_bv = crate::pyfmt::py_sum(terms);
        let switch = front_bv < rear_bv;
        let nominal_rear: HashSet<usize> = weapons.iter().copied().filter(|w| (switch ^ rear.contains(w)) && !self.is_arm(&self.items[*w]) && !self.items[*w].turret).collect();
        let mut records: Vec<(usize, f64, f64)> = weapons.iter().map(|w| (*w, self.weapon_bv(*w, Some(&nominal_rear)), self.weapon_heat(&self.items[*w]))).collect();
        records.sort_by(|a, b| {
            let (ha, hb) = (a.2, b.2);
            let o: i32 = if ha == 0.0 && hb > 0.0 {
                -1
            } else if ha > 0.0 && hb == 0.0 {
                1
            } else if ha == 0.0 && hb == 0.0 {
                0
            } else if a.1 == b.1 {
                (ha > hb) as i32 - (ha < hb) as i32
            } else {
                (b.1 > a.1) as i32 - (b.1 < a.1) as i32
            };
            o.cmp(&0)
        });
        let efficiency = self.heat_efficiency();
        if trace_level() > 0 { eprintln!("BVH\t{} {}\t{}", self.m.chassis, self.m.model, efficiency); }
        let mut exceeded = efficiency <= 0.0;
        let mut heat_sum = 0.0;
        let trace2 = trace_level() == 2;
        for (wi, bv, heat) in records {
            if trace2 { eprintln!("BVW\t{} {}\t{}\t{}\t{:.3}\t{}", self.m.chassis, self.m.model, self.items[wi].name, self.items[wi].location, bv, heat); }
            heat_sum += heat;
            let value = if exceeded { bv / 2.0 } else { bv };
            self.offensive += value;
            if heat_sum >= efficiency {
                exceeded = true;
            }
        }
    }

    fn ammunition(&mut self) {
        let mut ammo_bv: IndexMap<String, f64> = IndexMap::default();
        let mut weapon_bv: HashMap<String, f64> = HashMap::default();
        for i in &self.items {
            if i.kind.as_deref() != Some("ammo") {
                continue;
            }
            let at = i.ammo_type.as_deref();
            if matches!(at, Some("AMS") | Some("APDS") | Some("SCREEN_LAUNCHER")) || i.has("F_ONE_SHOT") {
                continue;
            }
            let key = format!("{}:{}", at.unwrap_or("None"), i.rack_size);
            *ammo_bv.entry(key).or_insert(0.0) += i.bv;
        }
        for i in &self.items {
            if i.kind.as_deref() != Some("weapon") || i.any(&["F_B_POD", "F_M_POD"]) {
                continue;
            }
            let at = i.ammo_type.as_deref();
            let energy = i.has("F_ENERGY") && !matches!(at, Some("PLASMA") | Some("VEHICLE_FLAMER") | Some("HEAVY_FLAMER") | Some("CHEMICAL_LASER"));
            if energy || i.has("F_ONE_SHOT") || i.has("F_INFANTRY") || matches!(at, None | Some("NA")) {
                continue;
            }
            let key = format!("{}:{}", at.unwrap(), i.rack_size);
            *weapon_bv.entry(key).or_insert(0.0) += i.bv;
        }
        for (key, value) in ammo_bv {
            match weapon_bv.get(&key) {
                None => {
                    if key == "COOLANT_POD:1" {
                        self.offensive += value;
                    }
                }
                Some(w) => self.offensive += value.min(*w),
            }
        }
    }

    fn misc_bv(&self, item: &Item) -> f64 {
        let weight = self.m.mass.unwrap_or(0) as f64;
        if item.has_bv {
            return item.bv;
        }
        let tsm = if self.has("F_TSM") { 2.0 } else { 1.0 };
        let f = &item.flags;
        let h = |x: &str| f.contains(x);
        if h("F_CLUB") && h("S_HATCHET") {
            return (weight / 5.0).ceil() * 1.5 * tsm;
        }
        if h("F_CLUB") && h("S_SWORD") {
            return (weight / 10.0 + 1.0).ceil() * 1.725 * tsm;
        }
        if h("F_CLUB") && h("S_LANCE") {
            return (weight / 5.0).ceil() * tsm;
        }
        if h("F_CLUB") && h("S_MACE") {
            return (weight / 4.0).ceil() * tsm;
        }
        if h("F_CLUB") && h("S_RETRACTABLE_BLADE") {
            return (weight / 10.0).ceil() * 1.725 * tsm;
        }
        if h("F_HAND_WEAPON") && h("S_CLAW") {
            return (weight / 7.0).ceil() * 1.275 * tsm;
        }
        if h("F_TALON") {
            return jround((weight / 5.0).floor() * 0.5) as f64 * tsm;
        }
        if h("F_RAM_PLATE") {
            let damage = ((weight * self.run as f64 * 0.1) as i64) / 2;
            return crate::pyfmt::py_round_n(damage as f64 * 1.1, 3);
        }
        0.0
    }

    fn offensive_equipment(&mut self) {
        const SKIP: [&str; 22] = ["F_AP_POD", "F_VIRAL_JAMMER_DECOY", "F_VIRAL_JAMMER_HOMING", "F_LIGHT_BRIDGE_LAYER", "F_MEDIUM_BRIDGE_LAYER", "F_HEAVY_BRIDGE_LAYER", "F_CHAFF_POD", "F_BULLDOZER", "F_BAP", "F_TARGETING_COMPUTER", "F_SPIKES", "F_MINESWEEPER", "F_HARJEL_II", "F_HARJEL_III", "F_MASS", "F_MINE", "F_SHIELD", "", "", "", "", ""];
        let mut add = 0.0;
        for item in &self.items {
            if item.kind.as_deref() != Some("misc") {
                continue;
            }
            if item.has("F_ECM") && !item.has("F_WATCHDOG") {
                continue;
            }
            if item.any(&SKIP[..17]) || Self::is_vibroblade(item) {
                continue;
            }
            let mut bv = self.misc_bv(item);
            if bv == 0.0 {
                continue;
            }
            if (item.has("F_CLUB") || item.has("F_HAND_WEAPON")) && self.arm_aes(&item.location) {
                bv *= 1.25;
            } else if item.has("F_WATCHDOG") {
                bv = 7.0;
            }
            add += bv;
        }
        self.offensive += add;
    }

    fn weight(&mut self) {
        let mass = self.m.mass.unwrap_or(0) as f64;
        let mut aes = 1.0;
        for loc in ARMS {
            if self.arm_aes(loc) {
                aes += 0.1;
            }
        }
        if self.items.iter().any(|i| i.has("F_ACTUATOR_ENHANCEMENT_SYSTEM") && i.slots_by_location.keys().any(|l| l.contains("Leg"))) {
            aes += if self.quad { 0.4 } else { 0.2 };
        }
        let weight = mass * aes;
        if self.items.iter().any(|i| i.has("F_TSM") && !i.has("F_INDUSTRIAL_TSM")) {
            self.offensive += weight * 1.5;
        } else if self.has("F_INDUSTRIAL_TSM") {
            self.offensive += weight * 1.15;
        } else {
            self.offensive += weight;
        }
    }

    fn speed_factor(&mut self) {
        let mp = self.run + jround(self.jump.max(self.umu) as f64 / 2.0);
        let factor = (((1.0 + (mp - 5) as f64 / 10.0).powf(1.2)) * 100.0).round_ties_even() / 100.0;
        self.offensive *= factor;
    }

    fn type_modifier(&mut self) {
        let c = up(&self.m.cockpit_type);
        if c.contains("INDUSTRIAL") && !c.contains("AFC") {
            self.offensive *= 0.9;
        }
    }

    fn run_all(&mut self) -> i64 {
        self.armor();
        self.structure();
        self.armored_components();
        self.defensive_equipment();
        self.explosive_equipment();
        self.defensive_factor();
        self.weapons();
        self.ammunition();
        self.offensive_equipment();
        self.weight();
        self.speed_factor();
        self.type_modifier();
        if trace_level() > 0 {
            eprintln!("BVTRACE\t{} {}\t{}\t{}\t{:.3}\t{:.3}", self.m.chassis, self.m.model, self.run, self.jump, self.defensive, self.offensive);
        }
        let mut base = self.defensive + self.offensive;
        let cockpit = up(&self.m.cockpit_type);
        if cockpit.contains("SMALL") || cockpit.contains("TORSO-MOUNTED") {
            base *= 0.95;
        } else if cockpit.contains("INTERFACE") {
            base *= 1.3;
        } else if self.has("F_DRONE_OPERATING_SYSTEM") {
            base *= 0.95;
        }
        let adjusted = jround(base);
        let factor = skill_factor(self.m.gunnery, self.m.piloting);
        jround(adjusted as f64 * factor)
    }
}

/// The 'Mech's Battle Value as built, with the pilot's skill factor.
pub fn battle_value(b: &Battle, u: UnitId) -> i64 {
    Calc::new(b, u).run_all()
}
