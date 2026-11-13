//! COMBAT LAB, CL3 (INTEGRATION__COMBAT_LAB_SPECS.md): the program the Combat Lab pages talk to. Daniel's decision
//! (2026-10-31): `CombatLab.exe` starts a local server and opens the browser; works offline.
//!
//!     combatlab [--port N] [--no-browser] [--web DIR]
//!
//! Serves the pages (built into the program; `--web DIR` serves them from a folder instead, for work on them) and
//! answers JSON requests, `POST /api/<name>` with a JSON body:
//!
//! | request | body | answer |
//! |---|---|---|
//! | `info` | - | bots, cores, the default board, the project folder |
//! | `list_units` | - | every unit: id, name, tons, Battle Value, tech base, source |
//! | `list_boards` | - | every board: id, name, width, height, source |
//! | `estimate` | {setup} | seconds for the batch, from a few pilot battles |
//! | `run` | {setup} | {run}: the batch started (runs.rs has the setup) |
//! | `progress` | {run} | battles done, finished, seconds |
//! | `results` | {run, filter?, from?, to?, bucket?} | statistics (of the battles the filter keeps, and of all) and the battle list in pieces (runs.rs) |
//! | `cancel` | {run} | stops the batch (battles under way finish) |
//! | `add_unit` | {file, text} | a dropped unit file copied into the data folder and listed |
//! | `history` | {run, sim} or {setup, seed} | one battle's full history (btsim_core::history, CL2) |
//!
//! and `GET /replay?run=R&sim=S` (or `?seed=S` after a setup was sent to `history`): the replay page of that battle.
//! An answer that went wrong is {"error": "what is wrong"}. Only this machine can connect (127.0.0.1); nothing leaves
//! it. The project folder is the repository root (BTSIM_ROOT, else found from where the program is), with its data
//! folder `data/` (units, boards, packs); lists are cached in `lab_cache/`.
mod catalog;
mod runs;

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use btsim_core::scenario::SetupPaths;
use serde_json::{json, Value};

#[global_allocator]
static ALLOC: mimalloc::MiMalloc = mimalloc::MiMalloc;

/// The pages, built into the program.
const PAGES: [(&str, &str, &str); 3] = [
    ("index.html", "text/html; charset=utf-8", include_str!("../web/index.html")),
    ("lab.css", "text/css; charset=utf-8", include_str!("../web/lab.css")),
    ("lab.js", "text/javascript; charset=utf-8", include_str!("../web/lab.js")),
];

struct Lab {
    paths: SetupPaths,
    catalog: catalog::Catalog,
    runs: Mutex<HashMap<u64, Arc<runs::Run>>>,
    next_run: Mutex<u64>,
    /// the last setup sent to `history` without a run: `GET /replay?seed=S` replays it
    last_setup: Mutex<Option<Value>>,
    /// units added from files this session (`add_unit`), after the catalog's
    added: Mutex<Vec<Value>>,
    defaults: Value,
    web: Option<PathBuf>,
}

fn arg(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1)).cloned()
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let paths = SetupPaths::find();
    let defaults: Value = std::fs::read_to_string(&paths.defaults)
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_else(|| panic!("combatlab: no settings defaults at {} (set BTSIM_ROOT to the project folder)", paths.defaults.display()));
    let data = paths.root.join(defaults["DATA_DIR"].as_str().unwrap_or("./data"));
    let catalog = catalog::Catalog::load(&data, &paths.root.join("lab_cache"), &defaults);
    eprintln!("combatlab: {} units, {} boards in {}", catalog.units.len(), catalog.boards.len(), data.display());
    let lab = Arc::new(Lab { paths, catalog, runs: Mutex::new(HashMap::new()), next_run: Mutex::new(1), last_setup: Mutex::new(None), added: Mutex::new(Vec::new()), defaults: defaults.clone(), web: arg(&args, "--web").map(PathBuf::from) });

    // a free port: the one asked for, else the first free one from 8765
    let wanted: Option<u16> = arg(&args, "--port").map(|p| p.parse().expect("--port"));
    let listener = match wanted {
        Some(p) => TcpListener::bind(("127.0.0.1", p)).unwrap_or_else(|e| panic!("combatlab: port {}: {}", p, e)),
        None => (8765..8865).find_map(|p| TcpListener::bind(("127.0.0.1", p)).ok()).expect("combatlab: no free port"),
    };
    let url = format!("http://127.0.0.1:{}/", listener.local_addr().unwrap().port());
    println!("Combat Lab is running at {}  (close this window to stop it)", url);
    if !args.iter().any(|a| a == "--no-browser") {
        open_browser(&url);
    }
    for stream in listener.incoming().flatten() {
        let lab = lab.clone();
        std::thread::spawn(move || {
            let _ = serve(stream, &lab);
        });
    }
}

/// Opens the page in the computer's browser (Windows, macOS, Linux); if that fails the address printed above still works.
fn open_browser(url: &str) {
    let r = if cfg!(target_os = "windows") {
        std::process::Command::new("cmd").args(["/C", "start", "", url]).spawn()
    } else if cfg!(target_os = "macos") {
        std::process::Command::new("open").arg(url).spawn()
    } else {
        std::process::Command::new("xdg-open").arg(url).spawn()
    };
    if r.is_err() {
        eprintln!("combatlab: open {} in your browser", url);
    }
}

// =====================================================================================================================
// HTTP: just enough of it for one browser on this machine (one request per connection)
// =====================================================================================================================

fn serve(stream: TcpStream, lab: &Lab) -> std::io::Result<()> {
    let mut reader = BufReader::new(stream.try_clone()?);
    let mut first = String::new();
    reader.read_line(&mut first)?;
    let mut parts = first.split_whitespace();
    let (method, target) = (parts.next().unwrap_or("").to_string(), parts.next().unwrap_or("/").to_string());
    let mut length = 0usize;
    loop {
        let mut line = String::new();
        if reader.read_line(&mut line)? == 0 || line.trim().is_empty() {
            break;
        }
        if let Some((k, v)) = line.split_once(':') {
            if k.trim().eq_ignore_ascii_case("content-length") {
                length = v.trim().parse().unwrap_or(0);
            }
        }
    }
    let mut body = vec![0u8; length.min(64 << 20)];
    reader.read_exact(&mut body)?;
    let (path, query) = target.split_once('?').unwrap_or((target.as_str(), ""));
    let query: HashMap<String, String> = query.split('&').filter_map(|kv| kv.split_once('=')).map(|(k, v)| (k.to_string(), v.to_string())).collect();
    let (status, kind, content): (&str, &str, Vec<u8>) = if method == "POST" && path.starts_with("/api/") {
        let request: Value = serde_json::from_slice(&body).unwrap_or(json!({}));
        let name = &path[5..];
        // a request that panics answers with the message, and the server goes on
        let answer = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| api(lab, name, &request))).unwrap_or_else(|e| {
            Err(e.downcast_ref::<String>().cloned().or_else(|| e.downcast_ref::<&str>().map(|m| m.to_string())).unwrap_or_else(|| "the engine stopped".into()))
        });
        let v = answer.unwrap_or_else(|e| json!({"error": e}));
        ("200 OK", "application/json", serde_json::to_vec(&v).unwrap())
    } else if method == "GET" && path == "/replay" {
        match replay_page(lab, &query) {
            Ok(page) => ("200 OK", "text/html; charset=utf-8", page.into_bytes()),
            Err(e) => ("404 Not Found", "text/plain; charset=utf-8", e.into_bytes()),
        }
    } else if method == "GET" {
        match page(lab, path.trim_start_matches('/')) {
            Some((kind, bytes)) => ("200 OK", kind, bytes),
            None => ("404 Not Found", "text/plain; charset=utf-8", b"not found".to_vec()),
        }
    } else {
        ("405 Method Not Allowed", "text/plain; charset=utf-8", Vec::new())
    };
    let mut out = stream;
    write!(out, "HTTP/1.1 {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n", status, kind, content.len())?;
    out.write_all(&content)?;
    out.flush()
}

fn page(lab: &Lab, name: &str) -> Option<(&'static str, Vec<u8>)> {
    let name = if name.is_empty() { "index.html" } else { name };
    let (_, kind, built_in) = PAGES.iter().find(|(n, _, _)| *n == name)?;
    match &lab.web {
        Some(dir) => std::fs::read(dir.join(name)).ok().map(|b| (*kind, b)),
        None => Some((*kind, built_in.as_bytes().to_vec())),
    }
}

// =====================================================================================================================
// THE REQUESTS
// =====================================================================================================================

fn run_of(lab: &Lab, req: &Value) -> Result<Arc<runs::Run>, String> {
    let id = req["run"].as_u64().ok_or("which run?")?;
    lab.runs.lock().unwrap().get(&id).cloned().ok_or_else(|| format!("no run {}", id))
}

fn api(lab: &Lab, name: &str, req: &Value) -> Result<Value, String> {
    match name {
        "info" => Ok(json!({
            "bots": runs::BOTS,
            "cores": std::thread::available_parallelism().map_or(1, |n| n.get()),
            "default_board": "16x17_Grassland_1.board",
            "project": lab.paths.root.display().to_string(),
        })),
        "list_units" => {
            let added = lab.added.lock().unwrap();
            Ok(json!({"units": lab.catalog.units.iter().map(|u| &u.json).chain(added.iter()).collect::<Vec<_>>()}))
        }
        "add_unit" => add_unit(lab, req),
        "list_boards" => Ok(json!({"boards": lab.catalog.boards})),
        "estimate" => {
            let s = runs::scenario_of(&req["setup"], &lab.catalog, &lab.paths)?;
            Ok(runs::estimate(&s, req["setup"]["battles"].as_u64().unwrap_or(20), req["setup"]["threads"].as_u64().unwrap_or(0) as usize))
        }
        "run" => {
            let s = runs::scenario_of(&req["setup"], &lab.catalog, &lab.paths)?;
            let id = {
                let mut n = lab.next_run.lock().unwrap();
                *n += 1;
                *n - 1
            };
            let run = runs::Run::start(id, req["setup"].clone(), s);
            lab.runs.lock().unwrap().insert(id, run);
            Ok(json!({"run": id}))
        }
        "progress" => Ok(run_of(lab, req)?.progress()),
        "results" => Ok(run_of(lab, req)?.results(req)),
        "cancel" => {
            let run = run_of(lab, req)?;
            run.cancel.store(true, std::sync::atomic::Ordering::Relaxed);
            Ok(run.progress())
        }
        "history" => history(lab, req),
        _ => Err(format!("unknown request '{}'", name)),
    }
}

/// A unit file the user dropped on a team (Part B: "A dropped file is copied into the project's Mech folder if it is not
/// already there"): {file, text} -> {unit, copied}. A file of that name already in the folder is used as it is; a
/// file the engine cannot read is not kept.
fn add_unit(lab: &Lab, req: &Value) -> Result<Value, String> {
    let file = req["file"].as_str().ok_or("no file name")?;
    let name = std::path::Path::new(file).file_name().map(|n| n.to_string_lossy().to_string()).ok_or("no file name")?;
    if !name.to_lowercase().ends_with(".mtf") {
        return Err("only .mtf unit files can be added".into());
    }
    let target = lab.catalog.data.join(&name);
    let copied = !target.exists();
    let text = if copied { req["text"].as_str().ok_or("the file is empty")?.to_string() } else { std::fs::read_to_string(&target).map_err(|e| e.to_string())? };
    let cfg = btsim_core::config::Config::from_json(&lab.defaults);
    let unit = catalog::describe_unit(btsim_core::equipment::EquipmentDb::shared(), &cfg, &name, "project", &text);
    if unit["ok"] != true {
        return Err(format!("the engine cannot play this unit: {}", unit["why"].as_str().unwrap_or("unreadable")));
    }
    if copied {
        std::fs::write(&target, &text).map_err(|e| e.to_string())?;
    }
    let mut added = lab.added.lock().unwrap();
    if !lab.catalog.units.iter().any(|u| u.id == name) && !added.iter().any(|u| u["id"] == name.as_str()) {
        added.push(unit.clone());
    }
    Ok(json!({"unit": unit, "copied": copied}))
}

/// The team colours a setup chose ({team: "#rrggbb"}), for the replay page.
fn colours(setup: &Value) -> Value {
    let m: serde_json::Map<String, Value> = setup["teams"].as_array().into_iter().flatten()
        .filter_map(|t| Some((t["name"].as_str()?.to_string(), json!(t["colour"].as_str()?))))
        .collect();
    Value::Object(m)
}

/// One battle's full history (with the setup's team colours): battle `sim` of run `run`, or the setup `setup` on seed
/// `seed`.
fn history(lab: &Lab, req: &Value) -> Result<Value, String> {
    let mut record = history_bare(lab, req)?;
    let setup = if req.get("run").is_some_and(|r| !r.is_null()) { run_of(lab, req)?.setup.clone() } else { req["setup"].clone() };
    record["colours"] = colours(&setup);
    Ok(record)
}

fn history_bare(lab: &Lab, req: &Value) -> Result<Value, String> {
    let seed_of = |v: &Value| v.as_u64().or_else(|| v.as_str().and_then(|s| s.parse().ok()));
    if req.get("run").is_some_and(|r| !r.is_null()) {
        let run = run_of(lab, req)?;
        let sim = req["sim"].as_u64().ok_or("which battle?")?;
        let seed = btsim_core::dice::PcgDice::battle_seed(run.seed, sim);
        return Ok(run.scenario.run_history(sim, seed).1);
    }
    let seed = seed_of(&req["seed"]).ok_or("which seed?")?;
    let s = runs::scenario_of(&req["setup"], &lab.catalog, &lab.paths)?;
    *lab.last_setup.lock().unwrap() = Some(req["setup"].clone());
    Ok(s.run_history(req["sim"].as_u64().unwrap_or(1), seed).1)
}

fn replay_page(lab: &Lab, q: &HashMap<String, String>) -> Result<String, String> {
    let num = |k: &str| q.get(k).and_then(|v| v.parse::<u64>().ok());
    let record = if let Some(run) = num("run") {
        history(lab, &json!({"run": run, "sim": num("sim").ok_or("which battle?")?}))?
    } else {
        let setup = lab.last_setup.lock().unwrap().clone().ok_or("no setup to replay")?;
        history(lab, &json!({"setup": setup, "seed": num("seed").ok_or("which seed?")?}))?
    };
    Ok(btsim_core::history::page(&record))
}
