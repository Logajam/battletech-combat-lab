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
mod describe;
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
const PAGES: [(&str, &str, &str); 14] = [
    ("three.min.js", "text/javascript; charset=utf-8", include_str!("../web/three.min.js")),
    ("tabletop.js", "text/javascript; charset=utf-8", include_str!("../web/tabletop.js")),
    ("mechsprites.js", "text/javascript; charset=utf-8", include_str!("../web/mechsprites.js")),
    ("spritemap.js", "text/javascript; charset=utf-8", include_str!("../web/spritemap.js")),
    ("boardart.js", "text/javascript; charset=utf-8", include_str!("../web/boardart.js")),
    ("mapview.js", "text/javascript; charset=utf-8", include_str!("../web/mapview.js")),
    ("play.html", "text/html; charset=utf-8", include_str!("../web/play.html")),
    ("play.js", "text/javascript; charset=utf-8", include_str!("../web/play.js")),
    ("tt_layer.js", "text/javascript; charset=utf-8", include_str!("../web/tt_layer.js")),
    ("index.html", "text/html; charset=utf-8", include_str!("../web/index.html")),
    ("lab.css", "text/css; charset=utf-8", include_str!("../web/lab.css")),
    ("lab.js", "text/javascript; charset=utf-8", include_str!("../web/lab.js")),
    ("options.json", "application/json", include_str!("../web/options.json")),
    ("availability.json", "application/json", include_str!("../web/availability.json")),
];

struct Lab {
    paths: SetupPaths,
    catalog: catalog::Catalog,
    runs: Mutex<HashMap<u64, Arc<runs::Run>>>,
    next_run: Mutex<u64>,
    /// games with a person in them (BattleROM play), by number
    games: Mutex<HashMap<u64, Arc<btsim_core::play_session::Game>>>,
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

/// Asks the operating system to run this program below normal priority, so a game or any other program the user has
/// open gets the processor first and the battles take only what is left (Daniel, 2026-11-17: a game crashed when a run
/// took every cycle). Windows: BELOW_NORMAL_PRIORITY_CLASS for the whole process (every battle thread inherits it).
/// Elsewhere: nice +10. No new library: the calls are the system's own (kernel32 / libc, linked by Rust's std already).
fn lower_priority() {
    #[cfg(windows)]
    {
        extern "system" {
            fn GetCurrentProcess() -> *mut core::ffi::c_void;
            fn SetPriorityClass(process: *mut core::ffi::c_void, class: u32) -> i32;
        }
        const BELOW_NORMAL_PRIORITY_CLASS: u32 = 0x0000_4000;
        // SAFETY: the pseudo-handle of this process and a documented priority class; failure only leaves the priority as it was
        let ok = unsafe { SetPriorityClass(GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS) };
        if ok == 0 {
            eprintln!("combatlab: could not lower the priority (battles run at normal priority)");
        }
    }
    #[cfg(unix)]
    {
        extern "C" {
            fn nice(inc: i32) -> i32;
        }
        // SAFETY: nice() only changes this process's scheduling priority
        unsafe { nice(10) };
    }
}

fn main() {
    lower_priority();
    let args: Vec<String> = std::env::args().skip(1).collect();
    let paths = SetupPaths::find();
    let defaults: Value = std::fs::read_to_string(&paths.defaults)
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_else(|| panic!("combatlab: no settings defaults at {} (set BTSIM_ROOT to the project folder)", paths.defaults.display()));
    let data = paths.root.join(defaults["DATA_DIR"].as_str().unwrap_or("./data"));
    let catalog = catalog::Catalog::load(&data, &paths.root.join("lab_cache"), &defaults);
    eprintln!("combatlab: {} units, {} boards in {}", catalog.units.len(), catalog.boards.len(), data.display());
    if catalog.units.is_empty() || catalog.boards.is_empty() {
        println!("NO UNITS OR BOARDS FOUND in {}.\nThe download comes in two parts: unzip the data part into the same folder as this program (its data folder\nmust sit beside CombatLab.exe), then start CombatLab again.", data.display());
    }
    let lab = Arc::new(Lab { paths, catalog, runs: Mutex::new(HashMap::new()), next_run: Mutex::new(1), games: Mutex::new(HashMap::new()), last_setup: Mutex::new(None), added: Mutex::new(Vec::new()), defaults: defaults.clone(), web: arg(&args, "--web").map(PathBuf::from) });

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

/// A URL path piece with its %XX escapes undone (the page asks for `sprites/` + encodeURIComponent(name)).
fn pct_decode(s: &str) -> String {
    let b = s.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        if b[i] == b'%' && i + 2 < b.len() + 0 && i + 2 <= b.len() - 1 {
            if let Ok(v) = u8::from_str_radix(&s[i + 1..i + 3], 16) {
                out.push(v);
                i += 3;
                continue;
            }
        }
        out.push(b[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn page(lab: &Lab, name: &str) -> Option<(&'static str, Vec<u8>)> {
    let name = if name.is_empty() { "index.html" } else { name };
    // MegaMek's unit pictures (tools/make_mechsprites_all.py): too many to build in, read from the folder they live in (CREDITS.txt goes with them)
    if let Some(file) = name.strip_prefix("sprites/") {
        let file = pct_decode(file);
        if file.contains("..") || file.contains('/') || file.contains('\\') {
            return None;
        }
        let dir = match &lab.web {
            Some(d) => d.join("sprites"),
            None => lab.paths.root.join("engine").join("lab").join("web").join("sprites"),
        };
        let kind = if file.ends_with(".png") { "image/png" } else { "text/plain; charset=utf-8" };
        return std::fs::read(dir.join(&file)).ok().map(|b| (kind, b));
    }
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
            // "human" is a team the person plays (Play button); a batch of simulations cannot include one
            "bots": runs::BOTS.iter().copied().chain(["human"]).collect::<Vec<_>>(),
            "cores": std::thread::available_parallelism().map_or(1, |n| n.get()),
            "default_board": "16x17_Grassland_1.board",
            "project": lab.paths.root.display().to_string(),
            "skill_table": btsim_core::battle_value::SKILL_TABLE,
            "missing_data": lab.catalog.units.is_empty() || lab.catalog.boards.is_empty(),
        })),
        "list_units" => {
            let added = lab.added.lock().unwrap();
            Ok(json!({"units": lab.catalog.units.iter().map(|u| &u.json).chain(added.iter()).collect::<Vec<_>>()}))
        }
        "add_unit" => add_unit(lab, req),
        // the unit sheet and editor (Daniel, 2026-11-15): a unit's file text, the equipment it can be built from, and the
        // engine's reading (Battle Value, or why it cannot be played) of a text that has been edited on the page
        "unit_text" => {
            let id = req["id"].as_str().ok_or("which unit?")?;
            lab.catalog.ensure(id)?;
            let text = std::fs::read_to_string(lab.catalog.data.join(id)).map_err(|e| format!("{}: {}", id, e))?;
            Ok(json!({"id": id, "text": text}))
        }
        "unit_eval" => {
            let text = req["text"].as_str().ok_or("no unit text")?;
            let cfg = btsim_core::config::Config::from_json(&lab.defaults);
            let db = btsim_core::equipment::EquipmentDb::shared();
            Ok(json!({"unit": catalog::describe_unit(db, &cfg, "(edited)", "custom", text), "structure": catalog::unit_structure(db, text), "bins": catalog::unit_bins(db, &cfg, text), "c3": catalog::unit_c3(db, &cfg, text)}))
        }
        "equipment_list" => Ok(json!({"equipment": catalog::equipment_list(btsim_core::equipment::EquipmentDb::shared())})),
        "list_boards" => Ok(json!({"boards": lab.catalog.boards})),
        // a board file's text, for the Map page's preview (the page draws it); the map pack's boards are unpacked on the way
        "board" => {
            let id = req["id"].as_str().ok_or("which board?")?;
            lab.catalog.ensure(id)?;
            let text = std::fs::read_to_string(lab.catalog.data.join(id)).map_err(|e| format!("{}: {}", id, e))?;
            Ok(json!({"id": id, "text": text}))
        }
        "estimate" => {
            no_human(&req["setup"])?;
            let plan = runs::scenario_of(&req["setup"], &lab.catalog, &lab.paths)?;
            let s = plan.scenario_for(1, 1).0;
            Ok(runs::estimate(&s, req["setup"]["battles"].as_u64().unwrap_or(20), req["setup"]["threads"].as_u64().unwrap_or(0) as usize, req["setup"]["full_power"].as_bool().unwrap_or(false)))
        }
        "play_start" => play_start(lab, req),
        // the Lab's Play button asks whether the setup can be played before it opens the play page (which starts the game itself, as in the browser build)
        "play_check" => {
            let mut setup = req["setup"].clone();
            let mut humans = 0;
            if let Some(teams) = setup["teams"].as_array_mut() {
                for t in teams {
                    if t["bot"].as_str() == Some("human") {
                        humans += 1;
                        t["bot"] = json!("gladiator");
                    }
                }
            }
            if humans == 0 {
                return Err("No team is set to Human. Set one team's bot to Human, then press Play.".into());
            }
            runs::scenario_of(&setup, &lab.catalog, &lab.paths)?;
            Ok(json!({"ok": true}))
        }
        "play_poll" => {
            let g = game_of(lab, req)?;
            Ok(g.poll(std::time::Duration::from_millis(req["wait_ms"].as_u64().unwrap_or(25000).min(60000))))
        }
        "play_query" => Ok(game_of(lab, req)?.query(req["query"].clone(), std::time::Duration::from_secs(60))),
        "play_answer" => {
            game_of(lab, req)?.answer(req["seq"].as_u64().ok_or("which question?")?, req["answer"].clone())?;
            Ok(json!({"ok": true}))
        }
        "run" => {
            no_human(&req["setup"])?;
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
        // CL20: a run as one file (setup, every battle's line, the crashes with their seeds, the unit files the setup used that
        // are not in the packs), so it can be sent to Claude for bug hunting and opened again anywhere
        "save_run" => {
            let run = run_of(lab, req)?;
            let mut files = serde_json::Map::new();
            for t in run.setup["teams"].as_array().into_iter().flatten() {
                for u in t["units"].as_array().into_iter().flatten() {
                    if u["mtf_text"].is_string() {
                        continue;        // a modified unit travels inside the setup itself
                    }
                    if let Some(id) = u["unit"].as_str() {
                        if !id.contains('/') && !id.contains("..") {
                            if let Ok(text) = std::fs::read_to_string(lab.catalog.data.join(id)) {
                                files.insert(id.to_string(), json!(text));
                            }
                        }
                    }
                }
            }
            Ok(run.export(files))
        }
        "load_run" => {
            let f = &req["file"];
            if f["combatlab_run"] != 1 {
                return Err("this is not a Combat Lab run file".into());
            }
            for (id, text) in f["unit_files"].as_object().into_iter().flatten() {
                let target = lab.catalog.data.join(id);
                if id.contains('/') || id.contains("..") || !id.to_lowercase().ends_with(".mtf") {
                    continue;
                }
                if !target.exists() {
                    add_unit(lab, &json!({"file": id, "text": text}))?;
                }
            }
            let plan = runs::scenario_of(&f["setup"], &lab.catalog, &lab.paths)?;
            let id = {
                let mut n = lab.next_run.lock().unwrap();
                *n += 1;
                *n - 1
            };
            let run = runs::Run::restore(id, f["setup"].clone(), plan, f["lines"].as_array().cloned().unwrap_or_default(), f["crashed"].as_array().cloned().unwrap_or_default(), f["seconds"].as_f64().unwrap_or(0.0));
            lab.runs.lock().unwrap().insert(id, run);
            Ok(json!({"run": id, "setup": f["setup"]}))
        }
        // a battle that crashes replays into the same crash: say so in words instead of dropping the request
        "history" => std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| history(lab, req)))
            .unwrap_or_else(|e| Err(format!("this battle crashes when played again: {}", e.downcast_ref::<String>().cloned().or_else(|| e.downcast_ref::<&str>().map(|s| s.to_string())).unwrap_or_else(|| "panic".into())))),
        _ => Err(format!("unknown request '{}'", name)),
    }
}

/// A unit file the user dropped on a team (Part B: "A dropped file is copied into the project's Mech folder if it is not
/// already there"): {file, text} -> {unit, copied}. A file of that name already in the folder is used as it is; a
/// file the engine cannot read is not kept.
/// A team set to Human is played (Play), not simulated.
fn no_human(setup: &Value) -> Result<(), String> {
    match setup["teams"].as_array().and_then(|t| t.iter().find(|t| t["bot"].as_str() == Some("human"))) {
        Some(t) => Err(format!("Team {} is set to Human: a person plays it, so it cannot be run as a simulation. Use Play, or set the team to a bot.", t["name"].as_str().unwrap_or("?"))),
        None => Ok(()),
    }
}

fn game_of(lab: &Lab, req: &Value) -> Result<Arc<btsim_core::play_session::Game>, String> {
    let id = req["game"].as_u64().ok_or("which game?")?;
    lab.games.lock().unwrap().get(&id).cloned().ok_or_else(|| "no such game (the Lab was restarted?)".to_string())
}

/// Start a battle with a person in it (BattleROM): the teams whose bot is "human" are played by the page; the rest by their bots.
fn play_start(lab: &Lab, req: &Value) -> Result<Value, String> {
    let mut setup = req["setup"].clone();
    let mut human: Vec<String> = Vec::new();
    if let Some(teams) = setup["teams"].as_array_mut() {
        for t in teams {
            if t["bot"].as_str() == Some("human") {
                human.push(t["name"].as_str().unwrap_or("").to_string());
                t["bot"] = json!("gladiator"); // the engine builds the team with a bot; the person answers in its place
            }
        }
    }
    // a game resumed from a list with a `branch` may start with nobody human (a team is handed to the person at the cut: Play from here on a bot battle)
    if human.is_empty() && !req.get("resume").is_some_and(|v| v.is_object()) {
        return Err("No team is set to Human. Set one team's bot to Human, then press Play.".into());
    }
    // a seed may arrive as text: a battle's seed passes JavaScript's exact-integer limit
    let asked = req["seed"].as_u64().or_else(|| req["seed"].as_str().and_then(|t| t.parse().ok()));
    let seed = asked.or_else(|| setup["seed"].as_u64()).filter(|s| *s != 0).unwrap_or_else(|| {
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(1, |d| d.as_nanos() as u64 & 0xFFFF_FFFF)
    });
    let plan = runs::scenario_of(&setup, &lab.catalog, &lab.paths)?;
    let scenario = plan.scenario_for(req["sim"].as_u64().filter(|n| *n >= 1).unwrap_or(1), seed).0;
    let id = {
        let mut games = lab.games.lock().unwrap();
        let id = games.len() as u64 + 1;
        games.insert(id, btsim_core::play_session::Game::start(scenario, seed, human, colours(&setup), req.get("resume").filter(|v| v.is_object()).cloned()));
        id
    };
    Ok(json!({"game": id, "seed": seed, "colours": colours(&setup)}))
}

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
        return Ok(run.plan.scenario_for(sim, seed).0.run_history(sim, seed).1);
    }
    let seed = seed_of(&req["seed"]).ok_or("which seed?")?;
    let s = runs::scenario_of(&req["setup"], &lab.catalog, &lab.paths)?.scenario_for(req["sim"].as_u64().unwrap_or(1), seed).0;
    *lab.last_setup.lock().unwrap() = Some(req["setup"].clone());
    Ok(s.run_history(req["sim"].as_u64().unwrap_or(1), seed).1)
}

fn replay_page(lab: &Lab, q: &HashMap<String, String>) -> Result<String, String> {
    let num = |k: &str| q.get(k).and_then(|v| v.parse::<u64>().ok());
    let record = if let Some(run) = num("run") {
        history(lab, &json!({"run": run, "sim": num("sim").ok_or("which battle?")?}))?
    } else {
        let setup = lab.last_setup.lock().unwrap().clone().ok_or("no setup to replay")?;
        history(lab, &json!({"setup": setup, "seed": num("seed").ok_or("which seed?")?, "sim": num("sim").unwrap_or(1)}))?
    };
    Ok(btsim_core::history::page(&record))
}
