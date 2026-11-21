// Translated from INTEGRATION__ammo.py (session 22): ammunition bins, shots, explosion sizes.
use fancy_regex::Regex;
use serde_json::Value;
use crate::fasthash::HashSet;
use std::sync::OnceLock;

use crate::battle::{Battle, UnitId};
use crate::damage_resolution::get_weapons;
use crate::equipment::{ItemId, Slot};
use crate::fire_modes::{atm_kind, is_mml, mml_kind, mml_shots};
use crate::mech_state::Mech;
use crate::pyfmt::py_strip;
use crate::weapon_profiles::is_arrow;
use crate::weapon_rules::is_torpedo;

pub const TASER_AMMO_EXPLOSION: i64 = 6;

pub fn narc_pod_damage(name: &str) -> Option<i64> {
    match name {
        "ISNarcBeacon" | "CLNarcBeacon" => Some(2),
        "ISImprovedNarc" => Some(3),
        _ => None,
    }
}
pub fn explosive_pod_damage(name: &str) -> Option<i64> {
    match name {
        "ISNarcBeacon" | "CLNarcBeacon" => Some(4),
        "ISImprovedNarc" => Some(6),
        _ => None,
    }
}

fn rx(cell: &'static OnceLock<Regex>, pat: &str) -> &'static Regex {
    cell.get_or_init(|| Regex::new(pat).unwrap())
}

macro_rules! re {
    ($pat:expr) => {{
        static C: OnceLock<Regex> = OnceLock::new();
        rx(&C, $pat)
    }};
}

fn norm_name(name: &str) -> String {
    name.replace(' ', "").replace('-', "").to_uppercase()
}

fn strip_is(name: &str) -> String {
    name.strip_prefix("IS ").unwrap_or(name).to_string()
}

fn entry_of(b: &Battle, name: &str) -> Option<Value> {
    b.db.lookup_equipment(name).map(|e| e.0.clone())
}

fn cat_is(e: &Value, c: &str) -> bool {
    e.get("category").and_then(|v| v.as_str()) == Some(c)
}

/// equipment.json row of the weapon a bin feeds, found by name.
pub fn weapon_entry_for_ammo(b: &Battle, bin_name: &str) -> Option<Value> {
    let base = bin_name.split(" - ").next().unwrap();
    let base: Vec<&str> = base.split_whitespace().filter(|w| {
        let l = w.to_lowercase();
        l != "ammo" && l != "inferno"
    }).collect();
    let entry = entry_of(b, &base.join(" "))?;
    if cat_is(&entry, "weapon") { Some(entry) } else { None }
}

fn improved_row(kind: &str, n: &str) -> String {
    match kind {
        "GAUSS" => "Improved Gauss Rifle".to_string(),
        "AC" => format!("Improved Autocannon/{}", n),
        "SRM" => format!("Improved SRM {}", n),
        _ => format!("Improved LRM {}", n),
    }
}

/// (weapon entry the bin feeds, munition, kind), or None for (None, None, None).
pub fn parse_bin(b: &Battle, bin_name: &str) -> Option<(Value, String, String)> {
    if re!(r"(?i)ArrowIV ?(Cluster|Inferno|Smoke|Thunder)|ECM Pods|Haywire|Nemesis").is_match(bin_name).unwrap() {
        return None;
    }
    let mut name = bin_name.to_string();
    let mut munition = "standard".to_string();
    let mut kind = String::new();
    let suffixes: [(&Regex, &str); 5] = [
        (re!(r"(?i)\s*Artemis V-capable"), "artemis5"),
        (re!(r"(?i)\s*Artemis-capable"), "artemis4"),
        (re!(r"(?i)\s*Narc-capable"), "narc"),
        (re!(r"(?i)\s*Homing(?=\s*Ammo|\s*$)"), "homing"),
        (re!(r"(?i)\s*\(?Inferno\)?"), "inferno"),
    ];
    for (pattern, guidance) in suffixes {
        if pattern.is_match(&name).unwrap() {
            name = pattern.replace_all(&name, "").to_string();
            munition = guidance.to_string();
            break;
        }
    }
    let name_c = py_strip(&name.replace("(Clan)", "")).to_string();
    name = name_c;
    let u = norm_name(&name);
    if u.contains("NARC") && (u.contains("POD") || u.ends_with("NARC")) {
        let weapon = if u.contains("INARC") { "ISImprovedNarc" } else if u.starts_with("CL") { "CLNarcBeacon" } else { "ISNarcBeacon" };
        let m = if u.contains("EXPLOSIVE") { "explosive" } else { "homing" };
        return entry_of(b, weapon).map(|e| (e, m.to_string(), String::new()));
    }
    if let Some(c) = re!(r"(AMMO)?(SC|ARMORPIERCING)?MORTAR(AMMO)?(\d)").captures(&u).unwrap() {
        if c.get(2).is_none() {
            return None;
        }
        let tech = if u.starts_with("CL") || u.starts_with("CLAN") { "Clan" } else { "IS" };
        return entry_of(b, &format!("{} Mech Mortar-{}", tech, &c[4])).map(|e| (e, munition, String::new()));
    }
    if let Some(c) = re!(r"^(?:CL|CLAN)IMP(?:ROVED)?(?:AMMO)?(GAUSS|AC|SRM|LRM)(\d*)(?:AMMO)?$").captures(&norm_name(&name)).unwrap() {
        return entry_of(b, &improved_row(&c[1], &c[2])).map(|e| (e, munition, String::new()));
    }
    if let Some(c) = re!(r"(?i)MML-?(\d)\s*(LRM|SRM)").captures(&name).unwrap() {
        let k = c[2].to_lowercase();
        return entry_of(b, &format!("ISMML{}", &c[1])).map(|e| (e, munition, k));
    }
    if let Some(c) = re!(r"(?i)(ATM-?\d+)\s+(ER|HE|IMP|IIW)\b").captures(&name).unwrap() {
        kind = c[2].to_lowercase();
        let first = c[1].to_string();
        let _ = first;
        name = re!(r"(?i)(ATM-?\d+)\s+(ER|HE|IMP|IIW)\b").replace_all(&name, "$1").to_string();
    }
    let own = entry_of(b, bin_name).or_else(|| entry_of(b, &name));
    let own = own.filter(|o| cat_is(o, "ammo"));
    if re!(r"(?i)\s*Cluster|\sCL(?= Ammo)").is_match(&name).unwrap()
        || own.as_ref().is_some_and(|o| o["canonical_name"].as_str().unwrap().to_uppercase().contains("CLUSTER"))
    {
        kind = "cluster".to_string();
    }
    let mut candidates = vec![name.clone()];
    if let Some(o) = &own {
        candidates.push(o["canonical_name"].as_str().unwrap().to_string());
        if let Some(al) = o.get("aliases").and_then(|a| a.as_array()) {
            candidates.extend(al.iter().map(|a| a.as_str().unwrap().to_string()));
        }
    }
    for candidate in candidates {
        let mut candidate = candidate;
        if kind == "cluster" {
            candidate = re!(r"(?i)\s*Cluster|\sCL(?= Ammo)").replace_all(&candidate, "").to_string();
        }
        candidate = py_strip(&re!(r"\((\d+|1/2 ton)\)").replace_all(&candidate, "")).to_string();
        let alts = [candidate.clone(), strip_is(&candidate), re!(r"Ammo$").replace_all(&candidate, "").to_string()];
        for c in alts {
            if let Some(entry) = weapon_entry_for_ammo(b, &c) {
                if own.as_ref().map_or(true, |o| entry.get("tech_base") == o.get("tech_base")) {
                    return Some((entry, munition, kind));
                }
            }
        }
    }
    None
}

/// Damage Value of one shot (p.107): missiles x damage each, else damage.
pub fn damage_per_shot(entry: &Value) -> Option<i64> {
    let d = entry.get("damage_per_shot").and_then(|v| v.as_i64())?;
    let rack = entry.get("rack_size").and_then(|v| v.as_i64()).unwrap_or(0);
    if entry.get("damage_type").and_then(|v| v.as_str()) == Some("Missile") && rack != 0 { Some(d * rack) } else { Some(d) }
}

pub fn is_one_shot(b: &Battle, name: &str) -> bool {
    let entry = entry_of(b, name);
    re!(r"\(I?-?OS\)|OS$|^CLI?OS").is_match(name).unwrap()
        || entry.is_some_and(|e| e.get("shots_per_ton").and_then(|v| v.as_str()) == Some("OS"))
}

/// Once per battle (fresh clone): link bins to weapons and fill them.
pub fn attach_ammo(b: &mut Battle, u: UnitId) {
    let mut seen: HashSet<ItemId> = HashSet::default();
    let slots: Vec<ItemId> = b.units[u].crits.values().flat_map(|v| v.iter()).filter_map(|s| if let Slot::Item(i) = s { Some(*i) } else { None }).collect();
    for id in slots {
        if !seen.insert(id) {
            continue; // Python walks every slot of the item: the second pass finds hasattr("feeds") true
        }
        if b.units[u].items[id].category.as_deref() != Some("ammo") || b.units[u].items[id].torpedo.is_some() {
            continue;
        }
        let name = b.units[u].items[id].name.clone();
        let parsed = parse_bin(b, &name);
        let entry = parsed.as_ref().map(|p| &p.0);
        let munition: Option<String> = parsed.as_ref().map(|p| p.1.clone());
        let kind: Option<String> = parsed.as_ref().map(|p| p.2.clone());
        let feeds = entry.map(|e| e["canonical_name"].as_str().unwrap().to_string());
        let torpedo = is_torpedo(&b.units[u], id);
        let rack = entry.and_then(|e| e.get("rack_size").and_then(|v| v.as_i64()));
        let kind_s = kind.clone().unwrap_or_default();
        let mut shots = entry.and_then(|e| e.get("shots_per_ton").and_then(|v| v.as_i64()));
        if mml_kind(&kind_s).is_some() && entry.is_some() {
            shots = mml_shots(rack, &kind_s);
        }
        let mut shots_left = shots;
        if let Some(c) = re!(r"\((\d+)\)\s*$").captures(&name).unwrap() {
            if entry.is_some() {
                shots_left = Some(c[1].parse().unwrap());
            }
        } else if re!(r" - Half\s*$").is_match(&name).unwrap() && shots_left.is_some() {
            shots_left = shots_left.map(|s| s.div_euclid(2));
        }
        let is_missile = entry.is_some_and(|e| e.get("damage_type").and_then(|v| v.as_str()) == Some("Missile"));
        let mut missiles_per_shot = if is_missile { rack.filter(|r| *r != 0).unwrap_or(1) } else { 1 };
        let mut shot_damage = entry.and_then(damage_per_shot);
        if entry.is_some_and(|e| norm_name(e["canonical_name"].as_str().unwrap()).contains("TASER")) {
            shot_damage = Some(TASER_AMMO_EXPLOSION);
        }
        if let Some(e) = entry {
            if let Some((per, ..)) = mml_kind(&kind_s) {
                shot_damage = Some(per * rack.filter(|r| *r != 0).unwrap_or(1));
            } else if let Some((per, _)) = atm_kind(&kind_s) {
                shot_damage = Some(per * rack.filter(|r| *r != 0).unwrap_or(1));
            }
            let _ = e;
        }
        let m = munition.clone().unwrap_or_default();
        if (m == "homing" || m == "explosive") && feeds.as_deref().is_some_and(|f| narc_pod_damage(f).is_some()) {
            let f = feeds.as_deref().unwrap();
            missiles_per_shot = 1;
            shot_damage = if m == "explosive" { explosive_pod_damage(f) } else { narc_pod_damage(f) };
        }
        let it = &mut b.units[u].items[id];
        it.feeds = feeds;
        it.munition = munition;
        it.kind = kind;
        it.torpedo = Some(torpedo);
        it.shots_left = shots_left;
        it.missiles_per_shot = Some(missiles_per_shot);
        it.shot_damage = Some(shot_damage);
        update_explosion(&mut b.units[u].items[id]);
    }
    for w in get_weapons(&b.units[u]) {
        let name = b.units[u].items[w].name.clone();
        let entry = entry_of(b, &name);
        let key = entry.as_ref().map(|e| e["canonical_name"].as_str().unwrap().to_string());
        let torpedo = is_torpedo(&b.units[u], w);
        let one_shot = is_one_shot(b, &name);
        let shots = entry.as_ref().and_then(|e| e.get("shots_per_ton").cloned());
        let shots_is_int = shots.as_ref().is_some_and(|v| v.is_i64() || v.is_u64());
        let mml = is_mml(b, u, w);
        let needs_ammo = !one_shot && (shots_is_int || mml);
        let dt = b.units[u].items[w].damage_type.clone();
        let dps = b.units[u].items[w].damage_per_shot.unwrap_or(0);
        let arrow = is_arrow(b, u, w);
        let unknown = !one_shot
            && (shots.is_none() || shots.as_ref().is_some_and(|v| v.is_null()))
            && ((matches!(dt.as_deref(), Some("Ballistic") | Some("Missile")) && dps > 0) || arrow);
        let it = &mut b.units[u].items[w];
        it.ammo_key = key;
        it.torpedo = Some(torpedo);
        it.one_shot = Some(one_shot);
        it.fired_once = Some(false);
        it.needs_ammo = Some(needs_ammo);
        it.ammo_unknown = Some(unknown);
    }
}

/// Explosion BASE damage = shots left x damage per shot (p.95); an empty bin isn't explosive (p.180).
pub fn update_explosion(bin: &mut crate::equipment::Equipment) {
    let Some(left) = bin.shots_left else { return };
    if left <= 0 {
        bin.is_explosive = false;
        bin.explosion_damage = 0;
    } else if let Some(Some(sd)) = bin.shot_damage {
        bin.explosion_damage = left * sd;
    }
}

fn dead_ids(mech: &Mech) -> HashSet<ItemId> {
    mech.destroyed_slot_info.values().filter_map(|i| i.instance_id).collect()
}

/// Live bins holding this weapon's ammo, with shots left (unique).
pub fn bins_for(mech: &Mech, weapon: ItemId) -> Vec<ItemId> {
    let dead = dead_ids(mech);
    let w = &mech.items[weapon];
    let mut seen: HashSet<ItemId> = HashSet::default();
    let mut out = Vec::new();
    for slots in mech.crits.values() {
        for s in slots {
            let Slot::Item(id) = s else { continue };
            let it = &mech.items[*id];
            if it.category.as_deref() == Some("ammo")
                && !seen.contains(id)
                && !dead.contains(id)
                && !it.exploded
                && it.feeds.is_some()
                && it.feeds == w.ammo_key
                && it.torpedo.unwrap_or(false) == w.torpedo.unwrap_or(false)
                && it.shots_left.map_or(true, |n| n > 0)
            {
                seen.insert(*id);
                out.push(*id);
            }
        }
    }
    out
}

/// Weapons that can't fire for lack of ammo, as ItemIds (Python: a frozenset of id()).
pub fn unavailable_weapons(mech: &Mech) -> HashSet<ItemId> {
    let mut out = HashSet::default();
    let mut by_key: crate::fasthash::IndexMap<Option<String>, Vec<ItemId>> = crate::fasthash::IndexMap::default();
    for w in get_weapons(mech) {
        let it = &mech.items[w];
        if matches!(it.tsemp_recharge_until, Some(Some(_))) {
            out.insert(w);
        } else if it.one_shot.unwrap_or(false) {
            if it.fired_once.unwrap_or(false) {
                out.insert(w);
            }
        } else if it.needs_ammo.unwrap_or(false) {
            by_key.entry(it.ammo_key.clone()).or_default().push(w);
        }
    }
    for (_, ws) in by_key {
        let bins = bins_for(mech, ws[0]);
        let shots = if bins.iter().any(|b| mech.items[*b].shots_left.is_none()) {
            f64::INFINITY
        } else {
            bins.iter().map(|b| mech.items[*b].shots_left.unwrap()).sum::<i64>() as f64
        };
        let k = shots.min(ws.len() as f64) as usize;
        for w in &ws[k..] {
            out.insert(*w);
        }
    }
    out
}

/// Where a bin sits: the location whose critical slots hold it.
pub fn bin_location(mech: &Mech, bin: ItemId) -> Option<String> {
    mech.crits.iter().find(|(_, slots)| slots.iter().any(|s| matches!(s, Slot::Item(id) if *id == bin))).map(|(loc, _)| loc.clone())
}

/// The automatic bin order for a person's unit (Daniel, 2026-11-21): Center Torso, side torsos, arms, legs, head; inside a
/// location the bin with the fewest shots left, the first of equals.
pub fn auto_bin(mech: &Mech, bins: &[ItemId]) -> ItemId {
    let rank = |i: ItemId| match bin_location(mech, i).as_deref() {
        Some("Center Torso") => 0,
        Some("Left Torso") | Some("Right Torso") => 1,
        Some(l) if l.ends_with("Arm") => 2,
        Some(l) if l.ends_with("Leg") => 3,
        Some("Head") => 4,
        _ => 5,
    };
    let key = |i: ItemId| (rank(i), mech.items[i].shots_left.unwrap_or(i64::MAX));
    let mut best = bins[0];
    for &i in &bins[1..] {
        if key(i) < key(best) {
            best = i;
        }
    }
    best
}

/// spend() that also returns the munition actually fired: (note, munition).
pub fn take(b: &mut Battle, u: UnitId, weapon: ItemId, munition: Option<&str>, kind: Option<&str>) -> (String, String) {
    if b.units[u].items[weapon].one_shot.unwrap_or(false) {
        b.units[u].items[weapon].fired_once = Some(true);
        return ("one-shot: now spent".into(), "standard".into());
    }
    if b.units[u].items[weapon].ammo_unknown.unwrap_or(false) {
        let side = b.units[u].side_name.clone().unwrap_or_default();
        let wname = b.units[u].items[weapon].name.clone();
        crate::stubs::stub_ammo_data(b, &side, &wname);
        return (String::new(), "standard".into());
    }
    if !b.units[u].items[weapon].needs_ammo.unwrap_or(false) {
        return (String::new(), "standard".into());
    }
    let mut bins = bins_for(&b.units[u], weapon);
    if let Some(k) = kind {
        bins.retain(|i| b.units[u].items[*i].kind.as_deref().unwrap_or("") == k);
    }
    if bins.is_empty() {
        return ("no ammo".into(), munition.unwrap_or("standard").to_string());
    }
    let mun_of = |b: &Battle, i: ItemId| b.units[u].items[i].munition.clone().unwrap_or_else(|| "standard".into());
    let preferred: Vec<ItemId> = bins.iter().copied().filter(|i| Some(mun_of(b, *i).as_str()) == munition).collect();
    if !preferred.is_empty() {
        bins = preferred;
    }
    let counted: Vec<ItemId> = bins.iter().copied().filter(|i| b.units[u].items[*i].shots_left.is_some()).collect();
    if counted.is_empty() {
        return (String::new(), mun_of(b, bins[0]));
    }
    let pname = b.units[u].side_name.clone().unwrap_or_default();
    let mut best = counted[0];
    if b.player.is_player(&pname) {
        // a unit a person controls: the bin the person picked, else the automatic order (Daniel, 2026-11-21)
        let forced = b.player.unit(&pname).and_then(|c| c.bin.get(&weapon)).copied().filter(|i| counted.contains(i));
        best = forced.unwrap_or_else(|| auto_bin(&b.units[u], &counted));
    } else {
        for &i in &counted[1..] {
            if b.units[u].items[i].shots_left < b.units[u].items[best].shots_left {
                best = i; // min(): the first of equals
            }
        }
    }
    let it = &mut b.units[u].items[best];
    it.shots_left = it.shots_left.map(|n| n - 1);
    update_explosion(it);
    let note = format!("{}: {} shots left", it.name, it.shots_left.unwrap());
    (note, mun_of(b, best))
}

pub fn spend(b: &mut Battle, u: UnitId, weapon: ItemId, munition: Option<&str>, kind: Option<&str>) -> String {
    take(b, u, weapon, munition, kind).0
}

/// 2 heat per missile left in an exploding inferno bin, max 30 (p.192).
pub fn inferno_heat(bin: &crate::equipment::Equipment) -> i64 {
    match bin.shots_left {
        None => 30,
        Some(n) => 30.min(2 * n * bin.missiles_per_shot.unwrap_or(1)),
    }
}

/// NARC HOMING AMMO FOR THE FORCE (Daniel's rule, 2026-11-20; setting NARC_HOMING_FOR_FORCE, Rust engine only): "if a team has Narc or
/// iNarc with homing beacon ammo on its side, all standard LRM and SRM ammo in their force is replaced with Narc homing ammo. Ammo
/// choice can be changed later." Narc-capable missiles get the beacon's bonus (Core pp.188, 193; `electronics::guidance`). Only bins of
/// standard ammunition for a standard LRM or SRM launcher (Inner Sphere or Clan; not Streak, Extended, Enhanced, Improved, MML, ATM,
/// Artemis or inferno) change; their shots and explosion stay the same. A setting absent from a scenario (the Python's units and
/// every reference battle) is off: the rules-as-written bins, as the unit file says. Runs once, when the battle starts. Returns the
/// number of bins changed.
pub fn narc_homing_for_force(b: &mut Battle) -> usize {
    if !(b.cfg.has("NARC_HOMING_FOR_FORCE") && b.cfg.b("NARC_HOMING_FOR_FORCE")) {
        return 0;
    }
    let side = |m: &Mech| m.team.clone().or_else(|| m.side_name.clone()).unwrap_or_default();
    let is_homing_bin = |e: &crate::equipment::Equipment| {
        e.category.as_deref() == Some("ammo") && e.munition.as_deref() == Some("homing") && e.feeds.as_deref().is_some_and(|f| narc_pod_damage(f).is_some())
    };
    let teams: HashSet<String> = b.units.iter().filter(|m| m.items.iter().any(|e| is_homing_bin(e))).map(|m| side(m)).collect();
    let standard = re!(r"^(CL)?(LRM|SRM) ?\d+$");
    let mut changed = 0;
    for u in 0..b.units.len() {
        if !teams.contains(&side(&b.units[u])) {
            continue;
        }
        let name = b.units[u].side_name.clone().unwrap_or_default();
        let mut loaded: Vec<String> = Vec::new();
        for e in b.units[u].items.iter_mut() {
            let launcher = e.feeds.as_deref().is_some_and(|f| standard.is_match(f).unwrap());
            if e.category.as_deref() == Some("ammo") && e.munition.as_deref() == Some("standard") && launcher && !e.munition_chosen.unwrap_or(false) {
                e.munition = Some("narc".to_string());
                loaded.push(e.name.clone());
            }
        }
        changed += loaded.len();
        for bin in loaded {
            b.log.log(format!("  {}: {} loaded with Narc homing missiles (the force carries homing beacons)", name, bin));
        }
    }
    changed
}

/// The ammunition a bin may be loaded with in a unit's setup (backlog N5, "Ammo choice can be changed later"): always the
/// standard round; for a standard LRM / SRM launcher (the Narc force rule's list) Narc-capable missiles (Core p.193); for an
/// SRM launcher inferno rounds (p.192); for an Arrow IV homing rounds (p.193, with TAG). More kinds come with N10 (special
/// munitions). The bin's own kind (an Artemis-capable bin, a Narc pod, MML / ATM rounds...) stays as the unit file says.
pub fn bin_choices(b: &Battle, u: UnitId, id: ItemId) -> Vec<&'static str> {
    let e = &b.units[u].items[id];
    if e.category.as_deref() != Some("ammo") {
        return Vec::new();
    }
    let Some(feeds) = e.feeds.as_deref() else { return Vec::new() };
    let base = e.munition.as_deref().unwrap_or("standard");
    if !matches!(base, "standard" | "narc" | "inferno" | "homing" | "ap" | "precision" | "caseless" | "semiguided") || e.kind.as_deref().is_some_and(|k| !k.is_empty()) {
        return Vec::new();
    }
    if narc_pod_damage(feeds).is_some() {
        return Vec::new();
    }
    if re!(r"^(CL)?LRM ?\d+$").is_match(feeds).unwrap() {
        // semi-guided LRMs are Inner Sphere (Core p.193)
        return if feeds.starts_with("CL") { vec!["standard", "narc"] } else { vec!["standard", "narc", "semiguided"] };
    }
    if re!(r"^(CL)?SRM ?\d+$").is_match(feeds).unwrap() {
        return vec!["standard", "narc", "inferno"];
    }
    if re!(r"(?i)ARROWIV").is_match(feeds).unwrap() {
        return vec!["standard", "homing"];
    }
    // AUTOCANNON MUNITIONS (Core pp.191-192; backlog N10): armor-piercing and precision for a standard or light AC, caseless for
    // those and the rotary AC (flak and cluster only matter against airborne units / are the LB-X's own)
    if re!(r"^(Autocannon|Light Auto Cannon)/\d+$").is_match(feeds).unwrap() {
        return vec!["standard", "ap", "precision", "caseless"];
    }
    if re!(r"RotaryAC\d+$").is_match(feeds).unwrap() {
        return vec!["standard", "caseless"];
    }
    Vec::new()
}

/// Core p.190 "Ammunition Multiplier": the shots a ton of this munition holds, as a share of standard rounds.
pub fn munition_multiplier(munition: &str) -> f64 {
    match munition {
        "ap" => 0.8,
        "precision" => 0.6,
        "caseless" => 2.0,
        _ => 1.0,
    }
}

/// A unit's setup chose this bin's ammunition (FORCES "ammo"): the bin at `location`, `slot` (any slot of it) is loaded
/// with `munition` if `bin_choices` allows it; anything else is a log line, not a silent default.
pub fn choose_bin_munition(b: &mut Battle, u: UnitId, location: &str, slot: usize, munition: &str) {
    let name = b.units[u].side_name.clone().unwrap_or_default();
    let id = match b.units[u].crits.get(location).and_then(|v| v.get(slot)) {
        Some(Slot::Item(id)) => *id,
        _ => {
            b.log(format!("  {}: ammunition choice for {} slot {} ignored - no bin there.", name, location, slot + 1));
            return;
        }
    };
    if !bin_choices(b, u, id).contains(&munition) {
        let bin = b.units[u].items[id].name.clone();
        b.log(format!("  {}: ammunition choice '{}' for {} ignored - not a choice for that bin.", name, munition, bin));
        return;
    }
    let e = &mut b.units[u].items[id];
    // a bin switched to a munition with another Ammunition Multiplier holds that many shots (rounded down; p.190)
    let before = munition_multiplier(e.munition.as_deref().unwrap_or("standard"));
    if let Some(s) = e.shots_left {
        e.shots_left = Some((s as f64 / before * munition_multiplier(munition)).floor() as i64);
    }
    e.munition = Some(munition.to_string());
    e.munition_chosen = Some(true);
    update_explosion(&mut b.units[u].items[id]);
    let e = &mut b.units[u].items[id];
    let bin = e.name.clone();
    b.log(format!("  {}: {} loaded with {} rounds (chosen in the unit's setup).", name, bin, munition));
}
