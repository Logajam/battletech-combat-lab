// The reflective dump of a Mech (tools/port_record.dump_unit) and its inverse. A fixture's units.json / trace lines are
// read back into Mechs with `from_json`, and `to_json` must reproduce every dump exactly (tests/mech_roundtrip.rs).
//! Equipment identity: dumps write each Equipment's first-slot address as `_addr`; ids in sets / keys are those
//! addresses. Items that no longer sit in a crit slot (destroyed) cannot be rebuilt from a dump except as placeholders
//! named in `destroyed_slot_info`; a live battle keeps its arena.

use indexmap::{IndexMap, IndexSet};
use serde_json::{json, Map, Value};

use crate::equipment::*;
use crate::mech_state::*;
use crate::pyfmt::Num;

/// `('Right Arm', 3)` -> ("Right Arm", 3)
fn parse_slot_key(k: &str) -> (String, usize) {
    let inner = k.trim_start_matches('(').trim_end_matches(')');
    let (name, idx) = inner.rsplit_once(", ").unwrap();
    (name.trim_matches('\'').trim_matches('"').to_string(), idx.parse().unwrap())
}

fn slot_key_repr(loc: &str, idx: usize) -> String {
    format!("({}, {})", crate::pyfmt::py_repr_str(loc), idx)
}

fn strs(v: &Value) -> Vec<String> {
    v.as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect()
}

pub fn armor_type_from(s: &str) -> ArmorType {
    match s {
        "ArmorType.STANDARD" => ArmorType::Standard,
        "ArmorType.REACTIVE" => ArmorType::Reactive,
        "ArmorType.REFLECTIVE" => ArmorType::Reflective,
        "ArmorType.HARDENED" => ArmorType::Hardened,
        "ArmorType.FERRO_LAMELLOR" => ArmorType::FerroLamellor,
        "ArmorType.IMPACT_RESISTANT" => ArmorType::ImpactResistant,
        "ArmorType.ANTI_PENETRATIVE_ABLATION" => ArmorType::AntiPenetrativeAblation,
        "ArmorType.BALLISTIC_REINFORCED" => ArmorType::BallisticReinforced,
        "ArmorType.HEAT_DISSIPATING" => ArmorType::HeatDissipating,
        other => panic!("armor type {}", other),
    }
}

pub fn structure_type_from(s: &str) -> StructureType {
    match s {
        "StructureType.STANDARD" => StructureType::Standard,
        "StructureType.REINFORCED" => StructureType::Reinforced,
        "StructureType.COMPOSITE" => StructureType::Composite,
        other => panic!("structure type {}", other),
    }
}

impl Mech {
    /// The address of an item: its first slot ("Right Arm#3"), computed from the crit table now.
    pub fn item_addresses(&self) -> IndexMap<ItemId, String> {
        let mut t = IndexMap::new();
        for (loc, slots) in &self.crits {
            for (i, s) in slots.iter().enumerate() {
                if let Slot::Item(id) = s {
                    t.entry(*id).or_insert_with(|| format!("{}#{}", loc, i));
                }
            }
        }
        t
    }

    /// Fix every item's `addr` (first slot) - done once when a battle starts; a destroyed item keeps its address.
    pub fn assign_addresses(&mut self) {
        let t = self.item_addresses();
        for (id, a) in t {
            if self.items[id].addr.is_none() {
                self.items[id].addr = Some(a);
            }
        }
    }

    fn addr_of(&self, id: ItemId) -> String {
        self.items[id].addr.clone().or_else(|| self.item_addresses().get(&id).cloned()).unwrap_or_else(|| format!("?{}", id))
    }

    /// Render the Equipment at `id` at dump depth `depth` (past 12 the Python cuts a cyclic chain off). Items not yet
    /// given an address (a freshly parsed mech) are addressed from the crit table.
    pub fn item_json(&self, id: ItemId, depth: i64) -> Value {
        if depth > 12 {
            return json!({"_deep": "Equipment"});
        }
        let mut it = self.items[id].clone();
        if it.addr.is_none() {
            it.addr = self.item_addresses().get(&id).cloned();
        }
        it.to_json(depth, &|p, d| self.item_json(p, d))
    }

    /// The reflective dump. `unit_name(i)` names unit i (charging / dfa are dumped as {"_unit": name}).
    pub fn to_json(&self, unit_name: &dyn Fn(usize) -> String) -> Value {
        let mut m = Map::new();
        macro_rules! put {
            ($k:expr, $v:expr) => {
                m.insert($k.into(), $v);
            };
        }
        put!("mech_type", json!(self.mech_type));
        put!("chassis", json!(self.chassis));
        put!("model", json!(self.model));
        put!("locations", Value::Object(self.locations.iter().map(|(k, v)| (k.clone(), v.to_json())).collect()));
        let mut crits = Map::new();
        for (k, slots) in &self.crits {
            let v: Vec<Value> = slots
                .iter()
                .map(|s| match s {
                    Slot::Name(n) => json!(n),
                    Slot::Item(id) => self.item_json(*id, 2),
                })
                .collect();
            crits.insert(k.clone(), Value::Array(v));
        }
        put!("crits", Value::Object(crits));
        put!("leg_locations", json!(self.leg_locations));
        put!("limb_locations", json!(self.limb_locations));
        put!("side_torso_child", json!(self.side_torso_child));
        put!("max_armor", json!(self.max_armor));
        put!("max_rear_armor", json!(self.max_rear_armor));
        put!("max_structure", json!(self.max_structure));
        put!("armor_type", Value::Object(self.armor_type.iter().map(|(k, v)| (k.clone(), json!(v.dump()))).collect()));
        put!("structure_type", json!(self.structure_type.dump()));
        put!("base_walk_mp", json!(self.base_walk_mp));
        put!("base_jump_mp", json!(self.base_jump_mp));
        put!("destroyed_leg_actuators", json!(self.destroyed_leg_actuators));
        let mut hips: Vec<&String> = self.destroyed_hip_locations.iter().collect();
        hips.sort();
        put!("destroyed_hip_locations", json!(hips));
        put!("destroyed_jump_jet_ids", sorted_addrs(self.destroyed_jump_jet_ids.iter().map(|i| self.addr_of(*i))));
        put!("base_heat_sinks", json!(self.base_heat_sinks));
        put!("heat_sink_type", json!(self.heat_sink_type));
        put!("current_heat", json!(self.current_heat));
        put!("heat_mp_penalty", json!(self.heat_mp_penalty));
        put!("heat_fire_modifier", json!(self.heat_fire_modifier));
        put!("shutdown", json!(self.shutdown));
        put!("tsm_active", json!(self.tsm_active));
        put!("deactivated_heat_sinks", json!(self.deactivated_heat_sinks));
        put!("run_mp_multiplier", json!(self.run_mp_multiplier));
        put!("myomer", json!(self.myomer));
        put!("destroyed_heat_sinks", Value::Object(self.destroyed_heat_sinks.iter().map(|(k, v)| (self.addr_of(*k), json!(v))).collect()));
        put!(
            "destroyed_slot_info",
            Value::Object(
                self.destroyed_slot_info
                    .iter()
                    .map(|((l, i), info)| {
                        (slot_key_repr(l, *i), json!({"name": info.name, "instance_id": info.instance_id.map(|id| self.addr_of(id))}))
                    })
                    .collect()
            )
        );
        put!("armored_slots", sorted_pairs(self.armored_slots.iter()));
        put!("base_mechanical_jump_booster_mp", json!(self.base_mechanical_jump_booster_mp));
        put!("mechanical_jump_booster_disabled", json!(self.mechanical_jump_booster_disabled));
        put!("partial_wing_active", json!(self.partial_wing_active));
        put!("pilot_hits", json!(self.pilot_hits));
        put!(
            "crew",
            Value::Object(
                self.crew
                    .iter()
                    .map(|(k, c)| (k.clone(), json!({"unconscious": c.unconscious, "check_pending": c.check_pending, "went_out_this_turn": c.went_out_this_turn})))
                    .collect()
            )
        );
        put!("engine_hits", json!(self.engine_hits));
        put!("gyro_hits", json!(self.gyro_hits));
        put!("cockpit_hit", json!(self.cockpit_hit));
        put!("explosions", json!(self.explosions));
        put!("destroyed", json!(self.destroyed));
        put!("cause_of_death", json!(self.cause_of_death));
        put!("crippled", json!(self.crippled));
        put!("crippled_at", json!(self.crippled_at));
        put!("prone", json!(self.prone));
        put!("preexisting_damage_snapshot", json!(self.preexisting_damage_snapshot));
        put!("pre_attack_phase_snapshot", json!(self.pre_attack_phase_snapshot));
        put!("movement_mode_this_turn", json!(self.movement_mode_this_turn));
        put!("round_capable", json!(self.round_capable));
        put!("initial_sensor_slots", json!(self.initial_sensor_slots));
        if let Some(v) = self.mass {
            put!("mass", json!(v));
        }
        for (k, v) in [("engine_desc", &self.engine_desc), ("cockpit_type", &self.cockpit_type), ("gyro_type", &self.gyro_type), ("armor_desc", &self.armor_desc)] {
            if let Some(s) = v {
                put!(k, json!(s));
            }
        }
        if let Some(b) = self.is_industrial {
            put!("is_industrial", json!(b));
        }
        for (k, v) in [("structure_desc", &self.structure_desc), ("tech_base", &self.tech_base)] {
            if let Some(s) = v {
                put!(k, json!(s));
            }
        }
        // ---- attached when a battle is set up ----
        if self.attached {
            put!("side_name", json!(self.side_name));
            put!("team", json!(self.team));
            put!("moved_this_turn", json!(self.moved_this_turn));
            put!("hex", json!(self.hex));
            put!("facing", json!(self.facing));
            put!("home_edge", json!(self.home_edge));
            put!("gunnery", json!(self.gunnery));
            put!("piloting", json!(self.piloting));
            put!("min_heat", json!(self.min_heat));
            put!("max_heat", json!(self.max_heat));
            put!("move_search", json!(self.move_search));
            put!("assumes_enemy_search", json!(self.assumes_enemy_search));
            put!("bot", json!(self.bot));
            put!("has_improved_jump_jets", json!(self.has_improved_jump_jets));
            put!("has_xxl_engine", json!(self.has_xxl_engine));
            put!("has_supercooled_myomer", json!(self.has_supercooled_myomer));
            put!(
                "equipment_systems",
                Value::Object(self.equipment_systems.iter().map(|(k, v)| (k.clone(), Value::Array(v.iter().map(|i| self.item_json(*i, 2)).collect()))).collect())
            );
            put!("has_tsm", json!(self.has_tsm));
            put!("has_stealth_armor", json!(self.has_stealth_armor));
            put!("torso_cockpit", json!(self.torso_cockpit));
            put!("escalating_turns", json!(self.escalating_turns));
            {
                // a Python set: dumped sorted
                let mut used = self.systems_used_this_turn.clone();
                used.sort();
                put!("systems_used_this_turn", json!(used));
            }
            put!("turn_number", json!(self.turn_number));
            put!("pfd_active", json!(self.pfd_active));
            put!("pfd_turns_used", json!(self.pfd_turns_used));
            put!("pfd_failed", json!(self.pfd_failed));
            put!(
                "narc_pods",
                Value::Array(self.narc_pods.iter().map(|p| json!({"effective": p.effective, "location": p.location, "owner": p.owner})).collect())
            );
            put!("ecm_suites", Value::Array(self.ecm_suites.iter().map(|i| self.item_json(*i, 1)).collect()));
            put!("unjamming", Value::Array(self.unjamming.iter().map(|i| self.item_json(*i, 1)).collect()));
            put!("capacitors", Value::Array(self.capacitors.iter().map(|i| self.item_json(*i, 1)).collect()));
            put!("capacitor_heat", json!(self.capacitor_heat));
            put!("modular_armor", Value::Array(self.modular_armor.iter().map(|i| self.item_json(*i, 1)).collect()));
            put!("tag_designated", match &self.tag_designated { Some(s) => json!(s), None => json!(false) });
            put!("move_mode", json!(self.move_mode));
            put!("move_fc", json!(self.move_fc));
            put!("mp_spent", json!(self.mp_spent));
            put!("movement_heat", json!(self.movement_heat));
            put!("charging", self.charging.map_or(Value::Null, |u| json!({"_unit": unit_name(u)})));
            put!("dfa", self.dfa.map_or(Value::Null, |u| json!({"_unit": unit_name(u)})));
            put!("deferred_end_of_move", json!(self.deferred_end_of_move));
        }
        // ---- appear during a battle ----
        if let Some(v) = &self.ams_used {
            put!("_ams_used", v.clone());
        }
        if let Some(a) = &self.arc_action {
            put!("arc_action", json!({"_type": "ArcAction", "twist": a.twist, "flip": a.flip, "turret": a.turret.as_ref().map_or(Value::Null, |t| t.to_json())}));
        }
        if let Some(v) = self.arc_action_locked {
            put!("arc_action_locked", json!(v));
        }
        if let Some(a) = &self.armor_at_turn_start {
            put!("armor_at_turn_start", Value::Object(a.iter().map(|(k, v)| (k.clone(), Value::Array(v.iter().map(|n| n.to_json()).collect()))).collect()));
        }
        if let Some(v) = self.arms_flipped {
            put!("arms_flipped", json!(v));
        }
        if let Some(v) = &self.blocked_hex {
            put!("blocked_hex", v.clone());
        }
        if let Some(s) = &self.breached_locations {
            let mut v: Vec<&String> = s.iter().collect();
            v.sort();
            put!("breached_locations", json!(v));
        }
        if let Some(v) = &self.hp_log {
            put!("hp_log", json!(v));
        }
        if let Some(v) = self.jump_only {
            put!("jump_only", json!(v));
        }
        if let Some(v) = &self.magma_entered {
            put!("magma_entered", json!(v));
        }
        if let Some(v) = &self.other_unit_hexes {
            put!("other_unit_hexes", v.clone());
        }
        if let Some(v) = self.outside_heat {
            put!("outside_heat", json!(v));
        }
        if let Some(v) = &self.shield_raised {
            put!("shield_raised", v.clone());
        }
        if let Some(v) = self.started_in_liquid {
            put!("started_in_liquid", json!(v));
        }
        if let Some(v) = self.torso_twist {
            put!("torso_twist", json!(v));
        }
        if let Some(s) = &self.weapons_fired_this_turn {
            put!("weapons_fired_this_turn", sorted_addrs(s.iter().map(|i| self.addr_of(*i))));
        }
        if let Some(v) = &self.club {
            put!("club", json!(v));
        }
        if let Some(s) = &self.breached_slot_set {
            put!("breached_slot_set", sorted_pairs(s.iter()));
        }
        if let Some(s) = &self.autocannon_crits {
            put!("autocannon_crits", sorted_addrs(s.iter().map(|i| self.addr_of(*i))));
        }
        if let Some(v) = &self.severed_limbs {
            put!("severed_limbs", json!(v));
        }
        if let Some(v) = &self.severed_seen {
            put!("severed_seen", json!(v));
        }
        if let Some(v) = self.bv_built {
            put!("_bv_built", json!(v));
        }
        if let Some(v) = self.turret_last_offset {
            put!("turret_last_offset", json!(v));
        }
        if let Some(v) = &self.taser_interference_until {
            put!("taser_interference_until", json!(v));
        }
        if let Some(v) = &self.taser_shutdown_until {
            put!("taser_shutdown_until", json!(v));
        }
        if let Some(v) = &self.tsemp_hits {
            put!("tsemp_hits", json!(v));
        }
        if let Some(v) = self.tsemp_interference_until {
            put!("tsemp_interference_until", json!(v));
        }
        if let Some(v) = &self.mech_turret_dir {
            put!("mech_turret_dir", json!(v));
        }
        if let Some(v) = &self.home_edge_row {
            put!("home_edge_row", json!(v));
        }
        if let Some(v) = &self.tsemp_shutdown_until {
            put!("tsemp_shutdown_until", json!(v));
        }
        if let Some(v) = &self.imp_until {
            put!("imp_until", json!(v));
        }
        if let Some(v) = self.imp_level {
            put!("imp_level", json!(v));
        }
        if let Some(v) = &self.imp_started {
            put!("imp_started", json!(v));
        }
        if let Some((t, c)) = &self.imp_missiles {
            put!("imp_missiles", json!([t, c]));
        }
        if let Some(v) = &self.stuck {
            put!("stuck", v.as_ref().map_or(Value::Null, |s| s.to_json()));
        }
        Value::Object(m)
    }

    /// Rebuilds a Mech from its dump. `unit_index(name)` finds a unit in the roster (charging / dfa targets).
    pub fn from_json(v: &Value, unit_index: &dyn Fn(&str) -> usize) -> Mech {
        let mut m = Mech::new(v["mech_type"].as_str().unwrap());
        m.items.clear();
        m.chassis = v["chassis"].as_str().unwrap().to_string();
        m.model = v["model"].as_str().unwrap().to_string();

        // -- the Equipment arena: every object with an `_addr` anywhere in the dump, plus placeholders --
        let mut ids: IndexMap<String, ItemId> = IndexMap::new();
        let mut dumps: IndexMap<String, &Value> = IndexMap::new();
        fn collect<'a>(v: &'a Value, ids: &mut IndexMap<String, ItemId>, dumps: &mut IndexMap<String, &'a Value>, top: bool) {
            match v {
                Value::Object(o) => {
                    if o.get("_type").and_then(|t| t.as_str()) == Some("Equipment") {
                        if let Some(a) = o.get("_addr").and_then(|a| a.as_str()) {
                            let n = ids.len();
                            ids.entry(a.to_string()).or_insert(n);
                            if top || !dumps.contains_key(a) {
                                dumps.insert(a.to_string(), v);
                            }
                        }
                    }
                    for x in o.values() {
                        collect(x, ids, dumps, false);
                    }
                }
                Value::Array(a) => {
                    for x in a {
                        collect(x, ids, dumps, false);
                    }
                }
                _ => {}
            }
        }
        for slots in v["crits"].as_object().unwrap().values() {
            for s in slots.as_array().unwrap() {
                collect(s, &mut ids, &mut dumps, true);
            }
        }
        for key in ["equipment_systems", "capacitors", "ecm_suites", "unjamming", "modular_armor"] {
            if let Some(x) = v.get(key) {
                collect(x, &mut ids, &mut dumps, false);
            }
        }
        // placeholders for addresses only named in id sets / keys
        let mut note = |a: &str, ids: &mut IndexMap<String, ItemId>| {
            let n = ids.len();
            ids.entry(a.to_string()).or_insert(n);
        };
        for k in ["destroyed_jump_jet_ids", "weapons_fired_this_turn", "autocannon_crits"] {
            if let Some(x) = v.get(k) {
                for a in x.as_array().unwrap() {
                    note(a.as_str().unwrap(), &mut ids);
                }
            }
        }
        for a in v["destroyed_heat_sinks"].as_object().unwrap().keys() {
            note(a, &mut ids);
        }
        let mut placeholder_names: IndexMap<String, String> = IndexMap::new();
        for info in v["destroyed_slot_info"].as_object().unwrap().values() {
            if let Some(a) = info["instance_id"].as_str() {
                note(a, &mut ids);
                placeholder_names.insert(a.to_string(), info["name"].as_str().unwrap().to_string());
            }
        }
        let resolve = |a: &str| -> ItemId { ids[a] };
        let mut items: Vec<Option<Equipment>> = (0..ids.len()).map(|_| None).collect();
        for (a, d) in &dumps {
            items[ids[a]] = Some(Equipment::from_json(d, &resolve));
        }
        m.items = items
            .into_iter()
            .enumerate()
            .map(|(i, e)| {
                e.unwrap_or_else(|| {
                    let a = ids.get_index(i).unwrap().0;
                    let name = placeholder_names.get(a).cloned().unwrap_or_else(|| "?".into());
                    let mut p = Equipment::simple(&name, 1, false, None, true);
                    p.addr = Some(a.clone());
                    p
                })
            })
            .collect();

        m.locations = v["locations"].as_object().unwrap().iter().map(|(k, x)| (k.clone(), Location::from_json(x))).collect();
        m.crits = v["crits"]
            .as_object()
            .unwrap()
            .iter()
            .map(|(k, slots)| {
                let sl: Vec<Slot> = slots
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|s| match s {
                        Value::String(n) => Slot::Name(n.clone()),
                        o => Slot::Item(ids[o["_addr"].as_str().unwrap()]),
                    })
                    .collect();
                (k.clone(), sl)
            })
            .collect();
        m.leg_locations = strs(&v["leg_locations"]);
        m.limb_locations = strs(&v["limb_locations"]);
        m.side_torso_child = v["side_torso_child"].as_object().unwrap().iter().map(|(k, x)| (k.clone(), x.as_str().unwrap().to_string())).collect();
        let ints = |x: &Value| -> IndexMap<String, i64> { x.as_object().unwrap().iter().map(|(k, y)| (k.clone(), y.as_i64().unwrap())).collect() };
        m.max_armor = ints(&v["max_armor"]);
        m.max_rear_armor = ints(&v["max_rear_armor"]);
        m.max_structure = ints(&v["max_structure"]);
        m.armor_type = v["armor_type"].as_object().unwrap().iter().map(|(k, x)| (k.clone(), armor_type_from(x.as_str().unwrap()))).collect();
        m.structure_type = structure_type_from(v["structure_type"].as_str().unwrap());
        m.base_walk_mp = v["base_walk_mp"].as_i64().unwrap();
        m.base_jump_mp = v["base_jump_mp"].as_i64().unwrap();
        m.destroyed_leg_actuators = ints(&v["destroyed_leg_actuators"]);
        m.destroyed_hip_locations = strs(&v["destroyed_hip_locations"]).into_iter().collect();
        m.destroyed_jump_jet_ids = strs(&v["destroyed_jump_jet_ids"]).iter().map(|a| ids[a.as_str()]).collect();
        m.base_heat_sinks = v["base_heat_sinks"].as_i64().unwrap();
        m.heat_sink_type = v["heat_sink_type"].as_str().unwrap().to_string();
        m.current_heat = v["current_heat"].as_i64().unwrap();
        m.heat_mp_penalty = v["heat_mp_penalty"].as_i64().unwrap();
        m.heat_fire_modifier = v["heat_fire_modifier"].as_i64().unwrap();
        m.shutdown = v["shutdown"].as_bool().unwrap();
        m.tsm_active = v["tsm_active"].as_bool().unwrap();
        m.deactivated_heat_sinks = v["deactivated_heat_sinks"].as_i64().unwrap();
        m.run_mp_multiplier = v["run_mp_multiplier"].as_f64().unwrap();
        m.myomer = v["myomer"].as_str().unwrap().to_string();
        m.destroyed_heat_sinks = v["destroyed_heat_sinks"].as_object().unwrap().iter().map(|(a, n)| (ids[a.as_str()], n.as_i64().unwrap())).collect();
        m.destroyed_slot_info = v["destroyed_slot_info"]
            .as_object()
            .unwrap()
            .iter()
            .map(|(k, info)| {
                (parse_slot_key(k), SlotInfo { name: info["name"].as_str().unwrap().to_string(), instance_id: info["instance_id"].as_str().map(|a| ids[a]) })
            })
            .collect();
        let pairs = |x: &Value| -> IndexSet<(String, usize)> {
            x.as_array().unwrap().iter().map(|p| (p[0].as_str().unwrap().to_string(), p[1].as_u64().unwrap() as usize)).collect()
        };
        m.armored_slots = pairs(&v["armored_slots"]);
        m.base_mechanical_jump_booster_mp = v["base_mechanical_jump_booster_mp"].as_i64().unwrap();
        m.mechanical_jump_booster_disabled = v["mechanical_jump_booster_disabled"].as_bool().unwrap();
        m.partial_wing_active = v["partial_wing_active"].as_bool().unwrap();
        m.pilot_hits = v["pilot_hits"].as_i64().unwrap();
        m.crew = v["crew"]
            .as_object()
            .unwrap()
            .iter()
            .map(|(k, c)| {
                (k.clone(), Crew { unconscious: c["unconscious"].as_bool().unwrap(), check_pending: c["check_pending"].as_bool().unwrap(), went_out_this_turn: c["went_out_this_turn"].as_bool().unwrap() })
            })
            .collect();
        m.engine_hits = v["engine_hits"].as_i64().unwrap();
        m.gyro_hits = v["gyro_hits"].as_i64().unwrap();
        m.cockpit_hit = v["cockpit_hit"].as_bool().unwrap();
        m.explosions = v["explosions"].as_i64().unwrap();
        m.destroyed = v["destroyed"].as_bool().unwrap();
        m.cause_of_death = v["cause_of_death"].as_str().map(|s| s.to_string());
        m.crippled = v["crippled"].as_bool().unwrap();
        m.crippled_at = if v["crippled_at"].is_null() { None } else { Some(v["crippled_at"].clone()) };
        m.prone = v["prone"].as_bool().unwrap();
        m.preexisting_damage_snapshot = v["preexisting_damage_snapshot"].as_object().unwrap().iter().map(|(k, x)| (k.clone(), x.clone())).collect();
        m.pre_attack_phase_snapshot = v["pre_attack_phase_snapshot"].as_object().unwrap().iter().map(|(k, x)| (k.clone(), x.clone())).collect();
        m.movement_mode_this_turn = v["movement_mode_this_turn"].as_str().unwrap().to_string();
        m.round_capable = v["round_capable"].as_object().unwrap().iter().map(|(k, x)| (k.clone(), x.as_bool().unwrap())).collect();
        m.initial_sensor_slots = v["initial_sensor_slots"].as_i64().unwrap();
        m.mass = v.get("mass").and_then(|x| x.as_i64());
        let gs = |k: &str| v.get(k).and_then(|x| x.as_str()).map(|s| s.to_string());
        m.engine_desc = gs("engine_desc");
        m.cockpit_type = gs("cockpit_type");
        m.gyro_type = gs("gyro_type");
        m.armor_desc = gs("armor_desc");
        m.is_industrial = v.get("is_industrial").and_then(|x| x.as_bool());
        m.structure_desc = gs("structure_desc");
        m.tech_base = gs("tech_base");
        if v.get("side_name").is_some() {
            m.attached = true;
            m.side_name = gs("side_name");
            m.team = gs("team");
            m.moved_this_turn = v["moved_this_turn"].as_bool().unwrap();
            m.hex = gs("hex");
            m.facing = v["facing"].as_str().unwrap().to_string();
            m.home_edge = v.get("home_edge").filter(|x| !x.is_null()).map(strs);
            m.gunnery = v["gunnery"].as_i64().unwrap();
            m.piloting = v["piloting"].as_i64().unwrap();
            m.min_heat = v["min_heat"].as_i64().unwrap();
            m.max_heat = v["max_heat"].as_i64().unwrap();
            m.move_search = gs("move_search");
            m.assumes_enemy_search = gs("assumes_enemy_search");
            m.bot = v["bot"].as_str().unwrap().to_string();
            m.has_improved_jump_jets = v["has_improved_jump_jets"].as_bool().unwrap();
            m.has_xxl_engine = v["has_xxl_engine"].as_bool().unwrap();
            m.has_supercooled_myomer = v["has_supercooled_myomer"].as_bool().unwrap();
            let refs = |x: &Value| -> Vec<ItemId> { x.as_array().unwrap().iter().map(|o| ids[o["_addr"].as_str().unwrap()]).collect() };
            m.equipment_systems = v["equipment_systems"].as_object().unwrap().iter().map(|(k, x)| (k.clone(), refs(x))).collect();
            m.has_tsm = v["has_tsm"].as_bool().unwrap();
            m.has_stealth_armor = v["has_stealth_armor"].as_bool().unwrap();
            m.torso_cockpit = v["torso_cockpit"].as_bool().unwrap();
            m.escalating_turns = ints(&v["escalating_turns"]);
            m.systems_used_this_turn = strs(&v["systems_used_this_turn"]);
            m.turn_number = v["turn_number"].as_i64().unwrap();
            m.pfd_active = v["pfd_active"].as_bool().unwrap();
            m.pfd_turns_used = v["pfd_turns_used"].as_i64().unwrap();
            m.pfd_failed = v["pfd_failed"].as_bool().unwrap();
            m.narc_pods = v["narc_pods"]
                .as_array()
                .unwrap()
                .iter()
                .map(|p| NarcPod { effective: p["effective"].as_bool().unwrap(), location: p["location"].as_str().unwrap().to_string(), owner: p["owner"].as_str().unwrap().to_string() })
                .collect();
            m.ecm_suites = refs(&v["ecm_suites"]);
            m.unjamming = refs(&v["unjamming"]);
            m.capacitors = refs(&v["capacitors"]);
            m.capacitor_heat = v["capacitor_heat"].as_i64().unwrap();
            m.modular_armor = refs(&v["modular_armor"]);
            m.tag_designated = v["tag_designated"].as_str().map(|s| s.to_string());
            m.move_mode = v["move_mode"].as_str().unwrap().to_string();
            m.move_fc = v["move_fc"].as_i64().unwrap();
            m.mp_spent = v["mp_spent"].as_i64().unwrap();
            m.movement_heat = v["movement_heat"].as_i64().unwrap();
            m.charging = v["charging"].get("_unit").map(|n| unit_index(n.as_str().unwrap()));
            m.dfa = v["dfa"].get("_unit").map(|n| unit_index(n.as_str().unwrap()));
            m.deferred_end_of_move = if v["deferred_end_of_move"].is_null() { None } else { Some(v["deferred_end_of_move"].clone()) };
        }
        m.ams_used = v.get("_ams_used").cloned();
        m.arc_action = v.get("arc_action").map(|a| ArcAction { twist: a["twist"].as_i64().unwrap(), flip: a["flip"].as_bool().unwrap(), turret: Turret::from_json(&a["turret"]) });
        m.arc_action_locked = v.get("arc_action_locked").and_then(|x| x.as_bool());
        m.armor_at_turn_start = v.get("armor_at_turn_start").map(|a| a.as_object().unwrap().iter().map(|(k, x)| (k.clone(), x.as_array().unwrap().iter().map(Num::from_json).collect())).collect());
        m.arms_flipped = v.get("arms_flipped").and_then(|x| x.as_bool());
        m.blocked_hex = v.get("blocked_hex").cloned();
        m.breached_locations = v.get("breached_locations").map(|x| strs(x).into_iter().collect());
        m.hp_log = v.get("hp_log").map(|x| x.as_array().unwrap().iter().map(|n| n.as_f64().unwrap()).collect());
        m.jump_only = v.get("jump_only").and_then(|x| x.as_bool());
        m.magma_entered = v.get("magma_entered").map(|x| x.as_array().unwrap().iter().map(|p| (p[0].as_str().unwrap().to_string(), p[1].as_str().unwrap().to_string())).collect());
        m.other_unit_hexes = v.get("other_unit_hexes").cloned();
        m.outside_heat = v.get("outside_heat").and_then(|x| x.as_i64());
        m.shield_raised = v.get("shield_raised").cloned();
        m.started_in_liquid = v.get("started_in_liquid").and_then(|x| x.as_bool());
        m.torso_twist = v.get("torso_twist").and_then(|x| x.as_i64());
        m.weapons_fired_this_turn = v.get("weapons_fired_this_turn").map(|x| strs(x).iter().map(|a| ids[a.as_str()]).collect());
        m.club = v.get("club").map(|x| x.as_str().map(|s| s.to_string()));
        m.breached_slot_set = v.get("breached_slot_set").map(&pairs);
        m.autocannon_crits = v.get("autocannon_crits").map(|x| strs(x).iter().map(|a| ids[a.as_str()]).collect());
        m.severed_limbs = v.get("severed_limbs").map(strs);
        m.severed_seen = v.get("severed_seen").map(strs);
        m.bv_built = v.get("_bv_built").and_then(|x| x.as_i64());
        m.turret_last_offset = v.get("turret_last_offset").and_then(|x| x.as_i64());
        m.taser_interference_until = v.get("taser_interference_until").map(|x| x.as_i64());
        m.taser_shutdown_until = v.get("taser_shutdown_until").map(|x| x.as_i64());
        m.tsemp_hits = v.get("tsemp_hits").map(|x| x.as_array().unwrap().iter().map(|n| n.as_i64().unwrap()).collect());
        m.tsemp_interference_until = v.get("tsemp_interference_until").map(|x| x.as_i64());
        m.mech_turret_dir = v.get("mech_turret_dir").map(ints);
        m.home_edge_row = v.get("home_edge_row").map(strs);
        m.tsemp_shutdown_until = v.get("tsemp_shutdown_until").map(|x| x.as_i64());
        m.imp_until = v.get("imp_until").map(|x| x.as_i64());
        m.imp_level = v.get("imp_level").and_then(|x| x.as_i64());
        m.imp_started = v.get("imp_started").map(|x| x.as_i64());
        m.imp_missiles = v.get("imp_missiles").map(|x| (x[0].as_i64(), x[1].as_i64().unwrap()));
        m.stuck = v.get("stuck").map(|x| if x.is_null() { None } else { Some(Stuck::from_json(x)) });
        m
    }
}

fn sorted_addrs(it: impl Iterator<Item = String>) -> Value {
    let mut v: Vec<String> = it.collect();
    v.sort_by_key(|s| serde_json::to_string(s).unwrap());
    json!(v)
}

fn sorted_pairs<'a>(it: impl Iterator<Item = &'a (String, usize)>) -> Value {
    let mut v: Vec<Value> = it.map(|(l, i)| json!([l, i])).collect();
    v.sort_by_key(|x| serde_json::to_string(x).unwrap());
    Value::Array(v)
}
