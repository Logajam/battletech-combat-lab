//! What the unit list and the unit editor ask of the engine about ONE unit file: its list entry with the Battle Value
//! (`describe_unit`), its internal structure (`unit_structure`) and the equipment it can be built from (`equipment_list`).
//! Pure functions of the unit text, shared by the desktop Lab (catalog.rs) and the browser build (engine/wasm).
use serde_json::{json, Value};

/// One unit of the list: name, tons, Battle Value (with the default pilot, 4 / 5), tech base.
pub fn describe_unit(db: &'static btsim_core::equipment::EquipmentDb, cfg: &btsim_core::config::Config, id: &str, source: &str, text: &str) -> Value {
    // header keys are written "mass:" in some files and "Mass:" in others
    let field = |key: &str| {
        text.lines().find_map(|l| (l.len() >= key.len() && l.is_char_boundary(key.len()) && l[..key.len()].eq_ignore_ascii_case(key)).then(|| l[key.len()..].trim().to_string())).unwrap_or_default()
    };
    let name = format!("{} {}", field("chassis:"), field("model:")).trim().to_string();
    let num = |key: &str| field(key).parse::<i64>().ok();
    // Mekbay-style details (CL13), read straight from the file's header and tables: no engine needed
    // every "<location> armor:N" line, front and rear alike; the key's case varies between files ("LA Armor" / "LA armor":
    // a quarter of the library writes it lower case, which summed to 0 until 2026-11-15), and the bare "armor:" header
    // (the armor type) has no location in front of it, so " armor" with the space leaves it out
    let armor: i64 = text.lines().filter_map(|l| {
        let (k, v) = l.split_once(':')?;
        k.trim_end().to_ascii_lowercase().ends_with(" armor").then(|| v.trim().parse::<i64>().ok()).flatten()
    }).sum::<i64>();
    let sinks = field("heat sinks:");
    let (sink_n, sink_kind) = sinks.split_once(' ').map(|(n, k)| (n.parse::<i64>().ok(), k.to_string())).unwrap_or((sinks.parse::<i64>().ok(), String::new()));
    // weapons: the lines after "Weapons:N" until the first blank line, each "Name, Location" (a leading "2 " style count is not used by .mtf)
    let mut weapons: std::collections::BTreeMap<String, i64> = Default::default();
    let mut lines = text.lines();
    while let Some(l) = lines.next() {
        if l.len() > 8 && l[..8].eq_ignore_ascii_case("weapons:") {
            for w in lines.by_ref().take_while(|w| !w.trim().is_empty()) {
                let n = w.split(',').next().unwrap_or("").trim();
                let n = n.trim_start_matches(|c: char| c.is_ascii_digit()).trim().trim_start_matches(|c: char| c == 'x').trim();
                if !n.is_empty() { *weapons.entry(n.to_string()).or_insert(0) += 1; }
            }
            break;
        }
    }
    let base = json!({"id": id, "name": name, "source": source, "tons": field("mass:").parse::<i64>().ok(), "tech": field("techbase:"), "era": field("era:").parse::<i64>().ok(),
        "config": field("config:"), "role": field("role:"), "rules": num("rules level:"), "book": field("source:"),
        "walk": num("walk mp:"), "jump": num("jump mp:"), "armor": armor, "sinks": sink_n, "sink_kind": sink_kind,
        "engine": field("engine:"), "armor_type": field("armor:"), "structure": field("structure:"),
        "weapons": weapons.into_iter().collect::<Vec<_>>()});
    let mut out = String::new();
    let parsed = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let mut m = btsim_core::mtf_parser::parse_mtf(db, text, &mut out)?;
        // the list's BV is the 4 / 5 pilot's (skill factor 1.00); the page scales it by the skill table for other pilots
        m.gunnery = 4;
        m.piloting = 5;
        let board = btsim_core::board_parser::Board::from_json(&json!({"width": 1, "height": 1, "hexes": {}}));
        let b = btsim_core::battle::Battle::new(cfg.clone(), board, vec![m], Box::new(btsim_core::battle::TapeDice::new(vec![])));
        Ok::<i64, String>(btsim_core::battle_value::battle_value(&b, 0))
    }));
    let mut v = base;
    // the engine's own complaints while reading the file (an armor type it does not know and so reads as standard, a line it
    // defaults...): kept on the unit so the odd files can be found across the library (the "witch hunt" for spaces, capitals, spellings)
    let warnings: Vec<&str> = out.lines().map(str::trim).filter(|l| !l.is_empty()).collect();
    if !warnings.is_empty() {
        v["warnings"] = json!(warnings);
    }
    match parsed {
        Ok(Ok(bv)) => {
            v["bv"] = json!(bv);
            v["ok"] = json!(true);
        }
        Ok(Err(e)) => {
            v["ok"] = json!(false);
            v["why"] = json!(e);
        }
        Err(_) => {
            v["ok"] = json!(false);
            v["why"] = json!("the engine could not read this unit");
        }
    }
    v
}

/// Everything a unit can be built from, for the editor's picker: the name to write in a crit slot (one the engine's
/// lookup resolves), the display name, kind (weapon / ammo / misc), tech base, crit slots, tons (None when the database has
/// none) and, for a weapon, heat, damage and Battle Value.
pub fn equipment_list(db: &btsim_core::equipment::EquipmentDb) -> Vec<Value> {
    let mut out: Vec<Value> = db.entries.values().map(|e| {
        let tech = e.opt_str("tech_base").unwrap_or_default();
        let prefix = if tech == "Clan" { "CL" } else { "IS" };
        let aliases: Vec<String> = e.get("aliases").and_then(|a| a.as_array()).map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect()).unwrap_or_default();
        // a name without spaces that starts IS / CL, as the unit files write it; else the first alias, spaces taken out
        let key = aliases.iter().find(|a| !a.contains(' ') && a.starts_with(prefix)).cloned()
            .or_else(|| aliases.iter().find(|a| !a.contains(' ')).cloned())
            .unwrap_or_else(|| e.canonical_name().replace(' ', ""));
        json!({"k": key, "n": e.canonical_name(), "cat": e.category().unwrap_or_default(), "dt": e.opt_str("damage_type"), "tech": tech, "slots": e.slots(),
               "tons": e.tonnage(), "heat": e.opt_i64("heat"), "dmg": e.opt_i64("damage_per_shot"), "bv": e.opt_i64("battle_value"),
               // every spelling the engine resolves to this item, lower case without spaces: how the page recognises a crit slot
               "al": aliases.iter().map(|a| a.to_lowercase().replace(' ', "")).collect::<Vec<_>>()})
    }).collect();
    out.sort_by(|a, b| a["n"].as_str().cmp(&b["n"].as_str()));
    out
}

/// The unit's ammunition bins and what each may be loaded with (backlog N5, the Configure unit window): [{"loc", "slot"
/// (its first slot, from 0), "name", "munition" (as the file loads it), "choices"}], only the bins with a choice. The keys
/// are what a FORCES entry's "ammo" names ("<loc>:<slot>"; setup.rs). Empty when the file does not parse.
pub fn unit_bins(db: &btsim_core::equipment::EquipmentDb, cfg: &btsim_core::config::Config, text: &str) -> Value {
    let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let m = btsim_core::mtf_parser::parse_mtf(db, text, &mut String::new()).ok()?;
        let board = btsim_core::board_parser::Board::from_json(&json!({"width": 1, "height": 1, "hexes": {}}));
        let mut b = btsim_core::battle::Battle::new(cfg.clone(), board, vec![m], Box::new(btsim_core::battle::TapeDice::new(vec![])));
        btsim_core::ammo::attach_ammo(&mut b, 0);
        let mut out = Vec::new();
        let mut seen = std::collections::HashSet::new();
        for (loc, slots) in &b.units[0].crits {
            for (i, s) in slots.iter().enumerate() {
                let btsim_core::equipment::Slot::Item(id) = s else { continue };
                if !seen.insert(*id) {
                    continue;
                }
                let choices = btsim_core::ammo::bin_choices(&b, 0, *id);
                if choices.len() > 1 {
                    let e = &b.units[0].items[*id];
                    out.push(json!({"loc": loc, "slot": i, "name": e.name, "munition": e.munition, "choices": choices}));
                }
            }
        }
        Some(out)
    }));
    json!(r.ok().flatten().unwrap_or_default())
}

/// The C3 a unit carries, for the Configure team window (N6): "master", "slave", "master+slave", "c3i", boosted marked
/// "(boosted)", or null.
pub fn unit_c3(db: &btsim_core::equipment::EquipmentDb, cfg: &btsim_core::config::Config, text: &str) -> Value {
    let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let m = btsim_core::mtf_parser::parse_mtf(db, text, &mut String::new()).ok()?;
        let names: Vec<String> = m.items.iter().map(|e| e.canonical.as_deref().unwrap_or(&e.name).to_uppercase().replace([' ', '-', '_'], "")).collect();
        let board = btsim_core::board_parser::Board::from_json(&json!({"width": 1, "height": 1, "hexes": {}}));
        let _ = (cfg, board);
        let c3i = names.iter().any(|n| n.contains("C3I") || n.contains("IMPROVEDC3"));
        let master = names.iter().any(|n| n.contains("C3MASTER") || n.contains("C3COMPUTER[MASTER]"));
        let slave = names.iter().any(|n| n.contains("C3SLAVE") || n.contains("C3BOOSTEDSYSTEMSLAVE") || n.contains("C3COMPUTER[SLAVE]"));
        let boosted = names.iter().any(|n| n.contains("C3") && n.contains("BOOSTED"));
        let kind = if c3i { "c3i" } else if master && slave { "master+slave" } else if master { "master" } else if slave { "slave" } else { return None };
        Some(json!({"kind": kind, "boosted": boosted}))
    }));
    r.ok().flatten().unwrap_or(Value::Null)
}

/// Each location's internal structure for the unit file `text`, as the engine reads it ({"Left Arm": 17, ...}); the editor
/// limits armor to twice this (a head to 9). Empty when the file does not parse.
pub fn unit_structure(db: &btsim_core::equipment::EquipmentDb, text: &str) -> Value {
    let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let mut out = String::new();
        btsim_core::mtf_parser::parse_mtf(db, text, &mut out).map(|m| m.locations.iter().map(|(l, v)| (l.clone(), json!(v.structure.as_int()))).collect::<serde_json::Map<String, Value>>())
    }));
    match r { Ok(Ok(m)) => Value::Object(m), _ => json!({}) }
}
