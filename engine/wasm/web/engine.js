// COMBAT LAB IN THE BROWSER, the page's end. lab.js asks every question of `window.LAB_WASM.api(name, body)` (the same
// names and answers as the desktop Lab's server, engine/lab/src/main.rs); this file answers them without a server:
//   - the unit and board lists and files are static files (catalog.json, data.pack.gz), loaded once;
//   - the batch's statistics are kept by one instance of the engine module on this page (its `push` / `results`);
//   - the battles are played by workers, one instance of the module each, as many as this computer has cores.
// So the visitor's own computer does all the work; the host only serves files.
"use strict";

(function () {
  const dec = new TextDecoder();
  const cores = Math.max(1, Math.min(navigator.hardwareConcurrency || 2, 16));
  let loading = null;                  // promise of {module, catalog, defaults, pack, coord}
  let S = null;                        // what it resolved to

  const status = (t) => { const el = document.getElementById("status"); if (el) el.textContent = t; };

  // every file's place in the unpacked data block: name -> [offset, length]
  function indexPack(buf) {
    const view = new DataView(buf), bytes = new Uint8Array(buf), index = new Map();
    let at = 0;
    while (at + 4 <= buf.byteLength) {
      const nl = view.getUint32(at, true); at += 4;
      const name = dec.decode(bytes.subarray(at, at + nl)); at += nl;
      const cl = view.getUint32(at, true); at += 4;
      index.set(name, [at, cl]); at += cl;
    }
    return { bytes, index, text: (name) => { const e = index.get(name); return e ? dec.decode(bytes.subarray(e[0], e[0] + e[1])) : null; } };
  }

  // the data block: data.pack.gz, or data.pack.b64.txt (the same bytes as base64) for a host that will not serve .gz files
  async function loadPack(get) {
    let gz;
    try {
      gz = (await get("data.pack.gz")).body;
    } catch (e) {
      const b64 = await (await get("data.pack.b64.txt")).text();
      gz = new Response(Uint8Array.from(atob(b64.trim()), (c) => c.charCodeAt(0))).body;
    }
    // a host may already have undone the compression on the way (a Content-Encoding header): only gzip data (1f 8b) is decompressed
    const buf = await new Response(gz).arrayBuffer();
    const head = new Uint8Array(buf, 0, 2);
    if (head[0] !== 0x1f || head[1] !== 0x8b) return buf;
    return new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer();
  }

  function init() {
    if (!loading) loading = (async () => {
      status("Loading the engine and the unit list...");
      const get = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(u + ": " + r.status); return r; });
      const [module, catalog, defaults, packBuf] = await Promise.all([
        get("combatlab.wasm").then((r) => WebAssembly.compileStreaming ? WebAssembly.compileStreaming(r) : r.arrayBuffer().then(WebAssembly.compile)),
        get("catalog.json").then((r) => r.json()),
        get("defaults.json").then((r) => r.text()),
        loadPack(get),
      ]);
      const pack = indexPack(packBuf);
      const coord = await makeEngine(module);
      coord.call("files", { defaults });
      S = { module, catalog, defaults, pack, coord };
      return S;
    })();
    return loading;
  }

  // ------------------------------------------------------------ workers
  class Player {
    constructor() {
      this.worker = new Worker("worker.js");
      this.n = 0; this.waiting = new Map();
      this.worker.onmessage = (e) => { const w = this.waiting.get(e.data.id); this.waiting.delete(e.data.id); if (w) w(e.data); };
    }
    ask(cmd, body, transfer) {
      return new Promise((resolve) => { const id = ++this.n; this.waiting.set(id, resolve); this.worker.postMessage({ id, cmd, ...body }, transfer || []); });
    }
    static async start() { const p = new Player(); await p.ask("init", { module: S.module }); return p; }
  }
  const players = [];
  async function getPlayers(n) {
    while (players.length < n) players.push(await Player.start());
    return players.slice(0, n);
  }
  let historian = null;   // one more worker, for replays
  const getHistorian = async () => historian || (historian = await Player.start());

  // ------------------------------------------------------------ what a setup needs
  function idsOf(setup) {
    const ids = new Set();
    for (const t of setup.teams || []) for (const u of t.units || []) if (u.unit) ids.add(u.unit);
    const b = setup.board;
    if (typeof b === "string") ids.add(b);
    else if (b) { (b.grid || []).flat().forEach((x) => ids.add(x)); (b.playlist || []).forEach((x) => ids.add(x)); }
    return ids;
  }
  function filesFor(setup) {
    const files = {};
    for (const id of idsOf(setup)) { const t = S.pack.text(id); if (t != null) files[id] = t; }
    return files;
  }

  // ------------------------------------------------------------ batches
  const setups = new Map();    // run id -> setup (for replays)
  let job = null;              // the batch being played

  async function runBatch(runId, setup, files) {
    const total = Math.max(1, Math.min(100000, setup.battles || 20));
    const n = Math.min(setup.threads > 0 ? setup.threads : cores, cores, total);
    const mine = { runId, next: 1, cancelled: false, buf: { lines: [], crashed: [] }, t0: performance.now() };
    job = mine;
    const flush = (finished) => {
      const { lines, crashed } = mine.buf;
      if (!lines.length && !crashed.length && !finished) return;
      mine.buf = { lines: [], crashed: [] };
      S.coord.call("push", { run: runId, lines, crashed, finished, seconds: finished ? (performance.now() - mine.t0) / 1000 : undefined });
    };
    const timer = setInterval(() => flush(false), 200);
    try {
      const ws = await getPlayers(n);
      await Promise.all(ws.map((w) => w.ask("prepare", { defaults: S.defaults, files, setup })));
      await Promise.all(ws.map(async (w) => {
        while (!mine.cancelled && mine.next <= total) {
          const sim = mine.next++;
          const r = await w.ask("play", { sim });
          if (r.error) { mine.buf.crashed.push({ sim, seed: "", crashed: r.error }); continue; }
          (r.crash ? mine.buf.crashed : mine.buf.lines).push(r.line);
        }
      }));
    } finally {
      clearInterval(timer);
      flush(true);
      if (job === mine) job = null;
    }
  }

  // seconds a batch would take, from a few test battles played side by side now
  async function estimate(setup) {
    const files = filesFor(setup);
    S.coord.call("files", { files });
    const check = S.coord.call("run", { setup });          // the setup's mistakes, in words (the run is not used)
    if (check.error) return check;
    S.coord.call("cancel", { run: check.run });
    const total = Math.max(1, setup.battles || 20);
    const threads = Math.min(setup.threads > 0 ? setup.threads : cores, cores);
    const pilots = Math.max(1, Math.min(threads, 4));
    const ws = await getPlayers(pilots);
    const started = performance.now();
    const times = await Promise.all(ws.map(async (w, i) => {
      await w.ask("prepare", { defaults: S.defaults, files, setup: { ...setup, seed: 0xC0FFEE } });
      const r = await w.ask("play", { sim: 1000 + i });
      return r.line && r.line.seconds != null ? r.line.seconds : 0;
    }));
    const per = times.reduce((a, b) => a + b, 0) / times.length;
    return { seconds: per * Math.ceil(total / threads), per_battle: per, threads, pilot_battles: pilots, pilot_seconds: (performance.now() - started) / 1000 };
  }

  // ------------------------------------------------------------ replays
  const replays = new Map();
  async function historyOf(req) {
    const key = JSON.stringify(req);
    if (replays.has(key)) return replays.get(key);
    let setup;
    if (req.run != null) { setup = setups.get(req.run); if (!setup) return { error: "no such run" }; }
    else setup = req.setup;
    const h = await getHistorian();
    const record = await h.ask("history", { defaults: S.defaults, files: filesFor(setup), request: { setup, sim: req.sim || 1, seed: req.seed } });
    replays.clear();
    if (!record.error) replays.set(key, record);
    return record;
  }

  // ------------------------------------------------------------ the api
  async function api(name, body) {
    await init();
    switch (name) {
      case "info": return { ...S.catalog.info, cores, project: "", missing_data: false };
      case "list_units": return { units: S.catalog.units };
      case "list_boards": return { boards: S.catalog.boards };
      case "board": { const text = S.pack.text(body.id); return text == null ? { error: "no board " + body.id } : { id: body.id, text }; }
      case "estimate": return estimate(body.setup);
      case "run": {
        const files = filesFor(body.setup);
        S.coord.call("files", { files });
        const r = S.coord.call("run", { setup: body.setup });
        if (r.error) return r;
        setups.set(r.run, body.setup);
        runBatch(r.run, body.setup, files);     // plays on in the workers; the page polls `progress`
        return r;
      }
      case "cancel": if (job && job.runId === body.run) job.cancelled = true; return S.coord.call("cancel", body);
      case "progress": case "results": return S.coord.call(name, body);
      case "save_run": return S.coord.call("save_run", body);
      case "load_run": {
        const f = body.file;
        if (f && f.setup) S.coord.call("files", { files: filesFor(f.setup) });
        const r = S.coord.call("load_run", body);
        if (!r.error) setups.set(r.run, f.setup);
        return r;
      }
      case "history": return historyOf(body);
      case "add_unit": return { error: "Adding your own unit files is not available in the browser version yet." };
      case "unit_text": case "unit_eval": case "equipment_list": return { error: "The unit sheet and editor are not in the browser version yet (they need the Combat Lab program)." };
      default: return { error: "unknown request '" + name + "'" };
    }
  }

  async function replayHtml(req) {
    await init();
    const rec = await historyOf(req);
    if (rec.error) return rec;
    const h = await getHistorian();
    return (await h.ask("page", { request: { record: rec } })).html;
  }

  window.LAB_WASM = { api, replayHtml };
})();
