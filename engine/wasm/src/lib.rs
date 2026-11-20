//! COMBAT LAB IN THE BROWSER: the engine and the Lab's batch statistics as one WebAssembly module, so a visitor's own
//! computer plays the battles (no server does any work; the pages and data are static files).
//!
//! The module has no file system, no threads and no clock of its own, so the page gives it everything:
//! * files (settings defaults, units, boards) are handed in with `files` and kept in memory (`SetupPaths::memory`);
//! * the clock is the import `host_now_ms`; a panic's message goes out through `host_panic` (a panic then stops the
//!   instance; the page notes the battle's seed as a crash and starts a fresh worker);
//! * parallelism is the page's: it starts one instance of this module per CPU core in Web Workers, each plays its
//!   share of the battles (`play`), and one more instance on the page keeps the batch's statistics (`push`, `results`:
//!   the very code the desktop Lab uses, lab/src/runs.rs, included below).
//!
//! The interface is one call: `wb_call(name, request)` -> answer, both JSON text, moved through memory the page
//! reserves with `wb_alloc` (web/engine.js has the other end). The names:
//!
//! | name | request | answer |
//! |---|---|---|
//! | `files` | {defaults?, files: {name: text}} | {files: count held} - add to the files held |
//! | `run` | {setup} | {run}: a batch started on this instance (statistics only; checks the setup in words) |
//! | `push` | {run, lines, crashed, finished?, seconds?} | the battles' lines the workers sent |
//! | `progress` `results` `cancel` | as the desktop Lab's | same |
//! | `save_run` `load_run` | as the desktop Lab's | same |
//! | `prepare` | {setup} | {ok, max_turns}: the worker builds the batch's scenarios |
//! | `play` | {sim} | {crash, line}: battle `sim` of the prepared batch |
//! | `history` | {setup, sim, seed?} | one battle's record |
//! | `page` | {record} | {html}: the replay page of a `history` record |
//! | `seed` | {run_seed, sim} | {seed}: the seed battle `sim` is played on |
//!
//! Only the browser build (wasm32) has anything in it; on the desktop this crate is empty.
#![cfg(target_arch = "wasm32")]

#[path = "../../lab/src/runs.rs"]
mod runs;
#[path = "../../lab/src/describe.rs"]
mod describe;

/// What `runs.rs` asks of the desktop's catalog, from the files held in memory.
mod catalog {
    pub struct Catalog;
    impl Catalog {
        pub fn ensure(&self, id: &str) -> Result<(), String> {
            if super::STATE.with(|s| s.borrow().paths.memory.as_ref().is_some_and(|m| m.files.contains_key(id))) {
                Ok(())
            } else {
                Err(format!("no unit or board '{}'", id))
            }
        }
        /// A unit edited on the page (its text is in the setup): `plan_of` has already put it in the files held under this
        /// name (a hash of the text); the desktop Lab writes a scratch file instead.
        pub fn scratch_unit(&self, text: &str) -> Result<String, String> {
            Ok(super::scratch_id(text))
        }
    }
}

use std::cell::RefCell;
use std::collections::HashMap;
use std::sync::Arc;

use btsim_core::scenario::{MemoryFiles, SetupPaths};
use serde_json::{json, Value};

extern "C" {
    /// the page is told a panic's message just before the instance stops
    fn host_panic(ptr: *const u8, len: usize);
}

struct State {
    paths: SetupPaths,
    runs: HashMap<u64, Arc<runs::Run>>,
    next_run: u64,
    /// the batch a worker plays (`prepare`) and its run seed
    prepared: Option<(runs::Plan, u64)>,
    out: Vec<u8>,
}

thread_local! {
    static STATE: RefCell<State> = RefCell::new(State {
        paths: SetupPaths { defaults: Default::default(), root: Default::default(), memory: Some(MemoryFiles::default()) },
        runs: HashMap::new(),
        next_run: 1,
        prepared: None,
        out: Vec::new(),
    });
}

#[no_mangle]
pub extern "C" fn wb_init() {
    std::panic::set_hook(Box::new(|info| {
        let msg = info.to_string();
        unsafe { host_panic(msg.as_ptr(), msg.len()) };
    }));
}

#[no_mangle]
pub extern "C" fn wb_alloc(len: usize) -> *mut u8 {
    let mut v = Vec::<u8>::with_capacity(len.max(1));
    let p = v.as_mut_ptr();
    std::mem::forget(v);
    p
}

#[no_mangle]
pub extern "C" fn wb_free(ptr: *mut u8, len: usize) {
    unsafe { drop(Vec::from_raw_parts(ptr, 0, len.max(1))) }
}

/// Runs request `name` (UTF-8 at name_ptr) with the JSON at req_ptr; returns the answer's length, the answer is at
/// `wb_result()` until the next call.
#[no_mangle]
pub extern "C" fn wb_call(name_ptr: *const u8, name_len: usize, req_ptr: *const u8, req_len: usize) -> usize {
    let name = unsafe { std::str::from_utf8_unchecked(std::slice::from_raw_parts(name_ptr, name_len)) };
    let req_text = unsafe { std::str::from_utf8_unchecked(std::slice::from_raw_parts(req_ptr, req_len)) };
    let answer = match serde_json::from_str::<Value>(req_text) {
        Ok(req) => dispatch(name, &req).unwrap_or_else(|e| json!({"error": e})),
        Err(e) => json!({"error": format!("bad request: {}", e)}),
    };
    STATE.with(|s| {
        let mut s = s.borrow_mut();
        s.out = answer.to_string().into_bytes();
        s.out.len()
    })
}

#[no_mangle]
pub extern "C" fn wb_result() -> *const u8 {
    STATE.with(|s| s.borrow().out.as_ptr())
}

fn run_of(req: &Value) -> Result<Arc<runs::Run>, String> {
    let id = req["run"].as_u64().ok_or("which run?")?;
    STATE.with(|s| s.borrow().runs.get(&id).cloned()).ok_or_else(|| format!("no run {}", id))
}

/// The name a modified unit's text is held under (the same rule as the desktop Lab's scratch file).
fn scratch_id(text: &str) -> String {
    use std::hash::{Hash, Hasher};
    let mut h = std::collections::hash_map::DefaultHasher::new();
    text.hash(&mut h);
    format!("_modified/{:016x}.mtf", h.finish())
}

/// A setup made into a plan, from the files held (and the texts of its modified units, held first).
fn plan_of(setup: &Value) -> Result<runs::Plan, String> {
    STATE.with(|s| {
        let mut s = s.borrow_mut();
        let m = s.paths.memory.as_mut().unwrap();
        for t in setup["teams"].as_array().into_iter().flatten() {
            for u in t["units"].as_array().into_iter().flatten() {
                if let Some(text) = u["mtf_text"].as_str() {
                    m.files.insert(scratch_id(text), text.to_string());
                }
            }
        }
    });
    // shared borrows only: the catalog's `ensure` looks at the same files
    STATE.with(|s| runs::scenario_of(setup, &catalog::Catalog, &s.borrow().paths))
}

fn dispatch(name: &str, req: &Value) -> Result<Value, String> {
    match name {
        "files" => STATE.with(|s| {
            let mut s = s.borrow_mut();
            let m = s.paths.memory.as_mut().unwrap();
            if let Some(d) = req["defaults"].as_str() {
                m.defaults = d.to_string();
            }
            for (k, v) in req["files"].as_object().into_iter().flatten() {
                m.files.insert(k.clone(), v.as_str().unwrap_or("").to_string());
            }
            Ok(json!({"files": m.files.len()}))
        }),
        "run" => {
            let plan = plan_of(&req["setup"])?;
            STATE.with(|s| {
                let mut s = s.borrow_mut();
                let id = s.next_run;
                s.next_run += 1;
                s.runs.insert(id, runs::Run::external(id, req["setup"].clone(), plan));
                Ok(json!({"run": id}))
            })
        }
        "push" => {
            let run = run_of(req)?;
            run.add(req["lines"].as_array().cloned().unwrap_or_default(), req["crashed"].as_array().cloned().unwrap_or_default());
            if req["finished"] == true {
                run.finish(req["seconds"].as_f64());
            }
            Ok(run.progress())
        }
        "progress" => Ok(run_of(req)?.progress()),
        "results" => Ok(run_of(req)?.results(req)),
        "cancel" => {
            let run = run_of(req)?;
            run.cancel.store(true, std::sync::atomic::Ordering::Relaxed);
            Ok(run.progress())
        }
        "save_run" => {
            let run = run_of(req)?;
            Ok(run.export(serde_json::Map::new()))
        }
        "load_run" => {
            let f = &req["file"];
            if f["combatlab_run"] != 1 {
                return Err("this is not a Combat Lab run file".into());
            }
            let plan = plan_of(&f["setup"])?;
            STATE.with(|s| {
                let mut s = s.borrow_mut();
                let id = s.next_run;
                s.next_run += 1;
                let run = runs::Run::restore(id, f["setup"].clone(), plan, f["lines"].as_array().cloned().unwrap_or_default(), f["crashed"].as_array().cloned().unwrap_or_default(), f["seconds"].as_f64().unwrap_or(0.0));
                s.runs.insert(id, run);
                Ok(json!({"run": id, "setup": f["setup"]}))
            })
        }
        "prepare" => {
            let plan = plan_of(&req["setup"])?;
            let max_turns = plan.max_turns;
            let seed = req["setup"]["seed"].as_u64().unwrap_or(1);
            STATE.with(|s| s.borrow_mut().prepared = Some((plan, seed)));
            Ok(json!({"ok": true, "max_turns": max_turns}))
        }
        "play" => {
            let sim = req["sim"].as_u64().ok_or("which battle?")?;
            STATE.with(|s| {
                let s = s.borrow();
                let (plan, seed) = s.prepared.as_ref().ok_or("no batch prepared")?;
                let (crash, line) = runs::play_one(plan, *seed, sim);
                Ok(json!({"crash": crash, "line": line}))
            })
        }
        // the unit editor's calls (the desktop Lab's `unit_eval` and `equipment_list`; unit text comes from the page's data block)
        "unit_eval" => {
            let text = req["text"].as_str().ok_or("no unit text")?;
            let defaults: Value = STATE.with(|s| serde_json::from_str(&s.borrow().paths.memory.as_ref().unwrap().defaults)).map_err(|e| e.to_string())?;
            let cfg = btsim_core::config::Config::from_json(&defaults);
            let db = btsim_core::equipment::EquipmentDb::shared();
            Ok(json!({"unit": describe::describe_unit(db, &cfg, "(edited)", "custom", text), "structure": describe::unit_structure(db, text), "bins": describe::unit_bins(db, &cfg, text)}))
        }
        "equipment_list" => Ok(json!({"equipment": describe::equipment_list(btsim_core::equipment::EquipmentDb::shared())})),
        "history" => history(req),
        "page" => Ok(json!({"html": btsim_core::history::page(&req["record"])})),
        // the seed battle `sim` of a batch on run seed `run_seed` is played on (for a crash the worker could not report)
        "seed" => Ok(json!({"seed": btsim_core::dice::PcgDice::battle_seed(req["run_seed"].as_u64().unwrap_or(1), req["sim"].as_u64().unwrap_or(1)).to_string()})),
        _ => Err(format!("unknown request '{}'", name)),
    }
}

/// One battle's full history with the setup's team colours: battle `sim` of the setup's batch (seed from the setup's
/// run seed), or the setup on an explicit `seed`.
fn history(req: &Value) -> Result<Value, String> {
    let plan = plan_of(&req["setup"])?;
    let sim = req["sim"].as_u64().unwrap_or(1);
    let seed = match req["seed"].as_u64().or_else(|| req["seed"].as_str().and_then(|s| s.parse().ok())) {
        Some(s) => s,
        None => btsim_core::dice::PcgDice::battle_seed(req["setup"]["seed"].as_u64().unwrap_or(1), sim),
    };
    let mut record = plan.scenario_for(sim, seed).0.run_history(sim, seed).1;
    let colours: serde_json::Map<String, Value> = req["setup"]["teams"].as_array().into_iter().flatten()
        .filter_map(|t| Some((t["name"].as_str()?.to_string(), json!(t["colour"].as_str()?))))
        .collect();
    record["colours"] = Value::Object(colours);
    Ok(record)
}
