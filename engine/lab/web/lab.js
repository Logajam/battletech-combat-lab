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

const lab = { addTo: 0,
  info: null, units: [], boards: [], byId: new Map(), boardById: new Map(),
  teams: [],
  map: { mode: "one", one: null, cols: 2, rows: 1, cells: [null, null], cell: 0, playlist: [], order: "sequence" },
  deploy: { mode: "rulebook", opposite: false },   // starting zones (CL14): "rulebook" = the Core Rulebook deployment, else fixed / rotating / random
  run: null, runSetup: null, filter: {}, poll: null,
  picked: new Set(),            // units selected in the unit browser
  options: {}, registry: [],    // the Options tab: changed settings {NAME: value}, and the list of every setting
};

// ---------------------------------------------------------------- talking to the server
async function api(name, body) {
  if (DEMO) return demoApi(name, body || {});
  if (window.LAB_WASM) return window.LAB_WASM.api(name, body || {});   // the browser build (engine/wasm): this computer plays the battles
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
  const base = u.mtf ? u.bv : (lab.byId.get(u.id) || {}).bv;        // a modified unit carries its own BV
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
  if (m.mode === "playlist") return { playlist: m.playlist, order: m.order };
  const grid = [];
  for (let r = 0; r < m.rows; r++) grid.push(m.cells.slice(r * m.cols, (r + 1) * m.cols));
  return { grid };
}

function setup() {
  return {
    teams: lab.teams.map((t, ti) => ({ name: t.name, colour: t.colour, bot: t.bot, units: t.units.map((u) => (u.mtf ? { unit: u.base || u.id, mtf_text: u.mtf, gunnery: u.gunnery, piloting: u.piloting } : { unit: u.id, gunnery: u.gunnery, piloting: u.piloting })),
      ...(lab.deploy.mode !== "rulebook" ? { zone: zoneOf(t, ti) } : {}) })),
    ...(lab.deploy.mode !== "rulebook" ? { zone_mode: lab.deploy.mode, zone_opposite: lab.deploy.mode === "random" && lab.deploy.opposite && lab.teams.length === 2 } : {}),
    board: boardOfSetup(),
    battles: +$("battles").value || 20,
    seed: +$("seed").value || 0,
    threads: +$("threads").value || 0,
    ...($("full-power").checked ? { full_power: true } : {}),
    max_turns: +$("max-turns").value || 100,
    ...(Object.keys(lab.options).length ? { options: lab.options } : {}),
  };
}

function save() {
  try { localStorage.setItem(STORE, JSON.stringify({ teams: lab.teams, map: lab.map, battles: $("battles").value, seed: $("seed").value, threads: $("threads").value, fullPower: $("full-power").checked, maxTurns: $("max-turns").value, options: lab.options, deploy: lab.deploy })); } catch (e) { /* storage off: nothing kept */ }
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
    lab.teams = saved.teams.map((t) => ({ ...t, units: t.units.map((u) => (u.mtf ? modifiedEntry(u.mtf, u.base || u.id, u.gunnery, u.piloting, { bv: u.bv }) : unitEntry(u.id, u.gunnery, u.piloting))).filter(Boolean) }));
    lab.map = { ...lab.map, ...saved.map };
    lab.options = saved.options || {};
    lab.deploy = { ...lab.deploy, ...(saved.deploy || {}) };
    $("battles").value = saved.battles || 20; $("seed").value = saved.seed && saved.seed !== "1" ? saved.seed : "";   // an empty box = a new seed each run (the old default, 1, is dropped)
    $("threads").value = saved.threads || 0; $("max-turns").value = saved.maxTurns || 100;
    $("full-power").checked = !!saved.fullPower; $("threads").disabled = $("full-power").checked;
  } else {
    const start = DEMO ? DEMO.setup : { teams: [{ name: "Red", bot: "gladiator", units: [{ unit: "Atlas AS7-K.mtf" }, { unit: "Griffin GRF-1N.mtf" }] },
      { name: "Blue", bot: "gladiator", units: [{ unit: "Awesome AWS-8Q.mtf" }, { unit: "Hunchback HBK-4G.mtf" }] }], board: lab.info.default_board, battles: 20, seed: "" };
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
    dockSize(el, key);
    const l = el.querySelector(".list"); if (l) l.scrollTop = scroll[ti] || 0;
  });
  drawAddTo();
  fitZoneLines();
  $("team-sum").textContent = `${lab.teams.length} teams, ${lab.teams.reduce((s, t) => s + t.units.length, 0)} units`;
  paintZoneGrids();
}

// ---------------------------------------------------------------- windows (CL11)
// A panel docks in its column; dragging its title bar pulls it out into a floating window (resize at the corner);
// double-clicking the title docks it again. Positions are kept in the browser (localStorage), "Reset layout" clears them.
const LAYOUT_KEY = "combatlab.layout.v1";
let zTop = 30;
const raiseWindow = (el) => { el.style.zIndex = ++zTop; };         // a window that opens, or is clicked, goes on top of the others
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
    <div class="team-zone" id="zmini-${ti}"></div>
    <div class="list sunken" id="list-${ti}"><table>
      <thead><tr><th data-ck="ico"></th><th data-ck="name">Unit</th><th data-ck="tons" class="num">Tons</th><th data-ck="bv" class="num">BV</th><th data-ck="g" title="Gunnery skill">G</th><th data-ck="p" title="Piloting skill">P</th><th data-ck="x"></th></tr></thead>
      <tbody>${t.units.length ? t.units.map((u, ui) => `<tr>
        <td class="ico">${classIcon(u.tons)}</td>
        <td class="name">${esc(u.name)}</td><td class="num">${u.tons ?? ""}</td><td class="num" id="bv-${ti}-${ui}">${unitBv(u) ?? ""}</td>
        <td><input type="number" min="0" max="8" value="${u.gunnery}" id="g-${ti}-${ui}" aria-label="Gunnery"></td>
        <td><input type="number" min="0" max="8" value="${u.piloting}" id="p-${ti}-${ui}" aria-label="Piloting"></td>
        <td class="acts"><button class="btn small" data-edit="${ui}" title="Edit this unit's stats and equipment">&#9998;</button><button class="btn small" data-remove="${ui}" title="Remove">&times;</button></td></tr>`).join("")
        : `<tr class="empty"><td colspan="7">No units yet. Pick the team in the Unit Browser\'s "Add to" box, or drag units here.</td></tr>`}</tbody>
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
  el.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => openSheet(t.units[+b.dataset.edit].id, ti, +b.dataset.edit)));
  el.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", () => { t.units.splice(+b.dataset.remove, 1); redraw(); }));
  t.units.forEach((u, ui) => {
    // a skill change re-draws the team, so the unit's BV and the team's total follow it
    el.querySelector(`#g-${ti}-${ui}`).addEventListener("change", (e) => { u.gunnery = Math.max(0, Math.min(8, +e.target.value)); redraw(); });
    el.querySelector(`#p-${ti}-${ui}`).addEventListener("change", (e) => { u.piloting = Math.max(0, Math.min(8, +e.target.value)); redraw(); });
  });
  el.querySelector(`#zmini-${ti}`).replaceWith(zoneGrid(ti, true));
  colResize(el.querySelector(".list table"), "team");
  const files = (list) => addFiles(t, list);
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

// a .mtf file (dropped on a team panel, or picked with the browser's From file...) is copied into the project and added
async function addFiles(t, list) {
  for (const f of list) {
    if (!f.name.toLowerCase().endsWith(".mtf")) { setStatus(`${f.name}: only .mtf unit files can be added`); continue; }
    const r = await api("add_unit", { file: f.name, text: await f.text() });
    if (r.error) { setStatus(`${f.name}: ${r.error}`); continue; }
    if (!lab.byId.has(r.unit.id)) { lab.units.push(r.unit); lab.byId.set(r.unit.id, r.unit); }
    t.units.push(unitEntry(r.unit.id));
    setStatus(r.copied ? `${r.unit.name} copied into the project's unit folder and added` : `${r.unit.name} added (already in the project)`);
  }
  save(); drawTeams();
}

// ---------------------------------------------------------------- sizes (Daniel, 2026-11-15)
// Column widths: drag the right edge of a header. The widths are kept per table kind ("ub" = the Unit Browser, "team") in the
// layout; a table with saved widths gets a fixed layout, wider than its box if need be (the box scrolls sideways).
function colResize(table, kind) {
  const ths = [...table.tHead.rows[0].cells];
  const saved = (lab.layout.cols && lab.layout.cols[kind]) || {};
  const total = () => ths.reduce((n, th) => n + (parseFloat(th.style.width) || 0), 0);
  const fix = (widths) => { table.style.tableLayout = "fixed"; ths.forEach((th, i) => { th.style.width = `${widths[i]}px`; }); table.style.width = `${total()}px`; };
  if (ths.some((th) => saved[th.dataset.ck])) fix(ths.map((th) => saved[th.dataset.ck] || (th.dataset.ck === "name" ? 170 : th.dataset.ck === "ico" ? 40 : 60)));
  ths.forEach((th, i) => {
    if (th.dataset.ck === "ico" || th.dataset.ck === "eye") return;
    const h = document.createElement("span"); h.className = "rz"; h.title = "Drag to resize the column; double-click to reset all widths";
    h.addEventListener("click", (e) => e.stopPropagation());
    h.addEventListener("dblclick", (e) => { e.stopPropagation(); if (lab.layout.cols) delete lab.layout.cols[kind]; saveLayout(); table.style.tableLayout = ""; table.style.width = ""; ths.forEach((t) => { t.style.width = ""; }); });
    h.addEventListener("pointerdown", (e) => {
      e.preventDefault(); e.stopPropagation();
      if (table.style.tableLayout !== "fixed") fix(ths.map((t) => t.getBoundingClientRect().width));
      const x0 = e.clientX, w0 = parseFloat(th.style.width);
      const move = (m) => { th.style.width = `${Math.max(22, w0 + m.clientX - x0)}px`; table.style.width = `${total()}px`; };
      const up = () => {
        window.removeEventListener("pointermove", move);
        lab.layout.cols = lab.layout.cols || {}; lab.layout.cols[kind] = Object.fromEntries(ths.map((t) => [t.dataset.ck, parseFloat(t.style.width)])); saveLayout();
      };
      window.addEventListener("pointermove", move); window.addEventListener("pointerup", up, { once: true });
    });
    th.appendChild(h);
  });
}

// The team columns can be made wider or narrower (Daniel, 2026-11-17: "Teams boxes should be allowed to be expanded sideways
// too"): the grips between them and the Unit Browser are dragged sideways; the widths are kept in the layout (double-click a
// grip, or Reset layout, to go back to the default shares). The browser keeps at least 360 px.
function deskColumns() {
  const L = lab.layout.deskL, R = lab.layout.deskR;
  $("page-units").querySelector(".units-desk").style.gridTemplateColumns =
    L || R ? `${L ? `${L}px` : "minmax(250px, 1fr)"} 8px minmax(360px, 1.5fr) 8px ${R ? `${R}px` : "minmax(250px, 1fr)"}` : "";
}
function wireColumnGrips() {
  const desk = $("page-units").querySelector(".units-desk");
  for (const [id, side] of [["grip-left", "deskL"], ["grip-right", "deskR"]]) {
    const g = $(id);
    g.addEventListener("pointerdown", (e) => {
      if (e.button || narrow()) return;
      e.preventDefault(); g.setPointerCapture(e.pointerId); g.classList.add("dragging");
      const move = (m) => {
        const d = desk.getBoundingClientRect();
        const other = side === "deskL" ? $("teams-right").getBoundingClientRect().width : $("teams-left").getBoundingClientRect().width;
        const max = d.width - other - 16 - 360;
        lab.layout[side] = Math.round(clampNum(side === "deskL" ? m.clientX - d.left : d.right - m.clientX, 180, Math.max(180, max)));
        deskColumns();
      };
      const up = () => { g.removeEventListener("pointermove", move); g.classList.remove("dragging"); saveLayout(); fitZoneLines(); };
      g.addEventListener("pointermove", move);
      g.addEventListener("pointerup", up, { once: true });
    });
    g.addEventListener("dblclick", () => { delete lab.layout[side]; saveLayout(); deskColumns(); fitZoneLines(); });
  }
  deskColumns();
}

// A docked team panel can be pulled taller or shorter by its bottom corner; the height is kept. Double-click its title to clear it.
function dockSize(el, key) {
  const h = lab.layout["dh_" + key];
  if (h && !narrow() && !el.classList.contains("float")) { el.style.height = `${h}px`; el.classList.add("sized"); }
  el.addEventListener("pointerdown", (e) => {
    if (el.classList.contains("float") || narrow()) return;
    const r = el.getBoundingClientRect();
    if (e.clientX < r.right - 20 || e.clientY < r.bottom - 20) return;         // only the resize corner
    const before = r.height;
    el.style.height = `${before}px`; el.classList.add("sized");
    window.addEventListener("pointerup", () => {
      const now = el.getBoundingClientRect().height;
      if (Math.abs(now - before) < 2 && !lab.layout["dh_" + key]) { el.style.height = ""; el.classList.remove("sized"); return; }
      lab.layout["dh_" + key] = now; saveLayout();
    }, { once: true });
  });
  el.querySelector(".wtitle").addEventListener("dblclick", () => {
    if (!lab.layout["dh_" + key]) return;
    delete lab.layout["dh_" + key]; saveLayout(); el.style.height = ""; el.classList.remove("sized");
  });
}

// The browser's list fills the window down to the bottom of the screen; pulling its bottom corner locks it at that height
// (kept in the layout) until Reset layout. On a narrow screen the page itself sets the height.
function lockBrowserList(h) {
  const l = document.querySelector(".ub-list"); if (!l) return;
  if (h && !narrow()) { l.style.flex = "none"; l.style.height = `${h}px`; } else { l.style.flex = ""; l.style.height = ""; }
}
function wireBrowserList() {
  const l = document.querySelector(".ub-list");
  lockBrowserList(lab.layout.ubH);
  l.addEventListener("pointerdown", (e) => {
    if (narrow()) return;
    const r = l.getBoundingClientRect();
    if (e.clientX < r.right - 20 || e.clientY < r.bottom - 20) return;
    const before = r.height;
    l.style.flex = "none"; l.style.height = `${before}px`;
    window.addEventListener("pointerup", () => {
      const now = l.getBoundingClientRect().height;
      if (Math.abs(now - before) < 2) { lockBrowserList(lab.layout.ubH); return; }
      lab.layout.ubH = now; saveLayout();
    }, { once: true });
  });
}

// The start line on a team panel always tries to be one line: the text shrinks until it fits (never below 7 px; then it wraps).
function fitZoneLines() {
  document.querySelectorAll(".zone-mini").forEach((w) => {
    w.style.flexWrap = "nowrap";
    let fs = 12; w.style.fontSize = `${fs}px`;
    while (w.scrollWidth > w.clientWidth + 1 && fs > 7) { fs -= 0.5; w.style.fontSize = `${fs}px`; }
    if (w.scrollWidth > w.clientWidth + 1) w.style.flexWrap = "wrap";
  });
}
window.addEventListener("resize", () => fitZoneLines());
if (window.ResizeObserver) { const zw = new ResizeObserver(() => fitZoneLines()); window.addEventListener("load", () => document.querySelectorAll("#teams-left, #teams-right").forEach((c) => zw.observe(c))); }

// the Unit Browser's "Add to" row (MegaMek style): choose the team once, then add the selection, a double-clicked unit, or a file
function drawAddTo() {
  const sel = $("ub-addto");
  if (!lab.teams[lab.addTo]) lab.addTo = 0;
  sel.innerHTML = lab.teams.map((t, i) => `<option value="${i}">${i + 1}: ${esc(t.name)}</option>`).join("");
  sel.value = lab.addTo;
  const b = $("ub-add"); b.disabled = !lab.picked.size; b.textContent = `Add selected (${lab.picked.size})`;
}

function setTeamCount(n) {
  n = Math.max(2, Math.min(999, n || 2));
  while (lab.teams.length < n) {
    const i = lab.teams.length;
    lab.teams.push({ name: freshTeamName(i), colour: defaultColour(i), bot: "gladiator", units: [] });
  }
  lab.teams.length = n;
  $("team-count").value = n;
  save(); drawTeams(); drawZones();
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
// armor and structure types are spelled a few ways in the unit files ("Hardened(Clan)" and "Hardened (Clan)", "Endo-Steel" and "Endo Steel"):
// one entry in the list for each, found by the text without spaces, hyphens and capitals, shown in its commonest spelling
const typeKey = (s) => String(s ?? "").toLowerCase().replace(/[\s\-_]+/g, "");
function uniqueTypes(key) {
  const groups = new Map();
  for (const u of lab.units) { const v = u[key]; if (!v) continue; const g = groups.get(typeKey(v)) || new Map(); g.set(v, (g.get(v) || 0) + 1); groups.set(typeKey(v), g); }
  return [...groups.values()].map((g) => [...g.entries()].sort((a, b) => b[1] - a[1])[0][0]).sort((a, b) => a.localeCompare(b));
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
      ${selectHtml("adv-armor", uniqueTypes("armor_type"), "Armor type", adv.armor_type)}
      ${selectHtml("adv-structure", uniqueTypes("structure"), "Structure", adv.structure)}
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
  if (adv.armor_type && typeKey(u.armor_type) !== typeKey(adv.armor_type)) return false;
  if (adv.structure && typeKey(u.structure) !== typeKey(adv.structure)) return false;
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

// The table's columns (Daniel, 2026-11-15): Unit, Tons and BV are always there; every other column appears only while the
// search uses it (a range, a pick list or a weapon), so a plain browse stays narrow. `on` says when; `show` is the cell.
const COLS = [
  { key: "move", head: "Move", title: "Walk / run / jump MP", num: true, on: () => "walk" in adv.ranges || "jump" in adv.ranges, show: (u) => `${u.walk ?? ""}/${u.walk != null ? Math.ceil(u.walk * 1.5) : ""}/${u.jump ?? ""}`, sort: "walk" },
  { key: "armor", head: "Armor", num: true, on: () => "armor" in adv.ranges, show: (u) => u.armor ?? "" },
  { key: "sinks", head: "Sinks", title: "Heat sinks", num: true, on: () => "sinks" in adv.ranges, show: (u) => u.sinks ?? "" },
  { key: "era", head: "Year", num: true, on: () => "era" in adv.ranges || adv.fyear !== "", show: (u) => u.era ?? "" },
  { key: "role", head: "Role", on: () => adv.sets.role.length > 0, show: (u) => u.role || "" },
  { key: "config", head: "Type", on: () => adv.sets.config.length > 0, show: (u) => u.config || "" },
  { key: "rules", head: "Rules", title: "Rules level", num: true, on: () => adv.sets.rules.length > 0, show: (u) => u.rules ?? "" },
  { key: "tech", head: "Tech", on: () => !!adv.tech, show: (u) => u.tech || "" },
  { key: "armor_type", head: "Armor type", on: () => !!adv.armor_type, show: (u) => u.armor_type || "" },
  { key: "structure", head: "Structure", on: () => !!adv.structure, show: (u) => u.structure || "" },
  { key: "book", head: "Book", on: () => !!adv.book, show: (u) => u.book || "" },
  { key: "weapons", head: "Weapons", title: "How many of each searched weapon the unit carries", on: () => adv.weapons.some((w) => w.name.trim()), sortable: false,
    show: (u) => adv.weapons.filter((w) => w.name.trim()).map((w) => (u.weapons || []).filter((x) => weaponLabel(x[0]).toLowerCase().includes(w.name.trim().toLowerCase())).reduce((n, x) => n + x[1], 0)).join(" / ") },
];
const EYE = '<svg class="eye" viewBox="0 0 20 12" width="16" height="10" aria-label="Preview"><path d="M1 6 C4 1.5 16 1.5 19 6 C16 10.5 4 10.5 1 6 Z" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="10" cy="6" r="2.4" fill="currentColor"/></svg>';
const STRING_SORTS = new Set(["name", "role", "config", "tech", "armor_type", "structure", "book"]);

function drawBrowser() {
  const words = $("ub-name").value.toLowerCase().split(/\s+/).filter(Boolean);
  const cls = CLASSES[$("ub-class").value];
  const list = lab.units.filter((u) => words.every((w) => u.name.toLowerCase().includes(w)) && (!cls || (u.tons >= cls[0] && u.tons <= cls[1])) && passes(u));
  const cols = COLS.filter((c) => c.on());
  // a sort on a column that has gone away falls back to the name
  if (browse.sort !== "name" && browse.sort !== "tons" && browse.sort !== "bv" && !cols.some((c) => (c.sort || c.key) === browse.sort)) { browse.sort = "name"; browse.dir = 1; }
  const k = browse.sort, d = browse.dir;
  list.sort((a, b) => (STRING_SORTS.has(k) ? String(a[k] ?? "").localeCompare(String(b[k] ?? "")) || a.name.localeCompare(b.name) : ((a[k] ?? -1) - (b[k] ?? -1)) || a.name.localeCompare(b.name)) * d);
  browse.shown = list.slice(0, 400);
  $("ub-count").textContent = `${list.length} unit${list.length === 1 ? "" : "s"}${list.length > 400 ? " (first 400 shown: narrow the search)" : ""}`;
  const th = (key, head, cls, title) => `<th data-ck="${esc(key || head)}" ${key ? `data-sort="${key}" ` : ""}class="${cls || ""}"${title ? ` title="${esc(title)}"` : ""}>${head}</th>`;
  $("ub-list").tHead.innerHTML = `<tr><th data-ck="ico"></th><th data-ck="eye" class="eyeh" title="Click an eye to open that unit's sheet; open several to compare them side by side">${EYE}</th>${th("name", "Unit")}${th("tons", "Tons", "num")}${th("bv", "BV", "num")}${cols.map((c) => th(c.sortable === false ? "" : (c.sort || c.key), c.head, c.num ? "num" : "", c.title)).join("")}</tr>`;
  document.querySelectorAll("#ub-list th[data-sort]").forEach((h) => h.addEventListener("click", () => {
    browse.dir = browse.sort === h.dataset.sort ? -browse.dir : 1; browse.sort = h.dataset.sort; drawBrowser();
  }));
  const body = $("ub-list").tBodies[0];
  body.innerHTML = browse.shown.map((u, i) => `<tr data-i="${i}" draggable="${u.ok}" class="${lab.picked.has(u.id) ? "on" : ""}${u.ok ? "" : " bad"}" title="${esc(u.ok ? "Drag onto a team" : u.why)}">
      <td class="ico">${classIcon(u.tons)}</td><td class="eye"><span class="eyebtn" data-eye title="Open this unit's sheet">${EYE}</span></td><td>${esc(u.name)}</td><td class="num">${u.tons ?? ""}</td><td class="num">${u.bv ?? ""}</td>${cols.map((c) => `<td${c.num ? ' class="num"' : ""}>${esc(String(c.show(u)))}</td>`).join("")}</tr>`).join("");
  body.querySelectorAll("tr").forEach((tr) => {
    const u = browse.shown[+tr.dataset.i];
    tr.querySelector("[data-eye]").addEventListener("click", (e) => { e.stopPropagation(); openSheet(u.id, null, null); });
    tr.addEventListener("dblclick", () => { if (u.ok) addUnits(lab.teams[lab.addTo], [u.id]); });
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
  document.querySelectorAll("#ub-list th[data-sort]").forEach((th) => { th.classList.toggle("sorted", th.dataset.sort === k); th.dataset.dir = String(d); });   // CSS draws the up / down triangle
  colResize($("ub-list"), "ub");
}

function pickedChanged() {
  $("ub-picked").textContent = lab.picked.size ? `${lab.picked.size} selected: drag them onto a team, or press "Add selected"` : "Drag a unit onto a team. Click to select several (Ctrl+click adds to the selection).";
  drawBrowser();
  drawAddTo();
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
  wireBrowserList();
  wireSheetWindow();
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
  $("ub-addto").addEventListener("change", (e) => { lab.addTo = +e.target.value; });
  $("ub-add").addEventListener("click", () => addUnits(lab.teams[lab.addTo], [...lab.picked]));
  $("ub-file").addEventListener("click", () => $("ub-fileinput").click());
  $("ub-fileinput").addEventListener("change", (e) => { addFiles(lab.teams[lab.addTo], e.target.files); e.target.value = ""; });
  $("ub-clear").addEventListener("click", () => { lab.picked.clear(); pickedChanged(); });
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
  const current = m.mode === "one" ? m.one : m.mode === "playlist" ? null : m.cells[m.cell];
  const body = $("boards").tBodies[0];
  body.innerHTML = list.slice(0, 400).map((b) => `<tr data-id="${esc(b.id)}" class="${b.id === current ? "on" : b.id === lab.peek ? "peek" : ""}"><td>${esc(b.name)}</td><td class="num">${b.width}&times;${b.height}</td><td>${esc(b.source)}</td></tr>`).join("")
    || `<tr><td colspan="3" class="note">No board matches</td></tr>`;
  // one click previews a board; a double-click chooses it (Daniel, 2026-11-17: "sometimes I want to see the preview of a map
  // before adding it"). A board added to the map list goes on TOP, so the preview (the list's first map) shows it.
  body.querySelectorAll("tr[data-id]").forEach((tr) => {
    tr.addEventListener("click", () => {
      lab.peek = tr.dataset.id;
      body.querySelectorAll("tr.peek").forEach((x) => x.classList.remove("peek"));
      if (!tr.classList.contains("on")) tr.classList.add("peek");
      drawPreview();
    });
    tr.addEventListener("dblclick", () => {
      lab.peek = null;
      if (m.mode === "one") m.one = tr.dataset.id;
      else if (m.mode === "playlist") m.playlist.unshift(tr.dataset.id);
      else { m.cells[m.cell] = tr.dataset.id; m.cell = (m.cell + 1) % m.cells.length; }
      save(); drawBoards();
    });
  });
  $("map-one").checked = m.mode === "one";
  $("map-stitch").checked = m.mode === "stitch";
  $("map-playlist").checked = m.mode === "playlist";
  $("stitch-box").hidden = m.mode !== "stitch";
  $("playlist-box").hidden = m.mode !== "playlist";
  $("playlist-order").value = m.order;
  drawPlaylist();
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
  if (lab.peek && lab.boardById.has(lab.peek)) { const b = await getBoard(lab.peek); if (b) return { w: b.w, h: b.h, cells: [{ board: b, ox: 0, oy: 0 }], peek: true }; }
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
  // starting zones. PLACED: a shade over the hexes of the team's boxes. WALK ON: the hexes the engine really lets a unit
  // enter from (Daniel, 2026-11-17: "The highlighted entry boxes should match the actual deployment area based on the
  // deployment depth options, including the anti-stuck options"): the entry band DEPLOYMENT_DEPTH deep, solid; the extra rows
  // out to DEPLOYMENT_STUCK_DEPTH, faint with a dashed edge, are used only by a unit that could not get out of the first band.
  // Then the team's name in the middle of each box.
  const { depth: dd, stuck: sd } = deployDepths();
  (zones || []).forEach((z, zi) => {
    if (z.walk_on) {
      const near = entryHexes(z.boxes, parts.w, parts.h, dd), far = sd > dd ? entryHexes(z.boxes, parts.w, parts.h, sd) : new Set();
      for (const k of far) {
        if (near.has(k)) continue;
        const [c, r] = k.split(",").map(Number), [x, y] = centre(c, r); path(x, y, 1);
        g.fillStyle = z.colour + "22"; g.fill(); g.setLineDash([2, 2]); g.strokeStyle = z.colour; g.lineWidth = 1; g.stroke(); g.setLineDash([]);
      }
      for (const k of near) { const [c, r] = k.split(",").map(Number), [x, y] = centre(c, r); path(x, y, 1); g.fillStyle = z.colour + "88"; g.fill(); }
    } else {
      for (let r = 1; r <= parts.h; r++) for (let c = 1; c <= parts.w; c++) {
        const box = Math.min(2, Math.floor(((r - 1) * 3) / parts.h)) * 3 + Math.min(2, Math.floor(((c - 1) * 3) / parts.w));
        if (!z.boxes[box]) continue;
        const [x, y] = centre(c, r); path(x, y, 1);
        g.fillStyle = z.colour + "55"; g.fill();
      }
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
// The deployment depths in force: the Options page's value, else the option's default (0 and 3).
function deployDepths() {
  const val = (k, d) => { const v = lab.options && lab.options[k]; if (v !== undefined && v !== "") return +v; const o = (lab.registry || []).find((x) => x.key === k); return o ? +o.default : d; };
  return { depth: val("DEPLOYMENT_DEPTH", 0), stuck: val("DEPLOYMENT_STUCK_DEPTH", 3) };
}
// The hexes ("col,row") a walk-on zone enters from, up to `depth` in: the same rule as the engine's
// deployment::zone_entry_band. A side box (N, E, S, W) = that whole edge; a corner box = the two edges meeting there, each from
// the corner to its half-way point (the middle hex of an odd length is in both halves); the centre = none.
function entryHexes(boxes, w, h, depth) {
  const BY_BOX = [[["N", 1], ["W", 1]], [["N", 0]], [["N", 2], ["E", 1]], [["W", 0]], [], [["E", 0]], [["S", 1], ["W", 2]], [["S", 0]], [["S", 2], ["E", 2]]];
  const out = new Set();
  boxes.forEach((on, k) => {
    if (!on) return;
    for (const [edge, part] of BY_BOX[k]) {
      const len = edge === "N" || edge === "S" ? w : h;
      for (let along = 1; along <= len; along++) {
        if ((part === 1 && along * 2 > len + 1) || (part === 2 && along * 2 < len + 1)) continue;
        for (let d = 0; d <= depth; d++) {
          const [c, r] = edge === "N" ? [along, 1 + d] : edge === "S" ? [along, h - d] : edge === "W" ? [1 + d, along] : [w - d, along];
          if (c >= 1 && c <= w && r >= 1 && r <= h) out.add(`${c},${r}`);
        }
      }
    }
  });
  return out;
}
let previewToken = 0;
async function drawPreview() {
  const token = ++previewToken, canvas = $("map-preview");
  const parts = await mapParts();
  if (token !== previewToken) return;
  canvas.hidden = !parts; $("map-legend").hidden = !parts;
  const pb = lab.peek && lab.boardById.get(lab.peek);
  $("board-chosen").innerHTML = pb ? `<p><b>Previewing ${esc(pb.name)}</b> (${pb.width}&times;${pb.height})<br><span class="note">Double-click it in the list to choose it; it is not chosen yet.</span></p>` : mapCheck().text;
  if (!parts) return;
  paintMap(canvas, parts, lab.zonesOverlay ? lab.zonesOverlay() : null);
  $("map-legend").innerHTML = [-2, 0, 2, 4, 6, 8, 10].map((l) => `<span><i style="background:${levelColour(l)}"></i>${l === 10 ? "10+" : l}</span>`).join("") +
    (lab.zonesOverlay && lab.zonesOverlay() && lab.zonesOverlay().some((z) => z.walk_on) ? (() => { const { depth, stuck } = deployDepths(); return `<span><i style="background:#88888888"></i>Walk-on entry (${depth ? `${depth + 1} rows deep` : "edge row"})</span>${stuck > depth ? `<span><i style="background:#88888822;outline:1px dashed #888"></i>Only for a unit stuck in the first rows (to ${stuck + 1} deep)</span>` : ""}`; })() : "") + `<span><i style="background:#1e5ac8"></i>Water</span><span><i style="background:#2d5a2a"></i>Woods</span><span><i style="background:#6e6e6e"></i>Road / paving</span><span><i style="background:#5a3c1e"></i>Rough</span><span><i style="background:#3c3c46"></i>Building</span>`;
}

function drawPlaylist() {
  const m = lab.map, ol = $("playlist").tBodies[0];
  ol.innerHTML = m.playlist.length ? m.playlist.map((id, i) => {
    const b = lab.boardById.get(id);
    return `<tr><td class="n">${i + 1}.</td><td>${esc(b ? b.name : id)}</td><td class="note">${b ? `${b.width}&times;${b.height}` : ""}</td>
      <td class="b"><button class="btn small" data-up="${i}" ${i ? "" : "disabled"} title="Earlier">&#9650;</button></td><td class="b"><button class="btn small" data-down="${i}" ${i < m.playlist.length - 1 ? "" : "disabled"} title="Later">&#9660;</button></td><td class="b"><button class="btn small" data-del="${i}" title="Remove">&times;</button></td></tr>`;
  }).join("") : `<tr><td class="note">No maps yet: double-click boards in the list.</td></tr>`;
  const move = (i, to) => { const [x] = m.playlist.splice(i, 1); m.playlist.splice(to, 0, x); save(); drawBoards(); };
  ol.querySelectorAll("[data-up]").forEach((b) => b.addEventListener("click", () => move(+b.dataset.up, +b.dataset.up - 1)));
  ol.querySelectorAll("[data-down]").forEach((b) => b.addEventListener("click", () => move(+b.dataset.down, +b.dataset.down + 1)));
  ol.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => { m.playlist.splice(+b.dataset.del, 1); save(); drawBoards(); }));
}

// ---------------------------------------------------------------- starting zones (CL14)
// A zone is a set of the nine boxes of a 3 x 3 cut of the board (NW N NE / W C E / SW S SE). Edge = the eight outer boxes,
// Anywhere = all nine. Walk on = the units enter from the board's border inside the zone; off = they are placed on it.
// Centre and Walk on exclude each other. Every team has its own; the one dropdown (Fixed / Rotating / Random) is for the run.
const BOX_LABELS = ["NW", "N", "NE", "W", "C", "E", "SW", "S", "SE"];
function zoneOf(t, ti) {
  if (!t.zone) { const boxes = new Array(9).fill(false); const d = [3, 5, 1, 7][ti]; if (d === undefined) boxes.fill(true); else boxes[d] = true; t.zone = { boxes, walk_on: d !== undefined }; }
  return t.zone;
}
function zoneGrid(ti, mini) {
  const t = lab.teams[ti], z = zoneOf(t, ti);
  const wrap = document.createElement("div");
  wrap.className = mini ? "zone-mini" : "zone-team";
  wrap.dataset.zteam = ti;
  const set = (fn) => { fn(zoneOf(lab.teams[ti], ti)); zonesChanged(); };
  if (mini) {
    // on a team panel: one line, "Start: NW N NE W C E SW S SE [walk on]", a checkbox each (Daniel, 2026-11-15)
    wrap.innerHTML = `<span class="zl-head" title="Where this team starts: tick the boxes of the 3 x 3 cut of the board">Start:</span>${BOX_LABELS.map((n, k) => `<label class="zl" title="${k === 4 ? "Centre" : "Zone " + n}"><input type="checkbox" data-box="${k}">${n}</label>`).join("")}<label class="zl" title="Units walk on from the board's border inside the zone"><input type="checkbox" data-walk>Walk on</label>`;
    wrap.querySelectorAll("[data-box]").forEach((b) => b.addEventListener("change", () => { const k = +b.dataset.box; set((z) => { z.boxes[k] = b.checked; if (k === 4 && z.boxes[4]) z.walk_on = false; }); }));
    wrap.querySelector("[data-walk]").addEventListener("change", (e) => set((z) => { z.walk_on = e.target.checked; if (z.walk_on) z.boxes[4] = false; }));
    return wrap;
  }
  wrap.innerHTML = `<div class="zname" data-zname></div>
    <div class="zone-grid">${BOX_LABELS.map((n, k) => `<button type="button" data-box="${k}" title="${k === 4 ? "Centre" : "Zone " + n}">${n}</button>`).join("")}</div>
    <div class="zone-tools"><label class="row"><input type="checkbox" data-walk> Walk on</label>${mini ? "" : `<button class="btn small" type="button" data-edge>Edge</button><button class="btn small" type="button" data-any>Anywhere</button><button class="btn small" type="button" data-none>Clear</button>`}</div>`;
  wrap.querySelectorAll("[data-box]").forEach((b) => b.addEventListener("click", () => { if (lab.deploy.mode === "rulebook") return; set((z) => { const k = +b.dataset.box; z.boxes[k] = !z.boxes[k]; if (k === 4 && z.boxes[4]) z.walk_on = false; }); }));
  wrap.querySelector("[data-walk]").addEventListener("change", (e) => set((z) => { z.walk_on = e.target.checked; if (z.walk_on) z.boxes[4] = false; }));
  if (!mini) {
    wrap.querySelector("[data-edge]").addEventListener("click", () => set((z) => { z.boxes = [true, true, true, true, false, true, true, true, true]; }));
    wrap.querySelector("[data-any]").addEventListener("click", () => set((z) => { z.boxes = new Array(9).fill(true); z.walk_on = false; }));
    wrap.querySelector("[data-none]").addEventListener("click", () => set((z) => { z.boxes = new Array(9).fill(false); }));
  }
  return wrap;
}
// bring every grid (the Map page's and the small ones on the team panels) up to date with the state
function paintZoneGrids() {
  const off = lab.deploy.mode === "rulebook";
  document.querySelectorAll("[data-zteam]").forEach((w) => {
    const ti = +w.dataset.zteam, t = lab.teams[ti];
    if (!t) return;
    const z = zoneOf(t, ti);
    const grid = w.querySelector(".zone-grid"); if (grid) grid.classList.toggle("off", off);
    w.querySelectorAll("[data-box]").forEach((b) => {
      const on = z.boxes[+b.dataset.box];
      if (b.type === "checkbox") { b.checked = on; b.disabled = off; return; }       // the one-line version on a team panel
      b.classList.toggle("on", on); b.style.background = on ? t.colour : "";
    });
    const walk = w.querySelector("[data-walk]"); walk.checked = z.walk_on; walk.disabled = off;
    const zn = w.querySelector("[data-zname]"); if (zn) { zn.textContent = `Team ${ti + 1}: ${t.name}`; zn.style.borderLeftColor = t.colour; }
    w.querySelectorAll("button.btn").forEach((b) => { b.disabled = off; });
  });
}
function zonesProblem() {
  if (lab.deploy.mode === "rulebook") return "";
  const t = lab.teams.findIndex((x, i) => !zoneOf(x, i).boxes.some(Boolean));
  return t >= 0 ? `${lab.teams[t].name} has no starting zone chosen.` : "";
}
function zonesChanged() {
  save(); paintZoneGrids();
  const p = zonesProblem();
  $("zone-note").innerHTML = p ? `<span class="err">${esc(p)}</span>` : zoneNote();
  drawPreview();
}
function zoneNote() {
  const n = lab.teams.length;
  return { rulebook: "The Core Rulebook's deployment: the sides roll for initiative and the loser picks a home edge; every unit walks on from its team's edge. Zones below are not used.",
    fixed: "Each team starts in its own zone every battle.",
    rotating: n === 2 ? "The two teams swap zone setups every battle." : `Each battle the zone setups move one team along: battle 2 gives team 2 team 1's setup, and after ${n} battles each team has its own again.`,
    random: "Each battle, each team starts in one box drawn from the boxes it has highlighted." }[lab.deploy.mode];
}
function drawZones() {
  const box = $("zone-grids");
  box.innerHTML = "";
  lab.teams.forEach((t, ti) => box.appendChild(zoneGrid(ti, false)));
  $("zone-mode").value = lab.deploy.mode;
  const opp = $("zone-opposite"), two = lab.teams.length === 2;
  opp.checked = !!lab.deploy.opposite && two; opp.disabled = !(two && lab.deploy.mode === "random");
  $("zone-opposite-tag").hidden = two;
  zonesChanged();
}
lab.zonesOverlay = () => (lab.deploy.mode === "rulebook" ? null : lab.teams.map((t, ti) => ({ boxes: zoneOf(t, ti).boxes, walk_on: !!zoneOf(t, ti).walk_on, colour: t.colour, label: t.name })));

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
  if (m.mode === "playlist") {
    const n = m.playlist.length;
    return n ? { ok: `${n} map${n === 1 ? "" : "s"} in a list (${m.order === "shuffle" ? "shuffled" : "in order"})`, text: `<p><b>${n} map${n === 1 ? "" : "s"} cycled through</b><br>${m.playlist.map((id) => esc((lab.boardById.get(id) || {}).name || id)).slice(0, 6).join("<br>")}${n > 6 ? `<br>and ${n - 6} more` : ""}<br><span class="note">The preview shows the first.</span></p>` } : { text: `<p class="err">The map list is empty.</p>` };
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
  else if (m.mode === "playlist") m.playlist.unshift(list[Math.floor(Math.random() * list.length)].id);
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
  const zp = zonesProblem();
  if (zp) { $("run-error").textContent = zp + " See the Map page."; return; }
  const chosen = setup();
  if (!DEMO && !$("seed").value.trim()) chosen.seed = freshSeed();   // an empty seed box: a new starting seed for this run, written into the setup (so the saved file replays it)
  const r = await api("run", { setup: chosen });
  if (r.error) { $("run-error").textContent = r.error; return; }
  lab.run = r.run;
  lab.runSetup = chosen;
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
    $("progress-text").textContent = `${p.done} / ${p.battles} battles, ${fmtSecs(p.seconds)}, seed ${lab.runSetup.seed}${p.cancelled ? " (cancelled)" : ""}`;
    $("cancel-btn").disabled = p.finished;
    $("cancel-btn-2").hidden = p.finished;
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
      <dt>Armor left</dt><dd>${t.max_armor ? pct(t.mean_armor_left / t.max_armor) : "n/a"}</dd>
      <dt>Structure left</dt><dd>${t.max_structure ? pct(t.mean_structure_left / t.max_structure) : "n/a"}</dd>
      <dt>Shots that hit</dt><dd>${pct(t.hit_rate)}</dd></dl></fieldset>`).join("")
    + `<fieldset><legend>${filtered ? "Matching battles" : "All battles"}</legend><dl>
      <dt>Battles</dt><dd>${s.battles}</dd>
      <dt>Draws</dt><dd>${s.draws}</dd>
      <dt>Turns, average</dt><dd>${s.mean_turns.toFixed(1)}</dd>
      <dt>Reached the turn cap (${s.max_turns})</dt><dd>${s.hit_turn_cap}</dd>
      <dt>Runtime</dt><dd>${fmtSecs(res.progress.seconds)}</dd>
      <dt>Seconds a battle</dt><dd>${s.mean_battle_seconds.toFixed(2)}</dd>
      ${res.crashed.length ? `<dt class="err">Crashed</dt><dd class="err">${res.crashed.length}</dd>` : ""}</dl></fieldset>`;
  $("save-run").disabled = false;
  drawCrashes(res.crashed || []);
  reportFlag(res.crashed || []);
  $("cause-list").innerHTML = (res.causes || []).map(([c, k]) => `<option value="${esc(c)}">${k} unit${k === 1 ? "" : "s"}</option>`).join("");
  if ($("unit-stats-box").open) loadUnitStats();
  const tree = $("battle-tree");
  tree.innerHTML = "";
  fillRange(tree, 1, total, res);
}

// A new starting seed: random bits mixed with the clock (Daniel, 2026-11-14: "starter seed + time ... is a more random plan"),
// kept under 2^52 so it stays an exact whole number in JSON. The battles' own seeds follow from it (runs.rs, PcgDice::battle_seed).
function freshSeed() {
  const r = new Uint32Array(2);
  crypto.getRandomValues(r);
  const mixed = (BigInt(r[0]) << 20n) ^ BigInt(r[1]) ^ (BigInt(Date.now()) * 0x9E3779B1n);
  return Number(mixed % (1n << 52n)) || 1;
}

// ---------------------------------------------------------------- SUGGESTION / BUG REPORT
// The project's issue page (the public repository). The report button flashes while the open run has crashed battles.
const ISSUES_URL = "https://github.com/Logajam/battletech-combat-lab/issues/new";
let reportCrashes = [];
function reportFlag(crashed) {
  reportCrashes = crashed;
  $("report-btn").classList.toggle("flash", crashed.length > 0);
}
// a link to a new issue with its title and text filled in (the address has a size limit, so the text stays short)
function issueLink(title, body) {
  return `${ISSUES_URL}?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}
function openReport() {
  const setupText = lab.runSetup ? JSON.stringify(lab.runSetup) : "";
  const n = reportCrashes.length;
  const seeds = reportCrashes.slice(0, 10).map((c) => `- battle ${c.sim}, seed ${c.seed}${c.board ? ", map " + c.board : ""}: ${String(c.crashed || "").slice(0, 160)}`).join("\n");
  const where = `${window.LAB_WASM ? "browser" : "desktop"}; ${navigator.userAgent}`;
  let bug = `**What happened**\n\n(Describe what you saw.)\n\n**Saved run file**\n\n(Drag the saved .txt file here.)\n\n---\n`;
  if (lab.runSetup) bug += `Batch seed: ${lab.runSetup.seed ?? "default"}, battles: ${lab.runSetup.battles}\n`;
  if (n) bug += `\nCrashed battles (${n}):\n${seeds}${n > 10 ? "\n- ... and " + (n - 10) + " more (see the file)" : ""}\n`;
  bug += `\nRunning on: ${where}\n`;
  if (setupText && encodeURIComponent(bug + setupText).length < 5500) bug += `\nSetup:\n\`\`\`json\n${setupText}\n\`\`\`\n`;
  else if (setupText) bug += `\n(The setup is in the saved file.)\n`;
  $("report-bug").href = issueLink(n ? `Bug: ${n} battle${n === 1 ? "" : "s"} crashed` : "Bug: ", bug);
  $("report-idea").href = issueLink("Suggestion: ", `**What would you like to see?**\n\n(Describe it.)\n\n---\nRunning on: ${where}\n`);
  $("report-crash").hidden = !n;
  $("report-crash").textContent = n ? `${n} battle${n === 1 ? "" : "s"} crashed in this run. That is a bug in the engine: please report it.` : "";
  $("report").hidden = false;
}

// crashed battles stay visible: seed, what happened, where; "Replay" plays the same battle again (it crashes again, and says so)
function drawCrashes(list) {
  const box = $("crashes");
  box.hidden = !list.length;
  if (!list.length) return;
  box.innerHTML = `<fieldset><legend class="err">Crashed battles (${list.length})</legend><table class="leaves"><thead><tr><th class="num">#</th><th>Seed</th><th>Map</th><th>Zones</th><th>What happened</th><th></th></tr></thead><tbody>${list.map((c) => `<tr><td class="num">${c.sim}</td><td>${esc(c.seed)}</td><td>${esc(String(c.board || "").replace(/\.board$/, "").replace(/_/g, " "))}</td><td>${c.zones ? esc(Object.entries(c.zones).map(([k, v]) => `${k}: ${v}`).join("; ")) : ""}</td><td>${esc(c.crashed)}</td>
    <td><button class="btn small" data-replay="${c.sim}">Replay</button> <button class="btn small" data-repro="${esc(c.seed)}" title="Copy what is needed to play it again on the command line">Copy seed</button></td></tr>`).join("")}</tbody></table></fieldset>`;
  box.querySelectorAll("[data-replay]").forEach((b) => b.addEventListener("click", async () => {
    const r = await api("history", { run: lab.run, sim: +b.dataset.replay });
    setStatus(r.error ? r.error : "That battle did not crash this time");
    if (!r.error) openReplay({ run: lab.run, sim: +b.dataset.replay });
  }));
  box.querySelectorAll("[data-repro]").forEach((b) => b.addEventListener("click", () => { try { navigator.clipboard.writeText(b.dataset.repro); } catch (e) { /* no clipboard */ } setStatus(`Seed ${b.dataset.repro} (battle seed: use it with Load by seed, or btsim --seed with the run's seed and battle number)`); }));
}

// a saved run's setup back into the Units, Map and Options pages
function applySetup(s) {
  lab.teams = s.teams.map((t, i) => ({ name: t.name, colour: t.colour || defaultColour(i), bot: t.bot, zone: t.zone, units: t.units.map((u) => (u.mtf_text ? modifiedEntry(u.mtf_text, u.unit, u.gunnery ?? 4, u.piloting ?? 5) : unitEntry(u.unit, u.gunnery ?? 4, u.piloting ?? 5))).filter(Boolean) }));
  const m = lab.map;
  if (typeof s.board === "string") { m.mode = "one"; m.one = s.board; }
  else if (s.board && s.board.playlist) { m.mode = "playlist"; m.playlist = [...s.board.playlist]; m.order = s.board.order || "sequence"; }
  else if (s.board && s.board.grid) { const g = s.board.grid; Object.assign(m, { mode: "stitch", rows: g.length, cols: g[0].length, cells: g.flat(), cell: 0 }); }
  lab.deploy = { mode: s.zone_mode || "rulebook", opposite: !!s.zone_opposite };
  lab.options = s.options || {};
  $("battles").value = s.battles; $("seed").value = s.seed; $("threads").value = s.threads || 0; $("max-turns").value = s.max_turns || 100; $("full-power").checked = !!s.full_power; $("threads").disabled = $("full-power").checked;
  $("team-count").value = lab.teams.length;
  save(); drawTeams(); drawZones(); drawBoards(); drawOptions();
}

// ---- unit statistics: team folders, unit folders inside them, the numbers inside those
async function loadUnitStats() {
  if (!lab.run) return;
  const res = await api("results", { run: lab.run, filter: lab.filter, from: 1, to: 1, unit_stats: true });
  if (res.error || !res.unit_stats) { $("unit-stats").textContent = res.error || "No statistics yet."; return; }
  const openKeys = new Set([...document.querySelectorAll("#unit-stats details[open]")].map((d) => d.dataset.key));
  const f1 = (x) => x.toFixed(1), p = (a, m) => (m > 0 ? pct(a / m) : "n/a");
  const html = Object.entries(res.unit_stats).map(([team, units]) => `<details class="folder" data-key="${esc(team)}" ${openKeys.has(team) || !openKeys.size ? "open" : ""}>
    <summary><span style="color:${colourOf(team)}">&#9632;</span> <b>${esc(team)}</b></summary>
    ${Object.entries(units).map(([label, u]) => {
      const n = u.battles || 1;
      const rows = [["Survived", u.survived], ...Object.entries(u.causes).sort((a, b) => b[1] - a[1])];
      return `<details class="folder" data-key="${esc(label)}" ${openKeys.has(label) ? "open" : ""}>
        <summary>${esc(u.name)} <span class="note">survived ${pct(u.survived / n)} &middot; armor left ${p(u.armor_left, u.armor_max)} &middot; structure left ${p(u.structure_left, u.structure_max)} &middot; ${u.kills.toFixed(2)} kills</span></summary>
        <div class="ustat">
          <table class="leaves"><thead><tr><th>How it ended (share of battles)</th><th class="num">%</th></tr></thead><tbody>${rows.map(([c, k], i) => `<tr class="cause-row" data-unit="${esc(label)}" data-cause="${i === 0 ? "" : esc(c)}" title="Show the battles where it ${i === 0 ? "survived" : "ended this way"}"><td><a href="#">${esc(c)}</a></td><td class="num">${pct(k / n)}</td></tr>`).join("")}</tbody></table>
          <table class="leaves"><thead><tr><th>Location</th><th class="num">Armor left (avg)</th><th class="num">%</th><th class="num">Structure left (avg)</th><th class="num">%</th></tr></thead><tbody>
            ${Object.entries(u.locations).map(([loc, v]) => `<tr><td>${esc(loc)}</td><td class="num">${f1(v.armor)} / ${f1(v.armor_max)}</td><td class="num">${p(v.armor, v.armor_max)}</td><td class="num">${f1(v.structure)} / ${f1(v.structure_max)}</td><td class="num">${p(v.structure, v.structure_max)}</td></tr>`).join("")}
            <tr><td><b>Whole unit</b></td><td class="num">${f1(u.armor_left)} / ${f1(u.armor_max)}</td><td class="num">${p(u.armor_left, u.armor_max)}</td><td class="num">${f1(u.structure_left)} / ${f1(u.structure_max)}</td><td class="num">${p(u.structure_left, u.structure_max)}</td></tr></tbody></table>
          <table class="leaves"><thead><tr><th>Weapon</th><th class="num">Shots a battle</th><th class="num">Accuracy</th><th class="num">Damage a turn</th><th class="num" title="Share of its turns standing in which the weapon fired">Used</th></tr></thead><tbody>
            ${Object.entries(u.weapons).map(([w, v]) => `<tr><td>${esc(weaponLabel(w))}</td><td class="num">${f1(v.fired_per_battle)}</td><td class="num">${pct(v.accuracy)}</td><td class="num">${v.damage_per_turn.toFixed(2)}</td><td class="num">${pct(v.utilization)}</td></tr>`).join("") || `<tr><td colspan="5" class="note">No weapons.</td></tr>`}</tbody></table>
          <p class="note">Standing ${u.turns_alive.toFixed(1)} turns a battle on average. Damage a turn = damage dealt by that weapon over every turn the unit stood.</p>
        </div></details>`;
    }).join("")}</details>`).join("");
  $("unit-stats").innerHTML = html;
  $("unit-stats").querySelectorAll(".cause-row").forEach((tr) => tr.addEventListener("click", (e) => { e.preventDefault(); filterByCause(tr.dataset.unit, tr.dataset.cause); }));
}

// A click on a "How it ended" row (Daniel, 2026-11-17): the battle list and statistics show only the battles where that unit
// ended that way (the "Survived" row: where it survived). It is an ordinary unit condition in the Find battles form, so it
// can be read, changed, added to, or cleared with Show all.
function filterByCause(unit, cause) {
  $("f-units").innerHTML = "";
  addUnitCondition(cause ? { unit, state: "destroyed", cause, exact: true } : { unit, state: "survived" });
  lab.filter = readFilter();
  drawResults();
  const list = $("battle-tree");
  if (list && list.scrollIntoView) list.scrollIntoView({ block: "start" });
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
    table.innerHTML = `<thead><tr><th class="num">#</th><th>Seed</th><th>Winner</th><th class="num">Turns</th><th class="num">Seconds</th><th>Map</th><th>Zones</th></tr></thead><tbody>` +
      res.battles.map((b) => `<tr data-sim="${b.sim}"><td class="num">${b.sim}</td><td>${b.seed}</td><td><span style="color:${colourOf(b.winner)}">&#9632;</span> ${esc(b.winner)}${b.capped ? " (turn cap)" : ""}</td><td class="num">${b.turns}</td><td class="num">${b.seconds.toFixed(2)}</td><td>${esc(String(b.board || "").replace(/\.board$/, "").replace(/_/g, " "))}</td><td>${b.zones ? esc(Object.entries(b.zones).map(([k, v]) => `${k}: ${v}`).join("; ")) : ""}</td></tr>`).join("") + "</tbody>";
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
    <select class="c-state" aria-label="What happened">${[["destroyed", "was destroyed"], ["survived", "survived"], ["", "either"]].map(([v, t]) => `<option value="${v}"${(cond.state ?? "destroyed") === v ? " selected" : ""}>${t}</option>`).join("")}</select>
    <input type="text" class="c-cause" list="cause-list" placeholder="cause (pick or type a word)" aria-label="Cause of death contains" value="${esc(cond.cause || "")}">
    <button class="btn small" title="Remove this condition">&times;</button>`;
  row.querySelector("button").addEventListener("click", () => row.remove());
  // a condition made by clicking a cause matches that cause exactly, until its text is changed by hand (then: every word)
  if (cond.exact) row.dataset.exact = cond.cause;
  $("f-units").appendChild(row);
}

function readFilter() {
  const f = {};
  if ($("f-winner").value) f.winner = $("f-winner").value;
  if ($("f-capped").value) f.capped = $("f-capped").value === "yes";
  if ($("f-tmin").value !== "") f.min_turns = +$("f-tmin").value;
  if ($("f-tmax").value !== "") f.max_turns = +$("f-tmax").value;
  const units = [...document.querySelectorAll("#f-units .cond")].map((r) => {
    const cause = r.querySelector(".c-cause").value, state = r.querySelector(".c-state").value;
    return r.dataset.exact !== undefined && r.dataset.exact === cause && state === "destroyed" ? { unit: r.querySelector(".c-unit").value, state, cause_is: cause } : { unit: r.querySelector(".c-unit").value, state, cause };
  });
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
  } else if (window.LAB_WASM) {
    const html = await window.LAB_WASM.replayHtml(which.run ? { run: which.run, sim: which.sim } : { setup: setup(), seed: which.seed, sim: Math.max(1, +$("replay-sim").value || 1) });
    if (html.error) { setStatus(html.error); return; }
    frame.srcdoc = html;
  } else if (which.run) {
    frame.removeAttribute("srcdoc");
    frame.src = `replay?run=${which.run}&sim=${which.sim}`;
  } else {
    const sim = Math.max(1, +$("replay-sim").value || 1);
    const r = await api("history", { setup: setup(), seed: which.seed, sim });   // checks the setup; the page plays it again
    if (r.error) { setStatus(r.error); return; }
    frame.removeAttribute("srcdoc");
    frame.src = `replay?seed=${which.seed}&sim=${sim}&t=${Date.now()}`;
  }
  frame.onload = () => setStatus("Replay ready");
}

// ---------------------------------------------------------------- tabs
function show(page) {
  if (page === "map" && typeof drawPreview === "function") setTimeout(drawPreview, 0);     // the deployment depths may have changed on the Options page
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
    if (c.cause_is !== undefined && (!u.destroyed || (u.cause || "unknown") !== c.cause_is)) return false;
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
    case "equipment_list": return { equipment: d.equipment || [] };
    case "unit_text": return d.unit_texts && d.unit_texts[body.id] ? { id: body.id, text: d.unit_texts[body.id] } : { error: "this demo carries the sheets of a few units only; Combat Lab has them all" };
    case "unit_eval": return { error: "the demo cannot work out a Battle Value" };
    case "board": return d.board_texts && d.board_texts[body.id] ? { id: body.id, text: d.board_texts[body.id] } : { error: "this board is not in the demo" };
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

// ---------------------------------------------------------------- unit sheet and editor (Daniel, 2026-11-15)
// A unit from the browser opens as a read-only sheet; a unit on a team opens the same sheet with its values editable. This is a
// .mtf editor feeding the engine, not a designer: nothing is checked for being a legal design, the aim is only that whatever
// is made plays. What is edited is the unit's own .mtf text, changed line by line, so whatever the page does not understand is
// kept as it was. The one hard rule is that equipment must fit the critical slots; everything else (heat sinks, jump jets,
// structure slots, armor, tonnage...) is at most a warning. A modified unit is temporary: it lives in the team and travels in the
// setup (so a saved run file carries it); it is never written to the unit folder and never appears in the unit list.
// The engine reads the edited text for the Battle Value (api "unit_eval"), so the BV shown is the one a battle uses.
const EMPTY = "-Empty-";
const LOC_RE = /^(Left Arm|Right Arm|Left Torso|Right Torso|Center Torso|Head|Left Leg|Right Leg|Center Leg|Front Left Leg|Front Right Leg|Rear Left Leg|Rear Right Leg):\s*$/i;
// the armor lines of a unit file: key -> [location, side] (the engine's own table, mtf_parser.rs armor_key_map). The same
// letters + " IS" are the internal structure lines the engine reads first when they are there ("LA IS:17").
const ARMOR_KEYS = { "la": ["Left Arm", "front"], "ra": ["Right Arm", "front"], "lt": ["Left Torso", "front"], "rt": ["Right Torso", "front"], "ct": ["Center Torso", "front"],
  "hd": ["Head", "front"], "ll": ["Left Leg", "front"], "rl": ["Right Leg", "front"], "cl": ["Center Leg", "front"], "fll": ["Front Left Leg", "front"], "frl": ["Front Right Leg", "front"],
  "rll": ["Rear Left Leg", "front"], "rrl": ["Rear Right Leg", "front"], "rtl": ["Left Torso", "rear"], "rtr": ["Right Torso", "rear"], "rtc": ["Center Torso", "rear"] };
const KEY_OF = Object.fromEntries(Object.entries(ARMOR_KEYS).filter(([, v]) => v[1] === "front").map(([k, v]) => [v[0], k.toUpperCase()]));
// the standard internal structure table (engine: mech_state.rs STRUCTURE_TABLE): tons -> [CT, side torso, arm, leg]
const STRUCT_ROWS = [[10,4,3,1,2],[15,5,4,2,3],[20,6,5,3,4],[25,8,6,4,6],[30,10,7,5,7],[35,11,8,6,8],[40,12,10,6,10],[45,14,11,7,11],[50,16,12,8,12],[55,18,13,9,13],[60,20,14,10,14],[65,21,15,10,15],[70,22,15,11,15],[75,23,16,12,16],[80,25,17,13,17],[85,27,18,14,18],[90,29,19,15,19],[95,30,20,16,20],[100,31,21,17,21],[105,32,22,17,22],[110,33,23,18,23],[115,35,24,19,24],[120,36,25,20,25],[125,38,26,21,26],[130,39,27,21,27],[135,41,28,22,28],[140,42,29,23,29],[145,44,31,24,31],[150,45,32,25,32],[155,47,33,26,33],[160,48,34,26,34],[165,50,35,27,35],[170,51,36,28,36],[175,53,37,29,37],[180,54,38,30,38],[185,56,39,31,39],[190,57,40,31,40],[195,59,41,32,41],[200,60,42,33,42]];
// where each location sits on the sheet, as the paper sheet has it: [row, column]
const SHEET_POS = { "Head": [1, 3], "Left Arm": [2, 1], "Left Torso": [2, 2], "Center Torso": [2, 3], "Right Torso": [2, 4], "Right Arm": [2, 5],
  "Left Leg": [3, 2], "Center Leg": [3, 3], "Right Leg": [3, 4], "Front Left Leg": [3, 2], "Front Right Leg": [3, 4], "Rear Left Leg": [4, 2], "Rear Right Leg": [4, 4] };
const slotCap = (loc) => (/Head|Leg/.test(loc) ? 6 : 12);                 // a head and a leg have 6 critical slots, everything else 12
// parts that cannot be taken out (Daniel): shoulder, hip, upper arm / leg, lower leg, foot, sensors, life support, cockpit, engine, gyro
const FIXED = new Set(["shoulder", "hip", "upperarmactuator", "upperlegactuator", "lowerlegactuator", "footactuator", "sensors", "lifesupport", "cockpit", "cockpit(armored)", "fusionengine", "gyro", "engine"]);
const isFixed = (raw) => FIXED.has(normName(raw));
const ACTUATORS = { 2: "Lower Arm Actuator", 3: "Hand Actuator" };      // the arm slots that are check boxes
// engine, gyro and cockpit lists with the slots they take (read off the unit files: how many "Fusion Engine" slots a type has in
// the centre torso and in each side torso, how many "Gyro" slots, what the head holds)
const ENGINES = [["Fusion Engine", 6, 0], ["XL Engine", 6, 3], ["XL (Clan) Engine", 6, 2], ["Light Engine", 6, 2], ["XXL Engine", 6, 6], ["XXL (Clan) Engine", 6, 4], ["Compact Engine", 3, 0], ["ICE Engine", 6, 0], ["Fuel Cell Engine", 6, 0]];
const GYROS = [["Standard Gyro", 4], ["Compact Gyro", 2], ["Heavy Duty Gyro", 4], ["XL Gyro", 6]];
const E = EMPTY;
const COCKPITS = { "Standard Cockpit": { head: ["Life Support", "Sensors", "Cockpit", E, "Sensors", "Life Support"], ct: 0 },
  "Small Cockpit": { head: ["Life Support", "Sensors", "Cockpit", "Sensors", E, E], ct: 0 },
  "Command Console": { head: ["Life Support", "Sensors", "Cockpit", "Cockpit", "Sensors", "Life Support"], ct: 0 },
  "Torso-Mounted Cockpit": { head: ["Sensors", "Sensors", E, E, E, E], ct: 1 },
  "Industrial Cockpit": { head: ["Life Support", "Sensors", "Cockpit", E, "Sensors", "Life Support"], ct: 0 },
  "Primitive Cockpit": { head: ["Life Support", "Sensors", "Cockpit", E, "Sensors", "Life Support"], ct: 0 } };
const STRUCTURES = ["Standard", "Endo Steel", "Endo-Composite", "Composite", "Reinforced", "Industrial"];
const ARMORS = ["Standard", "Ferro-Fibrous", "Light Ferro-Fibrous", "Heavy Ferro-Fibrous", "Stealth", "Reactive", "Reflective", "Hardened", "Ferro-Lamellor", "Ballistic-Reinforced", "Anti-Penetrative Ablation", "Impact-Resistant", "Heat-Dissipating"];
const MYOMERS = ["Standard", "Triple-Strength", "MASC", "Industrial Triple-Strength", "Super-Cooled"];
const CONFIGS = ["Biped", "Quad", "Tripod"];
const configOf = () => { const c = SHEET.mtf.get("Config"); return /quad/i.test(c) ? "Quad" : /tripod/i.test(c) ? "Tripod" : "Biped"; };
// the actuators of an arm and of the leg that replaces it on a quad (shoulder = hip, hand = foot)
const ARM_TO_LEG = { "Shoulder": "Hip", "Upper Arm Actuator": "Upper Leg Actuator", "Lower Arm Actuator": "Lower Leg Actuator", "Hand Actuator": "Foot Actuator" };
const LEG_TO_ARM = Object.fromEntries(Object.entries(ARM_TO_LEG).map(([a, l]) => [l, a]));
const QUAD_NAMES = [["Left Arm", "Front Left Leg", "LA", "FLL"], ["Right Arm", "Front Right Leg", "RA", "FRL"], ["Left Leg", "Rear Left Leg", "LL", "RLL"], ["Right Leg", "Rear Right Leg", "RL", "RRL"]];
const TECHBASES = ["Inner Sphere", "Clan", "Mixed (IS Chassis)", "Mixed (Clan Chassis)"];

// one state per open sheet window (previews from the browser's eye column can be open side by side); `SHEET` points at the one
// being drawn or answering an event (a capture listener on each window sets it before any handler there runs)
let SHEET = null;
const newSheet = (extra) => ({ mtf: null, original: "", id: "", team: null, unit: null, edit: false, pick: null, structure: {}, eval: null, evalError: "", msg: "", find: "", allAmmo: false, tray: [], evalTimer: 0, el: null, ...extra });
function createSheetWindow(S) {
  const d = document.createElement("div");
  d.className = "dialog sheet" + (S.edit ? " editing" : ""); d.setAttribute("role", "dialog");
  d.innerHTML = `<div class="titlebar"><span class="box" aria-hidden="true"></span><span class="name sheet-title-text">Unit sheet</span><button class="closebox" aria-label="Close">&times;</button></div>
    <div class="dialog-body"><div class="sheet-scroll"></div><div class="filters sheet-foot"></div></div>`;
  const n = document.querySelectorAll(".dialog.sheet").length;
  if (S.edit) { d.style.left = `${40 + (n % 8) * 28}px`; d.style.top = `${60 + (n % 8) * 28}px`; }
  else {
    // a preview opens against the right edge (the browser's eyes stay clickable) and the next one a little to the left and down
    const w = Math.min(720, window.innerWidth - 24);
    d.style.width = `${w}px`; d.style.left = `${Math.max(8, window.innerWidth - w - 16 - (n % 6) * 30)}px`; d.style.top = `${60 + (n % 6) * 30}px`;
  }
  $("app").appendChild(d);
  S.el = d;
  for (const ev of ["pointerdown", "click", "change", "input", "focusin", "dragstart", "drop", "toggle"]) d.addEventListener(ev, () => { SHEET = S; }, true);
  wireDialogMove(d, d.querySelector(".titlebar"));
  d.querySelector(".closebox").addEventListener("click", () => closeSheet(S));
  wireRaise(d); raiseWindow(d);
  return d;
}
let equipment = null;                       // { list, byAlias } from api "equipment_list"
const normName = (s) => String(s).toLowerCase().replace(/\s+/g, "");
const stripTags = (s) => String(s).replace(/\s*\((R|OMNIPOD|T|SPLIT|ARMORED)\)/gi, "");
const lookupEq = (raw) => (equipment ? equipment.byAlias.get(normName(stripTags(raw))) : null);
async function loadEquipment() {
  if (equipment) return;
  const r = await api("equipment_list");
  const list = r.equipment || [], byAlias = new Map();
  list.forEach((e) => (e.al || []).forEach((a) => { if (!byAlias.has(a)) byAlias.set(a, e); }));
  equipment = { list, byAlias };
}
// "ISERLargeLaser" -> "ER Large Laser", "CLERLargeLaser" -> "Clan ER Large Laser"
function pretty(raw) {
  let s = stripTags(raw).trim();
  const clan = /^CL(?=[A-Z])/.test(s);
  s = s.replace(/^(IS|CL)(?=[A-Z])/, "").replace(/([a-z])([A-Z0-9])/g, "$1 $2").replace(/([A-Z])([A-Z][a-z])/g, "$1 $2");
  return (clan ? "Clan " : "") + s;
}
// the folder an equipment item is listed under
const PHYSICAL_RE = /hatchet|sword|retractable|chain ?whip|mace|saw|claw|lance|flail|vibro|talon|wrecking|pile|dual saw|lift hoist|backhoe|rock cutter|spot welder/i;
function folderOf(e) {
  if (e.cat === "ammo") return "Ammo";
  if (e.cat === "weapon") return e.dt === "Energy" ? "Energy" : e.dt === "Ballistic" ? "Ballistic" : e.dt === "Missile" ? "Missile" : "Other";
  return PHYSICAL_RE.test(e.n + e.k) ? "Physical" : "Other";
}
const FOLDERS = ["Energy", "Ballistic", "Missile", "Physical", "Other", "Ammo"];
// does this ammo belong to a weapon on the unit: the ammo's name (without IS / CL and "Ammo") is the weapon's, or starts it
// (and the next letter is not a digit, so AC/2 ammo is not AC/20's)
const ammoBase = (a) => normName(a).replace(/^(is|cl|clan)/, "").replace(/ammo/g, "").replace(/[^a-z0-9]/g, "");
function ammoFits(ammo, present) {
  const b = ammoBase(ammo.k); if (!b) return false;
  return present.some((w) => (w.al || []).some((a) => { const x = ammoBase(a); return x === b || (x.startsWith(b) && !/\d/.test(x[b.length] || "")); }));
}

// the file as a list of lines; every edit changes a line in place
class Mtf {
  constructor(text) { this.nl = text.includes("\r\n") ? "\r\n" : "\n"; this.lines = text.split(/\r?\n/); }
  text() { return this.lines.join(this.nl); }
  find(key) { const k = key.toLowerCase() + ":"; return this.lines.findIndex((l) => l.toLowerCase().startsWith(k)); }
  get(key) { const i = this.find(key); return i < 0 ? "" : this.lines[i].slice(key.length + 1).trim(); }
  set(key, value) {
    const i = this.find(key);
    if (i >= 0) { this.lines[i] = this.lines[i].slice(0, key.length + 1) + value; return; }
    const w = this.find("mass"); this.lines.splice(w >= 0 ? w + 1 : this.lines.length, 0, `${key}:${value}`);
  }
  locations() {
    const out = [];
    this.lines.forEach((l, i) => {
      const m = LOC_RE.exec(l); if (!m) return;
      let j = i + 1; while (j < this.lines.length && this.lines[j].trim() !== "" && !LOC_RE.test(this.lines[j])) j++;
      const name = m[1].replace(/\b\w/g, (c) => c.toUpperCase());
      out.push({ name, at: i + 1, n: j - i - 1, cap: Math.min(j - i - 1, slotCap(name)) });
    });
    return out;
  }
  armor() {
    const out = [];
    this.lines.forEach((l, i) => {
      const m = /^([A-Za-z]{2,3}) armor:\s*(\d+)/i.exec(l); const k = m && ARMOR_KEYS[m[1].toLowerCase()];
      if (k) out.push({ line: i, key: m[1], loc: k[0], side: k[1], val: +m[2] });
    });
    return out;
  }
  // the "LA IS:17" lines (internal structure by hand); {} when the file has none
  isLines() {
    const out = {};
    this.lines.forEach((l, i) => { const m = /^([A-Za-z]{2,3}) IS:\s*(\d+)/i.exec(l); const k = m && ARMOR_KEYS[m[1].toLowerCase()]; if (k && k[1] === "front") out[k[0]] = { line: i, val: +m[2] }; });
    return out;
  }
  setIS(loc, val, all) {          // all = every location's current value, written together the first time
    let have = this.isLines();
    if (!Object.keys(have).length) {
      let at = this.armor().reduce((n, a) => Math.max(n, a.line), -1) + 1; if (at <= 0) at = this.lines.length;
      const add = Object.entries(all).filter(([l]) => KEY_OF[l]).map(([l, v]) => `${KEY_OF[l]} IS:${v}`);
      this.lines.splice(at, 0, ...add); have = this.isLines();
    }
    if (have[loc]) this.lines[have[loc].line] = this.lines[have[loc].line].replace(/:\s*\d+/, `:${val}`);
  }
  // the Weapons: block follows the crit slots (the engine reads the slots; the block feeds the list's weapon search)
  rewriteWeapons() {
    const block = [];
    for (const loc of this.locations()) {
      let run = null;
      const flush = () => { if (run) { const e = lookupEq(run.raw); const per = e && e.slots > 0 ? e.slots : 1; if (e && e.cat === "weapon") block.push(`${Math.max(1, Math.floor(run.n / per))} ${stripTags(run.raw)}, ${loc.name}`); run = null; } };
      for (let k = 0; k < loc.cap; k++) { const raw = this.lines[loc.at + k]; if (raw === EMPTY) { flush(); continue; } if (run && normName(run.raw) === normName(raw)) run.n++; else { flush(); run = { raw, n: 1 }; } }
      flush();
    }
    const i = this.lines.findIndex((l) => /^weapons:\s*\d+/i.test(l));
    if (i < 0) return;
    let j = i + 1; while (j < this.lines.length && this.lines[j].trim() !== "") j++;
    this.lines.splice(i, j - i, `Weapons:${block.length}`, ...block);
  }
}

// ---- the design as numbers
const sheetTons = () => +SHEET.mtf.get("Mass") || 0;
const engineRating = () => parseInt(SHEET.mtf.get("Engine"), 10) || 0;
const engineKind = () => { const t = SHEET.mtf.get("Engine").replace(/^\d+\s*/, ""); return ENGINES.find(([n]) => normName(n.replace(/ Engine$/, "")) === normName(t.replace(/\(.*?\)\s*$/, "").replace(/ Engine$/, "").replace(/ Fusion$/, ""))) || (/xxl/i.test(t) ? /clan/i.test(t) ? ENGINES[5] : ENGINES[4] : /xl/i.test(t) ? /clan/i.test(t) ? ENGINES[2] : ENGINES[1] : /light/i.test(t) ? ENGINES[3] : /compact/i.test(t) ? ENGINES[6] : /ice/i.test(t) ? ENGINES[7] : /fuel/i.test(t) ? ENGINES[8] : ENGINES[0]); };
const engineFree = () => { const k = engineKind()[0]; return /ICE|Fuel/.test(k) ? 0 : Math.floor(engineRating() / 25); };       // sinks the engine holds
const gyroKind = () => { const t = SHEET.mtf.get("Gyro"); return GYROS.find(([n]) => normName(n) === normName(t)) || GYROS.find(([n]) => t && normName(t).includes(normName(n.split(" ")[0]))) || GYROS[0]; };
const cockpitKind = () => { const t = SHEET.mtf.get("Cockpit"); return Object.keys(COCKPITS).find((n) => normName(n) === normName(t)) || "Standard Cockpit"; };
const sinkInfo = () => { const m = /^(\d+)\s*(\w*)/.exec(SHEET.mtf.get("Heat Sinks")) || []; return { n: +m[1] || 0, type: /double/i.test(m[2]) ? "Double" : "Single" }; };
const isClanTech = () => /clan/i.test(SHEET.mtf.get("TechBase")) && !/mixed \(IS/i.test(SHEET.mtf.get("TechBase"));
function sinkItem() {          // [slot name, slots each] for the design's heat sink type
  if (sinkInfo().type === "Single") return ["Heat Sink", 1];
  return isClanTech() ? ["CLDoubleHeatSink", 2] : ["ISDoubleHeatSink", 3];
}
const isSinkSlot = (raw) => /heatsink/.test(normName(raw)) && !/ammo/.test(normName(raw));
// a heat sink item takes 1 slot (single), 3 (inner sphere double) or 2 (clan double): the equipment database lists each as 1
const sinkSlotSize = (raw) => (/double/i.test(raw) ? (/^cl/i.test(String(raw).trim()) ? 2 : 3) : 1);
const isJetSlot = (raw) => /jumpjet/.test(normName(raw)) && !/ammo/.test(normName(raw));
const STRUCT_SLOT = /^(IS |Clan |CL )?(Endo Steel|Endo-Steel|Endo-Composite|Endo Composite|Ferro-Fibrous|Light Ferro-Fibrous|Heavy Ferro-Fibrous)$/i;
const isStructSlot = (raw) => STRUCT_SLOT.test(String(raw).trim());
// every slot of every location the sheet shows: [{loc, k, i (index in lines), raw}]
function allSlots() { const out = []; for (const loc of SHEET.mtf.locations()) for (let k = 0; k < loc.cap; k++) out.push({ loc: loc.name, k, i: loc.at + k, raw: SHEET.mtf.lines[loc.at + k] }); return out; }
// the items on the unit: a run of equal names, cut into pieces of the item's size
function itemsOf(pred) {
  const items = [], slots = allSlots();
  for (const s of slots) {
    if (!pred(s.raw)) continue;
    const e = lookupEq(s.raw), size = isSinkSlot(s.raw) ? sinkSlotSize(s.raw) : e && e.slots > 0 ? e.slots : 1;
    const last = items[items.length - 1];
    if (last && last.loc === s.loc && last.name === normName(s.raw) && last.at.length < last.size && last.at[last.at.length - 1] === s.i - 1) last.at.push(s.i);
    else items.push({ loc: s.loc, name: normName(s.raw), size, at: [s.i] });
  }
  return items;
}
const PREFER = { sink: [/Arm/, /Leg/, /Torso/], jet: [/Leg/, /Torso/], struct: [/Arm/, /Leg/, /Torso/] };
// put `size` equal slots in the first location of the preferred kinds that has that many empty ones in a row
function placeRun(name, size, prefs) {
  const m = SHEET.mtf;
  for (const pref of prefs) for (const loc of m.locations()) {
    if (!pref.test(loc.name) || /Head/.test(loc.name)) continue;
    for (let k = 0; k + size <= loc.cap; k++) {
      let free = true; for (let q = 0; q < size; q++) if (m.lines[loc.at + k + q] !== EMPTY) { free = false; break; }
      if (free) { for (let q = 0; q < size; q++) m.lines[loc.at + k + q] = name; return true; }
    }
  }
  return false;
}
// "first empty slots" of a location, `n` of them (not necessarily in a row): for engine and gyro slots
function takeEmpty(locName, n, name) {
  const m = SHEET.mtf, loc = m.locations().find((l) => l.name === locName); if (!loc) return n === 0;
  const idx = []; for (let k = 0; k < loc.cap && idx.length < n; k++) if (m.lines[loc.at + k] === EMPTY) idx.push(loc.at + k);
  if (idx.length < n) return false;
  idx.forEach((i) => { m.lines[i] = name; });
  return true;
}
const clearNamed = (locName, pred) => { const m = SHEET.mtf, loc = m.locations().find((l) => l.name === locName); if (loc) for (let k = 0; k < loc.n; k++) if (pred(m.lines[loc.at + k])) m.lines[loc.at + k] = EMPTY; };
// engine / gyro: the old slots out, the new ones into the first empty places; false (and the caller puts the lines back) when they do not fit
function rebuildEngineGyro(engine, gyro) {
  for (const loc of ["Center Torso", "Left Torso", "Right Torso"]) clearNamed(loc, (r) => /^(fusion engine|gyro)$/i.test(r.trim()) || /^engine$/i.test(r.trim()));
  return takeEmpty("Center Torso", engine[1], "Fusion Engine") && takeEmpty("Center Torso", gyro[1], "Gyro") && takeEmpty("Left Torso", engine[2], "Fusion Engine") && takeEmpty("Right Torso", engine[2], "Fusion Engine");
}
function rebuildCockpit(name) {
  const m = SHEET.mtf, c = COCKPITS[name], head = m.locations().find((l) => l.name === "Head"); if (!head) return true;
  clearNamed("Head", (r) => /^(life support|sensors|cockpit(\s*\(armored\))?)$/i.test(r.trim()));
  clearNamed("Center Torso", (r) => /^cockpit$/i.test(r.trim()));
  for (let k = 0; k < 6; k++) if (c.head[k] !== E) { if (m.lines[head.at + k] !== E) return false; m.lines[head.at + k] = c.head[k]; }
  return c.ct ? takeEmpty("Center Torso", c.ct, "Cockpit") : true;
}
// the configuration: the location blocks, their actuators and the armor / structure lines change; false (nothing changed) when a
// slot that would be lost holds equipment
function convertConfig(target) {
  const m = SHEET.mtf, cur = configOf(); if (cur === target) return true;
  const omni = /omni/i.test(m.get("Config")) ? " Omnimech" : "";
  const locs = () => m.locations();
  const keepsOnly = (name, ok) => { const loc = locs().find((l) => l.name === name); return !loc || Array.from({ length: loc.n }, (_, k) => m.lines[loc.at + k]).every((r, k) => r === EMPTY || ok(r, k)); };
  const rename = (from, to, map, keyFrom, keyTo) => {
    const i = m.lines.findIndex((l) => l.toLowerCase() === from.toLowerCase() + ":"); if (i < 0) return;
    m.lines[i] = to + ":";
    for (let k = i + 1; k < m.lines.length && m.lines[k].trim() !== "" && !LOC_RE.test(m.lines[k]); k++) if (map[m.lines[k].trim()]) m.lines[k] = map[m.lines[k].trim()];
    m.lines = m.lines.map((l) => l.replace(new RegExp(`^${keyFrom} (armor|IS):`, "i"), `${keyTo} $1:`));
  };
  const toTripod = () => {
    if (m.lines.some((l) => /^Center Leg:/i.test(l))) return;
    const rl = locs().find((l) => l.name === "Right Leg"); if (!rl) return;
    const end = rl.at + rl.n, leg = ["Hip", "Upper Leg Actuator", "Lower Leg Actuator", "Foot Actuator"];
    m.lines.splice(end, 0, "", "Center Leg:", ...leg, ...Array(rl.n - 4).fill(EMPTY));
    const ra = m.armor().find((a) => a.loc === "Right Leg"); if (ra) m.lines.splice(ra.line + 1, 0, `CL armor:${ra.val}`);
    const ri = m.isLines()["Right Leg"]; if (ri) m.lines.splice(ri.line + 1, 0, `CL IS:${ri.val}`);
  };
  const fromTripod = () => {
    const cl = locs().find((l) => l.name === "Center Leg"); if (!cl) return true;
    if (!keepsOnly("Center Leg", (r, k) => k < 4 && LEG_TO_ARM[r.trim()] !== undefined)) return false;
    m.lines.splice(cl.at - 1, cl.n + 1 + (m.lines[cl.at + cl.n] === "" ? 1 : 0));
    m.lines = m.lines.filter((l) => !/^CL (armor|IS):/i.test(l));
    return true;
  };
  if (cur === "Tripod") { if (!fromTripod()) return false; }
  const from = cur === "Tripod" ? "Biped" : cur, to = target === "Tripod" ? "Biped" : target;
  if (from === "Biped" && to === "Quad") {
    for (const [arm] of QUAD_NAMES.slice(0, 2)) { const loc = locs().find((l) => l.name === arm); if (loc && Array.from({ length: loc.n - 6 }, (_, k) => m.lines[loc.at + 6 + k]).some((r) => r !== EMPTY)) return false; }
    for (const [a, l, ka, kl] of QUAD_NAMES) rename(a, l, /Arm/.test(a) ? ARM_TO_LEG : {}, ka, kl);
  } else if (from === "Quad" && to === "Biped") {
    for (const [a, l, ka, kl] of QUAD_NAMES) rename(l, a, /Arm/.test(a) ? LEG_TO_ARM : {}, kl, ka);
  }
  if (target === "Tripod") toTripod();
  m.set("Config", target + omni);
  return true;
}

// how many of each slot kind a design should have, for the warnings
function expectedStructSlots() {
  const st = SHEET.mtf.get("Structure"), ar = SHEET.mtf.get("Armor"), clan = (t) => /clan/i.test(t) || (!/\bIS\b|inner sphere/i.test(t) && isClanTech());
  let n = 0;
  if (/endo.?steel/i.test(st)) n += clan(st) ? 7 : 14;
  if (/endo.?composite/i.test(st)) n += clan(st) ? 4 : 7;
  if (/light ferro/i.test(ar)) n += 7; else if (/heavy ferro/i.test(ar)) n += 21; else if (/ferro-?fibrous/i.test(ar) && !/lamellor/i.test(ar)) n += clan(ar) ? 7 : 14;
  return n;
}

// ---- items that still need a place: made by a choice (equipment picked, MASC, armor / structure types) and dragged into the slots
// {name: what is written in a slot, size: slots in a row, count: how many of them, label}
const MASC_PLACEHOLDER = "MASC size is a PLACEHOLDER (tons / 20 inner sphere, tons / 25 clan, rounded) until the TechManual is indexed.";
function addToTray(name, size, count, label) {
  const t = SHEET.tray.find((x) => x.name === name && x.size === size);
  if (t) t.count += count; else SHEET.tray.push({ name, size, count, label: label || pretty(name) });
}
function maybeTrayForTypes() {      // after a structure / armor / myomer change: the slots the new types ask for, not yet placed, wait in the tray
  const m = SHEET.mtf, want = expectedStructSlots(), have = allSlots().filter((s) => isStructSlot(s.raw)).length + SHEET.tray.filter((t) => isStructSlot(t.name)).reduce((n, t) => n + t.count, 0);
  if (want > have) addToTray((/clan/i.test(m.get("Structure") + m.get("Armor")) ? "Clan " : "IS ") + (/endo/i.test(m.get("Structure")) ? "Endo Steel" : "Ferro-Fibrous"), 1, want - have);
  if (/masc/i.test(m.get("Myomer")) && !allSlots().some((s) => /masc/i.test(s.raw)) && !SHEET.tray.some((t) => /masc/i.test(t.name))) {
    const clan = isClanTech(), n = Math.max(1, Math.round(sheetTons() / (clan ? 25 : 20)));
    addToTray(clan ? "CLMASC" : "ISMASC", n, 1, `MASC (${n} slot${n === 1 ? "" : "s"})`);
    SHEET.msg = MASC_PLACEHOLDER;
  }
}
// ---- warnings: [{level: "ok" | "warn" | "bad", text, fix?: [label, fn]}]; only "bad" (the engine cannot read the design) holds anything back
function sheetChecks() {
  const m = SHEET.mtf, out = [], rating = engineRating();
  if (SHEET.eval && SHEET.eval.ok === false) out.push({ level: "bad", text: `The engine cannot play this design: ${SHEET.eval.why}` });
  const { n } = sinkInfo(), free = Math.min(n, engineFree()), [sname, size] = sinkItem(), have = itemsOf(isSinkSlot).length, need = n - free;
  const ofs = have - need;
  if (ofs < 0) out.push({ level: "warn", text: `Heat sinks: ${n} (${free} fit in the engine), so ${need} should be in the critical slots: ${have} are placed, ${-ofs} short (${-ofs * size} slot${-ofs * size === 1 ? "" : "s"}).`, fix: [`Place ${-ofs}`, () => placeMany(isSinkSlot, -ofs, sname, size, PREFER.sink)] });
  else if (ofs > 0) out.push({ level: "warn", text: `Heat sinks: ${n} (${free} fit in the engine) but ${have} are placed in the slots, ${ofs} more than needed.` });
  const jets = itemsOf(isJetSlot).length, jump = +m.get("Jump MP") || 0;
  if (jets < jump) out.push({ level: "warn", text: `Jump MP ${jump} should have ${jump} jump jets in the slots: ${jets} are placed, ${jump - jets} short.`, fix: [`Place ${jump - jets}`, () => placeMany(isJetSlot, jump - jets, "Jump Jet", 1, PREFER.jet)] });
  else if (jets > jump) out.push({ level: "warn", text: `${jets} jump jets in the slots for Jump MP ${jump}.` });
  const ss = allSlots().filter((s) => isStructSlot(s.raw)).length, want = expectedStructSlots();
  if (ss < want) out.push({ level: "warn", text: `${m.get("Structure")} structure / ${m.get("Armor")} armor should take ${want} critical slots: ${ss} are placed, ${want - ss} short.`, fix: [`Place ${want - ss}`, () => placeMany(isStructSlot, want - ss, (/clan/i.test(m.get("Structure") + m.get("Armor")) ? "Clan " : "IS ") + (/endo/i.test(m.get("Structure")) ? "Endo Steel" : "Ferro-Fibrous"), 1, PREFER.struct, true)] });
  else if (ss > want) out.push({ level: "warn", text: `${ss} structure / armor slots are placed, ${ss - want} more than ${want}.` });
  if (n < 10) out.push({ level: "warn", text: `A 'Mech normally has at least 10 heat sinks (this has ${n}).` });
  if (rating > 400) out.push({ level: "warn", text: `Engine rating ${rating} is above 400.` });
  const tons = sheetTons(), walk = +m.get("Walk MP") || 0;
  if (rating && tons && walk * tons !== rating) out.push({ level: "warn", text: `Engine rating ${rating} is not Walk MP ${walk} x ${tons} t = ${walk * tons}.` });
  if (!STRUCT_ROWS.some((r) => r[0] === tons) && !Object.keys(m.isLines()).length) out.push({ level: "warn", text: `${tons} t has no internal structure in the table (10-200 t in steps of 5): press "Use tonnage" (the most the engine plays is 200 t), then edit the points by hand.` });
  const st = SHEET.structure, rear = {}; m.armor().filter((a) => a.side === "rear").forEach((a) => { rear[a.loc] = a.val; });
  for (const a of m.armor().filter((x) => x.side === "front")) {
    const s = st[a.loc]; if (s == null) continue;
    const max = a.loc === "Head" ? 9 : 2 * s;
    if (a.val + (rear[a.loc] || 0) > max) out.push({ level: "warn", text: `${a.loc} armor ${a.val + (rear[a.loc] || 0)} is more than twice its internal structure (${max}).` });
  }
  const waiting = SHEET.tray.reduce((n, t) => n + t.count, 0);
  if (waiting) out.push({ level: "warn", text: `${waiting} item${waiting === 1 ? "" : "s"} still need${waiting === 1 ? "s" : ""} a place: drag ${waiting === 1 ? "it" : "them"} from "Needs a place" into the slots.` });
  if (!out.length) out.push({ level: "ok", text: "Nothing to warn about. (Legality is not checked.)" });
  return out;
}
function placeMany(pred, count, name, size, prefs) {
  let placed = 0; while (placed < count && placeRun(name, size, prefs)) placed++;
  sheetChanged(placed < count ? `Only ${placed} of ${count} fitted: the critical slots are full.` : "");
}

// ---- opening, evaluating, drawing
async function openSheet(id, team, unit) {
  await loadEquipment();
  let text, base = id;
  if (team != null && lab.teams[team].units[unit].mtf) { text = lab.teams[team].units[unit].mtf; base = lab.teams[team].units[unit].base || id; }
  else { const r = await api("unit_text", { id }); if (r.error) { setStatus(`${id}: ${r.error}`); return; } text = r.text; }
  const S = newSheet({ mtf: new Mtf(text), original: text, id: base, team, unit, edit: team != null, unitJson: lab.byId.get(base) || {} });
  createSheetWindow(S); SHEET = S;
  drawSheet(); evalSheet();
}
function evalSheet() {
  const S = SHEET;
  clearTimeout(S.evalTimer);
  S.evalTimer = setTimeout(async () => {
    if (!S.mtf) return;
    const r = await api("unit_eval", { text: S.mtf.text() });
    S.eval = r.error ? null : r.unit; S.structure = r.structure || {}; S.evalError = r.error || "";
    if (S.mtf && S.el.isConnected) { SHEET = S; drawSheet(); }
  }, 200);
}
function sheetBv() {
  const e = SHEET.eval; const base = e && e.ok ? e.bv : (SHEET.evalError ? null : SHEET.unitJson.bv);
  if (base == null) return "n/a here (the program works it out)";
  const t = SHEET.team != null ? lab.teams[SHEET.team].units[SHEET.unit] : null, table = lab.info.skill_table;
  return t && table ? `${Math.floor(base * table[t.gunnery][t.piloting] + 0.5)} with this pilot (${base} at 4 / 5)` : String(base);
}
const opts = (list, cur) => list.map((x) => { const v = Array.isArray(x) ? x[0] : x; return `<option${normName(v) === normName(cur) ? " selected" : ""}>${esc(v)}</option>`; }).join("");
function drawSheet() {
  const S = SHEET, root = S.el, m = S.mtf, ed = S.edit, off = ed ? "" : " disabled";
  const rating = engineRating(), tons = sheetTons(), walk = +m.get("Walk MP") || 0, jump = +m.get("Jump MP") || 0, sk = sinkInfo();
  const changed = m.text() !== S.original;
  root.querySelector(".sheet-title-text").textContent = `${m.get("chassis")} ${m.get("model")}`.trim() + (ed ? "  -  editing (temporary)" : "");
  const armor = m.armor(), rear = {}; armor.filter((a) => a.side === "rear").forEach((a) => { rear[a.loc] = a; });
  const totalArmor = armor.reduce((n, a) => n + a.val, 0), isl = m.isLines();
  const checks = sheetChecks();
  const armorRows = armor.filter((a) => a.side === "front").map((a) => {
    const st = isl[a.loc] ? isl[a.loc].val : S.structure[a.loc], max = a.loc === "Head" ? 9 : st != null ? 2 * st : "";
    const r = rear[a.loc];
    return `<tr><td>${esc(a.loc)}</td><td class="num"><input type="number" min="0" data-armor="${a.line}" value="${a.val}"${off}></td><td class="num">${r ? `<input type="number" min="0" data-armor="${r.line}" value="${r.val}"${off}>` : ""}</td><td class="num"><input type="number" min="0" data-is="${esc(a.loc)}" value="${st ?? ""}"${off}></td><td class="num">${max}</td></tr>`;
  }).join("");
  // equipment totals from the slots
  const tally = new Map();
  for (const it of itemsOf((raw) => raw !== EMPTY && !!lookupEq(raw) && !isSinkSlot(raw) && !isJetSlot(raw))) {
    const raw = m.lines[it.at[0]], e = lookupEq(raw), k = normName(raw);
    const row = tally.get(k) || { e, raw, n: 0 }; row.n++; tally.set(k, row);
  }
  const eqRows = [...tally.values()].sort((a, b) => (b.e.tons || 0) - (a.e.tons || 0)).map((r) => `<tr><td>${esc(pretty(r.raw))}</td><td class="num">${r.n}</td><td class="num">${r.e.slots}</td><td class="num">${r.e.tons ?? ""}</td><td class="num">${r.e.heat ?? ""}</td><td class="num">${r.e.dmg ?? ""}</td></tr>`).join("");
  const grid = m.locations().map((loc) => {
    let freeN = 0;
    const slots = Array.from({ length: loc.cap }, (_, k) => {
      const raw = m.lines[loc.at + k]; let cls = "crit-slot", title = "", inner;
      const act = /Arm/.test(loc.name) && ACTUATORS[k];
      if (act && (raw === EMPTY || raw === act)) {
        // the lower arm and hand actuators are check boxes beside their slots
        if (raw === EMPTY) freeN++;
        inner = `<label><input type="checkbox" data-act="${esc(loc.name)}:${k}"${raw === act ? " checked" : ""}${off}> ${esc(raw === act ? act : `(${act.toLowerCase()})`)}</label>`;
        cls += raw === act ? " fixed" : " empty";
      } else {
        if (raw === EMPTY) { cls += " empty"; freeN++; } else if (isFixed(raw)) { cls += " fixed"; title = "A built-in part of the 'Mech: it cannot be taken out"; }
        inner = raw === EMPTY ? "(empty)" : esc(pretty(raw));
      }
      return `<div class="${cls}" data-loc="${esc(loc.name)}" data-k="${k}" title="${esc(title)}">${inner}</div>`;
    }).join("");
    const pos = SHEET_POS[loc.name] || [3, 3];
    return `<div class="crit-loc" style="grid-row:${pos[0]};grid-column:${pos[1]}"><h4><span>${esc(loc.name)}</span><span>${freeN} free</span></h4>${slots}</div>`;
  }).join("");
  // the equipment picker: one folder each for Energy, Ballistic, Missile, Physical, Other and the ammo of the weapons on the unit
  let picker = "";
  if (ed) {
    const present = itemsOf((raw) => raw !== EMPTY && !!lookupEq(raw) && lookupEq(raw).cat === "weapon").map((it) => lookupEq(m.lines[it.at[0]]));
    const q = normName(S.find);
    const folders = FOLDERS.map((f) => {
      let list = equipment.list.filter((e) => folderOf(e) === f && (!q || normName(e.n + e.k).includes(q)));
      if (f === "Ammo" && !S.allAmmo) list = list.filter((e) => ammoFits(e, present));
      const sel = `<select size="8" data-folder="${f}">${list.slice(0, 400).map((e) => `<option value="${esc(e.k)}"${S.pick && S.pick.k === e.k ? " selected" : ""}>${esc(pretty(e.k))} (${e.slots} slot${e.slots === 1 ? "" : "s"}${e.tons != null ? `, ${e.tons} t` : ""}${e.heat != null ? `, heat ${e.heat}` : ""})</option>`).join("")}</select>`;
      return `<details class="folder"${S.open && S.open[f] ? " open" : ""} data-fname="${f}"><summary>${f} <span class="note">(${list.length}${f === "Ammo" && !S.allAmmo ? ", for the weapons on this unit" : ""})</span></summary>${f === "Ammo" ? `<label class="row"><input type="checkbox" id="sh-allammo"${S.allAmmo ? " checked" : ""}> Show all ammo</label>` : ""}${sel}</details>`;
    }).join("");
    picker = `<div class="picker"><h3>Add equipment</h3><label>Find <input type="search" id="sh-find" placeholder="e.g. ER Large" value="${esc(S.find)}"></label>
      <div class="note">${S.pick ? `Click an empty slot to place ${esc(pretty(S.pick.k))}, or` : "Choose an item in a folder, then click an empty slot, or"} <button class="btn small" id="sh-totray"${S.pick ? "" : " disabled"}>send it to "Needs a place"</button>. Click a placed item to take it out; drag items to move them.</div>${folders}</div>`;
  }
  root.querySelector(".sheet-scroll").innerHTML = `
    <div class="head"><b>${esc(m.get("chassis"))} ${esc(m.get("model"))}</b><span>${tons} t</span><span>${esc(m.get("TechBase"))}</span><span>Battle Value ${esc(sheetBv())}</span>${changed ? `<span class="tag">modified (the original is ${esc(S.unitJson.bv ?? "?")})</span>` : ""}</div>
    <div class="sheet-msgs">${S.msg ? `<div class="bad">${esc(S.msg)}</div>` : ""}${checks.map((c, i) => `<div class="${c.level}">${c.level === "ok" ? "&#10003;" : c.level === "bad" ? "&#10007;" : "&#9888;"} ${esc(c.text)}${c.fix && ed ? ` <button class="btn small" data-fix="${i}">${esc(c.fix[0])}</button>` : ""}</div>`).join("")}</div>
    <div>
      <h3>Identity</h3>
      <table>
        <tr><td>Chassis</td><td colspan="2"><input type="text" id="sh-chassis" value="${esc(m.get("chassis"))}" style="width:150px"${off}></td></tr>
        <tr><td>Model</td><td colspan="2"><input type="text" id="sh-model" value="${esc(m.get("model"))}" style="width:150px"${off}></td></tr>
        <tr><td>Type</td><td colspan="2"><select id="sh-config"${off}>${opts(CONFIGS, configOf())}</select> <span class="note">${/omni/i.test(m.get("Config")) ? "Omni" : ""}</span></td></tr>
        <tr><td>Tonnage</td><td class="num"><input type="number" min="1" max="200" id="sh-mass" value="${tons}"${off}></td><td>${ed ? `<button class="btn small" id="sh-usetons" title="Rounds the tonnage up to a multiple of 5 and fills in the internal structure of the nearest tonnage in the table (10-200 t); edit the points by hand after">Use tonnage</button>` : ""}</td></tr>
        <tr><td>Tech base</td><td colspan="2"><select id="sh-tech"${off}>${opts(TECHBASES, m.get("TechBase"))}</select></td></tr>
      </table>
      <h3 style="margin-top:8px">Movement and heat</h3>
      <table>
        <tr><td>Engine</td><td colspan="2"><select id="sh-engine"${off}>${opts(ENGINES, engineKind()[0])}</select> <span class="note">${rating}</span></td></tr>
        <tr><td>Walk MP</td><td class="num"><input type="number" min="1" max="30" id="sh-walk" value="${walk}"${off}></td><td class="note">run ${Math.ceil(walk * 1.5)}; engine ${walk * tons}</td></tr>
        <tr><td>Jump MP</td><td class="num"><input type="number" min="0" max="30" id="sh-jump" value="${jump}"${off}></td><td class="note">${itemsOf(isJetSlot).length} jets placed</td></tr>
        <tr><td>Heat sinks</td><td class="num"><input type="number" min="0" max="500" id="sh-sinks" value="${sk.n}"${off}></td><td><select id="sh-sinktype"${off}><option${sk.type === "Single" ? " selected" : ""}>Single</option><option${sk.type === "Double" ? " selected" : ""}>Double</option></select></td></tr>
        <tr><td>Gyro</td><td colspan="2"><select id="sh-gyro"${off}>${opts(GYROS, gyroKind()[0])}</select></td></tr>
        <tr><td>Cockpit</td><td colspan="2"><select id="sh-cockpit"${off}>${opts(Object.keys(COCKPITS), cockpitKind())}</select></td></tr>
        <tr><td>Structure</td><td colspan="2"><select id="sh-structure"${off}>${opts(STRUCTURES, m.get("Structure").replace(/^(IS|Clan|CL) /i, "").replace(/-Steel/i, " Steel"))}</select></td></tr>
        <tr><td>Armor</td><td colspan="2"><select id="sh-armortype"${off}>${opts(ARMORS, m.get("Armor").replace(/\(.*\)/, "").replace(/^(IS|Clan|CL) /i, "").replace(/ Armor$/i, ""))}</select></td></tr>
        <tr><td>Myomer</td><td colspan="2"><select id="sh-myomer"${off}>${opts(MYOMERS, m.get("Myomer"))}</select></td></tr>
      </table>
      <h3 style="margin-top:8px">Armor (${totalArmor} points) and structure</h3>
      <table><thead><tr><th>Location</th><th class="num">Front</th><th class="num">Rear</th><th class="num" title="Internal structure points">IS</th><th class="num" title="Twice the internal structure (head 9)">2xIS</th></tr></thead><tbody>${armorRows}</tbody></table>
    </div>
    <div>
      <div class="crit-grid">${grid}</div>
      ${ed ? `<div class="tray" id="sh-tray"><b>Needs a place</b> ${S.tray.length ? S.tray.map((t, i) => `<span class="chip" draggable="true" data-tray="${i}" title="Drag into the slots">${esc(t.label)}${t.size > 1 && !/MASC/.test(t.label) ? ` (${t.size} slots)` : ""}${t.count > 1 ? ` x${t.count}` : ""} <button class="x" data-traydrop="${i}" title="Throw away">&times;</button></span>`).join(" ") : `<span class="note">Items that still need a place (new equipment, the slots a new armor, structure or myomer type asks for) wait here. Drag one into a slot, or drag a placed item back here.</span>`}</div>` : ""}
      ${picker}
      <h3 style="margin-top:8px">Weapons and equipment</h3>
      <table><thead><tr><th>Item</th><th class="num">Qty</th><th class="num">Slots</th><th class="num">Tons</th><th class="num">Heat</th><th class="num">Dmg</th></tr></thead><tbody>${eqRows}</tbody></table>
    </div>`;
  const foot = root.querySelector(".sheet-foot");
  foot.innerHTML = ed
    ? `<span class="note" style="flex:1;text-align:left">A modified unit is temporary: it is kept in the team and saved only inside a saved run.</span><button class="btn" id="sh-use"${checks.some((c) => c.level === "bad") ? " disabled" : ""}>Use this design for ${esc(lab.teams[S.team].name)}</button><button class="btn" id="sh-revert"${changed ? "" : " disabled"}>Revert changes</button><button class="btn" id="sh-close2">Close</button>`
    : `<button class="btn" id="sh-add">Add to ${esc((lab.teams[lab.addTo] || {}).name || "team")}</button><button class="btn" id="sh-close2">Close</button>`;
  wireSheet(checks);
}

function sheetChanged(msg) {
  SHEET.mtf.rewriteWeapons();
  SHEET.msg = msg || "";
  drawSheet(); evalSheet();
}
function wireSheet(checks) {
  const S = SHEET, root = S.el, m = S.mtf, q = (id) => root.querySelector("#" + id);
  q("sh-close2").addEventListener("click", () => closeSheet(S));
  if (!S.edit) { q("sh-add").addEventListener("click", () => { addUnits(lab.teams[lab.addTo], [S.id]); closeSheet(S); }); return; }
  const num = (id) => +q(id).value;
  // a change that moves slots around: if it does not fit the slots, the lines go back as they were and a message says why
  const attempt = (change, why) => { const before = m.lines.slice(); if (change() === false) { m.lines = before; sheetChanged(why); } else sheetChanged(); };
  q("sh-chassis").addEventListener("change", (e) => { m.set("chassis", e.target.value.trim() || m.get("chassis")); sheetChanged(); });
  q("sh-model").addEventListener("change", (e) => { m.set("model", e.target.value.trim() || m.get("model")); sheetChanged(); });
  q("sh-config").addEventListener("change", (e) => attempt(() => convertConfig(e.target.value), "A Biped to Quad change needs the arms' slots beyond the sixth to be empty (a leg has 6): take that equipment out first."));
  q("sh-tech").addEventListener("change", (e) => { m.set("TechBase", e.target.value); sheetChanged(); });
  q("sh-mass").addEventListener("change", () => { const t = Math.max(1, Math.min(200, Math.round(num("sh-mass")))); m.set("Mass", String(t)); m.set("Engine", m.get("Engine").replace(/^\d+/, String((+m.get("Walk MP") || 1) * t))); sheetChanged(); });      // the most the engine plays is 200 t
  q("sh-usetons").addEventListener("click", () => {
    const t = Math.max(10, Math.min(200, Math.ceil(sheetTons() / 5) * 5)), row = STRUCT_ROWS.find((r) => r[0] === t) || STRUCT_ROWS[STRUCT_ROWS.length - 1];
    const all = {}; for (const loc of m.locations()) all[loc.name] = /Head/.test(loc.name) ? (t >= 105 ? 4 : 3) : /Center Torso/.test(loc.name) ? row[1] : /Torso/.test(loc.name) ? row[2] : /Arm/.test(loc.name) ? row[3] : row[4];
    for (const l of Object.keys(m.isLines())) m.lines.splice(m.isLines()[l].line, 1);       // start from the table, then the points are edited by hand
    m.setIS("Head", all["Head"] ?? 3, all); for (const [loc, v] of Object.entries(all)) m.setIS(loc, v, all);
    sheetChanged(`Internal structure filled in from the ${t} t row of the table. Edit the points by hand if you like.`);
  });
  q("sh-engine").addEventListener("change", (e) => {
    const eng = ENGINES.find(([n]) => n === e.target.value); if (!eng) return;
    attempt(() => { m.set("Engine", `${engineRating()} ${eng[0]}`); return rebuildEngineGyro(eng, gyroKind()); }, `There is no room for that engine's slots (${eng[1]} in the centre torso, ${eng[2]} in each side torso): empty some slots there first.`);
  });
  q("sh-gyro").addEventListener("change", (e) => {
    const g = GYROS.find(([n]) => n === e.target.value); if (!g) return;
    attempt(() => { m.set("Gyro", g[0]); return rebuildEngineGyro(engineKind(), g); }, `There is no room for ${g[1]} gyro slots in the centre torso: empty some slots there first.`);
  });
  q("sh-cockpit").addEventListener("change", (e) => attempt(() => { m.set("Cockpit", e.target.value); return rebuildCockpit(e.target.value); }, "That cockpit needs head slots that hold other equipment: take that out first."));
  q("sh-structure").addEventListener("change", (e) => { m.set("Structure", (/endo|composite|reinforced/i.test(e.target.value) && isClanTech() ? "Clan " : "IS ") + e.target.value); maybeTrayForTypes(); sheetChanged(SHEET.msg); });
  q("sh-armortype").addEventListener("change", (e) => { m.set("Armor", `${e.target.value}(${isClanTech() ? "Clan" : "Inner Sphere"})`); maybeTrayForTypes(); sheetChanged(SHEET.msg); });
  q("sh-myomer").addEventListener("change", (e) => { m.set("Myomer", e.target.value); SHEET.msg = ""; maybeTrayForTypes(); sheetChanged(SHEET.msg); });
  // walk: the engine rating follows (Walk x tons); the sinks the engine holds change with it, but nothing is forced into the slots
  q("sh-walk").addEventListener("change", () => { const w = Math.max(1, Math.round(num("sh-walk"))); m.set("Walk MP", String(w)); m.set("Engine", m.get("Engine").replace(/^\d+/, String(w * sheetTons()))); sheetChanged(); });
  q("sh-jump").addEventListener("change", () => { m.set("Jump MP", String(Math.max(0, Math.round(num("sh-jump"))))); sheetChanged(); });
  q("sh-sinks").addEventListener("change", () => { m.set("Heat Sinks", `${Math.max(0, Math.round(num("sh-sinks")))} ${sinkInfo().type}`); sheetChanged(); });
  q("sh-sinktype").addEventListener("change", (e) => { m.set("Heat Sinks", `${sinkInfo().n} ${e.target.value}`); sheetChanged("The heat sinks in the slots are still the old kind: take them out and place the new ones with the button."); });
  root.querySelectorAll("[data-armor]").forEach((i) => i.addEventListener("change", () => { const ln = +i.dataset.armor; m.lines[ln] = m.lines[ln].replace(/:\s*\d+/, `:${Math.max(0, Math.round(+i.value))}`); sheetChanged(); }));
  root.querySelectorAll("[data-is]").forEach((i) => i.addEventListener("change", () => {
    const all = { ...S.structure }; const isl = m.isLines(); for (const l of Object.keys(isl)) all[l] = isl[l].val;
    m.setIS(i.dataset.is, Math.max(0, Math.round(+i.value)), all); sheetChanged();
  }));
  root.querySelectorAll("[data-fix]").forEach((b) => b.addEventListener("click", () => checks[+b.dataset.fix].fix[1]()));
  root.querySelectorAll("[data-act]").forEach((c) => {
    c.addEventListener("click", (e) => e.stopPropagation());
    c.addEventListener("change", () => {
      const [locName, k] = c.dataset.act.split(":"), loc = m.locations().find((l) => l.name === locName), at = loc.at + +k;
      if (c.checked) { if (m.lines[at] !== EMPTY) { sheetChanged("That slot is taken."); return; } m.lines[at] = ACTUATORS[+k]; } else m.lines[at] = EMPTY;
      sheetChanged();
    });
  });
  q("sh-find").addEventListener("input", (e) => { S.find = e.target.value; const pos = e.target.selectionStart; drawSheet(); const f = q("sh-find"); f.focus(); f.setSelectionRange(pos, pos); });
  q("sh-allammo").addEventListener("change", (e) => { S.allAmmo = e.target.checked; S.open = { ...(S.open || {}), Ammo: true }; drawSheet(); });
  root.querySelectorAll("details.folder[data-fname]").forEach((d) => d.addEventListener("toggle", () => { S.open = { ...(S.open || {}), [d.dataset.fname]: d.open }; }));
  root.querySelectorAll("select[data-folder]").forEach((s) => s.addEventListener("change", (e) => { S.pick = equipment.list.find((x) => x.k === e.target.value) || null; S.open = { ...(S.open || {}), [s.dataset.folder]: true }; drawSheet(); }));
  root.querySelectorAll(".crit-slot").forEach((d) => d.addEventListener("click", () => slotClick(d.dataset.loc, +d.dataset.k)));
  q("sh-totray").addEventListener("click", () => { if (S.pick) { addToTray(S.pick.k, Math.max(1, S.pick.slots), 1); sheetChanged(); } });
  root.querySelectorAll("[data-traydrop]").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); const t = S.tray[+b.dataset.traydrop]; if (t && --t.count <= 0) S.tray.splice(+b.dataset.traydrop, 1); sheetChanged(); }));
  // drag and drop: a chip from the tray or a placed item goes onto an empty slot; a placed item goes back to the tray by dropping it there
  root.querySelectorAll("[data-tray]").forEach((c) => c.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/x-sheet", `tray:${c.dataset.tray}`)));
  root.querySelectorAll(".crit-slot[data-loc]").forEach((d) => {
    const raw = m.lines[m.locations().find((l) => l.name === d.dataset.loc).at + +d.dataset.k];
    const movable = raw !== EMPTY && !isFixed(raw) && !(/Arm/.test(d.dataset.loc) && ACTUATORS[+d.dataset.k] === raw);
    if (movable) { d.draggable = true; d.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/x-sheet", `slot:${d.dataset.loc}:${d.dataset.k}`)); }
    d.addEventListener("dragover", (e) => { e.preventDefault(); d.classList.add("drop"); });
    d.addEventListener("dragleave", () => d.classList.remove("drop"));
    d.addEventListener("drop", (e) => { e.preventDefault(); dropOn(e.dataTransfer.getData("text/x-sheet"), d.dataset.loc, +d.dataset.k); });
  });
  const tray = q("sh-tray");
  tray.addEventListener("dragover", (e) => e.preventDefault());
  tray.addEventListener("drop", (e) => { e.preventDefault(); dropOnTray(e.dataTransfer.getData("text/x-sheet")); });
  q("sh-revert").addEventListener("click", () => { S.mtf = new Mtf(S.original); sheetChanged(); });
  q("sh-use").addEventListener("click", useDesign);
}
function dropOn(what, locName, k) {
  const S = SHEET, m = S.mtf, loc = m.locations().find((l) => l.name === locName); if (!loc || !what) return;
  let name, size, undo;
  if (what.startsWith("tray:")) { const t = S.tray[+what.slice(5)]; if (!t) return; name = t.name; size = t.size; }
  else {
    const [, ln, kk] = what.split(":"), src = m.locations().find((l) => l.name === ln), at = src.at + +kk;
    const item = itemsOf(() => true).find((it) => it.at.includes(at)); if (!item) return;
    name = m.lines[item.at[0]]; size = item.at.length;
    const before = m.lines.slice(); item.at.forEach((i) => { m.lines[i] = EMPTY; }); undo = () => { m.lines = before; };
  }
  const at = loc.at + k;
  if (k + size > loc.cap || Array.from({ length: size }, (_, q) => m.lines[at + q]).some((x) => x !== EMPTY)) { if (undo) undo(); sheetChanged(`${pretty(name)} needs ${size} empty slot${size === 1 ? "" : "s"} in a row from there (${loc.name} has ${loc.cap}).`); return; }
  for (let q = 0; q < size; q++) m.lines[at + q] = name;
  if (what.startsWith("tray:")) { const t = S.tray[+what.slice(5)]; if (--t.count <= 0) S.tray.splice(+what.slice(5), 1); }
  sheetChanged();
}
function dropOnTray(what) {
  const S = SHEET, m = S.mtf; if (!what.startsWith("slot:")) return;
  const [, ln, kk] = what.split(":"), src = m.locations().find((l) => l.name === ln), at = src.at + +kk;
  const item = itemsOf(() => true).find((it) => it.at.includes(at)); if (!item) return;
  const name = m.lines[item.at[0]]; item.at.forEach((i) => { m.lines[i] = EMPTY; });
  addToTray(name, item.at.length, 1);
  sheetChanged();
}
function slotClick(locName, k) {
  const S = SHEET, m = S.mtf, loc = m.locations().find((l) => l.name === locName); if (!loc) return;
  const at = loc.at + k, raw = m.lines[at];
  if (raw === EMPTY) {
    const e = S.pick; if (!e) { sheetChanged("Choose equipment first."); return; }
    const size = Math.max(1, e.slots);
    if (k + size > loc.cap || Array.from({ length: size }, (_, q) => m.lines[at + q]).some((x) => x !== EMPTY)) { sheetChanged(`${pretty(e.k)} needs ${size} empty slot${size === 1 ? "" : "s"} in a row from there (${loc.name} has ${loc.cap}).`); return; }
    for (let q = 0; q < size; q++) m.lines[at + q] = e.k;
    sheetChanged(); return;
  }
  if (isFixed(raw) || (/Arm/.test(loc.name) && ACTUATORS[k] === raw)) { sheetChanged(ACTUATORS[k] === raw ? "Use the check box to take an actuator out." : "That is a built-in part of the 'Mech: it cannot be taken out."); return; }
  const item = itemsOf(() => true).find((it) => it.at.includes(at));
  for (const i of (item ? item.at : [at])) m.lines[i] = EMPTY;
  sheetChanged();
}
// "Use this design": the modified unit goes into the team as it is, temporary, carrying its own text
async function useDesign() {
  const S = SHEET, m = S.mtf;
  if (!/Modified in Combat Lab/.test(m.lines.slice(0, 3).join(" "))) m.lines.unshift("# Modified in Combat Lab: a temporary unit, not a published design.");
  const name = `${m.get("chassis")} ${m.get("model")}`.trim();
  const r = await api("unit_eval", { text: m.text() });
  const demoBv = DEMO && r.error;          // the demo has no engine to ask: the unit is used with no BV
  if (!demoBv && (r.error || !r.unit || !r.unit.ok)) { S.msg = r.error || (r.unit && r.unit.why) || "The engine cannot play this design."; m.lines.shift(); drawSheet(); return; }
  const t = lab.teams[S.team], old = t.units[S.unit], same = m.text() === S.original && !old.mtf;
  t.units[S.unit] = same ? unitEntry(S.id, old.gunnery, old.piloting)
    : { id: `modified:${S.id}`, base: S.id, name: /modified/i.test(name) ? name : `${name} (modified)`, tons: sheetTons(), bv: demoBv ? null : r.unit.bv, gunnery: old.gunnery, piloting: old.piloting, mtf: m.text(), modified: true };
  if (!same && !/modified/i.test(m.get("model"))) { /* the name shown carries "(modified)"; the file's own model line is left as edited */ }
  setStatus(same ? `${name}: no changes` : `${name} used in ${t.name} as a modified unit (temporary: it is saved with a saved run)`);
  closeSheet(S); save(); drawTeams();
}
// a team entry from a unit text carried in a setup or a saved state (bv: asked of the engine when it is not known)
function modifiedEntry(text, base, g, p, known) {
  const mt = new Mtf(text), name = `${mt.get("chassis")} ${mt.get("model")}`.trim();
  const e = { id: `modified:${base}`, base, name: /modified/i.test(name) ? name : `${name} (modified)`, tons: +mt.get("Mass") || null, bv: known ? known.bv : null, gunnery: g, piloting: p, mtf: text, modified: true };
  if (e.bv == null) api("unit_eval", { text }).then((r) => { if (r.unit && r.unit.ok) { e.bv = r.unit.bv; save(); drawTeams(); } });
  return e;
}
function closeSheet(S = SHEET) { if (!S) return; S.mtf = null; S.el.remove(); if (SHEET === S) SHEET = null; }
// a popup window goes on top when it opens or is clicked
function wireRaise(d) {
  new MutationObserver(() => { if (!d.hidden) raiseWindow(d); }).observe(d, { attributes: true, attributeFilter: ["hidden"] });
  d.addEventListener("pointerdown", () => raiseWindow(d), true);
}
function wireSheetWindow() {
  document.querySelectorAll(".dialog").forEach(wireRaise);        // Advanced search, About, the report (the sheets add theirs as they open)
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
  } else {
    // ALPHA: unfinished software (Daniel, 2026-11-14: "the program should probably be considered as Alpha status")
    $("mode").textContent = "ALPHA";
    if ($("banner").hidden) {
      $("banner").hidden = false;
      $("banner").innerHTML = `<b>Alpha version.</b> Combat Lab is unfinished: expect bugs and results that are still being checked against the rules. Please report problems and ideas with the <b>Suggestion / bug report</b> button at the bottom right.`;
    }
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
  drawZones();
  drawBoards();
  wireBrowserWindow();
  wireColumnGrips();
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
    lab.layout = {}; saveLayout(); lockBrowserList(null); deskColumns();
    const b = $("browser"); sizeWatch.unobserve(b); b.classList.remove("float"); b.style.cssText = ""; $("browser-slot").appendChild(b);
    drawTeams();
  });
  $("about-btn").addEventListener("click", () => { $("about").hidden = false; });
  $("about-close").addEventListener("click", () => { $("about").hidden = true; });
  $("report-btn").addEventListener("click", openReport);
  $("report-close").addEventListener("click", () => { $("report").hidden = true; });
  // Cancel run (Daniel, 2026-11-17): beside the progress bar and beside the battle counter in the status bar
  const cancelRun = async () => { if (!lab.run) return; setStatus("Cancelling..."); await api("cancel", { run: lab.run }); };
  $("cancel-btn").addEventListener("click", cancelRun);
  $("cancel-btn-2").addEventListener("click", cancelRun);
  // Full power: every core; the threads box does not apply while it is on
  const fullPower = () => { $("threads").disabled = $("full-power").checked; $("full-power-warn").classList.toggle("on", $("full-power").checked); };
  $("full-power").addEventListener("change", () => { fullPower(); save(); });
  fullPower();
  $("board-search").addEventListener("input", drawBoards);
  $("board-size").addEventListener("change", drawBoards);
  $("board-random").addEventListener("click", randomMap);
  $("map-one").addEventListener("change", () => { lab.peek = null; lab.map.mode = "one"; save(); drawBoards(); });
  $("map-stitch").addEventListener("change", () => { lab.peek = null; lab.map.mode = "stitch"; save(); drawBoards(); });
  $("map-playlist").addEventListener("change", () => { lab.peek = null; lab.map.mode = "playlist"; save(); drawBoards(); });
  $("playlist-order").addEventListener("change", (e) => { lab.map.order = e.target.value; save(); drawBoards(); });
  $("playlist-clear").addEventListener("click", () => { lab.map.playlist = []; save(); drawBoards(); });
  $("zone-mode").addEventListener("change", (e) => { lab.deploy.mode = e.target.value; drawZones(); });
  $("zone-opposite").addEventListener("change", (e) => { lab.deploy.opposite = e.target.checked; zonesChanged(); });
  $("stitch-cols").addEventListener("change", resizeStitch);
  $("stitch-rows").addEventListener("change", resizeStitch);
  $("f-add-unit").addEventListener("click", () => addUnitCondition());
  $("save-run").addEventListener("click", async () => {
    const file = await api("save_run", { run: lab.run });
    if (file.error) { setStatus(file.error); return; }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(file)], { type: "application/json" }));
    a.download = `combatlab-run-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}.json.txt`;   // .txt: GitHub issues accept it, and not .json
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    setStatus(`Saved ${file.lines.length} battles, ${file.crashed.length} crashes`);
  });
  $("open-run").addEventListener("click", () => $("open-run-input").click());
  $("open-run-input").addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    let file; try { file = JSON.parse(await f.text()); } catch (x) { setStatus("That is not a run file"); return; }
    const r = await api("load_run", { file });
    if (r.error) { setStatus(r.error); return; }
    lab.run = r.run; lab.runSetup = r.setup; lab.filter = {};
    $("results-empty").hidden = true; $("results").hidden = false;
    if (confirm("Also put this run's setup (teams, map, zones, options) into the Units, Map and Options pages?")) applySetup(r.setup);
    show("results"); drawResults(); setStatus(`Opened ${f.name}`);
    e.target.value = "";
  });
  $("unit-stats-box").addEventListener("toggle", () => { if ($("unit-stats-box").open) loadUnitStats(); });
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
