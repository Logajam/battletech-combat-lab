// Translated from mechsim/equipment.py (session 22) + its JSON (mechsim/equipment.json, embedded).
//! Equipment identity and the external equipment database. Python shares ONE Equipment object between the crit slots
//! of a multi-slot item; here a mech owns an arena `items: Vec<Equipment>` and slots hold `ItemId`s, so sharing,
//! copying a mech and "id()" are all plain indices (RUST_PORT trap 6).

use crate::fasthash::IndexMap;
use serde_json::{json, Map, Value};

use crate::pyfmt::py_strip;

pub type ItemId = usize;

/// "range" of a weapon row: {"short","medium","long"} and sometimes "min".
#[derive(Clone, Debug, PartialEq)]
pub struct WeaponRange {
    pub short: i64,
    pub medium: i64,
    pub long: i64,
    pub min: Option<i64>,
}

impl WeaponRange {
    pub fn to_json(&self) -> Value {
        let mut m = Map::new();
        m.insert("short".into(), json!(self.short));
        m.insert("medium".into(), json!(self.medium));
        m.insert("long".into(), json!(self.long));
        if let Some(v) = self.min {
            m.insert("min".into(), json!(v));
        }
        Value::Object(m)
    }
    fn from_json(v: &Value) -> WeaponRange {
        // key order in equipment.json: long, medium, min, short (alphabetical); the dump keeps the file's order
        WeaponRange {
            short: v["short"].as_i64().unwrap(),
            medium: v["medium"].as_i64().unwrap(),
            long: v["long"].as_i64().unwrap(),
            min: v.get("min").and_then(|m| m.as_i64()),
        }
    }
}

/// A physical piece of gear that may occupy several crit slots (equipment.Equipment). Attributes Python adds later
/// (ammo links, jams, capacitors...) are `Option`s / defaults here, filled by the module that adds them.
#[derive(Clone, Debug)]
pub struct Equipment {
    pub name: String,
    pub slots_occupied: i64,
    pub is_explosive: bool,
    pub crit_eligible: bool,
    pub damage_type: Option<String>,
    pub special_rules: bool,
    pub special_rules_ref: Option<String>,
    pub category: Option<String>,
    pub weapon_range: Option<WeaponRange>,
    pub damage_per_shot: Option<i64>,
    pub heat: Option<i64>,
    pub battle_value: Option<i64>,
    pub tonnage: Option<f64>,
    pub rack_size: Option<i64>,
    pub explosion_damage: i64,
    pub exploded: bool,
    pub rear_mounted: bool,
    pub turret_mounted: bool,
    /// set by mtf_parser.build_crit_list for database items only
    pub slots_needed: Option<i64>,
    /// superheavy slots hold two items: each points at the other; the second is `partner_of_slot` of the first
    pub partner: Option<ItemId>,
    pub partner_of_slot: Option<ItemId>,
    /// identity: the address of its first slot ("Right Arm#3"), fixed when a battle starts (tools/port_record.dump's `_addr`)
    pub addr: Option<String>,
    // ---- attributes later modules attach (None = the Python attribute does not exist) ----
    pub canonical: Option<String>,        // "_canonical"
    pub ammo_key: Option<String>,
    pub ammo_unknown: Option<bool>,
    pub needs_ammo: Option<bool>,
    pub one_shot: Option<bool>,
    pub torpedo: Option<bool>,
    pub fired_once: Option<bool>,
    pub jammed: Option<bool>,
    pub feeds: Option<String>,
    pub kind: Option<String>,
    pub missiles_per_shot: Option<i64>,
    pub munition: Option<String>,
    /// present-but-None is possible (the attribute exists, holding None)
    pub shot_damage: Option<Option<i64>>,
    pub shots_left: Option<i64>,
    /// (the Artemis IV / V item, its kind 4 or 5) - Python's `w.artemis = (slot, kind)`
    pub artemis: Option<(ItemId, i64)>,
    pub charged: Option<bool>,
    pub charging: Option<bool>,
    pub firing: Option<bool>,
    pub linked_ppc: Option<ItemId>,
    /// an MRM's linked Apollo FCS (fire_modes.attach)
    pub apollo: Option<ItemId>,
    pub base_damage: Option<i64>,
    pub base_heat: Option<i64>,
    pub capacitor: Option<ItemId>,
    pub pod_used: Option<bool>,
    pub modular_field: Option<String>,
    pub modular_location: Option<String>,
    /// modular armor (TO:AUE p.93): points of armor left in the module (set by equipment_systems)
    pub modular_points: Option<i64>,
    pub shield_dc: Option<i64>,
    pub tsemp_recharge_until: Option<Option<i64>>,
    /// a machine gun array's guns
    pub mga_guns: Option<Vec<ItemId>>,
}

impl Equipment {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        name: &str,
        slots_occupied: i64,
        is_explosive: bool,
        explosion_damage: Option<i64>,
        crit_eligible: bool,
        damage_type: Option<String>,
        special_rules: bool,
        special_rules_ref: Option<String>,
        category: Option<String>,
        weapon_range: Option<WeaponRange>,
        damage_per_shot: Option<i64>,
        heat: Option<i64>,
        battle_value: Option<i64>,
        tonnage: Option<f64>,
        rack_size: Option<i64>,
    ) -> Equipment {
        let explosion_damage = match explosion_damage {
            Some(d) => d,
            None if is_explosive => 2 * slots_occupied,
            None => 0,
        };
        Equipment {
            name: name.to_string(),
            slots_occupied,
            is_explosive,
            crit_eligible,
            damage_type,
            special_rules,
            special_rules_ref,
            category,
            weapon_range,
            damage_per_shot,
            heat,
            battle_value,
            tonnage,
            rack_size,
            explosion_damage,
            exploded: false,
            rear_mounted: false,
            turret_mounted: false,
            slots_needed: None,
            partner: None,
            partner_of_slot: None,
            addr: None,
            canonical: None,
            ammo_key: None,
            ammo_unknown: None,
            needs_ammo: None,
            one_shot: None,
            torpedo: None,
            fired_once: None,
            jammed: None,
            feeds: None,
            kind: None,
            missiles_per_shot: None,
            munition: None,
            shot_damage: None,
            shots_left: None,
            artemis: None,
            charged: None,
            charging: None,
            firing: None,
            linked_ppc: None,
            apollo: None,
            base_damage: None,
            base_heat: None,
            capacitor: None,
            pod_used: None,
            modular_field: None,
            modular_location: None,
            modular_points: None,
            shield_dc: None,
            tsemp_recharge_until: None,
            mga_guns: None,
        }
    }

    /// `Equipment(name, slots_occupied=..., is_explosive=..., explosion_damage=...)` with the other arguments default.
    pub fn simple(name: &str, slots_occupied: i64, is_explosive: bool, explosion_damage: Option<i64>, crit_eligible: bool) -> Equipment {
        Equipment::new(name, slots_occupied, is_explosive, explosion_damage, crit_eligible, None, false, None, None, None, None, None, None, None, None)
    }

    /// The reflective dump of this object as tools/port_record.dump writes it. `ref_json(id)` renders a nested
    /// Equipment (the caller supplies the depth rule: past depth 12 the Python cuts the chain off).
    pub fn to_json(&self, depth: i64, ref_json: &dyn Fn(ItemId, i64) -> Value) -> Value {
        let mut m = Map::new();
        m.insert("_type".into(), json!("Equipment"));
        if let Some(a) = &self.addr {
            m.insert("_addr".into(), json!(a));
        }
        m.insert("name".into(), json!(self.name));
        m.insert("slots_occupied".into(), json!(self.slots_occupied));
        m.insert("is_explosive".into(), json!(self.is_explosive));
        m.insert("crit_eligible".into(), json!(self.crit_eligible));
        m.insert("damage_type".into(), json!(self.damage_type));
        m.insert("special_rules".into(), json!(self.special_rules));
        m.insert("special_rules_ref".into(), json!(self.special_rules_ref));
        m.insert("category".into(), json!(self.category));
        m.insert("weapon_range".into(), self.weapon_range.as_ref().map_or(Value::Null, |r| if depth + 1 > 12 { json!({"_deep": "dict"}) } else { r.to_json() }));
        m.insert("damage_per_shot".into(), json!(self.damage_per_shot));
        m.insert("heat".into(), json!(self.heat));
        m.insert("battle_value".into(), json!(self.battle_value));
        m.insert("tonnage".into(), json!(self.tonnage));
        m.insert("rack_size".into(), json!(self.rack_size));
        m.insert("explosion_damage".into(), json!(self.explosion_damage));
        m.insert("exploded".into(), json!(self.exploded));
        m.insert("rear_mounted".into(), json!(self.rear_mounted));
        m.insert("turret_mounted".into(), json!(self.turret_mounted));
        macro_rules! opt {
            ($key:expr, $field:expr) => {
                if let Some(v) = &$field {
                    m.insert($key.into(), json!(v));
                }
            };
        }
        opt!("slots_needed", self.slots_needed);
        opt!("_canonical", self.canonical);
        opt!("ammo_key", self.ammo_key);
        opt!("ammo_unknown", self.ammo_unknown);
        opt!("needs_ammo", self.needs_ammo);
        opt!("one_shot", self.one_shot);
        opt!("torpedo", self.torpedo);
        opt!("fired_once", self.fired_once);
        opt!("jammed", self.jammed);
        opt!("feeds", self.feeds);
        opt!("kind", self.kind);
        opt!("missiles_per_shot", self.missiles_per_shot);
        opt!("munition", self.munition);
        opt!("shot_damage", self.shot_damage);
        opt!("shots_left", self.shots_left);
        if let Some((item, kind)) = &self.artemis {
            m.insert("artemis".into(), if depth + 1 > 12 { json!({"_deep": "list"}) } else { Value::Array(vec![ref_json(*item, depth + 2), json!(kind)]) });
        }
        opt!("charged", self.charged);
        opt!("charging", self.charging);
        opt!("firing", self.firing);
        if let Some(i) = self.linked_ppc {
            m.insert("linked_ppc".into(), ref_json(i, depth + 1));
        }
        opt!("base_damage", self.base_damage);
        opt!("base_heat", self.base_heat);
        if let Some(i) = self.apollo {
            m.insert("apollo".into(), ref_json(i, depth + 1));
        }
        if let Some(i) = self.capacitor {
            m.insert("capacitor".into(), ref_json(i, depth + 1));
        }
        opt!("pod_used", self.pod_used);
        opt!("modular_field", self.modular_field);
        opt!("modular_location", self.modular_location);
        opt!("modular_points", self.modular_points);
        opt!("shield_dc", self.shield_dc);
        if let Some(i) = self.partner {
            m.insert("partner".into(), ref_json(i, depth + 1));
        }
        if let Some(i) = self.partner_of_slot {
            m.insert("partner_of_slot".into(), ref_json(i, depth + 1));
        }
        opt!("tsemp_recharge_until", self.tsemp_recharge_until);
        if let Some(list) = &self.mga_guns {
            m.insert("mga_guns".into(), if depth + 1 > 12 { json!({"_deep": "list"}) } else { Value::Array(list.iter().map(|i| ref_json(*i, depth + 2)).collect()) });
        }
        Value::Object(m)
    }

    /// Reads back a dump. `resolve(addr)` maps a nested object's `_addr` to its ItemId in the arena.
    pub fn from_json(v: &Value, resolve: &dyn Fn(&str) -> ItemId) -> Equipment {
        let gs = |k: &str| v.get(k).and_then(|x| x.as_str()).map(|s| s.to_string());
        let gi = |k: &str| v.get(k).and_then(|x| x.as_i64());
        let gb = |k: &str| v.get(k).and_then(|x| x.as_bool());
        let nested = |k: &str| v.get(k).filter(|x| x.is_object()).and_then(|x| x.get("_addr")).and_then(|a| a.as_str()).map(|a| resolve(a));
        let mut e = Equipment::new(
            v["name"].as_str().unwrap(),
            v["slots_occupied"].as_i64().unwrap(),
            v["is_explosive"].as_bool().unwrap(),
            Some(v["explosion_damage"].as_i64().unwrap()),
            v["crit_eligible"].as_bool().unwrap(),
            gs("damage_type"),
            v["special_rules"].as_bool().unwrap(),
            gs("special_rules_ref"),
            gs("category"),
            v.get("weapon_range").filter(|w| w.is_object()).map(WeaponRange::from_json),
            gi("damage_per_shot"),
            gi("heat"),
            gi("battle_value"),
            v.get("tonnage").and_then(|t| t.as_f64()),
            gi("rack_size"),
        );
        e.addr = gs("_addr");
        e.exploded = v["exploded"].as_bool().unwrap();
        e.rear_mounted = v["rear_mounted"].as_bool().unwrap();
        e.turret_mounted = v["turret_mounted"].as_bool().unwrap();
        e.slots_needed = gi("slots_needed");
        e.canonical = gs("_canonical");
        e.ammo_key = gs("ammo_key");
        e.ammo_unknown = gb("ammo_unknown");
        e.needs_ammo = gb("needs_ammo");
        e.one_shot = gb("one_shot");
        e.torpedo = gb("torpedo");
        e.fired_once = gb("fired_once");
        e.jammed = gb("jammed");
        e.feeds = gs("feeds");
        e.kind = gs("kind");
        e.missiles_per_shot = gi("missiles_per_shot");
        e.munition = gs("munition");
        e.shot_damage = v.get("shot_damage").map(|x| x.as_i64());
        e.shots_left = gi("shots_left");
        e.artemis = v.get("artemis").and_then(|a| a.as_array()).filter(|a| a[0].get("_addr").is_some()).map(|a| (resolve(a[0]["_addr"].as_str().unwrap()), a[1].as_i64().unwrap()));
        e.charged = gb("charged");
        e.charging = gb("charging");
        e.firing = gb("firing");
        e.linked_ppc = nested("linked_ppc");
        e.apollo = nested("apollo");
        e.base_damage = gi("base_damage");
        e.base_heat = gi("base_heat");
        e.capacitor = nested("capacitor");
        e.pod_used = gb("pod_used");
        e.modular_field = gs("modular_field");
        e.modular_location = gs("modular_location");
        e.modular_points = gi("modular_points");
        e.shield_dc = gi("shield_dc");
        e.partner = nested("partner");
        e.partner_of_slot = nested("partner_of_slot");
        e.tsemp_recharge_until = v.get("tsemp_recharge_until").map(|x| x.as_i64());
        e.mga_guns = v.get("mga_guns").and_then(|a| a.as_array()).map(|a| a.iter().filter_map(|x| x.get("_addr").and_then(|a| a.as_str())).map(|a| resolve(a)).collect());
        e
    }
}

/// What a crit slot holds: a plain name ("-Empty-", "Engine", "Sensors", "DESTROYED"...) or an Equipment item.
#[derive(Clone, Debug, PartialEq)]
pub enum Slot {
    Name(String),
    Item(ItemId),
}

impl Slot {
    pub fn name(s: &str) -> Slot {
        Slot::Name(s.to_string())
    }
    pub fn is_name(&self, s: &str) -> bool {
        matches!(self, Slot::Name(n) if n == s)
    }
}

// ---- the database ---------------------------------------------------------------------------------------------------

const EQUIPMENT_JSON: &str = include_str!("../../../mechsim/equipment.json");

/// One row of equipment.json (kept as the JSON object; `entry.get(key)` semantics).
pub struct Entry(pub Value);

impl Entry {
    pub fn get(&self, k: &str) -> Option<&Value> {
        self.0.get(k)
    }
    pub fn slots(&self) -> i64 {
        self.0["slots"].as_i64().unwrap()
    }
    pub fn canonical_name(&self) -> &str {
        self.0["canonical_name"].as_str().unwrap()
    }
    pub fn category(&self) -> Option<String> {
        self.0.get("category").and_then(|v| v.as_str()).map(|s| s.to_string())
    }
    pub fn flag(&self, k: &str) -> bool {
        self.0[k].as_bool().unwrap()
    }
    pub fn opt_i64(&self, k: &str) -> Option<i64> {
        self.0.get(k).and_then(|v| v.as_i64())
    }
    pub fn opt_str(&self, k: &str) -> Option<String> {
        self.0.get(k).and_then(|v| v.as_str()).map(|s| s.to_string())
    }
    pub fn range(&self) -> Option<WeaponRange> {
        match self.0.get("range") {
            Some(v) if v.is_object() => Some(WeaponRange::from_json(v)),
            _ => None,
        }
    }
    pub fn tonnage(&self) -> Option<f64> {
        self.0.get("tonnage").and_then(|v| v.as_f64())
    }
}

pub struct EquipmentDb {
    pub entries: IndexMap<String, Entry>,
    pub alias_map: IndexMap<String, String>,
}

impl EquipmentDb {
    /// The one parsed copy of equipment.json (it never changes; parsing it for every battle cost about a tenth of a
    /// short duel's time).
    pub fn shared() -> &'static EquipmentDb {
        static DB: std::sync::OnceLock<EquipmentDb> = std::sync::OnceLock::new();
        DB.get_or_init(EquipmentDb::load)
    }

    pub fn load() -> EquipmentDb {
        let v: Value = serde_json::from_str(EQUIPMENT_JSON).expect("equipment.json");
        let entries = v["entries"].as_object().unwrap().iter().map(|(k, e)| (k.clone(), Entry(e.clone()))).collect();
        let alias_map = v["alias_map"].as_object().unwrap().iter().map(|(k, c)| (k.clone(), c.as_str().unwrap().to_string())).collect();
        EquipmentDb { entries, alias_map }
    }

    /// Normalize a raw .mtf equipment name (lowercase, whitespace removed), resolve through the alias map.
    pub fn lookup_equipment(&self, raw_name: &str) -> Option<&Entry> {
        let key: String = py_strip(raw_name).to_lowercase().chars().filter(|c| !crate::pyfmt::py_is_space(*c)).collect();
        let mut canon = self.alias_map.get(&key).cloned();
        if canon.is_none() && is_torpedo_name(raw_name) {
            canon = self.alias_map.get(&torpedo_part_sub(&key)).cloned();
        }
        self.entries.get(&canon?)
    }
}

/// `(?:L|S)RT(?:ORPEDO)?-?\d` at position `i` of the lowercase chars: Some(end index of the match) or None. With
/// `lookahead` the digit is not consumed (the (?=...) form).
fn torpedo_at(c: &[char], i: usize) -> Option<usize> {
    if i + 3 > c.len() {
        return None;
    }
    if !(c[i] == 'l' || c[i] == 's') || c[i + 1] != 'r' || c[i + 2] != 't' {
        return None;
    }
    let mut starts = vec![i + 3];
    let word: Vec<char> = "orpedo".chars().collect();
    if c.len() >= i + 3 + word.len() && c[i + 3..i + 3 + word.len()] == word[..] {
        starts.insert(0, i + 3 + word.len()); // greedy: try with ORPEDO first
    }
    for s in starts {
        let mut p = s;
        if p < c.len() && c[p] == '-' {
            p += 1;
        }
        if p < c.len() && c[p].is_ascii_digit() {
            return Some(p);
        }
        // `-?` may also match empty: retry without the hyphen
        if s < c.len() && c[s].is_ascii_digit() {
            return Some(s);
        }
    }
    None
}

/// True for a torpedo launcher or torpedo ammo name ("LRT 15", "CLSRT6", "IS Ammo LRTorpedo-10").
pub fn is_torpedo_name(name: &str) -> bool {
    let c: Vec<char> = name.replace(' ', "").to_lowercase().chars().collect();
    (0..c.len()).any(|i| torpedo_at(&c, i).is_some())
}

/// `_TORPEDO_PART.sub(r"\1rm", key)`: every (l|s)rt(orpedo)? followed by -?digit becomes (l|s)rm.
fn torpedo_part_sub(key: &str) -> String {
    let c: Vec<char> = key.chars().collect();
    let mut out = String::new();
    let mut i = 0;
    while i < c.len() {
        if let Some(digit_at) = torpedo_at(&c, i) {
            // the match ends where the lookahead starts: before `-?digit`; torpedo_at returned the digit index,
            // so the matched span is i..(index before an optional hyphen)
            let mut end = digit_at;
            if end > i + 3 && c[end - 1] == '-' {
                end -= 1;
            }
            out.push(c[i]);
            out.push_str("rm");
            i = end;
        } else {
            out.push(c[i]);
            i += 1;
        }
    }
    out
}

pub const ANATOMY_COMPONENTS: [&str; 13] = [
    "CASE", "CASE II", "Sensors", "Life Support", "Heat Sink", "Shoulder", "Upper Arm Actuator", "Lower Arm Actuator",
    "Hand Actuator", "Hip", "Upper Leg Actuator", "Lower Leg Actuator", "Foot Actuator",
];

pub const ENGINE_NAMES: [&str; 6] = ["Fusion Engine", "XL Engine", "Light Engine", "Compact Engine", "ICE Engine", "Engine"];

pub const PLAIN_STRING_CRIT_INELIGIBLE: [&str; 2] = ["CASE", "CASE II"];

pub const STRUCTURE_ARMOR_SLOT_WORDS: [&str; 8] =
    ["ENDOSTEEL", "ENDOCOMPOSITE", "FERROFIBROUS", "FERROLAMELLOR", "STEALTH", "REACTIVE", "REFLECTIVE", "BALLISTICREINFORCED"];

/// True for a structure / armor filler slot name.
pub fn is_structure_or_armor_slot(name: &str) -> bool {
    let norm: String = name.to_uppercase().chars().filter(|c| c.is_alphabetic()).collect();
    STRUCTURE_ARMOR_SLOT_WORDS.iter().any(|w| norm.contains(w))
}

/// Can this crit-slot entry be the RESULT of a random critical-hit roll?
pub fn is_crit_target(slot: &Slot, items: &[Equipment]) -> bool {
    match slot {
        Slot::Name(n) => {
            if n == "DESTROYED" || n == "-Empty-" || PLAIN_STRING_CRIT_INELIGIBLE.contains(&n.as_str()) {
                return false;
            }
            !is_structure_or_armor_slot(n)
        }
        Slot::Item(id) => items[*id].crit_eligible && items[*id].partner_of_slot.is_none(),
    }
}
