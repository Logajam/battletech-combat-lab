// Combat Lab pages (INTEGRATION__COMBAT_LAB_SPECS.md CL4 and CL5's first step): Units, Map, Options, Results, Replay.
// Everything the engine does is asked of the Lab server (engine/lab/src/main.rs) as JSON; this script only shows and
// collects. With `window.LAB_DEMO` set (tools/make_lab_demo.py builds that page) the answers are canned ones recorded
// from a real Lab run, so the pages can be looked at without the program.
"use strict";

const DEMO = window.LAB_DEMO || null;
const $ = (id) => document.getElementById(id);
const COLOURS = [["Red", "#c00000"], ["Blue", "#0000c0"], ["Green", "#007000"], ["Yellow", "#b89000"], ["Purple", "#800080"], ["Orange", "#d05800"], ["Teal", "#007878"], ["Grey", "#606060"]];
const STORE = "combatlab.setup.v1";

const lab = {
  info: null, units: [], boards: [], byId: new Map(),
  teams: [], board: null, run: null, results: null, poll: null,
};

// ---------------------------------------------------------------- talking to the server
async function api(name, body) {
  if (DEMO) return demoApi(name, body || {});
  const r = await fetch("api/" + name, { method: "POST", body: JSON.stringify(body || {}) });
  return r.json();
}

function setStatus(text, right) {
  $("status").textContent = text;
  if (right !== undefined) $("status-right").textContent = right;
}

const fmtSecs = (s) => s < 60 ? `${s.toFixed(1)} s` : s < 3600 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : `${(s / 3600).toFixed(1)} h`;
const pct = (x) => `${(100 * x).toFixed(0)}%`;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const colourOf = (name) => (lab.teams.find((t) => t.name === name) || {}).colour || "#808080";

// ---------------------------------------------------------------- the setup (what Run sends)
function setup() {
  return {
    teams: lab.teams.map((t) => ({ name: t.name, bot: t.bot, units: t.units.map((u) => ({ unit: u.id, gunnery: u.gunnery, piloting: u.piloting })) })),
    board: lab.board,
    battles: +$("battles").value || 20,
    seed: +$("seed").value || 0,
    threads: +$("threads").value || 0,
    max_turns: +$("max-turns").value || 100,
  };
}

function save() {
  try { localStorage.setItem(STORE, JSON.stringify({ teams: lab.teams, board: lab.board, battles: $("battles").value, seed: $("seed").value, threads: $("threads").value, maxTurns: $("max-turns").value })); } catch (e) { /* storage off: nothing kept */ }
  $("estimate").textContent = "Press Estimate";
}

function restore() {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(STORE) || "null"); } catch (e) { saved = null; }
  if (DEMO) saved = null;     // the demo always opens on the setup its results came from
  const unit = (id, g = 4, p = 5) => { const u = lab.byId.get(id); return u && { id, name: u.name, tons: u.tons, bv: u.bv, gunnery: g, piloting: p }; };
  if (saved && saved.teams && saved.teams.length >= 2) {
    lab.teams = saved.teams.map((t) => ({ ...t, units: t.units.map((u) => unit(u.id, u.gunnery, u.piloting)).filter(Boolean) }));
    lab.board = saved.board;
    $("battles").value = saved.battles || 20; $("seed").value = saved.seed || 1; $("threads").value = saved.threads || 0; $("max-turns").value = saved.maxTurns || 100;
  } else {
    const start = DEMO ? DEMO.setup : { teams: [{ name: "Red", bot: "gladiator", units: [{ unit: "Atlas AS7-K.mtf" }, { unit: "Griffin GRF-1N.mtf" }] },
      { name: "Blue", bot: "gladiator", units: [{ unit: "Awesome AWS-8Q.mtf" }, { unit: "Hunchback HBK-4G.mtf" }] }], board: lab.info.default_board, battles: 20, seed: 1 };
    lab.teams = start.teams.map((t, i) => ({ name: t.name, colour: COLOURS[i][1], bot: t.bot, units: t.units.map((u) => unit(u.unit, u.gunnery ?? 4, u.piloting ?? 5)).filter(Boolean) }));
    lab.board = start.board;
    $("battles").value = start.battles; $("seed").value = start.seed;
  }
  if (!lab.boards.some((b) => b.id === lab.board)) lab.board = lab.info.default_board;
  $("team-count").value = lab.teams.length;
}

// ---------------------------------------------------------------- UNITS page
function drawTeams() {
  const box = $("teams");
  box.innerHTML = "";
  lab.teams.forEach((t, ti) => box.appendChild(teamPanel(t, ti)));
}

function teamPanel(t, ti) {
  const el = document.createElement("fieldset");
  el.className = "team raised";
  const bots = lab.info.bots.map((b) => `<option value="${b}"${b === t.bot ? " selected" : ""}>${b[0].toUpperCase() + b.slice(1)}</option>`).join("");
  const colours = COLOURS.map(([n, c]) => `<option value="${c}"${c === t.colour ? " selected" : ""}>${n}</option>`).join("");
  const tons = t.units.reduce((s, u) => s + (u.tons || 0), 0);
  const bv = t.units.reduce((s, u) => s + (u.bv || 0), 0);
  el.innerHTML = `
    <legend>Team ${ti + 1}</legend>
    <div class="team-head">
      <span class="swatch" style="background:${t.colour}"></span>
      <label for="tname-${ti}">Name <input type="text" id="tname-${ti}" value="${esc(t.name)}" maxlength="24"></label>
      <label for="tcol-${ti}">Colour <select id="tcol-${ti}">${colours}</select></label>
      <label for="tbot-${ti}">Bot <select id="tbot-${ti}">${bots}</select></label>
    </div>
    <div class="list sunken"><table>
      <thead><tr><th>Unit</th><th class="num">Tons</th><th class="num">BV</th><th title="Gunnery skill">G</th><th title="Piloting skill">P</th><th></th></tr></thead>
      <tbody>${t.units.length ? t.units.map((u, ui) => `<tr>
        <td class="name">${esc(u.name)}</td><td class="num">${u.tons ?? ""}</td><td class="num">${u.bv ?? ""}</td>
        <td><input type="number" min="0" max="8" value="${u.gunnery}" id="g-${ti}-${ui}" aria-label="Gunnery"></td>
        <td><input type="number" min="0" max="8" value="${u.piloting}" id="p-${ti}-${ui}" aria-label="Piloting"></td>
        <td><button class="btn small" data-remove="${ui}" title="Remove">&times;</button></td></tr>`).join("")
        : `<tr class="empty"><td colspan="6">No units. Search below, or drop a .mtf file here.</td></tr>`}</tbody>
    </table></div>
    <div class="totals"><span>${t.units.length} unit${t.units.length === 1 ? "" : "s"}</span><span>${tons} tons</span><span>BV ${bv}</span></div>
    <div class="adder">
      <input type="search" id="find-${ti}" placeholder="Add a unit: type a name" autocomplete="off">
      <button class="btn" id="file-${ti}">File&hellip;</button>
      <input type="file" id="fileinput-${ti}" accept=".mtf" multiple hidden>
      <div class="hits sunken" id="hits-${ti}" hidden></div>
    </div>`;
  const redraw = () => { save(); drawTeams(); };
  el.querySelector(`#tname-${ti}`).addEventListener("change", (e) => {
    const name = e.target.value.trim();
    if (name && !lab.teams.some((o, oi) => oi !== ti && o.name === name)) t.name = name;
    redraw();
  });
  el.querySelector(`#tcol-${ti}`).addEventListener("change", (e) => {
    const old = COLOURS.find(([, c]) => c === t.colour);
    const now = COLOURS.find(([, c]) => c === e.target.value);
    if (old && t.name === old[0] && !lab.teams.some((o) => o.name === now[0])) t.name = now[0];
    t.colour = e.target.value;
    redraw();
  });
  el.querySelector(`#tbot-${ti}`).addEventListener("change", (e) => { t.bot = e.target.value; save(); });
  el.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", () => { t.units.splice(+b.dataset.remove, 1); redraw(); }));
  t.units.forEach((u, ui) => {
    el.querySelector(`#g-${ti}-${ui}`).addEventListener("change", (e) => { u.gunnery = Math.max(0, Math.min(8, +e.target.value)); save(); });
    el.querySelector(`#p-${ti}-${ui}`).addEventListener("change", (e) => { u.piloting = Math.max(0, Math.min(8, +e.target.value)); save(); });
  });
  wireSearch(el, t, ti);
  // a .mtf file dropped on the panel (or picked with File...) is copied into the project and added
  const files = async (list) => {
    for (const f of list) {
      if (!f.name.toLowerCase().endsWith(".mtf")) { setStatus(`${f.name}: only .mtf unit files can be added`); continue; }
      const r = await api("add_unit", { file: f.name, text: await f.text() });
      if (r.error) { setStatus(`${f.name}: ${r.error}`); continue; }
      if (!lab.byId.has(r.unit.id)) { lab.units.push(r.unit); lab.byId.set(r.unit.id, r.unit); }
      t.units.push({ id: r.unit.id, name: r.unit.name, tons: r.unit.tons, bv: r.unit.bv, gunnery: 4, piloting: 5 });
      setStatus(r.copied ? `${r.unit.name} copied into the project's unit folder and added` : `${r.unit.name} added (already in the project)`);
    }
    redraw();
  };
  el.querySelector(`#file-${ti}`).addEventListener("click", () => el.querySelector(`#fileinput-${ti}`).click());
  el.querySelector(`#fileinput-${ti}`).addEventListener("change", (e) => files(e.target.files));
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("drop"); });
  el.addEventListener("dragleave", () => el.classList.remove("drop"));
  el.addEventListener("drop", (e) => { e.preventDefault(); el.classList.remove("drop"); files(e.dataTransfer.files); });
  return el;
}

function wireSearch(el, t, ti) {
  const input = el.querySelector(`#find-${ti}`);
  const hits = el.querySelector(`#hits-${ti}`);
  let shown = [];
  const add = (u) => {
    t.units.push({ id: u.id, name: u.name, tons: u.tons, bv: u.bv, gunnery: 4, piloting: 5 });
    save(); drawTeams();
    const again = $(`find-${ti}`); if (again) again.focus();
  };
  input.addEventListener("input", () => {
    const words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) { hits.hidden = true; return; }
    shown = lab.units.filter((u) => words.every((w) => u.name.toLowerCase().includes(w) || (u.source || "").toLowerCase().includes(w))).slice(0, 60);
    hits.innerHTML = shown.length ? shown.map((u, i) => `<div data-i="${i}" class="${u.ok ? "" : "bad"}" title="${esc(u.ok ? u.source : u.why)}"><span>${esc(u.name)}</span><span class="num">${u.tons ?? "?"} t</span><span class="num">${u.ok ? "BV " + u.bv : "can't play"}</span></div>`).join("")
      : `<div class="bad"><span>No unit matches</span></div>`;
    hits.hidden = false;
    hits.querySelectorAll("[data-i]").forEach((d) => d.addEventListener("mousedown", (e) => { e.preventDefault(); const u = shown[+d.dataset.i]; if (u.ok) add(u); }));
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { const u = shown.find((x) => x.ok); if (u && !hits.hidden) add(u); }
    if (e.key === "Escape") { hits.hidden = true; }
  });
  input.addEventListener("blur", () => setTimeout(() => { hits.hidden = true; }, 150));
}

function setTeamCount(n) {
  n = Math.max(2, Math.min(6, n));
  while (lab.teams.length < n) {
    const free = COLOURS.find(([name]) => !lab.teams.some((t) => t.name === name || t.colour === COLOURS.find((c) => c[0] === name)[1]));
    lab.teams.push({ name: free[0], colour: free[1], bot: "gladiator", units: [] });
  }
  lab.teams.length = n;
  $("team-count").value = n;
  save(); drawTeams();
}

async function estimate() {
  $("estimate").textContent = "Playing a few test battles...";
  const r = await api("estimate", { setup: setup() });
  $("estimate").textContent = r.error ? r.error : `About ${fmtSecs(r.seconds)}\n(${r.per_battle.toFixed(2)} s a battle, ${r.threads} at a time)`;
  $("estimate").style.whiteSpace = "pre-line";
}

// ---------------------------------------------------------------- MAP page
function drawBoards() {
  const words = $("board-search").value.toLowerCase().split(/\s+/).filter(Boolean);
  const size = $("board-size").value;
  const list = lab.boards.filter((b) => (!size || `${b.width}x${b.height}` === size) && words.every((w) => (b.name + " " + b.source).toLowerCase().includes(w)));
  const body = $("boards").tBodies[0];
  body.innerHTML = list.slice(0, 400).map((b) => `<tr data-id="${esc(b.id)}" class="${b.id === lab.board ? "on" : ""}"><td>${esc(b.name)}</td><td class="num">${b.width}&times;${b.height}</td><td>${esc(b.source)}</td></tr>`).join("")
    || `<tr><td colspan="3" class="note">No board matches</td></tr>`;
  body.querySelectorAll("tr[data-id]").forEach((tr) => tr.addEventListener("click", () => { lab.board = tr.dataset.id; save(); drawBoards(); }));
  const b = lab.boards.find((x) => x.id === lab.board);
  $("board-chosen").innerHTML = b ? `<p><b>${esc(b.name)}</b><br>${b.width} &times; ${b.height} hexes<br>${esc(b.source === "project" ? "Project folder" : "Map pack: " + b.source)}</p>` : "<p>None</p>";
  $("where").textContent = b ? `Board: ${b.name} (${b.width}×${b.height})` : "";
  return list;
}

// ---------------------------------------------------------------- RUN and RESULTS
async function runBatch() {
  $("run-error").textContent = "";
  const r = await api("run", { setup: setup() });
  if (r.error) { $("run-error").textContent = r.error; return; }
  lab.run = r.run;
  lab.runSetup = setup();
  $("results-empty").hidden = true;
  $("results").hidden = false;
  $("battle-list").tBodies[0].innerHTML = "";
  $("stats").innerHTML = "";
  $("winbar").innerHTML = "";
  show("results");
  clearInterval(lab.poll);
  let ticks = 0;
  lab.poll = setInterval(async () => {
    const p = await api("progress", { run: lab.run });
    $("bar").style.width = pct(p.done / p.battles);
    $("progress-text").textContent = `${p.done} / ${p.battles} battles, ${fmtSecs(p.seconds)}${p.cancelled ? " (cancelled)" : ""}`;
    $("cancel-btn").disabled = p.finished;
    setStatus(p.finished ? "Batch finished" : "Running...", `${p.done} / ${p.battles}`);
    if (p.finished || ticks++ % 5 === 0) drawResults(await api("results", { run: lab.run }));
    if (p.finished) clearInterval(lab.poll);
  }, 400);
}

function drawResults(res) {
  lab.results = res;
  const s = res.summary;
  const n = Math.max(1, s.battles);
  const teams = Object.entries(s.teams);
  $("winbar").innerHTML = teams.map(([name, t]) => `<div style="width:${100 * t.wins / n}%;background:${colourOf(name)}" title="${esc(name)}: ${t.wins} wins"></div>`).join("")
    + `<div style="width:${100 * s.draws / n}%;background:var(--face)" title="Draws: ${s.draws}"></div>`;
  const prog = res.progress;
  $("stats").innerHTML = teams.map(([name, t]) => `<fieldset><legend><span style="color:${colourOf(name)}">&#9632;</span> ${esc(name)}</legend><dl>
      <dt>Wins</dt><dd>${t.wins} (${pct(t.win_rate)})</dd>
      <dt>Losses</dt><dd>${s.battles - t.wins - s.draws}</dd>
      <dt>Damage dealt, average</dt><dd>${t.mean_damage_dealt.toFixed(1)}</dd>
      <dt>Units lost, average</dt><dd>${t.mean_units_lost.toFixed(2)}</dd>
      <dt>Armor + structure left</dt><dd>${pct(t.max_hp ? t.mean_hp_left / t.max_hp : 0)}</dd>
      <dt>Shots that hit</dt><dd>${pct(t.hit_rate)}</dd></dl></fieldset>`).join("")
    + `<fieldset><legend>All battles</legend><dl>
      <dt>Battles</dt><dd>${s.battles}</dd>
      <dt>Draws</dt><dd>${s.draws}</dd>
      <dt>Turns, average</dt><dd>${s.mean_turns.toFixed(1)}</dd>
      <dt>Reached the turn cap (${s.max_turns})</dt><dd>${s.hit_turn_cap}</dd>
      <dt>Runtime</dt><dd>${fmtSecs(prog.seconds)}</dd>
      <dt>Seconds a battle</dt><dd>${s.mean_battle_seconds.toFixed(2)}</dd>
      ${res.crashed.length ? `<dt class="err">Crashed</dt><dd class="err">${res.crashed.length}</dd>` : ""}</dl></fieldset>`;
  const body = $("battle-list").tBodies[0];
  body.innerHTML = res.battles.map((b) => `<tr data-sim="${b.sim}"><td class="num">${b.sim}</td><td>${b.seed}</td><td><span style="color:${colourOf(b.winner)}">&#9632;</span> ${esc(b.winner)}${b.capped ? " (turn cap)" : ""}</td><td class="num">${b.turns}</td><td class="num">${b.seconds.toFixed(2)}</td></tr>`).join("");
  body.querySelectorAll("tr").forEach((tr) => tr.addEventListener("click", () => openReplay({ run: lab.run, sim: +tr.dataset.sim })));
}

// ---------------------------------------------------------------- REPLAY page
async function openReplay(which) {
  show("replay");
  const frame = $("replay-frame");
  if (which.run) {
    const line = lab.results && lab.results.battles.find((b) => b.sim === which.sim);
    $("replay-what").textContent = `Battle ${which.sim}` + (line ? `, seed ${line.seed}: ${line.winner} in ${line.turns} turns` : "");
    $("replay-seed").value = line ? line.seed : "";
  } else {
    $("replay-what").textContent = `The current setup on seed ${which.seed}`;
  }
  setStatus("Playing the battle again for its replay...");
  if (DEMO) {
    const rec = which.run ? DEMO.histories[which.sim] : null;
    frame.srcdoc = rec ? DEMO.viewer.replace("__REPLAY_JSON__", JSON.stringify(rec).replace(/<\//g, "<\\/"))
      : `<p style="font:13px Tahoma,sans-serif;padding:12px">This demo carries the replays of battles ${Object.keys(DEMO.histories).join(", ")} only. In Combat Lab any battle replays.</p>`;
  } else if (which.run) {
    frame.removeAttribute("srcdoc");
    frame.src = `replay?run=${which.run}&sim=${which.sim}`;
  } else {
    const r = await api("history", { setup: setup(), seed: which.seed });   // checks the setup; the page plays it again
    if (r.error) { setStatus(r.error); return; }
    frame.removeAttribute("srcdoc");
    frame.src = `replay?seed=${which.seed}&t=${Date.now()}`;
  }
  frame.onload = () => setStatus("Replay ready");
}

// ---------------------------------------------------------------- tabs
function show(page) {
  document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.page === page)));
  document.querySelectorAll(".page").forEach((p) => { p.hidden = p.id !== "page-" + page; });
}

// ---------------------------------------------------------------- the demo's canned answers
let demoDone = 0;
function demoApi(name, body) {
  const d = DEMO;
  switch (name) {
    case "info": return d.info;
    case "list_units": return { units: d.units };
    case "list_boards": return { boards: d.boards };
    case "estimate": return { ...d.estimate, seconds: d.estimate.per_battle * Math.ceil((body.setup.battles || 20) / d.estimate.threads) };
    case "run": demoDone = 0; return { run: 1 };
    case "progress": {
      demoDone = Math.min(d.results.battles.length, demoDone + Math.ceil(d.results.battles.length / 8));
      const fin = demoDone >= d.results.battles.length;
      return { run: 1, done: demoDone, battles: d.results.battles.length, finished: fin, cancelled: false, seconds: fin ? d.results.progress.seconds : d.results.progress.seconds * demoDone / d.results.battles.length };
    }
    case "results": {
      const battles = d.results.battles.slice(0, demoDone);
      return demoDone >= d.results.battles.length ? d.results : { ...d.results, battles, summary: { ...d.results.summary, battles: battles.length } };
    }
    case "cancel": return { run: 1 };
    case "add_unit": return { error: "the demo cannot add unit files; Combat Lab copies them into the project" };
    default: return { error: "not in the demo: " + name };
  }
}

// ---------------------------------------------------------------- start
async function start() {
  try {
    lab.info = await api("info");
  } catch (e) {
    $("banner").hidden = false;
    $("banner").textContent = "Combat Lab's program is not running: start CombatLab, then reload this page.";
    return;
  }
  if (DEMO) {
    $("mode").textContent = "DEMO";
    $("banner").hidden = false;
    $("banner").innerHTML = DEMO.banner;
  }
  setStatus("Loading the unit and board lists...");
  const [u, b] = await Promise.all([api("list_units"), api("list_boards")]);
  lab.units = u.units; lab.boards = b.boards;
  lab.units.forEach((x) => lab.byId.set(x.id, x));
  const sizes = [...new Set(lab.boards.map((x) => `${x.width}x${x.height}`))].sort((p, q) => parseInt(p) - parseInt(q) || p.localeCompare(q, undefined, { numeric: true }));
  $("board-size").innerHTML = `<option value="">Any</option>` + sizes.map((s) => `<option>${s}</option>`).join("");
  restore();
  drawTeams();
  drawBoards();
  setStatus("Ready", `${lab.units.length} units, ${lab.boards.length} boards, ${lab.info.cores} cores`);

  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => show(t.dataset.page)));
  $("team-count").addEventListener("change", (e) => setTeamCount(+e.target.value));
  ["battles", "seed", "threads", "max-turns"].forEach((id) => $(id).addEventListener("change", save));
  $("estimate-btn").addEventListener("click", estimate);
  $("run-btn").addEventListener("click", runBatch);
  $("cancel-btn").addEventListener("click", () => api("cancel", { run: lab.run }));
  $("board-search").addEventListener("input", drawBoards);
  $("board-size").addEventListener("change", drawBoards);
  $("board-random").addEventListener("click", () => {
    const list = drawBoards();
    if (list.length) { lab.board = list[Math.floor(Math.random() * list.length)].id; save(); drawBoards(); }
  });
  $("replay-seed-btn").addEventListener("click", () => {
    const seed = $("replay-seed").value.trim();
    if (/^\d+$/.test(seed)) openReplay({ seed }); else setStatus("A seed is a whole number");
  });
  if (DEMO && DEMO.autorun) runBatch();
}

start();
