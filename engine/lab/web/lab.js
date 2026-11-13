// Combat Lab pages (INTEGRATION__COMBAT_LAB_SPECS.md CL4 and CL5's first step): Units, Map, Options, Results, Replay.
// Everything the engine does is asked of the Lab server (engine/lab/src/main.rs) as JSON; this script only shows and
// collects. With `window.LAB_DEMO` set (tools/make_lab_demo.py builds that page) the answers are canned ones recorded
// from a real Lab run, so the pages can be looked at without the program.
"use strict";

const DEMO = window.LAB_DEMO || null;
const $ = (id) => document.getElementById(id);
const NAMED = [["Red", "#c00000"], ["Blue", "#0000c0"], ["Green", "#007000"], ["Yellow", "#b89000"], ["Purple", "#800080"], ["Orange", "#d05800"], ["Teal", "#007878"], ["Grey", "#606060"]];
const STORE = "combatlab.setup.v2";
const CLASSES = { light: [20, 35], medium: [40, 55], heavy: [60, 75], assault: [80, 100], superheavy: [101, 999] };

const lab = {
  info: null, units: [], boards: [], byId: new Map(), boardById: new Map(),
  teams: [],
  map: { mode: "one", one: null, cols: 2, rows: 1, cells: [null, null], cell: 0 },
  run: null, runSetup: null, filter: {}, poll: null,
  picked: new Set(),            // units selected in the unit browser
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
// a unit's Battle Value for its pilot: the list gives it for gunnery 4 / piloting 5; the engine's skill table
// (battle_value.rs SKILL_TABLE, sent by the server) scales it, rounded as the engine rounds
function unitBv(u) {
  const base = (lab.byId.get(u.id) || {}).bv;
  if (base == null) return null;
  const table = lab.info.skill_table;
  if (!table) return base;
  const g = Math.max(0, Math.min(8, u.gunnery)), p = Math.max(0, Math.min(8, u.piloting));
  return Math.floor(base * table[g][p] + 0.5);
}
const colourOf = (name) => (lab.teams.find((t) => t.name === name) || {}).colour || "#808080";

// a team's default colour: the named ones first, then hues spread around the wheel (any number of teams)
function defaultColour(i) {
  if (i < NAMED.length) return NAMED[i][1];
  const h = (i * 137.508) % 360, s = 0.7, l = 0.36;
  const f = (n) => { const k = (n + h / 30) % 12; const c = l - s * Math.min(l, 1 - l) * Math.max(-1, Math.min(k - 3, 9 - k, 1)); return Math.round(255 * c).toString(16).padStart(2, "0"); };
  return `#${f(0)}${f(8)}${f(4)}`;
}
function freshTeamName(i) {
  const taken = new Set(lab.teams.map((t) => t.name));
  if (i < NAMED.length && !taken.has(NAMED[i][0])) return NAMED[i][0];
  let n = i + 1;
  while (taken.has(`Team ${n}`)) n++;
  return `Team ${n}`;
}

// ---------------------------------------------------------------- the setup (what Run sends)
function boardOfSetup() {
  const m = lab.map;
  if (m.mode === "one") return m.one;
  const grid = [];
  for (let r = 0; r < m.rows; r++) grid.push(m.cells.slice(r * m.cols, (r + 1) * m.cols));
  return { grid };
}

function setup() {
  return {
    teams: lab.teams.map((t) => ({ name: t.name, colour: t.colour, bot: t.bot, units: t.units.map((u) => ({ unit: u.id, gunnery: u.gunnery, piloting: u.piloting })) })),
    board: boardOfSetup(),
    battles: +$("battles").value || 20,
    seed: +$("seed").value || 0,
    threads: +$("threads").value || 0,
    max_turns: +$("max-turns").value || 100,
  };
}

function save() {
  try { localStorage.setItem(STORE, JSON.stringify({ teams: lab.teams, map: lab.map, battles: $("battles").value, seed: $("seed").value, threads: $("threads").value, maxTurns: $("max-turns").value })); } catch (e) { /* storage off: nothing kept */ }
  $("estimate").textContent = "Press Estimate";
}

function unitEntry(id, g = 4, p = 5) {
  const u = lab.byId.get(id);
  return u && { id, name: u.name, tons: u.tons, bv: u.bv, gunnery: g, piloting: p };
}

function restore() {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(STORE) || "null"); } catch (e) { saved = null; }
  if (DEMO) saved = null;     // the demo always opens on the setup its results came from
  if (saved && saved.teams && saved.teams.length >= 2) {
    lab.teams = saved.teams.map((t) => ({ ...t, units: t.units.map((u) => unitEntry(u.id, u.gunnery, u.piloting)).filter(Boolean) }));
    lab.map = { ...lab.map, ...saved.map };
    $("battles").value = saved.battles || 20; $("seed").value = saved.seed || 1; $("threads").value = saved.threads || 0; $("max-turns").value = saved.maxTurns || 100;
  } else {
    const start = DEMO ? DEMO.setup : { teams: [{ name: "Red", bot: "gladiator", units: [{ unit: "Atlas AS7-K.mtf" }, { unit: "Griffin GRF-1N.mtf" }] },
      { name: "Blue", bot: "gladiator", units: [{ unit: "Awesome AWS-8Q.mtf" }, { unit: "Hunchback HBK-4G.mtf" }] }], board: lab.info.default_board, battles: 20, seed: 1 };
    lab.teams = start.teams.map((t, i) => ({ name: t.name, colour: t.colour || defaultColour(i), bot: t.bot, units: t.units.map((u) => unitEntry(u.unit, u.gunnery ?? 4, u.piloting ?? 5)).filter(Boolean) }));
    lab.map.one = typeof start.board === "string" ? start.board : lab.info.default_board;
    $("battles").value = start.battles; $("seed").value = start.seed;
  }
  if (!lab.boardById.has(lab.map.one)) lab.map.one = lab.info.default_board;
  lab.map.cells = lab.map.cells.map((c) => (lab.boardById.has(c) ? c : null));
  $("team-count").value = lab.teams.length;
}

// ---------------------------------------------------------------- UNITS page
function drawTeams() {
  const box = $("teams");
  box.innerHTML = "";
  lab.teams.forEach((t, ti) => box.appendChild(teamPanel(t, ti)));
  $("team-sum").textContent = `${lab.teams.length} teams, ${lab.teams.reduce((s, t) => s + t.units.length, 0)} units`;
}

function teamPanel(t, ti) {
  const el = document.createElement("fieldset");
  el.className = "team raised";
  const bots = lab.info.bots.map((b) => `<option value="${b}"${b === t.bot ? " selected" : ""}>${b[0].toUpperCase() + b.slice(1)}</option>`).join("");
  const tons = t.units.reduce((s, u) => s + (u.tons || 0), 0);
  const bv = t.units.reduce((s, u) => s + (unitBv(u) || 0), 0);
  el.innerHTML = `
    <legend>Team ${ti + 1}</legend>
    <div class="team-head">
      <label for="tcol-${ti}">Colour <input type="color" id="tcol-${ti}" value="${t.colour}"></label>
      <label for="tname-${ti}">Name <input type="text" id="tname-${ti}" value="${esc(t.name)}" maxlength="24"></label>
      <label for="tbot-${ti}">Bot <select id="tbot-${ti}">${bots}</select></label>
    </div>
    <div class="list sunken"><table>
      <thead><tr><th>Unit</th><th class="num">Tons</th><th class="num">BV</th><th title="Gunnery skill">G</th><th title="Piloting skill">P</th><th></th></tr></thead>
      <tbody>${t.units.length ? t.units.map((u, ui) => `<tr>
        <td class="name">${esc(u.name)}</td><td class="num">${u.tons ?? ""}</td><td class="num" id="bv-${ti}-${ui}">${unitBv(u) ?? ""}</td>
        <td><input type="number" min="0" max="8" value="${u.gunnery}" id="g-${ti}-${ui}" aria-label="Gunnery"></td>
        <td><input type="number" min="0" max="8" value="${u.piloting}" id="p-${ti}-${ui}" aria-label="Piloting"></td>
        <td><button class="btn small" data-remove="${ui}" title="Remove">&times;</button></td></tr>`).join("")
        : `<tr class="empty"><td colspan="6">No units yet. Drag units here from the Unit Browser, or type a name below.</td></tr>`}</tbody>
    </table></div>
    <div class="totals"><span>${t.units.length} unit${t.units.length === 1 ? "" : "s"}</span><span>${tons} tons</span><span>BV ${bv}</span></div>
    <div class="adder">
      <input type="search" id="find-${ti}" placeholder="Quick add: type a unit name" autocomplete="off">
      <div class="hits sunken" id="hits-${ti}" hidden></div>
    </div>
    <div class="team-buttons">
      <button class="btn" id="browse-${ti}">Unit Browser&hellip;</button>
      <button class="btn" id="addsel-${ti}" ${lab.picked.size ? "" : "hidden"}>Add selected (${lab.picked.size})</button>
      <button class="btn" id="file-${ti}" title="Add a .mtf unit file from this computer">From file&hellip;</button>
      <input type="file" id="fileinput-${ti}" accept=".mtf" multiple hidden>
    </div>`;
  const redraw = () => { save(); drawTeams(); };
  el.querySelector(`#tname-${ti}`).addEventListener("change", (e) => {
    const name = e.target.value.trim();
    if (name && !lab.teams.some((o, oi) => oi !== ti && o.name === name)) t.name = name;
    redraw();
  });
  el.querySelector(`#tcol-${ti}`).addEventListener("input", (e) => { t.colour = e.target.value; save(); });
  el.querySelector(`#tbot-${ti}`).addEventListener("change", (e) => { t.bot = e.target.value; save(); });
  el.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", () => { t.units.splice(+b.dataset.remove, 1); redraw(); }));
  t.units.forEach((u, ui) => {
    // a skill change re-draws the team, so the unit's BV and the team's total follow it
    el.querySelector(`#g-${ti}-${ui}`).addEventListener("change", (e) => { u.gunnery = Math.max(0, Math.min(8, +e.target.value)); redraw(); });
    el.querySelector(`#p-${ti}-${ui}`).addEventListener("change", (e) => { u.piloting = Math.max(0, Math.min(8, +e.target.value)); redraw(); });
  });
  wireSearch(el, t, ti);
  el.querySelector(`#browse-${ti}`).addEventListener("click", openBrowser);
  el.querySelector(`#addsel-${ti}`).addEventListener("click", () => addUnits(t, [...lab.picked]));
  // a .mtf file (dropped on the panel, or picked with From file...) is copied into the project and added
  const files = async (list) => {
    for (const f of list) {
      if (!f.name.toLowerCase().endsWith(".mtf")) { setStatus(`${f.name}: only .mtf unit files can be added`); continue; }
      const r = await api("add_unit", { file: f.name, text: await f.text() });
      if (r.error) { setStatus(`${f.name}: ${r.error}`); continue; }
      if (!lab.byId.has(r.unit.id)) { lab.units.push(r.unit); lab.byId.set(r.unit.id, r.unit); }
      t.units.push(unitEntry(r.unit.id));
      setStatus(r.copied ? `${r.unit.name} copied into the project's unit folder and added` : `${r.unit.name} added (already in the project)`);
    }
    redraw();
  };
  el.querySelector(`#file-${ti}`).addEventListener("click", () => el.querySelector(`#fileinput-${ti}`).click());
  el.querySelector(`#fileinput-${ti}`).addEventListener("change", (e) => files(e.target.files));
  // drops: units dragged from the Unit Browser, or unit files from the computer
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("drop"); });
  el.addEventListener("dragleave", () => el.classList.remove("drop"));
  el.addEventListener("drop", (e) => {
    e.preventDefault(); el.classList.remove("drop");
    const ids = e.dataTransfer.getData("text/x-lab-units");
    if (ids) addUnits(t, JSON.parse(ids)); else files(e.dataTransfer.files);
  });
  return el;
}

function addUnits(t, ids) {
  const added = ids.map((id) => unitEntry(id)).filter((u) => u && lab.byId.get(u.id).ok);
  t.units.push(...added);
  setStatus(`${added.length} unit${added.length === 1 ? "" : "s"} added to ${t.name}`);
  save(); drawTeams();
}

function wireSearch(el, t, ti) {
  const input = el.querySelector(`#find-${ti}`);
  const hits = el.querySelector(`#hits-${ti}`);
  let shown = [];
  const add = (u) => {
    t.units.push(unitEntry(u.id));
    save(); drawTeams();
    const again = $(`find-${ti}`); if (again) again.focus();
  };
  input.addEventListener("input", () => {
    const words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) { hits.hidden = true; return; }
    shown = lab.units.filter((u) => words.every((w) => u.name.toLowerCase().includes(w))).slice(0, 60);
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
  n = Math.max(2, Math.min(999, n || 2));
  while (lab.teams.length < n) {
    const i = lab.teams.length;
    lab.teams.push({ name: freshTeamName(i), colour: defaultColour(i), bot: "gladiator", units: [] });
  }
  lab.teams.length = n;
  $("team-count").value = n;
  save(); drawTeams();
}

async function estimate() {
  $("estimate").textContent = "Playing a few test battles...";
  const r = await api("estimate", { setup: setup() });
  $("estimate").textContent = r.error ? r.error : `About ${fmtSecs(r.seconds)}\n(${r.per_battle.toFixed(2)} s a battle, ${r.threads} at a time)`;
}

// ---------------------------------------------------------------- the UNIT BROWSER window
const browse = { sort: "name", dir: 1, shown: [] };

function openBrowser() {
  const w = $("browser");
  w.hidden = false;
  if (!$("ub-source").options.length) {
    const sources = [...new Set(lab.units.map((u) => u.source))].sort((a, b) => (a === "project" ? -1 : b === "project" ? 1 : a.localeCompare(b)));
    $("ub-source").innerHTML = `<option value="">Any</option>` + sources.map((s) => `<option value="${esc(s)}">${esc(s === "project" ? "Project folder" : s)}</option>`).join("");
  }
  drawBrowser();
  $("ub-name").focus();
}

function drawBrowser() {
  const words = $("ub-name").value.toLowerCase().split(/\s+/).filter(Boolean);
  const cls = CLASSES[$("ub-class").value];
  const num = (id) => ($(id).value === "" ? null : +$(id).value);
  const [tmin, tmax, bmin, bmax, year] = [num("ub-tmin"), num("ub-tmax"), num("ub-bmin"), num("ub-bmax"), num("ub-year")];
  const tech = $("ub-tech").value, source = $("ub-source").value, playable = $("ub-playable").checked;
  const list = lab.units.filter((u) =>
    (!playable || u.ok) && words.every((w) => u.name.toLowerCase().includes(w)) &&
    (!cls || (u.tons >= cls[0] && u.tons <= cls[1])) &&
    (tmin === null || u.tons >= tmin) && (tmax === null || u.tons <= tmax) &&
    (bmin === null || (u.bv ?? 0) >= bmin) && (bmax === null || (u.bv ?? 0) <= bmax) &&
    (!tech || (u.tech || "").toLowerCase().includes(tech)) && (!source || u.source === source) &&
    (year === null || (u.era ?? 0) <= year));
  const k = browse.sort, d = browse.dir;
  list.sort((a, b) => (k === "name" ? a.name.localeCompare(b.name) : ((a[k] ?? -1) - (b[k] ?? -1)) || a.name.localeCompare(b.name)) * d);
  browse.shown = list.slice(0, 400);
  $("ub-count").textContent = `${list.length} unit${list.length === 1 ? "" : "s"}${list.length > 400 ? " (first 400 shown: narrow the search)" : ""}`;
  const body = $("ub-list").tBodies[0];
  body.innerHTML = browse.shown.map((u, i) => `<tr data-i="${i}" draggable="${u.ok}" class="${lab.picked.has(u.id) ? "on" : ""}${u.ok ? "" : " bad"}" title="${esc(u.ok ? "Drag onto a team" : u.why)}">
      <td>${esc(u.name)}</td><td class="num">${u.tons ?? ""}</td><td class="num">${u.bv ?? ""}</td><td>${esc(u.tech || "")}</td><td class="num">${u.era ?? ""}</td></tr>`).join("");
  body.querySelectorAll("tr").forEach((tr) => {
    const u = browse.shown[+tr.dataset.i];
    tr.addEventListener("click", (e) => {
      if (!u.ok) return;
      if (!(e.ctrlKey || e.metaKey || e.shiftKey)) { if (lab.picked.has(u.id) && lab.picked.size === 1) lab.picked.clear(); else { lab.picked.clear(); lab.picked.add(u.id); } }
      else if (lab.picked.has(u.id)) lab.picked.delete(u.id); else lab.picked.add(u.id);
      pickedChanged();
    });
    tr.addEventListener("dragstart", (e) => {
      const ids = lab.picked.has(u.id) ? [...lab.picked] : [u.id];
      e.dataTransfer.setData("text/x-lab-units", JSON.stringify(ids));
      e.dataTransfer.effectAllowed = "copy";
    });
  });
  document.querySelectorAll("#ub-list th[data-sort]").forEach((th) => th.classList.toggle("sorted", th.dataset.sort === k));
}

function pickedChanged() {
  $("ub-picked").textContent = lab.picked.size ? `${lab.picked.size} selected: drag them onto a team, or press that team's "Add selected"` : "Drag a unit onto a team. Click to select several (Ctrl+click adds to the selection).";
  drawBrowser();
  lab.teams.forEach((t, ti) => { const b = $(`addsel-${ti}`); if (b) { b.hidden = !lab.picked.size; b.textContent = `Add selected (${lab.picked.size})`; } });
}

// the window moves by its title bar
function wireBrowserWindow() {
  const w = $("browser"), bar = $("ub-title");
  bar.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button")) return;
    const r = w.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
    bar.setPointerCapture(e.pointerId);
    const move = (m) => { w.style.left = `${Math.max(0, m.clientX - dx)}px`; w.style.top = `${Math.max(0, m.clientY - dy)}px`; w.style.right = "auto"; };
    bar.addEventListener("pointermove", move);
    bar.addEventListener("pointerup", () => bar.removeEventListener("pointermove", move), { once: true });
  });
  $("ub-close").addEventListener("click", () => { w.hidden = true; });
  ["ub-name", "ub-tmin", "ub-tmax", "ub-bmin", "ub-bmax", "ub-year"].forEach((id) => $(id).addEventListener("input", drawBrowser));
  ["ub-class", "ub-tech", "ub-source", "ub-playable"].forEach((id) => $(id).addEventListener("change", drawBrowser));
  $("ub-clear").addEventListener("click", () => { lab.picked.clear(); pickedChanged(); });
  document.querySelectorAll("#ub-list th[data-sort]").forEach((th) => th.addEventListener("click", () => {
    browse.dir = browse.sort === th.dataset.sort ? -browse.dir : 1; browse.sort = th.dataset.sort; drawBrowser();
  }));
}

// ---------------------------------------------------------------- MAP page
function drawBoards() {
  const words = $("board-search").value.toLowerCase().split(/\s+/).filter(Boolean);
  const size = $("board-size").value;
  const list = lab.boards.filter((b) => (!size || `${b.width}x${b.height}` === size) && words.every((w) => (b.name + " " + b.source).toLowerCase().includes(w)));
  const m = lab.map;
  const current = m.mode === "one" ? m.one : m.cells[m.cell];
  const body = $("boards").tBodies[0];
  body.innerHTML = list.slice(0, 400).map((b) => `<tr data-id="${esc(b.id)}" class="${b.id === current ? "on" : ""}"><td>${esc(b.name)}</td><td class="num">${b.width}&times;${b.height}</td><td>${esc(b.source)}</td></tr>`).join("")
    || `<tr><td colspan="3" class="note">No board matches</td></tr>`;
  body.querySelectorAll("tr[data-id]").forEach((tr) => tr.addEventListener("click", () => {
    if (m.mode === "one") m.one = tr.dataset.id;
    else { m.cells[m.cell] = tr.dataset.id; m.cell = (m.cell + 1) % m.cells.length; }
    save(); drawBoards();
  }));
  $("map-one").checked = m.mode === "one";
  $("map-stitch").checked = m.mode === "stitch";
  $("stitch-box").hidden = m.mode !== "stitch";
  $("stitch-cols").value = m.cols; $("stitch-rows").value = m.rows;
  drawStitch();
  return list;
}

// the stitched map: a grid of places; the chosen place gets the next board clicked in the list
function drawStitch() {
  const m = lab.map;
  const g = $("stitch-grid");
  g.style.gridTemplateColumns = `repeat(${m.cols}, minmax(0, 1fr))`;
  g.innerHTML = m.cells.map((id, i) => {
    const b = lab.boardById.get(id);
    return `<button class="cell ${i === m.cell ? "on" : ""}" data-i="${i}">${b ? `${esc(b.name)}<br><span class="note">${b.width}&times;${b.height}</span>` : "<span class=\"note\">(choose)</span>"}</button>`;
  }).join("");
  g.querySelectorAll(".cell").forEach((c) => c.addEventListener("click", () => { m.cell = +c.dataset.i; drawBoards(); }));
  const { text, ok } = mapCheck();
  $("board-chosen").innerHTML = text;
  $("where").textContent = ok ? `Board: ${ok}` : "Board: not ready (see Map)";
}

// what the map will be, or why it can't be (stitched boards: same height along a row, same width down a column)
function mapCheck() {
  const m = lab.map;
  if (m.mode === "one") {
    const b = lab.boardById.get(m.one);
    return b ? { ok: `${b.name} (${b.width}×${b.height})`, text: `<p><b>${esc(b.name)}</b><br>${b.width} &times; ${b.height} hexes<br>${esc(b.source === "project" ? "Project folder" : "Map pack: " + b.source)}</p>` } : { text: "<p>None</p>" };
  }
  const at = (r, c) => lab.boardById.get(m.cells[r * m.cols + c]);
  if (m.cells.some((c) => !lab.boardById.has(c))) return { text: `<p class="err">Every place in the grid needs a board.</p>` };
  for (let r = 0; r < m.rows; r++) for (let c = 1; c < m.cols; c++) if (at(r, c).height !== at(r, 0).height) return { text: `<p class="err">Row ${r + 1}: the boards are not all the same height.</p>` };
  for (let c = 0; c < m.cols; c++) for (let r = 1; r < m.rows; r++) if (at(r, c).width !== at(0, c).width) return { text: `<p class="err">Column ${c + 1}: the boards are not all the same width.</p>` };
  let w = 0, h = 0;
  for (let c = 0; c < m.cols; c++) w += at(0, c).width;
  for (let r = 0; r < m.rows; r++) h += at(r, 0).height;
  return { ok: `${m.cols * m.rows} boards stitched (${w}×${h})`, text: `<p><b>${m.cols * m.rows} boards stitched together</b><br>${w} &times; ${h} hexes</p>` };
}

function resizeStitch() {
  const m = lab.map;
  const cols = Math.max(1, Math.min(8, +$("stitch-cols").value || 1)), rows = Math.max(1, Math.min(8, +$("stitch-rows").value || 1));
  const cells = [];
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) cells.push(r < m.rows && c < m.cols ? m.cells[r * m.cols + c] : null);
  Object.assign(m, { cols, rows, cells, cell: 0 });
  save(); drawBoards();
}

function randomMap() {
  const list = drawBoards();
  if (!list.length) return;
  const m = lab.map;
  if (m.mode === "one") m.one = list[Math.floor(Math.random() * list.length)].id;
  else {
    // one size for every place, so the boards always fit together
    const sizes = [...new Set(list.map((b) => `${b.width}x${b.height}`))];
    const size = sizes[Math.floor(Math.random() * sizes.length)];
    const same = list.filter((b) => `${b.width}x${b.height}` === size);
    m.cells = m.cells.map(() => same[Math.floor(Math.random() * same.length)].id);
  }
  save(); drawBoards();
}

// ---------------------------------------------------------------- RUN and RESULTS
async function runBatch() {
  $("run-error").textContent = "";
  if (!mapCheck().ok) { $("run-error").textContent = "The map is not ready: see the Map page."; return; }
  const r = await api("run", { setup: setup() });
  if (r.error) { $("run-error").textContent = r.error; return; }
  lab.run = r.run;
  lab.runSetup = setup();
  lab.filter = {};
  $("results-empty").hidden = true;
  $("results").hidden = false;
  drawFilterForm(null);
  show("results");
  clearInterval(lab.poll);
  let ticks = 0;
  lab.poll = setInterval(async () => {
    const p = await api("progress", { run: lab.run });
    $("bar").style.width = pct(p.done / p.battles);
    $("progress-text").textContent = `${p.done} / ${p.battles} battles, ${fmtSecs(p.seconds)}${p.cancelled ? " (cancelled)" : ""}`;
    $("cancel-btn").disabled = p.finished;
    setStatus(p.finished ? "Batch finished" : "Running...", `${p.done} / ${p.battles}`);
    if (p.finished || ticks++ % 5 === 0) await drawResults();
    if (p.finished) clearInterval(lab.poll);
  }, 400);
}

async function drawResults() {
  const total = lab.runSetup.battles;
  const res = await api("results", { run: lab.run, filter: lab.filter, from: 1, to: total, bucket: bucketFor(total) });
  if (res.error) { setStatus(res.error); return; }
  drawFilterForm(res);
  const s = res.summary, all = res.all;
  const filtered = Object.keys(lab.filter).length > 0;
  $("filter-note").textContent = filtered ? `${res.matching} of ${all.battles} battles match: the statistics below are theirs.` : `${all.battles} battles.`;
  const n = Math.max(1, s.battles);
  const teams = Object.entries(s.teams);
  $("winbar").innerHTML = teams.map(([name, t]) => `<div style="width:${100 * t.wins / n}%;background:${colourOf(name)}" title="${esc(name)}: ${t.wins} wins"></div>`).join("")
    + `<div style="width:${100 * s.draws / n}%;background:var(--face)" title="Draws: ${s.draws}"></div>`;
  $("stats").innerHTML = teams.map(([name, t]) => `<fieldset><legend><span style="color:${colourOf(name)}">&#9632;</span> ${esc(name)}</legend><dl>
      <dt>Wins</dt><dd>${t.wins} (${pct(t.win_rate)})</dd>
      <dt>Losses</dt><dd>${s.battles - t.wins - s.draws}</dd>
      <dt>Damage dealt, average</dt><dd>${t.mean_damage_dealt.toFixed(1)}</dd>
      <dt>Units lost, average</dt><dd>${t.mean_units_lost.toFixed(2)}</dd>
      <dt>Armor + structure left</dt><dd>${pct(t.max_hp ? t.mean_hp_left / t.max_hp : 0)}</dd>
      <dt>Shots that hit</dt><dd>${pct(t.hit_rate)}</dd></dl></fieldset>`).join("")
    + `<fieldset><legend>${filtered ? "Matching battles" : "All battles"}</legend><dl>
      <dt>Battles</dt><dd>${s.battles}</dd>
      <dt>Draws</dt><dd>${s.draws}</dd>
      <dt>Turns, average</dt><dd>${s.mean_turns.toFixed(1)}</dd>
      <dt>Reached the turn cap (${s.max_turns})</dt><dd>${s.hit_turn_cap}</dd>
      <dt>Runtime</dt><dd>${fmtSecs(res.progress.seconds)}</dd>
      <dt>Seconds a battle</dt><dd>${s.mean_battle_seconds.toFixed(2)}</dd>
      ${res.crashed.length ? `<dt class="err">Crashed</dt><dd class="err">${res.crashed.length}</dd>` : ""}</dl></fieldset>`;
  const tree = $("battle-tree");
  tree.innerHTML = "";
  fillRange(tree, 1, total, res);
}

// A long battle list is nested: a range with more than 100 battles to show is split into at most 100 smaller ranges,
// each opened on demand ("Battles 1-100 (37)"), so no level of the list is ever long.
function bucketFor(count) {
  if (count <= 100) return 1;
  let b = 100;
  while (Math.ceil(count / b) > 100) b *= 10;
  return b;
}

async function fillRange(box, from, to, res) {
  const bucket = bucketFor(to - from + 1);
  res = res || await api("results", { run: lab.run, filter: lab.filter, from, to, bucket });
  if (res.in_range <= 100 || bucket === 1) {
    if (!res.battles.length) { box.innerHTML = `<div class="note leaf">No battles here${Object.keys(lab.filter).length ? " match" : " yet"}.</div>`; return; }
    const table = document.createElement("table");
    table.className = "leaves";
    table.innerHTML = `<thead><tr><th class="num">#</th><th>Seed</th><th>Winner</th><th class="num">Turns</th><th class="num">Seconds</th></tr></thead><tbody>` +
      res.battles.map((b) => `<tr data-sim="${b.sim}"><td class="num">${b.sim}</td><td>${b.seed}</td><td><span style="color:${colourOf(b.winner)}">&#9632;</span> ${esc(b.winner)}${b.capped ? " (turn cap)" : ""}</td><td class="num">${b.turns}</td><td class="num">${b.seconds.toFixed(2)}</td></tr>`).join("") + "</tbody>";
    table.querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", () => openReplay({ run: lab.run, sim: +tr.dataset.sim })));
    box.appendChild(table);
    return;
  }
  (res.buckets || []).forEach((count, i) => {
    if (!count) return;
    const a = from + i * bucket, b = Math.min(to, a + bucket - 1);
    const node = document.createElement("div");
    node.className = "branch";
    node.innerHTML = `<button class="twig" aria-expanded="false"><span class="sign">+</span> Battles ${a}&ndash;${b} <span class="note">(${count})</span></button><div class="kids" hidden></div>`;
    const btn = node.querySelector(".twig"), kids = node.querySelector(".kids");
    btn.addEventListener("click", async () => {
      const open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(open));
      btn.querySelector(".sign").textContent = open ? "−" : "+";
      kids.hidden = !open;
      if (open && !kids.childElementCount) await fillRange(kids, a, b);
    });
    box.appendChild(node);
  });
}

// the "Find battles" form: winner, turn cap, turns, and any number of unit conditions
function drawFilterForm(res) {
  const teams = lab.runSetup ? lab.runSetup.teams.map((t) => t.name) : [];
  const w = $("f-winner");
  const keepW = w.value;
  w.innerHTML = `<option value="">Any</option>` + teams.map((t) => `<option>${esc(t)}</option>`).join("") + `<option>Draw</option>`;
  w.value = keepW;
  if (res && res.units) lab.unitLabels = res.units;
}

function addUnitCondition(cond = {}) {
  const labels = lab.unitLabels || {};
  const row = document.createElement("div");
  row.className = "cond";
  row.innerHTML = `<select class="c-unit" aria-label="Unit">${Object.entries(labels).map(([k, v]) => `<option value="${esc(k)}"${k === cond.unit ? " selected" : ""}>${esc(v)}</option>`).join("")}</select>
    <select class="c-state" aria-label="What happened"><option value="destroyed">was destroyed</option><option value="survived">survived</option><option value="">either</option></select>
    <input type="text" class="c-cause" placeholder="cause contains (e.g. head)" aria-label="Cause of death contains">
    <button class="btn small" title="Remove this condition">&times;</button>`;
  row.querySelector("button").addEventListener("click", () => row.remove());
  $("f-units").appendChild(row);
}

function readFilter() {
  const f = {};
  if ($("f-winner").value) f.winner = $("f-winner").value;
  if ($("f-capped").value) f.capped = $("f-capped").value === "yes";
  if ($("f-tmin").value !== "") f.min_turns = +$("f-tmin").value;
  if ($("f-tmax").value !== "") f.max_turns = +$("f-tmax").value;
  const units = [...document.querySelectorAll("#f-units .cond")].map((r) => ({ unit: r.querySelector(".c-unit").value, state: r.querySelector(".c-state").value, cause: r.querySelector(".c-cause").value }));
  if (units.length) f.units = units;
  return f;
}

// ---------------------------------------------------------------- REPLAY page
async function openReplay(which) {
  show("replay");
  const frame = $("replay-frame");
  if (which.run) {
    $("replay-what").textContent = `Battle ${which.sim}`;
  } else {
    $("replay-what").textContent = `The current setup on seed ${which.seed}`;
  }
  setStatus("Playing the battle again for its replay...");
  if (DEMO) {
    const rec = which.run ? DEMO.histories[which.sim] : null;
    if (rec) rec.colours = Object.fromEntries(lab.teams.map((t) => [t.name, t.colour]));
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
// (the same filter and pieces as the server's `results`, engine/lab/src/runs.rs, over the recorded battles)
let demoDone = 0;
function demoMatches(l, f) {
  if (f.winner && l.winner !== f.winner) return false;
  if (f.capped !== undefined && l.capped !== f.capped) return false;
  if (f.min_turns !== undefined && l.turns < f.min_turns) return false;
  if (f.max_turns !== undefined && l.turns > f.max_turns) return false;
  return (f.units || []).every((c) => {
    const u = l.units[c.unit] || {};
    if (c.state === "destroyed" && !u.destroyed) return false;
    if (c.state === "survived" && u.destroyed) return false;
    const cause = (u.cause || "").toLowerCase();
    return (c.cause || "").toLowerCase().split(/\s+/).filter(Boolean).every((w) => cause.includes(w));
  });
}
function demoSummary(lines) {
  const n = Math.max(1, lines.length);
  const teams = {};
  for (const t of DEMO.setup.teams.map((x) => x.name)) {
    const wins = lines.filter((l) => l.winner === t).length;
    const mean = (k) => lines.reduce((s, l) => s + (l.teams[t][k] || 0), 0) / n;
    const at = lines.reduce((s, l) => s + l.teams[t].attacks, 0), hi = lines.reduce((s, l) => s + l.teams[t].hits, 0);
    teams[t] = { wins, win_rate: wins / n, mean_damage_dealt: mean("damage_dealt"), mean_units_lost: mean("units_lost"), mean_hp_left: mean("final_hp"), max_hp: mean("max_hp"), hit_rate: at ? hi / at : 0 };
  }
  return { battles: lines.length, teams, draws: lines.filter((l) => l.winner === "Draw").length, hit_turn_cap: lines.filter((l) => l.capped).length,
    max_turns: DEMO.setup.max_turns, mean_turns: lines.reduce((s, l) => s + l.turns, 0) / n, mean_battle_seconds: lines.reduce((s, l) => s + l.seconds, 0) / n };
}
function demoApi(name, body) {
  const d = DEMO;
  const total = d.lines.length;
  switch (name) {
    case "info": return d.info;
    case "list_units": return { units: d.units };
    case "list_boards": return { boards: d.boards };
    case "estimate": return { ...d.estimate, seconds: d.estimate.per_battle * Math.ceil((body.setup.battles || 20) / d.estimate.threads) };
    case "run": demoDone = 0; return { run: 1 };
    case "progress": {
      demoDone = Math.min(total, demoDone + Math.ceil(total / 8));
      return { run: 1, done: demoDone, battles: total, finished: demoDone >= total, cancelled: false, seconds: d.seconds * demoDone / total };
    }
    case "results": {
      const lines = d.lines.filter((l) => l.sim <= demoDone);
      const kept = lines.filter((l) => demoMatches(l, body.filter || {}));
      const from = body.from || 1, to = body.to || total;
      const inRange = kept.filter((l) => l.sim >= from && l.sim <= to);
      const out = { progress: { seconds: d.seconds * demoDone / total }, all: demoSummary(lines), summary: demoSummary(kept), matching: kept.length,
        in_range: inRange.length, battles: inRange.slice(0, 500), units: d.unitLabels, crashed: [] };
      if (body.bucket) { out.buckets = new Array(Math.ceil((to - from + 1) / body.bucket)).fill(0); inRange.forEach((l) => out.buckets[Math.floor((l.sim - from) / body.bucket)]++); }
      return out;
    }
    case "cancel": return { run: 1 };
    case "add_unit": {
      // the demo reads the file's own name and weight; Combat Lab also copies it into the project and works out its BV
      const field = (k) => ((body.text.match(new RegExp(`^${k}:(.*)$`, "im")) || [])[1] || "").trim();
      const unit = { id: body.file, name: `${field("chassis")} ${field("model")}`.trim() || body.file, tons: +field("mass") || null, bv: null, source: "project", ok: true };
      return { unit, copied: true };
    }
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
  if (lab.info.missing_data) {
    $("banner").hidden = false;
    $("banner").innerHTML = `<b>No units or boards found.</b> Combat Lab comes in two parts: unzip the data part into the same folder as CombatLab.exe (the folder <code>data</code> must sit beside it), then close the black window and start CombatLab again.`;
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
  lab.boards.forEach((x) => lab.boardById.set(x.id, x));
  const sizes = [...new Set(lab.boards.map((x) => `${x.width}x${x.height}`))].sort((p, q) => parseInt(p) - parseInt(q) || p.localeCompare(q, undefined, { numeric: true }));
  $("board-size").innerHTML = `<option value="">Any</option>` + sizes.map((s) => `<option>${s}</option>`).join("");
  restore();
  drawTeams();
  drawBoards();
  wireBrowserWindow();
  pickedChanged();
  setStatus("Ready", `${lab.units.length} units, ${lab.boards.length} boards, ${lab.info.cores} cores`);

  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => show(t.dataset.page)));
  $("team-count").addEventListener("change", (e) => setTeamCount(+e.target.value));
  ["battles", "seed", "threads", "max-turns"].forEach((id) => $(id).addEventListener("change", save));
  $("estimate-btn").addEventListener("click", estimate);
  $("run-btn").addEventListener("click", runBatch);
  $("browse-btn").addEventListener("click", openBrowser);
  $("about-btn").addEventListener("click", () => { $("about").hidden = false; });
  $("about-close").addEventListener("click", () => { $("about").hidden = true; });
  $("cancel-btn").addEventListener("click", () => api("cancel", { run: lab.run }));
  $("board-search").addEventListener("input", drawBoards);
  $("board-size").addEventListener("change", drawBoards);
  $("board-random").addEventListener("click", randomMap);
  $("map-one").addEventListener("change", () => { lab.map.mode = "one"; save(); drawBoards(); });
  $("map-stitch").addEventListener("change", () => { lab.map.mode = "stitch"; save(); drawBoards(); });
  $("stitch-cols").addEventListener("change", resizeStitch);
  $("stitch-rows").addEventListener("change", resizeStitch);
  $("f-add-unit").addEventListener("click", () => addUnitCondition());
  $("f-apply").addEventListener("click", () => { lab.filter = readFilter(); drawResults(); });
  $("f-clear").addEventListener("click", () => {
    ["f-winner", "f-capped", "f-tmin", "f-tmax"].forEach((id) => { $(id).value = ""; });
    $("f-units").innerHTML = ""; lab.filter = {}; drawResults();
  });
  $("replay-seed-btn").addEventListener("click", () => {
    const seed = $("replay-seed").value.trim();
    if (/^\d+$/.test(seed)) openReplay({ seed }); else setStatus("A seed is a whole number");
  });
  if (DEMO && DEMO.autorun) runBatch();
}

start();
