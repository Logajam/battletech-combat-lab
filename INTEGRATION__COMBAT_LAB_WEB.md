# Combat Lab in the browser (session 26, 2026-11-14)

Daniel: "What if Combat Lab could be run in a browser from a webpage? Front load it so that the user's computer is the
one actually doing the work." Then: "Lets build it, see if it works. Maybe prune out all the maps that aren't standard
16x17 as a small mercy. Plus any other simplifications that would make it lighter."

**Status: built, and plays exactly the battles the desktop Lab plays** (`tests/check_web_lab.py`: four setups, every
battle's seed, winner, turns, damage and causes of death identical, in headless Chromium).

## How it works

```
 page (lab.js, unchanged pages)        window.LAB_WASM.api(name, body)       <- the same names as the desktop's /api/<name>
   engine.js                            |
     coordinator: one engine instance on the page; keeps the batch's statistics (the desktop's runs.rs, shared)
     workers x CPU cores: one engine instance each (worker.js); each plays battles `play(sim)` and sends the line back
   static files: combatlab.wasm, catalog.json, data.pack.gz, defaults.json, the pages
```

* `engine/wasm` (crate `combatlab_wasm`, empty on the desktop): the engine (`btsim_core`) plus `engine/lab/src/runs.rs`
  (included by path, so the statistics, filters and unit stats are the very code the desktop runs) as one `.wasm`.
  No wasm-bindgen: a handful of plain exports (`wb_call(name, json)`), and `engine/wasm/web/wasmio.js` is the whole glue.
* The module has no disk, threads or clock: files come in as memory (`SetupPaths::memory`, `MemoryFiles` in
  `core/src/scenario.rs`; the desktop path is unchanged), the clock is the page's (`host_now_ms`), parallelism is Web
  Workers. A battle that crashes the engine stops its worker instance (a WebAssembly panic cannot be caught); the worker
  records the crash with its seed, starts a fresh instance and goes on. (That crash path is written but not yet exercised: nothing known crashes the engine to try it on.)
* Same seeds, same battles: battle n of a batch is played on `PcgDice::battle_seed(seed, n)` wherever it runs.

## Build and test

```
python tools/build_web_lab.py         # -> web_lab/ (static files; any web host, or: python -m http.server -d web_lab)
python tests/check_web_lab.py         # desktop v browser, battle for battle (needs node + Playwright; skips without)
```
`rustup target add wasm32-unknown-unknown` once. `engine/.cargo/config.toml` lets the linker leave the page's functions
as imports.

## What was pruned (lighter)

| | desktop data | web |
|---|---|---|
| boards | 356 | 200: only 16x17 sheets (Daniel's call) |
| unit files | 18.6 MB, 4,252 units | 11.9 MB after dropping fluff lines the engine never reads (history, overview, capabilities, deployment, manufacturers...), 4,229 units (the 23 the engine cannot play are left out); all units and boards in one gzip block, **0.84 MB** |
| module | | 6.7 MB, 1.7 MB gzipped |
| first load | | about 3.5 MB over the wire |
Not in the browser build: the MegaMek bridge, `btsim --history` files, saving units into a folder. **Adding your own unit
file (drag and drop) is not built yet** (it needs `catalog::describe_unit`, which is in the desktop-only file).

## Measured (4-core sandbox, 20 battles of 2 v 2 Gladiator)

Desktop 5.1 s, browser 9.4 s: about 1.8x slower, as WebAssembly usually is. A 12-core laptop would be well ahead of
this machine either way. The page uses `navigator.hardwareConcurrency` workers (at most 16); each holds its own copy of
the engine's tables (a few tens of MB), so a phone should use fewer (the setup's `threads` field).

## Publishing (Daniel, 2026-11-14: "accessible as a public website"; alpha)

`python tools/publish_public.py --push` first (the code, as always), then `python tools/publish_web_lab.py --push`: builds
`web_lab/` and force-pushes it as the only commit of the public repository's `gh-pages` branch (generated files only; the
module changes with every build, so no history is kept). GitHub Pages serves it at
https://logajam.github.io/battletech-combat-lab/ after ONE setting by the owner: Settings > Pages > Deploy from a branch >
`gh-pages` / root (Claude's access cannot change it). The page says "ALPHA" in the title bar, in a banner and in About.

## Open

* Add-unit by file in the browser; progress is polled (every 200 ms flush) rather than pushed.
* Hosting: the page is plain static files (GitHub Pages works). Publishing it publicly goes through
  `tools/publish_public.py` and is Daniel's call (PROJECT_MAP E6); MegaMek-derived unit data keeps its CC BY-NC-SA headers.
* `tests/check_web_lab.py` is not in `run_checks.py` (needs a browser); run it after any change to `engine/wasm`,
  `engine/lab/src/runs.rs` or `Scenario::from_settings`.
