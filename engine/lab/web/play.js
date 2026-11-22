"use strict";
// BATTLEROM play page. Talks to the Combat Lab server: play_poll / play_answer / play_query (engine/core/src/play_session.rs).
// One question at a time: the engine waits. This page shows what it asks (move order, stand up, MASC, move, spot, TAG, target,
// weapons, physical attack, End Phase switches) and sends the answer; while a question waits it can also ask the engine for
// a route, re-price a weapon after a mode / ammunition change, and set equipment switches.
const $ = (id) => document.getElementById(id);
const qs = new URLSearchParams(location.search);
let GAME = +qs.get("game");
let COLOURS = {};
try { COLOURS = JSON.parse(qs.get("colours") || "{}"); } catch (e) { /* default colours */ }
const R = 34, SQ3 = Math.sqrt(3);
const NS = "http://www.w3.org/2000/svg";
const DIR = { N: [0, -1], NE: [SQ3 / 2, -0.5], SE: [SQ3 / 2, 0.5], S: [0, 1], SW: [-SQ3 / 2, 0.5], NW: [-SQ3 / 2, -0.5] };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const LOCAB = { "Head": "H", "Center Torso": "CT", "Left Torso": "LT", "Right Torso": "RT", "Left Arm": "LA", "Right Arm": "RA", "Left Leg": "LL", "Right Leg": "RL" };

// ---------------------------------------------------------------- looks (remembered on this device)
const LOOKS = { slhisd: "SL-HIS Dark", slhis: "SL-HIS Light", w95: "Windows 95", modern: "Modern" };
const pref = (k, d) => { try { const v = localStorage.getItem("bm_" + k); return v == null ? d : v; } catch (e) { return d; } };
const setPref = (k, v) => { try { localStorage.setItem("bm_" + k, v); } catch (e) { /* storage off */ } };
const O = { look: pref("look", "slhisd"), cvd: pref("cvd", "0") === "1", rings: pref("rings", "1") === "1", labels: pref("labels", "1") === "1" };
// movement colours follow MegaMek's (walk cyan, run yellow, jump orange; NOT VERIFIED against its source); the colour-blind set
// (Okabe-Ito) also gives each mode its own line pattern
const modeCol = (m) => (O.cvd ? { Walk: "#56B4E9", Run: "#F0E442", Jump: "#CC79A7" } : { Walk: "#00e5ff", Run: "#ffd400", Jump: "#ff7a3c" })[m] || "#99a";
const modeDash = (m) => (O.cvd ? { Walk: "", Run: "7 4", Jump: "2 4" }[m] || "" : "");
const BAND = () => (O.cvd ? { short: "#56B4E9", medium: "#F0E442", long: "#CC79A7" } : { short: "#6fbf86", medium: "#dba94a", long: "#e07468" });

const S = { seq: 0, req: null, board: null, units: [], max: {}, maxLoc: {}, critNames: {}, sel: null, dest: null, facing: null, mode: null, view: null, log: [], over: false,
  decl: null, path: null, attackSel: null, pending: false, myTeam: null };
const svg = $("map");
const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };

async function api(name, body) {
  if (window.LAB_WASM) return window.LAB_WASM.api(name, { game: GAME, ...body });   // the browser build (engine/wasm): this page plays the battle
  const r = await fetch("api/" + name, { method: "POST", body: JSON.stringify({ game: GAME, ...body }) });
  return r.json();
}
const query = (q) => api("play_query", { query: q });

// ---------------------------------------------------------------- geometry (flat-topped hexes, even columns half a hex lower, N up)
const parse = (l) => [parseInt(l.slice(0, 2), 10), parseInt(l.slice(2), 10)];
const centre = (l) => { const [c, r] = parse(l); return [R + (c - 1) * 1.5 * R, (SQ3 / 2) * R + (r - 1) * SQ3 * R + (c % 2 === 0 ? (SQ3 / 2) * R : 0)]; };
const pts = (cx, cy, k = 1) => [0, 1, 2, 3, 4, 5].map((i) => `${(cx + R * k * Math.cos(Math.PI / 3 * i)).toFixed(1)},${(cy + R * k * Math.sin(Math.PI / 3 * i)).toFixed(1)}`).join(" ");
const hexName = (c, r) => String(c).padStart(2, "0") + String(r).padStart(2, "0");
function neighbours(l) { // in the order of polygon edges 0..5 (SE, S, SW, NW, N, NE)
  const [c, r] = parse(l), low = c % 2 === 0;
  return [hexName(c + 1, r + (low ? 1 : 0)), hexName(c, r + 1), hexName(c - 1, r + (low ? 1 : 0)), hexName(c - 1, r + (low ? 0 : -1)), hexName(c, r - 1), hexName(c + 1, r + (low ? 0 : -1))];
}
function dist(a, b) {
  const cube = (l) => { const [c, r] = parse(l), x = c - 1, z = (r - 1) - (x - (x & 1)) / 2; return [x, -x - z, z]; };
  const p = cube(a), q = cube(b);
  return Math.max(Math.abs(p[0] - q[0]), Math.abs(p[1] - q[1]), Math.abs(p[2] - q[2]));
}
const unit = (id) => S.units.find((u) => u.id === id);

// ---------------------------------------------------------------- map
let gMap, gDyn;
function buildMap() {
  svg.innerHTML = "";
  const W = S.board.width, H = S.board.height;
  S.bounds = [0, 0, R * 2 + (W - 1) * 1.5 * R, SQ3 * R * H + (SQ3 / 2) * R];
  gMap = el("g", {}, svg); gDyn = el("g", {}, svg);
  for (const label of Object.keys(S.board.hexes).sort()) {
    const h = S.board.hexes[label], f = h.f || {}, [x, y] = centre(label);
    let fill = "#39402f";
    const trees = f.woods || f.jungle;
    if (f.road || f.pavement) fill = "#3a3b35";
    if (f.rough || f.rubble) fill = "#4b4535";
    if (trees) fill = String(trees) === "1" ? "#2f4a2b" : "#26402a";
    if (f.water && String(f.water) !== "0") fill = "#2a4a66";
    if (h.b) fill = "#55504a";
    const g = el("g", { "data-hex": label }, gMap);
    el("polygon", { points: pts(x, y), fill, stroke: "#1b2117", "stroke-width": h.l ? 1.8 : 0.8 }, g);
    if (O.labels) { const t = el("text", { x, y: y - R * 0.55, "text-anchor": "middle", "font-size": 8, fill: "#cfd8c4", "fill-opacity": ".55", "font-family": "ui-monospace,monospace" }, g); t.textContent = label; }
    if (h.l) { const lv = el("text", { x, y: y + R * 0.72, "text-anchor": "middle", "font-size": 9, fill: "#e0e6d8", "font-weight": 600 }, g); lv.textContent = "L" + h.l; }
    if (trees) { const w = el("text", { x, y: y + 3, "text-anchor": "middle", "font-size": 14, fill: "#7fb27f", "fill-opacity": ".7" }, g); w.textContent = "♣"; }
  }
  fit();
}
function applyView() { const v = S.view; svg.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`); }
function fit() {
  if (!S.bounds) return;
  const b = S.bounds, r = svg.getBoundingClientRect(), ar = (r.width || 1) / (r.height || 1);
  let w = b[2] + 8, h = b[3] + 8;
  if (w / h < ar) w = h * ar; else h = w / ar;
  S.view = { x: b[0] - 4 - (w - b[2] - 8) / 2, y: b[1] - 4 - (h - b[3] - 8) / 2, w, h };
  applyView();
}
function zoom(f, cx, cy) {
  const v = S.view, r = svg.getBoundingClientRect();
  const px = cx == null ? 0.5 : (cx - r.left) / r.width, py = cy == null ? 0.5 : (cy - r.top) / r.height;
  const nw = Math.max(120, Math.min(S.bounds[2] * 3, v.w * f)), nh = nw * v.h / v.w;
  S.view = { x: v.x + (v.w - nw) * px, y: v.y + (v.h - nh) * py, w: nw, h: nh };
  applyView();
}
// drag to pan, wheel / pinch to zoom, press and hold for a card
(() => {
  const ptrs = new Map(); let moved = false, lastDist = 0, timer = null;
  const cancel = () => { if (timer) { clearTimeout(timer); timer = null; } };
  svg.addEventListener("pointerdown", (e) => {
    ptrs.set(e.pointerId, [e.clientX, e.clientY]); moved = false; lastDist = 0; cancel();
    if (ptrs.size === 1) {
      const t = e.target.closest("[data-unit],[data-hex],[data-reach]");
      const hex = t && (t.dataset.hex || t.dataset.reach || (unit(+t.dataset.unit) || {}).hex);
      const which = hex || (t && (unit(+t.dataset.unit) || {}).hex);
      if (which) timer = setTimeout(() => { if (!moved) { moved = true; showHexCard(which); } }, 650);
    }
  });
  svg.addEventListener("pointermove", (e) => {
    if (!ptrs.has(e.pointerId)) return;
    const prev = ptrs.get(e.pointerId); ptrs.set(e.pointerId, [e.clientX, e.clientY]);
    const r = svg.getBoundingClientRect();
    if (ptrs.size === 1) {
      const dx = e.clientX - prev[0], dy = e.clientY - prev[1];
      if (Math.abs(dx) + Math.abs(dy) > 2) { moved = true; cancel(); }
      S.view.x -= dx * S.view.w / r.width; S.view.y -= dy * S.view.h / r.height; applyView();
    } else if (ptrs.size === 2) {
      cancel();
      const [a, b] = [...ptrs.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
      if (lastDist) zoom(lastDist / d, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
      lastDist = d; moved = true;
    }
  });
  const up = (e) => { ptrs.delete(e.pointerId); lastDist = 0; cancel(); };
  svg.addEventListener("pointerup", up); svg.addEventListener("pointercancel", up);
  svg.addEventListener("click", (e) => { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);
  svg.addEventListener("wheel", (e) => { e.preventDefault(); zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY); }, { passive: false });
})();
$("zin").onclick = () => zoom(1 / 1.3); $("zout").onclick = () => zoom(1.3); $("zfit").onclick = fit;

// ---------------------------------------------------------------- cards (press and hold)
function showCard(html) { const c = $("card"); c.innerHTML = html + '<div class="row"><button class="sm" data-act="card-close">Close</button></div>'; c.style.display = "block"; }
function showHexCard(label) {
  const h = S.board && S.board.hexes[label]; if (!h) return;
  const f = h.f || {}, feats = Object.entries(f).map(([k, v]) => `${k}${v && v !== true && v !== 0 ? " " + v : ""}`).join(", ") || "clear";
  const here = S.units.filter((u) => u.hex === label && !u.destroyed).map((u) => esc(u.name + " " + (u.mech || "")));
  const ref = unit(S.sel); const d = ref && ref.hex ? dist(ref.hex, label) : null;
  showCard(`<b>Hex ${label}</b> &middot; level ${h.l || 0}${h.b ? " &middot; building" : ""}<div class="msg">Terrain: ${esc(feats)}</div>${here.length ? `<div>${here.join("<br>")}</div>` : ""}${d != null ? `<div class="msg">${d} hex${d === 1 ? "" : "es"} from ${esc(ref.name)}</div>` : ""}`);
}
function showWeaponCard(w) {
  const r = w.ranges ? `min ${w.ranges.min ?? "-"} / short ${w.ranges.short} / medium ${w.ranges.medium} / long ${w.ranges.long}` : "range unknown";
  const bins = (w.bins || []).map((b) => `${esc(b.name)} (${esc(LOCAB[b.loc] || b.loc || "")}) ${b.shots ?? "?"} shots`).join("<br>");
  showCard(`<b>${esc(w.name)}</b> ${w.loc ? "&middot; " + esc([].concat(w.loc).join("/")) : ""}<div class="msg">${r}</div><div class="msg">Heat ${w.heat ?? "?"}${w.mode ? " &middot; mode " + esc(w.mode) : ""}${w.in_range ? "" : " &middot; out of range"}</div>${bins ? `<div class="msg">${bins}</div>` : ""}`);
}

// ---------------------------------------------------------------- units on the map
const teamColour = (u) => (O.cvd ? (u.team === S.myTeam ? "#56B4E9" : "#D55E00") : COLOURS[u.team] || (u.team === S.myTeam ? "#4b8fd8" : "#d86a4b"));
const short = (u) => String(u.mech || u.name || "").split(/\s+/)[0].slice(0, 7);
function fracOf(u) {
  const m = S.max[u.id] || (S.max[u.id] = { hp: Math.max(1, u.hp) });
  return Math.max(0, Math.min(1, u.hp / m.hp));
}
function drawUnits(layer) {
  for (const u of S.units) {
    if (!u.hex || u.destroyed) continue;
    const [x, y] = centre(u.hex), col = teamColour(u), mine = u.team === S.myTeam;
    const g = el("g", { "data-unit": u.id, style: "cursor:pointer" }, layer);
    el("polygon", { points: pts(x, y, 0.8), fill: col, "fill-opacity": ".55", stroke: S.sel === u.id ? "#fff" : col, "stroke-width": S.sel === u.id ? 2.5 : 1.5, "stroke-dasharray": mine ? "" : "5 3" }, g);
    const d = DIR[u.facing] || DIR.N;
    el("polygon", { points: `${x + d[0] * R * 0.78},${y + d[1] * R * 0.78} ${x + d[0] * R * 0.5 - d[1] * 5},${y + d[1] * R * 0.5 + d[0] * 5} ${x + d[0] * R * 0.5 + d[1] * 5},${y + d[1] * R * 0.5 - d[0] * 5}`, fill: "#fff" }, g);
    // placard: name, armour + structure bar, heat bar
    const f = fracOf(u), px = x - 24, py = y + R * 0.46;
    el("rect", { x: px, y: py, width: 48, height: 17, rx: 2, fill: "#0c0f13", "fill-opacity": ".78", stroke: col, "stroke-width": 0.8 }, g);
    const t = el("text", { x: x, y: py + 7, "text-anchor": "middle", "font-size": 7.5, "font-weight": 700, fill: "#fff" }, g); t.textContent = short(u);
    el("rect", { x: px + 3, y: py + 9, width: 42, height: 3, fill: "#2b333d" }, g);
    el("rect", { x: px + 3, y: py + 9, width: 42 * f, height: 3, fill: f > 0.5 ? "#6fbf86" : f > 0.25 ? "#dba94a" : "#e07468" }, g);
    el("rect", { x: px + 3, y: py + 13, width: 42, height: 2, fill: "#2b333d" }, g);
    el("rect", { x: px + 3, y: py + 13, width: 42 * Math.min(1, u.heat / 30), height: 2, fill: "#ff7a3c" }, g);
    if (u.prone) { const p = el("text", { x: x + 18, y: y - 14, "font-size": 8, fill: "#ffd400", "font-weight": 700 }, g); p.textContent = "PRONE"; }
    if (u.shutdown) { const p = el("text", { x: x + 18, y: y - 4, "font-size": 8, fill: "#e07468", "font-weight": 700 }, g); p.textContent = "OFF"; }
  }
}
function renderStrip() {
  $("strip").innerHTML = S.units.map((u) => `<div class="chip${u.destroyed ? " dead" : ""}${S.sel === u.id ? " sel" : ""}" data-u="${u.id}"><i style="background:${teamColour(u)}"></i>${esc(u.name)} <span class="msg">${esc(u.mech || "")}</span><span class="bar" title="armour and structure left"><b style="width:${Math.round(fracOf(u) * 100)}%"></b></span>${u.heat ? `<span class="warnt">${u.heat}H</span>` : ""}${u.shutdown ? '<span class="err">OFF</span>' : ""}${u.prone ? "<span>PRONE</span>" : ""}</div>`).join("");
}
function infoBar() {
  const u = unit(S.sel);
  if (!u) { $("info").textContent = "Tap a unit for its details."; return; }
  const locs = Object.entries(u.locs || {}).map(([k, v]) => `${LOCAB[k] || k} ${v[3] ? "gone" : v[0] + (v[1] ? "(" + v[1] + ")" : "") + "/" + v[2]}`).join(" · ");
  $("info").innerHTML = `<b>${esc(u.name)}</b> ${esc(u.mech || "")} ${u.tons || ""}t &middot; walk ${u.walk} run ${u.run}${u.jump ? " jump " + u.jump : ""} &middot; heat ${u.heat} &middot; facing ${u.facing} &middot; pilot hits ${u.pilot_hits}<br><span style="font-size:11px" title="armour (rear) / structure">${esc(locs)}</span>`;
}

// ---------------------------------------------------------------- drawing for the question
function redraw() {
  if (!gDyn) return;
  gDyn.innerHTML = "";
  const r = S.req;
  if (r && r.kind === "declaration") drawRings(gDyn);
  if (r && r.kind === "movement") drawReach(gDyn);
  if (r && r.kind === "target") drawTargets(gDyn);
  if (r && (r.kind === "spot" || r.kind === "tag")) drawPickTargets(gDyn);
  drawUnits(gDyn);
  if (r && r.kind === "movement") { drawDest(gDyn); drawPath(gDyn); drawAttackStops(gDyn); }
  if (r && r.kind === "declaration") drawAim(gDyn);
  renderStrip(); infoBar();
}
function setPhase(t) { $("phase").textContent = t; }
function sheet(html) { $("sheet").innerHTML = html; }
async function send(answer) {
  const seq = S.seq; S.req = null; S.decl = null; sheet('<div class="msg">Working...</div>'); redraw();
  const r = await api("play_answer", { seq, answer });
  if (r.error) sheet(`<div class="err">${esc(r.error)}</div>`);
  loop();
}
async function loop() {
  while (!S.over) {
    let p; try { p = await api("play_poll", { wait_ms: 20000 }); } catch (e) { setPhase("connection lost"); await new Promise((r) => setTimeout(r, 1500)); continue; }
    if (p.error) { setPhase("error"); sheet(`<div class="err">${esc(p.error)}</div>`); return; }
    if (p.state === "waiting") continue;
    if (p.state === "failed") { setPhase("the engine stopped"); sheet(`<div class="err">The engine stopped: ${esc(p.error)}</div>`); S.over = true; return; }
    if (p.state === "done") { finish(p.end); return; }
    if (p.seq === S.seq && S.req) { await new Promise((r) => setTimeout(r, 300)); continue; }
    S.seq = p.seq; take(p.request); return;
  }
}
const HANDLERS = {};
function take(r) {
  S.req = r; S.units = r.units;
  for (const u of S.units) { // first sight of a unit: its full armour, structure and slot names (for the bars and the criticals tab)
    if (!S.maxLoc[u.id]) S.maxLoc[u.id] = JSON.parse(JSON.stringify(u.locs || {}));
    if (u.crit_names) S.critNames[u.id] = u.crit_names;
  }
  if (r.board && !S.board) { S.board = r.board; buildMap(); }
  if (r.log && r.log.length) { S.log.push(...r.log); $("report").textContent = S.log.join("\n"); }
  const mine = unit(r.unit ?? (r.candidates || [])[0]);
  if (mine && !S.myTeam && r.kind !== "spot") S.myTeam = mine.team;
  if (r.unit != null) S.sel = r.unit;
  S.dest = null; S.facing = null; S.mode = null; S.decl = null; S.path = null; S.attackSel = null; S.reachIdx = null;
  const turn = (S.log.map((l) => /=== TURN (\d+)/.exec(l)).filter(Boolean).pop() || [])[1];
  const PH = { move_order: "Movement", movement: "Movement", stand_up: "Movement", boost: "Movement", spot: "Ranged attacks", tag: "TAG", target: "Ranged attacks", declaration: "Ranged attacks", physical: "Physical attacks", end_phase: "Heat" };
  setPhase(`Turn ${turn || "?"} · ${PH[r.kind] || r.kind}`);
  HANDLERS[r.kind](r);
  redraw();
}
const errLine = (r) => (r.error ? `<div class="err">${esc(r.error)}</div>` : "");
const eq = (u) => (u && u.equipment) || {};

// ---------------------------------------------------------------- the questions
HANDLERS.move_order = (r) => {
  sheet(`<h3>Choose a unit to move</h3><div class="msg">Tap one of your units that has not moved yet.</div><div class="row">${r.candidates.map((id) => `<button data-act="pick-unit" data-id="${id}">${esc(unit(id).name)} ${esc(unit(id).mech || "")}</button>`).join("")}</div>`);
  S.sel = r.candidates[0];
};
HANDLERS.stand_up = (r) => {
  sheet(`<h3>${esc(r.name)} is prone</h3>${errLine(r)}<div class="msg">Standing up costs 2 movement points and needs a piloting roll of <b>${r.tn}</b> or more (2D6); a failed roll is a fall${r.pilot_hits ? `; pilot hits ${r.pilot_hits} are already counted` : ""}. You then move on with the points left (${r.run} running MP to start). Stay prone to keep firing from the ground.</div><div class="row"><button class="go" data-act="stand" data-v="1">Stand up</button><button data-act="stand" data-v="0">Stay prone</button></div>`);
};
HANDLERS.boost = (r) => {
  const u = unit(r.unit), e = eq(u), b = (e.boost || {});
  sheet(`<h3>${esc(r.name)}: ${e.masc && e.supercharger ? "MASC and supercharger" : e.masc ? "MASC" : "supercharger"}</h3>${errLine(r)}<div class="msg">Using it this turn raises the running speed; each use needs a roll of <b>${b.tn}</b> or more, and a failure costs criticals and may force a fall. The roll gets harder each turn in a row. Your choice stays until you change it.</div><div class="row"><button class="${b.on ? "go" : ""}" data-act="boost" data-v="1">Use it</button><button class="${b.on ? "" : "go"}" data-act="boost" data-v="0">Not this turn</button></div>`);
};
HANDLERS.spot = (r) => {
  sheet(`<h3>${esc(r.name)}: spot for indirect fire?</h3>${errLine(r)}<div class="msg">A spotter that sees an enemy lets friends without a line of sight fire at it indirectly. A spotter may still fire its own weapons, at +1 to hit.</div><div class="row">${r.candidates.map((c) => `<button data-act="spot" data-id="${c.id}">${esc(c.name)} &middot; range ${c.distance} &middot; ${c.friends} friend${c.friends === 1 ? "" : "s"} could use it</button>`).join("")}<button class="go" data-act="spot" data-id="">No spotting</button></div>`);
};
HANDLERS.tag = (r) => {
  sheet(`<h3>${esc(r.name)}: TAG designation</h3>${errLine(r)}<div class="msg">TAG is its own short attack before the weapon attacks. Designating the 'Mech helps homing artillery; designating the hex works for the ground under it. Pick a target and what to light up, or skip.</div><table>${r.candidates.map((c) => `<tr><td>${esc(c.name)}</td><td>range ${c.distance}</td><td>${c.tn_mech != null ? `<button class="sm" data-act="tag" data-id="${c.id}" data-aim="mech">'Mech TN ${c.tn_mech}</button>` : ""}</td><td>${c.tn_hex != null ? `<button class="sm" data-act="tag" data-id="${c.id}" data-aim="hex">Hex TN ${c.tn_hex}</button>` : ""}</td></tr>`).join("")}</table><div class="row"><button class="go" data-act="tag" data-id="">Skip TAG</button></div>`);
};
function drawPickTargets(layer) {
  for (const c of (S.req.candidates || [])) { const u = unit(c.id); if (!u || !u.hex) continue; const [x, y] = centre(u.hex); el("polygon", { points: pts(x, y, 0.95), fill: "#dba94a", "fill-opacity": ".2", stroke: "#dba94a", "stroke-width": 2.5, "pointer-events": "none" }, layer); }
}

// ---- movement
function reachIndex(r) { const byHex = {}; for (const o of r.options) (byHex[o.hex] = byHex[o.hex] || []).push(o); return byHex; }
function drawReach(layer) {
  const idx = S.reachIdx || (S.reachIdx = reachIndex(S.req));
  const sets = { Walk: new Set(), Run: new Set(), Jump: new Set() };
  for (const [h, os] of Object.entries(idx)) for (const o of os) if (sets[o.mode]) sets[o.mode].add(h);
  for (const mode of ["Jump", "Run", "Walk"]) {
    const col = modeCol(mode);
    for (const h of sets[mode]) { const [x, y] = centre(h); el("polygon", { points: pts(x, y, 0.96), fill: col, "fill-opacity": mode === "Walk" ? ".22" : ".14", "pointer-events": "none" }, layer); }
    for (const h of sets[mode]) { // only the outer border of each mode's reach (MegaMek's look)
      const [x, y] = centre(h);
      neighbours(h).forEach((n, i) => {
        if (sets[mode].has(n)) return;
        const a = Math.PI / 3 * i, b2 = Math.PI / 3 * (i + 1);
        el("line", { x1: x + R * Math.cos(a), y1: y + R * Math.sin(a), x2: x + R * Math.cos(b2), y2: y + R * Math.sin(b2), stroke: col, "stroke-width": 2.4, "stroke-dasharray": modeDash(mode), "pointer-events": "none" }, layer);
      });
    }
  }
  for (const h of Object.keys(idx)) { const [x, y] = centre(h); const p = el("polygon", { points: pts(x, y), fill: "transparent", "data-reach": h, style: "cursor:pointer" }, layer); p.addEventListener("click", () => pickDest(h)); }
}
HANDLERS.movement = (r) => {
  S.sel = r.unit;
  sheet(`<h3>Move ${esc(r.name)}</h3>${errLine(r)}<div class="msg">${r.standup_mp != null ? "It has stood up and moves on with the points left. " : ""}${r.entry ? "Choose where to enter the map. " : ""}Tap a tinted hex. ${r.attacks.length ? "Tap an enemy for a charge or death from above. " : ""}Cyan = walk (${r.walk} MP), yellow = run (${r.run} MP)${r.jump ? ", orange = jump (" + r.jump + " MP)" : ""}.</div><div class="row"><button data-act="stay">Stay here</button></div>`);
};
async function pickDest(h) {
  const os = S.reachIdx[h]; if (!os) return;
  const cheapest = os.reduce((a, b) => (a.mp <= b.mp ? a : b));
  S.dest = h; S.mode = cheapest.mode; S.attackSel = null;
  const same = os.filter((o) => o.mode === S.mode), cur = unit(S.req.unit);
  S.facing = (same.find((o) => cur && o.facing === cur.facing) || same[0]).facing;
  moveSheet(); redraw(); loadPath();
}
const optNow = () => ((S.reachIdx || {})[S.dest] || []).find((o) => o.mode === S.mode && o.facing === S.facing);
async function loadPath() {
  const seq = S.seq; let q;
  if (S.attackSel) q = { q: "path", attack: S.attackSel };
  else if (S.dest) q = { q: "path", hex: S.dest, facing: S.facing, mode: S.mode };
  else { S.path = null; return; }
  const r = await query(q);
  if (seq !== S.seq || !S.req) return;
  S.path = r.path || null; redraw();
}
function drawPath(layer) {
  if (!S.path || !S.path.length) return;
  const u = unit(S.req.unit), black = !!S.attackSel && !S.attackConfirm, col = black ? "#000" : modeCol(S.attackSel ? S.attackSel.mode : S.mode);
  const pt = [u && u.hex ? centre(u.hex) : null, ...S.path.map((s) => centre(s.hex))].filter(Boolean);
  el("polyline", { points: pt.map((p) => p.join(",")).join(" "), fill: "none", stroke: black ? "#fff" : "#000", "stroke-width": 7, "stroke-opacity": ".55", "pointer-events": "none" }, layer);
  el("polyline", { points: pt.map((p) => p.join(",")).join(" "), fill: "none", stroke: col, "stroke-width": 3.5, "stroke-dasharray": modeDash(S.mode), "pointer-events": "none" }, layer);
  S.path.forEach((s, i) => { if (s.k === "turn") return; const [x, y] = centre(s.hex); const t = el("text", { x, y: y - 10, "text-anchor": "middle", "font-size": 9, "font-weight": 700, fill: "#fff", stroke: "#000", "stroke-width": 2.5, "paint-order": "stroke", "pointer-events": "none" }, layer); t.textContent = s.mp; });
}
function drawDest(layer) {
  if (!S.dest) return;
  const os = S.reachIdx[S.dest].filter((o) => o.mode === S.mode), [x, y] = centre(S.dest);
  el("polygon", { points: pts(x, y, 0.98), fill: "none", stroke: modeCol(S.mode), "stroke-width": 3, "pointer-events": "none" }, layer);
  for (const o of os) {
    const d = DIR[o.facing], sel = o.facing === S.facing, ax = x + d[0] * R * 1.12, ay = y + d[1] * R * 1.12;
    const g = el("g", { style: "cursor:pointer" }, layer);
    el("circle", { cx: ax, cy: ay, r: 11, fill: sel ? modeCol(S.mode) : "#252c35", stroke: modeCol(S.mode), "stroke-width": 1.5, "fill-opacity": sel ? 1 : .85 }, g);
    el("polygon", { points: `${ax + d[0] * 7},${ay + d[1] * 7} ${ax - d[0] * 4 - d[1] * 5},${ay - d[1] * 4 + d[0] * 5} ${ax - d[0] * 4 + d[1] * 5},${ay - d[1] * 4 - d[0] * 5}`, fill: sel ? "#101418" : modeCol(S.mode) }, g);
    g.addEventListener("click", (e) => { e.stopPropagation(); S.facing = o.facing; moveSheet(); redraw(); loadPath(); });
  }
}
function drawAttackStops(layer) {
  if (!S.attackSel && !S.attackTarget) return;
  for (const a of S.req.attacks.filter((x) => x.target === S.attackTarget)) {
    const [x, y] = centre(a.hex), sel = S.attackSel && S.attackSel.hex === a.hex && S.attackSel.facing === a.facing && S.attackSel.kind === a.kind;
    const p = el("polygon", { points: pts(x, y, 0.92), fill: "#000", "fill-opacity": sel ? ".5" : ".3", stroke: "#fff", "stroke-width": sel ? 3 : 1.5, style: "cursor:pointer" }, layer);
    const t = el("text", { x, y: y + 4, "text-anchor": "middle", "font-size": 10, "font-weight": 700, fill: "#fff", "pointer-events": "none" }, layer); t.textContent = a.kind === "charge" ? "CHG" : "DFA";
    p.addEventListener("click", (e) => { e.stopPropagation(); chooseAttack(a); });
  }
}
function moveSheet() {
  const os = S.reachIdx[S.dest], modes = [...new Set(os.map((o) => o.mode))], o = optNow() || os[0], warns = [];
  if (o.psrs) warns.push(`${o.psrs} piloting roll${o.psrs > 1 ? "s" : ""} on this path`);
  if (o.hazard) warns.push(`about ${(+o.hazard).toFixed(1)} damage from terrain`);
  sheet(`<h3>${esc(S.req.name)} to ${S.dest}</h3>${errLine(S.req)}
    <div class="row">${modes.map((m) => `<button data-act="mode" data-m="${m}" class="${m === S.mode ? "on" : ""}" style="border-color:${modeCol(m)}">${m}</button>`).join("")}</div>
    <div class="msg">${o.mp} MP (turns included) &middot; ${o.hexes} hex${o.hexes === 1 ? "" : "es"} &middot; target movement modifier +${o.tmm} &middot; movement heat ${o.heat}</div>
    ${warns.length ? `<div class="warnt">&#9888; ${warns.join("; ")}. Moving on accepts the warning.</div>` : ""}
    <div class="msg">The line on the map is the route the engine takes (the cheapest, avoiding hazards). Tap an arrow around the hex for the facing. Esc or Undo clears the choice.</div>
    <div class="row"><button class="go" data-act="commit">Move</button><button data-act="undo">Undo</button><button data-act="stay">Stay here</button></div>`);
}
function undo() { if (S.req && S.req.kind === "movement") { S.dest = null; S.path = null; S.attackSel = null; S.attackTarget = null; S.attackConfirm = false; HANDLERS.movement(S.req); redraw(); } }
// charge / death from above: tap an enemy; the stops go black; pick one; a popup explains and asks
function onUnitTap(id) {
  S.sel = id;
  const r = S.req;
  if (r && r.kind === "move_order" && r.candidates.includes(id)) { send({ unit: id }); return; }
  if (r && r.kind === "movement") {
    const list = r.attacks.filter((a) => a.target === id);
    if (list.length) { S.attackTarget = id; S.dest = null; S.path = null; S.attackSel = null; S.attackConfirm = false; attackSheet(list); redraw(); return; }
  }
  if (r && (r.kind === "spot" || r.kind === "tag")) { const c = r.candidates.find((x) => x.id === id); if (c && r.kind === "spot") { send({ target: id, fires: true }); return; } }
  redraw();
}
function attackSheet(list) {
  const t = list[0];
  sheet(`<h3>${esc(t.target_name)}: charge or death from above</h3><div class="msg">The black hexes are where you can stop to attack. The path turns to colour when you pick one.</div><div class="row">${list.map((a, i) => `<button data-act="atk" data-i="${i}">${a.kind === "charge" ? "Charge" : "Death from above"} from ${a.hex} (${a.mp} MP)</button>`).join("")}<button data-act="undo">Back</button></div>`);
}
async function chooseAttack(a) {
  S.attackSel = a; S.attackConfirm = true;
  sheet(`<h3>${a.kind === "charge" ? "Charge" : "Death from above"} on ${esc(a.target_name)}</h3><div class="msg">You end the move at <b>${a.hex}</b> facing ${a.facing}, using ${a.mp} MP (${a.mode}). The attack is made in the Physical Attack Phase: to hit <b>${a.tn}</b> or more, about ${a.hit != null ? Math.round(a.hit * 100) + "%" : "?"}; ${a.damage} damage to the target; <b>you take ${a.self_damage}</b>${a.kind === "dfa" ? " (and a fall if you miss)" : ""}. A charge or death from above cannot be undone once the turn is set.</div><div class="row"><button class="go" data-act="atk-yes">Yes, make the move</button><button data-act="atk-no">No, back up</button></div>`);
  redraw(); loadPath();
}

// ---- target, weapons
function drawTargets(layer) {
  const me = unit(S.req.unit);
  for (const t of S.req.enemies) {
    const u = unit(t.id); if (!u || !u.hex) continue;
    const [x, y] = centre(u.hex);
    const p = el("polygon", { points: pts(x, y, 0.95), fill: "#e07468", "fill-opacity": ".22", stroke: "#e07468", "stroke-width": 2.5, style: "cursor:pointer" }, layer);
    p.addEventListener("click", () => send({ target: t.id }));
    if (me && me.hex) { const [mx, my] = centre(me.hex); el("line", { x1: mx, y1: my, x2: x, y2: y, stroke: "#e07468", "stroke-width": 1.5, "stroke-dasharray": "5 4", "pointer-events": "none" }, layer); }
  }
}
HANDLERS.target = (r) => {
  S.sel = r.unit;
  sheet(`<h3>${esc(r.name)}: choose a target</h3>${errLine(r)}<div class="msg">Tap a red hex, or pick from the list. Press and hold a hex for its details.</div><div class="row">${r.enemies.map((t) => `<button data-act="target" data-id="${t.id}">${esc(t.name)} ${esc((unit(t.id) || {}).mech || "")} &middot; range ${t.distance ?? "?"}</button>`).join("")}<button data-act="target" data-id="">Hold fire</button></div>`);
};
// range bands and firing arc for the weapon in focus: shaded = outside its arc, dashed = in its arc only after a torso twist / arm flip
function drawRings(layer) {
  if (!O.rings || !S.decl) return;
  const me = unit(S.decl.req.unit), w = S.decl.rows.find((x) => x.id === S.decl.focus);
  if (!me || !me.hex || !w || !w.ranges) return;
  const rg = w.ranges, col = BAND(), L = { short: "S", medium: "M", long: "L" };
  const inNow = new Set(w.arc || []), inTwist = new Set(w.arc_twist || []);
  for (const label of Object.keys(S.board.hexes)) {
    const d = dist(me.hex, label); if (d === 0 || d > rg.long) continue;
    if (!inTwist.has(label)) { const [x, y] = centre(label); el("polygon", { points: pts(x, y, 0.98), fill: "#000", "fill-opacity": ".45", "pointer-events": "none" }, layer); continue; } // outside the weapon's arc
    if (!inNow.has(label)) { const [x, y] = centre(label); el("polygon", { points: pts(x, y, 0.9), fill: "none", stroke: "#fff", "stroke-width": 1.2, "stroke-dasharray": "3 3", "pointer-events": "none" }, layer); } // in arc only after a torso twist / arm flip
    const band = d <= rg.short ? "short" : d <= rg.medium ? "medium" : "long";
    const [x, y] = centre(label);
    const tooClose = rg.min && d < rg.min;
    el("polygon", { points: pts(x, y, 0.96), fill: tooClose ? "#888" : col[band], "fill-opacity": tooClose ? ".12" : band === "short" ? ".2" : band === "medium" ? ".14" : ".09", "pointer-events": "none" }, layer);
    if (O.cvd && (d === rg.short || d === rg.medium || d === rg.long)) { const t = el("text", { x, y: y + 3, "text-anchor": "middle", "font-size": 9, "font-weight": 700, fill: col[band], "pointer-events": "none" }, layer); t.textContent = L[band]; }
  }
}
function drawAim(layer) {
  if (!S.decl) return;
  for (const [wid, hex] of Object.entries(S.decl.aim)) { const [x, y] = centre(hex); el("circle", { cx: x, cy: y, r: R * 0.6, fill: "none", stroke: "#e07468", "stroke-width": 2.5, "stroke-dasharray": "4 3", "pointer-events": "none" }, layer); el("circle", { cx: x, cy: y, r: 3, fill: "#e07468", "pointer-events": "none" }, layer); }
  if (S.decl.aimFor) for (const label of Object.keys(S.board.hexes)) { const [x, y] = centre(label); const p = el("polygon", { points: pts(x, y), fill: "transparent", style: "cursor:crosshair" }, layer); p.addEventListener("click", () => setAim(label)); }
}
HANDLERS.declaration = (r) => {
  S.sel = r.unit;
  S.decl = { req: r, rows: r.weapons, sel: new Set(), aim: {}, charge: new Set(r.weapons.filter((w) => w.charge).map((w) => w.name)), focus: (r.weapons.find((w) => w.in_range) || r.weapons[0] || {}).id, aimFor: null, bin: null };
  declSheet();
};
const isDistant = (w) => (w.modes || []).some((m) => m.selected && /distant/i.test(m.label)) || /distant/i.test(w.mode || "");
function breakdownText(r) {
  const b = r.breakdown, parts = [["gunnery", b.gunnery], ["you moved", b.attacker_movement], ["target moved", b.target_movement], ["line of sight", b.line_of_sight], ["cover", b.cover], ["heat", b.heat], ["target prone", b.target_prone], ["stealth", b.stealth], ["other", b.other]].filter((p) => p[1]);
  return `base ${b.base}${b.secondary ? " (includes +1 for a secondary target)" : ""}: ` + parts.map((p) => `${p[0]} ${p[1] > 0 && p[0] !== "gunnery" ? "+" : ""}${p[1]}`).join(", ") + `. Each weapon adds its range band and its own modifiers.${b.note ? " " + esc(b.note) : ""}`;
}
function declSheet() {
  const D = S.decl, r = D.req, rows = D.rows;
  const sel = rows.filter((w) => D.sel.has(w.id)), wh = sel.reduce((a, w) => a + (w.heat || 0), 0), ev = sel.reduce((a, w) => a + (w.ev || 0), 0);
  const heat = Math.max(0, r.heat + r.move_heat + wh - r.dissipation), heatCls = heat >= 14 ? "err" : heat >= 8 ? "warnt" : "";
  const trs = rows.map((w) => {
    const ok = w.in_range && !w.jammed, on = D.sel.has(w.id);
    const modeBtn = w.charge || D.charge.has(w.name) ? "" : "";
    return `<tr class="${w.jammed ? "jam" : ok ? (on ? "pick" : "") : "out"}" data-w="${w.id}"><td><input type="checkbox" data-act="fire" data-id="${w.id}" ${on ? "checked" : ""} ${ok ? "" : "disabled"} aria-label="fire ${esc(w.name)}"></td><td class="w" data-act="focus" data-id="${w.id}">${esc(w.name)}${w.loc ? ' <span class="msg">' + esc([].concat(w.loc).join("/")) + "</span>" : ""}${w.rear ? ' <span class="msg">(rear)</span>' : ""}${w.needs_twist ? ' <span class="msg">(torso twist)</span>' : ""}${w.jammed ? ' <span class="err">JAMMED</span>' : ""}</td><td title="${w.adj != null ? "range and weapon modifiers: " + (w.adj >= 0 ? "+" : "") + w.adj : ""}">${ok ? "TN " + w.tn : w.jammed ? "" : "out"}</td><td>${ok ? (+w.ev).toFixed(1) : ""}</td><td>${w.heat ?? ""}</td><td>${(w.modes || []).length > 1 ? `<button class="sm" data-act="mode-w" data-id="${w.id}" title="ammunition / firing mode">${esc(shortMode(w.mode))}</button>` : ""}${(w.rates || []).length > 1 ? `<button class="sm" data-act="rate-w" data-id="${w.id}" title="rate of fire">x${w.shots}</button>` : ""}${w.chargeable ? `<button class="sm ${D.charge.has(w.name) ? "on" : ""}" data-act="charge-w" data-id="${w.id}" title="charge the capacitor instead of firing">&#9889; Charge</button>` : ""}${(w.bins || []).length ? `<button class="sm" data-act="bins-w" data-id="${w.id}" title="ammunition bin: which bin this weapon draws from">Ammo ${(w.bins.find((b) => b.selected) || {}).shots ?? "?"}</button>` : ""}</td></tr>${D.bin === w.id ? binRows(w) : ""}`;
  }).join("");
  const aimW = rows.find((w) => isDistant(w) && D.sel.has(w.id));
  sheet(`<h3>${esc(r.name)} fires on ${esc(r.target_name)} &middot; range ${r.distance}${r.indirect ? " &middot; indirect" : ""}</h3>${errLine(r)}
    <table><tr><th></th><th>Weapon</th><th>To hit</th><th>Dmg</th><th>Heat</th><th>Mode</th></tr>${trs}</table>
    <details><summary class="msg">To-hit parts</summary><div class="msg">${breakdownText(r)}</div></details>
    <div class="msg">Selected: ${D.sel.size} weapon${D.sel.size === 1 ? "" : "s"}, about ${ev.toFixed(1)} damage. Heat at end of turn about <span class="${heatCls}">${heat}</span> (now ${r.heat}, movement ${r.move_heat}, weapons ${wh}, sinks take off ${r.dissipation}).${heat >= 14 ? " Shutdown risk." : ""} Press and hold a weapon for its card.</div>
    ${aimW ? `<div class="msg warnt">${esc(aimW.name)} is a distant shot: it lands next turn. Aim: <b>${D.aim[aimW.id] || r.target_hex}</b> <button class="sm ${D.aimFor ? "on" : ""}" data-act="aim-w" data-id="${aimW.id}">${D.aimFor ? "tap a hex on the map" : "Change the aim hex"}</button></div>` : ""}
    <div class="row"><button class="go" data-act="fire-go">Fire!</button><button data-act="alpha">Alpha strike</button><button data-act="clear">Clear</button><button data-act="hold">Hold fire</button></div>`);
  $("sheet").querySelectorAll("tr[data-w]").forEach((tr) => holdFor(tr, () => { const w = rows.find((x) => x.id === +tr.dataset.w); if (w) showWeaponCard(w); }));
}
const shortMode = (m) => String(m || "mode").replace(/rounds?/i, "").trim().slice(0, 12) || "mode";
function binRows(w) { return `<tr><td></td><td colspan="5"><div class="msg">Draw ${esc(w.name)} from:</div>${w.bins.map((b) => `<button class="sm ${b.selected ? "on" : ""}" data-act="bin-pick" data-w="${w.id}" data-b="${b.id}">${esc(LOCAB[b.loc] || b.loc || "?")} ${esc(b.name)} &middot; ${b.shots ?? "?"} shots</button>`).join(" ")} <button class="sm" data-act="bin-pick" data-w="${w.id}" data-b="">Automatic</button></div></td></tr>`; }
function holdFor(node, fn) { let t = null; const stop = () => { if (t) { clearTimeout(t); t = null; } }; node.addEventListener("pointerdown", () => { stop(); t = setTimeout(() => { t = null; fn(); }, 650); }); ["pointerup", "pointerleave", "pointercancel", "pointermove"].forEach((e) => node.addEventListener(e, stop)); }
async function setWeapons(extra) {
  const D = S.decl; if (!D) return;
  const aim = {}; for (const [k, v] of Object.entries(D.aim)) aim[k] = v;
  const r = await query({ q: "set", unit: D.req.unit, charge: [...D.charge], aim, ...extra });
  if (r.error) { D.req.error = r.error; declSheet(); return; }
  D.rows = r.weapons; for (const id of [...D.sel]) { const w = D.rows.find((x) => x.id === id); if (!w || !w.in_range) D.sel.delete(id); }
  declSheet(); redraw();
}
function setAim(hex) { const D = S.decl; if (!D || !D.aimFor) return; D.aim[D.aimFor] = hex; D.aimFor = null; setWeapons({}); }

HANDLERS.physical = (r) => {
  S.sel = r.unit;
  sheet(`<h3>${esc(r.name)}: physical attack on ${esc(r.target_name)}</h3>${errLine(r)}<table><tr><th>Attack</th><th>To hit</th><th>Damage</th><th>Heat</th><th></th></tr>${r.kinds.map((k) => k.options.map((o, i) => `<tr><td>${esc(o.name)}</td><td>TN ${o.tn}</td><td>${o.damage}</td><td>${o.heat || ""}</td><td>${i === 0 ? `<button data-act="phys" data-k="${esc(k.kind)}">${esc(k.kind)}</button>` : ""}</td></tr>`).join("")).join("")}</table><div class="row"><button data-act="phys" data-k="">No physical attack</button></div>`);
};

// ---- end phase (switches that matter for the expected heat)
HANDLERS.end_phase = (r) => {
  S.sel = r.unit;
  const e = r.equipment, h = r.heat;
  const jam = (e.jammed || []).map((j) => `<label class="sw"><input type="checkbox" data-act="sw-unjam" data-name="${esc(j.name)}" ${j.unjam ? "checked" : ""}> Try to clear the jam on ${esc(j.name)} next turn (it does not fire that turn)</label>`).join("");
  sheet(`<h3>${esc(r.name)}: before the Heat Phase</h3>${errLine(r)}<div class="msg">Expected heat at the end of the turn: <b class="${h.projected >= 14 ? "err" : h.projected >= 8 ? "warnt" : ""}">${h.projected}</b> (now ${h.now}, movement ${h.movement}, weapons ${h.weapons}, heat sinks take off ${h.sinks}).</div>
    ${e.coolant.pods ? `<div class="sw"><label>Coolant pods (${e.coolant.pods})</label><button class="sm" data-act="sw-cool" data-v="now">Use a pod now</button><button class="sm" data-act="sw-cool" data-v="hold">Hold them</button><button class="sm" data-act="sw-cool" data-v="auto">Automatic</button><span class="msg">now: ${e.coolant.mode}</span></div>` : ""}
    ${e.radical.live ? `<div class="sw"><label>Radical heat sinks</label><button class="sm ${e.radical.on ? "go" : ""}" data-act="sw-rad" data-v="1">On (needs ${e.radical.tn}+)</button><button class="sm ${e.radical.on ? "" : "go"}" data-act="sw-rad" data-v="0">Off</button></div>` : ""}
    ${jam}
    <div class="row"><button class="go" data-act="end-go">Continue</button><button data-act="detail">All switches...</button></div>`);
};

// ---------------------------------------------------------------- detail sheet: Summary, Armour, Criticals, Equipment
let detailTab = "summary";
function openDetail(tab) { detailTab = tab || detailTab; renderDetail(); $("detail").style.display = "flex"; }
function closeDetail() { $("detail").style.display = "none"; }
function renderDetail() {
  const u = unit(S.sel) || S.units[0]; if (!u) return;
  const tabs = [["summary", "Summary"], ["armor", "Armor"], ["crits", "Criticals"], ["equip", "Equipment"]];
  $("detail").innerHTML = `<div class="tabs">${tabs.map(([k, n]) => `<button class="tab ${k === detailTab ? "on" : ""}" data-act="tab" data-t="${k}">${n}</button>`).join("")}<span class="sp" style="flex:1"></span><button class="sm" data-act="detail-close">Close</button></div><div class="body"><div style="margin-bottom:6px"><b>${esc(u.name)}</b> ${esc(u.mech || "")}</div>${detailBody(u)}</div>`;
}
function detailBody(u) {
  if (detailTab === "summary") {
    const eqp = eq(u);
    return `<div class="msg">${u.tons || "?"} tons &middot; gunnery ${u.gunnery} / piloting ${u.piloting} &middot; walk ${u.walk} run ${u.run}${u.jump ? " jump " + u.jump : ""}</div><div class="msg">Heat ${u.heat} &middot; facing ${u.facing} &middot; pilot hits ${u.pilot_hits}${u.prone ? " &middot; PRONE" : ""}${u.shutdown ? " &middot; SHUT DOWN" : ""}</div><div class="msg">Last move: ${esc(u.move_mode || "")}</div>${eqp.auto_eject ? '<div class="msg">Ejection is not built yet (a known shortfall).</div>' : ""}`;
  }
  if (detailTab === "armor") {
    const mx = S.maxLoc[u.id] || {};
    return Object.entries(u.locs || {}).map(([loc, v]) => { const m = mx[loc] || v, a = m[0] ? v[0] / m[0] : 0, s = m[2] ? v[2] / m[2] : 0, ra = m[1] ? v[1] / m[1] : null;
      return `<div class="locrow"><span class="nm">${LOCAB[loc] || loc}</span><div class="bars"><div class="bar2" title="armour"><b style="width:${Math.round(a * 100)}%;background:var(--ok)"></b></div><div class="bar2" title="structure"><b style="width:${Math.round(s * 100)}%;background:${s > 0.5 ? "#8aa" : "var(--err)"}"></b></div>${ra != null ? `<div class="bar2" title="rear armour"><b style="width:${Math.round(ra * 100)}%;background:var(--warn)"></b></div>` : ""}</div><span class="msg">${v[3] ? "destroyed" : `${v[0]}${v[1] ? " (" + v[1] + " rear)" : ""} / ${v[2]}`}</span></div>`; }).join("") + '<div class="msg">Top bar armour, then structure, then rear armour.</div>';
  }
  if (detailTab === "crits") {
    const names = S.critNames[u.id] || {}, alive = u.crit_alive || {};
    return Object.keys(names).map((loc) => `<div><b>${LOCAB[loc] || loc}</b></div><div class="crit">${names[loc].map((n, i) => `<span class="${alive[loc] && alive[loc][i] === false ? "x" : ""}">${esc(n)}</span>`).join("")}</div>`).join("");
  }
  return equipBody(u);
}
function equipBody(u) {
  const e = eq(u), mine = u.team === S.myTeam; if (!mine) return '<div class="msg">The switches of an enemy unit are not yours to set.</div>';
  const headAmmo = ((S.critNames[u.id] || {}).Head || []).some((n) => /ammo/i.test(n));
  const rows = [];
  rows.push(`<div class="sw"><label>Heat sinks off</label><button class="sm" data-act="sw-sinks" data-d="-1">&minus;</button><b>${e.sinks.off}</b> of ${e.sinks.working}<button class="sm" data-act="sw-sinks" data-d="1">+</button><button class="sm" data-act="sw-sinks" data-d="auto">Automatic</button><span class="msg">${e.sinks.chosen ? "set by you" : "automatic"}</span></div>`);
  if (e.coolant.pods) rows.push(`<div class="sw"><label>Coolant pods (${e.coolant.pods})</label>${["auto", "hold", "now"].map((m) => `<button class="sm ${e.coolant.mode === m ? "on" : ""}" data-act="sw-cool" data-v="${m}">${m === "auto" ? "Automatic" : m === "hold" ? "Hold" : "Use when heat is expected"}</button>`).join("")}</div>`);
  if (e.radical.has) rows.push(`<div class="sw"><label>Radical heat sinks</label><button class="sm ${e.radical.on ? "on" : ""}" data-act="sw-rad" data-v="${e.radical.on ? 0 : 1}">${e.radical.on ? "On" : "Off"}</button><span class="msg">${e.radical.live ? "works on " + e.radical.tn + "+" : "destroyed"}</span></div>`);
  if (e.boost.has) rows.push(`<div class="sw"><label>MASC / supercharger</label><button class="sm ${e.boost.on ? "on" : ""}" data-act="sw-boost" data-v="${e.boost.on ? 0 : 1}">${e.boost.on ? "On" : "Off"}</button><span class="msg">works on ${e.boost.tn}+; asked at the start of each move</span></div>`);
  for (const a of e.ams || []) rows.push(`<div class="sw"><label>${esc(a.name)}</label><button class="sm ${a.off ? "" : "on"}" data-act="sw-ams" data-id="${a.id}">${a.off ? "Off" : "On"}</button></div>`);
  if (e.blue_shield.has) rows.push(`<div class="sw"><label>Blue Shield</label><button class="sm ${e.blue_shield.on ? "on" : ""}" data-act="sw-blue" data-v="${e.blue_shield.on ? 0 : 1}">${e.blue_shield.on ? "On" : "Off"}</button></div>`);
  for (const j of e.jammed || []) rows.push(`<div class="sw"><label>${esc(j.name)} jammed</label><button class="sm ${j.unjam ? "on" : ""}" data-act="sw-unjam1" data-name="${esc(j.name)}">${j.unjam ? "Clear it next turn" : "Leave it"}</button></div>`);
  for (const c of e.capacitors || []) rows.push(`<div class="sw"><label>${esc(c.name)} capacitor</label><button class="sm ${c.charge ? "on" : ""}" data-act="sw-cap" data-name="${esc(c.name)}">&#9889; ${c.charge ? "Charge" : "Fire normally"}</button></div>`);
  rows.push(`<div class="sw"><label>Auto eject</label><span class="msg">Ejection is not built yet. ${headAmmo ? '<b class="warnt">&#9888; This unit carries ammunition in the head and auto eject is off.</b>' : ""}</span></div>`);
  return rows.join("") + '<div class="msg">A switch stays as you set it and counts from the next Heat Phase. Switches can be set while a question is waiting.</div>';
}
async function setSwitch(sw, uid) {
  const id = uid ?? S.sel, r = await query({ q: "switches", unit: id, switches: sw });
  if (r.error) { $("detail").querySelector(".body").insertAdjacentHTML("afterbegin", `<div class="err">${esc(r.error)}</div>`); return null; }
  const u = unit(id); if (u) u.equipment = r.equipment;
  if (S.req && S.req.kind === "end_phase") S.req.equipment = r.equipment;
  if ($("detail").style.display === "flex") renderDetail();
  if (S.req && S.req.kind === "end_phase") HANDLERS.end_phase(S.req);
  return r.equipment;
}

// ---------------------------------------------------------------- clicks
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-act]");
  if (t && !(t.tagName === "INPUT" && t.type === "checkbox")) { act(t); return; }
  const chip = e.target.closest(".chip"); if (chip) { S.sel = +chip.dataset.u; redraw(); if ($("detail").style.display === "flex") renderDetail(); return; }
  const un = e.target.closest("[data-unit]"); if (un && !(S.req && S.req.kind === "target" && S.req.enemies.some((x) => x.id === +un.dataset.unit))) { onUnitTap(+un.dataset.unit); return; }
  if (!e.target.closest("#menu") && !e.target.closest("#menu-btn")) $("menu").style.display = "none";
});
document.addEventListener("change", (e) => { const t = e.target; if (t.dataset && t.dataset.act === "fire") { t.checked ? S.decl.sel.add(+t.dataset.id) : S.decl.sel.delete(+t.dataset.id); declSheet(); redraw(); } else if (t.dataset && t.dataset.act === "sw-unjam") { sendUnjam(); } });
function sendUnjam() { const names = [...document.querySelectorAll('[data-act="sw-unjam"]')].filter((c) => c.checked).map((c) => c.dataset.name); setSwitch({ unjam: names }, S.req ? S.req.unit : S.sel); }
function act(t) {
  const d = t.dataset, a = d.act, D = S.decl, r = S.req;
  switch (a) {
    case "card-close": $("card").style.display = "none"; break;
    case "pick-unit": send({ unit: +d.id }); break;
    case "stand": send({ stand: d.v === "1" }); break;
    case "boost": send({ use: d.v === "1" }); break;
    case "spot": send({ target: d.id === "" ? null : +d.id, fires: true }); break;
    case "tag": send(d.id === "" ? { target: null } : { target: +d.id, aim: d.aim }); break;
    case "target": send({ target: d.id === "" ? null : +d.id }); break;
    case "stay": send({ stay: true }); break;
    case "undo": undo(); break;
    case "mode": S.mode = d.m; { const os = S.reachIdx[S.dest].filter((x) => x.mode === S.mode); if (!os.some((x) => x.facing === S.facing)) S.facing = os[0].facing; } moveSheet(); redraw(); loadPath(); break;
    case "commit": send({ hex: S.dest, facing: S.facing, mode: S.mode }); break;
    case "atk": chooseAttack(r.attacks.filter((x) => x.target === S.attackTarget)[+d.i]); break;
    case "atk-yes": send({ attack: S.attackSel }); break;
    case "atk-no": S.attackSel = null; S.attackConfirm = false; S.path = null; attackSheet(r.attacks.filter((x) => x.target === S.attackTarget)); redraw(); break;
    case "focus": D.focus = +d.id; declSheet(); redraw(); break;
    case "mode-w": { const w = D.rows.find((x) => x.id === +d.id), i = w.modes.findIndex((m) => m.selected), next = w.modes[(i + 1) % w.modes.length]; setWeapons({ modes: { [w.id]: next.label } }); break; }
    case "rate-w": { const w = D.rows.find((x) => x.id === +d.id), i = w.rates.findIndex((m) => m.selected), next = w.rates[(i + 1) % w.rates.length]; setWeapons({ shots: { [w.id]: next.shots } }); break; }
    case "charge-w": { const w = D.rows.find((x) => x.id === +d.id); D.charge.has(w.name) ? D.charge.delete(w.name) : (D.charge.add(w.name), D.sel.delete(w.id)); setWeapons({}); break; }
    case "bins-w": D.bin = D.bin === +d.id ? null : +d.id; declSheet(); break;
    case "bin-pick": D.bin = null; setWeapons({ bins: { [d.w]: d.b === "" ? null : +d.b } }); break;
    case "aim-w": D.aimFor = D.aimFor ? null : +d.id; declSheet(); redraw(); break;
    case "alpha": D.rows.forEach((w) => { if (w.in_range && !w.jammed && !D.charge.has(w.name)) D.sel.add(w.id); }); declSheet(); redraw(); break;
    case "clear": D.sel.clear(); declSheet(); redraw(); break;
    case "hold": send({ weapons: [] }); break;
    case "fire-go": { const aim = {}; for (const [k, v] of Object.entries(D.aim)) aim[k] = v; send({ weapons: [...D.sel], charge: [...D.charge], aim }); break; }
    case "phys": send({ kind: d.k === "" ? null : d.k }); break;
    case "end-go": send({}); break;
    case "detail": openDetail("equip"); break;
    case "detail-close": closeDetail(); break;
    case "tab": detailTab = d.t; renderDetail(); break;
    case "sw-cool": setSwitch({ coolant: d.v }); break;
    case "sw-rad": setSwitch({ radical: d.v === "1" }); break;
    case "sw-boost": setSwitch({ boost: d.v === "1" }); break;
    case "sw-blue": setSwitch({ blue_shield: d.v === "1" }); break;
    case "sw-ams": { const u = unit(S.sel), off = (eq(u).ams || []).filter((x) => (x.id === +d.id ? !x.off : x.off)).map((x) => x.id); setSwitch({ ams_off: off }); break; }
    case "sw-unjam1": { const u = unit(S.sel), names = (eq(u).jammed || []).filter((x) => (x.name === d.name ? !x.unjam : x.unjam)).map((x) => x.name); setSwitch({ unjam: names }); break; }
    case "sw-cap": { const u = unit(S.sel), names = (eq(u).capacitors || []).filter((x) => (x.name === d.name ? !x.charge : x.charge)).map((x) => x.name); setSwitch({ charge: names }); break; }
    case "sw-sinks": { const u = unit(S.sel), e = eq(u); if (d.d === "auto") setSwitch({ sinks_off: null }); else setSwitch({ sinks_off: Math.max(0, Math.min(e.sinks.working, e.sinks.off + +d.d)) }); break; }
    case "menu-folder": { const sub = document.querySelector(`#menu .sub[data-f="${d.f}"]`); if (sub) sub.classList.toggle("open"); break; }
    case "look": O.look = d.v; setPref("look", d.v); applyLook(); buildMenu(); break;
    case "cvd": O.cvd = !O.cvd; setPref("cvd", O.cvd ? "1" : "0"); buildMenu(); redraw(); if (S.req && S.req.kind === "movement") { if (S.dest) moveSheet(); } if (S.decl) declSheet(); break;
    case "rings": O.rings = !O.rings; setPref("rings", O.rings ? "1" : "0"); buildMenu(); redraw(); break;
    case "labels": O.labels = !O.labels; setPref("labels", O.labels ? "1" : "0"); buildMenu(); if (S.board) { buildMap(); redraw(); } break;
    case "report": toggleReport(); $("menu").style.display = "none"; break;
    case "lab": location.href = "index.html"; break;
  }
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { undo(); $("card").style.display = "none"; } });

// ---------------------------------------------------------------- the end, the menu, the look
function finish(end) {
  S.over = true; S.units = end.units; S.req = null; S.decl = null;
  if (end.log) { S.log.push(...end.log); $("report").textContent = S.log.join("\n"); }
  setPhase("Battle over");
  redraw();
  sheet(`<h3>Battle over</h3><div class="msg">${end.winner === "Draw" ? "A draw" : esc(end.winner) + " wins"} after ${end.turns} turns. ${end.decisions} decisions recorded.</div><div class="row"><button data-act="report">Show the report</button><button data-act="lab">Back to the Lab</button></div>`);
}
function toggleReport() { const r = $("report"); r.style.display = r.style.display === "block" ? "none" : "block"; r.scrollTop = r.scrollHeight; }
function applyLook() { document.documentElement.setAttribute("data-theme", O.look); document.body.setAttribute("data-theme", O.look); }
function buildMenu() {
  const m = $("menu");
  const item = (label, act, extra, on) => `<div class="item ${on ? "on" : ""}" data-act="${act}" ${extra || ""}>${label}</div>`;
  m.innerHTML = `<div class="f" data-act="menu-folder" data-f="look">Look &#9656;</div><div class="sub open" data-f="look">${Object.entries(LOOKS).map(([k, n]) => item(n, "look", `data-v="${k}"`, O.look === k)).join("")}</div>
    <div class="f" data-act="menu-folder" data-f="view">View &#9656;</div><div class="sub open" data-f="view">${item("Colour-blind mode", "cvd", "", O.cvd)}${item("Range bands for the weapon", "rings", "", O.rings)}${item("Hex numbers", "labels", "", O.labels)}</div>
    <div class="f" data-act="menu-folder" data-f="game">Game &#9656;</div><div class="sub open" data-f="game">${item("Report", "report")}${item("Back to the Lab", "lab")}</div>`;
}
$("menu-btn").onclick = () => { buildMenu(); const m = $("menu"); m.style.display = m.style.display === "block" ? "none" : "block"; };
$("rep-btn").onclick = toggleReport;
$("det-btn").onclick = () => { if ($("detail").style.display === "flex") closeDetail(); else openDetail(); };
window.addEventListener("resize", () => { if (S.board) fit(); });
applyLook();
// The browser build has no server to start the game: the Lab page left the setup for this page (localStorage), which
// starts the battle in its own worker. The desktop Lab starts it itself and passes ?game=N.
async function boot() {
  if (!GAME && window.LAB_WASM) {
    let setup = null;
    try { setup = JSON.parse(localStorage.getItem("bm_play_setup") || "null"); localStorage.removeItem("bm_play_setup"); } catch (e) { /* storage off */ }
    if (setup) {
      $("info").textContent = "Starting the battle...";
      const r = await api("play_start", { setup });
      if (r.error) { setPhase("could not start"); $("info").textContent = r.error; return; }
      GAME = r.game; COLOURS = r.colours || {};
    }
  }
  if (!GAME) { $("info").textContent = "No game: start one from the Lab (set a team to Human, then Play)."; } else { loop(); }
}
boot();
window.__bm = S;
