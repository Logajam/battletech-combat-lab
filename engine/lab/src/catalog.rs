//! What the Lab can put on the field: every unit and every board in the project's data folder (`data/`), loose files
//! and the two packs (`data/meks.zip`, `data/maps.zip`).
//!
//! A unit or board is named by its path under the data folder, the name the engine's settings take
//! (`FORCES[].mtf`, `DEFAULT_BOARD_PATH`): "Atlas AS7-K.mtf" for a loose file, "meks/3039u/Archer ARC-2K.mtf" for one in
//! the unit pack, "maps/AGoAC Maps/16x17 Desert 2.board" for one in the map pack. A packed file is unpacked to that
//! same path under the data folder the first time a battle uses it (`ensure`), so the engine reads it like any other.
//!
//! The unit list (name, tons, Battle Value, tech base) needs every unit parsed once; that takes a few seconds for the
//! whole pack, so it is done once and kept in `lab_cache/units.json`, made again when the data folder changes.
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use rayon::prelude::*;
use serde_json::{json, Value};

/// One unit of the list.
#[derive(Clone)]
pub struct UnitEntry {
    pub id: String,
    pub json: Value,
}

pub struct Catalog {
    pub data: PathBuf,
    pub units: Vec<UnitEntry>,
    pub boards: Vec<Value>,
}

/// where the units edited on the page are kept while a run needs them (emptied when the Lab starts)
const MODIFIED_DIR: &str = "_modified/";
const UNIT_PACK: &str = "meks.zip";
const MAP_PACK: &str = "maps.zip";
/// a board from the map pack is named under this folder
const MAP_PREFIX: &str = "maps/";

impl Catalog {
    /// Reads (or builds and keeps) the lists for the data folder `data`; the cache goes in `cache_dir`.
    pub fn load(data: &Path, cache_dir: &Path, defaults: &Value) -> Catalog {
        let _ = fs::remove_dir_all(data.join(MODIFIED_DIR));
        if let Err(e) = unpack_solid(data) {
            eprintln!("combatlab: the unit pack could not be unpacked: {}", e);
        }
        let sig = signature(data);
        let cache = cache_dir.join("units.json");
        let cached: Option<Value> = fs::read_to_string(&cache).ok().and_then(|t| serde_json::from_str(&t).ok());
        let units_json: Vec<Value> = match cached {
            Some(c) if c["signature"] == sig => c["units"].as_array().cloned().unwrap_or_default(),
            _ => {
                let started = std::time::Instant::now();
                let list = index_units(data, defaults);
                eprintln!("combatlab: unit list built ({} units, {:.1} s)", list.len(), started.elapsed().as_secs_f64());
                let _ = fs::create_dir_all(cache_dir);
                let _ = fs::write(&cache, serde_json::to_string(&json!({"signature": sig, "units": list})).unwrap());
                list
            }
        };
        let units = units_json.into_iter().map(|j| UnitEntry { id: j["id"].as_str().unwrap_or("").to_string(), json: j }).collect();
        Catalog { data: data.to_path_buf(), units, boards: index_boards(data) }
    }

    /// A unit edited on the page: its text as a scratch file under `data/_modified/` (named by a hash of the text), the name the
    /// engine reads it by. See runs.rs.
    pub fn scratch_unit(&self, text: &str) -> Result<String, String> {
        use std::hash::{Hash, Hasher};
        let mut h = std::collections::hash_map::DefaultHasher::new();
        text.hash(&mut h);
        let id = format!("{}{:016x}.mtf", MODIFIED_DIR, h.finish());
        let target = self.data.join(&id);
        if !target.exists() {
            fs::create_dir_all(self.data.join(MODIFIED_DIR)).map_err(|e| e.to_string())?;
            fs::write(&target, text).map_err(|e| e.to_string())?;
        }
        Ok(id)
    }

    /// Makes sure the unit or board named `id` is a file under the data folder (unpacking it from its pack if need be).
    /// Err = no such unit or board.
    pub fn ensure(&self, id: &str) -> Result<(), String> {
        if id.contains("..") {
            return Err(format!("bad name '{}'", id));
        }
        let target = self.data.join(id);
        if target.exists() {
            return Ok(());
        }
        let (pack, inner) = if id.starts_with("meks/") {
            (UNIT_PACK, id.to_string())
        } else if let Some(rest) = id.strip_prefix(MAP_PREFIX) {
            (MAP_PACK, rest.to_string())
        } else {
            return Err(format!("no file '{}' in the data folder", id));
        };
        let text = read_from_pack(&self.data.join(pack), &inner).ok_or_else(|| format!("'{}' is not in {}", inner, pack))?;
        if let Some(dir) = target.parent() {
            fs::create_dir_all(dir).map_err(|e| e.to_string())?;
        }
        fs::write(&target, text).map_err(|e| e.to_string())
    }
}

/// The packaged download carries the unit pack as ONE xz-compressed block, `data/meks.pack.xz` (ten times smaller than
/// meks.zip, which compresses each unit file on its own; tools/package_lab.py writes it). On the first start it is made
/// into `data/meks.zip` again (files stored, not compressed), so everything else reads units the usual way. The block
/// is, per unit file: name length (4 bytes, little-endian), name (UTF-8), content length (4 bytes), content.
fn unpack_solid(data: &Path) -> Result<(), String> {
    let solid = data.join("meks.pack.xz");
    let pack = data.join(UNIT_PACK);
    if pack.exists() || !solid.exists() {
        return Ok(());
    }
    let started = std::time::Instant::now();
    let mut raw = Vec::new();
    lzma_rs::xz_decompress(&mut std::io::BufReader::new(fs::File::open(&solid).map_err(|e| e.to_string())?), &mut raw).map_err(|e| format!("{:?}", e))?;
    let tmp = data.join("meks.zip.part");
    let mut z = zip::ZipWriter::new(fs::File::create(&tmp).map_err(|e| e.to_string())?);
    let opts = zip::write::SimpleFileOptions::default().compression_method(zip::CompressionMethod::Stored);
    let mut at = 0usize;
    let mut take = |n: usize| -> Result<&[u8], String> {
        let s = raw.get(at..at + n).ok_or("the unit pack is cut short")?;
        at += n;
        Ok(s)
    };
    let mut count = 0;
    loop {
        let Ok(len) = take(4) else { break };
        let len = u32::from_le_bytes(len.try_into().unwrap()) as usize;
        let name = String::from_utf8(take(len)?.to_vec()).map_err(|e| e.to_string())?;
        let size = u32::from_le_bytes(take(4)?.try_into().unwrap()) as usize;
        let content = take(size)?.to_vec();
        z.start_file(name, opts).map_err(|e| e.to_string())?;
        std::io::Write::write_all(&mut z, &content).map_err(|e| e.to_string())?;
        count += 1;
    }
    z.finish().map_err(|e| e.to_string())?;
    fs::rename(&tmp, &pack).map_err(|e| e.to_string())?;
    eprintln!("combatlab: unit pack unpacked ({} units, {:.1} s)", count, started.elapsed().as_secs_f64());
    Ok(())
}

/// What the cached unit list was built from: the loose unit files and the unit pack (names, sizes, times).
fn signature(data: &Path) -> Value {
    let mut parts: Vec<String> = Vec::new();
    for p in loose(data, "mtf") {
        let meta = fs::metadata(&p).ok();
        parts.push(format!("{}:{}", p.file_name().unwrap().to_string_lossy(), meta.map_or(0, |m| m.len())));
    }
    if let Ok(m) = fs::metadata(data.join(UNIT_PACK)) {
        let t = m.modified().ok().and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok()).map_or(0, |d| d.as_secs());
        parts.push(format!("{}:{}:{}", UNIT_PACK, m.len(), t));
    }
    // bump the list number whenever the engine's reading of a unit or its BV changes: the cache does not see code changes
    // (list 8, 2026-11-20: the BV reads its own view of the unit file)
    parts.push(format!("engine {} list 8 bv-megamek", env!("CARGO_PKG_VERSION")));
    json!(parts)
}

/// The data folder's own files with this extension, by name.
fn loose(data: &Path, ext: &str) -> Vec<PathBuf> {
    let mut out: Vec<PathBuf> = fs::read_dir(data).map(|r| r.filter_map(|e| e.ok()).map(|e| e.path()).filter(|p| p.extension().is_some_and(|x| x == ext)).collect()).unwrap_or_default();
    out.sort();
    out
}

/// Every file of a pack whose name ends with `ext`, as (name in the pack, text).
fn pack_files(pack: &Path, ext: &str) -> Vec<(String, String)> {
    let Ok(f) = fs::File::open(pack) else { return Vec::new() };
    let Ok(mut z) = zip::ZipArchive::new(f) else { return Vec::new() };
    let mut out = Vec::new();
    for i in 0..z.len() {
        let Ok(mut e) = z.by_index(i) else { continue };
        let name = e.name().to_string();
        if !name.ends_with(ext) {
            continue;
        }
        let mut text = String::new();
        if e.read_to_string(&mut text).is_ok() {
            out.push((name, text));
        }
    }
    out
}

fn read_from_pack(pack: &Path, name: &str) -> Option<String> {
    let mut z = zip::ZipArchive::new(fs::File::open(pack).ok()?).ok()?;
    let mut e = z.by_name(name).ok()?;
    let mut text = String::new();
    e.read_to_string(&mut text).ok()?;
    Some(text)
}

/// The unit list: every loose unit file, then the unit pack's, each parsed by the engine (a unit it cannot read is
/// listed with `ok: false` and the reason, so the page can show it greyed out).
fn index_units(data: &Path, defaults: &Value) -> Vec<Value> {
    let mut files: Vec<(String, String, String)> = Vec::new();
    for p in loose(data, "mtf") {
        if let Ok(t) = fs::read_to_string(&p) {
            files.push((p.file_name().unwrap().to_string_lossy().to_string(), "project".into(), t));
        }
    }
    for (name, text) in pack_files(&data.join(UNIT_PACK), ".mtf") {
        // "meks/3039u/Archer ARC-2K.mtf": the pack's folder is the unit's source (era / book)
        let source = name.split('/').nth(1).unwrap_or("").to_string();
        files.push((name, source, text));
    }
    let db = btsim_core::equipment::EquipmentDb::shared();
    let cfg = btsim_core::config::Config::from_json(defaults);
    files.par_iter().map(|(id, source, text)| describe_unit(db, &cfg, id, source, text)).collect()
}

/// The board list: loose boards, then the map pack's; each with its size (the file's "size W H" line).
fn index_boards(data: &Path) -> Vec<Value> {
    let size = |text: &str| -> (i64, i64) {
        text.lines()
            .find_map(|l| {
                let mut p = l.split_whitespace();
                if p.next() != Some("size") {
                    return None;
                }
                Some((p.next()?.parse().ok()?, p.next()?.parse().ok()?))
            })
            .unwrap_or((0, 0))
    };
    let mut out = Vec::new();
    for p in loose(data, "board") {
        if let Ok(t) = fs::read_to_string(&p) {
            let (w, h) = size(&t);
            let id = p.file_name().unwrap().to_string_lossy().to_string();
            out.push(json!({"id": id, "name": id.trim_end_matches(".board").replace('_', " "), "width": w, "height": h, "source": "project"}));
        }
    }
    for (name, text) in pack_files(&data.join(MAP_PACK), ".board") {
        let (w, h) = size(&text);
        let file = name.rsplit('/').next().unwrap_or(&name).to_string();
        let source = name.rsplit_once('/').map_or("", |(d, _)| d).to_string();
        out.push(json!({"id": format!("{}{}", MAP_PREFIX, name), "name": file.trim_end_matches(".board"), "width": w, "height": h, "source": source}));
    }
    out
}

pub use crate::describe::{describe_unit, equipment_list, unit_structure};
