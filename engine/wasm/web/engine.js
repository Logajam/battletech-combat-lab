// COMBAT LAB IN THE BROWSER, the page's end. lab.js asks every question of `window.LAB_WASM.api(name, body)` (the same
// names and answers as the desktop Lab's server, engine/lab/src/main.rs); this file answers them without a server:
//   - the unit and board lists and files are static files (catalog.json, data.pack.gz), loaded once;
//   - the batch's statistics are kept by one instance of the engine module on this page (its `push` / `results`);
//   - the battles are played by workers, one instance of the module each: by default every core but a quarter of them
//     (`autoThreads`), so the visitor's other programs keep room to run.
// So the visitor's own computer does all the work; the host only serves files.
"use strict";

(function () {
  const dec = new TextDecoder();
  const cores = Math.max(1, Math.min(navigator.hardwareConcurrency || 2, 16));
  // How many workers play at once. 0 (the default) = automatic: every core but a quarter of them, at least one left free
  // (Daniel, 2026-11-17: another program crashed when a run took every cycle; a web page cannot lower its own priority,
  // so it leaves cores free instead). A number typed in is used as it is, up to the core count. Same rule as the desktop
  // Lab's `runs::threads_for`.
  // "Full power" (Daniel, 2026-11-17) = every core, whatever was typed.
  const autoThreads = (asked, full) => (full ? cores : asked > 0 ? Math.min(asked, cores) : Math.max(1, cores - Math.max(1, Math.floor(cores / 4))));
  let loading = null;                  // promise of {module, catalog, defaults, pack, coord}
  let S = null;                        // what it resolved to
  let equipmentList = null;            // the unit editor's equipment catalogue, asked of the module once

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
    // Cancel (Daniel, 2026-11-17: "a way to stop a run in the middle"): a battle inside the engine cannot be interrupted, so
    // the worker is ended on the spot and every question still waiting on it answers {stopped: true}; a new one is started
    // for the next run.
    stop() { this.worker.terminate(); for (const w of this.waiting.values()) w({ stopped: true }); this.waiting.clear(); }
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
    const n = Math.min(autoThreads(setup.threads, setup.full_power), total);
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
      mine.players = ws;
      await Promise.all(ws.map((w) => w.ask("prepare", { defaults: S.defaults, files, setup })));
      await Promise.all(ws.map(async (w) => {
        while (!mine.cancelled && mine.next <= total) {
          const sim = mine.next++;
          const r = await w.ask("play", { sim });
          if (r.stopped || mine.cancelled) break;      // cancelled: a battle cut off in the middle is not counted
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
    const threads = autoThreads(setup.threads, setup.full_power);
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

  // ------------------------------------------------------------ BattleROM: a battle with a person in it
  // One Web Worker plays the battle (playworker.js) and sleeps while the person thinks; this side keeps what the desktop
  // Lab's server keeps (engine/core/src/play_session.rs `Game`): the question waiting, its number, the end, and the query
  // being answered, and answers play_poll / play_answer / play_query in the same words. The shared buffer needs the
  // page to be cross-origin isolated (coi.js), so without it Play says so.
  const games = new Map();
  const humanTeams = (setup) => (setup.teams || []).filter((t) => t.bot === "human").map((t) => t.name);
  const asBots = (setup) => ({ ...setup, teams: (setup.teams || []).map((t) => (t.bot === "human" ? { ...t, bot: "gladiator" } : t)) });

  class PlayGame {
    constructor(id, setup, seed) {
      this.id = id; this.seq = 0; this.pending = null; this.end = null; this.failed = null; this.waiters = []; this.outbox = []; this.qwait = null;
      this.sab = new SharedArrayBuffer(8 + (1 << 20));
      this.ctl = new Int32Array(this.sab, 0, 2); this.data = new Uint8Array(this.sab, 8);
      this.worker = new Worker("playworker.js");
      this.worker.onmessage = (e) => {
        const m = e.data;
        if (m.ev === "post") { this.seq++; this.pending = m.request; }
        else if (m.ev === "qreply") { if (this.qwait) { this.qwait(m.reply); this.qwait = null; } }
        else if (m.ev === "done") this.end = m.end;
        else if (m.ev === "failed") this.failed = m.error;
        const w = this.waiters; this.waiters = []; w.forEach((f) => f());
      };
      this.worker.postMessage({ cmd: "start", module: S.module, defaults: S.defaults, files: filesFor(setup), setup, seed, sab: this.sab });
    }
    // a message for the sleeping worker; one at a time: the next goes in once the worker has taken the last
    send(msg) { this.outbox.push(msg); this.pump(); }
    pump() {
      if (!this.outbox.length) return;
      if (Atomics.load(this.ctl, 0) !== 0) { setTimeout(() => this.pump(), 5); return; }
      const bytes = new TextEncoder().encode(JSON.stringify(this.outbox.shift()));
      this.data.set(bytes); Atomics.store(this.ctl, 1, bytes.length); Atomics.store(this.ctl, 0, 1); Atomics.notify(this.ctl, 0);
      if (this.outbox.length) setTimeout(() => this.pump(), 5);
    }
    state() {
      if (this.failed) return { state: "failed", error: this.failed };
      if (this.end) return { state: "done", end: this.end };
      if (this.pending) return { state: "pending", seq: this.seq, request: this.pending };
      return null;
    }
    poll(waitMs) {
      const now = this.state();
      if (now) return Promise.resolve(now);
      return new Promise((resolve) => {
        const t = setTimeout(() => { this.waiters = this.waiters.filter((f) => f !== wake); resolve({ state: "waiting" }); }, waitMs);
        const wake = () => { clearTimeout(t); resolve(this.state() || { state: "waiting" }); };
        this.waiters.push(wake);
      });
    }
    answer(seq, answer) {
      if (!this.pending || this.seq !== seq) return { error: "that question is not the one waiting" };
      this.pending = null;
      this.send({ k: "a", v: answer });
      return { ok: true };
    }
    query(q) {
      if (!this.pending || this.qwait) return Promise.resolve({ error: "no question is waiting" });
      return new Promise((resolve) => {
        const t = setTimeout(() => { this.qwait = null; resolve({ error: "the engine did not answer" }); }, 60000);
        this.qwait = (r) => { clearTimeout(t); resolve(r); };
        this.send({ k: "q", v: q });
      });
    }
  }

  // a batch cannot be played by a person (the desktop Lab's `no_human`)
  const noHuman = (setup) => {
    const t = (setup.teams || []).find((x) => x.bot === "human");
    return t ? { error: `Team ${t.name || "?"} is set to Human: a person plays it, so it cannot be run as a simulation. Use Play, or set the team to a bot.` } : null;
  };

  // the setup's mistakes, in words (the same check a batch's run makes), with the Human teams as bots
  function playCheck(setup) {
    if (!humanTeams(setup).length) return { error: "No team is set to Human. Set one team's bot to Human, then press Play." };
    const plain = asBots(setup);
    S.coord.call("files", { files: filesFor(plain) });
    const r = S.coord.call("run", { setup: plain });
    if (r.error) return r;
    S.coord.call("cancel", { run: r.run });
    return { ok: true };
  }

  function playStart(setup, seedAsked) {
    if (!window.crossOriginIsolated || typeof SharedArrayBuffer === "undefined") {
      return { error: "Playing needs a browser that allows this site's service worker (it gives the page the shared memory the battle waits in). Reload the page once; if this stays, try another browser, or use the desktop Lab." };
    }
    const bad = playCheck(setup);
    if (bad.error) return bad;
    const seed = (seedAsked || setup.seed || 0) || (Math.floor(Math.random() * 0xFFFFFFFF) + 1);
    const id = games.size + 1;
    games.set(id, new PlayGame(id, setup, seed));
    const colours = {};
    for (const t of setup.teams || []) if (t.name && t.colour) colours[t.name] = t.colour;
    return { game: id, seed, colours };
  }

  // ------------------------------------------------------------ the api
  async function api(name, body) {
    await init();
    switch (name) {
      case "info": return { ...S.catalog.info, cores, project: "", missing_data: false };
      case "list_units": return { units: S.catalog.units };
      case "list_boards": return { boards: S.catalog.boards };
      case "board": { const text = S.pack.text(body.id); return text == null ? { error: "no board " + body.id } : { id: body.id, text }; }
      case "estimate": return noHuman(body.setup) || estimate(body.setup);
      case "run": {
        if (noHuman(body.setup)) return noHuman(body.setup);
        const files = filesFor(body.setup);
        S.coord.call("files", { files });
        const r = S.coord.call("run", { setup: body.setup });
        if (r.error) return r;
        setups.set(r.run, body.setup);
        runBatch(r.run, body.setup, files);     // plays on in the workers; the page polls `progress`
        return r;
      }
      case "cancel": {
        if (job && job.runId === body.run) {
          job.cancelled = true;
          for (const w of job.players || []) { w.stop(); const i = players.indexOf(w); if (i >= 0) players.splice(i, 1); }
        }
        return S.coord.call("cancel", body);
      }
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
      case "play_check": return playCheck(body.setup);
      case "play_start": return playStart(body.setup, body.seed);
      case "play_poll": case "play_answer": case "play_query": {
        const g = games.get(body.game);
        if (!g) return { error: "no such game (the page was reloaded?)" };
        if (name === "play_poll") return g.poll(Math.min(body.wait_ms || 25000, 60000));
        if (name === "play_answer") return g.answer(body.seq, body.answer);
        return g.query(body.query);
      }
      case "add_unit": return { error: "Adding your own unit files is not available in the browser version yet." };
      // the unit sheet and editor: the file text comes from the data block, the engine's reading and the equipment list from the module
      case "unit_text": { const text = S.pack.text(body.id); return text == null ? { error: "no unit " + body.id } : { id: body.id, text }; }
      case "unit_eval": return (await getHistorian()).ask("eval", { defaults: S.defaults, text: body.text });
      case "equipment_list": return equipmentList || (equipmentList = S.coord.call("equipment_list", {}));
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
