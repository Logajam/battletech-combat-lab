// Translated from mechsim/mtf_parser.py (session 22).
//! .mtf file parser: header lines, armor and structure types, and the crit-slot lists built through the equipment
//! database (multi-slot items share one Equipment). Python's `print` and `config.log` lines go to `out` (VERBOSE is on).

use std::collections::BTreeSet;

use crate::damage_resolution::is_partial_wing;
use crate::equipment::*;
use crate::mech_state::*;
use crate::pyfmt::{py_int, py_repr_str, py_strip, Num};

/// Normalized (lowercase, whitespace / hyphens stripped) armor-type text -> ArmorType.
fn armor_type_by_name(norm: &str) -> Option<ArmorType> {
    Some(match norm {
        // these read as standard armor, as before: the sim has no combat difference for them. The extra spellings ("Standard Armor",
        // "Light / Heavy Ferro-Fibrous", "Stealth Armor") were reported as unrecognised on ~460 unit files (witch hunt, 2026-11-15)
        "standard" | "standardarmor" | "ferrofibrous" | "lightferrofibrous" | "heavyferrofibrous" | "ferrofibrousprototype" | "stealth" | "stealtharmor" => ArmorType::Standard,
        "antipenetrativeablation" => ArmorType::AntiPenetrativeAblation,
        "impactresistant" => ArmorType::ImpactResistant,
        "reflective" => ArmorType::Reflective,
        "reactive" => ArmorType::Reactive,
        "hardened" => ArmorType::Hardened,
        "ferrolamellor" => ArmorType::FerroLamellor,
        "ballisticreinforced" => ArmorType::BallisticReinforced,
        "heatdissipating" => ArmorType::HeatDissipating,
        _ => return None,
    })
}

fn structure_type_by_name(norm: &str) -> Option<StructureType> {
    Some(match norm {
        "standard" | "endosteel" | "endosteelprototype" | "endocomposite" => StructureType::Standard,
        "reinforced" => StructureType::Reinforced,
        "composite" => StructureType::Composite,
        _ => return None,
    })
}

/// `re.sub(r"\([^)]*\)", "", text).strip()`, then one leading "IS " / "Clan " / "CL " removed.
pub fn strip_armor_type_tech_base(name_text: &str) -> String {
    let mut text = String::new();
    let chars: Vec<char> = name_text.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == '(' {
            if let Some(close) = chars[i + 1..].iter().position(|c| *c == ')') {
                i += 1 + close + 1;
                continue;
            }
        }
        text.push(chars[i]);
        i += 1;
    }
    let mut text = py_strip(&text).to_string();
    for prefix in ["IS ", "Clan ", "CL "] {
        if let Some(rest) = text.strip_prefix(prefix) {
            text = rest.to_string();
            break;
        }
    }
    text
}

fn normalize_type_text(name_text: &str) -> String {
    // letters and digits only: spaces, hyphens and stray brackets ("Standard((Unknown Technology Base))") make no difference
    strip_armor_type_tech_base(name_text).chars().filter(|c| c.is_alphanumeric()).collect::<String>().to_lowercase()
}

pub fn map_structure_type_name(name_text: &str) -> Option<StructureType> {
    structure_type_by_name(&normalize_type_text(name_text))
}

pub fn map_armor_type_name(name_text: &str) -> Option<ArmorType> {
    armor_type_by_name(&normalize_type_text(name_text))
}

/// (header key, location, "front"/"rear") for a mech type, in the Python dict's order.
pub fn armor_key_map(mech_type: &str) -> Vec<(&'static str, &'static str, &'static str)> {
    if mech_type == "quad" || mech_type == "quadvee" {
        vec![
            ("FLL armor", "Front Left Leg", "front"), ("FRL armor", "Front Right Leg", "front"),
            ("LT armor", "Left Torso", "front"), ("RT armor", "Right Torso", "front"),
            ("CT armor", "Center Torso", "front"), ("HD armor", "Head", "front"),
            ("RLL armor", "Rear Left Leg", "front"), ("RRL armor", "Rear Right Leg", "front"),
            ("RTL armor", "Left Torso", "rear"), ("RTR armor", "Right Torso", "rear"),
            ("RTC armor", "Center Torso", "rear"),
        ]
    } else {
        vec![
            ("LA armor", "Left Arm", "front"), ("RA armor", "Right Arm", "front"),
            ("LT armor", "Left Torso", "front"), ("RT armor", "Right Torso", "front"),
            ("CT armor", "Center Torso", "front"), ("HD armor", "Head", "front"),
            ("LL armor", "Left Leg", "front"), ("RL armor", "Right Leg", "front"),
            ("CL armor", "Center Leg", "front"),
            ("RTL armor", "Left Torso", "rear"), ("RTR armor", "Right Torso", "rear"),
            ("RTC armor", "Center Torso", "rear"),
        ]
    }
}

/// Substring match on the Config field (and the cockpit for a QuadVee).
pub fn determine_mech_type(config_str: &str, cockpit_str: &str) -> Result<&'static str, String> {
    let cfg = py_strip(config_str).to_lowercase();
    let cockpit = py_strip(cockpit_str).to_lowercase();
    if cfg.contains("quad") {
        Ok(if cockpit.contains("quadvee") { "quadvee" } else { "quad" })
    } else if cfg.contains("tripod") {
        Ok("tripod")
    } else if cfg.contains("biped") {
        Ok("biped")
    } else {
        Err(format!(
            "Config '{}' is not yet supported by this simulator (only Biped, Tripod, Quad, and QuadVee are implemented - LAM/etc. still on the backlog).",
            config_str
        ))
    }
}

/// The "LA IS:17" lines of a unit file: (location, internal structure), front keys of `armor_key_map` only.
fn structure_overrides(text: &str, mech_type: &str) -> Vec<(String, i64)> {
    let map = armor_key_map(mech_type);
    let mut out = Vec::new();
    for l in text.lines() {
        let Some((k, v)) = l.split_once(':') else { continue };
        let k = py_strip(k).to_lowercase();
        let Some(stem) = k.strip_suffix(" is") else { continue };
        let want = format!("{} armor", stem);
        if let Some((_, loc, _)) = map.iter().find(|(mk, _, side)| mk.to_lowercase() == want && *side == "front") {
            if let Ok(n) = py_strip(v).parse::<i64>() {
                out.push((loc.to_string(), n));
            }
        }
    }
    out
}

pub const KNOWN_LOCATIONS: [&str; 13] = [
    "Left Arm", "Right Arm", "Left Torso", "Right Torso", "Center Torso", "Head", "Left Leg", "Right Leg", "Center Leg",
    "Front Left Leg", "Front Right Leg", "Rear Left Leg", "Rear Right Leg",
];

/// Strip the cosmetic mounting / variant tags "(R)", "(OMNIPOD)", "(T)", "(SPLIT)", "(ARMORED)", stacked in any order,
/// matched case-insensitively; the item's own text keeps its case.
pub fn strip_cosmetic_suffixes(name: &str) -> String {
    let mut name = name.to_string();
    let mut changed = true;
    while changed {
        changed = false;
        for suffix in ["(R)", "(OMNIPOD)", "(T)", "(SPLIT)", "(ARMORED)"] {
            if name.to_uppercase().ends_with(suffix) {
                // Python cuts name[:-len(suffix)] on the ORIGINAL-case string
                let chars: Vec<char> = name.chars().collect();
                let keep: String = chars[..chars.len() - suffix.chars().count()].iter().collect();
                name = py_strip(&keep).to_string();
                changed = true;
            }
        }
    }
    name
}

/// True if a raw crit line carries the "(armored)" tag (Core p.207).
pub fn is_armored(raw_name: &str) -> bool {
    raw_name.to_uppercase().contains("(ARMORED)")
}

// CHAINSAW .. HYPERLASER added 2026-11-20 (BV check against MegaMek): the equipment table gave these 1 slot but they fill 2-7, so every line
// of one became its own item and the BV counted it that many times (the table's slot counts of the weapons that split across locations,
// like the Long Tom, were corrected instead, so that join_split_items can put their parts together)
const VARIABLE_SIZE_FRAGMENTS: [&str; 19] = ["HATCHET", "SWORD", "MACE", "LANCE", "CLAW", "RETRACTABLEBLADE", "VIBROBLADE", "SHIELD",
    "CHAINSAW", "DUALSAW", "ROCKCUTTER", "COMBINE", "BUZZSAW", "BEAGLEACTIVEPROBE", "BLOODHOUNDACTIVEPROBE",
    "NULLSIGNATURE", "VOIDSIGNATURE", "CHAMELEON", "HYPERLASER"];

fn variable_size(canonical_name: &str) -> bool {
    let n = canonical_name.replace(' ', "").replace('-', "").to_uppercase();
    VARIABLE_SIZE_FRAGMENTS.iter().any(|f| n.contains(f)) && !n.contains("BLUESHIELD")
}

/// Join each set of same-named short parts of a split item whose slots add up to the item's size into ONE instance.
fn join_split_items(mech: &mut Mech, out: &mut String) {
    let mut parts: Vec<ItemId> = Vec::new();
    let mut seen: Vec<ItemId> = Vec::new();
    for slots in mech.crits.values() {
        for s in slots {
            if let Slot::Item(id) = s {
                if !seen.contains(id) {
                    seen.push(*id);
                    let e = &mech.items[*id];
                    if e.slots_occupied < e.slots_needed.unwrap_or(e.slots_occupied) {
                        parts.push(*id);
                    }
                }
            }
        }
    }
    let mut used: Vec<ItemId> = Vec::new();
    for &a in &parts {
        if used.contains(&a) {
            continue;
        }
        let others: Vec<ItemId> = parts.iter().copied().filter(|&b| b != a && !used.contains(&b) && mech.items[b].name == mech.items[a].name).collect();
        let needed = mech.items[a].slots_needed.unwrap();
        // itertools.combinations in order, sizes 1 then 2; first combination whose slots add up
        let mut partners: Option<Vec<ItemId>> = None;
        'search: for k in [1usize, 2] {
            for combo in combinations(&others, k) {
                if mech.items[a].slots_occupied + combo.iter().map(|b| mech.items[*b].slots_occupied).sum::<i64>() == needed {
                    partners = Some(combo);
                    break 'search;
                }
            }
        }
        match partners {
            None => {
                out.push_str(&format!(
                    "WARNING: expected {} slots for {} but only found {} consecutive matching lines - treating as a {}-slot item.\n",
                    needed, mech.items[a].name, mech.items[a].slots_occupied, mech.items[a].slots_occupied
                ));
                continue;
            }
            Some(partners) => {
                used.push(a);
                for p in partners {
                    used.push(p);
                    let add = mech.items[p].slots_occupied;
                    mech.items[a].slots_occupied += add;
                    for slots in mech.crits.values_mut() {
                        for s in slots.iter_mut() {
                            if *s == Slot::Item(p) {
                                *s = Slot::Item(a);
                            }
                        }
                    }
                }
            }
        }
    }
}

/// itertools.combinations(items, k) in lexicographic order of positions.
fn combinations(items: &[ItemId], k: usize) -> Vec<Vec<ItemId>> {
    let n = items.len();
    let mut out = Vec::new();
    if k > n {
        return out;
    }
    let mut idx: Vec<usize> = (0..k).collect();
    loop {
        out.push(idx.iter().map(|&i| items[i]).collect());
        let mut i = k;
        loop {
            if i == 0 {
                return out;
            }
            i -= 1;
            if idx[i] != i + n - k {
                break;
            }
            if i == 0 {
                return out;
            }
        }
        idx[i] += 1;
        for j in i + 1..k {
            idx[j] = idx[j - 1] + 1;
        }
    }
}

thread_local! {
    /// "IS" or "CL": the unit's tech base while its slots are read, for generic weapon names ("ER Small Laser") that the table lists
    /// only with a prefix. MegaMek reads such a name in the unit's own tech base (Daniel, 2026-11-20: "the weapons should match the tech
    /// base unless noted"). Set by parse_mtf.
    static TECH_PREFIX: std::cell::Cell<&'static str> = const { std::cell::Cell::new("") };
}

/// Builds one location's crit list from its raw .mtf lines; new Equipment goes into `items`.
pub fn build_crit_list(
    db: &EquipmentDb,
    raw_lines: &[String],
    special_rules_seen: &mut BTreeSet<(String, Option<String>)>,
    superheavy: bool,
    items: &mut Vec<Equipment>,
    out: &mut String,
) -> Vec<Slot> {
    let mut result: Vec<Slot> = Vec::new();
    let mut partners: Vec<Slot> = Vec::new();
    let mut i = 0;
    let n = raw_lines.len();
    while i < n {
        let raw = &raw_lines[i];
        let name = py_strip(raw);

        if superheavy && name.contains('|') {
            let (first, second) = name.split_once('|').unwrap();
            let (first, second) = (py_strip(first).to_string(), py_strip(second).to_string());
            let a = build_crit_list(db, &[first], special_rules_seen, false, items, out).remove(0);
            let b = build_crit_list(db, &[second], special_rules_seen, false, items, out).remove(0);
            if let (Slot::Item(ai), Slot::Item(bi)) = (&a, &b) {
                items[*ai].partner = Some(*bi);
                items[*bi].partner = Some(*ai);
                items[*bi].partner_of_slot = Some(*ai);
                partners.push(b.clone());
            }
            result.push(a);
            i += 1;
            continue;
        }

        if name == "-Empty-" {
            result.push(Slot::name("-Empty-"));
            i += 1;
            continue;
        }
        let base_name = strip_cosmetic_suffixes(name);
        if ENGINE_NAMES.contains(&base_name.as_str()) {
            result.push(Slot::name("Engine"));
            i += 1;
            continue;
        }
        if base_name == "Gyro" {
            result.push(Slot::name("Gyro"));
            i += 1;
            continue;
        }
        if base_name == "Cockpit" {
            result.push(Slot::name("Cockpit"));
            i += 1;
            continue;
        }
        if base_name.to_uppercase().starts_with("MECHANICALJUMPBOOSTER:SIZE:") {
            items.push(Equipment::simple("Mechanical Jump Booster", 1, false, None, true));
            result.push(Slot::Item(items.len() - 1));
            i += 1;
            continue;
        }

        let tp = TECH_PREFIX.with(|c| c.get());
        let found = db.lookup_equipment(&base_name).or_else(|| if tp.is_empty() { None } else { db.lookup_equipment(&format!("{}{}", tp, base_name)) });
        if let Some(entry) = found {
            let mut slots_needed = entry.slots();
            if superheavy {
                slots_needed = -((-slots_needed).div_euclid(2)); // -(-slots // 2): half, rounded up
            }
            // a PROTOTYPE weapon fills more slots than the ordinary weapon its table row stands for (a prototype Gauss rifle 8, not 7):
            // the extra slots (MegaMek's sizes), so a leftover line is not taken for a second weapon
            if base_name.to_uppercase().contains("PROTOTYPE") {
                let key = entry.canonical_name().replace(' ', "").to_lowercase();
                let extra = match key.as_str() {
                    "isgaussrifle" | "isultraac5" | "islbxac10" | "clstreaksrm4" | "isarrowiv" => 1,
                    "clultraac2" | "cllbxac2" | "cllbxac5" => 2,
                    "cllbxac20" | "clultraac20" => 3,
                    "clultraac10" => 4,
                    "improvedjumpjet" => -1, // the prototype improved jump jet fills 1 slot, the ordinary improved one 2
                    _ => 0,
                };
                slots_needed += extra;
            }
            if variable_size(entry.canonical_name()) {
                slots_needed = 1;
                while i + (slots_needed as usize) < n && strip_cosmetic_suffixes(py_strip(&raw_lines[i + slots_needed as usize])) == base_name {
                    slots_needed += 1;
                }
            }
            let mut group = vec![raw_lines[i].clone()];
            let mut j = i + 1;
            while (group.len() as i64) < slots_needed && j < n {
                let next_base = strip_cosmetic_suffixes(py_strip(&raw_lines[j]));
                if next_base == base_name {
                    group.push(raw_lines[j].clone());
                    j += 1;
                } else {
                    break;
                }
            }
            let actual_slots = group.len() as i64;
            let explosion_damage = if entry.category().as_deref() == Some("ammo") && entry.flag("explosive") && entry.get("explosion_damage").map_or(true, |v| v.is_null()) {
                Some(20)
            } else {
                entry.opt_i64("explosion_damage")
            };
            let mut equip = Equipment::new(
                &base_name,
                actual_slots,
                entry.flag("explosive"),
                explosion_damage,
                entry.flag("crit_eligible"),
                entry.opt_str("damage_type"),
                entry.flag("special_rules"),
                entry.opt_str("special_rules_ref"),
                entry.category(),
                entry.range(),
                entry.opt_i64("damage_per_shot"),
                entry.opt_i64("heat"),
                entry.opt_i64("battle_value"),
                entry.tonnage(),
                entry.opt_i64("rack_size"),
            );
            equip.slots_needed = Some(slots_needed);
            equip.rear_mounted = name.to_uppercase().contains("(R)");
            equip.turret_mounted = name.to_uppercase().contains("(T)");
            if entry.flag("special_rules") {
                special_rules_seen.insert((entry.canonical_name().to_string(), entry.opt_str("special_rules_ref")));
            }
            items.push(equip);
            let id = items.len() - 1;
            for _ in 0..actual_slots {
                result.push(Slot::Item(id));
            }
            i = j;
            continue;
        }

        let lower = base_name.to_lowercase();
        if lower.starts_with("is ammo") || lower.starts_with("clan ammo") || lower.starts_with("ammo") {
            out.push_str(&format!(
                "  NOTE: ammo item '{}' not found in equipment.json - falling back to explosive/20-damage default rather than silently treating it as inert. Add it to equipment.json to get its real value.\n",
                base_name
            ));
            items.push(Equipment::simple(&base_name, 1, true, Some(20), true));
            result.push(Slot::Item(items.len() - 1));
            i += 1;
            continue;
        }
        if !ANATOMY_COMPONENTS.contains(&base_name.as_str()) && !is_structure_or_armor_slot(&base_name) {
            out.push_str(&format!(
                "  NOTE: unrecognized component '{}' - treating as a plain 1-slot component with no special effect. Add it to equipment.json if it needs real properties.\n",
                base_name
            ));
        }
        result.push(Slot::Name(base_name));
        i += 1;
    }
    result.extend(partners);
    result
}

fn partition(line: &str) -> (&str, &str, &str) {
    match line.find(':') {
        Some(p) => (&line[..p], ":", &line[p + 1..]),
        None => (line, "", ""),
    }
}

/// `str.split(None, 1)`
fn split_ws_once(value: &str) -> Vec<String> {
    let t = value.trim_start_matches(crate::pyfmt::py_is_space);
    if t.is_empty() {
        return vec![];
    }
    match t.find(crate::pyfmt::py_is_space) {
        None => vec![t.to_string()],
        Some(p) => {
            let rest = t[p..].trim_start_matches(crate::pyfmt::py_is_space);
            if rest.is_empty() {
                vec![t[..p].to_string()]
            } else {
                vec![t[..p].to_string(), rest.to_string()]
            }
        }
    }
}

/// `MechanicalJumpBooster:SIZE:([\d.]+)` (case-insensitive) searched in a line: the matched number text.
fn booster_size_text(line: &str) -> Option<String> {
    let lower = line.to_lowercase();
    let pat = "mechanicaljumpbooster:size:";
    let at = lower.find(pat)?;
    // char boundaries: `lower` and `line` can differ in byte length for odd Unicode; ASCII in practice
    let rest = &line[at + pat.len()..];
    let n = rest.chars().take_while(|c| c.is_ascii_digit() || *c == '.').count();
    if n == 0 {
        return None;
    }
    Some(rest[..n].to_string())
}

/// Python reads a text file with universal newlines; `l.rstrip("\n")` per line.
fn universal_lines(text: &str) -> Vec<String> {
    let t = text.replace("\r\n", "\n").replace('\r', "\n");
    t.split_inclusive('\n').map(|s| s.trim_end_matches('\n').to_string()).collect()
}

/// Parse a .mtf file's text into a Mech. Err = the ValueError text; `out` receives the prints and log lines.
pub fn parse_mtf(db: &EquipmentDb, text: &str, out: &mut String) -> Result<Mech, String> {
    let raw_lines = universal_lines(text);

    let mut config_str = "Biped".to_string();
    let mut cockpit_str = String::new();
    let mut gyro_str = String::new();
    for raw in &raw_lines {
        let line = py_strip(raw);
        if line.contains(':') {
            let (key, _, value) = partition(line);
            let key_lower = py_strip(key).to_lowercase();
            if key_lower == "config" {
                config_str = py_strip(value).to_string();
            } else if key_lower == "cockpit" {
                cockpit_str = py_strip(value).to_string();
            } else if key_lower == "gyro" {
                gyro_str = py_strip(value).to_string();
            }
        }
    }
    let mech_type = determine_mech_type(&config_str, &cockpit_str)?;
    let armor_keys = armor_key_map(mech_type);

    let mut global_armor_text: Option<String> = None;
    for raw in &raw_lines {
        let line = py_strip(raw);
        if line.contains(':') {
            let (key, _, value) = partition(line);
            if py_strip(key).to_lowercase() == "armor" {
                global_armor_text = Some(py_strip(value).to_string());
                break;
            }
        }
    }
    let global_armor_type: Option<ArmorType> = match &global_armor_text {
        None => {
            out.push_str("WARNING: no top-level 'armor:' line found in .mtf file - assuming Standard as the fallback type for any location armor line with no type text of its own.\n");
            Some(ArmorType::Standard)
        }
        Some(t) if py_strip(t).to_lowercase() == "patchwork" => None,
        Some(t) => match map_armor_type_name(t) {
            Some(a) => Some(a),
            None => {
                out.push_str(&format!("WARNING: unrecognized global armor type '{}' - defaulting to Standard as the fallback type for any location armor line with no type text of its own.\n", t));
                Some(ArmorType::Standard)
            }
        },
    };

    let mut structure_text: Option<String> = None;
    for raw in &raw_lines {
        let line = py_strip(raw);
        if line.contains(':') {
            let (key, _, value) = partition(line);
            if py_strip(key).to_lowercase() == "structure" {
                structure_text = Some(py_strip(value).to_string());
                break;
            }
        }
    }
    let structure_type = match &structure_text {
        None => {
            out.push_str("WARNING: no top-level 'structure:' line found in .mtf file - defaulting to Standard.\n");
            StructureType::Standard
        }
        Some(t) => match map_structure_type_name(t) {
            Some(s) => s,
            None => {
                out.push_str(&format!("WARNING: unrecognized structure type '{}' - defaulting to Standard (no combat-math difference in this sim for types like Endo Steel/Endo-Composite).\n", t));
                StructureType::Standard
            }
        },
    };

    let mut mech_jump_booster_size = 0;
    let mut found_booster_sizes: BTreeSet<i64> = BTreeSet::new();
    for raw in &raw_lines {
        if let Some(t) = booster_size_text(py_strip(raw)) {
            if let Ok(f) = t.parse::<f64>() {
                found_booster_sizes.insert(f as i64);
            }
        }
    }
    if found_booster_sizes.len() > 1 {
        let sorted: Vec<String> = found_booster_sizes.iter().map(|n| n.to_string()).collect();
        let max = *found_booster_sizes.iter().max().unwrap();
        out.push_str(&format!("WARNING: Mechanical Jump Booster SIZE values disagree across crit lines ([{}]) - using {}. Check the .mtf file for a data error.\n", sorted.join(", "), max));
        mech_jump_booster_size = max;
    } else if let Some(&v) = found_booster_sizes.iter().next() {
        mech_jump_booster_size = v;
    }

    let mut bare_names: Vec<String> = Vec::new();
    for raw in &raw_lines {
        let s = py_strip(raw);
        if s.is_empty() {
            continue;
        }
        if s.to_lowercase().starts_with("version:") {
            continue;
        }
        if !s.contains(':') {
            bare_names.push(s.to_string());
            if bare_names.len() == 2 {
                break;
            }
        } else {
            break;
        }
    }
    let mut chassis = bare_names.get(0).cloned().unwrap_or_default();
    let mut model = bare_names.get(1).cloned().unwrap_or_default();

    let mut mass: Option<i64> = None;
    let mut engine_line = String::new();
    let mut tech_base_line = String::new();
    let mut myomer_line = "Standard".to_string();
    let (mut walk_mp, mut jump_mp): (Option<i64>, Option<i64>) = (None, None);
    let mut risc_kit = false;
    let (mut heat_sink_count, mut heat_sink_type): (Option<i64>, Option<String>) = (None, None);
    let mut front_armor: crate::fasthash::IndexMap<String, i64> = crate::fasthash::IndexMap::default();
    let mut rear_armor: crate::fasthash::IndexMap<String, i64> = crate::fasthash::IndexMap::default();
    let mut location_armor_type: crate::fasthash::IndexMap<String, ArmorType> = crate::fasthash::IndexMap::default();
    let mut location_lines: crate::fasthash::IndexMap<String, Vec<String>> = crate::fasthash::IndexMap::default();

    let mut i = 0;
    let n = raw_lines.len();
    while i < n {
        let line = py_strip(&raw_lines[i]);
        if line.is_empty() || line.starts_with('#') {
            i += 1;
            continue;
        }
        if line.ends_with(':') && KNOWN_LOCATIONS.contains(&&line[..line.len() - 1]) {
            let loc_name = line[..line.len() - 1].to_string();
            let mut slots = Vec::new();
            i += 1;
            while i < n && py_strip(&raw_lines[i]) != "" {
                slots.push(py_strip(&raw_lines[i]).to_string());
                i += 1;
            }
            location_lines.insert(loc_name, slots);
            continue;
        }
        if line.contains(':') {
            let (key, _, value) = partition(line);
            let key = py_strip(key).to_lowercase();
            let value = py_strip(value);
            if key == "chassis" {
                if !value.is_empty() {
                    chassis = value.to_string();
                }
            } else if key == "model" {
                if !value.is_empty() {
                    model = value.to_string();
                }
            } else if key == "mass" {
                if let Ok(v) = py_int(value) {
                    mass = Some(v);
                }
            } else if key == "engine" {
                engine_line = value.to_string();
            } else if key == "techbase" {
                tech_base_line = value.to_string();
            } else if key == "myomer" {
                if !value.is_empty() {
                    myomer_line = value.to_string();
                }
            } else if key == "walk mp" {
                if let Ok(v) = py_int(value) {
                    walk_mp = Some(v);
                }
            } else if key == "jump mp" {
                if let Ok(v) = py_int(value) {
                    jump_mp = Some(v);
                }
            } else if key == "heat sink kit" {
                risc_kit = value.to_uppercase().contains("RISC");
            } else if key == "heat sinks" {
                let parts = split_ws_once(value);
                if !parts.is_empty() {
                    if let Ok(c) = py_int(&parts[0]) {
                        heat_sink_count = Some(c);
                        heat_sink_type = Some(if parts.len() > 1 { py_strip(&parts[1]).to_string() } else { "Single".to_string() });
                    }
                }
            } else if let Some((_, loc, side)) = armor_keys.iter().find(|(k, _, _)| k.to_lowercase() == key) {
                let (loc, side) = (loc.to_string(), *side);
                let points_text: String;
                if side == "front" {
                    let (type_text, sep, pts) = match value.rfind(':') {
                        Some(p) => (&value[..p], ":", &value[p + 1..]),
                        None => ("", "", value),
                    };
                    let armor_type;
                    if !sep.is_empty() {
                        points_text = pts.to_string();
                        armor_type = match map_armor_type_name(type_text) {
                            Some(a) => a,
                            None => {
                                out.push_str(&format!("WARNING: unrecognized armor type '{}' for {} - defaulting to Standard.\n", type_text, loc));
                                ArmorType::Standard
                            }
                        };
                    } else {
                        points_text = value.to_string();
                        armor_type = match global_armor_type {
                            None => {
                                out.push_str(&format!("WARNING: {} armor line has no type text and the mech's top-level armor line is 'Patchwork' (no fallback type available) - defaulting to Standard.\n", loc));
                                ArmorType::Standard
                            }
                            Some(a) => a,
                        };
                    }
                    location_armor_type.insert(loc.clone(), armor_type);
                } else {
                    points_text = value.to_string();
                }
                let val = py_int(&points_text).unwrap_or(0);
                if side == "front" {
                    front_armor.insert(loc, val);
                } else {
                    rear_armor.insert(loc, val);
                }
            }
        }
        i += 1;
    }

    let mass = match mass {
        Some(m) => m,
        None => {
            let keys: Vec<String> = raw_lines.iter().filter(|l| l.contains(':')).map(|l| py_repr_str(py_strip(l))).take(20).collect();
            return Err(format!("Could not find mass. Check file. First 20 keys: [{}]", keys.join(", ")));
        }
    };

    // Combat Lab's editor can set each location's internal structure by hand ("LA IS:17", one line per location, the same key
    // letters as the armor lines): lines present override the tonnage table, and with them a mass between the table's steps (up to 200 t) plays too, on the table's shape for 200 t. A file without such lines reads exactly as before.
    let overrides = structure_overrides(text, mech_type);
    let mut structure = match structure_for_tonnage(mass, mech_type) {
        Ok(s) => s,
        Err(e) if overrides.is_empty() || mass > 200 => return Err(e),      // nothing above 200 t plays (Daniel, 2026-11-15)
        Err(_) => structure_for_tonnage(200, mech_type)?,
    };
    for (loc, n) in overrides {
        structure.insert(loc, n);
    }
    let mut mech = Mech::new(mech_type);
    mech.chassis = chassis;
    mech.model = model;
    mech.mass = Some(mass);
    mech.engine_desc = Some(engine_line);
    mech.myomer = myomer_line;
    mech.cockpit_type = Some(cockpit_str);
    mech.gyro_type = Some(gyro_str);
    mech.armor_desc = Some(global_armor_text.clone().unwrap_or_default());
    mech.structure_type = structure_type;
    mech.is_industrial = Some(structure_text.clone().unwrap_or_default().to_uppercase().contains("INDUSTRIAL"));
    mech.structure_desc = Some(structure_text.clone().unwrap_or_default());
    mech.tech_base = Some(tech_base_line.clone());

    let walk_mp = match walk_mp {
        Some(w) => w,
        None => {
            out.push_str("WARNING: no 'walk mp:' line found in .mtf file - defaulting to 1 (TMM/walk-MP calculations will be degenerate for this mech).\n");
            1
        }
    };
    mech.base_walk_mp = walk_mp;
    mech.base_jump_mp = jump_mp.unwrap_or(0);
    mech.base_mechanical_jump_booster_mp = mech_jump_booster_size;

    let heat_sink_count = match heat_sink_count {
        Some(c) => c,
        None => {
            out.push_str("WARNING: no 'heat sinks:' line found (or it didn't parse) in .mtf file - defaulting to 0 (heat dissipation will be degenerate for this mech).\n");
            0
        }
    };
    mech.risc_heat_sink_kit = risc_kit;
    mech.base_heat_sinks = heat_sink_count;
    mech.heat_sink_type = match heat_sink_type {
        Some(t) if !t.is_empty() => t,
        _ => "Single".to_string(),
    };

    let loc_names: Vec<String> = mech.locations.keys().cloned().collect();
    for loc in &loc_names {
        if !front_armor.contains_key(loc) {
            out.push_str(&format!("WARNING: no armor value found for {} in .mtf file - defaulting to 0.\n", loc));
        }
        let entry = mech.locations.get_mut(loc).unwrap();
        entry.armor = Num::I(front_armor.get(loc).copied().unwrap_or(0));
        if entry.rear_armor.is_some() {
            entry.rear_armor = Some(Num::I(rear_armor.get(loc).copied().unwrap_or(0)));
        }
        entry.structure = Num::I(structure[loc.as_str()]);
        if !location_armor_type.contains_key(loc) {
            out.push_str(&format!("WARNING: no armor type found for {} in .mtf file - defaulting to Standard.\n", loc));
        }
        mech.armor_type.insert(loc.clone(), location_armor_type.get(loc).copied().unwrap_or(ArmorType::Standard));
    }

    let mut special_rules_seen: BTreeSet<(String, Option<String>)> = BTreeSet::new();
    for loc in &loc_names {
        if let Some(lines) = location_lines.get(loc) {
            TECH_PREFIX.with(|c| c.set(if tech_base_line.to_uppercase().starts_with("CLAN") || tech_base_line.to_uppercase().contains("MIXED (CLAN") { "CL" } else { "IS" }));
            let slots = build_crit_list(db, lines, &mut special_rules_seen, mass >= SUPERHEAVY_MIN_TONS, &mut mech.items, out);
            for (idx, (raw, slot)) in lines.iter().zip(slots.iter()).enumerate() {
                let is_ammo = matches!(slot, Slot::Item(id) if mech.items[*id].category.as_deref() == Some("ammo"));
                if is_armored(raw) && !is_ammo {
                    mech.armored_slots.insert((loc.clone(), idx));
                }
            }
            mech.crits.insert(loc.clone(), slots);
        } else {
            out.push_str(&format!("WARNING: no critical slot section found for {} in .mtf file.\n", loc));
        }
    }
    join_split_items(&mut mech, out);

    mech.partial_wing_active = mech.crits.values().any(|slots| slots.iter().any(|s| matches!(s, Slot::Item(id) if is_partial_wing(&mech, *id))));

    mech.max_armor = mech.locations.iter().map(|(l, v)| (l.clone(), v.armor.as_int())).collect();
    mech.max_rear_armor = mech.locations.iter().filter_map(|(l, v)| v.rear_armor.map(|r| (l.clone(), r.as_int()))).collect();
    mech.max_structure = mech.locations.iter().map(|(l, v)| (l.clone(), v.structure.as_int())).collect();
    mech.initial_sensor_slots = mech.crits.get("Head").map_or(0, |h| h.iter().filter(|s| s.is_name("Sensors")).count() as i64);
    snapshot_round_capability(&mut mech);

    if !special_rules_seen.is_empty() {
        out.push_str("\nNOTE: this unit has equipment with special rules not yet fully modeled by this sim (see FOR LATER in main.py's header docstring):\n");
        for (name, reference) in &special_rules_seen {
            out.push_str(&format!("  - {} (ref: {})\n", name, reference.as_deref().unwrap_or("None")));
        }
        out.push('\n');
    }
    Ok(mech)
}
