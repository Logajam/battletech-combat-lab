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
  options: {}, registry: [],    // the Options tab: changed settings {NAME: value}, and the list of every setting
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
    ...(Object.keys(lab.options).length ? { options: lab.options } : {}),
  };
}

function save() {
  try { localStorage.setItem(STORE, JSON.stringify({ teams: lab.teams, map: lab.map, battles: $("battles").value, seed: $("seed").value, threads: $("threads").value, maxTurns: $("max-turns").value, options: lab.options })); } catch (e) { /* storage off: nothing kept */ }
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
    lab.options = saved.options || {};
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
  const left = $("teams-left"), right = $("teams-right"), layer = $("units-float");
  const scroll = lab.teams.map((_, i) => { const l = $(`list-${i}`); return l ? l.scrollTop : 0; });   // a list keeps its place when a unit is added
  left.innerHTML = ""; right.innerHTML = "";
  layer.querySelectorAll(".win.team").forEach((x) => x.remove());
  // odd-numbered teams (1, 3, 5...) in the left column, even ones on the right (Daniel, 2026-11-14)
  lab.teams.forEach((t, ti) => {
    const el = teamPanel(t, ti), key = `team${ti}`;
    if (!applyFloat(el, key)) (ti % 2 === 0 ? left : right).appendChild(el);
    wireWindow(el, key, drawTeams);
    const l = el.querySelector(".list"); if (l) l.scrollTop = scroll[ti] || 0;
  });
  $("team-sum").textContent = `${lab.teams.length} teams, ${lab.teams.reduce((s, t) => s + t.units.length, 0)} units`;
}

// ---------------------------------------------------------------- windows (CL11)
// A panel docks in its column; dragging its title bar pulls it out into a floating window (resize at the corner);
// double-clicking the title docks it again. Positions are kept in the browser (localStorage), "Reset layout" clears them.
const LAYOUT_KEY = "combatlab.layout.v1";
let zTop = 30;
try { lab.layout = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}") || {}; } catch (e) { lab.layout = {}; }
function saveLayout() { try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(lab.layout)); } catch (e) { /* storage off */ } }
const narrow = () => window.matchMedia("(max-width: 900px)").matches;
const clampNum = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const sizeWatch = new ResizeObserver((entries) => {
  for (const e of entries) {
    const f = lab.layout[e.target.dataset.wkey];
    if (f && e.target.classList.contains("float") && (Math.abs(f.w - e.target.offsetWidth) > 1 || Math.abs(f.h - e.target.offsetHeight) > 1)) {
      f.w = e.target.offsetWidth; f.h = e.target.offsetHeight; clearTimeout(sizeWatch.t); sizeWatch.t = setTimeout(saveLayout, 300);
    }
  }
});
// put a panel in the floating layer if its layout says so; false = it stays docked
function applyFloat(el, key) {
  const f = lab.layout[key];
  el.dataset.wkey = key;
  // on a narrow screen everything stays docked in one column
  if (!f || narrow()) { el.classList.remove("float"); el.style.cssText = ""; return false; }
  el.classList.add("float");
  Object.assign(el.style, { left: `${f.x}px`, top: `${f.y}px`, width: `${f.w}px`, height: `${f.h}px`, zIndex: ++zTop });
  $("units-float").appendChild(el);
  sizeWatch.observe(el);
  return true;
}
function wireWindow(el, key, redock) {
  const title = el.querySelector(".wtitle");
  el.addEventListener("pointerdown", () => { if (el.classList.contains("float")) el.style.zIndex = ++zTop; });
  title.addEventListener("dblclick", (e) => {
    if (e.target.closest("button,input,select") || !lab.layout[key]) return;
    delete lab.layout[key]; saveLayout(); sizeWatch.unobserve(el); el.classList.remove("float"); el.style.cssText = ""; redock(el);
  });
  title.addEventListener("pointerdown", (e) => {
    if (e.button || e.target.closest("button,input,select") || narrow()) return;
    const lr = $("units-float").getBoundingClientRect(), r = el.getBoundingClientRect();
    const dx = e.clientX - r.left, dy = e.clientY - r.top, sx = e.clientX, sy = e.clientY;
    let moved = false;
    const move = (m) => {
      if (!moved) {
        if (Math.hypot(m.clientX - sx, m.clientY - sy) < 4) return;
        moved = true;
        if (!el.classList.contains("float")) { lab.layout[key] = { x: r.left - lr.left, y: r.top - lr.top, w: r.width, h: Math.min(r.height, 440) }; applyFloat(el, key); }
      }
      const f = lab.layout[key];
      f.x = clampNum(m.clientX - dx - lr.left, 80 - f.w, lr.width - 80); f.y = clampNum(m.clientY - dy - lr.top, 0, lr.height - 28);
      el.style.left = `${f.x}px`; el.style.top = `${f.y}px`;
    };
    const up = () => { window.removeEventListener("pointermove", move); if (moved) saveLayout(); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up, { once: true });
    e.preventDefault();
  });
}

// weight-class icons (CL12): a grip and a little 'Mech whose build grows with the class
const classOf = (t) => (t == null ? null : t <= 35 ? "light" : t <= 55 ? "medium" : t <= 75 ? "heavy" : t <= 100 ? "assault" : "superheavy");
const CLASS_SHAPES = {
  light: '<circle cx="10" cy="4" r="2.2"/><rect x="8" y="7" width="4" height="6"/><rect x="7" y="13" width="2" height="5"/><rect x="11" y="13" width="2" height="5"/>',
  medium: '<circle cx="10" cy="4" r="2.5"/><rect x="6" y="7" width="8" height="6"/><rect x="4" y="7" width="2" height="6"/><rect x="14" y="7" width="2" height="6"/><rect x="6.5" y="13" width="3" height="5"/><rect x="10.5" y="13" width="3" height="5"/>',
  heavy: '<circle cx="10" cy="3.8" r="2.4"/><rect x="5" y="6.5" width="10" height="7.5"/><rect x="2.5" y="6.5" width="2.5" height="7"/><rect x="15" y="6.5" width="2.5" height="7"/><rect x="5.5" y="14" width="3.5" height="4.5"/><rect x="11" y="14" width="3.5" height="4.5"/>',
  assault: '<circle cx="10" cy="3.5" r="2.4"/><rect x="4" y="6" width="12" height="8.5"/><rect x="1" y="5.5" width="3" height="9"/><rect x="16" y="5.5" width="3" height="9"/><rect x="5" y="14.5" width="4" height="4"/><rect x="11" y="14.5" width="4" height="4"/>',
};
CLASS_SHAPES.superheavy = CLASS_SHAPES.assault;
function classIcon(tons) {
  const c = classOf(tons);
  if (!c) return `<span class="grip">&#8942;&#8942;</span>`;
  const [lo, hi] = CLASSES[c];
  return `<span class="grip">&#8942;&#8942;</span><svg class="cls cls-${c}" viewBox="0 0 20 20" role="img" aria-label="${c}"><title>${c[0].toUpperCase() + c.slice(1)} (${c === "superheavy" ? "over 100" : lo + "-" + hi} t)</title>${CLASS_SHAPES[c]}</svg>`;
}

function teamPanel(t, ti) {
  const el = document.createElement("div");
  el.className = "win team";
  const bots = lab.info.bots.map((b) => `<option value="${b}"${b === t.bot ? " selected" : ""}>${b[0].toUpperCase() + b.slice(1)}</option>`).join("");
  const tons = t.units.reduce((s, u) => s + (u.tons || 0), 0);
  const bv = t.units.reduce((s, u) => s + (unitBv(u) || 0), 0);
  el.innerHTML = `
    <div class="wtitle" id="wt-${ti}" style="border-left-color:${t.colour}" title="Drag to float this panel; double-click to dock it again"><span class="name">Team ${ti + 1}</span><span class="note" style="color:inherit;font-weight:normal">${t.units.length} unit${t.units.length === 1 ? "" : "s"} &middot; ${tons} t &middot; BV ${bv}</span></div>
    <div class="wbody">
    <div class="team-head">
      <label for="tcol-${ti}">Colour <input type="color" id="tcol-${ti}" value="${t.colour}"></label>
      <label for="tname-${ti}">Name <input type="text" id="tname-${ti}" value="${esc(t.name)}" maxlength="24"></label>
      <label for="tbot-${ti}">Bot <select id="tbot-${ti}">${bots}</select></label>
    </div>
    <div class="team-tools">
      <button class="btn" id="addsel-${ti}" ${lab.picked.size ? "" : "disabled"}>Add selected (${lab.picked.size})</button>
      <button class="btn" id="file-${ti}" title="Add a .mtf unit file from this computer">From file&hellip;</button>
      <input type="file" id="fileinput-${ti}" accept=".mtf" multiple hidden>
    </div>
    <div class="adder">
      <input type="search" id="find-${ti}" placeholder="Quick add: type a unit name" autocomplete="off">
      <div class="hits sunken" id="hits-${ti}" hidden></div>
    </div>
    <div class="list sunken" id="list-${ti}"><table>
      <thead><tr><th></th><th>Unit</th><th class="num">Tons</th><th class="num">BV</th><th title="Gunnery skill">G</th><th title="Piloting skill">P</th><th></th></tr></thead>
      <tbody>${t.units.length ? t.units.map((u, ui) => `<tr>
        <td class="ico">${classIcon(u.tons)}</td>
        <td class="name">${esc(u.name)}</td><td class="num">${u.tons ?? ""}</td><td class="num" id="bv-${ti}-${ui}">${unitBv(u) ?? ""}</td>
        <td><input type="number" min="0" max="8" value="${u.gunnery}" id="g-${ti}-${ui}" aria-label="Gunnery"></td>
        <td><input type="number" min="0" max="8" value="${u.piloting}" id="p-${ti}-${ui}" aria-label="Piloting"></td>
        <td><button class="btn small" data-remove="${ui}" title="Remove">&times;</button></td></tr>`).join("")
        : `<tr class="empty"><td colspan="7">No units yet. Drag units here from the Unit Browser, or type a name above.</td></tr>`}</tbody>
    </table></div>
    </div>`;
  const redraw = () => { save(); drawTeams(); };
  el.querySelector(`#tname-${ti}`).addEventListener("change", (e) => {
    const name = e.target.value.trim();
    if (name && !lab.teams.some((o, oi) => oi !== ti && o.name === name)) t.name = name;
    redraw();
  });
  el.querySelector(`#tcol-${ti}`).addEventListener("input", (e) => { t.colour = e.target.value; el.querySelector(".wtitle").style.borderLeftColor = t.colour; save(); });
  el.querySelector(`#tbot-${ti}`).addEventListener("change", (e) => { t.bot = e.target.value; save(); });
  el.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", () => { t.units.splice(+b.dataset.remove, 1); redraw(); }));
  t.units.forEach((u, ui) => {
    // a skill change re-draws the team, so the unit's BV and the team's total follow it
    el.querySelector(`#g-${ti}-${ui}`).addEventListener("change", (e) => { u.gunnery = Math.max(0, Math.min(8, +e.target.value)); redraw(); });
    el.querySelector(`#p-${ti}-${ui}`).addEventListener("change", (e) => { u.piloting = Math.max(0, Math.min(8, +e.target.value)); redraw(); });
  });
  wireSearch(el, t, ti);
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

// ---- advanced search (CL13): Mekbay-style filters. `adv` holds them; drawBrowser applies them.
const ADV_KEY = "combatlab.adv.v1", PRESET_KEY = "combatlab.advpresets.v1";
const ADV_EMPTY = () => ({ ranges: {}, tech: "", source: "", book: "", armor_type: "", structure: "", sets: { config: [], role: [], rules: [] }, playable: true, weapons: [], faction: "", fyear: "" });
let adv = ADV_EMPTY();
let availability = null;          // availability.json (who fielded what, when): loaded the first time a faction is chosen
const RANGES = [["Tons", "tons"], ["Battle Value", "bv"], ["Walk MP", "walk"], ["Jump MP", "jump"], ["Armor points", "armor"], ["Heat sinks", "sinks"], ["Year introduced", "era"]];
const store = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage off */ } };
const fetchStore = (k, d) => { try { return JSON.parse(localStorage.getItem(k) || "null") ?? d; } catch (e) { return d; } };
// an equipment id as the file writes it ("ISERLargeLaser") in words ("ER Large Laser"; Clan ones say so)
function weaponLabel(id) {
  let s = id, clan = false;
  if (/^CL/.test(s)) { clan = true; s = s.slice(2); } else if (/^IS/.test(s)) s = s.slice(2);
  s = s.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2").replace(/([A-Za-z])(\d)/g, "$1 $2");
  return clan ? `${s} (Clan)` : s;
}
const unique = (key) => [...new Set(lab.units.map((u) => u[key]).filter((x) => x !== null && x !== undefined && x !== ""))].sort((a, b) => (typeof a === "number" ? a - b : String(a).localeCompare(String(b))));
const selectHtml = (id, values, label, current) => `<label for="${id}">${label} <select id="${id}"><option value="">Any</option>${values.map((v) => `<option value="${esc(v)}"${String(v) === String(current) ? " selected" : ""}>${esc(v === "project" ? "Project folder" : v)}</option>`).join("")}</select></label>`;
const checksHtml = (name, values, picked) => `<div class="checks">${values.map((v) => `<label class="row"><input type="checkbox" data-set="${name}" value="${esc(v)}" ${picked.includes(String(v)) ? "checked" : ""}> ${esc(v)}</label>`).join("")}</div>`;

function buildAdvanced() {
  const grid = RANGES.map(([label, k]) => `<label>${label} <span class="pair"><input type="number" data-range="${k}" data-end="0" placeholder="min" value="${adv.ranges[k]?.[0] ?? ""}"><input type="number" data-range="${k}" data-end="1" placeholder="max" value="${adv.ranges[k]?.[1] ?? ""}"></span></label>`).join("");
  const wnames = [...new Set(lab.units.flatMap((u) => (u.weapons || []).map((w) => w[0])))].sort((a, b) => weaponLabel(a).localeCompare(weaponLabel(b)));
  lab.weaponNames = wnames;
  const factions = lab.availFactions || [];
  $("adv-body").innerHTML = `
    <fieldset><legend>Numbers</legend><div class="adv-grid">${grid}</div></fieldset>
    <fieldset><legend>Kind</legend><div class="adv-grid">
      ${selectHtml("adv-tech", ["Inner Sphere", "Clan", "Mixed"], "Tech base", adv.tech)}
      ${selectHtml("adv-armor", unique("armor_type"), "Armor type", adv.armor_type)}
      ${selectHtml("adv-structure", unique("structure"), "Structure", adv.structure)}
      ${selectHtml("adv-source", unique("source"), "Unit set", adv.source)}
      <label for="adv-book">Source book contains <input type="text" id="adv-book" value="${esc(adv.book)}" placeholder="e.g. TRO 3050"></label></div>
      <p class="note" style="margin:6px 0 2px">Configuration</p>${checksHtml("config", unique("config"), adv.sets.config)}
      <p class="note" style="margin:6px 0 2px">Role</p>${checksHtml("role", unique("role"), adv.sets.role)}
      <p class="note" style="margin:6px 0 2px">Rules level</p>${checksHtml("rules", unique("rules"), adv.sets.rules)}
    </fieldset>
    <fieldset><legend>Weapons and equipment (all must be carried)</legend><div id="adv-weapons"></div>
      <button class="btn small" id="adv-add-weapon">Add a weapon</button>
      <datalist id="adv-wlist">${wnames.map((n) => `<option value="${esc(weaponLabel(n))}">`).join("")}</datalist></fieldset>
    <fieldset><legend>Who fielded it (MegaMek's availability data)</legend><div class="adv-grid">
      <label for="adv-faction">Faction <select id="adv-faction"><option value="">Any</option>${factions.map((f) => `<option value="${esc(f.key)}"${f.key === adv.faction ? " selected" : ""}>${esc(f.name)}</option>`).join("")}</select></label>
      <label for="adv-fyear">In the year <input type="number" id="adv-fyear" min="2398" max="3200" value="${esc(adv.fyear)}" placeholder="any year"></label></div>
      <p class="note" id="adv-avail-note">Pick a faction to see only the 'Mechs it could field. A year uses the nearest earlier era table; no year means any era. Only 'Mechs MegaMek has availability for can match.</p></fieldset>
    <label class="row" for="adv-playable"><input type="checkbox" id="adv-playable" ${adv.playable ? "checked" : ""}> Playable only (the engine can load them)</label>`;
  drawAdvWeapons();
  const body = $("adv-body");
  const changed = () => { store(ADV_KEY, adv); advCount(); drawBrowser(); };
  body.querySelectorAll("[data-range]").forEach((i) => i.addEventListener("input", () => {
    const k = i.dataset.range, r = adv.ranges[k] || [null, null];
    r[+i.dataset.end] = i.value === "" ? null : +i.value;
    if (r[0] === null && r[1] === null) delete adv.ranges[k]; else adv.ranges[k] = r;
    changed();
  }));
  for (const [id, key] of [["adv-tech", "tech"], ["adv-armor", "armor_type"], ["adv-structure", "structure"], ["adv-source", "source"]]) $(id).addEventListener("change", (e) => { adv[key] = e.target.value; changed(); });
  $("adv-book").addEventListener("input", (e) => { adv.book = e.target.value; changed(); });
  body.querySelectorAll("[data-set]").forEach((i) => i.addEventListener("change", () => {
    const list = adv.sets[i.dataset.set];
    if (i.checked) list.push(i.value); else list.splice(list.indexOf(i.value), 1);
    changed();
  }));
  $("adv-playable").addEventListener("change", (e) => { adv.playable = e.target.checked; changed(); });
  $("adv-faction").addEventListener("change", async (e) => { adv.faction = e.target.value; if (adv.faction) await loadAvailability(); changed(); });
  $("adv-fyear").addEventListener("input", (e) => { adv.fyear = e.target.value; changed(); });
  $("adv-add-weapon").addEventListener("click", () => { adv.weapons.push({ name: "", min: 1 }); drawAdvWeapons(); });
  advCount();
}

function drawAdvWeapons() {
  const box = $("adv-weapons");
  box.innerHTML = adv.weapons.map((w, i) => `<div class="wrow"><input type="text" list="adv-wlist" data-w="${i}" value="${esc(w.name)}" placeholder="weapon name, e.g. ER Large Laser" aria-label="Weapon"><span class="note">at least</span><input type="number" min="1" data-wn="${i}" value="${w.min}" aria-label="Count"><button class="btn small" data-wd="${i}" title="Remove">&times;</button></div>`).join("");
  box.querySelectorAll("[data-w]").forEach((i) => i.addEventListener("input", () => { adv.weapons[+i.dataset.w].name = i.value; store(ADV_KEY, adv); advCount(); drawBrowser(); }));
  box.querySelectorAll("[data-wn]").forEach((i) => i.addEventListener("input", () => { adv.weapons[+i.dataset.wn].min = Math.max(1, +i.value || 1); store(ADV_KEY, adv); drawBrowser(); }));
  box.querySelectorAll("[data-wd]").forEach((b) => b.addEventListener("click", () => { adv.weapons.splice(+b.dataset.wd, 1); drawAdvWeapons(); store(ADV_KEY, adv); advCount(); drawBrowser(); }));
}

async function loadAvailability() {
  if (availability) return;
  $("adv-avail-note").textContent = "Loading availability tables...";
  try {
    const r = await fetch("availability.json");
    availability = r.ok ? await r.json() : { eras: [], factions: [], units: {} };
  } catch (e) { availability = { eras: [], factions: [], units: {} }; }
  $("adv-avail-note").textContent = availability.eras.length ? "A year uses the nearest earlier era table; no year means any era. Only 'Mechs MegaMek has availability for can match." : "No availability data in this copy.";
}

// does a unit pass the advanced filters
function passes(u) {
  if (adv.playable && !u.ok) return false;
  for (const [k, [lo, hi]] of Object.entries(adv.ranges)) {
    const v = u[k]; if (v === null || v === undefined) return false;
    if (lo !== null && v < lo) return false; if (hi !== null && v > hi) return false;
  }
  if (adv.tech && !(u.tech || "").toLowerCase().includes(adv.tech.toLowerCase())) return false;
  if (adv.source && u.source !== adv.source) return false;
  if (adv.armor_type && u.armor_type !== adv.armor_type) return false;
  if (adv.structure && u.structure !== adv.structure) return false;
  if (adv.book && !(u.book || "").toLowerCase().includes(adv.book.toLowerCase())) return false;
  for (const k of ["config", "role", "rules"]) if (adv.sets[k].length && !adv.sets[k].includes(String(u[k]))) return false;
  for (const w of adv.weapons) {
    if (!w.name.trim()) continue;
    const want = w.name.trim().toLowerCase();
    const have = (u.weapons || []).filter((x) => weaponLabel(x[0]).toLowerCase().includes(want)).reduce((s, x) => s + x[1], 0);
    if (have < w.min) return false;
  }
  if (adv.faction && availability) {
    const row = availability.units[u.name]; if (!row) return false;
    const fi = availability.factions.findIndex((f) => f.key === adv.faction);
    const bit = (m) => Math.floor(m / 2 ** fi) % 2 === 1;      // masks have up to 47 bits: no bit operators
    if (adv.fyear === "") return row.some(bit);
    const ei = availability.eras.filter((y) => y <= +adv.fyear).length - 1;
    return ei >= 0 && bit(row[ei]);
  }
  return true;
}

function advCount() {
  const n = Object.keys(adv.ranges).length + ["tech", "source", "book", "armor_type", "structure", "faction"].filter((k) => adv[k]).length +
    Object.values(adv.sets).filter((l) => l.length).length + adv.weapons.filter((w) => w.name.trim()).length + (adv.playable ? 0 : 1);
  $("ub-adv-btn").textContent = n ? `Advanced search (${n})…` : "Advanced search…";
}

function advPresets() {
  const presets = fetchStore(PRESET_KEY, {});
  $("adv-preset").innerHTML = `<option value="">(none)</option>` + Object.keys(presets).map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  return presets;
}

async function initBrowser() {
  adv = { ...ADV_EMPTY(), ...fetchStore(ADV_KEY, {}) };
  adv.sets = { config: [], role: [], rules: [], ...(adv.sets || {}) };
  // the faction list is small: it comes with the availability file, loaded now so the choice list is there; a saved faction filter needs the tables
  try { const r = await fetch("availability.json"); if (r.ok) { availability = await r.json(); lab.availFactions = availability.factions; } } catch (e) { /* demo or no file */ }
  if (adv.faction && !availability) adv.faction = "";
  buildAdvanced();
  advPresets();
  drawBrowser();
}

function drawBrowser() {
  const words = $("ub-name").value.toLowerCase().split(/\s+/).filter(Boolean);
  const cls = CLASSES[$("ub-class").value];
  const list = lab.units.filter((u) => words.every((w) => u.name.toLowerCase().includes(w)) && (!cls || (u.tons >= cls[0] && u.tons <= cls[1])) && passes(u));
  const k = browse.sort, d = browse.dir;
  list.sort((a, b) => ((k === "name" || k === "role") ? String(a[k] ?? "").localeCompare(String(b[k] ?? "")) || a.name.localeCompare(b.name) : ((a[k] ?? -1) - (b[k] ?? -1)) || a.name.localeCompare(b.name)) * d);
  browse.shown = list.slice(0, 400);
  $("ub-count").textContent = `${list.length} unit${list.length === 1 ? "" : "s"}${list.length > 400 ? " (first 400 shown: narrow the search)" : ""}`;
  const body = $("ub-list").tBodies[0];
  body.innerHTML = browse.shown.map((u, i) => `<tr data-i="${i}" draggable="${u.ok}" class="${lab.picked.has(u.id) ? "on" : ""}${u.ok ? "" : " bad"}" title="${esc(u.ok ? "Drag onto a team" : u.why)}">
      <td class="ico">${classIcon(u.tons)}</td><td>${esc(u.name)}</td><td class="num">${u.tons ?? ""}</td><td class="num">${u.bv ?? ""}</td><td class="num">${u.walk ?? ""}/${u.walk != null ? Math.ceil(u.walk * 1.5) : ""}/${u.jump ?? ""}</td><td class="num">${u.armor ?? ""}</td><td>${esc(u.role || "")}</td><td class="num">${u.era ?? ""}</td></tr>`).join("");
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
  lab.teams.forEach((t, ti) => { const b = $(`addsel-${ti}`); if (b) { b.disabled = !lab.picked.size; b.textContent = `Add selected (${lab.picked.size})`; } });
}

// a popup window (Advanced search) moves by its title bar
function wireDialogMove(w, bar) {
  bar.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button")) return;
    const r = w.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
    bar.setPointerCapture(e.pointerId);
    const move = (m) => { w.style.left = `${Math.max(0, m.clientX - dx)}px`; w.style.top = `${Math.max(0, m.clientY - dy)}px`; w.style.marginLeft = "0"; w.style.right = "auto"; };
    bar.addEventListener("pointermove", move);
    bar.addEventListener("pointerup", () => bar.removeEventListener("pointermove", move), { once: true });
  });
}
function wireBrowserWindow() {
  wireWindow($("browser"), "browser", () => $("browser-slot").appendChild($("browser")));
  const key = "browser";
  applyFloat($("browser"), key);
  wireDialogMove($("adv"), $("adv-title"));
  $("ub-adv-btn").addEventListener("click", () => { $("adv").hidden = !$("adv").hidden; });
  $("adv-close").addEventListener("click", () => { $("adv").hidden = true; });
  $("ub-name").addEventListener("input", drawBrowser);
  $("ub-class").addEventListener("change", drawBrowser);
  $("adv-clear").addEventListener("click", () => { adv = ADV_EMPTY(); store(ADV_KEY, adv); buildAdvanced(); drawBrowser(); });
  $("adv-save").addEventListener("click", () => {
    const name = (prompt("Name this search:") || "").trim();
    if (!name) return;
    const presets = fetchStore(PRESET_KEY, {}); presets[name] = adv; store(PRESET_KEY, presets); advPresets(); $("adv-preset").value = name;
  });
  $("adv-preset").addEventListener("change", async (e) => {
    const p = fetchStore(PRESET_KEY, {})[e.target.value]; if (!p) return;
    adv = { ...ADV_EMPTY(), ...JSON.parse(JSON.stringify(p)) }; if (adv.faction) await loadAvailability();
    store(ADV_KEY, adv); buildAdvanced(); drawBrowser();
  });
  $("adv-del").addEventListener("click", () => { const n = $("adv-preset").value; if (!n) return; const p = fetchStore(PRESET_KEY, {}); delete p[n]; store(PRESET_KEY, p); advPresets(); });
  $("ub-clear").addEventListener("click", () => { lab.picked.clear(); pickedChanged(); });
  document.querySelectorAll("#ub-list th[data-sort]").forEach((th) => th.addEventListener("click", () => {
    browse.dir = browse.sort === th.dataset.sort ? -browse.dir : 1; browse.sort = th.dataset.sort; drawBrowser();
  }));
}

// ---------------------------------------------------------------- OPTIONS page (CL15)
async function loadOptions() {
  try {
    const r = await fetch("options.json");
    lab.registry = r.ok ? await r.json() : [];
  } catch (e) { lab.registry = []; }          // the canned demo has no options.json: the tab then shows only the run settings
  // a saved choice for a setting that no longer exists is dropped
  for (const k of Object.keys(lab.options)) if (!lab.registry.some((o) => o.key === k && o.active)) delete lab.options[k];
  drawOptions();
}

const optValue = (o) => (o.key in lab.options ? lab.options[o.key] : o.default);

function optionRow(o) {
  const row = document.createElement("div");
  const id = `opt-${o.key}`;
  row.className = "opt" + (o.active ? "" : " inactive");
  row.dataset.search = `${o.key} ${o.label} ${o.text} ${o.folder}`.toLowerCase();
  const val = optValue(o);
  let control;
  if (o.kind === "bool") control = `<input type="checkbox" id="${id}" ${val ? "checked" : ""} ${o.active ? "" : "disabled"}>`;
  else if (o.kind === "int" || o.kind === "number") control = `<input type="number" id="${id}" step="${o.kind === "int" ? 1 : "any"}" value="${val}" ${o.active ? "" : "disabled"}>`;
  else control = `<input type="text" id="${id}" value="${esc(o.kind === "json" ? JSON.stringify(val) : val ?? "")}" ${o.active ? "" : "disabled"} ${o.default === null ? "placeholder=\"set in the engine\"" : ""}>`;
  row.innerHTML = `<div class="opt-main"><label for="${id}" title="${esc(o.key)}">${esc(o.label)}</label>${control}
      ${o.active ? "" : `<span class="tag off">not active yet</span>`}<span class="tag chg" ${o.key in lab.options ? "" : "hidden"}>changed</span>
      <button class="btn small" data-reset ${o.key in lab.options ? "" : "hidden"} title="Back to ${esc(JSON.stringify(o.default))}">Reset</button></div>
    ${o.short ? `<p class="note desc" title="${esc(o.text)}">${esc(o.short)}</p>` : ""}`;
  if (!o.active) return row;
  const input = row.querySelector("input");
  const changed = () => {
    const on = o.key in lab.options;
    row.classList.toggle("changed", on);
    row.querySelector(".tag.chg").hidden = !on; row.querySelector("[data-reset]").hidden = !on;
    save(); optionCounts();
  };
  input.addEventListener("change", () => {
    let v;
    if (o.kind === "bool") v = input.checked;
    else if (o.kind === "int" || o.kind === "number") { v = o.kind === "int" ? Math.round(+input.value) : +input.value; if (input.value === "" || Number.isNaN(v)) { input.classList.add("bad"); return; } }
    else if (o.kind === "json") { try { v = JSON.parse(input.value); } catch (e) { input.classList.add("bad"); setStatus(`${o.label}: that is not valid JSON`); return; } }
    else v = input.value;
    input.classList.remove("bad");
    if (JSON.stringify(v) === JSON.stringify(o.default)) delete lab.options[o.key]; else lab.options[o.key] = v;
    changed();
  });
  row.querySelector("[data-reset]").addEventListener("click", () => {
    delete lab.options[o.key];
    if (o.kind === "bool") input.checked = !!o.default; else input.value = o.kind === "json" ? JSON.stringify(o.default) : o.default;
    input.classList.remove("bad"); changed();
  });
  if (o.key in lab.options) row.classList.add("changed");
  return row;
}

function drawOptions() {
  for (const [top, id] of [["Game setup", "opt-folders-game"], ["Bot features", "opt-folders-bots"]]) {
    const box = $(id); box.innerHTML = "";
    const folders = [...new Set(lab.registry.filter((o) => o.top === top).map((o) => o.folder))];
    for (const f of folders) {
      const d = document.createElement("details");
      d.className = "folder"; d.dataset.folder = f;
      const items = lab.registry.filter((o) => o.top === top && o.folder === f);
      // folders that are mostly inert (debug switches, a bot with nothing wired) start closed
      d.open = items.some((o) => o.active) && f !== "Technical and debugging";
      d.innerHTML = `<summary>${esc(f)} <span class="note">(${items.filter((o) => o.active).length} active of ${items.length})</span></summary>`;
      items.forEach((o) => d.appendChild(optionRow(o)));
      box.appendChild(d);
    }
  }
  optionCounts(); filterOptions();
}

function optionCounts() {
  const n = Object.keys(lab.options).length;
  $("opt-count").textContent = n ? `${n} option${n === 1 ? "" : "s"} changed from the defaults` : "All options at their defaults";
  $("opt-reset-all").disabled = !n;
}

// the search: every word must appear in a row's name, key, description or folder; folders with no hit disappear and
// folders with hits open; each sub-tab says how many hits it holds
function filterOptions() {
  const words = $("opt-search").value.toLowerCase().split(/\s+/).filter(Boolean);
  const hits = { game: 0, bots: 0 };
  for (const pane of ["game", "bots"]) {
    document.querySelectorAll(`#opt-pane-${pane} details.folder`).forEach((d) => {
      let any = 0;
      d.querySelectorAll(".opt, p[data-search]").forEach((r) => {
        const show = words.every((w) => r.dataset.search.includes(w));
        r.hidden = !show; if (show) any++;
      });
      d.hidden = words.length > 0 && !any;
      if (words.length && any) d.open = true;
      hits[pane] += any;
    });
  }
  const label = { game: "Game setup", bots: "Bot features" };
  document.querySelectorAll(".subtab").forEach((b) => { b.textContent = words.length ? `${label[b.dataset.pane]} (${hits[b.dataset.pane]})` : label[b.dataset.pane]; });
  if (words.length) {
    const cur = document.querySelector('.subtab[aria-selected="true"]').dataset.pane;
    if (!hits[cur] && hits[cur === "game" ? "bots" : "game"]) showOptionPane(cur === "game" ? "bots" : "game");
  }
  $("opt-none").hidden = !(words.length && !hits.game && !hits.bots);
}

function showOptionPane(pane) {
  document.querySelectorAll(".subtab").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.pane === pane)));
  $("opt-pane-game").hidden = pane !== "game"; $("opt-pane-bots").hidden = pane !== "bots";
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

// ---------------------------------------------------------------- the map preview (CL14)
// Heights are shown the way MegaMek's board view does: a colour ramp from the low ground (dark green) up through
// yellow and brown to white, so a ridge or a pit reads at a glance; terrain is laid over the height colour.
const LEVEL_RAMP = { "-3": "#2f4d2c", "-2": "#3e6335", "-1": "#55803f", 0: "#76a35a", 1: "#98b865", 2: "#bfc86e", 3: "#dbc77a", 4: "#d2ad6a", 5: "#c4915c", 6: "#b07a52", 7: "#9c6a4b", 8: "#8a5c46", 9: "#c9b6ab", 10: "#e6ddd8", 11: "#ffffff" };
const levelColour = (l) => LEVEL_RAMP[Math.max(-3, Math.min(11, l))];
const boardCache = new Map();
function parseBoardText(text) {
  const b = { w: 0, h: 0, hexes: new Map() };
  for (const line of text.split("\n")) {
    const size = /^size\s+(\d+)\s+(\d+)/.exec(line);
    if (size) { b.w = +size[1]; b.h = +size[2]; continue; }
    const hex = /^hex\s+(\d{2})(\d{2})\s+(-?\d+)\s+"([^"]*)"/.exec(line);
    if (!hex) continue;
    const feats = {};
    for (const part of hex[4].split(";")) { const [name, ...rest] = part.split(":"); if (name) feats[name.trim()] = rest; }
    b.hexes.set(`${+hex[1]},${+hex[2]}`, { level: +hex[3], f: feats });
  }
  return b;
}
async function getBoard(id) {
  if (!boardCache.has(id)) boardCache.set(id, api("board", { id }).then((r) => (r.error ? null : parseBoardText(r.text))));
  return boardCache.get(id);
}
// the place of the chosen map: [{board, ox, oy}] with its total size, or null when it is not ready
async function mapParts() {
  const m = lab.map;
  if (m.mode === "one" || m.mode === "playlist") {
    const id = m.mode === "one" ? m.one : (m.playlist || [])[0];
    const b = id && (await getBoard(id)); return b ? { w: b.w, h: b.h, cells: [{ board: b, ox: 0, oy: 0 }] } : null;
  }
  if (m.cells.some((c) => !lab.boardById.has(c)) || !mapCheck().ok) return null;
  const boards = await Promise.all(m.cells.map(getBoard));
  if (boards.some((b) => !b)) return null;
  const cells = []; let oy = 0, W = 0;
  for (let r = 0; r < m.rows; r++) {
    let ox = 0;
    for (let c = 0; c < m.cols; c++) { const b = boards[r * m.cols + c]; cells.push({ board: b, ox, oy }); ox += b.w; }
    W = ox; oy += boards[r * m.cols].h;
  }
  return { w: W, h: oy, cells };
}
// draw a map into a canvas as wide as its box; zones = [{boxes: [9 booleans, row by row from NW], colour, label}] shades the starting zones
function paintMap(canvas, parts, zones) {
  const dpr = window.devicePixelRatio || 1, cssW = Math.max(200, canvas.parentElement.clientWidth - 20);
  const R = cssW / (1.5 * parts.w + 0.5), SQ = Math.sqrt(3);
  const cssH = SQ * R * (parts.h + 0.5);
  canvas.style.height = `${cssH}px`; canvas.width = Math.round(cssW * dpr); canvas.height = Math.round(cssH * dpr);
  const g = canvas.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, cssW, cssH);
  const centre = (c, r) => [R + (c - 1) * 1.5 * R, (SQ / 2) * R + (r - 1) * SQ * R + (c % 2 === 0 ? (SQ / 2) * R : 0)];
  const path = (x, y, k) => { g.beginPath(); for (let i = 0; i < 6; i++) { const a = Math.PI / 3 * i; g.lineTo(x + k * R * Math.cos(a), y + k * R * Math.sin(a)); } g.closePath(); };
  const showLevels = R >= 11;
  for (const { board, ox, oy } of parts.cells) {
    for (const [key, hex] of board.hexes) {
      const [c0, r0] = key.split(",").map(Number), c = c0 + ox, r = r0 + oy, [x, y] = centre(c, r), f = hex.f;
      path(x, y, 1); g.fillStyle = levelColour(hex.level); g.fill();
      const wood = f.woods || f.jungle, water = f.water && f.water[0] !== "0";
      if (water) { g.fillStyle = `rgba(30,90,200,${Math.min(0.85, 0.45 + 0.15 * (+f.water[0] || 1))})`; path(x, y, 1); g.fill(); }
      if (f.magma) { g.fillStyle = "rgba(220,60,10,.7)"; path(x, y, 1); g.fill(); }
      if (f.hazardous_liquid) { g.fillStyle = "rgba(130,40,170,.6)"; path(x, y, 1); g.fill(); }
      if (f.pavement || f.road) { g.fillStyle = "rgba(110,110,110,.55)"; path(x, y, f.pavement ? 1 : 0.45); g.fill(); }
      if (f.rough || f.rubble) { g.fillStyle = "rgba(90,60,30,.45)"; for (let i = 0; i < 3; i++) { g.beginPath(); g.arc(x + (i - 1) * R * 0.4, y + (i % 2 ? 0.25 : -0.25) * R, R * 0.15, 0, 7); g.fill(); } }
      if (f.sand) { g.fillStyle = "rgba(240,215,110,.5)"; path(x, y, 1); g.fill(); }
      if (f.ice) { g.fillStyle = "rgba(220,245,255,.65)"; path(x, y, 1); g.fill(); }
      if (wood) { g.fillStyle = `rgba(15,80,25,${String(wood[0]) === "1" ? 0.5 : 0.75})`; path(x, y, 0.72); g.fill(); }
      if (f.building) { g.fillStyle = "rgba(60,60,70,.85)"; g.fillRect(x - R * 0.45, y - R * 0.4, R * 0.9, R * 0.8); }
      path(x, y, 1); g.strokeStyle = "rgba(0,0,0,.28)"; g.lineWidth = 0.6; g.stroke();
      if (showLevels && hex.level !== 0) { g.fillStyle = hex.level > 8 || hex.level < -1 ? "#fff" : "#222"; g.font = `${Math.round(R * 0.5)}px sans-serif`; g.textAlign = "center"; g.fillText(hex.level, x, y + R * 0.7); }
    }
  }
  // starting zones: a shade over the hexes of each team's boxes, and the team's name in the middle of each box
  (zones || []).forEach((z, zi) => {
    for (let r = 1; r <= parts.h; r++) for (let c = 1; c <= parts.w; c++) {
      const box = Math.min(2, Math.floor(((r - 1) * 3) / parts.h)) * 3 + Math.min(2, Math.floor(((c - 1) * 3) / parts.w));
      if (!z.boxes[box]) continue;
      const [x, y] = centre(c, r); path(x, y, 1);
      g.fillStyle = z.colour + "55"; g.fill();
    }
    g.font = `bold ${Math.max(10, Math.round(R * 0.9))}px sans-serif`; g.textAlign = "center";
    z.boxes.forEach((on, box) => {
      if (!on) return;
      const bx = (box % 3 + 0.5) / 3, by = (Math.floor(box / 3) + 0.5) / 3;
      const lx = cssW * bx, ly = cssH * by + (zi - (zones.length - 1) / 2) * Math.max(11, R);
      g.fillStyle = "rgba(255,255,255,.85)"; g.fillRect(lx - g.measureText(z.label).width / 2 - 3, ly - R * 0.8, g.measureText(z.label).width + 6, R * 1.05);
      g.fillStyle = z.colour; g.fillText(z.label, lx, ly);
    });
  });
}
let previewToken = 0;
async function drawPreview() {
  const token = ++previewToken, canvas = $("map-preview");
  const parts = await mapParts();
  if (token !== previewToken) return;
  canvas.hidden = !parts; $("map-legend").hidden = !parts;
  if (!parts) return;
  paintMap(canvas, parts, lab.zonesOverlay ? lab.zonesOverlay() : null);
  $("map-legend").innerHTML = [-2, 0, 2, 4, 6, 8, 10].map((l) => `<span><i style="background:${levelColour(l)}"></i>${l === 10 ? "10+" : l}</span>`).join("") +
    `<span><i style="background:#1e5ac8"></i>Water</span><span><i style="background:#2d5a2a"></i>Woods</span><span><i style="background:#6e6e6e"></i>Road / paving</span><span><i style="background:#5a3c1e"></i>Rough</span><span><i style="background:#3c3c46"></i>Building</span>`;
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
  drawPreview();
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
  lab.units.forEach((x) => { if (!x.name.trim()) x.name = x.id.replace(/\.mtf$/i, ""); lab.byId.set(x.id, x); });   // a unit file with no chassis/model line shows its file name
  lab.boards.forEach((x) => lab.boardById.set(x.id, x));
  const sizes = [...new Set(lab.boards.map((x) => `${x.width}x${x.height}`))].sort((p, q) => parseInt(p) - parseInt(q) || p.localeCompare(q, undefined, { numeric: true }));
  $("board-size").innerHTML = `<option value="">Any</option>` + sizes.map((s) => `<option>${s}</option>`).join("");
  restore();
  drawTeams();
  drawBoards();
  wireBrowserWindow();
  await initBrowser();
  await loadOptions();
  pickedChanged();
  setStatus("Ready", `${lab.units.length} units, ${lab.boards.length} boards, ${lab.info.cores} cores`);

  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => show(t.dataset.page)));
  $("team-count").addEventListener("change", (e) => setTeamCount(+e.target.value));
  ["battles", "seed", "threads", "max-turns"].forEach((id) => $(id).addEventListener("change", save));
  $("estimate-btn").addEventListener("click", estimate);
  $("run-btn").addEventListener("click", runBatch);
  $("opt-search").addEventListener("input", filterOptions);
  document.querySelectorAll(".subtab").forEach((b) => b.addEventListener("click", () => showOptionPane(b.dataset.pane)));
  $("opt-reset-all").addEventListener("click", () => { lab.options = {}; save(); drawOptions(); });
  $("reset-layout").addEventListener("click", () => {
    lab.layout = {}; saveLayout();
    const b = $("browser"); sizeWatch.unobserve(b); b.classList.remove("float"); b.style.cssText = ""; $("browser-slot").appendChild(b);
    drawTeams();
  });
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
  let wasNarrow = narrow();
  window.addEventListener("resize", () => { if (narrow() !== wasNarrow) { wasNarrow = narrow(); location.reload(); } });
  if (DEMO && DEMO.autorun) runBatch();
}

start();
